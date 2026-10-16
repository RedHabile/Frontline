from pathlib import Path
import re
import subprocess
import tempfile

p = Path('index.html')
s = p.read_text()
changes = []

def rep(old, new, desc):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        changes.append(desc)
        return True
    return False

rep(
    "goldBase: 0.1, goldTile: 0.0015, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.35, portGold: 0.15,",
    "goldBase: 0.055, goldTile: 0.0008, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.18, portGold: 0.08,",
    "reduce gold income",
)

marker = "  /* ---------- Connexion aux salons privés multijoueurs ---------- */"
start = s.find(marker)
end = s.find("  var lfSocket", start + len(marker)) if start >= 0 else -1
if start >= 0 and end > start:
    block = s[start:end]
    if "\\n" in block:
        block = block.replace("\\n", "\n")
        s = s[:start] + block + s[end:]
        changes.append("repair escaped multiplayer JavaScript")

double_handler = "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);\n      } else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);"
if double_handler in s:
    s = s.replace(double_handler, "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);", 1)
    changes.append("deduplicate state receiver")

state_block = "    if (lfSocket && lfRoomCode && st.phase === 'play' && lfRoomHost && ts - lfStateSendAt > 220) {\n      lfStateSendAt = ts;\n      if (sim) { lfSendRoomMessage(lfMakeNetState(sim)); if (sim.netChanged) sim.netChanged.length = 0; }\n    }"
double_sender = state_block + "\n" + state_block
if double_sender in s:
    s = s.replace(double_sender, state_block, 1)
    changes.append("deduplicate state sender")
s = s.replace("lfSyncSendAt = 0, lfStateSendAt = 0, lfStateSendAt = 0,", "lfSyncSendAt = 0, lfStateSendAt = 0,")

# Small visual logistics links between every factory and its nearest city/base of the same owner.
road_marker = "    var br = Math.max(cw < 700 ? 3.9 : 4.9, z * 1.15);\n    for (i = 0; i < sim.buildings.length; i++) {"
road_code = """    var br = Math.max(cw < 700 ? 3.9 : 4.9, z * 1.15);
    if (z >= 2.2 && sim.buildings.length > 1) {
      var citiesByOwner = Object.create(null);
      for (i = 0; i < sim.buildings.length; i++) {
        var cb = sim.buildings[i];
        if (cb.type === 'city') (citiesByOwner[cb.owner] || (citiesByOwner[cb.owner] = [])).push(cb);
      }
      ctx.save(); ctx.lineWidth = Math.max(0.7, Math.min(1.5, z * 0.10)); ctx.setLineDash([Math.max(2, z * 0.7), Math.max(2, z * 1.2)]);
      for (i = 0; i < sim.buildings.length; i++) {
        var fb = sim.buildings[i]; if (fb.type !== 'factory') continue;
        var arr = citiesByOwner[fb.owner]; if (!arr || !arr.length) continue;
        var fx0 = fb.tile % W, fy0 = (fb.tile / W) | 0, near = arr[0], nd = Infinity;
        for (var ri = 0; ri < arr.length; ri++) { var cb2 = arr[ri], cx2 = cb2.tile % W, cy2 = (cb2.tile / W) | 0, dd = (cx2-fx0)*(cx2-fx0) + (cy2-fy0)*(cy2-fy0); if (dd < nd) { nd = dd; near = cb2; } }
        var fxp = (fx0 + 0.5) * z + dx, fyp = (fy0 + 0.5) * z + dy, txp = ((near.tile % W) + 0.5) * z + dx, typ = (((near.tile / W) | 0) + 0.5) * z + dy;
        var fp = pl[fb.owner]; ctx.strokeStyle = fp ? 'rgba(' + fp.color.join(',') + ',0.34)' : 'rgba(255,255,255,0.22)';
        ctx.beginPath(); ctx.moveTo(fxp, fyp); ctx.lineTo(txp, typ); ctx.stroke();
      }
      ctx.restore();
    }
    for (i = 0; i < sim.buildings.length; i++) {"""
rep(road_marker, road_code, "add factory-city logistics links")

# Multiplayer hardening layer. It deliberately lives after the game code so it can
# observe the existing socket/state functions without replacing the simulation.
net_marker = "</body>"
if "FrontlineNetGuard" not in s and net_marker in s:
    net_guard = r'''<script>
/* FrontlineNetGuard: anti-désynchronisation côté navigateur. */
(function () {
  'use strict';
  if (window.FrontlineNetGuard) return;
  window.FrontlineNetGuard = true;

  var lastServerSeq = 0;
  var lastStateAt = 0;
  var lastHeartbeatAt = 0;
  var lastResyncAt = 0;
  var rtt = 0;
  var guardTimer = null;
  var originalApply = window.lfApplyNetState;

  function socketOpen() {
    return window.lfSocket && window.lfSocket.readyState === 1 && window.lfRoomCode;
  }
  function send(msg) {
    try {
      if (typeof window.lfSendRoomMessage === 'function') window.lfSendRoomMessage(msg);
      else if (socketOpen()) window.lfSocket.send(JSON.stringify(msg));
    } catch (e) {}
  }
  function isFresh(msg) {
    var seq = Number(msg && msg.serverSeq) || 0;
    if (!seq) return true;
    if (seq <= lastServerSeq && !msg.resync) return false;
    lastServerSeq = seq;
    return true;
  }

  function applyWrapped(msg) {
    if (!isFresh(msg)) return;
    lastStateAt = performance.now();
    if (typeof originalApply === 'function') return originalApply.apply(this, arguments);
  }
  if (typeof originalApply === 'function') window.lfApplyNetState = applyWrapped;

  function requestResync(reason) {
    var now = performance.now();
    if (!socketOpen() || now - lastResyncAt < 1800) return;
    lastResyncAt = now;
    send({ type: 'resync', reason: reason || 'state-timeout', clientSeq: Date.now() & 0x7fffffff });
    if (typeof window.toast === 'function') window.toast('Resynchronisation multijoueur…');
  }

  function guard() {
    if (!socketOpen()) return;
    var now = performance.now();
    if (now - lastHeartbeatAt >= 1000) {
      lastHeartbeatAt = now;
      send({ type: 'heartbeat', clientTime: Date.now() });
    }
    if (window.st && window.st.phase === 'play' && !window.lfRoomHost) {
      if (!lastStateAt) lastStateAt = now;
      if (now - lastStateAt > 3200) requestResync('no-state');
    }
  }

  function start() {
    if (guardTimer) clearInterval(guardTimer);
    lastServerSeq = 0;
    lastStateAt = performance.now();
    guardTimer = setInterval(guard, 250);
  }
  start();

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
      // A backgrounded Safari tab can be throttled. Never let that become
      // permanent network drift: ask the authoritative host for a fresh state.
      lastStateAt = 0;
      requestResync('tab-visible');
    }
  });

  window.addEventListener('online', function () { requestResync('network-online'); });
  window.addEventListener('offline', function () {
    if (typeof window.toast === 'function') window.toast('Connexion perdue — tentative de reconnexion…', 'danger');
  });

  window.addEventListener('beforeunload', function () {
    try { if (window.lfSocket && window.lfSocket.readyState === 1) window.lfSocket.close(1000, 'page closing'); } catch (e) {}
  });
})();
</script>
'''
    s = s.replace(net_marker, net_guard + net_marker, 1)
    changes.append("add multiplayer heartbeat, stale-state rejection and automatic resync")

if "function lfApplyNetState(msg)" not in s:
    raise SystemExit("sync function missing")

scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", s, re.I)
for idx, js in enumerate(scripts):
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(js)
        path = f.name
    result = subprocess.run(['node', '--check', path], capture_output=True, text=True)
    Path(path).unlink(missing_ok=True)
    if result.returncode:
        print(result.stderr)
        raise SystemExit(f'JavaScript syntax check failed for script {idx}')
print('JavaScript syntax OK')

if changes:
    p.write_text(s)
    print('\n'.join(changes))
else:
    print('no changes needed')

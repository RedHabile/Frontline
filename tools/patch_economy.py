from pathlib import Path
import re
import subprocess
import tempfile

p = Path('index.html')
s = p.read_text()
changes = []

# Replace the old factory -> nearest city visual link with links from each factory
# to up to three nearby non-factory buildings owned by the same nation.
start = s.find("    if (z >= 2.2 && sim.buildings.length > 1) {")
if start >= 0:
    end = s.find("    for (i = 0; i < sim.buildings.length; i++) {", start)
    if end > start:
        new_links = """    if (z >= 2.2 && sim.buildings.length > 1) {
      var linksByOwner = Object.create(null);
      for (i = 0; i < sim.buildings.length; i++) {
        var lb = sim.buildings[i];
        if (lb.type !== 'factory') (linksByOwner[lb.owner] || (linksByOwner[lb.owner] = [])).push(lb);
      }
      ctx.save();
      ctx.lineWidth = Math.max(0.65, Math.min(1.35, z * 0.09));
      ctx.setLineDash([Math.max(2, z * 0.65), Math.max(2, z * 1.15)]);
      for (i = 0; i < sim.buildings.length; i++) {
        var factory = sim.buildings[i]; if (factory.type !== 'factory') continue;
        var targets = linksByOwner[factory.owner]; if (!targets || !targets.length) continue;
        var fx0 = factory.tile % W, fy0 = (factory.tile / W) | 0, ranked = [];
        for (var li = 0; li < targets.length; li++) {
          var target = targets[li], tx0 = target.tile % W, ty0 = (target.tile / W) | 0;
          ranked.push({ b: target, d: (tx0-fx0)*(tx0-fx0) + (ty0-fy0)*(ty0-fy0) });
        }
        ranked.sort(function(a,b){ return a.d-b.d; });
        var maxLinks = Math.min(3, ranked.length);
        for (var lk = 0; lk < maxLinks; lk++) {
          var near = ranked[lk].b, nx = near.tile % W, ny = (near.tile / W) | 0;
          var fp = pl[factory.owner];
          ctx.strokeStyle = fp ? 'rgba(' + fp.color.join(',') + ',0.30)' : 'rgba(255,255,255,0.18)';
          ctx.beginPath();
          ctx.moveTo((fx0 + 0.5) * z + dx, (fy0 + 0.5) * z + dy);
          ctx.lineTo((nx + 0.5) * z + dx, (ny + 0.5) * z + dy);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
"""
        s = s[:start] + new_links + s[end:]
        changes.append('link factories to nearby same-owner buildings')

# Add elimination reward logic once, after the existing game code.
if 'FrontlineEliminationGold' not in s:
    marker = '</body>'
    reward = r'''<script>
/* FrontlineEliminationGold: the victor recovers the eliminated nation's gold. */
(function () {
  'use strict';
  if (window.FrontlineEliminationGold) return;
  window.FrontlineEliminationGold = true;

  var previousOwners = null;
  var rewarded = Object.create(null);
  var timer = null;

  function player(id) {
    try { return Array.isArray(window.pl) ? window.pl[id] : window.pl && window.pl[id]; } catch (e) { return null; }
  }
  function ownerArray() {
    try {
      var sim = window.sim;
      if (!sim || typeof W !== 'number' || typeof H !== 'number') return null;
      var total = W * H, best = null, bestScore = -1;
      var keys = Object.keys(sim);
      for (var k = 0; k < keys.length; k++) {
        var v = sim[keys[k]];
        if (!v || typeof v.length !== 'number' || v.length !== total) continue;
        var sample = Math.min(total, 5000), valid = 0, distinct = Object.create(null), distinctCount = 0;
        for (var i = 0; i < sample; i++) {
          var n = Number(v[i]);
          if (!Number.isFinite(n) || n < 0 || Math.floor(n) !== n) continue;
          valid++;
          if (!distinct[n]) { distinct[n] = 1; distinctCount++; }
        }
        var score = valid - distinctCount * 2;
        if (valid > sample * 0.75 && distinctCount > 1 && distinctCount < 128 && score > bestScore) { best = v; bestScore = score; }
      }
      return best;
    } catch (e) { return null; }
  }
  function snapshot() {
    var a = ownerArray();
    if (!a) return null;
    return Array.from(a, Number);
  }
  function hostMayAward() {
    return !window.lfRoomCode || !!window.lfRoomHost;
  }
  function tick() {
    if (!hostMayAward()) return;
    var cur = snapshot();
    if (!cur) return;
    if (!previousOwners) { previousOwners = cur; return; }
    var changedFrom = Object.create(null);
    for (var i = 0; i < cur.length; i++) {
      var oldId = previousOwners[i], newId = cur[i];
      if (oldId !== newId) {
        if (!changedFrom[oldId]) changedFrom[oldId] = Object.create(null);
        changedFrom[oldId][newId] = (changedFrom[oldId][newId] || 0) + 1;
      }
    }
    var counts = Object.create(null);
    for (var j = 0; j < cur.length; j++) counts[cur[j]] = (counts[cur[j]] || 0) + 1;
    var ids = Object.keys(changedFrom);
    for (var x = 0; x < ids.length; x++) {
      var deadId = ids[x], dead = player(deadId);
      if (!dead || rewarded[deadId]) continue;
      if ((counts[deadId] || 0) !== 0) continue;
      var transfers = changedFrom[deadId], killerId = null, best = 0;
      Object.keys(transfers).forEach(function (id) {
        var n = Number(id), amount = transfers[id];
        if (n !== Number(deadId) && amount > best && player(n)) { best = amount; killerId = n; }
      });
      if (killerId === null) continue;
      var killer = player(killerId), amountGold = Number(dead.gold) || 0;
      if (amountGold > 0) {
        killer.gold = (Number(killer.gold) || 0) + amountGold;
        dead.gold = 0;
        rewarded[deadId] = 1;
        if (typeof window.toast === 'function') window.toast('Nation éliminée : +' + Math.floor(amountGold) + ' or récupéré');
      } else {
        rewarded[deadId] = 1;
      }
    }
    previousOwners = cur;
  }
  timer = setInterval(tick, 450);
  tick();
})();
</script>
'''
    if marker in s:
        s = s.replace(marker, reward + marker, 1)
        changes.append('give eliminated nation gold to the victor')

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

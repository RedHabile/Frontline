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


# Balance: territory no longer increases troop production or troop capacity.
rep(
    "growBase: 1.6, growTile: 0.009, growTroop: 0.0009, maxBase: 1800, maxTile: 55,\n    neutralCost: 8.5, defMul: 1.45, defBase: 2, defLoss: 0.3, speedDiv: 17, speedCap: 45, startTroops: 1800,",
    "growBase: 1.25, growTile: 0, growTroop: 0.00065, maxBase: 1800, maxTile: 0,\n    neutralCost: 8.5, defMul: 1.45, defBase: 2, defLoss: 0.3, speedDiv: 17, speedCap: 45, startTroops: 1200,",
    "reduce starting troops and remove territory-based troop growth",
)
rep(
    "cityTroops: 3000, factoryGold: 0.18, portGold: 0.08,",
    "cityTroops: 4500, factoryGold: 0.18, portGold: 0.08,",
    "increase troop capacity provided by each city",
)
rep(
    "function maxTroops(p) { return P.maxBase + p.tiles * P.maxTile + p.count.city * P.cityTroops * (1 + 0.25 * tl(p, 'yBase')) ; }",
    "function maxTroops(p) { return P.maxBase + p.count.city * P.cityTroops * (1 + 0.25 * tl(p, 'yBase')); }",
    "remove territory from troop capacity calculation",
)
rep(
    "p.troops += ((P.growBase + p.tiles * P.growTile + p.troops * P.growTroop) *",
    "p.troops += ((P.growBase + p.troops * P.growTroop) *",
    "remove territory-based troop generation",
)
# OpenFront-style economy: land contributes to troop capacity with diminishing returns,
# cities add a large capacity bonus, and growth slows near the cap using a sublinear troop curve.
rep(
    "function maxTroops(p) { return P.maxBase + p.count.city * P.cityTroops * (1 + 0.25 * tl(p, 'yBase')); }",
    "function maxTroops(p) { return P.maxBase + Math.round(20 * Math.pow(Math.max(0, p.tiles), 0.6)) + p.count.city * P.cityTroops * (1 + 0.25 * tl(p, 'yBase')); }",
    "restore OpenFront-style territory-based troop capacity with diminishing returns",
)
rep(
    "p.troops += ((P.growBase + p.troops * P.growTroop) * (1 - p.troops / max) * P.growMul + (max - p.troops) * P.growRoom)",
    "p.troops += ((P.growBase + Math.pow(Math.max(0, p.troops), 0.73) / 250) * (1 - p.troops / max) * P.growMul + (max - p.troops) * P.growRoom)",
    "use OpenFront-style sublinear troop growth that slows near maximum",
)
# Transfer all remaining gold directly inside the real elimination function.
elim_old = "  Sim.prototype.eliminate = function (victim, killer) {\n    victim.alive = false; victim.troops = 0; victim.label = null;"
elim_new = """  Sim.prototype.eliminate = function (victim, killer) {
    if (killer && killer.id !== victim.id) {
      var recoveredGold = Math.max(0, Number(victim.gold) || 0);
      if (recoveredGold > 0) {
        killer.gold = (Number(killer.gold) || 0) + recoveredGold;
        victim.gold = 0;
        this.events.push({ type: 'goldRecovered', id: victim.id, by: killer.id, amount: recoveredGold });
      }
    }
    victim.alive = false; victim.troops = 0; victim.label = null;"""
rep(elim_old, elim_new, "transfer eliminated nation's gold to its conqueror")
# Remove the old standalone heuristic reward script; the actual simulation now handles elimination.
if "FrontlineEliminationGold" in s:
    start = s.find("<script>\n/* FrontlineEliminationGold:")
    if start >= 0:
        end = s.find("</script>", start)
        if end >= 0:
            s = s[:start] + s[end + len("</script>"):]
            changes.append("remove fragile standalone elimination reward")

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

# Draw logistics connections from each factory to up to three nearby same-owner buildings.
road_marker = "    var br = Math.max(cw < 700 ? 3.9 : 4.9, z * 1.15);\n    for (i = 0; i < sim.buildings.length; i++) {"
road_code = """    var br = Math.max(cw < 700 ? 3.9 : 4.9, z * 1.15);
    if (z >= 2.2 && sim.buildings.length > 1) {
      var linksByOwner = Object.create(null);
      for (i = 0; i < sim.buildings.length; i++) {
        var lb = sim.buildings[i];
        if (lb.type !== 'factory') (linksByOwner[lb.owner] || (linksByOwner[lb.owner] = [])).push(lb);
      }
      ctx.save();
      ctx.lineWidth = Math.max(0.65, Math.min(1.35, z * 0.09));
      ctx.setLineDash([Math.max(2, z * 0.65), Math.max(2, z * 1.15)]);
      for (i = 0; i < sim.buildings.length; i++) {
        var factory = sim.buildings[i];
        if (factory.type !== 'factory') continue;
        var targets = linksByOwner[factory.owner];
        if (!targets || !targets.length) continue;
        var fx0 = factory.tile % W, fy0 = (factory.tile / W) | 0, ranked = [];
        for (var li = 0; li < targets.length; li++) {
          var target = targets[li], tx0 = target.tile % W, ty0 = (target.tile / W) | 0;
          ranked.push({ b: target, d: (tx0 - fx0) * (tx0 - fx0) + (ty0 - fy0) * (ty0 - fy0) });
        }
        ranked.sort(function (a, b) { return a.d - b.d; });
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
    for (i = 0; i < sim.buildings.length; i++) {"""
rep(road_marker, road_code, "link factories to nearby same-owner buildings")

# The elimination reward is handled by Sim.prototype.eliminate above.

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

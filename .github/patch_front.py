from pathlib import Path
import re

path = Path('index.html')
s = path.read_text(encoding='utf-8')

new_process = r'''  Sim.prototype._processAttack = function (a) {
    var o = this.players[a.owner];
    if (!o || !o.alive) { a.active = false; return; }
    var tgt = a.target ? this.players[a.target] : null;
    if (tgt && !tgt.alive) { this.finish(a, 'done'); return; }

    // Full contact front: every defender tile touching the attacker is eligible.
    var front = [];
    var marked = new Set();
    var owner = this.owner, terrain = this.terrain;
    o.border.forEach(function (b) {
      var x = b % W, y = (b / W) | 0, n;
      if (x > 0) { n = b - 1; if (terrain[n] > 0 && owner[n] === a.target && !marked.has(n)) { marked.add(n); front.push(n); } }
      if (x < W - 1) { n = b + 1; if (terrain[n] > 0 && owner[n] === a.target && !marked.has(n)) { marked.add(n); front.push(n); } }
      if (y > 0) { n = b - W; if (terrain[n] > 0 && owner[n] === a.target && !marked.has(n)) { marked.add(n); front.push(n); } }
      if (y < H - 1) { n = b + W; if (terrain[n] > 0 && owner[n] === a.target && !marked.has(n)) { marked.add(n); front.push(n); } }
    });

    if (!front.length) { this.finish(a, a.gained === 0 ? 'weak' : 'done'); return; }
    front.sort(function (aa, bb) { return aa - bb; });
    if (a.frontCursor === undefined) a.frontCursor = 0;
    a.frontCursor = a.frontCursor % front.length;

    // Much stronger troop advantage = much faster visual advance.
    var defenderForce = tgt ? Math.max(1, tgt.troops) : 1;
    var ratio = tgt ? a.troops / defenderForce : 3.0;
    var ratioBoost = Math.pow(Math.max(0.15, ratio), 0.72);
    var stackBoost = Math.pow(Math.max(0.25, a.troops / 1800), 0.22);
    var speed = 0.75 + 1.15 * ratioBoost * stackBoost;
    speed = Math.max(0.55, Math.min(P.speedCap, speed));
    a.acc = (a.acc || 0) + speed;
    var budget = Math.floor(a.acc);
    a.acc -= budget;

    while (budget-- > 0 && front.length) {
      if (a.frontCursor >= front.length) a.frontCursor %= front.length;
      // Spread the captures around the whole current front instead of following one path.
      var stride = Math.max(1, Math.floor(front.length / Math.max(1, Math.min(8, budget + 1))));
      var idx = (a.frontCursor + stride) % front.length;
      var t = front[idx];
      a.frontCursor = (idx + Math.max(1, stride)) % Math.max(1, front.length);

      if (owner[t] !== a.target || terrain[t] <= 0 || this._friendly(t, a.owner) === 0) {
        front.splice(idx, 1);
        continue;
      }

      var mag = MAG[terrain[t]], atkLoss, defLoss = 0;
      if (tgt) {
        var dens = tgt.troops / Math.max(1, tgt.tiles);
        var localRatio = tgt.troops / Math.max(1, a.troops);
        var lossRatio = Math.max(0.42, Math.min(1.65, localRatio));
        atkLoss = dens * mag * P.defMul * lossRatio + P.defBase * Math.max(0.52, Math.min(1.35, localRatio));
        defLoss = dens * P.defLoss;
        if (tgt.defs.length) {
          var tx = t % W, ty = (t / W) | 0, R2 = P.defRadius * P.defRadius;
          for (var di = 0; di < tgt.defs.length; di++) {
            var ddx = (tgt.defs[di] % W) - tx, ddy = ((tgt.defs[di] / W) | 0) - ty;
            if (ddx * ddx + ddy * ddy <= R2) {
              var dl = 1 + 0.25 * tl(tgt, 'dDef');
              atkLoss *= 1 + (P.defAtk - 1) * dl;
              defLoss *= Math.max(0.15, P.defDef / dl);
              break;
            }
          }
        }
      } else {
        atkLoss = P.neutralCost * mag;
      }

      if (a.troops < atkLoss) { this.finish(a, a.gained === 0 ? 'weak' : 'done'); return; }
      a.troops -= atkLoss;
      if (tgt) tgt.troops = Math.max(0, tgt.troops - defLoss);
      this.setOwner(t, a.owner);
      a.gained++;

      var x = t % W, y = (t / W) | 0;
      if (a.cx < 0) { a.cx = x; a.cy = y; }
      else { a.cx += (x - a.cx) * 0.12; a.cy += (y - a.cy) * 0.12; }

      if (tgt && tgt.tiles === 0) { this.eliminate(tgt, o); this.finish(a, 'done'); return; }

      // Rebuild the full front after each captured pixel so the advance stays broad.
      front = [];
      marked = new Set();
      o.border.forEach(function (b) {
        var bx = b % W, by = (b / W) | 0, nn;
        if (bx > 0) { nn = b - 1; if (terrain[nn] > 0 && owner[nn] === a.target && !marked.has(nn)) { marked.add(nn); front.push(nn); } }
        if (bx < W - 1) { nn = b + 1; if (terrain[nn] > 0 && owner[nn] === a.target && !marked.has(nn)) { marked.add(nn); front.push(nn); } }
        if (by > 0) { nn = b - W; if (terrain[nn] > 0 && owner[nn] === a.target && !marked.has(nn)) { marked.add(nn); front.push(nn); } }
        if (by < H - 1) { nn = b + W; if (terrain[nn] > 0 && owner[nn] === a.target && !marked.has(nn)) { marked.add(nn); front.push(nn); } }
      });
      if (!front.length) { this.finish(a, 'done'); return; }
    }
  };

'''

pattern = re.compile(r"  Sim\.prototype\._processAttack = function \(a\) \{.*?\n  \};\n\n  /\* ---------- Bots ---------- \*/", re.S)
s2, n = pattern.subn(new_process + "  /* ---------- Bots ---------- */", s, count=1)
if n != 1:
    raise SystemExit('Could not locate _processAttack; no changes made')
if s2 == s:
    raise SystemExit('No changes were produced')
path.write_text(s2, encoding='utf-8')
print('Patched full-front invasion algorithm')

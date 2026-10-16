from pathlib import Path
import re

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

# Economy: deliberately slower gold generation.
rep(
    "goldBase: 0.1, goldTile: 0.0015, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.35, portGold: 0.15,",
    "goldBase: 0.055, goldTile: 0.0008, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.18, portGold: 0.08,",
    "reduce gold income",
)

# Keep one network change buffer only.
s = s.replace("this.changed = []; this.netChanged = []; this.netChanged = [];", "this.changed = []; this.netChanged = [];")

# The previous attempt inserted the sync function as literal \\n characters. Remove that malformed block.
malformed = re.compile(r"(  /\* ---------- Connexion aux salons privés multijoueurs ---------- \*/)\\n  function lfApplyNetState[\\s\\S]*?\\n  }\\n\\n  var lfSocket", re.M)
if malformed.search(s):
    s = malformed.sub(r"\1\n  var lfSocket", s, count=1)
    changes.append('remove malformed sync block')

# Insert a real authoritative state synchronizer immediately before the room socket variables.
if "function lfApplyNetState" not in s:
    marker = "  var lfSocket = null, lfRoomCode = '', lfPlayerId = '', lfRoomHost = false, lfRoomPlayers = [];"
    insert = '''  function lfApplyNetState(msg) {
    var sim = st.sim; if (!sim || !msg || !Array.isArray(msg.players)) return;
    if (Number.isFinite(msg.tick)) { sim.tick = msg.tick; lfHostTick = msg.tick; lfLastHostSyncAt = performance.now(); }
    if (typeof msg.paused === 'boolean') { lfHostPaused = msg.paused; if (st.paused !== msg.paused) setPaused(msg.paused, true); }
    var changes = Array.isArray(msg.tiles) ? msg.tiles : [];
    for (var i = 0; i < changes.length; i++) { var c = changes[i]; if (Array.isArray(c) && c.length >= 2 && c[0] >= 0 && c[0] < sim.owner.length) sim.setOwner(c[0], c[1] | 0); }
    for (var pi = 0; pi < msg.players.length; pi++) {
      var src = msg.players[pi], dst = sim.players[src.id]; if (!dst) continue;
      ['tiles','sx','sy','peak','troops','gold','alive','spawned','spawnX','spawnY','traitor','aggr','nextThink','isolated','level'].forEach(function(k){ if (src[k] !== undefined) dst[k] = src[k]; });
      if (src.count) dst.count = Object.assign({}, src.count);
      if (src.tech) dst.tech = Object.assign({}, src.tech);
      dst.research = src.research ? Object.assign({}, src.research) : null;
      if (Array.isArray(src.allies)) dst.allies = new Set(src.allies);
      if (src.lastHit) dst.lastHit = Object.assign({}, src.lastHit);
    }
    if (Array.isArray(msg.buildings)) {
      sim.buildings = msg.buildings.map(function(b){ return Object.assign({},b); });
      sim.bmap = new Map(); sim.buildings.forEach(function(b){ sim.bmap.set(b.tile,b); });
      for (var id = 1; id < sim.players.length; id++) if (sim.players[id]) { sim.players[id].defs=[]; sim.players[id].sams=[]; }
      sim.buildings.forEach(function(b){ var p=sim.players[b.owner]; if(p){ if(b.type==='def') p.defs.push(b.tile); if(b.type==='sam') p.sams.push(b.tile); } });
    }
    if (Array.isArray(msg.ships)) sim.ships = msg.ships.map(function(x){ return Object.assign({},x); });
    if (Array.isArray(msg.boats)) sim.boats = msg.boats.map(function(x){ return Object.assign({},x, {path:Array.isArray(x.path)?x.path.slice():[]}); });
    if (Array.isArray(msg.bombs)) sim.bombs = msg.bombs.map(function(x){ return Object.assign({},x); });
    if (Array.isArray(msg.planes)) sim.planes = msg.planes.map(function(x){ return Object.assign({},x); });
    if (Number.isInteger(msg.nextBid)) sim.nextBid = Math.max(sim.nextBid,msg.nextBid);
    sim.netChanged.length = 0;
    sim.updateLabels();
  }

  function lfMakeNetState(sim) {
    var tiles = [], seen = Object.create(null);
    if (sim.netChanged) for (var i=0;i<sim.netChanged.length;i++) { var t=sim.netChanged[i]; if (seen[t]) continue; seen[t]=1; tiles.push([t,sim.owner[t]]); }
    var players = [];
    for (var i=1;i<sim.players.length;i++) {
      var p=sim.players[i]; if(!p) continue;
      players.push({id:p.id,tiles:p.tiles,sx:p.sx,sy:p.sy,peak:p.peak,troops:p.troops,gold:p.gold,alive:p.alive,spawned:p.spawned,spawnX:p.spawnX,spawnY:p.spawnY,traitor:p.traitor,aggr:p.aggr,nextThink:p.nextThink,isolated:p.isolated,level:p.level,count:p.count,tech:p.tech,research:p.research,allies:Array.from(p.allies),lastHit:p.lastHit});
    }
    return {type:'state',tick:sim.tick,paused:!!st.paused,tiles:tiles,players:players,buildings:sim.buildings.map(function(b){return Object.assign({},b);}),ships:sim.ships.map(function(x){return Object.assign({},x,{path:null,firing:null});}),boats:sim.boats.map(function(x){return Object.assign({},x,{path:Array.isArray(x.path)?x.path.slice():[]});}),bombs:sim.bombs.map(function(x){return Object.assign({},x);}),planes:sim.planes.map(function(x){return Object.assign({},x);}),nextBid:sim.nextBid};
  }
'''
    s = s.replace(marker, insert + "\n" + marker, 1)
    changes.append('add authoritative multiplayer state sync')

# Remove duplicated state handler if the earlier patch inserted it twice.
double_handler = "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);\n      } else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);"
rep(double_handler, "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);", 'deduplicate state handler')

# Keep exactly one authoritative state-send block.
state_block = "    if (lfSocket && lfRoomCode && st.phase === 'play' && lfRoomHost && ts - lfStateSendAt > 220) {\n      lfStateSendAt = ts;\n      if (sim) { lfSendRoomMessage(lfMakeNetState(sim)); if (sim.netChanged) sim.netChanged.length = 0; }\n    }"
while s.count(state_block) > 1:
    s = s.replace(state_block + "\n" + state_block, state_block, 1)
    changes.append('deduplicate state sender')

# Avoid duplicate timer declaration.
s = s.replace("lfSyncSendAt = 0, lfStateSendAt = 0, lfStateSendAt = 0,", "lfSyncSendAt = 0, lfStateSendAt = 0,")

if changes:
    p.write_text(s)
    print('\n'.join(changes))
else:
    print('no changes needed')

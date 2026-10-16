from pathlib import Path

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

# Gold income is intentionally slower.
rep(
    "goldBase: 0.1, goldTile: 0.0015, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.35, portGold: 0.15,",
    "goldBase: 0.055, goldTile: 0.0008, startGold: 200,\n    cityTroops: 3000, factoryGold: 0.18, portGold: 0.08,",
    "reduce gold income",
)

# Normalize the multiplayer block: an earlier patch accidentally wrote literal \\n escape sequences into the JavaScript source.
marker = "  /* ---------- Connexion aux salons privés multijoueurs ---------- */"
start = s.find(marker)
end = s.find("  var lfSocket", start + len(marker)) if start >= 0 else -1
if start >= 0 and end > start:
    block = s[start:end]
    if "\\n" in block:
        block = block.replace("\\n", "\n")
        s = s[:start] + block + s[end:]
        changes.append("repair escaped multiplayer JavaScript")

# Remove duplicated state receiver.
double_handler = "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);\n      } else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);"
if double_handler in s:
    s = s.replace(double_handler, "} else if (msg.type === 'state' && msg.from !== lfPlayerId && st.sim && st.phase === 'play') {\n        lfApplyNetState(msg);", 1)
    changes.append("deduplicate state receiver")

# Remove duplicated authoritative sender.
state_block = "    if (lfSocket && lfRoomCode && st.phase === 'play' && lfRoomHost && ts - lfStateSendAt > 220) {\n      lfStateSendAt = ts;\n      if (sim) { lfSendRoomMessage(lfMakeNetState(sim)); if (sim.netChanged) sim.netChanged.length = 0; }\n    }"
double_sender = state_block + "\n" + state_block
if double_sender in s:
    s = s.replace(double_sender, state_block, 1)
    changes.append("deduplicate state sender")

s = s.replace("lfSyncSendAt = 0, lfStateSendAt = 0, lfStateSendAt = 0,", "lfSyncSendAt = 0, lfStateSendAt = 0,")

# Ensure the authoritative function exists in normal source form.
if "function lfApplyNetState(msg)" not in s:
    raise SystemExit("sync function missing after repair")

if changes:
    p.write_text(s)
    print('\n'.join(changes))
else:
    print('no changes needed')

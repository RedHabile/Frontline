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
if "function lfApplyNetState(msg)" not in s:
    raise SystemExit("sync function missing")

# Validate every inline JavaScript block before allowing the workflow to commit it.
scripts = re.findall(r"<script[^>]*>([\\s\\S]*?)</script>", s, re.I)
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

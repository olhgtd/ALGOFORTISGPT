from pathlib import Path

path = Path("dashboard/web/scripts/user-action-control-smoke.mjs")
text = path.read_text(encoding="utf-8")
old = '''      const [, , , , deploymentId, action] = p.split("/");
      const nextStatus = action === "pause" ? "PAUSED" : action === "resume" ? "DEPLOYED" : "STOPPED";
'''
new = '''      const parts = p.split("/");
      const deploymentId = parts[5];
      const action = parts[6];
      const nextStatus = action === "pause" ? "PAUSED" : action === "resume" ? "DEPLOYED" : "STOPPED";
'''
if old not in text:
    raise SystemExit("smoke deployment parser marker not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

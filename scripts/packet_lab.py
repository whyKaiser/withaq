"""Build and run a disposable packet lab without host binds, ports or external networking."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
subprocess.run(["docker", "build", "-f", "lab/Dockerfile", "-t", "withaq-packet-lab:local", "."], cwd=root, check=True)
result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--cap-add", "NET_ADMIN", "--cap-add", "SYS_ADMIN",
                         "--sysctl", "net.ipv4.ip_forward=1", "withaq-packet-lab:local"], cwd=root, capture_output=True, text=True)
if result.returncode:
    print(result.stderr[-2000:])
    raise SystemExit("Packet lab failed; no successful evidence recorded")
report = json.loads(result.stdout)
report["recorded_at"] = datetime.now(timezone.utc).isoformat()
report["code_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
report["working_tree_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
report["image_id"] = subprocess.check_output(["docker", "image", "inspect", "withaq-packet-lab:local", "--format", "{{.Id}}"], text=True).strip()
output = root / "artifacts/packet-lab.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report["checks"], indent=2))
print("Packet evidence:", output)

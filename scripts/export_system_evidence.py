"""Export token-free lab state and packet receipts. Use synthetic data only."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="artifacts/system-evidence.json")
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
token = (root / "data/local-access.txt").read_text(encoding="utf-8").strip()
with httpx.Client(timeout=10, trust_env=False) as client:
    response = client.get("http://127.0.0.1:8000/v1/state", headers={"Authorization": "Bearer " + token})
    response.raise_for_status()
    state = response.json()
report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "mode": "synthetic-lab-state-with-optional-real-packet-receipts",
          "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
          "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root)), "state": state}
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("Token-free evidence:", output)

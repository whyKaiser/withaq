"""Export reproducible synthetic decision and guard evidence; never benchmark packets."""
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from withaq.planner import solve
from withaq.scenarios import scenarios
from withaq.store import Store
from withaq.validator import validate


def collect():
    repo = Path(__file__).resolve().parent.parent
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    rows = []
    for snapshot in scenarios().values():
        plan = solve(snapshot)
        rows.append({"scenario": snapshot.id, "plan": plan.model_dump(mode="json"), "validation": validate(snapshot, plan).model_dump(mode="json")})
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "evidence.sqlite3")
        run = store.create("separable", "mfsc", str(uuid4()))
        for action in ("apply", "revoke", "complete-late", "recover"):
            run = store.mutate(run["id"], action, run["version"], str(uuid4()))
        run = store.mutate(run["id"], "inspect", run["version"], str(uuid4()), {
            "artifact": "T2b", "destination": "mock://review", "account": "demo", "purpose": "competition-demo"})
        request = run["command_result"]["request"]
        body = {"request_id": request["id"], "payload_hash": request["payload_hash"]}
        for action in ("approve", "dispatch"):
            run = store.mutate(run["id"], action, run["version"], str(uuid4()), body)
    return {"mode": "simulation", "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": revision.stdout.strip() if revision.returncode == 0 else "uncommitted-initial-tree",
            "python": sys.version.split()[0], "platform": platform.system(), "fixture_set": "deterministic-v1",
            "scope": "Six deterministic finite models and one local mock journey; no packet or 300-setting benchmark.",
            "decisions": rows, "journey": run}


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/demo-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(collect(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Simulation evidence: {output}")

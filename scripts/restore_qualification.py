"""Qualification in NEW disposable databases; never restore over the team's live database."""
import json
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from withaq.database import migrate
from withaq.engine import Engine
from withaq.restore import sign_ledger, reconcile
from withaq.store import DomainError

root = Path(__file__).resolve().parent.parent
values = json.loads((root / "data/local-credentials.json").read_text(encoding="utf-8"))
base_url = "postgresql+psycopg://withaq:" + values["postgres"] + "@127.0.0.1:55432/"
prefix = "restore_" + uuid4().hex
source_db, target_db = prefix + "_source", prefix + "_target"
admin = create_engine(base_url + "postgres", isolation_level="AUTOCOMMIT", hide_parameters=True)
engines = []
checks = {}
output = root / "artifacts/restore-qualification.json"
output.parent.mkdir(exist_ok=True)
container = subprocess.check_output(["docker", "compose", "-f", "compose.dev.yml", "ps", "-q", "db"], cwd=root, text=True).strip()
if not container:
    raise SystemExit("Start the project's PostgreSQL container first")
try:
    with admin.connect() as db:
        for name in (source_db, target_db):
            db.execute(text('CREATE DATABASE "' + name + '"'))
    migrate(base_url + source_db)
    source = Engine(base_url + source_db)
    engines.append(source)
    version = lambda engine: engine.state()["version"]
    r1 = source.create_record("roots", {"label": "S1 synthetic restore test"}, version(source), str(uuid4()))["id"]
    a1 = source.create_artifact({"label": "old artifact", "payload": "Synthetic restore qualification input", "root_ids": [r1], "parent_ids": []}, version(source), str(uuid4()))["id"]
    run = source.create_run({"label": "pending output", "task": "summary", "replacement_for": None,
        "inputs": [{"artifact_id": a1, "role": "source"}]}, version(source), str(uuid4()))
    # Backup BEFORE revocation, intentionally making restored roots older than the trusted ledger.
    dumped = subprocess.run(["docker", "exec", container, "pg_dump", "-U", "withaq", "-d", source_db, "-Fc"], capture_output=True, check=True).stdout
    source.revoke(r1, "newer than backup", version(source), str(uuid4()))
    key = secrets.token_urlsafe(32)
    signed = sign_ledger(source.state(), key)
    subprocess.run(["docker", "exec", "-i", container, "pg_restore", "-U", "withaq", "-d", target_db, "--exit-on-error"], input=dumped, capture_output=True, check=True)
    restored = Engine(base_url + target_db)
    engines.append(restored)
    checks["old_snapshot_root_was_active"] = restored.state()["roots"][0]["status"] == "ACTIVE"
    invalid = {**signed, "signature": "0" * 64}
    try:
        reconcile(restored, invalid, key)
    except DomainError:
        checks["tampered_ledger_rejected"] = True
    reconcile(restored, signed, key)
    checks["newer_barrier_restored_before_resume"] = restored.state()["roots"][0]["status"] == "REVOKED"
    try:
        restored.read_artifact(a1)
    except DomainError:
        checks["old_artifact_read_denied"] = True
    job = restored.claim("restored-worker", ("MODEL",))
    receipt = {name: job[name] for name in ("attempt_id", "fence", "worker_id")}
    try:
        restored.job_inputs(job["id"], **receipt)
    except DomainError:
        checks["restored_pending_run_guarded"] = True
    checks["pending_outbox_preserved"] = job["entity_id"] == run["id"]
    checks["migration_head_restored"] = restored.db.ready()
    report = {"mode": "postgresql-old-backup-plus-newer-authenticated-ledger", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root)),
              "synthetic_only": True, "checks": checks, "dump_bytes": len(dumped),
              "limits": "Operator-selected latest trusted ledger; no automatic off-host ledger replication or freshness authority."}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if len(checks) != 7 or not all(checks.values()):
        raise SystemExit("Restore qualification failed")
finally:
    for engine in engines:
        engine.db.engine.dispose()
    # Only the two UUID-named databases created by THIS invocation are removed.
    with admin.connect() as db:
        for name in (source_db, target_db):
            db.execute(text('DROP DATABASE IF EXISTS "' + name + '" WITH (FORCE)'))
    admin.dispose()

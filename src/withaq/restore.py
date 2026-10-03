"""Restore admission: authenticated newer revocation ledger before resuming any jobs.

HMAC keys and the trusted ledger must live outside the restored database. This helper
does not prove freshness by itself; the operator must select the newest trusted ledger.
"""
import hashlib
import hmac
from uuid import uuid4

from sqlalchemy import insert, update

from . import schema as s
from .store import DomainError, digest


def sign_ledger(state, key):
    ledger = {"schema": state["schema"], "barriers": [
        {"root_id": root["id"], "version": root["version"]} for root in state["roots"] if root["status"] == "REVOKED"]}
    signature = hmac.new(key.encode(), digest(ledger).encode(), hashlib.sha256).hexdigest()
    return {"ledger": ledger, "signature": signature}


def reconcile(engine, signed, key):
    ledger = signed["ledger"]
    expected = hmac.new(key.encode(), digest(ledger).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signed["signature"]) or ledger["schema"] != "0003":
        raise DomainError("UNTRUSTED_REVOCATION_LEDGER", 403)
    with engine.db.transaction() as db:
        for barrier in sorted(ledger["barriers"], key=lambda row: row["root_id"]):
            root = engine._get(db, s.roots, barrier["root_id"])
            if barrier["version"] < 2:
                raise DomainError("INVALID_REVOCATION_BARRIER", 403)
            if root["status"] == "REVOKED" and root["version"] >= barrier["version"]:
                continue
            db.execute(update(s.roots).where(s.roots.c.id == root["id"]).values(status="REVOKED", version=max(root["version"], barrier["version"])))
            identity = str(uuid4())
            db.execute(insert(s.revocations).values(id=identity, root_id=root["id"], barrier_version=barrier["version"], reason="Trusted ledger reconciled before resume", at=engine.clock()))
            engine._event(db, "RESTORE_BARRIER_RECONCILED", root_id=root["id"], barrier_version=barrier["version"])
            engine._job(db, "REVOKE", identity)
        db.execute(update(s.workspace).values(version=s.workspace.c.version + 1))
    return {"reconciled": len(ledger["barriers"])}

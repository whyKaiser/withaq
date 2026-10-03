"""Narrow loopback broker for disposable network-none packet trials.

No arbitrary commands, host volumes, host network or Docker socket inside the lab.
Only this broker has access to the local Docker CLI. Signed receipts bind measured
results to exact plans. These trials are ephemeral synthetic devices, not production IoT.
"""
import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Model, Plan, Snapshot
from .store import digest
from .validator import validate


class Trial(Model):
    snapshot: Snapshot
    candidate: Plan


def supported(snapshot):
    if set(snapshot.nodes) != {"G", "X", "P", "M", "A"} or snapshot.attack_sources != ("G",) or snapshot.protected_targets != ("P",):
        return False
    action_edges = {"a": {("G", "P")}, "b": {("G", "X")}, "c": {("G", "P"), ("G", "X"), ("G", "M"), ("G", "A")}, "d": {("X", "P")}}
    for action in snapshot.actions:
        if action.id not in action_edges or {(e.source, e.target) for e in action.blocks} != action_edges[action.id]:
            return False
    for hypothesis in snapshot.hypotheses:
        if {(e.source, e.target) for e in hypothesis.attack_edges} != {("G", "P"), ("G", "X"), ("X", "P")}:
            return False
        if not {(e.source, e.target) for e in hypothesis.function_edges} <= {("G", "M"), ("G", "A"), ("G", "X")}:
            return False
        if any(c.source != "G" or c.target not in ("M", "A", "X") for c in hypothesis.contracts):
            return False
    return True


def receipt_signature(receipt, secret):
    return hmac.new(secret.encode(), digest(receipt).encode(), hashlib.sha256).hexdigest()


def create_app():
    app = FastAPI(title="WITHAQ isolated packet broker")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    token = os.environ.get("WITHAQ_PEP_TOKEN", "")
    signing_key = os.environ.get("WITHAQ_PEP_SIGNING_KEY", "")

    @app.get("/health/live")
    def live():
        return {"service": "isolated-packet-broker", "ready": bool(token and signing_key)}

    @app.post("/v1/trials")
    def trial(body: Trial, authorization: str = Header(default="")):
        scheme, _, supplied = authorization.partition(" ")
        if not token or not signing_key or scheme != "Bearer" or not hmac.compare_digest(supplied, token):
            raise HTTPException(403, detail="PEP_ROLE_DENIED")
        if not validate(body.snapshot, body.candidate).accepted:
            raise HTTPException(409, detail="VALIDATION_REJECTED")
        if not supported(body.snapshot):
            raise HTTPException(422, detail="UNSUPPORTED_PACKET_MODEL")
        root = Path(__file__).resolve().parents[2]
        try:
            result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--cap-add", "NET_ADMIN", "--cap-add", "SYS_ADMIN",
                "--sysctl", "net.ipv4.ip_forward=1", "--env", "WITHAQ_PLAN_ACTIONS=" + json.dumps(list(body.candidate.actions)),
                "withaq-packet-lab:local"], cwd=root, capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise HTTPException(409, detail="PACKET_TRIAL_FAILED")
            report = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            raise HTTPException(503, detail="PACKET_LAB_UNAVAILABLE")
        contracts = {}
        for hypothesis in body.snapshot.hypotheses:
            for contract in hypothesis.contracts:
                measurements = report["cases"]["mfsc_after"][contract.target.lower()]["records"]
                contracts[hypothesis.id + ":" + contract.id] = all(
                    record["delivered"] and record["latency_s"] <= contract.max_latency_s and
                    record.get("freshness_s", float("inf")) <= contract.max_age_s for record in measurements)
        if any(not contracts[h.id + ":" + c.id] for h in body.snapshot.hypotheses for c in h.contracts if c.critical):
            raise HTTPException(409, detail="MEASURED_FUNCTION_CONTRACT_FAILED")
        receipt = {"status": "LAB_CONFIRMED", "plan_hash": digest(body.candidate.model_dump(mode="json")),
                   "snapshot_hash": digest(body.snapshot.model_dump(mode="json")), "actions": list(body.candidate.actions),
                   "measured_packets": True, "contracts": contracts, "evidence": report}
        return {"receipt": receipt, "signature": receipt_signature(receipt, signing_key)}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8004, access_log=False)

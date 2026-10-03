"""HTTP-only durable worker. It never imports the database or authoritative engine."""
import os
import time
import threading
from contextlib import contextmanager
from uuid import uuid4

import httpx

from .models import Snapshot
from .planner import solve
from .store import digest


@contextmanager
def renewing_lease(client, identity, receipt):
    stopped = threading.Event()
    def renew():
        while not stopped.wait(5):
            try:
                client.post(f"/internal/jobs/{identity}/heartbeat", json=receipt).raise_for_status()
            except httpx.HTTPError:
                return  # Completion still must pass the authoritative fence/expiry checks.
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


def process(client, lease, validator_url, validator_token):
    identity = lease["id"]
    receipt = {key: lease[key] for key in ("attempt_id", "fence", "worker_id")}
    response = client.post(f"/internal/jobs/{identity}/inputs", json=receipt)
    if response.status_code != 200:
        result = {"error": "INPUT_GUARD_DENIED"}
    else:
        inputs = response.json()
        if lease["kind"] == "PLAN":
            snapshot = Snapshot.model_validate(inputs["snapshot"])
            candidate = solve(snapshot).model_dump(mode="json")
            with httpx.Client(timeout=5, trust_env=False) as validation:
                checked = validation.post(validator_url + "/v1/validate", json={"snapshot": inputs["snapshot"], "candidate": candidate},
                                          headers={"Authorization": "Bearer " + validator_token})
                checked.raise_for_status()
            report = checked.json()
            if report["plan_hash"] != digest(candidate):
                raise ValueError("VALIDATION_BINDING_MISMATCH")
            result = {"candidate": candidate, "snapshot_hash": report["snapshot_hash"], "verdict": report["verdict"]}
        elif lease["kind"] == "MODEL":
            # Local mock: exact manifest bytes only, no hidden prompts or tool calls.
            time.sleep(min(max(inputs.get("delay_s", 0), 0), 10))
            payload = "WITHAQ " + inputs["task"].upper() + "\n" + "\n".join(item["payload"] for item in inputs["inputs"])
            result = {"payload": payload, "manifest_hash": inputs["manifest_hash"]}
        elif lease["kind"] == "APPLY":
            if inputs.get("adapter") == "packet-lab":
                with renewing_lease(client, identity, receipt), httpx.Client(timeout=50, trust_env=False) as broker:
                    checked = broker.post(os.environ.get("WITHAQ_PEP_URL", "http://127.0.0.1:8004") + "/v1/trials",
                        headers={"Authorization": "Bearer " + os.environ.get("WITHAQ_PEP_TOKEN", "")},
                        json={"snapshot": inputs["snapshot"], "candidate": inputs["candidate"]})
                    checked.raise_for_status()
                    result = checked.json()
            else:
                result = {"status": "SIMULATED_CONFIRMED", "plan_hash": inputs["plan_hash"],
                          "actions": inputs["candidate"]["actions"], "measured_packets": False}
        elif lease["kind"] == "REVOKE":
            result = {"barrier_version": inputs["revocation"]["barrier_version"]}
        else:
            result = {"error": "JOB_KIND_DENIED"}
    completed = client.post(f"/internal/jobs/{identity}/complete", json={**receipt, "result": result})
    completed.raise_for_status()
    return completed.json()


def run(once=False):
    token = os.environ.get("WITHAQ_WORKER_TOKEN", "")
    validator_token = os.environ.get("WITHAQ_VALIDATOR_TOKEN", "")
    if not token or not validator_token:
        raise SystemExit("Worker and validator service credentials are required")
    worker_id = "worker-" + str(uuid4())
    with httpx.Client(base_url=os.environ.get("WITHAQ_API_URL", "http://127.0.0.1:8000"),
                      headers={"Authorization": "Bearer " + token}, timeout=10, trust_env=False) as client:
        while True:
            lease = None
            try:
                response = client.post("/internal/jobs/claim", json={"worker_id": worker_id})
                response.raise_for_status()
                lease = response.json()["lease"]
                if lease:
                    process(client, lease, os.environ.get("WITHAQ_VALIDATOR_URL", "http://127.0.0.1:8002"), validator_token)
            except (httpx.HTTPError, ValueError, KeyError) as error:
                if lease and (isinstance(error, (ValueError, KeyError)) or isinstance(error, httpx.HTTPStatusError) and 400 <= error.response.status_code < 500):
                    reason = "RESULT_SCHEMA_INVALID"
                    if isinstance(error, httpx.HTTPStatusError):
                        try:
                            reason = error.response.json().get("detail", "RESULT_SCHEMA_INVALID")
                        except ValueError:
                            pass
                    receipt = {key: lease[key] for key in ("attempt_id", "fence", "worker_id")}
                    try:
                        client.post(f"/internal/jobs/{lease['id']}/complete", json={**receipt, "result": {"error": reason}}).raise_for_status()
                    except httpx.HTTPError:
                        pass
                # No payload/token/error-body logging. Expired attempts are fenced on retry.
                print("Worker attempt interrupted; durable lease will reconcile", flush=True)
            if once:
                return
            time.sleep(0.5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    run(parser.parse_args().once)

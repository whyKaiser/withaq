"""HTTP-only gateway process. Only mock destinations are supported in this release."""
import hashlib
import os
import time
from uuid import uuid4

import httpx


def process(client, lease, lose_response=False):
    identity = lease["id"]
    receipt = {key: lease[key] for key in ("attempt_id", "fence", "worker_id")}
    admitted = client.post(f"/internal/jobs/{identity}/admit", json=receipt)
    if admitted.status_code != 200:
        result = {"error": "ADMISSION_GUARD_DENIED"}
    else:
        request = admitted.json()
        # The mock adapter receives these exact frozen bytes. Never construct an HTTP URL.
        payload_hash = hashlib.sha256(request["payload"].encode()).hexdigest()
        if payload_hash != request["binding"]["payload_hash"] or request["binding"]["destination"] not in ("mock://local", "mock://review"):
            result = {"error": "FROZEN_PAYLOAD_OR_DESTINATION_MISMATCH"}
        else:
            result = {"status": "OUTCOME_UNKNOWN" if lose_response else "MOCK_SENT", "payload_hash": payload_hash,
                      "external_bytes_sent": 0}
    response = client.post(f"/internal/jobs/{identity}/complete", json={**receipt, "result": result})
    response.raise_for_status()
    return response.json()


def run(once=False):
    token = os.environ.get("WITHAQ_GATEWAY_TOKEN", "")
    if not token:
        raise SystemExit("Gateway credential is required")
    worker_id = "gateway-" + str(uuid4())
    with httpx.Client(base_url=os.environ.get("WITHAQ_API_URL", "http://127.0.0.1:8000"),
                      headers={"Authorization": "Bearer " + token}, timeout=10, trust_env=False) as client:
        while True:
            try:
                response = client.post("/internal/jobs/claim", json={"worker_id": worker_id})
                response.raise_for_status()
                lease = response.json()["lease"]
                if lease:
                    process(client, lease, os.environ.get("WITHAQ_MOCK_LOSE_RESPONSE") == "1")
            except (httpx.HTTPError, ValueError, KeyError):
                print("Gateway interrupted; admitted attempts will not be blindly retried", flush=True)
            if once:
                return
            time.sleep(0.5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    run(parser.parse_args().once)

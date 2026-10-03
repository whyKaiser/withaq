"""Round-robin HTTP-only worker/gateway for the disposable judge workspaces."""
import os
import time
from uuid import uuid4

import httpx

from .gateway import process as dispatch
from .worker import process as execute


def run(gateway=False):
    token = os.environ.get("WITHAQ_GATEWAY_TOKEN" if gateway else "WITHAQ_WORKER_TOKEN", "")
    validator = os.environ.get("WITHAQ_VALIDATOR_TOKEN", "")
    if not token or not gateway and not validator:
        raise SystemExit("Service credentials required")
    address = os.environ["WITHAQ_API_URL"]
    headers = {"Authorization": "Bearer " + token}
    worker_id = ("public-gateway-" if gateway else "public-worker-") + str(uuid4())
    with httpx.Client(base_url=address, headers=headers, timeout=10, trust_env=False) as control:
        while True:
            try:
                sessions = control.get("/internal/demo/sessions")
                sessions.raise_for_status()
                for identity in sessions.json()["sessions"]:
                    with httpx.Client(base_url=address + "/internal/demo/sessions/" + identity,
                                      headers=headers, timeout=10, trust_env=False) as client:
                        lease = None
                        try:
                            claimed = client.post("/internal/jobs/claim", json={"worker_id": worker_id})
                            claimed.raise_for_status()
                            lease = claimed.json()["lease"]
                            if lease:
                                if gateway:
                                    dispatch(client, lease)
                                else:
                                    execute(client, lease, os.environ["WITHAQ_VALIDATOR_URL"], validator)
                        except (httpx.HTTPError, ValueError, KeyError):
                            if lease:
                                # No body/token logging. Failure completes only at the current fence.
                                receipt = {k: lease[k] for k in ("attempt_id", "fence", "worker_id")}
                                try:
                                    client.post(f"/internal/jobs/{lease['id']}/complete", json={**receipt, "result": {"error": "RESULT_SCHEMA_INVALID"}})
                                except httpx.HTTPError:
                                    pass
            except (httpx.HTTPError, ValueError, KeyError):
                pass  # Startup or expiring sessions; durable leases remain authoritative.
            time.sleep(0.5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", action="store_true")
    run(parser.parse_args().gateway)

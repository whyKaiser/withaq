"""Actual API/validator/worker/gateway processes, including a killed model worker."""
import os
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import update

from withaq.engine import Engine
from withaq.scenarios import scenarios
from withaq import schema as s


def port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def stop(process):
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            process.terminate()
        process.wait(timeout=5)


def test_real_worker_kill_restart_and_separate_services(tmp_path):
    api_port, validator_port = port(), port()
    while validator_port == api_port:
        validator_port = port()
    api_url, validator_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{validator_port}"
    url = "sqlite:///" + str(tmp_path / "engine.db").replace("\\", "/")
    base = {key: value for key, value in os.environ.items() if key.upper() in (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PYTHONPATH")}
    api_env = {**base, "WITHAQ_DATABASE_URL": url, "WITHAQ_DB": str(tmp_path / "demo.db"),
               "WITHAQ_ADMIN_TOKEN": "test-operator", "WITHAQ_WORKER_TOKEN": "test-worker", "WITHAQ_GATEWAY_TOKEN": "test-gateway"}
    worker_env = {**base, "WITHAQ_API_URL": api_url, "WITHAQ_VALIDATOR_URL": validator_url,
                  "WITHAQ_WORKER_TOKEN": "test-worker", "WITHAQ_VALIDATOR_TOKEN": "test-validator"}
    gateway_env = {**base, "WITHAQ_API_URL": api_url, "WITHAQ_GATEWAY_TOKEN": "test-gateway"}
    assert "WITHAQ_DATABASE_URL" not in worker_env and "WITHAQ_ADMIN_TOKEN" not in gateway_env
    children = []
    def spawn(args, env):
        child = subprocess.Popen([sys.executable, *args], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(child)
        return child
    try:
        spawn(["-m", "uvicorn", "withaq.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(api_port), "--no-access-log"], api_env)
        spawn(["-m", "uvicorn", "withaq.validator_service:create_app", "--factory", "--host", "127.0.0.1", "--port", str(validator_port), "--no-access-log"], {**base, "WITHAQ_VALIDATOR_TOKEN": "test-validator"})
        with httpx.Client(base_url=api_url, headers={"Authorization": "Bearer test-operator"}, timeout=5, trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    if client.get("/health/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "API did not become ready"
                time.sleep(0.1)
            def state():
                response = client.get("/v1/state"); response.raise_for_status(); return response.json()
            def command(path, **body):
                response = client.post(path, json={"expected_version": state()["version"], **body}, headers={"Idempotency-Key": str(uuid4())})
                response.raise_for_status(); return response.json()
            r1 = command("/v1/roots", label="Synthetic process test")["id"]
            a1 = command("/v1/artifacts", label="input", root_ids=[r1], payload="Synthetic worker restart input")["id"]
            created = command("/v1/runs", label="resumable", inputs=[{"artifact_id": a1}], delay_s=3)
            first = spawn(["-m", "withaq.worker", "--once"], worker_env)
            deadline = time.monotonic() + 10
            while True:
                job = next(job for job in state()["jobs"] if job["id"] == created["job_id"])
                if job["state"] == "LEASED":
                    break
                assert time.monotonic() < deadline, "Worker did not claim job"
                time.sleep(0.1)
            stop(first)  # Actual process termination; no successful completion receipt exists.
            engine = Engine(url)
            with engine.db.transaction() as db:
                db.execute(update(s.outbox).where(s.outbox.c.id == created["job_id"]).values(lease_until=time.time() - 1))
            second = spawn(["-m", "withaq.worker", "--once"], worker_env)
            assert second.wait(timeout=12) == 0
            current = state()
            resumed = next(job for job in current["jobs"] if job["id"] == created["job_id"])
            assert resumed["state"] == "DONE" and resumed["fence"] == 2
            assert len(current["artifacts"]) == 2 and current["runs"][0]["status"] == "PUBLISHED"
            device = command("/v1/devices", label="G")["id"]
            snapshot = command("/v1/snapshots", spec=scenarios()["separable"].model_dump(mode="json"))["id"]
            incident = command("/v1/incidents", device_id=device, snapshot_id=snapshot, evidence={"mode": "synthetic"})["id"]
            command("/v1/plans", incident_id=incident, snapshot_id=snapshot)
            planner = spawn(["-m", "withaq.worker", "--once"], worker_env)
            assert planner.wait(timeout=10) == 0
            assert state()["plans"][0]["status"] == "OPTIMAL" and state()["reports"][0]["verdict"]["accepted"]
            inspected = command("/v1/egress/requests", artifact_id=a1, destination="mock://local")
            command(f"/v1/egress/{inspected['id']}/dispatch")
            gateway = spawn(["-m", "withaq.gateway", "--once"], {**gateway_env, "WITHAQ_MOCK_LOSE_RESPONSE": "1"})
            assert gateway.wait(timeout=10) == 0
            assert state()["egress"][0]["status"] == "OUTCOME_UNKNOWN"
            retry = spawn(["-m", "withaq.gateway", "--once"], gateway_env)
            assert retry.wait(timeout=10) == 0
            assert state()["egress"][0]["status"] == "OUTCOME_UNKNOWN"
            assert len([job for job in state()["jobs"] if job["kind"] == "EGRESS"]) == 1
            engine.db.engine.dispose()
    finally:
        for child in reversed(children):
            stop(child)

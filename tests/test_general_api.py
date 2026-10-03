from uuid import uuid4

from fastapi.testclient import TestClient
from withaq.main import create_app


def test_user_and_service_capabilities_are_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("WITHAQ_WORKER_TOKEN", "worker-test")
    monkeypatch.setenv("WITHAQ_GATEWAY_TOKEN", "gateway-test")
    with TestClient(create_app(str(tmp_path / "demo.db"), "operator-test", "viewer-test")) as client:
        auth = lambda token: {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid4())}
        assert client.get("/v1/state").status_code == 401
        assert client.post("/v1/roots", json={"label": "S1", "expected_version": 0}, headers=auth("viewer-test")).status_code == 403
        source = client.post("/v1/roots", json={"label": "S1", "expected_version": 0}, headers=auth("operator-test")).json()["id"]
        artifact = client.post("/v1/artifacts", json={"label": "input", "payload": "Synthetic safe telemetry", "root_ids": [source], "expected_version": 1}, headers=auth("operator-test")).json()["id"]
        run = client.post("/v1/runs", json={"label": "summary", "inputs": [{"artifact_id": artifact}], "expected_version": 2}, headers=auth("operator-test"))
        assert run.status_code == 202
        assert client.post("/internal/jobs/claim", json={"worker_id": "x"}, headers=auth("operator-test")).status_code == 403
        assert client.post("/internal/jobs/claim", json={"worker_id": "x"}, headers=auth("gateway-test")).json()["lease"] is None
        lease = client.post("/internal/jobs/claim", json={"worker_id": "worker"}, headers=auth("worker-test")).json()["lease"]
        receipt = {key: lease[key] for key in ("attempt_id", "fence", "worker_id")}
        assert client.post(f"/internal/jobs/{lease['id']}/inputs", json=receipt, headers=auth("gateway-test")).status_code == 403
        assert client.post(f"/internal/jobs/{lease['id']}/admit", json=receipt, headers=auth("worker-test")).status_code == 403
        assert client.post(f"/internal/jobs/{lease['id']}/complete", json={**receipt, "result": {}}, headers=auth("gateway-test")).status_code == 403
        assert client.post(f"/internal/jobs/{lease['id']}/inputs", json=receipt, headers=auth("worker-test")).status_code == 200
        state = client.get("/v1/state", headers=auth("viewer-test")).json()
        assert all("payload" not in row for row in state["artifacts"])

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from withaq.public_demo import COOKIE, create_app
from withaq.scenarios import scenarios


@pytest.fixture
def demo(monkeypatch, tmp_path):
    monkeypatch.setenv("WITHAQ_WORKER_TOKEN", "private-test-worker")
    monkeypatch.setenv("WITHAQ_GATEWAY_TOKEN", "private-test-gateway")
    monkeypatch.delenv("WITHAQ_DATABASE_URL", raising=False)
    monkeypatch.delenv("WITHAQ_PEP_SIGNING_KEY", raising=False)
    clock = [1000.0]
    app = create_app(tmp_path / "owned", public_url="http://testserver", maximum=2, ttl=100, clock=lambda: clock[0])
    app.state.test_clock = clock
    return app


def client(app):
    return TestClient(app, headers={"X-Withaq-Demo": "1"})


def start(c):
    result = c.post("/demo/session")
    assert result.status_code == 200
    assert "httponly" in result.headers["set-cookie"].lower()
    assert "samesite=strict" in result.headers["set-cookie"].lower()
    assert "token" not in result.json()


def mutate(c, path, body):
    version = c.get("/v1/state").json()["version"]
    return c.post(path, json={"expected_version": version, **body}, headers={"Idempotency-Key": str(uuid4())})


def test_visitors_have_independent_databases_and_cannot_read_other_ids(demo):
    with client(demo) as first, client(demo) as second:
        start(first)
        start(second)
        root = mutate(first, "/v1/roots", {"label": "Synthetic visitor A"}).json()
        item = mutate(first, "/v1/artifacts", {"label": "Synthetic", "payload": "Synthetic private workspace test", "root_ids": [root["id"]]}).json()
        assert first.get(f"/v1/artifacts/{item['id']}").status_code == 200
        assert second.get(f"/v1/artifacts/{item['id']}").status_code == 404
        assert second.get("/v1/state").json()["roots"] == []
        assert first.cookies.get(COOKIE) != second.cookies.get(COOKIE)
        exported = json.dumps(first.get("/v1/state").json())
        assert "Synthetic private workspace test" not in exported
        assert "private-test-worker" not in exported


def test_origin_internal_routes_body_and_packet_boundaries(demo):
    with client(demo) as visitor:
        assert visitor.post("/demo/session", headers={"Origin": "https://evil.example"}).status_code == 403
        assert visitor.post("/demo/session", headers={"X-Withaq-Demo": "0"}).status_code == 403
        start(visitor)
        assert visitor.get("/internal/demo/sessions").status_code == 403
        assert visitor.post("/internal/jobs/claim", json={"worker_id": "attacker"}).status_code == 404
        assert visitor.post("/v1/roots", content=b"x" * 32769).status_code == 413
        assert visitor.get("/v1/capabilities").json()["packet_lab_configured"] is False
        assert visitor.post("/v1/plans/arbitrary/apply", json={"adapter": "packet-lab"}).status_code == 403
        safe = scenarios()["separable"].model_dump(mode="json")
        assert mutate(visitor, "/v1/snapshots", {"spec": safe}).status_code == 200
        safe["nodes"].append("arbitrary-public-model")
        assert mutate(visitor, "/v1/snapshots", {"spec": safe}).status_code == 422


def test_expiry_capacity_and_scoped_cleanup(demo):
    with client(demo) as first, client(demo) as second, client(demo) as third:
        start(first)
        start(second)
        assert third.post("/demo/session").status_code == 503
        mutate(first, "/v1/roots", {"label": "Synthetic"})
        old_id = first.cookies.get(COOKIE)
        demo.state.test_clock[0] += 101
        assert first.get("/v1/state").status_code == 401
        start(third)
        assert not (demo.state.workspaces.directory / old_id).exists()
        assert third.get("/v1/state").json()["roots"] == []


def test_private_gateway_cannot_claim_model_jobs(demo):
    with client(demo) as visitor:
        start(visitor)
        root = mutate(visitor, "/v1/roots", {"label": "Synthetic"}).json()
        item = mutate(visitor, "/v1/artifacts", {"label": "Input", "payload": "Synthetic bounded test input", "root_ids": [root["id"]]}).json()
        mutate(visitor, "/v1/runs", {"label": "Output", "inputs": [{"artifact_id": item["id"], "role": "source"}]})
        session = visitor.cookies.get(COOKIE)
        address = f"/internal/demo/sessions/{session}/internal/jobs/claim"
        gateway = visitor.post(address, json={"worker_id": "gateway"}, headers={"Authorization": "Bearer private-test-gateway"})
        assert gateway.json()["lease"] is None
        worker = visitor.post(address, json={"worker_id": "worker"}, headers={"Authorization": "Bearer private-test-worker"})
        assert worker.json()["lease"]["kind"] == "MODEL"


def test_request_and_write_limits(demo):
    with client(demo) as visitor:
        start(visitor)
        session = demo.state.workspaces.lookup(visitor.cookies.get(COOKIE))
        session.mutations = 256
        assert visitor.post("/v1/roots", json={"label": "Synthetic"}).status_code == 429
        session.rate_count = 20
        session.rate_second = int(demo.state.test_clock[0])
        assert visitor.get("/v1/state").status_code == 429


def test_spoofed_forwarded_header_does_not_grant_private_access(demo):
    with TestClient(demo, client=("198.51.100.5", 5000)) as attacker:
        response = attacker.get("/internal/demo/sessions", headers={"Authorization": "Bearer private-test-worker", "X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 404

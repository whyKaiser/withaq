from uuid import uuid4

from fastapi.testclient import TestClient

from withaq.main import create_app


def test_auth_roles_versions_and_error_boundaries(tmp_path):
    app = create_app(tmp_path / "db.sqlite3", token="test-only-operator", viewer_token="test-only-viewer")
    client = TestClient(app)
    assert client.get("/health/ready").status_code == 200
    assert client.get("/v1/scenarios").status_code == 401
    viewer = {"Authorization": "Bearer test-only-viewer"}
    assert client.get("/v1/scenarios", headers=viewer).status_code == 200
    assert client.post("/v1/demo/runs", json={}, headers=viewer).status_code == 403
    admin = {"Authorization": "Bearer test-only-operator", "Idempotency-Key": str(uuid4())}
    response = client.post("/v1/demo/runs", json={}, headers=admin)
    assert response.status_code == 200
    run = response.json()
    assert run["plan"]["actions"] == ["a", "b"]
    assert "payload" not in str(run["artifacts"])
    response = client.post(f'/v1/demo/runs/{run["id"]}/revoke', json={"expected_version": 999}, headers={**admin,"Idempotency-Key":str(uuid4())})
    assert response.status_code == 409
    assert response.json()["detail"] == "STALE_SNAPSHOT"
    assert client.get("/health/live", headers={"Host": "attacker.invalid"}).status_code == 400


def test_missing_credentials_fail_readiness(tmp_path):
    client = TestClient(create_app(tmp_path / "db.sqlite3", token=""))
    assert client.get("/health/ready").status_code == 503

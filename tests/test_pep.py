from fastapi.testclient import TestClient
from withaq.pep_service import create_app, supported
from withaq.models import Snapshot
from withaq.planner import solve
from withaq.scenarios import scenarios


def test_packet_broker_rejects_identity_unsafe_and_unmapped_models(monkeypatch):
    monkeypatch.setenv("WITHAQ_PEP_TOKEN", "pep-test")
    monkeypatch.setenv("WITHAQ_PEP_SIGNING_KEY", "signing-test")
    def forbidden(*args, **kwargs):
        raise AssertionError("Docker must not run for rejected requests")
    monkeypatch.setattr("withaq.pep_service.subprocess.run", forbidden)
    snapshot = scenarios()["separable"]
    body = {"snapshot": snapshot.model_dump(mode="json"), "candidate": solve(snapshot).model_dump(mode="json")}
    with TestClient(create_app()) as client:
        assert client.post("/v1/trials", json=body).status_code == 403
        headers = {"Authorization": "Bearer pep-test"}
        invalid = {**body, "candidate": {**body["candidate"], "actions": ["c"], "cost": 1}}
        assert client.post("/v1/trials", json=invalid, headers=headers).status_code == 409
        extended = snapshot.model_copy(update={"nodes": (*snapshot.nodes, "Z")})
        assert not supported(extended)
        unmapped = {"snapshot": extended.model_dump(mode="json"), "candidate": solve(extended).model_dump(mode="json")}
        assert client.post("/v1/trials", json=unmapped, headers=headers).status_code == 422
    assert supported(snapshot) and supported(scenarios()["bounded-dependency"])

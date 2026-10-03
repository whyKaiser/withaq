from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from withaq.store import DomainError, Store


def key():
    return str(uuid4())


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "state.sqlite3")


def mutate(store, run, action, **body):
    return store.mutate(run["id"], action, run["version"], key(), body)


def inspect(store, run, artifact="T2", **extra):
    return mutate(store, run, "inspect", artifact=artifact, destination="mock://review", account="demo", purpose="competition-demo", **extra)


def test_revoke_late_result_independent_branch_and_recovery(store):
    run = store.create("separable", "mfsc", key())
    run = mutate(store, run, "apply")
    assert run["enforcement"] == "SIMULATED_CONFIRMED"
    run = mutate(store, run, "revoke")
    for identity in ("T1", "T2", "C-D"):
        with pytest.raises(DomainError):
            store.read_artifact(run["id"], identity)
    assert store.read_artifact(run["id"], "T3")["roots"] == {"S3": 1}
    run = mutate(store, run, "complete-late")
    assert run["command_result"]["reason"] == "ROOT_REVOKED"
    run = mutate(store, run, "recover")
    assert store.read_artifact(run["id"], "T2b")["roots"] == {"S2": 1}
    assert run["roots"]["S1"]["status"] == "REVOKED"
    assert next(a for a in run["artifacts"] if a["id"] == "C-D")["status"] == "HELD"


def test_unsafe_candidate_cannot_apply(store):
    run = store.create("separable", "quarantine", key())
    with pytest.raises(DomainError, match="VALIDATION_REJECTED"):
        mutate(store, run, "apply")


def test_idempotency_versions_and_restart(store):
    command_key = key()
    run = store.create("separable", "mfsc", command_key)
    assert store.create("separable", "mfsc", command_key) == run
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        store.create("shared-channel", "mfsc", command_key)
    updated = mutate(store, run, "revoke")
    with pytest.raises(DomainError, match="STALE_SNAPSHOT"):
        mutate(store, run, "recover")
    restarted = Store(store.path)
    assert restarted.read(run["id"])["roots"]["S1"]["status"] == "REVOKED"
    assert restarted.read(run["id"])["events"] == updated["events"]


def test_racing_commands_cannot_overwrite_newer_state(store):
    run = store.create("separable", "mfsc", key())
    def revoke():
        try:
            return mutate(store, run, "revoke")["version"]
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: revoke(), range(2)))
    assert set(outcomes) == {2, "STALE_SNAPSHOT"}


@pytest.mark.parametrize("field", ["national_id=TEST", "password=TEST", "رقم الهوية: تجربة", "كلمة المرور: تجربة"])
def test_prohibited_disclosure_fields_blocked(store, field):
    run = inspect(store, store.create("separable", "mfsc", key()), extra_text=field)
    request = run["command_result"]["request"]
    assert request["status"] == "BLOCKED" and not request["payload"]
    with pytest.raises(DomainError, match="REQUEST_NOT_APPROVABLE"):
        mutate(store, run, "approve", request_id=request["id"], payload_hash=request["payload_hash"])


def test_approval_rechecks_exact_bytes_and_revocation(store):
    run = inspect(store, store.create("separable", "mfsc", key()))
    request = run["command_result"]["request"]
    body = {"request_id": request["id"], "payload_hash": request["payload_hash"]}
    with pytest.raises(DomainError, match="PAYLOAD_CHANGED"):
        mutate(store, run, "approve", request_id=request["id"], payload_hash="changed")
    run = mutate(store, run, "approve", **body)
    run = mutate(store, run, "revoke")
    with pytest.raises(DomainError, match="ROOT_REVOKED"):
        mutate(store, run, "dispatch", **body)


def test_revoked_payload_cannot_leak_through_inspect_or_cached_replay(store):
    run = store.create("separable", "mfsc", key())
    command_key = key()
    body = {"artifact": "T2", "destination": "mock://review", "account": "demo", "purpose": "competition-demo"}
    inspected = store.mutate(run["id"], "inspect", run["version"], command_key, body)
    revoked = mutate(store, inspected, "revoke")
    with pytest.raises(DomainError, match="ROOT_REVOKED"):
        store.mutate(run["id"], "inspect", run["version"], command_key, body)
    assert not inspect(store, revoked)["command_result"]["request"]["payload"]


def test_unknown_send_not_retried(store):
    run = inspect(store, store.create("separable", "mfsc", key()))
    request = run["command_result"]["request"]
    body = {"request_id": request["id"], "payload_hash": request["payload_hash"]}
    run = mutate(store, run, "approve", **body)
    run = mutate(store, run, "dispatch", **body, lose_response=True)
    assert run["command_result"]["status"] == "OUTCOME_UNKNOWN"
    with pytest.raises(DomainError, match="ALREADY_ATTEMPTED_NO_RETRY"):
        mutate(store, run, "dispatch", **body)

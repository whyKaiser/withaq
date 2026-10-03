"""The same safety suite runs against SQLite and PostgreSQL when configured."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from withaq.database import migrate
from withaq.engine import Engine, mock_output
from withaq.lineage import closure
from withaq.scenarios import scenarios
from withaq.store import DomainError, digest
from withaq.models import Plan, Snapshot
from withaq.planner import solve
from withaq.validator import validate
from withaq import schema as s


def race_operation(url, start, queue, kind, payload):
    engine = Engine(url, clock=lambda: 1000.0)
    start.wait(10)
    try:
        if kind == "revoke":
            result = engine.revoke(payload["root"], "cross-process race", payload["version"], str(uuid4()))
        else:
            result = engine.complete(payload["job"]["id"], **lease_args(payload["job"]), result=payload["result"])
        queue.put((kind, result))
    except DomainError as error:
        queue.put((kind, {"error": error.code}))
    finally:
        engine.db.engine.dispose()


@pytest.fixture(params=["sqlite", "postgres"] if os.environ.get("WITHAQ_TEST_DATABASE_URL") else ["sqlite"])
def engine(request, tmp_path):
    cleanup = None
    if request.param == "postgres":
        admin = create_engine(os.environ["WITHAQ_TEST_DATABASE_URL"], hide_parameters=True)
        schema = "test_" + uuid4().hex
        with admin.begin() as db:
            db.execute(CreateSchema(schema))
        url = make_url(os.environ["WITHAQ_TEST_DATABASE_URL"]).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
        cleanup = (admin, schema)
    else:
        url = "sqlite:///" + str(tmp_path / "engine.db").replace("\\", "/")
    migrate(url)
    clock = [1000.0]
    result = Engine(url, clock=lambda: clock[0])
    result.test_clock = clock
    result.test_url = url
    yield result
    result.db.engine.dispose()
    if cleanup:
        admin, schema = cleanup
        with admin.begin() as db:
            db.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def version(engine):
    return engine.state()["version"]


def root(engine, name="S1"):
    return engine.create_record("roots", {"label": name}, version(engine), str(uuid4()))["id"]


def artifact(engine, roots=(), parents=(), payload="Synthetic approved telemetry.", label="input"):
    return engine.create_artifact({"label": label, "payload": payload, "root_ids": list(roots), "parent_ids": list(parents)}, version(engine), str(uuid4()))["id"]


def run(engine, inputs, replacement_for=None):
    return engine.create_run({"label": "summary", "task": "recovery" if replacement_for else "summary",
        "inputs": [{"artifact_id": identity, "role": "source"} for identity in inputs], "replacement_for": replacement_for}, version(engine), str(uuid4()))


def lease_args(job):
    return {key: job[key] for key in ("attempt_id", "fence", "worker_id")}


def model_result(engine, job):
    inputs = engine.job_inputs(job["id"], **lease_args(job))
    return {"manifest_hash": inputs["manifest_hash"], "payload": mock_output(inputs["task"], inputs["inputs"])}


def complete_model(engine):
    job = engine.claim("test-worker", ("MODEL",))
    assert engine.complete(job["id"], **lease_args(job), result=model_result(engine, job))["status"] == "DONE"
    return next(row["output_id"] for row in engine.state()["runs"] if row["id"] == job["entity_id"])


def inspected(engine, identity, destination="mock://review"):
    return engine.inspect_egress({"artifact_id": identity, "destination": destination, "account": "demo", "purpose": "competition-demo"}, version(engine), str(uuid4()))


def test_general_transitive_lineage_revocation_and_recovery(engine):
    s1, s2, s3 = root(engine), root(engine, "S2"), root(engine, "S3")
    a = artifact(engine, [s1])
    b = artifact(engine, parents=[a], label="derived")
    independent = artifact(engine, [s3])
    held = artifact(engine)
    alternative = artifact(engine, [s2], payload="Independent approved replacement input.")
    run(engine, [a, b])
    job = engine.claim("late-worker", ("MODEL",))
    output = model_result(engine, job)
    revoked = engine.revoke(s1, "synthetic incident", version(engine), str(uuid4()))
    assert set(revoked["proven"]) == {a, b}
    assert revoked["precaution"] == [held]
    for identity in (a, b):
        with pytest.raises(DomainError, match="ROOT_REVOKED"):
            engine.read_artifact(identity)
    with pytest.raises(DomainError, match="UNKNOWN_LINEAGE"):
        engine.read_artifact(held)
    assert engine.read_artifact(independent)["id"] == independent
    assert engine.complete(job["id"], **lease_args(job), result=output)["reason"] == "ROOT_REVOKED"
    run(engine, [alternative], replacement_for=b)
    replacement = complete_model(engine)
    assert replacement != b
    assert s1 not in next(item["roots"] for item in engine.state()["artifacts"] if item["id"] == replacement)
    assert next(item["status"] for item in engine.state()["roots"] if item["id"] == s1) == "REVOKED"


def test_manifest_includes_system_history_tool_and_all_roots(engine):
    roots = [root(engine, role) for role in ("source", "system", "history", "tool")]
    inputs = [artifact(engine, [identity]) for identity in roots]
    created = engine.create_run({"label": "complete context", "task": "summary", "replacement_for": None,
        "inputs": [{"artifact_id": identity, "role": role} for identity, role in zip(inputs, ("source", "system", "history", "tool"))]}, version(engine), str(uuid4()))
    manifest = next(item for item in engine.state()["manifests"] if item["id"] == created["manifest_id"])
    assert set(manifest["sealed"]["roots"]) == set(roots)
    assert len(manifest["sealed"]["inputs"]) == 4
    assert manifest["hash"] == digest(manifest["sealed"])
    engine.revoke(roots[2], "history revoked", version(engine), str(uuid4()))
    job = engine.claim("worker", ("MODEL",))
    with pytest.raises(DomainError, match="ROOT_REVOKED"):
        engine.job_inputs(job["id"], **lease_args(job))


def test_cycles_and_immutable_identity(engine):
    with pytest.raises(DomainError, match="LINEAGE_CYCLE"):
        closure({"a": ["b"], "b": ["c"]}, [("a", "c")])
    with pytest.raises(DomainError, match="LINEAGE_CYCLE"):
        closure({}, [("a", "a")])
    assert closure({"b": ["a"], "c": ["b"]})["c"] == {"b"}
    with pytest.raises(DomainError, match="ARTIFACTS_NOT_FOUND"):
        artifact(engine, parents=[str(uuid4())])


def test_fenced_crash_retry_duplicate_completion_and_restart(engine):
    source = artifact(engine, [root(engine)])
    run(engine, [source])
    old = engine.claim("worker-A", ("MODEL",))
    result = model_result(engine, old)
    engine.test_clock[0] += 21
    restarted = Engine(engine.test_url, clock=lambda: engine.test_clock[0])
    fresh = restarted.claim("worker-B", ("MODEL",))
    assert fresh["fence"] == old["fence"] + 1
    with pytest.raises(DomainError, match="STALE_FENCING_TOKEN"):
        engine.complete(old["id"], **lease_args(old), result=result)
    assert restarted.complete(fresh["id"], **lease_args(fresh), result=result)["status"] == "DONE"
    assert restarted.complete(fresh["id"], **lease_args(fresh), result=result)["duplicate"]
    assert len(restarted.state()["artifacts"]) == 2
    restarted.db.engine.dispose()


def test_revocation_outbox_transaction_and_idempotency(engine):
    source = root(engine)
    expected, key = version(engine), str(uuid4())
    first = engine.revoke(source, "test", expected, key)
    assert engine.revoke(source, "test", expected, key) == first
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        engine.revoke(source, "different", expected, key)
    state = engine.state()
    assert len(state["revocations"]) == 1 and len(state["jobs"]) == 1
    assert state["roots"][0]["version"] == 2
    with pytest.raises(DomainError, match="STALE_SNAPSHOT"):
        engine.create_record("roots", {"label": "new"}, expected, str(uuid4()))


@pytest.mark.parametrize("change", ["payload", "account", "purpose", "destination"])
def test_exact_approval_rejects_mutation(engine, change):
    source = artifact(engine, [root(engine)])
    request = inspected(engine, source)
    engine.approve(request["id"], request["binding_hash"], version(engine), str(uuid4()))
    with engine.db.transaction() as db:
        row = engine._get(db, s.egress, request["id"])
        if change == "payload":
            db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(payload="changed exact bytes"))
        else:
            binding = {**row["binding"], change: "changed"}
            db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(binding=binding))
    with pytest.raises(DomainError, match="PAYLOAD_OR_BINDING_CHANGED"):
        engine.dispatch(request["id"], version(engine), str(uuid4()))


def test_revocation_before_admission_and_after_admission_limit(engine):
    r1 = root(engine)
    source = artifact(engine, [r1])
    request = inspected(engine, source, "mock://local")
    engine.dispatch(request["id"], version(engine), str(uuid4()))
    job = engine.claim("gateway", ("EGRESS",))
    engine.revoke(r1, "deny before admission", version(engine), str(uuid4()))
    with pytest.raises(DomainError, match="ROOT_REVOKED"):
        engine.admit(job["id"], **lease_args(job))
    assert engine.complete(job["id"], **lease_args(job), result={"error": "ADMISSION_DENIED"})["status"] == "FAILED"
    r2 = root(engine)
    request2 = inspected(engine, artifact(engine, [r2]), "mock://local")
    engine.dispatch(request2["id"], version(engine), str(uuid4()))
    job2 = engine.claim("gateway", ("EGRESS",))
    admitted = engine.admit(job2["id"], **lease_args(job2))
    engine.revoke(r2, "after admission", version(engine), str(uuid4()))
    # Already admitted requests cannot be recalled. Record truthfully, never report BLOCKED after sending.
    assert engine.complete(job2["id"], **lease_args(job2), result={"status": "MOCK_SENT", "payload_hash": admitted["binding"]["payload_hash"], "external_bytes_sent": 0})["status"] == "DONE"
    assert next(item["status"] for item in engine.state()["egress"] if item["id"] == request2["id"]) == "MOCK_SENT"


def test_lost_gateway_lease_never_blindly_retries(engine):
    source = artifact(engine, [root(engine)])
    request = inspected(engine, source, "mock://local")
    engine.dispatch(request["id"], version(engine), str(uuid4()))
    job = engine.claim("gateway-A", ("EGRESS",))
    engine.admit(job["id"], **lease_args(job))
    engine.test_clock[0] += 21
    assert engine.claim("gateway-B", ("EGRESS",)) is None
    assert engine.state()["egress"][0]["status"] == "OUTCOME_UNKNOWN"
    with pytest.raises(DomainError, match="REQUEST_NOT_DISPATCHABLE"):
        engine.dispatch(request["id"], version(engine), str(uuid4()))


def test_sanitizing_does_not_drop_lineage_or_bypass_root_guard(engine):
    source_root = root(engine)
    source = artifact(engine, [source_root], payload="Synthetic contact fake@example.test phone ٠٥٠١٢٣٤٥٦٧.")
    request = inspected(engine, source)
    assert request["decision"] == "SANITIZE"
    inspected_bytes = engine.read_egress(request["id"])
    assert "fake@example.test" not in inspected_bytes["payload"]
    assert source_root in inspected_bytes["binding"]["roots"]
    engine.revoke(source_root, "test", version(engine), str(uuid4()))
    with pytest.raises(DomainError, match="ROOT_REVOKED"):
        engine.read_egress(request["id"])
    # Cached mutation receipt contains only hashes; a replay cannot return old payload bytes.
    assert all("payload" not in item for item in engine.state()["artifacts"] + engine.state()["egress"])


def test_planner_worker_result_binding_and_apply(engine):
    snapshot = scenarios()["separable"].model_dump(mode="json")
    device = engine.create_record("devices", {"label": "G", "kind": "simulated"}, version(engine), str(uuid4()))["id"]
    snap = engine.create_record("snapshots", {"spec": snapshot}, version(engine), str(uuid4()))["id"]
    incident = engine.create_record("incidents", {"device_id": device, "snapshot_id": snap, "evidence": {"synthetic": "yes"}}, version(engine), str(uuid4()))["id"]
    plan = engine.create_plan({"incident_id": incident, "snapshot_id": snap}, version(engine), str(uuid4()))
    job = engine.claim("worker", ("PLAN",))
    candidate = solve(Snapshot.model_validate(snapshot)).model_dump(mode="json")
    result = {"candidate": candidate, "snapshot_hash": digest(snapshot), "verdict": validate(Snapshot.model_validate(snapshot), Plan.model_validate(candidate)).model_dump(mode="json")}
    assert engine.complete(job["id"], **lease_args(job), result=result)["status"] == "DONE"
    assert engine.state()["plans"][0]["candidate"]["actions"] == ["a", "b"]
    engine.apply_plan(plan["id"], version(engine), str(uuid4()))
    job = engine.claim("worker", ("APPLY",))
    inputs = engine.job_inputs(job["id"], **lease_args(job))
    assert engine.complete(job["id"], **lease_args(job), result={"status": "SIMULATED_CONFIRMED", "plan_hash": inputs["plan_hash"], "actions": ["a", "b"], "measured_packets": False})["status"] == "DONE"


def test_cross_process_revoke_publication_race(engine):
    import multiprocessing
    root_id = root(engine)
    source = artifact(engine, [root_id])
    run(engine, [source])
    job = engine.claim("worker", ("MODEL",))
    result = model_result(engine, job)
    context = multiprocessing.get_context("spawn")
    start, queue = context.Event(), context.Queue()
    processes = [context.Process(target=race_operation, args=(engine.test_url, start, queue, kind, payload)) for kind, payload in (
        ("revoke", {"root": root_id, "version": version(engine)}), ("publish", {"job": job, "result": result}))]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("Race process did not finish")
        assert process.exitcode == 0
    outcomes = dict(queue.get(timeout=2) for _ in processes)
    assert "error" not in outcomes["revoke"]
    assert outcomes["publish"]["status"] in ("DONE", "FAILED")
    state = engine.state()
    for item in state["artifacts"]:
        with pytest.raises(DomainError, match="ROOT_REVOKED"):
            engine.read_artifact(item["id"])
    assert state["runs"][0]["status"] in ("PUBLISHED", "REJECTED")


def test_expired_attempts_are_bounded_and_heartbeats_extend_lease(engine):
    source = artifact(engine, [root(engine)])
    run(engine, [source])
    first = engine.claim("worker", ("MODEL",))
    engine.test_clock[0] += 15
    engine.heartbeat(first["id"], **lease_args(first))
    engine.test_clock[0] += 6
    assert engine.claim("other-worker", ("MODEL",)) is None
    engine.test_clock[0] += 15
    second = engine.claim("other-worker", ("MODEL",))
    assert second["fence"] == 2
    engine.test_clock[0] += 21
    third = engine.claim("third-worker", ("MODEL",))
    assert third["fence"] == 3
    engine.test_clock[0] += 21
    assert engine.claim("fourth-worker", ("MODEL",)) is None
    assert engine.state()["jobs"][0]["state"] == "FAILED"
    assert engine.state()["runs"][0]["reason"] == "ATTEMPT_LIMIT_REACHED"


def test_packet_receipt_cannot_be_forged_as_simulated_result(engine, monkeypatch):
    monkeypatch.setenv("WITHAQ_PEP_SIGNING_KEY", "synthetic-test-key")
    snapshot = scenarios()["separable"].model_dump(mode="json")
    device = engine.create_record("devices", {"label": "G", "kind": "synthetic"}, version(engine), str(uuid4()))["id"]
    snap = engine.create_record("snapshots", {"spec": snapshot}, version(engine), str(uuid4()))["id"]
    incident = engine.create_record("incidents", {"device_id": device, "snapshot_id": snap, "evidence": {"mode": "synthetic"}}, version(engine), str(uuid4()))["id"]
    plan = engine.create_plan({"incident_id": incident, "snapshot_id": snap}, version(engine), str(uuid4()))
    job = engine.claim("worker", ("PLAN",))
    candidate = solve(Snapshot.model_validate(snapshot)).model_dump(mode="json")
    engine.complete(job["id"], **lease_args(job), result={"candidate": candidate, "snapshot_hash": digest(snapshot),
        "verdict": validate(Snapshot.model_validate(snapshot), Plan.model_validate(candidate)).model_dump(mode="json")})
    engine.apply_plan(plan["id"], version(engine), str(uuid4()), adapter="packet-lab")
    apply_job = engine.claim("worker", ("APPLY",))
    forged = {"status": "LAB_CONFIRMED", "measured_packets": True, "plan_hash": digest(candidate), "signature": "0" * 64}
    result = engine.complete(apply_job["id"], **lease_args(apply_job), result=forged)
    assert result == {"status": "FAILED", "reason": "ENFORCEMENT_RECEIPT_INVALID"}
    assert engine.state()["enforcements"][0]["status"] == "FAILED"

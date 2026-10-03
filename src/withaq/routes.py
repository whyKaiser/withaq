"""Typed general APIs; worker/gateway identities are capabilities, not user roles."""
import hmac
import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from .models import Model, Contract, Snapshot


class Version(Model):
    expected_version: int = Field(ge=0)


class DeviceCreate(Version):
    label: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="simulated-sensor", min_length=1, max_length=80)


class ContractCreate(Version):
    spec: Contract


class SnapshotCreate(Version):
    spec: Snapshot


class IncidentCreate(Version):
    device_id: str
    snapshot_id: str
    evidence: dict[str, str | float] = Field(max_length=20)


class RootCreate(Version):
    label: str = Field(min_length=1, max_length=120)


class ArtifactCreate(RootCreate):
    payload: str = Field(max_length=16384)
    root_ids: list[str] = Field(default_factory=list, max_length=32)
    parent_ids: list[str] = Field(default_factory=list, max_length=32)


class PlanCreate(Version):
    incident_id: str
    snapshot_id: str


class Input(Model):
    artifact_id: str
    role: Literal["source", "system", "history", "tool"] = "source"


class RunCreate(RootCreate):
    task: Literal["summary", "recovery"] = "summary"
    inputs: list[Input] = Field(min_length=1, max_length=32)
    replacement_for: str | None = None
    delay_s: float = Field(default=0, ge=0, le=10)


class Revoke(Version):
    reason: str = Field(min_length=1, max_length=120)


class Inspect(Version):
    artifact_id: str
    destination: str = Field(default="mock://review", max_length=200)
    account: str = Field(default="demo", max_length=120)
    purpose: str = Field(default="competition-demo", max_length=120)


class Approve(Version):
    binding_hash: str = Field(min_length=64, max_length=64)


class Apply(Version):
    adapter: Literal["simulation", "packet-lab"] = "simulation"


class Claim(Model):
    worker_id: str = Field(min_length=1, max_length=80)


class Lease(Claim):
    attempt_id: str
    fence: int = Field(ge=1)


class Complete(Lease):
    result: dict


def routes(engine, identity, operator, key):
    router = APIRouter()
    worker_token = os.environ.get("WITHAQ_WORKER_TOKEN", "")
    gateway_token = os.environ.get("WITHAQ_GATEWAY_TOKEN", "")

    def service(authorization: str = Header(default="")):
        scheme, _, token = authorization.partition(" ")
        if scheme != "Bearer" or not token:
            raise HTTPException(401, detail="SERVICE_AUTHENTICATION_REQUIRED")
        if worker_token and hmac.compare_digest(token, worker_token):
            return "worker"
        if gateway_token and hmac.compare_digest(token, gateway_token):
            return "gateway"
        raise HTTPException(403, detail="SERVICE_ROLE_DENIED")

    def permit_job(identity, role):
        # Check kind before exposing inputs or completing; gateway cannot complete MODEL jobs.
        from .schema import outbox
        with engine.db.transaction() as db:
            job = engine._get(db, outbox, identity)
            if (job["kind"] == "EGRESS") != (role == "gateway"):
                raise HTTPException(403, detail="JOB_KIND_DENIED")

    @router.get("/v1/state", dependencies=[Depends(identity)])
    def state():
        return engine.state()

    @router.get("/v1/capabilities", dependencies=[Depends(identity)])
    def capabilities():
        return {"packet_lab_configured": bool(os.environ.get("WITHAQ_PEP_SIGNING_KEY")), "provider": "mock"}

    def creator(kind):
        def execute(body, command_key):
            return engine.create_record(kind, body.model_dump(mode="json", exclude={"expected_version"}), body.expected_version, command_key)
        return execute

    @router.post("/v1/devices", dependencies=[Depends(operator)])
    def device(body: DeviceCreate, command_key=Depends(key)):
        return creator("devices")(body, command_key)

    @router.post("/v1/contracts", dependencies=[Depends(operator)])
    def contract(body: ContractCreate, command_key=Depends(key)):
        return creator("contracts")(body, command_key)

    @router.post("/v1/snapshots", dependencies=[Depends(operator)])
    def snapshot(body: SnapshotCreate, command_key=Depends(key)):
        return creator("snapshots")(body, command_key)

    @router.post("/v1/incidents", dependencies=[Depends(operator)])
    def incident(body: IncidentCreate, command_key=Depends(key)):
        return creator("incidents")(body, command_key)

    @router.post("/v1/roots", dependencies=[Depends(operator)])
    def root(body: RootCreate, command_key=Depends(key)):
        return creator("roots")(body, command_key)

    @router.post("/v1/artifacts", dependencies=[Depends(operator)])
    def artifact(body: ArtifactCreate, command_key=Depends(key)):
        return engine.create_artifact(body.model_dump(exclude={"expected_version"}), body.expected_version, command_key)

    @router.get("/v1/artifacts/{identity}", dependencies=[Depends(identity)])
    def read_artifact(identity: str):
        return engine.read_artifact(identity)

    @router.post("/v1/plans", status_code=202, dependencies=[Depends(operator)])
    def plan(body: PlanCreate, command_key=Depends(key)):
        return engine.create_plan(body.model_dump(exclude={"expected_version"}), body.expected_version, command_key)

    @router.post("/v1/plans/{identity}/apply", status_code=202, dependencies=[Depends(operator)])
    def apply(identity: str, body: Apply, command_key=Depends(key)):
        return engine.apply_plan(identity, body.expected_version, command_key, body.adapter)

    @router.post("/v1/runs", status_code=202, dependencies=[Depends(operator)])
    def run(body: RunCreate, command_key=Depends(key)):
        return engine.create_run(body.model_dump(exclude={"expected_version"}), body.expected_version, command_key)

    @router.post("/v1/roots/{identity}/revoke", status_code=202, dependencies=[Depends(operator)])
    def revoke(identity: str, body: Revoke, command_key=Depends(key)):
        return engine.revoke(identity, body.reason, body.expected_version, command_key)

    @router.post("/v1/egress/requests", dependencies=[Depends(operator)])
    def inspect(body: Inspect, command_key=Depends(key)):
        return engine.inspect_egress(body.model_dump(exclude={"expected_version"}), body.expected_version, command_key)

    @router.get("/v1/egress/{identity}", dependencies=[Depends(identity)])
    def read_egress(identity: str):
        return engine.read_egress(identity)

    @router.post("/v1/egress/{identity}/approve", dependencies=[Depends(operator)])
    def approve(identity: str, body: Approve, command_key=Depends(key)):
        return engine.approve(identity, body.binding_hash, body.expected_version, command_key)

    @router.post("/v1/egress/{identity}/dispatch", status_code=202, dependencies=[Depends(operator)])
    def dispatch(identity: str, body: Version, command_key=Depends(key)):
        return engine.dispatch(identity, body.expected_version, command_key)

    @router.post("/internal/jobs/claim")
    def claim(body: Claim, role=Depends(service)):
        return {"lease": engine.claim(body.worker_id, ("EGRESS",) if role == "gateway" else ("PLAN", "MODEL", "APPLY", "REVOKE"))}

    @router.post("/internal/jobs/{identity}/heartbeat")
    def heartbeat(identity: str, body: Lease, role=Depends(service)):
        permit_job(identity, role)
        return engine.heartbeat(identity, **body.model_dump())

    @router.post("/internal/jobs/{identity}/inputs")
    def inputs(identity: str, body: Lease, role=Depends(service)):
        if role != "worker":
            raise HTTPException(403, detail="JOB_KIND_DENIED")
        permit_job(identity, role)
        return engine.job_inputs(identity, **body.model_dump())

    @router.post("/internal/jobs/{identity}/admit")
    def admit(identity: str, body: Lease, role=Depends(service)):
        if role != "gateway":
            raise HTTPException(403, detail="JOB_KIND_DENIED")
        return engine.admit(identity, **body.model_dump())

    @router.post("/internal/jobs/{identity}/complete")
    def complete(identity: str, body: Complete, role=Depends(service)):
        permit_job(identity, role)
        return engine.complete(identity, **body.model_dump())

    return router

"""Authoritative lab engine: general lineage, durable jobs and exact-byte admission.

All artifacts are immutable. Public summaries omit bytes. A conservative workspace
lock serializes short transactions; workers have HTTP capabilities, never DB access.
"""
import time
import os
import hmac
import hashlib
from uuid import uuid4

from sqlalchemy import select, update, insert

from . import schema as s
from .database import Database
from .disclosure import Policy, sha
from .lineage import closure, merge_roots
from .models import Plan, Snapshot
from .store import DomainError, digest
from .validator import validate


def uid():
    return str(uuid4())


def mock_output(task, inputs):
    """The mock provider has no hidden context, tools, history or network access."""
    return "WITHAQ " + task.upper() + "\n" + "\n".join(item["payload"] for item in inputs)


class Engine:
    def __init__(self, url, policy_path=None, clock=time.time):
        self.db = Database(url)
        self.policy = Policy(policy_path)
        self.clock = clock

    def _get(self, db, table, identity):
        row = db.execute(select(table).where(table.c.id == identity)).mappings().first()
        if row is None:
            raise DomainError(table.name.upper() + "_NOT_FOUND", 404)
        return dict(row)

    def _event(self, db, kind, **details):
        db.execute(insert(s.audit).values(id=uid(), kind=kind, details=details, at=self.clock()))

    def _job(self, db, kind, identity):
        job_id = uid()
        db.execute(insert(s.outbox).values(id=job_id, event_id=uid(), kind=kind, entity_id=identity,
                                          state="QUEUED", fence=0, created_at=self.clock()))
        self._event(db, "JOB_QUEUED", job_id=job_id, job_kind=kind, entity_id=identity)
        return job_id

    def command(self, key, action, expected_version, body, operation):
        request_hash = digest({"action": action, "expected_version": expected_version, "body": body})
        with self.db.transaction() as db:
            previous = db.execute(select(s.commands).where(s.commands.c.id == key)).mappings().first()
            if previous:
                if previous["request_hash"] != request_hash:
                    raise DomainError("IDEMPOTENCY_CONFLICT")
                return previous["response"]  # Metadata only; guarded bytes are never cached here.
            version = db.execute(select(s.workspace.c.version)).scalar_one()
            if expected_version != version:
                raise DomainError("STALE_SNAPSHOT")
            result = operation(db)
            db.execute(update(s.workspace).values(version=version + 1))
            result["workspace_version"] = version + 1
            db.execute(insert(s.commands).values(id=key, request_hash=request_hash, response=result))
            return result

    def _bindings(self, db, artifact_id):
        rows = db.execute(select(s.artifact_roots).where(s.artifact_roots.c.artifact_id == artifact_id)).mappings()
        return {row["root_id"]: row["root_version"] for row in rows}

    def _guard(self, db, bindings):
        if not bindings:
            raise DomainError("UNKNOWN_LINEAGE", 403)
        for identity in sorted(bindings):
            root = db.execute(select(s.roots).where(s.roots.c.id == identity).with_for_update()).mappings().first()
            if not root:
                raise DomainError("UNKNOWN_ROOT", 403)
            if root["status"] != "ACTIVE":
                raise DomainError("ROOT_REVOKED", 403)
            if root["version"] != bindings[identity]:
                raise DomainError("STALE_ROOT_VERSION")

    def _artifact(self, db, identity):
        item = self._get(db, s.artifacts, identity)
        if not item["lineage_complete"]:
            raise DomainError("UNKNOWN_LINEAGE", 403)
        self._guard(db, self._bindings(db, identity))
        if item["status"] != "ACTIVE":
            raise DomainError("ARTIFACT_NOT_ACTIVE", 403)
        if sha(item["payload"]) != item["hash"]:
            raise DomainError("ARTIFACT_INTEGRITY_FAILED", 403)
        return item

    def read_artifact(self, identity):
        with self.db.transaction() as db:
            return self._artifact(db, identity)

    def create_record(self, kind, data, version, key):
        def execute(db):
            identity = uid()
            if kind == "devices":
                db.execute(insert(s.devices).values(id=identity, label=data["label"], kind=data["kind"], version=1))
            elif kind == "contracts":
                db.execute(insert(s.contracts).values(id=identity, spec=data["spec"], version=1))
            elif kind == "snapshots":
                snapshot = Snapshot.model_validate(data["spec"])
                value = snapshot.model_dump(mode="json")
                db.execute(insert(s.snapshots).values(id=identity, spec=value, hash=digest(value), version=1))
            elif kind == "incidents":
                self._get(db, s.devices, data["device_id"])
                self._get(db, s.snapshots, data["snapshot_id"])
                db.execute(insert(s.incidents).values(id=identity, device_id=data["device_id"],
                    snapshot_id=data["snapshot_id"], evidence=data["evidence"], version=1))
            elif kind == "roots":
                db.execute(insert(s.roots).values(id=identity, label=data["label"], status="ACTIVE", version=1))
            else:
                raise DomainError("UNKNOWN_RECORD_KIND", 422)
            self._event(db, "RECORD_CREATED", record_kind=kind, entity_id=identity)
            return {"id": identity, "version": 1}
        return self.command(key, "create:" + kind, version, data, execute)

    def _insert_artifact(self, db, label, payload, bindings, parents=(), complete=True):
        identity = uid()
        known_edges = db.execute(select(s.edges)).mappings().all()
        graph = {}
        for edge in known_edges:
            graph.setdefault(edge["child_id"], []).append(edge["parent_id"])
        closure(graph, [(parent, identity) for parent in parents])
        db.execute(insert(s.artifacts).values(id=identity, label=label, payload=payload, hash=sha(payload),
                   lineage_complete=int(complete), status="STAGED" if complete else "HELD", created_at=self.clock()))
        for root, version in bindings.items():
            db.execute(insert(s.artifact_roots).values(artifact_id=identity, root_id=root, root_version=version))
        for parent in parents:
            db.execute(insert(s.edges).values(parent_id=parent, child_id=identity))
        if complete:
            self._guard(db, bindings)
            db.execute(update(s.artifacts).where(s.artifacts.c.id == identity).values(status="ACTIVE"))
        self._event(db, "ARTIFACT_PROMOTED" if complete else "ARTIFACT_HELD", artifact_id=identity,
                    roots=list(sorted(bindings)), payload_hash=sha(payload), measured_quality=False)
        return identity

    def create_artifact(self, data, version, key):
        def execute(db):
            bindings = []
            for identity in data["root_ids"]:
                root = self._get(db, s.roots, identity)
                bindings.append({identity: root["version"]})
            for parent in data["parent_ids"]:
                self._artifact(db, parent)
                bindings.append(self._bindings(db, parent))
            roots = merge_roots(bindings) if bindings else {}
            if roots:
                self._guard(db, roots)
            identity = self._insert_artifact(db, data["label"], data["payload"], roots, data["parent_ids"], bool(roots))
            return {"id": identity, "hash": sha(data["payload"]), "status": "ACTIVE" if roots else "HELD"}
        return self.command(key, "artifact:create", version, data, execute)

    def create_plan(self, data, version, key):
        def execute(db):
            incident = self._get(db, s.incidents, data["incident_id"])
            if incident["snapshot_id"] != data["snapshot_id"]:
                raise DomainError("SNAPSHOT_INCIDENT_MISMATCH")
            identity = uid()
            db.execute(insert(s.plans).values(id=identity, incident_id=incident["id"], snapshot_id=incident["snapshot_id"],
                                              status="QUEUED", version=1))
            return {"id": identity, "job_id": self._job(db, "PLAN", identity), "status": "QUEUED"}
        return self.command(key, "plan:create", version, data, execute)

    def apply_plan(self, identity, version, key, adapter="simulation"):
        def execute(db):
            if adapter not in ("simulation", "packet-lab"):
                raise DomainError("UNSUPPORTED_ADAPTER", 422)
            if adapter == "packet-lab" and not os.environ.get("WITHAQ_PEP_SIGNING_KEY"):
                raise DomainError("PACKET_LAB_NOT_CONFIGURED", 503)
            plan = self._get(db, s.plans, identity)
            snapshot = self._get(db, s.snapshots, plan["snapshot_id"])
            if not plan["candidate"] or digest(plan["candidate"]) != plan["hash"] or digest(snapshot["spec"]) != snapshot["hash"]:
                raise DomainError("PLAN_BINDING_MISMATCH")
            if not validate(Snapshot.model_validate(snapshot["spec"]), Plan.model_validate(plan["candidate"])).accepted:
                raise DomainError("VALIDATION_REJECTED")
            existing = db.execute(select(s.enforcements).where(s.enforcements.c.plan_id == identity)).mappings().first()
            if existing:
                raise DomainError("PLAN_ALREADY_APPLIED_OR_PENDING")
            attempt_id = uid()
            db.execute(insert(s.enforcements).values(id=attempt_id, plan_id=identity, status="QUEUED", result={"adapter": adapter}, version=1))
            return {"id": attempt_id, "job_id": self._job(db, "APPLY", attempt_id), "status": "QUEUED"}
        return self.command(key, "plan:apply", version, {"id": identity, "adapter": adapter}, execute)

    def create_run(self, data, version, key):
        def execute(db):
            input_ids = [item["artifact_id"] for item in data["inputs"]]
            if len(input_ids) != len(set(input_ids)):
                raise DomainError("DUPLICATE_INPUT", 422)
            inputs, roots = [], []
            for item in data["inputs"]:
                artifact = self._artifact(db, item["artifact_id"])
                inputs.append({**item, "hash": artifact["hash"]})
                roots.append(self._bindings(db, artifact["id"]))
            bindings = merge_roots(roots)
            if data.get("replacement_for"):
                old = self._get(db, s.artifacts, data["replacement_for"])
                old_roots = self._bindings(db, old["id"])
                try:
                    self._guard(db, old_roots)
                except DomainError:
                    pass
                else:
                    raise DomainError("RECOVERY_NOT_NEEDED")
                if set(old_roots) & set(bindings):
                    raise DomainError("RECOVERY_DEPENDENCY_NOT_INDEPENDENT", 403)
            sealed = {"inputs": inputs, "roots": bindings, "task": data["task"],
                      "replacement_for": data.get("replacement_for"), "provider": "mock", "hidden_inputs": False,
                      "delay_s": data.get("delay_s", 0)}
            manifest_id, identity = uid(), uid()
            db.execute(insert(s.manifests).values(id=manifest_id, sealed=sealed, hash=digest(sealed)))
            db.execute(insert(s.runs).values(id=identity, manifest_id=manifest_id, task=data["task"], label=data["label"],
                                             status="QUEUED", version=1))
            for item in inputs:
                db.execute(insert(s.run_inputs).values(run_id=identity, artifact_id=item["artifact_id"], role=item["role"]))
            self._event(db, "MANIFEST_SEALED", run_id=identity, manifest_id=manifest_id, manifest_hash=digest(sealed))
            return {"id": identity, "manifest_id": manifest_id, "manifest_hash": digest(sealed),
                    "job_id": self._job(db, "MODEL", identity), "status": "QUEUED"}
        return self.command(key, "run:create", version, data, execute)

    def revoke(self, identity, reason, version, key):
        def execute(db):
            root = self._get(db, s.roots, identity)
            if root["status"] != "ACTIVE":
                raise DomainError("ROOT_ALREADY_REVOKED")
            barrier = root["version"] + 1
            db.execute(update(s.roots).where(s.roots.c.id == identity).values(status="REVOKED", version=barrier))
            revocation_id = uid()
            db.execute(insert(s.revocations).values(id=revocation_id, root_id=identity, barrier_version=barrier,
                                                  reason=reason, at=self.clock()))
            proven = list(db.execute(select(s.artifact_roots.c.artifact_id).where(s.artifact_roots.c.root_id == identity)).scalars())
            precaution = list(db.execute(select(s.artifacts.c.id).where(s.artifacts.c.lineage_complete == 0)).scalars())
            self._event(db, "ROOT_REVOKED", root_id=identity, barrier_version=barrier, proven=proven, precaution=precaution)
            return {"id": revocation_id, "barrier_version": barrier, "proven": proven, "precaution": precaution,
                    "job_id": self._job(db, "REVOKE", revocation_id)}
        return self.command(key, "root:revoke", version, {"id": identity, "reason": reason}, execute)

    def inspect_egress(self, data, version, key):
        def execute(db):
            artifact = self._artifact(db, data["artifact_id"])
            bindings = self._bindings(db, artifact["id"])
            inspected = self.policy.inspect(artifact["payload"], data["destination"], data["account"], data["purpose"])
            payload = inspected["payload"]
            binding = {"artifact_id": artifact["id"], "payload_hash": sha(payload), "roots": bindings,
                       "destination": data["destination"], "account": data["account"], "purpose": data["purpose"],
                       "policy_hash": inspected["policy_hash"], "policy_version": inspected["policy_version"],
                       "approval_required": inspected["approval"], "expires_at": self.clock() + 300}
            identity = uid()
            status = "BLOCKED" if inspected["decision"] == "BLOCK" else ("REVIEW_REQUIRED" if inspected["approval"] else "READY")
            db.execute(insert(s.egress).values(id=identity, artifact_id=artifact["id"], binding=binding,
                       binding_hash=digest(binding), payload=payload, decision=inspected["decision"],
                       status=status, reason=inspected["reason"], expires_at=binding["expires_at"], version=1))
            self._event(db, "DISCLOSURE_INSPECTED", request_id=identity, decision=inspected["decision"],
                        status=status, payload_hash=sha(payload), roots=list(bindings))
            return {"id": identity, "decision": inspected["decision"], "status": status, "payload_hash": sha(payload),
                    "binding_hash": digest(binding), "reason": inspected["reason"]}
        return self.command(key, "egress:inspect", version, data, execute)

    def _egress_guard(self, db, request):
        self._artifact(db, request["artifact_id"])
        self._guard(db, request["binding"]["roots"])
        _, current_policy_hash = self.policy.load()
        if request["expires_at"] < self.clock():
            raise DomainError("APPROVAL_EXPIRED", 403)
        if request["binding"]["policy_hash"] != current_policy_hash:
            raise DomainError("STALE_POLICY", 403)
        if digest(request["binding"]) != request["binding_hash"] or sha(request["payload"]) != request["binding"]["payload_hash"]:
            raise DomainError("PAYLOAD_OR_BINDING_CHANGED", 403)

    def approve(self, identity, binding_hash, version, key):
        def execute(db):
            request = self._get(db, s.egress, identity)
            self._egress_guard(db, request)
            if request["status"] != "REVIEW_REQUIRED" or binding_hash != request["binding_hash"]:
                raise DomainError("EXACT_APPROVAL_REQUIRED", 403)
            db.execute(insert(s.approvals).values(id=uid(), request_id=identity, binding_hash=binding_hash, actor="operator"))
            db.execute(update(s.egress).where(s.egress.c.id == identity).values(status="APPROVED", version=request["version"] + 1))
            self._event(db, "EXACT_REQUEST_APPROVED", request_id=identity, binding_hash=binding_hash)
            return {"id": identity, "status": "APPROVED"}
        return self.command(key, "egress:approve", version, {"id": identity, "binding_hash": binding_hash}, execute)

    def dispatch(self, identity, version, key):
        def execute(db):
            request = self._get(db, s.egress, identity)
            self._egress_guard(db, request)
            if request["status"] not in ("READY", "APPROVED"):
                raise DomainError("REQUEST_NOT_DISPATCHABLE", 403)
            if request["binding"]["approval_required"]:
                approval = db.execute(select(s.approvals).where(s.approvals.c.request_id == identity)).mappings().first()
                if not approval or approval["binding_hash"] != request["binding_hash"]:
                    raise DomainError("EXACT_APPROVAL_REQUIRED", 403)
            db.execute(update(s.egress).where(s.egress.c.id == identity).values(status="QUEUED", version=request["version"] + 1))
            return {"id": identity, "job_id": self._job(db, "EGRESS", identity), "status": "QUEUED"}
        return self.command(key, "egress:dispatch", version, {"id": identity}, execute)

    def read_egress(self, identity):
        with self.db.transaction() as db:
            request = self._get(db, s.egress, identity)
            if request["status"] == "BLOCKED":
                return {"id": identity, "status": "BLOCKED", "payload": "", "decision": "BLOCK"}
            self._egress_guard(db, request)
            return request

    def _lease(self, db, identity, attempt_id, fence, worker_id):
        job = self._get(db, s.outbox, identity)
        if (job["attempt_id"], job["fence"], job["worker_id"]) != (attempt_id, fence, worker_id):
            raise DomainError("STALE_FENCING_TOKEN")
        if job["state"] != "LEASED" or job["lease_until"] <= self.clock():
            raise DomainError("LEASE_EXPIRED_OR_FINISHED")
        return job

    def claim(self, worker_id, kinds=("PLAN", "MODEL", "APPLY", "REVOKE"), lease_s=20):
        with self.db.transaction() as db:
            jobs = db.execute(select(s.outbox).where(s.outbox.c.kind.in_(kinds)).order_by(s.outbox.c.created_at, s.outbox.c.id)).mappings().all()
            for row in jobs:
                job = dict(row)
                if job["state"] == "LEASED" and job["lease_until"] <= self.clock():
                    db.execute(update(s.attempts).where(s.attempts.c.id == job["attempt_id"]).values(state="EXPIRED"))
                    if job["kind"] == "EGRESS":
                        request = self._get(db, s.egress, job["entity_id"])
                        if request["status"] == "ADMITTED":
                            db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(status="OUTCOME_UNKNOWN"))
                            db.execute(update(s.outbox).where(s.outbox.c.id == job["id"]).values(state="OUTCOME_UNKNOWN"))
                            self._event(db, "OUTCOME_UNKNOWN", request_id=request["id"], reason="LEASE_LOST_AFTER_ADMISSION")
                            continue
                elif job["state"] != "QUEUED":
                    continue
                if job["fence"] >= 3:
                    db.execute(update(s.outbox).where(s.outbox.c.id == job["id"]).values(state="FAILED"))
                    if job["kind"] == "MODEL":
                        db.execute(update(s.runs).where(s.runs.c.id == job["entity_id"]).values(status="REJECTED", reason="ATTEMPT_LIMIT_REACHED"))
                    elif job["kind"] == "PLAN":
                        db.execute(update(s.plans).where(s.plans.c.id == job["entity_id"]).values(status="FAILED"))
                    elif job["kind"] == "APPLY":
                        db.execute(update(s.enforcements).where(s.enforcements.c.id == job["entity_id"]).values(status="FAILED"))
                    elif job["kind"] == "EGRESS":
                        db.execute(update(s.egress).where(s.egress.c.id == job["entity_id"]).values(status="FAILED", reason="ATTEMPT_LIMIT_REACHED"))
                    self._event(db, "ATTEMPT_LIMIT_REACHED", job_id=job["id"], job_kind=job["kind"])
                    continue
                attempt_id, fence = uid(), job["fence"] + 1
                values = {"state": "LEASED", "attempt_id": attempt_id, "fence": fence, "worker_id": worker_id,
                          "lease_until": self.clock() + lease_s}
                db.execute(update(s.outbox).where(s.outbox.c.id == job["id"]).values(**values))
                db.execute(insert(s.attempts).values(id=attempt_id, job_id=job["id"], fence=fence, worker_id=worker_id,
                                                     state="LEASED", at=self.clock()))
                self._event(db, "JOB_CLAIMED", job_id=job["id"], attempt_id=attempt_id, fence=fence)
                return {**job, **values}
            return None

    def heartbeat(self, identity, attempt_id, fence, worker_id):
        with self.db.transaction() as db:
            self._lease(db, identity, attempt_id, fence, worker_id)
            until = self.clock() + 20
            db.execute(update(s.outbox).where(s.outbox.c.id == identity).values(lease_until=until))
            return {"lease_until": until}

    def job_inputs(self, identity, attempt_id, fence, worker_id):
        with self.db.transaction() as db:
            job = self._lease(db, identity, attempt_id, fence, worker_id)
            if job["kind"] == "PLAN":
                plan = self._get(db, s.plans, job["entity_id"])
                snapshot = self._get(db, s.snapshots, plan["snapshot_id"])
                return {"snapshot": snapshot["spec"], "snapshot_hash": snapshot["hash"]}
            if job["kind"] == "APPLY":
                attempt = self._get(db, s.enforcements, job["entity_id"])
                plan = self._get(db, s.plans, attempt["plan_id"])
                snapshot = self._get(db, s.snapshots, plan["snapshot_id"])
                return {"snapshot": snapshot["spec"], "candidate": plan["candidate"], "plan_hash": plan["hash"],
                        "adapter": (attempt["result"] or {}).get("adapter", "simulation")}
            if job["kind"] == "MODEL":
                run = self._get(db, s.runs, job["entity_id"])
                manifest = self._get(db, s.manifests, run["manifest_id"])
                if digest(manifest["sealed"]) != manifest["hash"]:
                    raise DomainError("MANIFEST_INTEGRITY_FAILED", 403)
                self._guard(db, manifest["sealed"]["roots"])
                inputs = []
                for item in manifest["sealed"]["inputs"]:
                    artifact = self._artifact(db, item["artifact_id"])
                    if artifact["hash"] != item["hash"]:
                        raise DomainError("MANIFEST_INPUT_CHANGED", 403)
                    inputs.append({**item, "payload": artifact["payload"]})
                return {"task": run["task"], "inputs": inputs, "manifest_hash": manifest["hash"], "delay_s": manifest["sealed"].get("delay_s", 0)}
            if job["kind"] == "REVOKE":
                return {"revocation": self._get(db, s.revocations, job["entity_id"])}
            raise DomainError("JOB_KIND_DENIED", 403)

    def admit(self, identity, attempt_id, fence, worker_id):
        # Commit before the gateway can invoke its adapter. Admission is irreversible.
        with self.db.transaction() as db:
            job = self._lease(db, identity, attempt_id, fence, worker_id)
            if job["kind"] != "EGRESS":
                raise DomainError("JOB_KIND_DENIED", 403)
            request = self._get(db, s.egress, job["entity_id"])
            self._egress_guard(db, request)
            if request["status"] != "QUEUED":
                raise DomainError("ALREADY_ADMITTED_NO_RETRY", 403)
            if request["binding"]["approval_required"]:
                approval = db.execute(select(s.approvals).where(s.approvals.c.request_id == request["id"])).mappings().first()
                if not approval or approval["binding_hash"] != request["binding_hash"]:
                    raise DomainError("EXACT_APPROVAL_REQUIRED", 403)
            db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(status="ADMITTED"))
            self._event(db, "DISPATCH_ADMITTED", request_id=request["id"], binding_hash=request["binding_hash"])
            return {"id": request["id"], "payload": request["payload"], "binding": request["binding"], "mode": "mock"}

    def complete(self, identity, attempt_id, fence, worker_id, result):
        result_hash = digest(result)
        with self.db.transaction() as db:
            prior = self._get(db, s.outbox, identity)
            if prior["state"] in ("DONE", "FAILED", "OUTCOME_UNKNOWN") and prior["result_hash"] == result_hash:
                if (prior["attempt_id"], prior["fence"], prior["worker_id"]) != (attempt_id, fence, worker_id):
                    raise DomainError("STALE_FENCING_TOKEN")
                return {"status": prior["state"], "duplicate": True}
            job = self._lease(db, identity, attempt_id, fence, worker_id)
            status, reason = "DONE", None
            try:
                if "error" in result:
                    safe_codes = {"UNSUPPORTED_PACKET_MODEL", "PACKET_TRIAL_FAILED", "MEASURED_FUNCTION_CONTRACT_FAILED", "VALIDATION_REJECTED", "RESULT_SCHEMA_INVALID"}
                    raise DomainError(result["error"] if result["error"] in safe_codes else "WORKER_EXECUTION_FAILED")
                if job["kind"] == "PLAN":
                    plan = self._get(db, s.plans, job["entity_id"])
                    snapshot = self._get(db, s.snapshots, plan["snapshot_id"])
                    candidate = Plan.model_validate(result["candidate"])
                    verdict = validate(Snapshot.model_validate(snapshot["spec"]), candidate)
                    candidate_data = candidate.model_dump(mode="json")
                    if result["snapshot_hash"] != snapshot["hash"] or result["verdict"] != verdict.model_dump(mode="json"):
                        raise DomainError("VALIDATION_BINDING_MISMATCH")
                    db.execute(update(s.plans).where(s.plans.c.id == plan["id"]).values(candidate=candidate_data,
                        hash=digest(candidate_data), status=candidate.status, version=plan["version"] + 1))
                    db.execute(insert(s.reports).values(id=uid(), plan_id=plan["id"], snapshot_hash=snapshot["hash"],
                        plan_hash=digest(candidate_data), verdict=verdict.model_dump(mode="json")))
                elif job["kind"] == "MODEL":
                    run = self._get(db, s.runs, job["entity_id"])
                    manifest = self._get(db, s.manifests, run["manifest_id"])
                    if digest(manifest["sealed"]) != manifest["hash"] or result["manifest_hash"] != manifest["hash"]:
                        raise DomainError("MANIFEST_INTEGRITY_FAILED", 403)
                    self._guard(db, manifest["sealed"]["roots"])
                    inputs = [self._artifact(db, item["artifact_id"]) for item in manifest["sealed"]["inputs"]]
                    if result["payload"] != mock_output(run["task"], inputs):
                        raise DomainError("MOCK_OUTPUT_INTEGRITY_FAILED", 403)
                    if len(result["payload"].strip()) < 16 or len(result["payload"].encode()) > 65536:
                        raise DomainError("QUALITY_CONTRACT_FAILED", 403)
                    output_id = self._insert_artifact(db, run["label"], result["payload"], manifest["sealed"]["roots"],
                                                      [item["artifact_id"] for item in manifest["sealed"]["inputs"]])
                    db.execute(update(s.runs).where(s.runs.c.id == run["id"]).values(status="PUBLISHED", output_id=output_id,
                                                                               version=run["version"] + 1))
                elif job["kind"] == "APPLY":
                    attempt = self._get(db, s.enforcements, job["entity_id"])
                    plan = self._get(db, s.plans, attempt["plan_id"])
                    snapshot = self._get(db, s.snapshots, plan["snapshot_id"])
                    candidate = Plan.model_validate(plan["candidate"])
                    if not validate(Snapshot.model_validate(snapshot["spec"]), candidate).accepted:
                        raise DomainError("VALIDATION_REJECTED")
                    if (attempt["result"] or {}).get("adapter") == "packet-lab":
                        receipt = result.get("receipt", {})
                        secret = os.environ.get("WITHAQ_PEP_SIGNING_KEY", "")
                        signature = hmac.new(secret.encode(), digest(receipt).encode(), hashlib.sha256).hexdigest()
                        if not secret or not hmac.compare_digest(signature, result.get("signature", "")):
                            raise DomainError("ENFORCEMENT_RECEIPT_INVALID")
                        if receipt.get("status") != "LAB_CONFIRMED" or receipt.get("plan_hash") != plan["hash"] or receipt.get("snapshot_hash") != snapshot["hash"] or receipt.get("actions") != list(candidate.actions) or receipt.get("measured_packets") is not True:
                            raise DomainError("ENFORCEMENT_RECEIPT_INVALID")
                        required_checks = {"attack_paths_exist_before", "relay_reaches_protected_before", "direct_and_relay_blocked_after", "existing_session_blocked", "each_monitor_and_alert_event_under_2s", "controller_absence_keeps_denies", "quarantine_breaks_functions", "no_alternate_client_interface"}
                        checks = receipt.get("evidence", {}).get("checks", {})
                        if set(checks) != required_checks or not all(value is True for value in checks.values()):
                            raise DomainError("PACKET_CHECKS_FAILED")
                        for hypothesis in Snapshot.model_validate(snapshot["spec"]).hypotheses:
                            for contract in hypothesis.contracts:
                                if not contract.critical:
                                    continue
                                observations = receipt["evidence"]["cases"]["mfsc_after"][contract.target.lower()]["records"]
                                if receipt.get("contracts", {}).get(hypothesis.id + ":" + contract.id) is not True or len(observations) != 5 or not all(
                                    row.get("delivered") is True and 0 <= row["latency_s"] <= contract.max_latency_s and
                                    0 <= row["freshness_s"] <= contract.max_age_s for row in observations):
                                    raise DomainError("MEASURED_FUNCTION_CONTRACT_FAILED")
                        confirmed_status = "LAB_CONFIRMED"
                    else:
                        expected = {"status": "SIMULATED_CONFIRMED", "plan_hash": plan["hash"], "actions": list(candidate.actions), "measured_packets": False}
                        if result != expected:
                            raise DomainError("ENFORCEMENT_RECEIPT_INVALID")
                        confirmed_status = "SIMULATED_CONFIRMED"
                    db.execute(update(s.enforcements).where(s.enforcements.c.id == attempt["id"]).values(
                        status=confirmed_status, result=result, version=attempt["version"] + 1))
                elif job["kind"] == "REVOKE":
                    revocation = self._get(db, s.revocations, job["entity_id"])
                    affected = db.execute(select(s.artifact_roots.c.artifact_id).where(s.artifact_roots.c.root_id == revocation["root_id"])).scalars().all()
                    if affected:
                        db.execute(update(s.artifacts).where(s.artifacts.c.id.in_(affected)).values(status="REVOKED"))
                elif job["kind"] == "EGRESS":
                    request = self._get(db, s.egress, job["entity_id"])
                    if request["status"] != "ADMITTED":
                        raise DomainError("DISPATCH_NOT_ADMITTED")
                    if result.get("status") not in ("MOCK_SENT", "OUTCOME_UNKNOWN", "FAILED") or result.get("payload_hash") != request["binding"]["payload_hash"] or result.get("external_bytes_sent") != 0:
                        raise DomainError("GATEWAY_RECEIPT_INVALID")
                    db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(status=result["status"]))
                    if result["status"] != "MOCK_SENT":
                        status = result["status"]
                else:
                    raise DomainError("JOB_KIND_DENIED", 403)
            except (DomainError, ValueError, KeyError, TypeError, AttributeError) as error:
                reason = error.code if isinstance(error, DomainError) else "RESULT_SCHEMA_INVALID"
                status = "FAILED"
                if job["kind"] == "MODEL":
                    db.execute(update(s.runs).where(s.runs.c.id == job["entity_id"]).values(status="REJECTED", reason=reason))
                elif job["kind"] == "EGRESS":
                    request = self._get(db, s.egress, job["entity_id"])
                    # A gateway error after admission cannot prove that the provider saw no bytes.
                    status = "OUTCOME_UNKNOWN" if request["status"] == "ADMITTED" else "FAILED"
                    db.execute(update(s.egress).where(s.egress.c.id == request["id"]).values(status=status, reason=reason))
                elif job["kind"] == "APPLY":
                    db.execute(update(s.enforcements).where(s.enforcements.c.id == job["entity_id"]).values(status="FAILED"))
                elif job["kind"] == "PLAN":
                    db.execute(update(s.plans).where(s.plans.c.id == job["entity_id"]).values(status="FAILED"))
            db.execute(update(s.outbox).where(s.outbox.c.id == identity).values(state=status, result_hash=result_hash))
            db.execute(update(s.attempts).where(s.attempts.c.id == attempt_id).values(state=status))
            self._event(db, "JOB_COMPLETED", job_id=identity, job_kind=job["kind"], status=status, reason=reason,
                        result_hash=result_hash, fence=fence)
            return {"status": status, "reason": reason}

    def state(self):
        with self.db.transaction() as db:
            result = {"version": db.execute(select(s.workspace.c.version)).scalar_one(),
                      "mode": "mock", "database": self.db.engine.dialect.name, "schema": "0003"}
            tables = {"devices": s.devices, "contracts": s.contracts, "snapshots": s.snapshots, "incidents": s.incidents,
                      "plans": s.plans, "reports": s.reports, "enforcements": s.enforcements, "roots": s.roots,
                      "artifacts": s.artifacts, "runs": s.runs, "manifests": s.manifests,
                      "revocations": s.revocations, "egress": s.egress, "jobs": s.outbox, "events": s.audit}
            for name, table in tables.items():
                records = [dict(row) for row in db.execute(select(table)).mappings()]
                for item in records:
                    if name == "artifacts":
                        item["roots"] = self._bindings(db, item["id"])
                        item["parents"] = list(db.execute(select(s.edges.c.parent_id).where(s.edges.c.child_id == item["id"])).scalars())
                        try:
                            self._guard(db, item["roots"])
                        except DomainError as error:
                            item["status"] = "HELD" if error.code.startswith("UNKNOWN") else "REVOKED"
                    if name == "egress" and item["status"] in ("READY", "REVIEW_REQUIRED", "APPROVED", "QUEUED"):
                        try:
                            self._egress_guard(db, item)
                        except DomainError as error:
                            item.update(status="BLOCKED", reason=error.code)
                    if name == "jobs":
                        item.pop("worker_id", None)
                    item.pop("payload", None)
                result[name] = records
            result["events"].sort(key=lambda item: (item["at"], item["id"]))
            created = {}
            for item in result["events"]:
                for field in ("entity_id", "artifact_id", "run_id", "request_id", "job_id"):
                    identity = item["details"].get(field)
                    if identity:
                        created.setdefault(identity, item["at"])
            for name in tables:
                if name != "events":
                    result[name].sort(key=lambda item: (item.get("created_at", item.get("at", created.get(item["id"], 0))), item["id"]))
            return result

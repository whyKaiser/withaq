"""Single-machine simulation store; transactions serialize each demo aggregate.

Not the PostgreSQL/outbox implementation specified for the distributed lab.
Only synthetic fixture content is stored. Audit records omit artifact bytes.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import Plan
from .planner import solve
from .scenarios import scenarios
from .validator import validate


class DomainError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def event(state, kind, **details):
    state["events"].append({"seq": len(state["events"]) + 1, "at": datetime.now(timezone.utc).isoformat(),
                            "kind": kind, "details": details})


def guard(state, roots):
    if not roots:
        raise DomainError("UNKNOWN_LINEAGE", 403)
    for identity, version in roots.items():
        root = state["roots"].get(identity)
        if root is None:
            raise DomainError("UNKNOWN_ROOT", 403)
        if root["status"] != "ACTIVE":
            raise DomainError("ROOT_REVOKED", 403)
        if root["version"] != version:
            raise DomainError("STALE_ROOT_VERSION")


def artifact_state(state, item):
    try:
        guard(state, item["roots"])
        return "ACTIVE"
    except DomainError as error:
        return "HELD" if error.code.startswith("UNKNOWN") else "REVOKED"


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS demo_runs(id TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands(key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, response TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ready(self):
        with self.connection() as db:
            return db.execute("PRAGMA user_version").fetchone()[0] == 1

    def _read(self, db, identity):
        row = db.execute("SELECT state FROM demo_runs WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise DomainError("RUN_NOT_FOUND", 404)
        return json.loads(row[0])

    def _public(self, state):
        result = json.loads(json.dumps(state))
        result["artifacts"] = [{"id": a["id"], "roots": a["roots"], "parents": a["parents"],
                                "status": artifact_state(state, a)} for a in state["artifacts"].values()]
        result.pop("pending_output", None)
        # Disclosure payload is visible only through its dedicated inspection response.
        for request in result["disclosures"].values():
            request.pop("payload", None)
            if request["status"] in ("REVIEW_REQUIRED", "APPROVED"):
                try:
                    guard(state, request["roots"])
                except DomainError as error:
                    request.update(status="BLOCKED", reason=error.code)
        return result

    def read(self, identity):
        with self.connection() as db:
            return self._public(self._read(db, identity))

    def command(self, key, request, operation):
        request_hash = digest(request)
        with self.connection() as db:
            previous = db.execute("SELECT request_hash,response FROM commands WHERE key=?", (key,)).fetchone()
            if previous:
                if previous[0] != request_hash:
                    raise DomainError("IDEMPOTENCY_CONFLICT")
                cached = json.loads(previous[1])
                disclosure = cached.get("command_result", {}).get("request", {})
                if disclosure.get("payload"):
                    guard(self._read(db, request["run"]), disclosure["roots"])
                return cached
            response = operation(db)
            db.execute("INSERT INTO commands VALUES(?,?,?)", (key, request_hash, json.dumps(response)))
            return response

    def create(self, scenario, policy, key):
        if scenario not in scenarios():
            raise DomainError("SCENARIO_NOT_FOUND", 404)

        def execute(db):
            snapshot = scenarios()[scenario]
            plan = solve(snapshot)
            if policy != "mfsc":
                actions = ("c",) if policy == "quarantine" else ("a",)
                plan = Plan(snapshot_id=snapshot.id, revision=snapshot.revision,
                            policy_version=snapshot.policy_version, capability_version=snapshot.capability_version,
                            status="FEASIBLE", actions=actions, cost=1, reason="Untrusted baseline candidate; independent validation required.")
            verdict = validate(snapshot, plan)
            identity = str(uuid4())
            artifacts = {
                "T1": {"id": "T1", "roots": {"S1": 1}, "parents": [], "payload": "Synthetic monitoring report from S1."},
                "T2": {"id": "T2", "roots": {"S1": 1}, "parents": ["T1"], "payload": "Synthetic summary derived from T1."},
                "T3": {"id": "T3", "roots": {"S3": 1}, "parents": [], "payload": "Independent synthetic report from S3."},
                "C-D": {"id": "C-D", "roots": {}, "parents": [], "payload": "Unproven lineage; always held."},
            }
            state = {"id": identity, "version": 1, "mode": "simulation", "scenario": scenario, "policy": policy,
                     "snapshot": snapshot.model_dump(mode="json"), "plan": plan.model_dump(mode="json"),
                     "validation": verdict.model_dump(mode="json"),
                     "snapshot_hash": digest(snapshot.model_dump(mode="json")), "plan_hash": digest(plan.model_dump(mode="json")),
                     "enforcement": "NOT_APPLIED", "roots": {r: {"status": "ACTIVE", "version": 1} for r in ("S1", "S2", "S3")},
                     "artifacts": artifacts, "pending_output": {"roots": {"S1": 1}, "manifest_hash": digest({"S1": 1})},
                     "disclosures": {}, "events": []}
            event(state, "INCIDENT_SIMULATED", scenario=scenario)
            event(state, "PLAN_CHECKED", accepted=verdict.accepted, plan_hash=state["plan_hash"], snapshot_hash=state["snapshot_hash"])
            db.execute("INSERT INTO demo_runs VALUES(?,?)", (identity, json.dumps(state)))
            return self._public(state)
        return self.command(key, {"action": "create", "scenario": scenario, "policy": policy}, execute)

    def mutate(self, identity, action, expected_version, key, body=None):
        body = body or {}

        def execute(db):
            state = self._read(db, identity)
            if state["version"] != expected_version:
                raise DomainError("STALE_SNAPSHOT")
            detail = None
            if action == "apply":
                snapshot = scenarios()[state["scenario"]]
                candidate = Plan.model_validate(state["plan"])
                if digest(candidate.model_dump(mode="json")) != state["plan_hash"] or digest(snapshot.model_dump(mode="json")) != state["snapshot_hash"]:
                    raise DomainError("PLAN_BINDING_MISMATCH")
                if not validate(snapshot, candidate).accepted:
                    raise DomainError("VALIDATION_REJECTED")
                state["enforcement"] = "SIMULATED_CONFIRMED"
                event(state, "SIMULATED_RULES_APPLIED", actions=list(candidate.actions), measured_packets=False)
            elif action == "revoke":
                root = state["roots"]["S1"]
                if root["status"] == "ACTIVE":
                    root.update(status="REVOKED", version=root["version"] + 1)
                    event(state, "ROOT_REVOKED", root="S1", barrier_version=root["version"])
            elif action == "complete-late":
                try:
                    guard(state, state["pending_output"]["roots"])
                except DomainError as error:
                    detail = {"status": "REJECTED", "reason": error.code}
                    event(state, "LATE_PUBLICATION_REJECTED", reason=error.code)
                else:
                    detail = {"status": "PERMITTED", "reason": "Roots remain active."}
                    event(state, "PUBLICATION_GUARD_PASSED")
            elif action == "recover":
                if state["roots"]["S1"]["status"] != "REVOKED":
                    raise DomainError("RECOVERY_NOT_NEEDED")
                guard(state, {"S2": 1})
                if "T2b" not in state["artifacts"]:
                    state["artifacts"]["T2b"] = {"id": "T2b", "roots": {"S2": 1}, "parents": [], "payload": "New synthetic summary rebuilt only from approved S2."}
                    event(state, "REPLACEMENT_PUBLISHED", artifact="T2b", roots=["S2"], quality_check="deterministic_fixture_only")
            elif action == "inspect":
                artifact = state["artifacts"].get(body["artifact"])
                if not artifact:
                    raise DomainError("ARTIFACT_NOT_FOUND", 404)
                reason = None
                try:
                    guard(state, artifact["roots"])
                except DomainError as error:
                    reason = error.code
                if body["destination"] != "mock://review" or body["account"] != "demo" or body["purpose"] != "competition-demo":
                    reason = "DESTINATION_ACCOUNT_OR_PURPOSE_DENIED"
                payload = artifact["payload"] + body.get("extra_text", "")
                normalized = payload.casefold()
                if any(term in normalized for term in ("national_id", "password", "رقم الهوية", "كلمة المرور")):
                    reason = "PROHIBITED_FIELD"
                if reason:
                    payload = ""
                request_id = str(uuid4())
                request = {"id": request_id, "artifact": artifact["id"], "roots": artifact["roots"],
                           "payload": payload, "payload_hash": hashlib.sha256(payload.encode()).hexdigest(),
                           "destination": body["destination"], "account": body["account"], "purpose": body["purpose"],
                           "policy_version": 1, "status": "BLOCKED" if reason else "REVIEW_REQUIRED", "reason": reason,
                           "expires_at": datetime.now(timezone.utc).timestamp() + 300}
                state["disclosures"][request_id] = request
                detail = {"request": request, "warning": "Synthetic payload only; no external provider is contacted."}
                event(state, "DISCLOSURE_INSPECTED", request_id=request_id, decision=request["status"], reason=reason)
            elif action in ("approve", "dispatch"):
                request = state["disclosures"].get(body["request_id"])
                if not request:
                    raise DomainError("DISCLOSURE_NOT_FOUND", 404)
                if request["expires_at"] < datetime.now(timezone.utc).timestamp():
                    raise DomainError("APPROVAL_EXPIRED", 403)
                if request["status"] in ("OUTCOME_UNKNOWN", "SIMULATED_SENT"):
                    raise DomainError("ALREADY_ATTEMPTED_NO_RETRY")
                guard(state, request["roots"])
                binding = {k: request[k] for k in ("payload_hash", "destination", "account", "purpose", "roots", "policy_version", "expires_at")}
                if body["payload_hash"] != request["payload_hash"] or hashlib.sha256(request["payload"].encode()).hexdigest() != request["payload_hash"]:
                    raise DomainError("PAYLOAD_CHANGED", 403)
                if action == "approve":
                    if request["status"] != "REVIEW_REQUIRED":
                        raise DomainError("REQUEST_NOT_APPROVABLE", 403)
                    request["approval_hash"] = digest(binding)
                    request["status"] = "APPROVED"
                    event(state, "EXACT_REQUEST_APPROVED", request_id=request["id"], binding_hash=request["approval_hash"])
                else:
                    if request["status"] != "APPROVED" or request.get("approval_hash") != digest(binding):
                        raise DomainError("APPROVAL_REQUIRED", 403)
                    event(state, "DISPATCH_ADMITTED", request_id=request["id"], payload_hash=request["payload_hash"])
                    request["status"] = "OUTCOME_UNKNOWN" if body.get("lose_response") else "SIMULATED_SENT"
                    event(state, request["status"], request_id=request["id"], external_bytes_sent=0)
                    detail = {"status": request["status"], "external_bytes_sent": 0}
            else:
                raise DomainError("UNKNOWN_COMMAND", 400)
            state["version"] += 1
            db.execute("UPDATE demo_runs SET state=? WHERE id=?", (json.dumps(state), identity))
            result = self._public(state)
            if detail:
                result["command_result"] = detail
            return result
        return self.command(key, {"run": identity, "action": action, "expected_version": expected_version, "body": body}, execute)

    def read_artifact(self, identity, artifact_id):
        with self.connection() as db:
            state = self._read(db, identity)
            item = state["artifacts"].get(artifact_id)
            if item is None:
                raise DomainError("ARTIFACT_NOT_FOUND", 404)
            guard(state, item["roots"])
            return item

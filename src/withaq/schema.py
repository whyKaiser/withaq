"""Versioned relational schema. Migration 0001-0003 import these frozen definitions.

Payloads are synthetic UTF-8 in this lab. Production object storage is a separate gate.
Do not change these definitions in place after release; add a migration first.
"""
from sqlalchemy import (MetaData, Table, Column, String, Text, Integer, Float, JSON,
                        ForeignKey, CheckConstraint, UniqueConstraint)

metadata = MetaData()


def entity(name, *columns, checks=()):
    return Table(name, metadata, Column("id", String(36), primary_key=True),
                 *columns, *(CheckConstraint(c) for c in checks))


workspace = Table("workspace", metadata, Column("id", Integer, primary_key=True),
                  Column("version", Integer, nullable=False), CheckConstraint("version >= 0"))
devices = entity("devices", Column("label", String(120), nullable=False),
                 Column("kind", String(80), nullable=False), Column("version", Integer, nullable=False),
                 checks=("version >= 1",))
contracts = entity("function_contracts", Column("spec", JSON, nullable=False),
                   Column("version", Integer, nullable=False), checks=("version >= 1",))
snapshots = entity("snapshots", Column("spec", JSON, nullable=False),
                   Column("hash", String(64), nullable=False), Column("version", Integer, nullable=False),
                   checks=("version >= 1",))
incidents = entity("incidents", Column("device_id", ForeignKey("devices.id"), nullable=False),
                   Column("snapshot_id", ForeignKey("snapshots.id"), nullable=False),
                   Column("evidence", JSON, nullable=False), Column("version", Integer, nullable=False))
plans = entity("plans", Column("incident_id", ForeignKey("incidents.id"), nullable=False),
               Column("snapshot_id", ForeignKey("snapshots.id"), nullable=False),
               Column("candidate", JSON), Column("hash", String(64)),
               Column("status", String(24), nullable=False), Column("version", Integer, nullable=False))
reports = entity("validation_reports", Column("plan_id", ForeignKey("plans.id"), nullable=False),
                 Column("snapshot_hash", String(64), nullable=False), Column("plan_hash", String(64), nullable=False),
                 Column("verdict", JSON, nullable=False))
enforcements = entity("enforcement_attempts", Column("plan_id", ForeignKey("plans.id"), nullable=False),
                      Column("status", String(32), nullable=False), Column("result", JSON),
                      Column("version", Integer, nullable=False))

roots = entity("source_roots", Column("label", String(120), nullable=False),
               Column("status", String(16), nullable=False), Column("version", Integer, nullable=False),
               checks=("version >= 1", "status IN ('ACTIVE','REVOKED')"))
artifacts = entity("artifacts", Column("label", String(120), nullable=False),
                   Column("payload", Text, nullable=False), Column("hash", String(64), nullable=False),
                   Column("lineage_complete", Integer, nullable=False),
                   Column("status", String(16), nullable=False), Column("created_at", Float, nullable=False),
                   checks=("lineage_complete IN (0,1)", "status IN ('STAGED','ACTIVE','HELD','REVOKED')"))
artifact_roots = Table("artifact_roots", metadata,
                       Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True),
                       Column("root_id", ForeignKey("source_roots.id"), primary_key=True),
                       Column("root_version", Integer, nullable=False), CheckConstraint("root_version >= 1"))
edges = Table("lineage_edges", metadata,
              Column("parent_id", ForeignKey("artifacts.id"), primary_key=True),
              Column("child_id", ForeignKey("artifacts.id"), primary_key=True),
              CheckConstraint("parent_id <> child_id"))
manifests = entity("manifests", Column("sealed", JSON, nullable=False), Column("hash", String(64), nullable=False))
runs = entity("runs", Column("manifest_id", ForeignKey("manifests.id"), nullable=False),
              Column("task", String(32), nullable=False), Column("label", String(120), nullable=False),
              Column("status", String(24), nullable=False), Column("output_id", ForeignKey("artifacts.id")),
              Column("reason", String(120)), Column("version", Integer, nullable=False))
run_inputs = Table("run_inputs", metadata, Column("run_id", ForeignKey("runs.id"), primary_key=True),
                   Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True),
                   Column("role", String(24), nullable=False))
revocations = entity("revocations", Column("root_id", ForeignKey("source_roots.id"), nullable=False),
                     Column("barrier_version", Integer, nullable=False), Column("reason", String(120), nullable=False),
                     Column("at", Float, nullable=False))

egress = entity("egress_requests", Column("artifact_id", ForeignKey("artifacts.id"), nullable=False),
                Column("binding", JSON, nullable=False), Column("binding_hash", String(64), nullable=False),
                Column("payload", Text, nullable=False), Column("decision", String(24), nullable=False),
                Column("status", String(24), nullable=False), Column("reason", String(120)),
                Column("expires_at", Float, nullable=False), Column("version", Integer, nullable=False))
approvals = entity("approvals", Column("request_id", ForeignKey("egress_requests.id"), nullable=False, unique=True),
                   Column("binding_hash", String(64), nullable=False), Column("actor", String(24), nullable=False))
outbox = entity("outbox", Column("event_id", String(36), nullable=False, unique=True),
                Column("kind", String(24), nullable=False), Column("entity_id", String(36), nullable=False),
                Column("state", String(24), nullable=False), Column("fence", Integer, nullable=False),
                Column("attempt_id", String(36)), Column("worker_id", String(80)),
                Column("lease_until", Float), Column("created_at", Float, nullable=False),
                Column("result_hash", String(64)), checks=("fence >= 0",))
attempts = entity("job_attempts", Column("job_id", ForeignKey("outbox.id"), nullable=False),
                  Column("fence", Integer, nullable=False), Column("worker_id", String(80), nullable=False),
                  Column("state", String(24), nullable=False), Column("at", Float, nullable=False),
                  UniqueConstraint("job_id", "fence"))
audit = entity("audit_events", Column("kind", String(80), nullable=False),
               Column("details", JSON, nullable=False), Column("at", Float, nullable=False))
commands = Table("idempotency_keys", metadata, Column("id", String(128), primary_key=True),
                 Column("request_hash", String(64), nullable=False), Column("response", JSON, nullable=False))

GROUPS = {
    "0001": (workspace, devices, contracts, snapshots, incidents, plans, reports, enforcements),
    "0002": (roots, artifacts, artifact_roots, edges, manifests, runs, run_inputs, revocations),
    "0003": (egress, approvals, outbox, attempts, audit, commands),
}

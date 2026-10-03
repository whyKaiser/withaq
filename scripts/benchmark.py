"""300 reproducible model settings, not 300 physical network experiments.

Six scenario families x ten seeded cost/probe variations x five explicit policies.
Baseline algorithms are project-defined comparisons, not claims about commercial products.
"""
import argparse
import csv
import json
import random
import subprocess
import time
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from withaq.models import Plan, Snapshot
from withaq.planner import solve
from withaq.scenarios import scenarios
from withaq.store import digest
from withaq.validator import validate

POLICIES = ("full-quarantine", "static-segmentation", "risk-based", "function-aware-greedy", "mfsc")


def candidate(snapshot, actions, reason):
    return Plan(snapshot_id=snapshot.id, revision=snapshot.revision, policy_version=snapshot.policy_version,
                capability_version=snapshot.capability_version, status="FEASIBLE", actions=tuple(sorted(actions)),
                cost=sum(a.cost for a in snapshot.actions if a.id in actions), reason=reason)


def policy(snapshot, name):
    if name == "mfsc":
        return solve(snapshot)
    if name == "full-quarantine":
        return candidate(snapshot, ("c",), "Full source isolation baseline")
    if name == "static-segmentation":
        return candidate(snapshot, ("a", "d"), "Static direct/relay-to-protected deny profile")
    if name == "risk-based":
        selected = max((a for a in snapshot.actions if a.enforceable), key=lambda a: (len(a.blocks), -a.cost, a.id), default=None)
        return candidate(snapshot, (selected.id,) if selected else (), "Maximal deny coverage heuristic; function contracts ignored during selection")
    selected = []
    for action in sorted(snapshot.actions, key=lambda a: (a.cost, a.id)):
        if not action.enforceable:
            continue
        current = candidate(snapshot, (*selected, action.id), "Greedy cheapest function-safe next action; no optimality claim")
        verdict = validate(snapshot, current)
        if all(value is True for value in verdict.contracts.values()) and "UNKNOWN_EVIDENCE" not in verdict.reasons:
            selected.append(action.id)
            if verdict.accepted:
                return current
    result = candidate(snapshot, selected, "Greedy heuristic could not establish containment; not proof of infeasibility")
    return result.model_copy(update={"status": "UNKNOWN"})


def execute():
    root = Path(__file__).resolve().parent.parent
    rows, snapshots = [], []
    for scenario_id, base in scenarios().items():
        for seed in range(10):
            randomizer = random.Random(seed)
            spec = base.model_dump(mode="json")
            for action in spec["actions"]:
                action["cost"] = randomizer.randint(1, 5)
            # Preserve missing/failed evidence while varying measurements inside passing limits.
            for hypothesis in spec["hypotheses"]:
                for contract in hypothesis["contracts"]:
                    if contract["observed_age_s"] is not None and contract["observed_age_s"] <= contract["max_age_s"]:
                        contract["observed_age_s"] = randomizer.uniform(0.05, 0.5)
                    if contract["observed_latencies_s"] and max(contract["observed_latencies_s"]) <= contract["max_latency_s"]:
                        contract["observed_latencies_s"] = [randomizer.uniform(0.05, 0.5) for _ in range(5)]
            snapshot = Snapshot.model_validate(spec)
            snapshot_hash = digest(snapshot.model_dump(mode="json"))
            snapshots.append({"scenario": scenario_id, "seed": seed, "hash": snapshot_hash, "spec": spec})
            for name in POLICIES:
                start = time.perf_counter()
                plan = policy(snapshot, name)
                elapsed = time.perf_counter() - start
                verdict = validate(snapshot, plan)
                rows.append({"trial_id": f"{scenario_id}:{seed}:{name}", "scenario": scenario_id, "seed": seed,
                    "policy": name, "snapshot_hash": snapshot_hash, "plan_hash": digest(plan.model_dump(mode="json")),
                    "status": plan.status if name == "mfsc" or verdict.accepted or plan.status == "UNKNOWN" else "REJECTED",
                    "candidate_status": plan.status, "actions": list(plan.actions), "proposed_cost": plan.cost,
                    "accepted_cost": plan.cost if verdict.accepted else None, "duration_s": elapsed,
                    "validation": verdict.model_dump(mode="json"), "reason": plan.reason})
    report = {"mode": "model-only", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root)),
              "design": "6 scenario families x 10 seeded cost/probe variations x 5 project-defined policies", "python": sys.version,
              "count": len(rows), "snapshots": snapshots, "trials": rows,
              "summary": {name: {"accepted": sum(r["validation"]["accepted"] for r in rows if r["policy"] == name),
                                  "statuses": dict(Counter(r["status"] for r in rows if r["policy"] == name))} for name in POLICIES}}
    assert len(rows) == 300 and len({r["trial_id"] for r in rows}) == 300
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/benchmark.json")
    args = parser.parse_args()
    report = execute()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("trial_id", "scenario", "seed", "policy", "status", "actions", "accepted", "accepted_cost", "duration_s"))
        writer.writeheader()
        for row in report["trials"]:
            writer.writerow({key: row[key] for key in writer.fieldnames if key not in ("accepted", "actions")} | {
                "accepted": row["validation"]["accepted"], "actions": "+".join(row["actions"])})
    print(json.dumps({"count": report["count"], "mode": report["mode"], "summary": report["summary"]}, indent=2))

"""Independent transitive-closure oracle. Shares schemas, not planner logic."""
from .models import Plan, Snapshot, Verdict


def validate(snapshot: Snapshot, plan: Plan) -> Verdict:
    reasons = []
    versions = (snapshot.id, snapshot.revision, snapshot.policy_version, snapshot.capability_version)
    if versions != (plan.snapshot_id, plan.revision, plan.policy_version, plan.capability_version):
        reasons.append("STALE_SNAPSHOT")
    if plan.status not in ("OPTIMAL", "FEASIBLE"):
        reasons.append("NO_EXECUTABLE_PLAN")
    if not snapshot.evidence_complete:
        reasons.append("UNKNOWN_EVIDENCE")
    catalog = {a.id: a for a in snapshot.actions}
    if len(set(plan.actions)) != len(plan.actions):
        reasons.append("DUPLICATE_ACTION")
    denied = set()
    actual_cost = 0
    for action_id in plan.actions:
        action = catalog.get(action_id)
        if action is None or not action.enforceable:
            reasons.append("UNSUPPORTED_ACTION:" + action_id)
            continue
        actual_cost += action.cost
        denied.update((e.source, e.target) for e in action.blocks)
    if actual_cost != plan.cost:
        reasons.append("COST_MISMATCH")

    def closure(edges):
        result = {(e.source, e.target) for e in edges if (e.source, e.target) not in denied}
        result.update((n, n) for n in snapshot.nodes)
        for pivot in snapshot.nodes:
            for source in snapshot.nodes:
                for target in snapshot.nodes:
                    if (source, pivot) in result and (pivot, target) in result:
                        result.add((source, target))
        return result

    blocked = True
    contracts = {}
    for hypothesis in snapshot.hypotheses:
        attack_paths = closure(hypothesis.attack_edges)
        if any((s, t) in attack_paths for s in snapshot.attack_sources for t in snapshot.protected_targets):
            blocked = False
            reasons.append("ATTACK_REACHABLE:" + hypothesis.id)
        function_paths = closure(hypothesis.function_edges)
        for c in hypothesis.contracts:
            key = hypothesis.id + ":" + c.id
            if c.observed_age_s is None or not c.observed_latencies_s:
                contracts[key] = None
            else:
                contracts[key] = ((c.source, c.target) in function_paths and c.observed_age_s <= c.max_age_s
                                  and all(delay <= c.max_latency_s for delay in c.observed_latencies_s)
                                  and c.lost_events == 0)
            if c.critical and contracts[key] is not True:
                reasons.append("CONTRACT_FAILED_OR_UNKNOWN:" + key)
    return Verdict(accepted=not reasons, reasons=tuple(reasons), attack_blocked=blocked, contracts=contracts)

"""Bounded deny-only planner. This module never calls the independent validator."""
from itertools import combinations
from time import monotonic

from .models import Plan, Snapshot


def reachable(edges, source, target, denied):
    adjacency = {}
    for e in edges:
        if (e.source, e.target) not in denied:
            adjacency.setdefault(e.source, set()).add(e.target)
    pending, seen = [source], set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            pending.extend(adjacency.get(node, ()) - seen if node in adjacency else ())
    return False


def solve(snapshot: Snapshot, budget_s: float = 1.0, clock=monotonic) -> Plan:
    start = clock()
    base = dict(snapshot_id=snapshot.id, revision=snapshot.revision,
                policy_version=snapshot.policy_version, capability_version=snapshot.capability_version)
    if not snapshot.evidence_complete or any(
        c.observed_age_s is None or not c.observed_latencies_s
        for h in snapshot.hypotheses for c in h.contracts if c.critical
    ):
        return Plan(**base, status="UNKNOWN", reason="Required dependency or probe evidence is missing.")
    best = None
    examined = feasible = 0
    for size in range(len(snapshot.actions) + 1):
        for selected in combinations(snapshot.actions, size):
            if clock() - start >= budget_s:
                return Plan(**base, status="FEASIBLE" if best else "UNKNOWN",
                            actions=best[3] if best else (), cost=best[0] if best else 0,
                            examined=examined, feasible_count=feasible,
                            reason="Search deadline reached; optimality is not established.")
            examined += 1
            if any(not a.enforceable for a in selected):
                continue
            denied = {(e.source, e.target) for a in selected for e in a.blocks}
            noncritical_loss = 0
            valid = True
            for hypothesis in snapshot.hypotheses:
                if any(reachable(hypothesis.attack_edges, s, t, denied)
                       for s in snapshot.attack_sources for t in snapshot.protected_targets):
                    valid = False
                for c in hypothesis.contracts:
                    passes = (reachable(hypothesis.function_edges, c.source, c.target, denied)
                              and c.observed_age_s is not None and c.observed_age_s <= c.max_age_s
                              and bool(c.observed_latencies_s) and max(c.observed_latencies_s) <= c.max_latency_s
                              and c.lost_events == 0)
                    if c.critical and not passes:
                        valid = False
                    elif not c.critical and not passes:
                        noncritical_loss += 1
            if valid:
                feasible += 1
                rank = (sum(a.cost for a in selected), noncritical_loss, len(selected), tuple(sorted(a.id for a in selected)))
                if best is None or rank < best:
                    best = rank
    return Plan(**base, status="OPTIMAL" if best else "INFEASIBLE",
                actions=best[3] if best else (), cost=best[0] if best else 0,
                examined=examined, feasible_count=feasible,
                reason="Complete finite search; optimum only within this model." if best else "Complete search found no plan satisfying every hard constraint.")

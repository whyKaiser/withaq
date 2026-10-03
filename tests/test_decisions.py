from itertools import combinations

import pytest
from pydantic import ValidationError

from withaq.models import Plan, Snapshot
from withaq.planner import solve
from withaq.scenarios import scenarios
from withaq.validator import validate


def candidate(snapshot, actions):
    return Plan(snapshot_id=snapshot.id, revision=snapshot.revision, policy_version=snapshot.policy_version,
                capability_version=snapshot.capability_version, status="FEASIBLE", actions=actions,
                cost=sum(a.cost for a in snapshot.actions if a.id in actions), reason="Oracle test candidate")


def test_all_sixteen_subsets_against_hand_computed_oracle():
    snapshot = scenarios()["separable"]
    expected = {("a", "b"), ("a", "d"), ("a", "b", "d")}
    accepted = set()
    for count in range(5):
        for actions in combinations(("a", "b", "c", "d"), count):
            if validate(snapshot, candidate(snapshot, actions)).accepted:
                accepted.add(actions)
    assert accepted == expected
    plan = solve(snapshot)
    assert (plan.status, plan.actions, plan.cost, plan.examined, plan.feasible_count) == ("OPTIMAL", ("a", "b"), 2, 16, 3)


@pytest.mark.parametrize("scenario,status,actions", [
    ("shared-channel", "INFEASIBLE", ()), ("unknown-evidence", "UNKNOWN", ()),
    ("bounded-dependency", "OPTIMAL", ("a", "d")), ("late-alert", "INFEASIBLE", ()),
    ("unavailable-action", "OPTIMAL", ("a", "d")),
])
def test_scenario_outcomes(scenario, status, actions):
    snapshot = scenarios()[scenario]
    plan = solve(snapshot)
    assert (plan.status, plan.actions) == (status, actions)
    assert validate(snapshot, plan).accepted == (status == "OPTIMAL")


def test_timeout_and_valid_empty_plan_are_distinct():
    snapshot = scenarios()["separable"]
    assert solve(snapshot, budget_s=0).status == "UNKNOWN"
    clear = snapshot.model_copy(update={"hypotheses": (snapshot.hypotheses[0].model_copy(update={"attack_edges": ()}),)})
    assert solve(clear).actions == ()
    assert solve(clear).status == "OPTIMAL"
    ticks = iter([0, 0, 2])
    partial = solve(clear, budget_s=1, clock=lambda: next(ticks))
    assert partial.status == "FEASIBLE" and partial.actions == ()
    assert validate(clear, partial).accepted


@pytest.mark.parametrize("update", [
    {"revision": 999}, {"capability_version": 2}, {"policy_version": 2},
    {"snapshot_id": "different"}, {"actions": ("a", "a", "b")},
    {"actions": ("invented",)}, {"cost": -1}, {"actions": ("c",), "cost": 1},
])
def test_tampered_plan_rejected(update):
    snapshot = scenarios()["separable"]
    assert not validate(snapshot, solve(snapshot).model_copy(update=update)).accepted


def test_missing_measurements_fail_closed():
    snapshot = scenarios()["separable"]
    h = snapshot.hypotheses[0]
    h = h.model_copy(update={"contracts": (h.contracts[0].model_copy(update={"observed_age_s": None}), h.contracts[1])})
    snapshot = snapshot.model_copy(update={"hypotheses": (h,)})
    assert solve(snapshot).status == "UNKNOWN"
    assert not validate(snapshot, candidate(snapshot, ("a", "b"))).accepted


def test_schema_rejects_unknown_endpoints_and_duplicates():
    raw = scenarios()["separable"].model_dump(mode="json")
    raw["nodes"].remove("P")
    with pytest.raises(ValidationError):
        Snapshot.model_validate(raw)
    raw = scenarios()["separable"].model_dump(mode="json")
    raw["actions"].append(raw["actions"][0])
    with pytest.raises(ValidationError):
        Snapshot.model_validate(raw)

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Edge(Model):
    source: str
    target: str


class Contract(Model):
    id: str
    name: str
    source: str
    target: str
    critical: bool = True
    owner: str = "synthetic-lab"
    version: int = 1
    max_age_s: float = Field(default=2, gt=0)
    max_latency_s: float = Field(default=2, gt=0)
    observed_age_s: float | None = Field(default=0.1, ge=0)
    observed_latencies_s: tuple[float, ...] = (0.1,)
    lost_events: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def nonnegative_measurements(self):
        if any(x < 0 or x != x or x == float("inf") for x in self.observed_latencies_s):
            raise ValueError("Latency measurements must be finite and nonnegative")
        return self


class Action(Model):
    id: str
    label: str
    cost: int = Field(ge=0)
    blocks: tuple[Edge, ...]
    enforceable: bool = True


class Hypothesis(Model):
    id: str
    attack_edges: tuple[Edge, ...]
    function_edges: tuple[Edge, ...]
    contracts: tuple[Contract, ...] = Field(min_length=1)


class Snapshot(Model):
    id: str
    title: str
    description: str
    revision: int = Field(default=1, ge=1)
    policy_version: int = 1
    capability_version: int = 1
    nodes: tuple[str, ...]
    attack_sources: tuple[str, ...] = Field(min_length=1)
    protected_targets: tuple[str, ...] = Field(min_length=1)
    actions: tuple[Action, ...] = Field(max_length=12)
    hypotheses: tuple[Hypothesis, ...] = Field(min_length=1)
    evidence_complete: bool = True

    @model_validator(mode="after")
    def references_are_known(self):
        nodes = set(self.nodes)
        if len(nodes) != len(self.nodes):
            raise ValueError("Duplicate node identities")
        if len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError("Duplicate action identities")
        if len({h.id for h in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("Duplicate hypothesis identities")
        if not set(self.attack_sources + self.protected_targets) <= nodes:
            raise ValueError("Unknown attack source or target")
        all_edges = [e for a in self.actions for e in a.blocks]
        for hypothesis in self.hypotheses:
            if len({c.id for c in hypothesis.contracts}) != len(hypothesis.contracts):
                raise ValueError("Duplicate contract identities")
            all_edges.extend(hypothesis.attack_edges + hypothesis.function_edges)
            all_edges.extend(Edge(source=c.source, target=c.target) for c in hypothesis.contracts)
        if any(e.source not in nodes or e.target not in nodes for e in all_edges):
            raise ValueError("Unknown edge or contract endpoint")
        return self


class Plan(Model):
    snapshot_id: str
    revision: int
    policy_version: int
    capability_version: int
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
    actions: tuple[str, ...] = ()
    cost: int = 0
    examined: int = 0
    feasible_count: int = 0
    reason: str


class Verdict(Model):
    accepted: bool
    reasons: tuple[str, ...]
    attack_blocked: bool
    contracts: dict[str, bool | None]

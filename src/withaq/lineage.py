"""Pure lineage checks: unknown roots never become an empty, implicitly trusted set."""
from .store import DomainError


def closure(parents, proposed_edges=()):
    graph = {identity: set(values) for identity, values in parents.items()}
    for parent, child in proposed_edges:
        graph.setdefault(child, set()).add(parent)
    visited, active = set(), set()

    def visit(identity):
        if identity in active:
            raise DomainError("LINEAGE_CYCLE", 422)
        if identity in visited:
            return
        active.add(identity)
        for parent in graph.get(identity, ()):
            visit(parent)
        active.remove(identity)
        visited.add(identity)

    for identity in graph:
        visit(identity)
    return graph


def merge_roots(bindings):
    result = {}
    for binding in bindings:
        if not binding:
            raise DomainError("UNKNOWN_LINEAGE", 403)
        for identity, version in binding.items():
            if identity in result and result[identity] != version:
                raise DomainError("ROOT_VERSION_CONFLICT")
            result[identity] = version
    if not result:
        raise DomainError("UNKNOWN_LINEAGE", 403)
    return result

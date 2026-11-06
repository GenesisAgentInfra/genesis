"""Bounded caller-root suggestions, never business-flow or runtime-entry claims."""

import hashlib
from collections import defaultdict, deque

from genesis_contracts.intelligence import FlowEntryCandidate, FlowEntryDiscovery, FlowEntryPath
from genesis_contracts.models import CapabilityStatus, EvidenceSide, validate_evidence_refs

from .impact import node_id
from .python.extract import incomplete

HEAD = EvidenceSide.head
MAX_CANDIDATES = 100
MAX_PATHS = 256
MAX_PATH_LENGTH = 64
SCOPE = "Unique top-level code functions with no non-module code callers except self; head unassigned changes only"
LIMITATIONS = (
    "Candidates require human confirmation; no business name, acceptance criteria or runtime entry is inferred.",
    "Only supported static calls are searched. Dynamic callers, callbacks, decorators and omitted source can hide other entries.",
    "One shortest observed path per entry/change is retained; branches and candidate edges do not prove execution.",
    "Test callers are excluded. Module calls are boundary evidence; imports, nested definitions and class membership are not invented call edges.",
)


def code_symbols(ir):
    refs = {ref.evidence_id: ref for ref in ir.evidence}
    groups = defaultdict(list)
    for symbol in ir.symbols:
        if symbol.side == HEAD and any(refs[r].kind == "code" for r in symbol.evidence_ids):
            groups[symbol.symbol_id].append(symbol)
    return groups


def candidate_graph(ir, impact, registered):
    groups = code_symbols(ir)
    incoming = defaultdict(list)
    for edge in impact.graph.edges:
        if not edge.source_id.startswith("head::") or not edge.target_id.startswith("head::"):
            continue
        source, target = edge.source_id[6:], edge.target_id[6:]
        if (
            source in groups
            and target in groups
            and edge.relation in {"calls", "awaits", "dispatches"}
        ):
            incoming[target].append(edge)
    for edges in incoming.values():
        edges.sort(key=lambda edge: edge.edge_id)
    roots = set()
    for sid, symbols in groups.items():
        if len(symbols) != 1:
            continue
        symbol = symbols[0]
        if symbol.kind != "function" or "." in symbol.qualified_name or sid in registered:
            continue
        if all(
            edge.source_id == node_id(HEAD, sid)
            or all(s.kind == "module" for s in groups[edge.source_id[6:]])
            for edge in incoming[sid]
        ):
            roots.add(sid)
    return groups, incoming, roots


def discover_entries(ir, impact, unassigned, registered):
    groups, incoming, roots = candidate_graph(ir, impact, registered)
    targets = sorted(item.symbol_id for item in unassigned if item.side == HEAD)
    paths = defaultdict(list)
    unresolved = []
    reasons = set()
    remaining = ir.options.max_graph_visits
    path_count = 0
    for target in targets:
        pending = deque([(target, (), (target,))])
        seen = {target}
        found = False
        while pending:
            if remaining <= 0:
                reasons.add(
                    "Shared candidate traversal budget exhausted; remaining paths were not searched."
                )
                break
            current, chain, symbols = pending.popleft()
            remaining -= 1
            if current in roots:
                if path_count >= MAX_PATHS or (
                    current not in paths and len(paths) >= MAX_CANDIDATES
                ):
                    reasons.add(
                        "Candidate/path output budget exhausted; some suggestions were omitted."
                    )
                    continue
                refs = {
                    *(ref for sid in symbols for s in groups[sid] for ref in s.evidence_ids),
                    *(ref for edge in chain for ref in edge.evidence_ids),
                }
                paths[current].append(
                    FlowEntryPath(
                        changed_symbol_id=target,
                        symbol_ids=symbols,
                        edge_ids=tuple(edge.edge_id for edge in chain),
                        evidence_ids=tuple(sorted(refs)),
                    )
                )
                path_count += 1
                found = True
                continue
            for edge in incoming[current]:
                if remaining <= 0:
                    reasons.add(
                        "Shared candidate traversal budget exhausted; remaining paths were not searched."
                    )
                    break
                remaining -= 1
                source = edge.source_id[6:]
                if source in seen or all(s.kind == "module" for s in groups[source]):
                    continue
                if len(chain) >= MAX_PATH_LENGTH:
                    reasons.add(
                        "Candidate path length budget exceeded; deeper callers were not searched."
                    )
                    continue
                seen.add(source)
                pending.append((source, (edge, *chain), (source, *symbols)))
        if not found:
            unresolved.append(target)
    if unresolved:
        reasons.add(
            "Some unassigned changes have no proposed entry; cycles, nested/class-only roots, registered entries or budgets may prevent a suggestion."
        )
    if targets and (
        impact.coverage.status != "analyzed"
        or any(
            e.source_id.startswith("head::") and e.resolution != "resolved"
            for e in impact.graph.edges
        )
        or any(item.syntax.status != "analyzed" for item in ir.coverage if item.side == HEAD)
    ):
        reasons.add("Input graph or parser coverage is incomplete; suggestions are not exhaustive.")
    candidates = []
    for sid, entries in sorted(paths.items()):
        boundary = next(
            (e for e in incoming[sid] if all(s.kind == "module" for s in groups[e.source_id[6:]])),
            None,
        )
        refs = {
            *(r for p in entries for r in p.evidence_ids),
            *(boundary.evidence_ids if boundary else ()),
        }
        candidates.append(
            FlowEntryCandidate(
                candidate_id="flow_entry_" + hashlib.sha256(sid.encode()).hexdigest()[:16],
                symbol_id=sid,
                reason="Supported caller graph has no non-module code caller except possible self-recursion; a path reaches an unassigned change.",
                paths=tuple(entries),
                evidence_ids=tuple(sorted(refs)),
            )
        )
    result = FlowEntryDiscovery(
        candidates=tuple(candidates),
        unresolved_change_ids=tuple(unresolved),
        coverage=incomplete("; ".join(sorted(reasons)))
        if reasons
        else CapabilityStatus(status="analyzed", analyzed_scope=SCOPE),
        limitations=(*LIMITATIONS, *sorted(reasons)),
    )
    validate_entries(ir, impact, unassigned, registered, result)
    return result


def validate_entries(ir, impact, unassigned, registered, discovery):
    groups, _, roots = candidate_graph(ir, impact, registered)
    targets = {item.symbol_id for item in unassigned if item.side == HEAD}
    edges = {edge.edge_id: edge for edge in impact.graph.edges}
    refs = {ref.evidence_id: ref for ref in ir.evidence}
    if (
        len(discovery.candidates) > MAX_CANDIDATES
        or sum(len(item.paths) for item in discovery.candidates) > MAX_PATHS
        or len(set(discovery.unresolved_change_ids)) != len(discovery.unresolved_change_ids)
    ):
        raise ValueError(
            "Flow entry discovery exceeds output limits or duplicates unresolved changes"
        )
    ids, entries, covered = set(), set(), set()
    for item in discovery.candidates:
        if item.candidate_id in ids or item.symbol_id in entries:
            raise ValueError("Duplicate flow entry candidate")
        ids.add(item.candidate_id)
        entries.add(item.symbol_id)
        if (
            item.candidate_id
            != "flow_entry_" + hashlib.sha256(item.symbol_id.encode()).hexdigest()[:16]
            or item.symbol_id not in roots
            or item.side != HEAD
            or item.status != "candidate"
            or not item.paths
        ):
            raise ValueError("Flow entry must be a unique unregistered top-level head code root")
        validate_evidence_refs(
            snapshot_id=ir.snapshot_id, evidence=ir.evidence, evidence_ids=item.evidence_ids
        )
        if any(refs[ref].side != HEAD for ref in item.evidence_ids):
            raise ValueError("Flow entry evidence must stay on head")
        path_targets = set()
        for path in item.paths:
            if (
                path.changed_symbol_id not in targets
                or path.changed_symbol_id in path_targets
                or not path.symbol_ids
                or path.symbol_ids[0] != item.symbol_id
                or path.symbol_ids[-1] != path.changed_symbol_id
                or len(path.edge_ids) > MAX_PATH_LENGTH
                or len(path.edge_ids) + 1 != len(path.symbol_ids)
                or len(set(path.symbol_ids)) != len(path.symbol_ids)
            ):
                raise ValueError("Flow entry path must connect its entry to one unassigned change")
            path_targets.add(path.changed_symbol_id)
            required = set()
            for sid in path.symbol_ids:
                if sid not in groups:
                    raise ValueError("Flow entry path contains a missing or non-code symbol")
                required.update(r for s in groups[sid] for r in s.evidence_ids)
            for index, edge_id in enumerate(path.edge_ids):
                edge = edges.get(edge_id)
                if (
                    edge is None
                    or edge.source_id != node_id(HEAD, path.symbol_ids[index])
                    or edge.target_id != node_id(HEAD, path.symbol_ids[index + 1])
                    or edge.relation not in {"calls", "awaits", "dispatches"}
                ):
                    raise ValueError("Flow entry path has an invalid graph edge")
                required.update(edge.evidence_ids)
            if not required <= set(path.evidence_ids) <= set(item.evidence_ids):
                raise ValueError("Flow entry path is missing source or edge evidence")
            covered.add(path.changed_symbol_id)
    if discovery.unresolved_change_ids and discovery.coverage.status == "analyzed":
        raise ValueError("Unresolved entry changes require incomplete discovery coverage")
    if set(discovery.unresolved_change_ids) != targets - covered:
        raise ValueError("Flow entry discovery must account for every unassigned head change")

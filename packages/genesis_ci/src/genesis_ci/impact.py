"""Bounded static reachability on side-qualified symbols."""

from collections import defaultdict, deque

from genesis_contracts.intelligence import ImpactAnalysis
from genesis_contracts.models import CapabilityStatus, GraphEdge, GraphNode, ImpactGraph

from .python.extract import incomplete


def node_id(side, symbol_id):
    return side.value + "::" + symbol_id


def build_impact(extraction, patterns):
    ir = extraction.analysis
    nodes = {}
    edges = []
    reverse = defaultdict(set)
    symbols = {(s.side, s.symbol_id): s for s in ir.symbols}
    for key, symbol in symbols.items():
        nodes[node_id(*key)] = GraphNode(
            node_id=node_id(*key),
            symbol_id=symbol.symbol_id,
            kind="symbol",
            evidence_ids=symbol.evidence_ids,
        )
    for call in ir.calls:
        source = node_id(call.side, call.symbol_id)
        for index, target in enumerate(call.target.targets):
            dest = node_id(call.side, target)
            if dest not in nodes:
                nodes[dest] = GraphNode(
                    node_id=dest, kind="external", evidence_ids=call.evidence_ids
                )
            edges.append(
                GraphEdge(
                    edge_id=call.call_id + f":{index}",
                    source_id=source,
                    target_id=dest,
                    relation="awaits" if call.awaited else "calls",
                    resolution=call.target.status,
                    reason=call.target.reason or "Statically resolved call; not a runtime trace",
                    condition="; ".join(call.conditions) or None,
                    evidence_ids=call.evidence_ids,
                )
            )
            if (call.side, target) in symbols:
                reverse[(call.side, target)].add((call.side, call.symbol_id))
    # A tool is reachable through a model-selected dispatch, never guaranteed executed.
    for loop in patterns.loops:
        for index, target in enumerate(loop.loop.reachable_tools.targets):
            source = node_id(loop.side, loop.loop.symbol_id)
            dest = node_id(loop.side, target)
            if dest not in nodes:
                nodes[dest] = GraphNode(
                    node_id=dest, kind="external", evidence_ids=loop.loop.evidence_ids
                )
            edges.append(
                GraphEdge(
                    edge_id=loop.loop.loop_id + f":tool:{index}",
                    source_id=source,
                    target_id=dest,
                    relation="dispatches",
                    resolution="candidate",
                    reason="Schema name matches a static dispatch candidate; model choice and helper roles unknown",
                    condition="Only if the model selects this tool",
                    evidence_ids=loop.loop.evidence_ids,
                )
            )
            if (loop.side, target) in symbols:
                reverse[(loop.side, target)].add((loop.side, loop.loop.symbol_id))
    changed = tuple(sorted(key for key in symbols if key[1] in ir.change_set.changed_symbol_ids))
    queue = deque(changed)
    affected = set()
    truncated = False
    while queue:
        item = queue.popleft()
        if item in affected:
            continue
        if len(affected) >= ir.options.max_graph_visits:
            truncated = True
            break
        affected.add(item)
        queue.extend(sorted(reverse[item]))
    unresolved = tuple(c.call_id for c in ir.calls if c.target.status != "resolved")
    partial = (
        truncated
        or unresolved
        or ir.change_set.unresolved
        or any(e.resolution != "resolved" for e in edges)
    )
    return ImpactAnalysis(
        graph=ImpactGraph(
            nodes=tuple(nodes[key] for key in sorted(nodes)),
            edges=tuple(sorted(edges, key=lambda edge: edge.edge_id)),
        ),
        affected_symbols=tuple(sorted(affected)),
        changed_symbols=changed,
        unresolved_calls=unresolved,
        coverage=incomplete(
            "Graph traversal truncated"
            if truncated
            else "Dynamic/candidate calls or unavailable input prevent exhaustive reachability"
        )
        if partial
        else CapabilityStatus(
            status="analyzed",
            analyzed_scope="Captured, statically resolvable calls on each version",
        ),
    )


def reachable(graph, start, limit):
    adjacency = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source_id].add(edge.target_id)
    pending = [start]
    seen = set()
    while pending:
        item = pending.pop()
        if item in seen:
            continue
        if len(seen) >= limit:
            return seen, True
        seen.add(item)
        pending.extend(sorted(adjacency[item] - seen, reverse=True))
    return seen, False

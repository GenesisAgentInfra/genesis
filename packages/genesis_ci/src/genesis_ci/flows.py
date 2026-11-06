from dataclasses import dataclass

import yaml
from genesis_contracts.intelligence import FlowEntryDiscovery, FlowSideImpact, UnassignedChange
from genesis_contracts.models import (
    CapabilityStatus,
    EvidenceSide,
    FlowImpact,
    FlowsDocument,
    IntentItem,
    Limitation,
    ReferenceRange,
)
from pydantic import ValidationError

from .flow_candidates import discover_entries
from .impact import node_id, reachable
from .python.extract import incomplete


@dataclass(frozen=True)
class FlowAnalysis:
    head: FlowsDocument
    impacts: tuple[FlowSideImpact, ...]
    intents: tuple[IntentItem, ...]
    coverage: CapabilityStatus
    limitations: tuple[Limitation, ...]
    entry_discovery: FlowEntryDiscovery
    unassigned_changes: tuple[UnassignedChange, ...] = ()


def whole_file_ref(source, registry, side, path):
    text = source.read_text(side, path)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    if not lines:
        return ()
    span = ReferenceRange(
        start_line=1, end_line=len(lines), start_column=0, end_column=len(lines[-1])
    )
    return (registry.register(side, path, span).evidence_id,)


def map_flows(snapshot, extraction, impact):
    path = ".genesis/flows.yaml"
    head = FlowsDocument()
    results = []
    intents = []
    limitations = []
    known = {(s.side, s.symbol_id) for s in extraction.analysis.symbols}
    failed = {
        (c.side, c.path) for c in extraction.analysis.coverage if c.syntax.status != "analyzed"
    }
    changed = set(impact.changed_symbols)
    registered = set()
    for side in EvidenceSide:
        if path not in snapshot.source.list_files(side):
            if side == EvidenceSide.head:
                limitations.append(
                    Limitation(
                        code="flows_missing",
                        message="No optional head flow map supplied; review uses code paths without confirmed business grouping.",
                        affects_completeness=False,
                    )
                )
            continue
        refs = whole_file_ref(snapshot.source, extraction.registry, side, path)
        try:
            raw = snapshot.source.read_bytes(side, path)
            if len(raw) > 262144:
                raise ValueError("Flow map byte budget exceeded")
            doc = FlowsDocument.model_validate(yaml.safe_load(raw))
        except (yaml.YAMLError, ValueError, ValidationError, RecursionError):
            limitations.append(
                Limitation(
                    code="flows_invalid",
                    message=f"{side.value} flow map cannot be parsed or validated.",
                    evidence_ids=refs,
                    affects_completeness=True,
                )
            )
            continue
        if side == EvidenceSide.head:
            head = doc
            registered.update(entry for flow in doc.flows for entry in flow.entries)
        for flow in doc.flows:
            hits = set()
            unknown = False
            invalid = False
            truncated = False
            for entry in flow.entries:
                entry_path = entry.split("#")[0]
                if (side, entry) not in known:
                    omitted = any(
                        item.side == side
                        and item.affects_completeness
                        and (entry_path == item.path or entry_path.startswith(item.path + "/"))
                        for item in snapshot.capture.omissions
                    )
                    if (side, entry_path) in failed or omitted:
                        unknown = True
                    else:
                        invalid = True
                    continue
                nodes, limited = reachable(
                    impact.graph, node_id(side, entry), extraction.analysis.options.max_graph_visits
                )
                truncated |= limited
                hits.update(sid for s, sid in changed if s == side and node_id(s, sid) in nodes)
                unknown |= any(
                    edge.source_id in nodes and edge.resolution != "resolved"
                    for edge in impact.graph.edges
                )
                unknown |= any(
                    node_id(call.side, call.symbol_id) in nodes and call.target.status != "resolved"
                    for call in extraction.analysis.calls
                )
            status = "unknown" if invalid or unknown or truncated else "resolved"
            results.append(
                FlowSideImpact(
                    side=side,
                    impact=FlowImpact(
                        flow_id=flow.id,
                        status=status,
                        entry_status="invalid"
                        if invalid
                        else "unknown"
                        if unknown and not all((side, e) in known for e in flow.entries)
                        else "valid",
                        changed_symbol_ids=tuple(sorted(hits)),
                        reason="Entry missing"
                        if invalid
                        else "Incomplete or candidate reachability"
                        if unknown or truncated
                        else "Static entry reachability computed",
                        evidence_ids=refs,
                    ),
                )
            )
            if side == EvidenceSide.head and flow.status == "confirmed":
                intents.extend(
                    IntentItem(
                        intent_id=f"flow:{flow.id}:{index}",
                        source_type="flow_acceptance",
                        nature="user_intent",
                        text=text,
                        evidence_ids=refs,
                        flow_id=flow.id,
                    )
                    for index, text in enumerate(flow.acceptance)
                )
    assigned = {(item.side, sid) for item in results for sid in item.impact.changed_symbol_ids}
    ref_catalog = {ref.evidence_id: ref for ref in extraction.analysis.evidence}
    unassigned = {}
    for symbol in extraction.analysis.symbols:
        key = (symbol.side, symbol.symbol_id)
        if (
            key in changed
            and key not in assigned
            and symbol.kind == "function"
            and any(ref_catalog[ref].kind == "code" for ref in symbol.evidence_ids)
        ):
            unassigned.setdefault(key, set()).update(symbol.evidence_ids)
    unassigned_changes = tuple(
        UnassignedChange(
            side=side,
            symbol_id=sid,
            reason="No supported static path from a named flow entry was found; missing maps, invalid entries and dynamic calls can hide paths.",
            evidence_ids=tuple(sorted(refs)),
        )
        for (side, sid), refs in sorted(unassigned.items())
    )
    discovery = discover_entries(extraction.analysis, impact, unassigned_changes, registered)
    if discovery.coverage.status != "analyzed":
        limitations.append(
            Limitation(
                code="flow_entry_discovery_partial",
                message=discovery.coverage.reason,
                affects_completeness=True,
            )
        )
    # Missing optional business labels do not make the underlying code graph incomplete.
    # Supplied invalid maps, unresolved entries and traversal gaps still do.
    unnamed_graph_partial = not head.flows and impact.coverage.status != "analyzed"
    partial = (
        any(item.affects_completeness for item in limitations)
        or any(item.impact.status != "resolved" for item in results)
        or unnamed_graph_partial
    )
    return FlowAnalysis(
        head,
        tuple(results),
        tuple(intents),
        incomplete("Invalid flow map or incomplete code/entry reachability")
        if partial
        else CapabilityStatus(
            status="analyzed",
            analyzed_scope="User-confirmed flow entries; static paths only"
            if head.flows
            else "Captured static code paths and candidate entries; no confirmed business grouping",
        ),
        tuple(limitations),
        discovery,
        unassigned_changes,
    )

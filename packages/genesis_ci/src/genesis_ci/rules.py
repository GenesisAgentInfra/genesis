"""Evidence-backed structural comparisons. No inferred runtime counts or prices."""

import hashlib
from collections import defaultdict

from genesis_contracts.models import Finding
from genesis_contracts.validation import _refs


def identity(rule, key):
    return rule + "_" + hashlib.sha256(str(key).encode()).hexdigest()[:16]


def static_characters(expressions):
    """Count strings only if the entire value tree is statically known."""
    total = 0
    for expr in expressions:
        if expr.kind == "literal":
            total += len(expr.value) if isinstance(expr.value, str) else 0
        elif expr.kind in {"list", "tuple"}:
            count = static_characters(expr.children)
            if count is None:
                return None
            total += count
        elif expr.kind == "dict":
            if any(entry.key is None for entry in expr.entries):
                return None
            count = static_characters(tuple(entry.value for entry in expr.entries))
            if count is None:
                return None
            total += count
        else:
            return None
    return total


def structural_findings(extraction, patterns, flows):
    results = []
    groups = defaultdict(lambda: defaultdict(list))
    for call in patterns.model_calls:
        groups[(call.symbol_id, call.provider, call.api)][call.side.value].append(call)
    changed = set(extraction.analysis.change_set.changed_symbol_ids)
    parsed_calls = {c.call_id: c for c in extraction.analysis.calls}

    def add(rule, key, statement, calls, *, severity="info", gap=None):
        refs = tuple(sorted({r for call in calls for r in _refs(call)}))
        if not refs:
            return
        results.append(
            Finding(
                finding_id=identity(rule, key),
                category="cost_risk",
                statement=statement,
                severity=severity,
                basis=("code_fact",),
                evidence_ids=refs,
                condition="Static recognized call sites only. Branches, repeated invocations, retries, dynamic mutation and runtime outcomes can differ.",
                gap=gap,
            )
        )

    for key, sides in sorted(groups.items()):
        symbol, provider, api = key
        before, after = sides["base"], sides["head"]
        base_available = any(
            c.side == "base" and c.path == symbol.split("#")[0] and c.syntax.status == "analyzed"
            for c in extraction.analysis.coverage
        )
        added_file = any(
            f.head_path == symbol.split("#")[0] and f.base_path is None
            for f in extraction.analysis.change_set.files
        )
        if len(after) > len(before) and (base_available or added_file):
            add(
                "sdk_sites_added",
                key,
                f"{symbol}: recognized {provider} {api} call sites increase from {len(before)} to {len(after)}.",
                (*before, *after),
                gap="This is not an invocation count, token count or monetary estimate.",
            )
        if len(before) == len(after) == 1:
            old, new = before[0], after[0]
            if old.model.kind == new.model.kind == "literal" and old.model.value != new.model.value:
                add(
                    "model_literal_changed",
                    key,
                    f"{symbol}: model literal changes from {old.model.value!r} to {new.model.value!r}.",
                    (old, new),
                )
            old_chars, new_chars = static_characters(old.prompt), static_characters(new.prompt)
            if old_chars is not None and new_chars is not None and old_chars != new_chars:
                add(
                    "prompt_literal_changed",
                    key,
                    f"{symbol}: static string characters in prompt argument values change from {old_chars} to {new_chars}.",
                    (old, new),
                    gap="Character counts exclude dictionary keys and are not token counts; SDK serialization is not modeled.",
                )

        def direct(items):
            return [
                c
                for c in items
                if parsed_calls[c.call_id].awaited and not c.conditions and not c.loop_ids
            ]

        old_direct, new_direct = direct(before), direct(after)
        if len(new_direct) > len(old_direct) and (base_available or added_file):
            add(
                "direct_await_sites_added",
                key,
                f"{symbol}: directly awaited model-call sites outside branches/loops increase from {len(old_direct)} to {len(new_direct)}.",
                (*old_direct, *new_direct),
                gap="No latency estimate. Calls supplied to gather/create_task are not counted as direct awaits; reachability and early returns remain unknown.",
            )

    for item in patterns.loops:
        loop = item.loop
        if item.side.value != "head" or loop.symbol_id not in changed:
            continue
        bound = loop.iteration_bound
        if bound.status == "unbounded":
            add(
                "loop_no_count_bound",
                loop.loop_id,
                f"{loop.symbol_id}: model calls occur in a loop without a static iteration-count bound.",
                (loop,),
                severity="medium",
                gap=bound.reason,
            )
        elif bound.status == "bounded":
            add(
                "loop_literal_bound",
                loop.loop_id,
                f"{loop.symbol_id}: a model-containing loop has a static iteration bound of {bound.max_iterations}.",
                (loop,),
                gap="This is a per-loop bound; nested loops, per-iteration calls and early exits require separate accounting.",
            )
        if (
            item.schema_complete
            and item.dispatch_complete
            and (item.unmatched_schema_tools or item.unmatched_dispatch_tools)
        ):
            add(
                "tool_schema_dispatch_mismatch",
                loop.loop_id,
                f"{loop.symbol_id}: literal schema-only tools={list(item.unmatched_schema_tools)}; dispatch-only tools={list(item.unmatched_dispatch_tools)}.",
                (loop,),
                severity="low",
                gap="Only the supported literal dictionary dispatch is compared; runtime registrations are unknown.",
            )

    # Compare extracted facts even when a module-level config changed outside the loop body.
    loop_groups = defaultdict(lambda: defaultdict(list))
    for item in patterns.loops:
        loop_groups[item.loop.symbol_id][item.side.value].append(item)
    for symbol, sides in sorted(loop_groups.items()):
        before, after = sides["base"], sides["head"]
        if len(before) != 1 or len(after) != 1:
            continue  # No stable correspondence between multiple/added/deleted loops.
        old, new = before[0], after[0]
        if (
            old.schema_complete
            and new.schema_complete
            and old.schema_tool_names != new.schema_tool_names
        ):
            add(
                "tool_schema_changed",
                symbol,
                f"{symbol}: literal tool schema names change from {list(old.schema_tool_names)} to {list(new.schema_tool_names)}.",
                (old.loop, new.loop),
                gap="Schema declarations do not prove the model will select a tool.",
            )
        old_sites = {
            (s.tool_name, target) for s in old.dispatch_sites for target in s.target.targets
        }
        new_sites = {
            (s.tool_name, target) for s in new.dispatch_sites for target in s.target.targets
        }
        if old_sites != new_sites and old_sites and new_sites:
            add(
                "tool_dispatch_changed",
                symbol,
                f"{symbol}: recognized tool dispatch candidates change; removed={sorted(old_sites - new_sites)}, added={sorted(new_sites - old_sites)}.",
                (old.loop, new.loop),
                gap="Observed static candidates only, including possible branch helpers; incomplete dispatch is not treated as an empty runtime tool set.",
            )

        def control_signatures(item):
            return sorted(
                (control.kind, control.expression, control.conditions, control.caveats)
                for control in item.controls
            )

        if control_signatures(old) != control_signatures(new):
            add(
                "loop_controls_changed",
                symbol,
                f"{symbol}: lexical loop controls changed from {control_signatures(old)} to {control_signatures(new)}.",
                (old.loop, new.loop),
                gap="Includes continue as iteration control, not a loop exit; explicit raises may be caught and finally/with can override transfers. No runtime termination claim.",
            )
        old_bound, new_bound = old.loop.iteration_bound, new.loop.iteration_bound
        if (
            old_bound.status != "unknown"
            and new_bound.status != "unknown"
            and (old_bound.status, old_bound.max_iterations)
            != (new_bound.status, new_bound.max_iterations)
        ):
            add(
                "loop_bound_changed",
                symbol,
                f"{symbol}: static loop bound changes from {old_bound.status}:{old_bound.max_iterations} to {new_bound.status}:{new_bound.max_iterations}.",
                (old.loop, new.loop),
                severity="medium" if new_bound.status == "unbounded" else "info",
                gap="Per-loop syntactic bounds are not observed invocation counts, latency or cost.",
            )

    symbol_refs = defaultdict(list)
    for symbol in extraction.analysis.symbols:
        if symbol.side.value == "head":
            symbol_refs[symbol.symbol_id].extend(symbol.evidence_ids)
    for item in flows.impacts:
        if item.side.value != "head" or not item.impact.changed_symbol_ids:
            continue
        flow = item.impact
        refs = tuple(
            sorted(
                {
                    *flow.evidence_ids,
                    *(ref for sid in flow.changed_symbol_ids for ref in symbol_refs[sid]),
                }
            )
        )
        if not any(symbol_refs[sid] for sid in flow.changed_symbol_ids):
            continue
        results.append(
            Finding(
                finding_id=identity("flow_changed_path", flow.flow_id),
                category="flow_impact",
                statement=f"Flow {flow.flow_id} has static paths to changed symbols: {', '.join(flow.changed_symbol_ids)}.",
                severity="info",
                basis=("code_fact",),
                evidence_ids=refs,
                flow_ids=(flow.flow_id,),
                condition="Reachability includes candidate edges; it does not demonstrate business behavior or execution.",
            )
        )
    # Missing maps already have a limitation. With a map, surface uncovered changed functions.
    if flows.head.flows:
        unassigned = [item for item in flows.unassigned_changes if item.side.value == "head"]
        if unassigned:
            shown = unassigned[:50]
            results.append(
                Finding(
                    finding_id="flow_unassigned_head",
                    category="flow_impact",
                    severity="info",
                    statement=f"{len(unassigned)} changed head functions have no discovered named-flow path: "
                    + ", ".join(item.symbol_id for item in shown),
                    basis=("code_fact",),
                    evidence_ids=tuple(
                        sorted({ref for item in shown for ref in item.evidence_ids})
                    ),
                    condition="This does not prove the functions are unused; dynamic paths and invalid entries may hide their flow.",
                    gap="Report displays at most 50 functions; the full list is in flows.json."
                    if len(unassigned) > 50
                    else None,
                )
            )
    discovery = flows.entry_discovery
    for item in discovery.candidates[:50]:
        targets = sorted(path.changed_symbol_id for path in item.paths)
        results.append(
            Finding(
                finding_id=item.candidate_id,
                category="flow_impact",
                severity="info",
                statement=f"Candidate flow entry {item.symbol_id} has observed static paths to unassigned head changes: "
                + ", ".join(targets[:10]),
                basis=("code_fact",),
                evidence_ids=item.evidence_ids,
                condition="Caller-root heuristic only; paths can include branches or candidate targets and do not prove runtime entry or business ownership.",
                recommendation="Review this entry and its paths before adding a named flow; acceptance criteria must come from the user.",
                gap="Report shows at most 50 candidates and 10 target names per candidate; bounded discovery, full paths and limitations are in flows.json. "
                + (discovery.coverage.reason or "Dynamic paths can hide additional entries."),
            )
        )
    return tuple(results)

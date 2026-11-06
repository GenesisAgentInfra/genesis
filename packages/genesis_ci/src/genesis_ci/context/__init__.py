"""Build bounded wire requests from typed local analysis and frozen evidence."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genesis_contracts.models import AnalysisRequest, CapabilityStatus, LocalAnalysis
from genesis_contracts.validation import (
    validate_excerpts,
    validate_local_analysis,
    validate_request_against_local,
)

from genesis_ci.snapshot import SnapshotReader

from .filters import contains_secret, evidence_ids, excluded_path, unsafe_value

if TYPE_CHECKING:
    from genesis_contracts.models import ReviewDirectives


class ContextBudgetExceeded(ValueError):
    """Even the minimum valid request cannot fit the caller's input budget."""


@dataclass(frozen=True)
class ContextOptions:
    input_token_budget: int = 40_000
    max_excerpt_chars: int = 12_000
    max_excerpts: int = 80
    exclude_paths: tuple[str, ...] = ()
    preferred_evidence_ids: tuple[str, ...] = ()
    behavior_review_version: str | None = None
    behavior_view_versions: tuple[str, ...] = ("1", "2")

    def __post_init__(self) -> None:
        if min(self.input_token_budget, self.max_excerpt_chars, self.max_excerpts) < 1:
            raise ValueError("context budgets must be positive")

    @property
    def payload_token_budget(self) -> int:
        """Reserve half the token estimate for service prompts/schema/prior output.

        The shared pinned encoding is an estimate, not provider-token attestation.
        The service independently checks each complete context, including repairs.
        """
        return self.input_token_budget // 2


MAX_WIRE_BYTES = 524_288


def _payload_text(request: AnalysisRequest) -> str:
    from genesis_contracts.models import project_analysis_request

    return json.dumps(project_analysis_request(request), ensure_ascii=False, separators=(",", ":"))


def _payload_byte_size(request: AnalysisRequest) -> int:
    return len(_payload_text(request).encode("utf-8"))


def _payload_token_estimate(request: AnalysisRequest) -> int:
    from genesis_tokenizer import count_fragments

    return count_fragments((_payload_text(request),))


def _fits_budget(request: AnalysisRequest, options: ContextOptions, *, reserve_tokens=0) -> bool:
    return (
        len(request.model_dump_json().encode("utf-8")) <= MAX_WIRE_BYTES
        and _payload_token_estimate(request) <= options.payload_token_budget - reserve_tokens
    )


def _import_context_bundles(local, changed):
    """Supply frozen modules importing changed symbols, without inferring calls.

    Callback registrations and configuration can reference a function without
    calling it. Existing import/module facts identify candidate source context;
    they do not establish runtime reachability. Ambiguous module suffixes are
    skipped, and normal whole-excerpt privacy and packing limits still apply.
    """
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    modules = {}
    for fact in local.facts.functions:
        if fact.kind == "module":
            path = catalog[fact.evidence_ids[0]].path
            modules[(fact.side, path)] = fact.evidence_ids
    targets = defaultdict(set)
    for symbol in changed:
        path, _, name = symbol.partition("#")
        if name and name != "<module>":
            targets[path].add(name.split(".")[0])

    def module_path(name, side, owner):
        if not name:
            return None
        if name.startswith("."):
            dots = len(name) - len(name.lstrip("."))
            parts = owner.split("/")[:-1]
            if dots > len(parts):
                return None
            prefix = parts[: len(parts) - dots + 1]
            suffix = "/".join([*prefix, *name[dots:].split(".")]).rstrip("/")
            candidates = {
                path
                for candidate_side, path in modules
                if candidate_side == side
                and path
                in {
                    suffix + extension
                    for extension in (".py", ".pyi", "/__init__.py", "/__init__.pyi")
                }
            }
        else:
            suffix = name.replace(".", "/")
            endings = tuple(
                suffix + extension for extension in (".py", ".pyi", "/__init__.py", "/__init__.pyi")
            )
            candidates = {
                path
                for candidate_side, path in modules
                if candidate_side == side
                and any(path == ending or path.endswith("/" + ending) for ending in endings)
            }
        return next(iter(candidates)) if len(candidates) == 1 else None

    supporting = set()
    for fact in local.facts.imports:
        owner = catalog[fact.evidence_ids[0]].path
        target = module_path(fact.module, fact.side, owner)
        relevant = target in targets and (
            fact.imported_name is None or fact.imported_name in targets[target]
        )
        # ``from package import module`` names the changed module itself.
        if not relevant and fact.imported_name not in {None, "*"}:
            name = fact.module + ("" if fact.module.endswith(".") else ".") + fact.imported_name
            relevant = module_path(name, fact.side, owner) in targets
        if relevant and owner not in targets:
            supporting.add(owner)
    return [
        tuple(
            ident
            for (side, candidate), identifiers in sorted(modules.items())
            if candidate == path
            for ident in identifiers
        )
        for path in sorted(supporting)
    ]


def _source_bundles(local, reader=None, missing=None):
    """Pair changed bodies first, then their statically resolved direct callers.

    Importing modules provide registration/configuration context before other
    methods of changed classes. Added/deleted functions have only their existing
    side. No runtime connectivity is inferred here.
    """
    missing = [] if missing is None else missing
    changed = set(local.change_set.changed_symbol_ids)
    changed_classes = {
        fact.symbol_id
        for fact in local.facts.functions
        if fact.kind == "class" and fact.symbol_id in changed
    }
    bodies = defaultdict(list)
    changed_functions, class_members = set(), set()
    for fact in local.facts.functions:
        if fact.kind != "function":
            continue
        bodies[fact.symbol_id].extend(fact.evidence_ids)
        if fact.symbol_id in changed:
            changed_functions.add(fact.symbol_id)
        elif any(fact.symbol_id.startswith(owner + ".") for owner in changed_classes):
            class_members.add(fact.symbol_id)
    nodes = {node.node_id: node for node in local.impact_graph.nodes}
    callers = {
        nodes[edge.source_id].symbol_id
        for edge in local.impact_graph.edges
        if edge.relation in {"calls", "awaits"}
        and edge.resolution == "resolved"
        and nodes[edge.target_id].symbol_id in changed_functions | changed_classes
        and nodes[edge.source_id].symbol_id in bodies
    } - changed_functions
    primary = [
        tuple(dict.fromkeys(bodies[symbol]))
        for symbols in (changed_functions, callers)
        for symbol in sorted(symbols)
    ]
    from .dependencies import lexical_bundles
    from .related import related_bundles

    supporting, related = (
        related_bundles(local, reader, changed_functions | changed_classes, missing)
        if reader is not None
        else ([], set())
    )

    dependencies = (
        lexical_bundles(local, reader, changed_functions | callers | related, missing)
        if reader is not None
        else []
    )
    return [
        *primary,
        *supporting,
        *dependencies,
        *_import_context_bundles(local, changed_functions | changed_classes),
        *(tuple(dict.fromkeys(bodies[symbol])) for symbol in sorted(class_members - callers)),
    ]


def _priorities(local, preferred, missing):
    priorities = {ref: 0 for ref in preferred}

    def include(value, priority):
        for ref in evidence_ids(value):
            priorities[ref] = min(priority, priorities.get(ref, priority))

    include(local.intents, 1)
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    changed_functions = {
        fact.symbol_id
        for fact in local.facts.functions
        if fact.kind == "function"
        and fact.symbol_id in local.change_set.changed_symbol_ids
        and all(catalog[ref].kind == "code" for ref in fact.evidence_ids)
    }
    for fact in local.facts.functions:
        if fact.symbol_id in changed_functions:
            include(fact, 2)
    # When a complete body cannot fit, its existing local observations remain
    # useful. Do not let module-level imports precede changed-function evidence.
    for name in type(local.facts).model_fields:
        if name == "coverage":
            continue
        for fact in getattr(local.facts, name):
            if (
                getattr(fact, "symbol_id", None) in changed_functions
                or getattr(fact, "caller_symbol_id", None) in changed_functions
            ):
                include(fact, 3)
    # Source labels are selected provenance, never classified requirement evidence.
    include(tuple(item for item in local.limitations if item.code == "intent_source_location"), 1)
    include(local.rule_findings, 3)
    include(local.flow_impacts, 3)
    include(local.estimates, 4)
    symbols = set(local.change_set.changed_symbol_ids)
    for fact in local.facts.functions:
        if set(fact.evidence_ids) & priorities.keys():
            symbols.add(fact.symbol_id)
    nodes = {node.node_id: node for node in local.impact_graph.nodes}
    adjacency = defaultdict(set)
    for edge in local.impact_graph.edges:
        # Do not connect unrelated callers through a shared external SDK target.
        if nodes[edge.source_id].symbol_id and nodes[edge.target_id].symbol_id:
            adjacency[edge.source_id].add(edge.target_id)
            adjacency[edge.target_id].add(edge.source_id)
    pending = deque(sorted(node.node_id for node in nodes.values() if node.symbol_id in symbols))
    reached = set()
    while pending:
        node_id = pending.popleft()
        if node_id in reached:
            continue
        if len(reached) >= 256:
            missing.append("Context graph expansion reached its 256-node limit.")
            break
        reached.add(node_id)
        include(nodes[node_id], 4)
        symbols.add(nodes[node_id].symbol_id)
        pending.extend(sorted(adjacency[node_id] - reached))
    for edge in local.impact_graph.edges:
        if edge.source_id in reached or edge.target_id in reached:
            include(edge, 5)
            include(nodes[edge.source_id], 5)
            include(nodes[edge.target_id], 5)
    for name in type(local.facts).model_fields:
        if name == "coverage":
            continue
        for fact in getattr(local.facts, name):
            if (
                getattr(fact, "symbol_id", None) in symbols
                or getattr(fact, "caller_symbol_id", None) in symbols
                or evidence_ids(fact) & priorities.keys()
            ):
                include(fact, 5)
    for loop in local.agent_loops:
        if loop.symbol_id in symbols:
            include(loop, 5)
    for test in local.test_definitions:
        if set(test.association.targets) & symbols or evidence_ids(test) & priorities.keys():
            # Associated tests are first-class semantic evidence for every changed
            # entry, not optional tail material after changed source excerpts.
            include(test, 2 if all(catalog[ref].side == "head" for ref in test.evidence_ids) else 6)
    changed_paths = {
        path for file in local.change_set.files for path in (file.base_path, file.head_path) if path
    }
    for ref in local.evidence:
        if ref.path in changed_paths:
            priorities.setdefault(ref.evidence_id, 5)
        if ref.kind in {"config", "flow"}:
            priorities.setdefault(ref.evidence_id, 7)
    return priorities


def _project(
    local,
    selected,
    excerpts,
    *,
    request_id,
    options,
    cli_version,
    missing,
    input_gaps,
    review_directives=None,
):
    allowed = {ref.evidence_id for ref in selected}

    def safe(item):
        if unsafe_value(item, options.exclude_paths):
            if "Sensitive or excluded derived material omitted." not in missing:
                missing.append("Sensitive or excluded derived material omitted.")
            return False
        return True

    def keep(item):
        return evidence_ids(item) <= allowed and safe(item)

    facts = {
        name: tuple(item for item in getattr(local.facts, name) if keep(item))
        for name in type(local.facts).model_fields
        if name != "coverage"
    }
    flow_evidence = any(ref.kind == "flow" for ref in selected)
    flows = tuple(flow for flow in local.flows if safe(flow)) if flow_evidence else ()
    flow_ids = {flow.id for flow in flows}
    calls = {call.call_id for call in facts["calls"]}
    estimates = tuple(e for e in local.estimates if keep(e) and set(e.flow_ids) <= flow_ids)
    estimate_ids = {estimate.estimate_id for estimate in estimates}
    edges = tuple(edge for edge in local.impact_graph.edges if keep(edge))
    used_nodes = {node_id for edge in edges for node_id in (edge.source_id, edge.target_id)}
    nodes = tuple(
        node
        for node in local.impact_graph.nodes
        if keep(node) and (node.evidence_ids or node.node_id in used_nodes)
    )
    node_ids = {node.node_id for node in nodes}
    paths = {ref.path for ref in selected}
    symbols = {item.symbol_id for item in facts["functions"]}
    coverage = (
        local.facts.coverage
        if not missing and safe(local.facts.coverage)
        else CapabilityStatus(
            status="insufficient_context", reason="Selected context omits local analysis material."
        )
    )
    return AnalysisRequest(
        # Reserve the view envelope while packing original source. Units are
        # admitted afterwards, so new structure never crowds out accepted source.
        behavior_view=local.behavior_view.model_copy(
            update={
                "units": (),
                "omitted_units": local.behavior_view.omitted_units + len(local.behavior_view.units),
            }
        )
        if local.behavior_view is not None
        and local.behavior_view.version in options.behavior_view_versions
        else None,
        request_id=request_id,
        snapshot_id=local.snapshot.snapshot_id,
        cli_version=cli_version,
        change_set=local.change_set.model_copy(
            update={
                "files": tuple(
                    item
                    for item in local.change_set.files
                    if keep(item) and (item.base_path in paths or item.head_path in paths)
                ),
                "changed_symbol_ids": tuple(
                    symbol
                    for symbol in local.change_set.changed_symbol_ids
                    if symbol in symbols and safe(symbol)
                ),
                "unresolved": tuple(
                    reason for reason in local.change_set.unresolved if safe(reason)
                ),
            }
        ),
        facts=local.facts.model_copy(update={**facts, "coverage": coverage}),
        agent_loops=tuple(
            item for item in local.agent_loops if keep(item) and set(item.call_ids) <= calls
        ),
        impact_graph={
            "nodes": nodes,
            "edges": tuple(
                edge for edge in edges if edge.source_id in node_ids and edge.target_id in node_ids
            ),
        },
        flows=flows,
        flow_impacts=tuple(
            item for item in local.flow_impacts if keep(item) and item.flow_id in flow_ids
        ),
        test_definitions=tuple(item for item in local.test_definitions if keep(item)),
        intents=tuple(
            item
            for item in local.intents
            if keep(item) and (item.flow_id is None or item.flow_id in flow_ids)
        ),
        evidence=selected,
        excerpts=excerpts,
        rule_findings=tuple(
            item
            for item in local.rule_findings
            if keep(item)
            and set(item.flow_ids) <= flow_ids
            and set(item.estimate_ids) <= estimate_ids
        ),
        estimates=estimates,
        missing_context=tuple(dict.fromkeys((*input_gaps, *missing))),
        truncated=bool(missing),
        input_token_budget=options.input_token_budget,
        behavior_review_version=options.behavior_review_version,
        **({"review_directives": review_directives} if review_directives is not None else {}),
    )


def build_context(
    local: LocalAnalysis,
    reader: SnapshotReader,
    *,
    request_id: str,
    options: ContextOptions | None = None,
    cli_version: str = "0.1.0",
    review_directives: ReviewDirectives | None = None,
    selection_log: list | None = None,
) -> AnalysisRequest:
    options = options or ContextOptions()
    validate_local_analysis(local)
    catalog = {ref.evidence_id: ref for ref in reader.evidence_catalog()}
    local_catalog = {ref.evidence_id: ref for ref in local.evidence}
    selected, excerpts = [], []
    missing = []
    input_gaps = [
        f"{name}: local capability is {getattr(local.capabilities, name).status.value}."
        for name in type(local.capabilities).model_fields
        if getattr(local.capabilities, name).status != "analyzed"
    ]
    if local.snapshot.omitted_inputs:
        input_gaps.append("The frozen snapshot omitted inputs; consult the local capture manifest.")
    if any(item.affects_completeness for item in local.limitations):
        input_gaps.append("Local analysis has incomplete inputs; consult the local limitations.")
    local_ids = {ref.evidence_id for ref in local.evidence}
    if set(options.preferred_evidence_ids) - local_ids:
        raise ValueError("preferred evidence is absent from the local analysis")
    priorities = _priorities(local, options.preferred_evidence_ids, missing)
    ranked = sorted(
        (ref for ref in local.evidence if ref.evidence_id in priorities),
        key=lambda ref: (
            priorities[ref.evidence_id],
            ref.path,
            ref.side.value,
            ref.range.start_line,
            ref.range.end_line,
            ref.evidence_id,
        ),
    )
    # Interleave sides within each priority. A diff must not spend its entire
    # capacity on lexically earlier base excerpts before considering head.
    candidates = []
    for priority in sorted(set(priorities.values())):
        queues = {
            side: deque(
                ref
                for ref in ranked
                if priorities[ref.evidence_id] == priority and ref.side == side
            )
            for side in ("head", "base")
        }
        while any(queues.values()):
            for queue in queues.values():
                if queue:
                    candidates.append(queue.popleft())
    # Seed each available diff side with a small existing changed-symbol
    # observation before a large body can monopolize the byte budget. This is
    # source coverage, not a claim that a complete function has been inspected.
    changed = set(local.change_set.changed_symbol_ids)
    concrete_changed = {symbol for symbol in changed if not symbol.endswith("#<module>")}
    seed_symbols = concrete_changed or changed
    seed_ids = set()
    for name in type(local.facts).model_fields:
        if name == "coverage":
            continue
        for fact in getattr(local.facts, name):
            owners = (getattr(fact, "symbol_id", None), getattr(fact, "caller_symbol_id", None))
            if any(
                owner and (owner == symbol or owner.startswith(symbol + "."))
                for owner in owners
                for symbol in seed_symbols
            ):
                seed_ids.update(evidence_ids(fact))
    seeds = sorted(
        (ref for ref in candidates if ref.kind == "code" and ref.evidence_id in seed_ids),
        key=lambda ref: (
            len(reader.read_excerpt(ref.evidence_id).text.encode("utf-8")),
            ref.path,
            ref.range.start_line,
            ref.evidence_id,
        ),
    )
    seed_queues = {
        side: deque(ref for ref in seeds if ref.side == side) for side in ("head", "base")
    }
    seed_order = []
    while any(seed_queues.values()):
        for queue in seed_queues.values():
            if queue:
                seed_order.append((queue.popleft(), True))
    ordered = [(ref, False) for ref in candidates if priorities[ref.evidence_id] < 2]
    body_bundles = {}
    for bundle in _source_bundles(local, reader, missing):
        for ident in bundle:
            body_bundles[ident] = bundle
        ordered.append((local_catalog[bundle[0]], False))
    ordered += seed_order
    ordered += [
        (ref, False)
        for ref in candidates
        if priorities[ref.evidence_id] >= 2 and ref.evidence_id not in body_bundles
    ]
    selected_ids, seeded_sides, seed_selected_ids = set(), set(), set()
    body_ids = {
        ref
        for fact in local.facts.functions
        if fact.kind == "function"
        for ref in fact.evidence_ids
        if local_catalog[ref].kind == "code"
    }
    test_bundles = {}
    for test in local.test_definitions:
        if any(ref in priorities for ref in test.evidence_ids):
            # A partial test body without its assertion/call evidence is not a
            # usable TestDefinition. Admit its complete existing closure at once.
            for ref in test.evidence_ids:
                test_bundles[ref] = test.evidence_ids
    # Reserve the small omission-status envelope while packing. A later rejected
    # candidate must not make already accepted evidence overflow the hard cap.
    omission_notes = (
        "Sensitive or excluded evidence omitted.",
        "Sensitive or excluded derived material omitted.",
        "Evidence omitted by excerpt budget.",
        "Evidence omitted by request token-estimate or wire-byte budget.",
        "Changed source is present locally, but no changed-code evidence was selected.",
        "Complete changed/caller or supporting module context omitted by a configured budget or filter.",
    )
    for ref, is_seed in ordered:
        complete_bundle = all(
            ident in selected_ids for ident in body_bundles.get(ref.evidence_id, (ref.evidence_id,))
        )
        if complete_bundle or (is_seed and ref.side in seeded_sides):
            continue
        bundle = (
            (ref.evidence_id,)
            if ref.evidence_id in options.preferred_evidence_ids
            and ref.evidence_id not in selected_ids
            else body_bundles.get(
                ref.evidence_id, test_bundles.get(ref.evidence_id, (ref.evidence_id,))
            )
        )
        additions = [local_catalog[ident] for ident in bundle if ident not in selected_ids]
        # A full body supersedes a provisional seed excerpt contained within it.
        # The source remains covered without paying twice for overlapping text.
        replaced = {
            old.evidence_id
            for old in selected
            if old.evidence_id in seed_selected_ids
            and any(
                new.evidence_id in body_ids
                and old.path == new.path
                and old.side == new.side
                and new.range.start_line <= old.range.start_line
                and old.range.end_line <= new.range.end_line
                for new in additions
            )
        }
        kept_refs = tuple(item for item in selected if item.evidence_id not in replaced)
        kept_excerpts = tuple(item for item in excerpts if item.evidence_id not in replaced)
        extra_excerpts, omission = [], None
        for member in additions:
            if excluded_path(member.path, options.exclude_paths):
                omission = omission_notes[0]
                break
            if catalog.get(member.evidence_id) != member:
                raise ValueError("reader evidence differs from the frozen local catalog")
            excerpt = reader.read_excerpt(member.evidence_id)
            validate_excerpts(local.snapshot.snapshot_id, (member,), (excerpt,))
            if contains_secret(excerpt.text):
                omission = omission_notes[0]
                break
            if (
                len(kept_excerpts) + len(additions) > options.max_excerpts
                or len(excerpt.text) > options.max_excerpt_chars
            ):
                omission = omission_notes[2]
                break
            extra_excerpts.append(excerpt)
        if omission:
            if selection_log is not None:
                selection_log.append(
                    {"decision": "omitted", "evidence_ids": bundle, "reason": omission}
                )
            if ref.evidence_id in body_bundles and omission_notes[5] not in missing:
                missing.append(omission_notes[5])
            if omission not in missing:
                missing.append(omission)
            continue
        trial_missing = list(dict.fromkeys((*missing, *omission_notes)))
        trial = _project(
            local,
            (*kept_refs, *additions),
            (*kept_excerpts, *extra_excerpts),
            request_id=request_id,
            options=options,
            cli_version=cli_version,
            missing=trial_missing,
            input_gaps=input_gaps,
            review_directives=review_directives,
        )
        # Complete source comes first. Reserve room for structural behavior units
        # before filling the tail with overlapping individual fact excerpts.
        reserve = (
            min(2500, options.payload_token_budget // 8)
            if ref.evidence_id not in body_bundles
            and trial.behavior_view is not None
            and not is_seed
            and priorities.get(ref.evidence_id, 5) >= 2
            else 0
        )
        if not _fits_budget(trial, options, reserve_tokens=reserve):
            if selection_log is not None:
                selection_log.append(
                    {"decision": "omitted", "evidence_ids": bundle, "reason": omission_notes[3]}
                )
            if ref.evidence_id in body_bundles and omission_notes[5] not in missing:
                missing.append(omission_notes[5])
            if omission_notes[3] not in missing:
                missing.append(omission_notes[3])
            continue
        selected = [*kept_refs, *additions]
        excerpts = [*kept_excerpts, *extra_excerpts]
        selected_ids.difference_update(replaced)
        seed_selected_ids.difference_update(replaced)
        selected_ids.update(member.evidence_id for member in additions)
        if is_seed:
            seed_selected_ids.update(member.evidence_id for member in additions)
        seeded_sides.update(member.side for member in additions if member.evidence_id in seed_ids)
    changed_paths = {
        path for file in local.change_set.files for path in (file.base_path, file.head_path) if path
    }
    if any(ref.kind == "code" and ref.path in changed_paths for ref in local.evidence) and not any(
        ref.kind == "code" and ref.path in changed_paths for ref in selected
    ):
        missing.append(omission_notes[4])
    request = _project(
        local,
        tuple(selected),
        tuple(excerpts),
        request_id=request_id,
        options=options,
        cli_version=cli_version,
        missing=missing,
        input_gaps=input_gaps,
        review_directives=review_directives,
    )
    if not _fits_budget(request, options):
        raise ContextBudgetExceeded("Minimum request exceeds the input budget.")
    request = _select_behaviors(local, request, options)
    validate_request_against_local(local, request)
    if selection_log is not None:
        selection_log.append(
            {
                "decision": "selected",
                "evidence_ids": tuple(ref.evidence_id for ref in request.evidence),
                "reason": "Retained in the bounded request; retrieval does not establish runtime reachability.",
            }
        )
    return request


def _select_behaviors(local, request, options):
    """Retain complete original units only, within the same wire/token budgets."""
    if (
        local.behavior_view is None
        or local.behavior_view.version not in options.behavior_view_versions
    ):
        return request
    allowed = {ref.evidence_id for ref in request.evidence}
    owners = {(fact.side, fact.symbol_id) for fact in request.facts.functions}
    changed = set(local.change_set.changed_symbol_ids)
    units = sorted(
        local.behavior_view.units,
        key=lambda unit: (
            unit.symbol_id not in changed,
            unit.symbol_id,
            unit.result.range.start_line if unit.result else 0,
            unit.side != "head",
            unit.unit_id,
        ),
    )
    selected = []
    for unit in units:
        if (
            (unit.side, unit.symbol_id) not in owners
            or not evidence_ids(unit) <= allowed
            or unsafe_value(unit, options.exclude_paths)
        ):
            continue
        view = local.behavior_view.model_copy(
            update={
                "units": tuple([*selected, unit]),
                "omitted_units": local.behavior_view.omitted_units + len(units) - len(selected) - 1,
            }
        )
        candidate = request.model_copy(update={"behavior_view": view})
        if _fits_budget(candidate, options):
            selected.append(unit)
            request = candidate
    return request


def preview_request(request: AnalysisRequest) -> str:
    size = len(request.model_dump_json().encode("utf-8"))
    lines = [
        f"Snapshot: {request.snapshot_id}",
        f"Selected {len(request.excerpts)} excerpts; {size} UTF-8 wire bytes.",
        f"Model review payload: {_payload_byte_size(request)} UTF-8 bytes.",
        f"Model review payload: {_payload_token_estimate(request)} estimated o200k tokens; "
        "not a provider-reported token count.",
        f"Model payload allowance: {request.input_token_budget // 2} estimated tokens "
        "(50% of the input budget); "
        "the remaining 50% is reserved for service prompts, schema and previous model output.",
    ]
    lines.extend(
        f"- {ref.side.value}:{ref.path}:{ref.range.start_line}-{ref.range.end_line} ({ref.kind.value})"
        for ref in request.evidence
    )
    lines.extend(f"Missing: {reason}" for reason in request.missing_context)
    if request.behavior_view is not None:
        lines.append(
            f"Behavior view v{request.behavior_view.version}: "
            f"{len(request.behavior_view.units)} selected units; "
            f"{request.behavior_view.omitted_units} omitted. Lexical paths, not execution proof."
        )
    if request.behavior_review_version is not None:
        lines.append(f"Requested structured behavior review v{request.behavior_review_version}.")
    return "\n".join(lines)

"""Static skeleton: the control structure of each entry, before any synthesis.

Built from facts alone, without a model. Each entry becomes one flow that shows the
conditions, loops, results and non-trivial calls of the entry function itself, in
source order, connected by the branches they sit on. Names are source text.

Limits: callees are not expanded, `try`/`except` is not modelled, and a call on an
object of unknown type is shown only when it is awaited.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from genesis_contracts.business_map import BusinessMap, EntryDetection
from genesis_contracts.facts import CallBoundary, CodeEntry, CodeFact, FactKind, FactSet
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.models import EvidenceSide

MAX_STEPS = 60
MAX_FALLBACK_ROOTS = 20
_RESULTS = {FactKind.returns, FactKind.raises}
_JUMPS = {FactKind.breaks, FactKind.continues}


def _short(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _digest(text: str, length: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _shown(fact: CodeFact) -> bool:
    if fact.kind != FactKind.call:
        return True
    if fact.boundary in {CallBoundary.internal, CallBoundary.external}:
        return True
    return fact.boundary == CallBoundary.unknown and fact.awaited


def _evaluation_order(fact: CodeFact):
    """Order facts as they are evaluated: an inner expression before the one containing it.

    A call inside `raise f(x)` or `return f(x)` ends where its statement ends, so it
    sorts by end position first and, on a tie, by the later start.
    """
    span = fact.range
    return (
        span.end_line,
        span.end_column or 0,
        -span.start_line,
        -(span.start_column or 0),
    )


def _step_kind(fact: CodeFact) -> str:
    if fact.kind in {FactKind.condition, FactKind.loop}:
        return "decision"
    if fact.kind in _RESULTS:
        return "result"
    return "external" if fact.boundary == CallBoundary.external else "action"


def _entry_label(entry: CodeEntry) -> str:
    attributes = entry.attributes
    if entry.kind == "http_route":
        return " ".join(part for part in (attributes.get("method"), attributes.get("path")) if part)
    for key in ("command", "task"):
        if key in attributes:
            return f"{key} {attributes[key]}"
    if entry.kind == "cli_command":
        # Typer and Click derive the command name from the function name.
        return "command " + entry.symbol_id.rsplit(".", 1)[-1].rsplit("#", 1)[-1].replace("_", "-")
    return entry.kind.value.replace("_", " ")


class _Flow:
    """Turn the ordered facts of one entry function into steps and control edges."""

    def __init__(self, entry: CodeEntry, items: list[CodeFact]):
        self.entry, self.items = entry, items
        self.steps: list[dict] = []
        self.edges: list[dict] = []
        self.evidence: set[str] = set(entry.evidence_ids)
        # Control transfers that leave a loop body early, by loop and by kind.
        self.jumps: dict[tuple[str, FactKind], list] = {}

    @staticmethod
    def step_id(fingerprint: str) -> str:
        return "step_" + fingerprint[3:19]

    def add_step(self, fingerprint, name, kind, evidence) -> str:
        self.evidence.update(evidence)
        self.steps.append(
            {
                "step_id": self.step_id(fingerprint),
                "name": _short(name),
                "kind": kind,
                "support": "static_fact",
                "resolution": "resolved",
                "anchors": [fingerprint],
                "evidence_ids": list(evidence),
            }
        )
        return self.step_id(fingerprint)

    def connect(self, pending, fingerprint, evidence, *, loop_back=False) -> None:
        """Attach every pending control transfer to the step of `fingerprint`."""
        for source, branch in pending:
            edge = {
                "source": self.step_id(source.fingerprint),
                "target": self.step_id(fingerprint),
                "support": "static_fact",
                "resolution": "resolved",
            }
            if branch is not None:
                edge["relation"] = "branch"
                edge["condition"] = {
                    "label": _short(branch),
                    "branch": _short(branch),
                    "anchor": source.fingerprint,
                }
                edge["evidence_ids"] = list(source.evidence_ids)
            else:
                edge["relation"] = "loop" if loop_back else "sequence"
                edge["anchors"] = sorted({source.fingerprint, fingerprint})
                edge["evidence_ids"] = list(evidence)
            self.edges.append(edge)

    def block(self, index: int, prefix: tuple, pending: list) -> tuple[int, list]:
        """Consume the facts nested exactly under `prefix`; return what stays pending."""
        items = self.items
        while index < len(items):
            fact = items[index]
            chain = tuple((guard.fingerprint, guard.branch) for guard in fact.guards)
            if chain[: len(prefix)] != prefix:
                break
            if fact.kind in _JUMPS:
                # Not a step: whatever was pending now goes back to, or out of, the loop.
                if fact.loops:
                    self.jumps.setdefault((fact.loops[-1], fact.kind), []).extend(pending)
                index, pending = index + 1, []
                continue
            self.add_step(fact.fingerprint, fact.text, _step_kind(fact), fact.evidence_ids)
            self.connect(pending, fact.fingerprint, fact.evidence_ids)
            index += 1
            if fact.kind in {FactKind.condition, FactKind.loop}:
                taken, ends = [], []
                while index < len(items):
                    nested = tuple((g.fingerprint, g.branch) for g in items[index].guards)
                    if (
                        nested[: len(prefix)] != prefix
                        or len(nested) <= len(prefix)
                        or nested[len(prefix)][0] != fact.fingerprint
                    ):
                        break
                    branch = nested[len(prefix)][1]
                    taken.append(branch)
                    index, branch_ends = self.block(
                        index, (*prefix, (fact.fingerprint, branch)), [(fact, branch)]
                    )
                    if fact.kind == FactKind.loop:
                        self.connect(
                            branch_ends, fact.fingerprint, fact.evidence_ids, loop_back=True
                        )
                    else:
                        ends.extend(branch_ends)
                if fact.kind == FactKind.loop:
                    continued = self.jumps.pop((fact.fingerprint, FactKind.continues), [])
                    self.connect(continued, fact.fingerprint, fact.evidence_ids, loop_back=True)
                    broken = self.jumps.pop((fact.fingerprint, FactKind.breaks), [])
                    pending = [(fact, "exit"), *broken]
                else:
                    untaken = [branch for branch in fact.branches if branch not in taken]
                    pending = ends + [(fact, branch) for branch in untaken]
            else:
                pending = [] if fact.kind in _RESULTS else [(fact, None)]
        return index, pending


def _entry_fact(entry: CodeEntry, label: str) -> CodeFact:
    """A stand-in fact for the entry itself, so the trigger step can be anchored and linked."""
    return CodeFact.model_construct(
        fingerprint=fact_fingerprint(symbol=entry.symbol_id, kind="entry", text=label),
        evidence_ids=entry.evidence_ids,
    )


def control_edges(facts, root: str) -> dict[str, list[tuple[str, str | None]]]:
    """Control transfers between the facts of one symbol, keyed by fingerprint.

    `root` stands for entering the symbol. Each transfer is `(target, branch)`; the
    branch is set when the transfer leaves a condition or loop on that branch.
    """
    items = sorted(facts, key=_evaluation_order)
    flow = _Flow(CodeFact.model_construct(evidence_ids=()), items)
    start = CodeFact.model_construct(fingerprint=root, evidence_ids=())
    flow.add_step(root, "entry", "trigger", ())
    flow.block(0, (), [(start, None)])
    by_step = {flow.step_id(fact.fingerprint): fact.fingerprint for fact in items}
    by_step[flow.step_id(root)] = root
    graph: dict[str, list[tuple[str, str | None]]] = {}
    for edge in flow.edges:
        branch = edge["condition"]["branch"] if "condition" in edge else None
        graph.setdefault(by_step[edge["source"]], []).append((by_step[edge["target"]], branch))
    return graph


def flow_id_for(symbol_ids) -> str:
    """Identity of a flow: its entry symbols, independent of any name given to it."""
    return "flow_" + _digest("\0".join(sorted(symbol_ids)))


def shown_facts(facts: FactSet, side: EvidenceSide = EvidenceSide.head) -> dict:
    """The facts a skeleton shows, by symbol, in evaluation order."""
    by_symbol: dict[str, list[CodeFact]] = {}
    for fact in facts.facts:
        if fact.side == side and _shown(fact):
            by_symbol.setdefault(fact.symbol_id, []).append(fact)
    for items in by_symbol.values():
        items.sort(key=_evaluation_order)
    return by_symbol


def skeleton_flow(entries, by_symbol, *, max_steps: int = MAX_STEPS) -> tuple[dict, set[str]]:
    """The skeleton of one flow from its entries. Returns the flow and the evidence it cites."""
    entries = sorted(entries, key=lambda item: item.symbol_id)
    steps, edges, evidence, names = [], [], set(), []
    counted, total, truncated = 0, 0, False
    for entry in entries:
        qualified = entry.symbol_id.partition("#")[2]
        label = _entry_label(entry)
        items = by_symbol.get(entry.symbol_id, [])
        flow = _Flow(entry, items[:max_steps])
        trigger = _entry_fact(entry, label)
        flow.add_step(trigger.fingerprint, f"{label} · {qualified}", "trigger", entry.evidence_ids)
        flow.block(0, (), [(trigger, None)])
        steps += flow.steps
        edges += flow.edges
        evidence |= flow.evidence
        names.append(f"{label} · {qualified}")
        counted += len([fact for fact in flow.items if fact.kind not in _JUMPS])
        total += len(items)
        truncated |= len(items) > max_steps
    return (
        {
            "flow_id": flow_id_for(entry.symbol_id for entry in entries),
            "name": _short(" + ".join(names)),
            "stage": "skeleton",
            "support": "static_fact",
            "entries": [
                entry.model_dump(mode="json", exclude={"side"}, exclude_none=True)
                for entry in entries
            ],
            "steps": steps,
            "edges": edges,
            "accounting": {
                "accountable": counted,
                "covered": counted,
                "omitted": 0,
                "unaccounted": 0,
                "truncated": truncated,
            },
            "limitations": [
                {
                    "code": "skeleton_truncated",
                    "message": f"Only the first {max_steps} facts of an entry are shown; "
                    f"{total} facts exist.",
                    "affects_completeness": True,
                }
            ]
            if truncated
            else [],
        },
        evidence,
    )


def build_skeleton(
    facts: FactSet, *, side: EvidenceSide = EvidenceSide.head, max_steps: int = MAX_STEPS
) -> BusinessMap:
    """Build the skeleton map of one snapshot side from its facts."""
    entries = [entry for entry in facts.entries if entry.side == side]
    shown = [entry for entry in entries if entry.detection == EntryDetection.adapter]
    by_symbol = shown_facts(facts, side)
    limitations = []
    if not shown:
        roots = sorted(entries, key=lambda e: (-len(by_symbol.get(e.symbol_id, ())), e.symbol_id))
        shown = roots[:MAX_FALLBACK_ROOTS]
        limitations.append(
            {
                "code": "no_framework_entries",
                "message": "No framework entry was recognised; the largest uncalled public "
                "functions are shown instead and may not be real entries.",
                "affects_completeness": True,
            }
        )
    flows, domains, evidence = [], {}, set()
    for entry in sorted(shown, key=lambda item: item.symbol_id):
        flow, cited = skeleton_flow([entry], by_symbol, max_steps=max_steps)
        flows.append(flow)
        evidence.update(cited)
        folder = str(PurePosixPath(entry.symbol_id.partition("#")[0]).parent)
        domains.setdefault("(repository root)" if folder == "." else folder, []).append(
            flow["flow_id"]
        )
    catalog = {ref.evidence_id: ref for ref in facts.evidence}
    hidden = len(entries) - len(shown)
    return BusinessMap.model_validate(
        {
            "snapshot_id": facts.snapshot_id,
            "side": side.value,
            "analysis_status": "partial",
            "domains": [
                {
                    "domain_id": "domain_" + _digest(name),
                    "name": _short(name),
                    "support": "path_grouping",
                    "flow_ids": flow_ids,
                }
                for name, flow_ids in sorted(domains.items())
            ],
            "flows": flows,
            "coverage": {
                "scope": f"Static skeleton of {len(shown)} entries, not yet synthesized; "
                f"{hidden} further candidate entries are not shown.",
                "entries_total": len(entries),
                "entries_planned": 0,
                "entries_skipped": 0,
                "entries_unhandled": len(entries),
                "tasks_total": 0,
                "tasks_validated": 0,
                "tasks_pending": 0,
            },
            "limitations": limitations,
            "evidence": [catalog[key].model_dump(mode="json") for key in sorted(evidence)],
        }
    )

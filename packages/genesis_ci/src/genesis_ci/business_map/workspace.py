"""The agent loop over a prepared session: plan, context, query, submit, assemble.

Every call does one bounded thing and stores its result, so an interrupted agent
loses nothing. The map is never edited in place: it is rebuilt from the plan, the
accepted submissions and the facts each time something changes.

An agent's submission is taken or rejected as a whole. What it calls resolved must
be anchored in analyzer facts; a relation the facts cannot support has to be
submitted as a candidate with a reason. A path into an exception handler is the one
relation no fact speaks about, so it is always kept as a candidate.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath

from genesis_contracts.business_map import BusinessMap, EdgeRelation, MapFlow, StepKind
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.facts import CallBoundary, CodeEntry, CodeFact, FactKind, FactSet, Language
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.map_tasks import EvidenceCite, FlowSubmission, MapPlan, place
from genesis_contracts.models import EvidenceRef, EvidenceSide, ReferenceRange
from pydantic import ValidationError

from genesis_ci.snapshot import slice_source
from genesis_ci.snapshot_store import load_snapshot

from .changes import CHANGE_TASK, ChangeAnalysis
from .python_entries import entry_id
from .session import evidence_bundle, session_root, write_json
from .skeleton import (
    _JUMPS,
    _entry_label,
    _evaluation_order,
    control_edges,
    flow_id_for,
    shown_facts,
    skeleton_flow,
)

HEAD = EvidenceSide.head
ACCOUNTABLE_LIMIT = 400
# A step may stand for a whole function. From this many conditions, loops and results
# inside the function on, the submission has to say why one step is enough.
UNEXPANDED_REASON_FROM = 8
REACH_DEPTH = 4
# How many calls an edge may pass through between two steps. Functions that only hand
# the work on get no step of their own, and the way in and out leads through them.
FRAME_DEPTH = 6
# Standard-library modules that do reach outside the process. The rest are helpers,
# such as reading the clock, and are not outside systems a flow has to account for.
_EFFECTFUL_STDLIB = {"subprocess", "socket", "urllib", "http", "smtplib", "ftplib", "sqlite3"}
ANCHOR_RANGE_LINES = 12
# How many steps a message names before it says how many more there are.
STEPS_NAMED = 4
# How much of a fact's source text a message quotes.
QUOTED_CHARS = 80
SOURCE_CHARS = 12000
SEARCH_LIMIT = 40
CLAIM_SECONDS = 900
OTHER_FACT_LIMIT = 80
ROOT_CANDIDATE_LIMIT = 40
POSSIBLE_ENTRY_LIMIT = 20
# What the map says about a path into an exception handler the agent gave no reason for.
HANDLER_REASON = (
    "try/except is not analyzed; this path into the handler is the agent's reading of the code."
)
_ACCOUNTED = {FactKind.condition, FactKind.loop, FactKind.raises}
# What `submit` says about an omission of something no flow has to account for.
UNNEEDED = (
    "This fact needs no entry: it is not among the units this flow has to account for. "
    "Nothing was recorded for it."
)
RULES = (
    "Name steps in business language; one step may cover several code facts.",
    "Cite evidence for every step: an evidence_id, or path + start_line + end_line + quote.",
    "A resolved step needs anchors. List fact fingerprints, or cite a range of at most "
    f"{ANCHOR_RANGE_LINES} lines and the facts inside it become the anchors.",
    "Account for the chain, not for every line. `accountable` lists units: a `fact` is a "
    "condition, loop or result of an entry function; a `function` is a function called on the "
    "chain; a `system` is an outside system the chain talks to; an `await` is an awaited call "
    "whose target is not internal.",
    "For each called function choose one: anchor a step inside it to expand it (its own "
    "conditions, loops and raised errors then become accountable and are reported back), "
    "anchor a step on the call so that one step stands for it, or list the call in `omitted` "
    "with a reason. One choice covers every call to the same function.",
    "A step that stands for a function with many conditions, loops and results inside needs "
    "`unexpanded_reason`: one sentence on why its inside is not part of the business chain.",
    "Every unit must be used by a step or branch, or listed in `omitted` with a reason. "
    "Whatever is left is reported as unaccounted.",
    "A branch edge leaves a decision step and names the branch of that condition it takes.",
    "An expanded function is entered by a `call` edge from the step that calls it, and left "
    "by an edge from where it is done to the step the caller runs next.",
    "If the code does not show a relation, submit it as candidate or unknown with a reason.",
)


class LoopError(ValueError):
    """A request the session cannot accept. `errors` lists every problem found."""

    def __init__(self, code: str, message: str, errors: list[dict] | None = None):
        self.code = code
        self.errors = errors or []
        super().__init__(message)


@dataclass
class _Unit:
    """One thing a flow has to account for.

    `fact`: a condition, loop or result. `await`: an awaited call that leaves the code.
    `function`: a function called on the chain, whatever the number of calls to it.
    `system`: an outside system. Any of `facts` can stand for the unit as an anchor.
    """

    kind: str
    key: str
    facts: list[CodeFact]

    @property
    def anchor(self) -> str:
        return self.facts[0].fingerprint

    @property
    def members(self) -> set[str]:
        return {fact.fingerprint for fact in self.facts}


def external_system(fact: CodeFact) -> str | None:
    """The outside system a call talks to, by its top-level package; nothing for helpers."""
    if fact.boundary != CallBoundary.external:
        return None
    names = sorted(
        {
            target.removeprefix("instance:").removeprefix("external:").split(".")[0]
            for target in fact.target.targets
        }
        - {""}
    )
    if not names:
        return None
    helper = (
        fact.language == Language.python
        and names[0] in sys.stdlib_module_names
        and names[0] not in _EFFECTFUL_STDLIB
    )
    return None if helper else names[0]


def _digest(text: str, length: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _jump_advice(fact: CodeFact) -> str:
    """Why a `break` or `continue` cannot be an anchor, and how to draw it instead."""
    onward = "the step that follows the loop" if fact.kind == FactKind.breaks else "the loop's step"
    return (
        f"`{fact.text}` on line {fact.range.start_line} is not a step: it only says where its "
        "loop goes next. Leave it out and point the edge that led to it, usually a branch of "
        f"the condition around it, at {onward}."
    )


def _quoted(fact: CodeFact) -> str:
    """The first line of a fact's source text, short enough to sit inside a sentence."""
    line = fact.text.strip().splitlines()[0] if fact.text.strip() else ""
    return line if len(line) <= QUOTED_CHARS else line[: QUOTED_CHARS - 1] + "…"


def _problem(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


_ITEM = re.compile(r"^(steps|edges|omitted|observations|changes)\[(\d+)\]")
_NAMED_BY = {
    "steps": ("step {}", ("key",)),
    "edges": ("edge {} -> {}", ("source", "target")),
    "omitted": ("omitted {}", ("anchor",)),
    "observations": ("observation on {}", ("step",)),
    "changes": ("change {}", ("change_id",)),
}


def _keys(found: list[str]) -> str:
    """`step 'a'` or `steps 'a', 'b'`, for a message that names steps by their keys."""
    shown = ", ".join(f"'{key}'" for key in found[:STEPS_NAMED])
    more = f" and {len(found) - STEPS_NAMED} more" if len(found) > STEPS_NAMED else ""
    return ("step " if len(found) == 1 else "steps ") + shown + more


def _named(problems: list[dict], raw, describe=None) -> list[dict]:
    """Say which item each problem is about, by the name the submission gives it.

    A path names an item by its position, and among fifty steps a position is easy to
    misread: `steps[34]` was taken for another step twice in a row. `describe` adds what
    the name stands for where the name says nothing, as with a fingerprint.
    """
    for problem in problems:
        found = _ITEM.match(problem["path"])
        items = raw.get(found.group(1)) if found and isinstance(raw, dict) else None
        if not isinstance(items, list) or int(found.group(2)) >= len(items):
            continue
        item = items[int(found.group(2))]
        wording, fields = _NAMED_BY[found.group(1)]
        values = [item.get(field) for field in fields] if isinstance(item, dict) else []
        if values and all(isinstance(value, str) for value in values):
            problem["item"] = wording.format(*values)
            about = describe(found.group(1), item) if describe else None
            if about:
                problem["item"] += f" ({about})"
    return problems


def _location(parts) -> str:
    """`steps[1].evidence[0]`, the same form the CLI's own checks report."""
    return place(parts) or "(document)"


def pydantic_problems(error: ValidationError) -> list[dict]:
    found = error.errors()
    places = [tuple(item["loc"]) for item in found]

    def echo(item) -> bool:
        # A list reported as too short only because one of its items was invalid.
        place = tuple(item["loc"])
        return item["type"] == "too_short" and any(
            other != place and other[: len(place)] == place for other in places
        )

    return [
        _problem(_location(item["loc"]), "invalid_" + item["type"], item["msg"])
        for item in found
        if not echo(item)
    ]


_pydantic_problems = pydantic_problems


class Workspace:
    def __init__(self, repo: Path, session_id: str):
        self.repo = repo.expanduser().resolve(strict=True)
        self.root = session_root(self.repo, session_id)
        if not (self.root / "session.json").is_file():
            raise FileNotFoundError(f"no such session: {session_id}")
        self.session = self._read("session.json")
        stored = self._read("evidence.json") if (self.root / "evidence.json").is_file() else []
        self._minted = {item["evidence_id"]: EvidenceRef.model_validate(item) for item in stored}

    def _read(self, name: str):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    @cached_property
    def facts(self) -> FactSet:
        return FactSet.model_validate_json((self.root / "facts.json").read_text(encoding="utf-8"))

    @cached_property
    def snapshot(self):
        return load_snapshot(self.root / "snapshot")

    @cached_property
    def symbols(self) -> dict:
        return {item.symbol_id: item for item in self.facts.symbols if item.side == HEAD}

    @cached_property
    def by_symbol(self) -> dict[str, list[CodeFact]]:
        grouped: dict[str, list[CodeFact]] = {}
        for fact in self.facts.facts:
            if fact.side == HEAD:
                grouped.setdefault(fact.symbol_id, []).append(fact)
        for items in grouped.values():
            items.sort(key=_evaluation_order)
        return grouped

    @cached_property
    def by_fingerprint(self) -> dict[str, CodeFact]:
        return {fact.fingerprint: fact for fact in self.facts.facts if fact.side == HEAD}

    @cached_property
    def catalog(self) -> dict[str, EvidenceRef]:
        return {ref.evidence_id: ref for ref in self.facts.evidence}

    def evidence(self, evidence_id: str) -> EvidenceRef | None:
        return self.catalog.get(evidence_id) or self._minted.get(evidence_id)

    def adopt_evidence(self, refs: dict[str, EvidenceRef]) -> None:
        """Keep references minted elsewhere in this session, so they can be read back."""
        fresh = {key: ref for key, ref in refs.items() if key not in self._minted}
        if fresh:
            self._minted.update(fresh)
            write_json(
                self.root / "evidence.json",
                [self._minted[key].model_dump(mode="json") for key in sorted(self._minted)],
            )

    # ----- change sessions ---------------------------------------------------------

    @property
    def is_change(self) -> bool:
        return self.session.get("mode") == "change"

    @cached_property
    def changes(self) -> ChangeAnalysis:
        return ChangeAnalysis(self)

    def stored_map(self) -> BusinessMap:
        return BusinessMap.model_validate_json(
            (self.root / "business-map.json").read_text(encoding="utf-8")
        )

    def stored_report(self) -> ChangeReport | None:
        if not self.is_change:
            return None
        path = self.root / "change-report.json"
        if not path.is_file():
            return self.refresh_change()
        return ChangeReport.model_validate_json(path.read_text(encoding="utf-8"))

    def change_summary(self) -> dict:
        if not self.is_change:
            raise LoopError(
                "not_a_change_session",
                "This session compares nothing. Run `genesis map prepare --base REV` to "
                "analyze the changes since a revision.",
            )
        return {**self.session, **self.changes.summary(self.stored_map())}

    def refresh_change(self) -> ChangeReport | None:
        """Rebuild the change report against the map as it is stored now."""
        return self._publish(self.stored_map())

    def _publish(self, business_map: BusinessMap) -> ChangeReport | None:
        """Store the map, the change report that follows from it, and their excerpts."""
        write_json(
            self.root / "business-map.json",
            business_map.model_dump(mode="json", exclude_none=True),
        )
        evidence = {ref.evidence_id: ref for ref in business_map.evidence}
        report = None
        if self.is_change:
            report, closest = self.changes.build_with_closest(business_map)
            write_json(
                self.root / "change-report.json", report.model_dump(mode="json", exclude_none=True)
            )
            # Kept beside the report for `status`: the flows asked to describe changed code.
            write_json(self.root / "closest-flows.json", closest)
            evidence.update((ref.evidence_id, ref) for ref in report.evidence)
        bundle = evidence_bundle(self.snapshot, tuple(evidence[key] for key in sorted(evidence)))
        write_json(self.root / "evidence-bundle.json", bundle.model_dump(mode="json"))
        return report

    def _submit_change(self, raw) -> dict:
        """Check explanations and coverage verdicts for changes; all or nothing."""
        folder = self.root / "changes"
        try:
            accepted, found = self.changes.check(raw)
            problems = [_problem(*item) for item in found]
        except ValidationError as error:
            accepted, problems = {}, _pydantic_problems(error)
        if problems:
            _named(problems, raw)
            counter = {"rejected": 0}
            if (folder / "attempts.json").is_file():
                counter = json.loads((folder / "attempts.json").read_text(encoding="utf-8"))
            counter["rejected"] += 1
            write_json(folder / "attempts.json", counter)
            return {
                "task_id": CHANGE_TASK,
                "status": "rejected",
                "rejections": counter["rejected"],
                "accepted_version_kept": True,
                "errors": problems,
            }
        write_json(
            folder / "accepted.json",
            {"assessments": {**self.changes.assessments(), **accepted}},
        )
        report = self.refresh_change()
        return {
            "task_id": CHANGE_TASK,
            "status": "accepted",
            "assessed": len(accepted),
            **self._change_progress(report),
            "errors": [],
        }

    def _change_progress(self, report: ChangeReport) -> dict:
        placed = [item for item in report.changes if item.projection.status != "unassigned"]
        return {
            "analysis_status": report.analysis_status,
            "changes": len(report.changes),
            "changes_placed": len(placed),
            "changes_waiting": sum(1 for item in report.owed() if item.explanation is None),
            "limitations": [item.code for item in report.limitations if item.affects_completeness],
        }

    # ----- entries, plan and tasks ------------------------------------------------

    @cached_property
    def plan(self) -> dict | None:
        return self._read("plan.json") if (self.root / "plan.json").is_file() else None

    def entries(self) -> dict[str, CodeEntry]:
        """Head-side entries by id, including the ones an accepted plan proposed."""
        found = {item.entry_id: item for item in self.facts.entries if item.side == HEAD}
        for raw in (self.plan or {}).get("proposed", []):
            found[raw["entry_id"]] = CodeEntry.model_validate(raw)
        return found

    def entry_anchor(self, entry: CodeEntry) -> str:
        return fact_fingerprint(symbol=entry.symbol_id, kind="entry", text=_entry_label(entry))

    def default_plan(self) -> MapPlan:
        folders: dict[str, list[CodeEntry]] = {}
        for entry in self.entries().values():
            if entry.detection == "adapter":
                folder = str(PurePosixPath(entry.symbol_id.partition("#")[0]).parent)
                folders.setdefault("(repository root)" if folder == "." else folder, []).append(
                    entry
                )
        return MapPlan(
            domains=[{"key": "d_" + _digest(name), "name": name[:200]} for name in sorted(folders)],
            flows=[
                {
                    "key": "f_" + entry.entry_id[6:],
                    "domain": "d_" + _digest(name),
                    "entry_ids": [entry.entry_id],
                }
                for name in sorted(folders)
                for entry in sorted(folders[name], key=lambda item: item.symbol_id)
            ],
        )

    def _entered(self, targets) -> list[str]:
        """The definitions a call runs. Creating an object runs its `__init__`, never the
        class body, which ran once when the module was imported."""
        found = []
        for target in targets:
            symbol = self.symbols.get(target)
            if symbol is None:
                continue
            if symbol.kind != "class":
                found.append(target)
            elif target + ".__init__" in self.symbols:
                found.append(target + ".__init__")
        return found

    def _units(self, entry_symbols, used) -> tuple[list[_Unit], set[str]]:
        """What a flow has to account for, given the anchors its steps and edges use.

        The entry functions are always expanded. Any other function is expanded when
        something is anchored inside it. Expanded functions contribute their conditions,
        loops and results; every function they call and every outside system they talk
        to counts once, however many calls there are.
        """
        expanded = list(dict.fromkeys(entry_symbols))
        for fingerprint in sorted(used):
            fact = self.by_fingerprint.get(fingerprint)
            if fact is None or fact.symbol_id in expanded:
                continue
            symbol = self.symbols.get(fact.symbol_id)
            if symbol is not None and symbol.kind == "function":
                expanded.append(fact.symbol_id)
        own: list[_Unit] = []
        functions: dict[str, _Unit] = {}
        systems: dict[str, _Unit] = {}
        for symbol in expanded:
            entry = symbol in entry_symbols
            for fact in self.by_symbol.get(symbol, ()):
                if fact.kind in _ACCOUNTED or (fact.kind == FactKind.returns and entry):
                    own.append(_Unit("fact", fact.fingerprint, [fact]))
                if fact.kind != FactKind.call:
                    continue
                entered = self._entered(fact.target.targets)
                system = external_system(fact)
                if entered:
                    key = "\0".join(sorted(set(entered)))
                    functions.setdefault(key, _Unit("function", key, [])).facts.append(fact)
                elif fact.awaited and fact.boundary != CallBoundary.builtin:
                    own.append(_Unit("await", fact.fingerprint, [fact]))
                elif system is not None:
                    systems.setdefault(system, _Unit("system", system, [])).facts.append(fact)
        return [*own, *functions.values(), *systems.values()], set(expanded)

    def _inside(self, symbol_id: str) -> dict[str, int]:
        """How much a function contains, for deciding whether one step can stand for it."""
        facts = self.by_symbol.get(symbol_id, ())
        return {
            "conditions": sum(1 for fact in facts if fact.kind == FactKind.condition),
            "loops": sum(1 for fact in facts if fact.kind == FactKind.loop),
            "results": sum(1 for fact in facts if fact.kind in {FactKind.returns, FactKind.raises}),
        }

    def _reaches(self, symbol_id: str) -> list[str]:
        """Outside systems a function can get to through the calls it makes."""
        cache = self.__dict__.setdefault("_reached_systems", {})
        if symbol_id not in cache:
            found, seen, frontier = set(), {symbol_id}, [symbol_id]
            for _ in range(REACH_DEPTH + 1):
                following = []
                for symbol in frontier:
                    for fact in self.by_symbol.get(symbol, ()):
                        if fact.kind != FactKind.call:
                            continue
                        system = external_system(fact)
                        if system is not None:
                            found.add(system)
                        for callee in self._entered(fact.target.targets):
                            if callee not in seen:
                                seen.add(callee)
                                following.append(callee)
                frontier = following
            cache[symbol_id] = sorted(found)
        return cache[symbol_id]

    def _unit_view(self, unit: _Unit) -> dict:
        view = {**self._fact_view(unit.facts[0]), "unit": unit.kind}
        if unit.kind == "function":
            callees = unit.key.split("\0")
            view["function"] = callees
            view["inside"] = {**self._inside(callees[0]), "reaches": self._reaches(callees[0])}
            view["calls"] = len(unit.facts)
        elif unit.kind == "system":
            view["system"] = unit.key
            view["calls"] = len(unit.facts)
        return view

    def save_plan(self, plan: MapPlan | None) -> dict:
        origin = "agent" if plan is not None else "default"
        plan = plan or self.default_plan()
        known = {item.entry_id: item for item in self.facts.entries if item.side == HEAD}
        problems, proposed = [], []
        for index, item in enumerate(plan.proposed_entries):
            where = f"proposed_entries[{index}]"
            symbol = self.symbols.get(item.symbol_id)
            if symbol is None or symbol.kind != "function":
                problems.append(
                    _problem(
                        where + ".symbol_id", "unknown_symbol", "No such function in the snapshot."
                    )
                )
                continue
            # A candidate is a guess the agent may confirm, and say what kind of entry it
            # is. What the analyzers recognised is settled.
            current = known.get(entry_id(item.symbol_id))
            if current is not None and current.detection != "root_heuristic":
                problems.append(
                    _problem(where + ".symbol_id", "already_an_entry", entry_id(item.symbol_id))
                )
                continue
            cited = self._cite(item.evidence, where + ".evidence", problems)
            if cited:
                proposed.append(
                    {
                        "entry_id": entry_id(item.symbol_id),
                        "symbol_id": item.symbol_id,
                        "kind": item.kind.value,
                        "detection": "agent_proposed",
                        "attributes": {"reason": item.reason[:200]},
                        "evidence_ids": cited,
                        "side": "head",
                    }
                )
        # An entry an earlier plan proposed stays available: a plan uses it by its id
        # without proposing it again, and withdraws it by no longer mentioning it.
        again = {item["entry_id"] for item in proposed}
        mentioned = {entry for flow in plan.flows for entry in flow.entry_ids}
        mentioned |= {item.entry_id for item in plan.skipped}
        proposed += [
            raw
            for raw in (self.plan or {}).get("proposed", [])
            if raw["entry_id"] in mentioned and raw["entry_id"] not in again
        ]
        usable = set(known) | {item["entry_id"] for item in proposed}
        for index, flow in enumerate(plan.flows):
            if origin == "agent" and not flow.name:
                problems.append(
                    _problem(
                        f"flows[{index}].name",
                        "name_required",
                        "Give the flow the name a person would use for it, not a route "
                        "or a function name.",
                    )
                )
            for entry in flow.entry_ids:
                if entry not in usable:
                    problems.append(
                        _problem(f"flows[{index}].entry_ids", "unknown_entry", f"No entry {entry}.")
                    )
        for index, item in enumerate(plan.skipped):
            if item.entry_id not in usable:
                problems.append(
                    _problem(
                        f"skipped[{index}].entry_id", "unknown_entry", f"No entry {item.entry_id}."
                    )
                )
        if problems:
            raise LoopError("invalid_plan", "The plan was not accepted.", problems)
        entries = {
            **known,
            **{item["entry_id"]: CodeEntry.model_validate(item) for item in proposed},
        }
        tasks = []
        for flow in plan.flows:
            symbols = [entries[entry].symbol_id for entry in flow.entry_ids]
            # What the flow has to account for before any step exists: its entry functions.
            units, _ = self._units(symbols, set())
            flow_id = flow_id_for(symbols)
            tasks.append(
                {
                    "task_id": "task_" + flow_id[5:],
                    "kind": "flow",
                    "flow_key": flow.key,
                    "flow_id": flow_id,
                    "entry_ids": list(flow.entry_ids),
                    "accountable": [unit.anchor for unit in units[:ACCOUNTABLE_LIMIT]],
                    "truncated": len(units) > ACCOUNTABLE_LIMIT,
                }
            )
        write_json(
            self.root / "plan.json",
            {
                "origin": origin,
                "plan": plan.model_dump(mode="json", exclude_none=True),
                "proposed": proposed,
                "tasks": tasks,
            },
        )
        self.__dict__.pop("plan", None)
        self.assemble()
        return {"status": "accepted", **self.status()}

    def tasks(self) -> list[dict]:
        if self.plan is None:
            raise LoopError("no_plan", "Run `genesis map plan` before working on tasks.")
        return self.plan["tasks"]

    def task(self, task_id: str) -> dict:
        found = next((item for item in self.tasks() if item["task_id"] == task_id), None)
        if found is None:
            raise LoopError("unknown_task", f"No task {task_id} in the current plan.")
        return found

    def _task_file(self, task_id: str, name: str) -> Path:
        return self.root / "tasks" / task_id / name

    def _stored(self, task_id: str, name: str):
        path = self._task_file(task_id, name)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def task_state(self, task: dict) -> str:
        if self._stored(task["task_id"], "accepted.json") is not None:
            return "validated"
        if self._stored(task["task_id"], "rejected.json") is not None:
            return "failed"
        claim = self._stored(task["task_id"], "claim.json")
        return "claimed" if claim and claim["expires_at"] > time.time() else "pending"

    # ----- evidence ----------------------------------------------------------------

    def _register(self, side, path, span) -> EvidenceRef:
        ref = self.snapshot.source.evidence(side, path, span)
        if ref.evidence_id not in self.catalog and ref.evidence_id not in self._minted:
            self._minted[ref.evidence_id] = ref
            write_json(
                self.root / "evidence.json",
                [self._minted[key].model_dump(mode="json") for key in sorted(self._minted)],
            )
        return ref

    def _cite(self, cites: tuple[EvidenceCite, ...], where: str, problems: list) -> list[str]:
        """Resolve citations against the frozen snapshot; report every one that fails."""
        resolved = []
        for index, cite in enumerate(cites):
            at = f"{where}[{index}]"
            if cite.evidence_id is not None:
                if self.evidence(cite.evidence_id) is None:
                    problems.append(_problem(at, "unknown_evidence", cite.evidence_id))
                else:
                    resolved.append(cite.evidence_id)
                continue
            if cite.side != HEAD:
                problems.append(
                    _problem(at, "wrong_side", "Only head-side source can be cited here.")
                )
                continue
            if cite.path not in self.snapshot.source.list_files(cite.side):
                problems.append(
                    _problem(
                        at, "file_not_in_snapshot", f"{cite.path} is not in the frozen snapshot."
                    )
                )
                continue
            span = ReferenceRange(start_line=cite.start_line, end_line=cite.end_line)
            try:
                text = slice_source(self.snapshot.source.read_text(cite.side, cite.path), span)
            except ValueError:
                problems.append(
                    _problem(at, "range_out_of_bounds", "The line range is outside the file.")
                )
                continue
            if cite.quote not in text:
                problems.append(
                    _problem(
                        at,
                        "quote_not_found",
                        "The quote is not in that range of the frozen file; read it again through the CLI.",
                    )
                )
                continue
            resolved.append(self._register(cite.side, cite.path, span).evidence_id)
        return list(dict.fromkeys(resolved))

    def _facts_in(self, evidence_ids) -> list[str]:
        """Fingerprints of the facts short cited ranges give a step, in evaluation order."""
        return [
            fact.fingerprint
            for fact in self._starting_in(evidence_ids)
            if fact.kind not in _JUMPS and fact.boundary != CallBoundary.builtin
        ]

    def _starting_in(self, evidence_ids) -> list[CodeFact]:
        """Every fact that starts inside a short cited range, picked up as an anchor or not."""
        found = []
        for evidence_id in evidence_ids:
            ref = self.evidence(evidence_id)
            if ref is None or ref.range.end_line - ref.range.start_line >= ANCHOR_RANGE_LINES:
                continue
            for symbol, facts in self.by_symbol.items():
                if symbol.partition("#")[0] != ref.path:
                    continue
                if symbol.endswith("#<module>"):
                    # A decorator or default value runs at import time, not in the flow.
                    continue
                found += [
                    fact
                    for fact in facts
                    # A fact belongs to the range it starts in. A call written over many
                    # lines is cited by its first lines, not by all of them.
                    if ref.range.start_line <= fact.range.start_line <= ref.range.end_line
                ]
        return found

    def _clash(self, unit: _Unit, omitted: str, steps: dict, symbols: dict, expanded) -> str:
        """Why a unit cannot be left out: which steps expand it, or which step uses it.

        The two call for different repairs, and one sentence for both named neither the
        function nor the step.
        """
        opened = sorted(set(unit.key.split("\0")) & expanded) if unit.kind == "function" else []
        if opened:
            inside = [
                key
                for key, step in steps.items()
                if any(symbols.get(anchor) in opened for anchor in step["anchors"])
            ]
            if not inside:
                # An entry function of the flow that the flow also calls.
                return (
                    f"{', '.join(opened)} is an entry of this flow, and an entry function is "
                    "always expanded. No call to it belongs in `omitted`: drop this entry."
                )
            return (
                f"{', '.join(opened)} is expanded: {_keys(inside)} "
                f"{'is' if len(inside) == 1 else 'are'} anchored inside it. That accounts "
                "for every call to it, so none of them belongs in `omitted`: drop this entry. "
                "To leave the function out instead, take out the steps inside it."
            )
        target = (
            unit.key.replace("\0", ", ")
            if unit.kind == "function"
            else f"the outside system `{unit.key}`"
        )
        holders = [key for key, step in steps.items() if omitted in step["anchors"]]
        if holders and unit.kind in {"function", "system"}:
            return (
                f"This call is in the `anchors` of {_keys(holders)}, and a step anchored on a "
                f"call stands for {target}. Drop this entry, or take the call out of those "
                "`anchors`."
            )
        if holders:
            return (
                f"It is in the `anchors` of {_keys(holders)}. A fact is on a step or left "
                "out, not both: drop this entry, or take it out of those `anchors`."
            )
        # Another call to the same function or system: one unit, so one choice.
        other = min(
            (
                (self.by_fingerprint[anchor], key)
                for key, step in steps.items()
                for anchor in step["anchors"]
                if anchor in unit.members
            ),
            key=lambda found: (found[0].symbol_id, found[0].range.start_line),
        )
        return (
            f"Step '{other[1]}' is anchored on another call to {target}, on line "
            f"{other[0].range.start_line}, and one choice covers every call to the same "
            f"{'function' if unit.kind == 'function' else 'system'}. Drop this entry, or take "
            "that call out of the step's `anchors`."
        )

    def _about(self, kind: str, item: dict) -> str | None:
        """What an item of a submission is, where its own name is only a fingerprint."""
        fact = self.by_fingerprint.get(item.get("anchor")) if kind == "omitted" else None
        if fact is None:
            return None
        path = fact.symbol_id.partition("#")[0]
        return f"`{_quoted(fact)}` on line {fact.range.start_line} of {path}"

    def _unit_key(self, fact: CodeFact) -> tuple[str, str]:
        """The unit a fact is accounted for by: a function, an outside system, or itself."""
        if fact.kind == FactKind.call:
            entered = self._entered(fact.target.targets)
            if entered:
                return ("function", "\0".join(sorted(set(entered))))
            if not fact.awaited or fact.boundary == CallBoundary.builtin:
                system = external_system(fact)
                if system is not None:
                    return ("system", system)
        return ("fact", fact.fingerprint)

    # ----- context and queries -----------------------------------------------------

    def _source(self, symbol_id: str) -> dict:
        symbol = self.symbols[symbol_id]
        span = ReferenceRange(start_line=symbol.range.start_line, end_line=symbol.range.end_line)
        text = slice_source(self.snapshot.source.read_text(HEAD, symbol.path), span)
        return {
            "symbol_id": symbol_id,
            "path": symbol.path,
            "start_line": span.start_line,
            "end_line": span.end_line,
            "text": text[:SOURCE_CHARS],
            "truncated": len(text) > SOURCE_CHARS,
        }

    def _fact_view(self, fact: CodeFact) -> dict:
        view = {
            "fingerprint": fact.fingerprint,
            "kind": fact.kind.value,
            "text": fact.text[:400],
            "symbol_id": fact.symbol_id,
            "line": fact.range.start_line,
            "evidence_id": fact.evidence_ids[0],
        }
        if fact.branches:
            view["branches"] = list(fact.branches)
        if fact.guards:
            view["guards"] = [
                {"fingerprint": g.fingerprint, "branch": g.branch} for g in fact.guards
            ]
        if fact.kind == FactKind.call:
            view["boundary"] = fact.boundary.value
            view["targets"] = list(fact.target.targets)
            if fact.deferred:
                # Handed to another call or written in a lambda: run by the receiver.
                view["deferred"] = True
                view["note"] = fact.target.reason
        return view

    def _expands_to(self, symbol_id: str) -> list[dict]:
        """The units a step anchored inside this function adds to what a flow accounts for."""
        facts = self.by_symbol.get(symbol_id, ())
        if not facts:
            return []
        units, _ = self._units([], {facts[0].fingerprint})
        return [self._unit_view(unit) for unit in units[:OTHER_FACT_LIMIT]]

    def _large(self, symbol_ids) -> list[str]:
        """Called functions that one step can stand for only with a reason why."""
        return [
            callee
            for callee in self._callees(symbol_ids)
            if sum(self._inside(callee).values()) >= UNEXPANDED_REASON_FROM
        ]

    def _callees(self, symbol_ids) -> list[str]:
        found = []
        for symbol in symbol_ids:
            for fact in self.by_symbol.get(symbol, ()):
                if fact.kind == FactKind.call:
                    found += self._entered(fact.target.targets)
        return sorted(set(found) - set(symbol_ids))

    def context(self, task_id: str, claim: bool = False) -> dict:
        if task_id == CHANGE_TASK:
            if not self.is_change:
                self.change_summary()
            return self.changes.context(self.stored_map())
        task = self.task(task_id)
        if claim:
            current = self._stored(task_id, "claim.json")
            if current and current["expires_at"] > time.time():
                raise LoopError("task_claimed", "Another worker holds this task for now.")
            write_json(
                self._task_file(task_id, "claim.json"), {"expires_at": time.time() + CLAIM_SECONDS}
            )
        entries = self.entries()
        chosen = [entries[item] for item in task["entry_ids"]]
        symbols = [entry.symbol_id for entry in chosen]
        accepted = self._stored(task_id, "accepted.json")
        # With an accepted version the list reflects what its steps already expanded.
        used = set(accepted["used"]) if accepted and "used" in accepted else set()
        units, _ = self._units(symbols, used)
        listed = {fingerprint for unit in units for fingerprint in unit.members}
        # Code several flows share is described on one of them: which changes this flow
        # carries, which it is asked to bring onto the map, and which other flows take.
        change = (
            {"change": self.changes.for_flow(self.stored_map(), task["flow_id"])}
            if self.is_change
            else {}
        )
        return {
            "task_id": task_id,
            "kind": task["kind"],
            "state": self.task_state(task),
            "flow_id": task["flow_id"],
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "symbol_id": entry.symbol_id,
                    "kind": entry.kind.value,
                    "detection": entry.detection.value,
                    "framework": entry.framework,
                    "attributes": entry.attributes,
                    "anchor": self.entry_anchor(entry),
                    "evidence_ids": list(entry.evidence_ids),
                }
                for entry in chosen
            ],
            "source": [self._source(symbol) for symbol in symbols],
            "accountable": [self._unit_view(unit) for unit in units[:ACCOUNTABLE_LIMIT]],
            "accountable_truncated": len(units) > ACCOUNTABLE_LIMIT,
            "other_facts": [
                self._fact_view(fact)
                for symbol in symbols
                for fact in self.by_symbol.get(symbol, ())
                if fact.fingerprint not in listed
                and fact.kind not in _JUMPS
                and fact.boundary != CallBoundary.builtin
            ][:OTHER_FACT_LIMIT],
            "callees": self._callees(symbols),
            # Of those, the ones too big inside to fold into one step without saying why.
            "large_callees": self._large(symbols),
            **change,
            "previous": accepted["result"] if accepted else None,
            "rules": list(RULES),
        }

    def query_symbol(self, symbol_id: str) -> dict:
        if symbol_id not in self.symbols:
            near = sorted(key for key in self.symbols if key.endswith(symbol_id.rsplit("#", 1)[-1]))
            raise LoopError(
                "unknown_symbol",
                f"No symbol {symbol_id}.",
                [_problem("symbol", "candidates", ", ".join(near[:10]) or "none")],
            )
        callers = sorted(
            {
                fact.symbol_id
                for fact in self.by_fingerprint.values()
                if fact.kind == FactKind.call and symbol_id in fact.target.targets
            }
        )
        return {
            "source": self._source(symbol_id),
            "inside": {**self._inside(symbol_id), "reaches": self._reaches(symbol_id)},
            # Without `break` and `continue`: they are in the source above, and a fact
            # listed here is one a step can be anchored on.
            "facts": [
                self._fact_view(fact)
                for fact in self.by_symbol.get(symbol_id, ())
                if fact.kind not in _JUMPS
            ],
            "callers": callers,
            "callees": self._callees([symbol_id]),
            "large_callees": self._large([symbol_id]),
            # Known before a submission expands it, not from what that leaves unaccounted.
            "expands_to": self._expands_to(symbol_id),
        }

    def search(self, text: str) -> dict:
        if not text.strip():
            raise LoopError("empty_search", "Search text must not be empty.")
        matches, truncated = [], False
        for path in self.snapshot.source.list_files(HEAD):
            lines = self.snapshot.source.read_text(HEAD, path).split("\n")
            for number, line in enumerate(lines, 1):
                if text in line:
                    if len(matches) >= SEARCH_LIMIT:
                        truncated = True
                        break
                    span = ReferenceRange(start_line=number, end_line=number)
                    matches.append(
                        {
                            "path": path,
                            "line": number,
                            "text": line.strip()[:240],
                            "evidence_id": self._register(HEAD, path, span).evidence_id,
                        }
                    )
            if truncated:
                break
        return {"matches": matches, "truncated": truncated}

    def read(self, evidence_id: str) -> dict:
        ref = self.evidence(evidence_id)
        if ref is None:
            raise LoopError("unknown_evidence", f"No evidence {evidence_id} in this session.")
        text = slice_source(self.snapshot.source.read_text(ref.side, ref.path), ref.range)
        return {
            "evidence_id": evidence_id,
            "side": ref.side.value,
            "path": ref.path,
            "start_line": ref.range.start_line,
            "end_line": ref.range.end_line,
            "text": text[:SOURCE_CHARS],
            "truncated": len(text) > SOURCE_CHARS,
        }

    # ----- submission --------------------------------------------------------------

    def _root(self, symbol: str) -> str:
        return fact_fingerprint(symbol=symbol, kind="entry", text="<enter>")

    def _graph(self, symbol: str) -> dict:
        cache = self.__dict__.setdefault("_graphs", {})
        if symbol not in cache:
            cache[symbol] = control_edges(self.by_symbol.get(symbol, ()), self._root(symbol))
        return cache[symbol]

    def _reach(self, symbol: str, starts) -> set[str]:
        """Facts of a symbol that control can reach from `starts`, the starts included."""
        graph, seen, pending = self._graph(symbol), set(starts), list(starts)
        while pending:
            for target, _ in graph.get(pending.pop(), ()):
                if target not in seen:
                    seen.add(target)
                    pending.append(target)
        return seen

    def _runs(self, symbol: str) -> set[str]:
        """The definitions the calls written in one definition run."""
        cache = self.__dict__.setdefault("_run_by", {})
        if symbol not in cache:
            cache[symbol] = {
                callee
                for fact in self.by_symbol.get(symbol, ())
                if fact.kind == FactKind.call
                for callee in self._entered(fact.target.targets)
            }
        return cache[symbol]

    def _leads_to(self, fact: CodeFact) -> set[str]:
        """The definitions a call gets to: the ones it runs, and theirs, a few calls deep."""
        cache = self.__dict__.setdefault("_led", {})
        if fact.fingerprint not in cache:
            frontier = set(self._entered(fact.target.targets))
            seen = set(fact.target.targets) | frontier
            for _ in range(FRAME_DEPTH - 1):
                frontier = {callee for symbol in frontier for callee in self._runs(symbol)} - seen
                seen |= frontier
            cache[fact.fingerprint] = seen
        return cache[fact.fingerprint]

    def _passes(self, starts: dict[str, set[str]], targets: list[str], symbols: dict) -> bool:
        """Whether control can pass from `starts` (facts by symbol) to any target fact.

        Inside one function the target must be reachable in its control structure. Across
        functions, a reachable call must lead into the target's function, or the target
        must come after a call that leads into the function control is leaving. Either
        way the call may get there through functions in between that have no step.
        """
        goals: dict[str, set[str]] = {}
        for fingerprint in targets:
            goals.setdefault(symbols[fingerprint], set()).add(fingerprint)
        for symbol, nodes in starts.items():
            reached = self._reach(symbol, nodes)
            if reached & goals.get(symbol, set()):
                return True
            for fact in self.by_symbol.get(symbol, ()):
                if (
                    fact.kind == FactKind.call
                    and fact.fingerprint in reached
                    and self._leads_to(fact) & goals.keys()
                ):
                    return True
            for callee_of, wanted in goals.items():
                returns_to = {
                    fact.fingerprint
                    for fact in self.by_symbol.get(callee_of, ())
                    if fact.kind == FactKind.call and symbol in self._leads_to(fact)
                }
                if returns_to and self._reach(callee_of, returns_to) & wanted:
                    return True
        return False

    def _nodes(self, anchors: list[str], symbols: dict, entry_anchors: set[str]) -> dict:
        """Group a step's anchors by symbol; an entry anchor stands for entering it."""
        grouped: dict[str, set[str]] = {}
        for fingerprint in anchors:
            symbol = symbols[fingerprint]
            node = self._root(symbol) if fingerprint in entry_anchors else fingerprint
            grouped.setdefault(symbol, set()).add(node)
        return grouped

    def submit(self, task_id: str, raw) -> dict:
        if task_id == CHANGE_TASK:
            if not self.is_change:
                self.change_summary()
            return self._submit_change(raw)
        task = self.task(task_id)
        try:
            submission = FlowSubmission.model_validate(raw)
        except ValidationError as error:
            return self._reject(task, _pydantic_problems(error), raw)
        entries = self.entries()
        chosen = [entries[item] for item in task["entry_ids"]]
        anchor_symbols = {fp: fact.symbol_id for fp, fact in self.by_fingerprint.items()}
        entry_anchors = {self.entry_anchor(entry) for entry in chosen}
        anchor_symbols.update((self.entry_anchor(entry), entry.symbol_id) for entry in chosen)
        problems: list[dict] = []
        # What the submission leaves out, by the unit each entry stands for. A call that
        # a cited range merely picks up, such as a helper in the arguments of a `return`,
        # is no anchor of the step when its unit is left out: saying so outranks it.
        left_out_units = {
            self._unit_key(self.by_fingerprint[item.anchor])
            for item in submission.omitted
            if item.anchor in self.by_fingerprint
        }
        steps, by_key, cited, taken_ids = [], {}, set(), set()
        # Steps whose citations failed: report that once, not every consequence of it.
        broken: set[str] = set()
        for index, step in enumerate(submission.steps):
            where = f"steps[{index}]"
            before = len(problems)
            evidence = self._cite(step.evidence, where + ".evidence", problems)
            if len(problems) > before:
                broken.add(step.key)
            unknown = [fp for fp in step.anchors if fp not in anchor_symbols]
            if unknown:
                problems.append(_problem(where + ".anchors", "unknown_anchor", ", ".join(unknown)))
            # A `break` or `continue` is no node of the control structure. Edges to and
            # from a step on one would be refused as unreachable, which says nothing
            # about the cause, so the anchor is refused here and the edges are not checked.
            jumps = [
                fp
                for fp in step.anchors
                if fp in self.by_fingerprint and self.by_fingerprint[fp].kind in _JUMPS
            ]
            if jumps:
                problems.append(
                    _problem(
                        where + ".anchors",
                        "anchor_not_a_step",
                        " ".join(_jump_advice(self.by_fingerprint[fp]) for fp in jumps),
                    )
                )
                broken.add(step.key)
            anchors = list(
                dict.fromkeys(
                    [
                        *(fp for fp in step.anchors if fp in anchor_symbols and fp not in jumps),
                        *(
                            fp
                            for fp in self._facts_in(evidence)
                            if self._unit_key(self.by_fingerprint[fp]) not in left_out_units
                        ),
                    ]
                )
            )
            if not anchors:
                # Calls to built-ins are kept out of what a range gives, or `len(...)`
                # would sit in every step. Where the cited lines hold nothing else, they
                # are what the step rests on: refusing it only had the same call sent
                # again by its fingerprint.
                anchors = [
                    fact.fingerprint
                    for fact in self._starting_in(evidence)
                    if fact.boundary == CallBoundary.builtin
                ]
            if step.key in broken:
                pass
            elif step.resolution == "resolved" and not anchors:
                short = all(
                    (ref := self.evidence(item)).range.end_line - ref.range.start_line
                    < ANCHOR_RANGE_LINES
                    for item in evidence
                )
                # What the cited lines do hold, set aside because the submission leaves
                # it out. Told that no fact starts there, an agent looks for a missing
                # fact; what it has to undo is its own omission.
                set_aside = [
                    fact
                    for fact in self._starting_in(evidence)
                    if fact.kind not in _JUMPS and self._unit_key(fact) in left_out_units
                ]
                if set_aside:
                    message = (
                        "The cited lines hold nothing but "
                        + ", ".join(f"`{_quoted(fact)}`" for fact in set_aside[:STEPS_NAMED])
                        + ", which this submission lists in `omitted`. A step cannot rest on "
                        "what is left out: drop that entry, or drop this step."
                    )
                elif evidence and short:
                    message = (
                        "No analyzer fact starts in the cited lines; a plain assignment has "
                        "none. Fold this into a neighbouring step, list the fingerprint of a "
                        "fact in `anchors`, or submit the step as candidate with a reason."
                    )
                else:
                    message = (
                        "A resolved step needs an analyzer fact: list anchors, cite a "
                        f"range of at most {ANCHOR_RANGE_LINES} lines that contains one, or "
                        "submit the step as candidate with a reason."
                    )
                problems.append(_problem(where, "step_not_anchored", message))
            if (
                step.key not in broken
                and (step.resolution != "unknown" or step.contract is not None)
                and not evidence
            ):
                problems.append(
                    _problem(where + ".evidence", "evidence_required", "Cite the code.")
                )
            if step.resolution != "resolved" and not step.reason:
                problems.append(
                    _problem(where + ".reason", "reason_required", "Say what is uncertain.")
                )
            if len(problems) > before:
                broken.add(step.key)
            identity = anchors[0] if anchors else "key:" + step.key
            step_id = "step_" + _digest(task["flow_id"] + "\0" + identity, 16)
            if step_id in taken_ids:
                step_id = "step_" + _digest(task["flow_id"] + "\0" + identity + "\0" + step.key, 16)
            taken_ids.add(step_id)
            cited.update(evidence)
            item = {
                "step_id": step_id,
                "name": step.name,
                "kind": step.kind.value,
                "support": "agent_synthesis",
                "resolution": step.resolution.value,
                "anchors": anchors,
                "evidence_ids": evidence,
                "finding_ids": [],
            }
            if step.reason:
                item["reason"] = step.reason
            if step.contract:
                item["contract"] = step.contract.model_dump(mode="json", exclude_none=True)
            steps.append(item)
            by_key[step.key] = item
        edges = []
        for index, edge in enumerate(submission.edges):
            where = f"edges[{index}]"
            source, target = by_key[edge.source], by_key[edge.target]
            evidence = self._cite(edge.evidence, where + ".evidence", problems)
            cited.update(evidence)
            if broken & {edge.source, edge.target}:
                continue
            item = {
                "source": source["step_id"],
                "target": target["step_id"],
                "relation": edge.relation.value,
            }
            if edge.label and edge.relation != EdgeRelation.branch:
                item["label"] = edge.label
            # `try` and `except` are not analyzed. Checked like any other edge, a path into
            # a handler was refused when the `try` body ends in a `return` and taken as a
            # fact when the handler merely follows it in the source. Neither is known.
            unchecked = edge.relation == EdgeRelation.exception
            if edge.relation == EdgeRelation.branch:
                conditions = [
                    fp
                    for fp in source["anchors"]
                    if fp in self.by_fingerprint and edge.branch in self.by_fingerprint[fp].branches
                ]
                if source["kind"] != StepKind.decision.value or not conditions:
                    valid = sorted(
                        {
                            branch
                            for fp in source["anchors"]
                            if fp in self.by_fingerprint
                            for branch in self.by_fingerprint[fp].branches
                        }
                    )
                    problems.append(
                        _problem(
                            where + ".branch",
                            "unknown_branch",
                            "The source must be a decision step anchored on a condition with this "
                            f"branch. Branches available there: {', '.join(valid) or 'none'}.",
                        )
                    )
                    continue
                taken = {
                    target
                    for target, branch in self._graph(anchor_symbols[conditions[0]]).get(
                        conditions[0], ()
                    )
                    if branch == edge.branch
                }
                if not (
                    target["anchors"]
                    and self._passes(
                        {anchor_symbols[conditions[0]]: taken}, target["anchors"], anchor_symbols
                    )
                ):
                    problems.append(
                        _problem(
                            where,
                            "branch_target_not_reachable",
                            f"Taking the '{edge.branch}' branch does not lead to the target step. "
                            "Point the edge at the step that branch reaches, or submit the "
                            "relation as a candidate sequence with a reason.",
                        )
                    )
                    continue
                item.update(
                    condition={
                        "label": edge.label or edge.branch,
                        "branch": edge.branch,
                        "anchor": conditions[0],
                    },
                    support="static_fact",
                    resolution="resolved",
                    evidence_ids=evidence or list(self.by_fingerprint[conditions[0]].evidence_ids),
                )
            elif edge.resolution == "resolved" and not unchecked:
                supported = (
                    source["anchors"]
                    and target["anchors"]
                    and self._passes(
                        self._nodes(source["anchors"], anchor_symbols, entry_anchors),
                        [
                            self._root(anchor_symbols[fp]) if fp in entry_anchors else fp
                            for fp in target["anchors"]
                        ],
                        {
                            **anchor_symbols,
                            **{self._root(s): s for s in set(anchor_symbols.values())},
                        },
                    )
                )
                if not supported:
                    problems.append(
                        _problem(
                            where,
                            "edge_not_supported",
                            "The code's control structure does not let execution pass from the "
                            "source step to the target step. Check the order and the branches, "
                            "or submit the edge as candidate with a reason.",
                        )
                    )
                    continue
                item.update(
                    support="static_fact",
                    resolution="resolved",
                    anchors=sorted({source["anchors"][0], target["anchors"][0]}),
                    evidence_ids=evidence or target["evidence_ids"] or source["evidence_ids"],
                )
            else:
                reason = edge.reason or (HANDLER_REASON if unchecked else "")
                if not reason:
                    problems.append(
                        _problem(where + ".reason", "reason_required", "Say what is uncertain.")
                    )
                item.update(
                    support="agent_synthesis",
                    resolution="candidate"
                    if edge.resolution == "resolved"
                    else edge.resolution.value,
                    reason=reason,
                    evidence_ids=evidence or target["evidence_ids"] or source["evidence_ids"],
                )
            cited.update(item["evidence_ids"])
            edges.append(item)
        used = {fp for step in steps for fp in step["anchors"]}
        used.update(fp for edge in edges for fp in edge.get("anchors", ()))
        used.update(edge["condition"]["anchor"] for edge in edges if "condition" in edge)
        units, expanded = self._units([entry.symbol_id for entry in chosen], used)
        truncated = len(units) > ACCOUNTABLE_LIMIT
        units = units[:ACCOUNTABLE_LIMIT]
        unit_of = {fingerprint: unit for unit in units for fingerprint in unit.members}
        covered = {
            id(unit)
            for unit in units
            if unit.members & used
            or (unit.kind == "function" and set(unit.key.split("\0")) & expanded)
        }
        omitted, left_out, ignored = [], set(), []
        for index, item in enumerate(submission.omitted):
            where = f"omitted[{index}].anchor"
            unit = unit_of.get(item.anchor)
            if unit is None and item.anchor in anchor_symbols:
                # A real fact that nothing had to account for, such as a logging call or
                # the inside of a function one step stands for. Leaving it out claims
                # nothing false, and a refusal could only be answered by deleting the line.
                ignored.append(
                    {"path": f"omitted[{index}]", "anchor": item.anchor, "message": UNNEEDED}
                )
            elif unit is None:
                problems.append(_problem(where, "unknown_anchor", "No fact has this fingerprint."))
            elif id(unit) in covered:
                problems.append(
                    _problem(
                        where,
                        "omitted_but_used",
                        self._clash(unit, item.anchor, by_key, anchor_symbols, expanded),
                    )
                )
            elif id(unit) in left_out:
                problems.append(
                    _problem(
                        where,
                        "already_omitted",
                        "Another entry already omits this. One entry covers every call to the "
                        "same function or outside system.",
                    )
                )
            else:
                left_out.add(id(unit))
                entry = {"anchor": item.anchor, "reason": item.reason.value}
                if item.note:
                    entry["note"] = item.note
                omitted.append(entry)
        open_units = [
            unit for unit in units if id(unit) not in covered and id(unit) not in left_out
        ]
        unaccounted = [unit.anchor for unit in open_units]
        # A step anchored on a call, with nothing anchored inside the function called,
        # stands for that function as a whole. Say how much it hides.
        for index, step in enumerate(submission.steps):
            hidden: dict[str, dict] = {}
            for fingerprint in by_key[step.key]["anchors"]:
                fact = self.by_fingerprint.get(fingerprint)
                if fact is None or fact.kind != FactKind.call:
                    continue
                for callee in self._entered(fact.target.targets):
                    inside, reaches = self._inside(callee), self._reaches(callee)
                    if (
                        callee in expanded
                        or callee in hidden
                        or not (sum(inside.values()) or reaches)
                    ):
                        continue
                    hidden[callee] = {"symbol_id": callee, **inside, "reaches": reaches}
            if not hidden:
                continue
            largest = max(
                hidden.values(),
                key=lambda item: item["conditions"] + item["loops"] + item["results"],
            )
            size = largest["conditions"] + largest["loops"] + largest["results"]
            if size >= UNEXPANDED_REASON_FROM and not step.unexpanded_reason:
                problems.append(
                    _problem(
                        f"steps[{index}].unexpanded_reason",
                        "unexpanded_reason_required",
                        f"This step stands for {largest['symbol_id']}, which has "
                        f"{largest['conditions']} conditions, {largest['loops']} loops and "
                        f"{largest['results']} results inside. Anchor steps inside it if it is "
                        "part of the business chain, or say in `unexpanded_reason` why one step "
                        "is enough.",
                    )
                )
            by_key[step.key]["unexpanded"] = [
                {
                    **hidden[callee],
                    **({"reason": step.unexpanded_reason} if step.unexpanded_reason else {}),
                }
                for callee in sorted(hidden)
            ]
        findings = []
        for index, item in enumerate(submission.observations):
            evidence = self._cite(item.evidence, f"observations[{index}].evidence", problems)
            cited.update(evidence)
            finding_id = "find_" + _digest(task["flow_id"] + "\0" + item.statement)
            if evidence:
                finding = {
                    "finding_id": finding_id,
                    "source": "agent_observation",
                    "severity": item.severity.value,
                    "statement": item.statement,
                    "evidence_ids": evidence,
                }
                if item.gap:
                    finding["gap"] = item.gap
                if item.category is not None:
                    finding["category"] = item.category.value
                findings.append(finding)
                by_key[item.step]["finding_ids"].append(finding_id)
        flow = {
            "flow_id": task["flow_id"],
            "name": submission.name,
            "stage": "synthesized",
            "support": "agent_synthesis",
            "entries": [
                entry.model_dump(mode="json", exclude={"side"}, exclude_none=True)
                for entry in chosen
            ],
            "steps": steps,
            "edges": edges,
            "accounting": {
                "accountable": len(units),
                "covered": len(units) - len(omitted) - len(unaccounted),
                "omitted": len(omitted),
                "unaccounted": len(unaccounted),
                "truncated": truncated,
            },
            "omitted": omitted,
            "unaccounted": unaccounted,
        }
        if submission.summary:
            flow["summary"] = submission.summary
        cited.update(ref for entry in chosen for ref in entry.evidence_ids)
        if not problems:
            try:
                MapFlow.model_validate(flow)
            except ValidationError as error:
                problems = _pydantic_problems(error)
        if problems:
            return self._reject(task, problems, raw)
        result = {
            "task_id": task_id,
            "status": "accepted",
            "flow_id": task["flow_id"],
            "steps": {step.key: by_key[step.key]["step_id"] for step in submission.steps},
            "accounting": flow["accounting"],
            "unaccounted": [self._unit_view(unit) for unit in open_units],
            "errors": [],
        }
        if ignored:
            result["ignored"] = ignored
        accepted = self._task_file(task_id, "accepted.json")
        previous = accepted.read_text(encoding="utf-8") if accepted.is_file() else None
        write_json(
            accepted,
            {
                "flow": flow,
                "findings": findings,
                "evidence_ids": sorted(cited),
                # The anchors in use decide which functions count as expanded next time.
                "used": sorted(used),
                "result": result,
            },
        )
        try:
            assembled = self.assemble()
        except ValidationError as error:
            # Never keep a submission the whole map cannot be built with.
            if previous is None:
                accepted.unlink()
            else:
                accepted.write_text(previous, encoding="utf-8")
            return self._reject(task, _pydantic_problems(error), raw)
        self._task_file(task_id, "rejected.json").unlink(missing_ok=True)
        return {**result, "analysis_status": assembled.analysis_status}

    def _reject(self, task: dict, problems: list[dict], raw=None) -> dict:
        """Keep the last accepted version; record why this attempt was refused."""
        _named(problems, raw, self._about)
        counter = self._stored(task["task_id"], "attempts.json") or {"rejected": 0}
        counter["rejected"] += 1
        write_json(self._task_file(task["task_id"], "attempts.json"), counter)
        kept = self._stored(task["task_id"], "accepted.json") is not None
        if not kept:
            write_json(self._task_file(task["task_id"], "rejected.json"), {"errors": problems})
            self.assemble()
        return {
            "task_id": task["task_id"],
            "status": "rejected",
            "flow_id": task["flow_id"],
            "rejections": counter["rejected"],
            "accepted_version_kept": kept,
            "errors": problems,
        }

    # ----- assembly and status -----------------------------------------------------

    def assemble(self) -> BusinessMap:
        """Rebuild the map from the plan, the accepted submissions and the facts."""
        if self.plan is None:
            raise LoopError("no_plan", "Nothing to assemble before a plan exists.")
        plan, entries = self.plan["plan"], self.entries()
        shown = shown_facts(self.facts)
        flows, findings, cited, states = [], [], set(), []
        flow_of_key = {}
        planned = {item["key"]: item for item in plan.get("flows", [])}
        outlined = self.plan["origin"] == "agent"
        for task in self.plan["tasks"]:
            accepted = self._stored(task["task_id"], "accepted.json")
            states.append(self.task_state(task))
            outline = planned.get(task["flow_key"], {})
            if accepted is not None:
                flow = accepted["flow"]
                findings += accepted["findings"]
                cited.update(accepted["evidence_ids"])
            else:
                flow, evidence = skeleton_flow([entries[item] for item in task["entry_ids"]], shown)
                cited.update(evidence)
                if outlined and outline.get("name"):
                    # Until it is described, the flow carries what the plan said about it.
                    flow = {
                        **flow,
                        "name": outline["name"],
                        **({"summary": outline["summary"]} if outline.get("summary") else {}),
                        "name_from_plan": True,
                    }
            flow = {**flow, "tier": outline.get("tier", "primary")}
            if accepted is not None and flow["accounting"]["truncated"]:
                flow = {
                    **flow,
                    "limitations": [
                        {
                            "code": "accountable_truncated",
                            "message": "More code facts are reachable than this task lists.",
                            "affects_completeness": True,
                        }
                    ],
                }
            flows.append(flow)
            flow_of_key[task["flow_key"]] = flow["flow_id"]
        grouping = "agent_synthesis" if self.plan["origin"] == "agent" else "path_grouping"
        domains = []
        for domain in plan.get("domains", []):
            members = [
                flow_of_key[flow["key"]]
                for flow in plan.get("flows", [])
                if flow.get("domain") == domain["key"]
            ]
            if members:
                domains.append(
                    {
                        "domain_id": "domain_" + _digest(domain["key"]),
                        "name": domain["name"],
                        "support": grouping,
                        "flow_ids": members,
                    }
                )
        planned_entries = sum(len(task["entry_ids"]) for task in self.plan["tasks"])
        skipped_entries = [
            {
                "entry_id": item["entry_id"],
                "symbol_id": entries[item["entry_id"]].symbol_id,
                "reason": item["reason"],
                **({"note": item["note"]} if item.get("note") else {}),
            }
            for item in plan.get("skipped", [])
        ]
        skipped = len(skipped_entries)
        coverage = {
            "scope": f"{len(flows)} planned flows covering {planned_entries} of "
            f"{len(entries)} entries.",
            "entries_total": len(entries),
            "entries_planned": planned_entries,
            "entries_skipped": skipped,
            "skipped_entries": skipped_entries,
            "entries_unhandled": len(entries) - planned_entries - skipped,
            "tasks_total": len(states),
            "tasks_validated": states.count("validated"),
            "tasks_pending": states.count("pending") + states.count("claimed"),
            "tasks_failed": states.count("failed"),
        }
        document = {
            "snapshot_id": self.facts.snapshot_id,
            "side": "head",
            "domains": domains,
            "flows": flows,
            "findings": findings,
            "coverage": coverage,
            "evidence": [self.evidence(key).model_dump(mode="json") for key in sorted(cited)],
        }
        try:
            assembled = BusinessMap.model_validate({**document, "analysis_status": "complete"})
        except ValidationError:
            assembled = BusinessMap.model_validate({**document, "analysis_status": "partial"})
        self._publish(assembled)
        return assembled

    def status(self) -> dict:
        """Session state plus the entries a plan can refer to."""

        def view(entry):
            return {
                "entry_id": entry.entry_id,
                "symbol_id": entry.symbol_id,
                "kind": entry.kind.value,
                "detection": entry.detection.value,
                "framework": entry.framework,
                "attributes": entry.attributes,
            }

        entries = sorted(self.entries().values(), key=lambda item: item.symbol_id)
        roots = [item for item in entries if item.detection == "root_heuristic"]
        return {
            **self._status(),
            "entries": [view(item) for item in entries if item.detection != "root_heuristic"],
            "root_candidates": [view(item) for item in roots[:ROOT_CANDIDATE_LIMIT]],
            "root_candidates_total": len(roots),
        }

    def _status(self) -> dict:
        stored = BusinessMap.model_validate_json(
            (self.root / "business-map.json").read_text(encoding="utf-8")
        )
        overall = {
            "analysis_status": stored.analysis_status,
            "coverage": stored.coverage.model_dump(
                mode="json", exclude={"limitations", "scope", "skipped_entries"}
            ),
        }
        change, affected = {}, set()
        report = self.stored_report()
        if report is not None:
            closest = (
                self._read("closest-flows.json")
                if (self.root / "closest-flows.json").is_file()
                else {}
            )
            # The flows this report needs described: those the changes are on, and those
            # closest to changed code that no flow has expanded yet.
            affected = {
                target.flow_id
                for item in report.changes
                for target in (item.projection, *item.other_projections)
                if target.flow_id
            } | closest.keys()
            change = {
                "change": {
                    "task_id": CHANGE_TASK,
                    **self._change_progress(report),
                    "affected_flows": [
                        {
                            "flow_id": flow.flow_id,
                            "name": flow.name,
                            "stage": flow.stage.value,
                            "entry_ids": [entry.entry_id for entry in flow.entries],
                            "closest_to": closest.get(flow.flow_id, []),
                        }
                        for flow in stored.flows
                        if flow.flow_id in affected
                    ],
                    # Uncalled functions that lead to the changes and start no flow: ways
                    # in the map may lack.
                    "possible_entries": [
                        item.model_dump(mode="json")
                        for item in report.possible_entries[:POSSIBLE_ENTRY_LIMIT]
                    ],
                    "possible_entries_total": len(report.possible_entries),
                }
            }
        if self.plan is None:
            return {
                **self.session,
                "plan": None,
                **overall,
                **change,
                "tasks": [],
                "next_task": None,
            }
        flows = {flow["key"]: flow for flow in self.plan["plan"].get("flows", [])}
        tasks = []
        for task in self.plan["tasks"]:
            accepted = self._stored(task["task_id"], "accepted.json")
            rejected = self._stored(task["task_id"], "rejected.json")
            tasks.append(
                {
                    "task_id": task["task_id"],
                    "kind": task["kind"],
                    "state": self.task_state(task),
                    "flow_key": task["flow_key"],
                    "flow_id": task["flow_id"],
                    "name": (accepted or {}).get("flow", {}).get("name")
                    or flows[task["flow_key"]].get("name"),
                    "tier": flows[task["flow_key"]].get("tier", "primary"),
                    "entry_ids": task["entry_ids"],
                    "accountable": len(task["accountable"]),
                    "accounting": (accepted or {}).get("flow", {}).get("accounting"),
                    "errors": len((rejected or {}).get("errors", [])),
                    "rejections": (self._stored(task["task_id"], "attempts.json") or {}).get(
                        "rejected", 0
                    ),
                }
            )

        def first(wanted, among=tasks):
            return next((item["task_id"] for item in among if wanted(item)), None)

        def open_work(among):
            # The business processes before the lookups and upkeep around them. Within
            # each: untouched work, then refused work, then accepted flows that left
            # facts out.
            for tier in ("primary", "supporting"):
                tiered = [item for item in among if item["tier"] == tier]
                found = (
                    first(lambda item: item["state"] == "pending", tiered)
                    or first(lambda item: item["state"] == "failed", tiered)
                    or first(lambda item: (item["accounting"] or {}).get("unaccounted"), tiered)
                )
                if found:
                    return found
            return None

        # A change session needs the flows the changes land on, then the changes themselves.
        touched = [item for item in tasks if item["flow_id"] in affected]
        waiting = change and change["change"]["changes_waiting"]
        return {
            **self.session,
            "plan": self.plan["origin"],
            **overall,
            **change,
            "tasks": tasks,
            "next_task": open_work(touched)
            or (CHANGE_TASK if waiting else None)
            or open_work(tasks),
        }

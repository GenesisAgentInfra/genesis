"""Change report: fact changes placed on the head map, with what tests say about them.

The list of changes comes from the fact diff alone. This module places each change on
a step of the head map, attaches the tests that statically reach the changed code, and
merges in what an agent submitted: a business explanation and a coverage verdict.

Placement prefers a step anchored on the changed code itself. When there is none, the
change goes to the decision it runs under, the nearest step of the same function, or a
step that calls the function, and the report says which of these was used. A change no
step can stand for stays unassigned, and flows that can reach it are listed apart.

No verdict here says a test ran. Static analysis can show that a test calls the changed
function; whether its input takes the changed path is for the agent to assess.
"""

from __future__ import annotations

import ast
import json
import re
from functools import cached_property
from pathlib import PurePosixPath

from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import (
    ChangeKind,
    ChangeReport,
    validate_change_report_against_map,
)
from genesis_contracts.facts import CodeFact, CodeTest, FactKind
from genesis_contracts.map_tasks import ChangeAssessment, ChangeSubmission
from pydantic import ValidationError

from .fact_diff import BASE, HEAD, FactDiff, RawChange, _innermost, diff_facts
from .python_facts import canonical_python
from .skeleton import _evaluation_order, _short, shown_facts, skeleton_flow

CHANGE_TASK = "task_change"
CONTEXT_LIMIT = 30
REACH_DEPTH = 6
TEST_DEPTH = 4
MAX_PROJECTIONS = 6
MAX_CASES = 20
MAX_REMOVED_FLOWS = 20
MAX_UNANALYZED = 100
_SOURCE_KINDS = {ChangeKind.source_added, ChangeKind.source_removed, ChangeKind.source_modified}
_ADDED_KINDS = {
    ChangeKind.condition_added,
    ChangeKind.call_added,
    ChangeKind.result_added,
    ChangeKind.loop_added,
    ChangeKind.symbol_added,
    ChangeKind.source_added,
}
_ASSIGNED = re.compile(r"^\s*([A-Za-z_]\w{2,})\s*(?::[^=\n]*)?=(?!=)", re.MULTILINE)
UNDER = "No step is anchored on this code; it runs under this decision."
NEAREST = "No step is anchored on this code; placed on the nearest step of the same function."
NEAREST_REMOVED = "Removed code; placed on the nearest remaining step of the same function."
CALLS = "No step covers the body of this function; this step calls it."
CITED = "No step is anchored on this code; this step cites the changed lines."
REFERS = "This step's code refers to `{}`, which the changed line defines."
READS = (
    "No step covers the line that reads `{}`, which the changed line defines; placed on the "
    "nearest step of the function that does."
)
# An import statement: the module it names, and the names on one line or in parentheses.
_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+([.\w]+)[ \t]+import[ \t]*(?:\(([^)]*)\)|([^\n]*))", re.MULTILINE
)
CITED_RANGE_LINES = 12
# A request made through an HTTP test client: the method and a literal path.
_HTTP_CALL = re.compile(
    r"\.(get|post|put|patch|delete|head|options)\(\s*f?[\"'](/[^\"'?#]*)", re.IGNORECASE
)
_PATH_PARAMETER = re.compile(r"^(\{.*\}|<.*>|:\w+)$")
RULES = (
    "Read both sides of a change with `genesis map read --evidence <id>` before explaining it.",
    "`summary` says in business terms what is different; `effect` says what that means for "
    "the flow. Do not describe line edits.",
    "Give a `verdict` only after reading the listed tests. covered: a test's input takes the "
    "changed path and the test asserts on the result. reached_only: tests call the code but "
    "miss the changed path or do not assert on it; say what is missing in `note`. "
    "not_reached: no test reaches it. unknown: you could not tell; say why.",
    "`test_ids` names the tests your verdict is about. You may name a test static analysis "
    "did not link, for example one that goes through an HTTP client.",
    "No test was run. Never state that a test passed or that a path executed.",
    "Leave `verdict` out to keep the static result shown under `tests`.",
)


def _closure(starts, graph: dict[str, set[str]], depth: int) -> set[str]:
    seen, frontier = set(starts), list(starts)
    for _ in range(depth):
        following = []
        for symbol in frontier:
            for target in graph.get(symbol, ()):
                if target not in seen:
                    seen.add(target)
                    following.append(target)
        frontier = following
    return seen


def _distances(starts, graph: dict[str, set[str]], depth: int) -> dict[str, int]:
    """How many calls each definition is away from the nearest of `starts`."""
    found = dict.fromkeys(starts, 0)
    frontier = list(found)
    for calls in range(1, depth + 1):
        following = []
        for symbol in frontier:
            for target in graph.get(symbol, ()):
                if target not in found:
                    found[target] = calls
                    following.append(target)
        frontier = following
    return found


def _unassigned(reason: str) -> dict:
    return {"status": "unassigned", "reason": reason}


class _Placement:
    """Where changes go on one particular map."""

    def __init__(self, analysis: ChangeAnalysis, business_map: BusinessMap):
        self.analysis = analysis
        workspace = analysis.workspace
        self.entry_anchor = {
            entry.symbol_id: workspace.entry_anchor(entry) for entry in workspace.entries().values()
        }
        entry_symbol = {anchor: symbol for symbol, anchor in self.entry_anchor.items()}
        self.order: dict[tuple[str, str], tuple[int, int]] = {}
        self.steps_of: dict[str, list[tuple[str, str]]] = {}
        # Steps by the definition their anchors sit in: line, flow, step, enclosing guards.
        self.in_symbol: dict[str, list[tuple[int, str, str, tuple[str, ...]]]] = {}
        # Short source ranges a step cites, by file: first line, last line, flow, step.
        self.cited: dict[str, list[tuple[int, int, str, str]]] = {}
        refs = {ref.evidence_id: ref for ref in business_map.evidence}
        self.reach: dict[str, set[str]] = {}
        # Calls from a flow's entries to each definition it reaches, and its first entry.
        self.calls_to: dict[str, dict[str, int]] = {}
        self.first_entry: dict[str, str] = {}
        for flow_index, flow in enumerate(business_map.flows):
            entries = [entry.symbol_id for entry in flow.entries]
            self.calls_to[flow.flow_id] = _distances(entries, analysis.calls[HEAD], REACH_DEPTH)
            self.first_entry[flow.flow_id] = min(entries, default="")
            self.reach[flow.flow_id] = set(self.calls_to[flow.flow_id])
            for step_index, step in enumerate(flow.steps):
                key = (flow.flow_id, step.step_id)
                self.order[key] = (flow_index, step_index)
                for evidence_id in step.evidence_ids:
                    span = refs[evidence_id].range
                    if span.end_line - span.start_line < CITED_RANGE_LINES:
                        self.cited.setdefault(refs[evidence_id].path, []).append(
                            (span.start_line, span.end_line, *key)
                        )
                for anchor in step.anchors:
                    self.steps_of.setdefault(anchor, []).append(key)
                    fact = workspace.by_fingerprint.get(anchor)
                    if fact is not None:
                        chain = tuple(guard.fingerprint for guard in fact.guards)
                        spot = (fact.range.start_line, *key, chain)
                        self.in_symbol.setdefault(fact.symbol_id, []).append(spot)
                    elif anchor in entry_symbol:
                        # Entering the function comes before anything inside it.
                        self.in_symbol.setdefault(entry_symbol[anchor], []).append((0, *key, ()))

    def _pick(self, hits) -> list[tuple[str, str]]:
        """One step per flow, the earliest on the map, flows in map order."""
        chosen: dict[str, tuple[str, str]] = {}
        for key in sorted(set(hits), key=self.order.__getitem__):
            chosen.setdefault(key[0], key)
        return list(chosen.values())

    def closest(self, change: RawChange) -> str | None:
        """The flow that gets to a change through the fewest calls.

        A tie goes to the flow whose entry sorts first, so the answer is the same
        whatever order a plan lists the flows in.
        """
        symbols = set(self._symbols(change))
        ranked = sorted(
            (min(calls[symbol] for symbol in symbols & calls.keys()), self.first_entry[flow], flow)
            for flow, calls in self.calls_to.items()
            if symbols & calls.keys()
        )
        return ranked[0][2] if ranked else None

    def _symbols(self, change: RawChange) -> tuple[str, ...]:
        """Head-side definitions the change lives in."""
        analysis = self.analysis
        if change.head_symbols:
            return change.head_symbols
        if change.after is None:
            symbol = analysis.diff.moved.get(change.symbol_id, change.symbol_id)
            return (symbol,) if symbol in analysis.workspace.symbols else ()
        users = sorted(
            {fact.symbol_id for _, fact in self._users(change)}
            | {symbol for _, symbol, _ in self._readers(change)}
        )
        if users:
            return tuple(users)
        if change.module_level:
            # A decorator or default value belongs to the function it is written on.
            functions = [
                item
                for item in analysis.symbols_in(HEAD, change.after.path)
                if item.kind == "function"
            ]
            holder = _innermost(functions, change.after.start[0])
            if holder is not None:
                return (holder.symbol_id,)
        return (change.symbol_id,)

    def _names(self, change: RawChange) -> tuple[str, ...]:
        """Module-level names a change defines, or sits inside the definition of.

        A word added to a set that runs over several lines, or a sentence changed in a
        long string, does not show the name it belongs to. The assignment around it does.
        """
        if not change.module_level or change.is_test:
            return ()
        part = change.after or change.before
        found = _ASSIGNED.findall(part.text) if change.kind in _SOURCE_KINDS else []
        for first, last, names in self.analysis.assignments(part.side, part.path):
            if first <= part.end[0] and part.start[0] <= last:
                found += names
        return tuple(dict.fromkeys(found))

    def _reading(self, change: RawChange) -> tuple[list, list]:
        """Where head code reads a name the change defines: by facts, and by lines."""
        cache = self.__dict__.setdefault("_read", {})
        if change.change_id not in cache:
            analysis, part = self.analysis, change.after or change.before
            facts, lines = [], []
            for name in self._names(change):
                word = re.compile(rf"\b{re.escape(name)}\b")
                for path in analysis.readers(part.path, name):
                    facts += [
                        (name, fact)
                        for fact in analysis.facts_in(HEAD, path)
                        if word.search(fact.text) and not fact.symbol_id.endswith("#<module>")
                    ]
                    functions = [
                        item for item in analysis.symbols_in(HEAD, path) if item.kind == "function"
                    ]
                    text = analysis.workspace.snapshot.source.read_text(HEAD, path)
                    for number, line in enumerate(text.split("\n"), start=1):
                        holder = _innermost(functions, number) if word.search(line) else None
                        if holder is not None:
                            lines.append((name, holder.symbol_id, number))
            cache[change.change_id] = (facts, lines)
        return cache[change.change_id]

    def _users(self, change: RawChange) -> list[tuple[str, CodeFact]]:
        """Head facts that refer to a name a module-level change defines."""
        return self._reading(change)[0]

    def _readers(self, change: RawChange) -> list[tuple[str, str, int]]:
        """Lines inside functions that read such a name: the name, the function, the line.

        A line can read a constant without being a fact, as an assignment does.
        """
        return self._reading(change)[1]

    def _line(self, change: RawChange, symbol: str) -> int:
        """The head line a change belongs at; for removed code, where it used to follow."""
        if change.after is not None:
            return change.after.start[0]
        analysis = self.analysis
        line = analysis.workspace.symbols[symbol].range.start_line
        same = analysis.diff.same.get(change.symbol_id)
        for fact in analysis.ordered(BASE, change.symbol_id):
            if (fact.range.start_line, fact.range.start_column or 0) >= change.before.start:
                break
            chain = tuple(guard.fingerprint for guard in fact.guards)
            # Where the facts of this definition were compared, a base fact is found on
            # the head side by what it was matched with, not by its own fingerprint.
            kept = fact.fingerprint if same is None else same.get(fact.fingerprint)
            survivor = analysis.workspace.by_fingerprint.get(kept)
            # Code inside a branch that already ended does not lead to the removed code.
            if survivor is not None and chain == change.guards[: len(chain)]:
                line = survivor.range.start_line
        return line

    def _guards(self, change: RawChange) -> tuple[str, ...]:
        """The conditions and loops a change sits under, as the head side names them.

        Removed code carries the base names of its guards; one that did not survive has
        no head name and matches nothing.
        """
        same = self.analysis.diff.same.get(change.symbol_id)
        if change.after is not None or same is None:
            return change.guards
        return tuple(same.get(guard, "") for guard in change.guards)

    def place(self, change: RawChange) -> tuple[list[dict], set[str]]:
        """Map targets of a change, the first being the main one, and flows that reach it."""
        if change.is_test:
            return [_unassigned("Test code is not placed on the map.")], set()
        analysis = self.analysis
        symbols = self._symbols(change)
        reaching = {flow for flow, reach in self.reach.items() if reach & set(symbols)}

        def projected(hits, reason: str | None = None):
            chosen = self._pick(hits)[:MAX_PROJECTIONS]
            note = {"reason": reason} if reason else {}
            targets = [
                {"status": "projected", "flow_id": flow, "step_id": step, **note}
                for flow, step in chosen
            ]
            return targets, reaching - {flow for flow, _ in chosen}

        hits = [key for anchor in change.head_anchors for key in self.steps_of.get(anchor, ())]
        for symbol in change.head_symbols:
            hits += self.steps_of.get(self.entry_anchor.get(symbol, ""), ())
        if hits:
            return projected(hits)
        if change.after is not None:
            # No fact to match, as for an assignment: use the step that cites these lines.
            first, last = change.after.start[0], change.after.end[0]
            tightest: dict[str, tuple[int, str, str]] = {}
            for start, end, flow, step in self.cited.get(change.after.path, ()):
                if start <= first and last <= end:
                    if flow not in tightest or end - start < tightest[flow][0]:
                        tightest[flow] = (end - start, flow, step)
            if tightest:
                return projected([(flow, step) for _, flow, step in tightest.values()], CITED)
        guards = self._guards(change)
        for guard in reversed(guards):
            if guard in self.steps_of:
                return projected(self.steps_of[guard], UNDER)
        for name, fact in self._users(change):
            if fact.fingerprint in self.steps_of:
                return projected(
                    [
                        key
                        for other, user in self._users(change)
                        if other == name
                        for key in self.steps_of.get(user.fingerprint, ())
                    ],
                    REFERS.format(name),
                )
        reading: dict[str, tuple[str, int]] = {}
        for name, symbol, number in self._readers(change):
            cited = [
                (flow, step)
                for start, end, flow, step in self.cited.get(symbol.partition("#")[0], ())
                if start <= number <= end
            ]
            if cited:
                return projected(cited, REFERS.format(name))
            reading.setdefault(symbol, (name, number))
        for symbol in symbols:
            spots = sorted(self.in_symbol.get(symbol, ()))
            if not spots:
                continue
            line, nearest = self._line(change, symbol), {}
            if symbol in reading:
                # Not where the constant is written: where this function reads it.
                line = reading[symbol][1]
            # Prefer a step at the same nesting or around it over one in a finished branch.
            around = [spot for spot in spots if spot[3] == guards[: len(spot[3])]]
            for spot_line, flow, step, _ in (*spots, *around):
                if flow not in nearest or spot_line <= line:
                    nearest[flow] = (flow, step)
            reason = NEAREST if change.after is not None else NEAREST_REMOVED
            if symbol in reading:
                reason = READS.format(reading[symbol][0])
            return projected(nearest.values(), reason)
        hits = [
            key
            for symbol in symbols
            for fact in analysis.callers[HEAD].get(symbol, ())
            for key in self.steps_of.get(fact.fingerprint, ())
        ]
        if hits:
            return projected(hits, CALLS)
        if not symbols and change.symbol_id in analysis.base_entries:
            return [
                _unassigned("This entry was removed; its flow is listed under removed flows.")
            ], set()
        if not symbols and change.before is not None:
            # The definition is gone: say which flows used to call it.
            callers = {
                analysis.diff.moved.get(fact.symbol_id, fact.symbol_id)
                for symbol in change.base_symbols or (change.symbol_id,)
                for fact in analysis.callers[BASE].get(symbol, ())
            }
            flows = [flow for flow, reach in self.reach.items() if reach & callers]
            if flows:
                removed = {
                    "step_id": "step_" + change.before.anchor[3:19],
                    "name": _short(change.before.text.splitlines()[-1], 200),
                }
                return [
                    {"status": "removed_step", "flow_id": flow, "removed_step": removed}
                    for flow in flows[:MAX_PROJECTIONS]
                ], set()
        if reaching:
            return [
                _unassigned(
                    "No step on the map covers this code; flows that can reach it are listed "
                    "as possibly affected."
                )
            ], reaching
        return [_unassigned("This code is not reachable from any entry on the map.")], set()


class ChangeAnalysis:
    """Changes of one change session. Only `build` depends on the current map."""

    def __init__(self, workspace):
        self.workspace = workspace

    @cached_property
    def diff(self) -> FactDiff:
        snapshot = self.workspace.snapshot
        tests = frozenset(
            (item.side, item.path)
            for item in snapshot.capture.manifest.files
            if item.kind == "test"
        )
        renames = {
            delta.change.base_path: delta.change.head_path
            for delta in snapshot.capture.file_diff.changes
            if delta.change.change_type == "renamed"
        }
        found = diff_facts(
            self.workspace.facts,
            snapshot.source,
            test_paths=tests,
            renames=renames,
            canonical={"python": canonical_python},
        )
        self.workspace.adopt_evidence(found.evidence)
        return found

    @cached_property
    def _by_symbol(self) -> dict:
        grouped = {BASE: {}, HEAD: self.workspace.by_symbol}
        for fact in self.workspace.facts.facts:
            if fact.side == BASE:
                grouped[BASE].setdefault(fact.symbol_id, []).append(fact)
        for items in grouped[BASE].values():
            items.sort(key=_evaluation_order)
        return grouped

    def ordered(self, side, symbol_id: str) -> list[CodeFact]:
        return self._by_symbol[side].get(symbol_id, [])

    @cached_property
    def _by_path(self) -> dict:
        symbols, facts = {}, {}
        for symbol in self.workspace.facts.symbols:
            symbols.setdefault((symbol.side, symbol.path), []).append(symbol)
        for fact in self.workspace.facts.facts:
            facts.setdefault((fact.side, fact.symbol_id.partition("#")[0]), []).append(fact)
        return {"symbols": symbols, "facts": facts}

    def symbols_in(self, side, path: str) -> list:
        return self._by_path["symbols"].get((side, path), [])

    def facts_in(self, side, path: str) -> list[CodeFact]:
        return self._by_path["facts"].get((side, path), [])

    def assignments(self, side, path: str) -> list[tuple[int, int, tuple[str, ...]]]:
        """Module-level assignments of a Python file: first line, last line, names."""
        cache = self.__dict__.setdefault("_assigned", {})
        if (side, path) not in cache:
            found = []
            try:
                source = self.workspace.snapshot.source.read_text(side, path)
                body = ast.parse(source).body if path.endswith(".py") else []
            except (SyntaxError, ValueError, KeyError):
                body = []
            for node in body:
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                    targets = [node.target]
                else:
                    continue
                names = tuple(item.id for item in targets if isinstance(item, ast.Name))
                if names:
                    found.append((node.lineno, node.end_lineno or node.lineno, names))
            cache[(side, path)] = found
        return cache[(side, path)]

    def readers(self, path: str, name: str) -> list[str]:
        """Head files that can read a module-level name: its own, and those importing it."""
        cache = self.__dict__.setdefault("_importers", {})
        if (path, name) not in cache:
            source = self.workspace.snapshot.source
            module = PurePosixPath(path)
            stem = module.parent.name if module.stem == "__init__" else module.stem
            word = re.compile(rf"\b{re.escape(name)}\b")
            found = [path] if path in set(source.list_files(HEAD)) else []
            for other in source.list_files(HEAD):
                if other == path or not other.endswith(".py"):
                    continue
                text = source.read_text(HEAD, other)
                if name in text and any(
                    origin.rpartition(".")[2] == stem and word.search(grouped or inline)
                    for origin, grouped, inline in _IMPORT.findall(text)
                ):
                    found.append(other)
            cache[(path, name)] = found
        return cache[(path, name)]

    @cached_property
    def calls(self) -> dict:
        """Calls between definitions of one side: caller to callees."""
        graph = {BASE: {}, HEAD: {}}
        known = {BASE: set(), HEAD: set()}
        for symbol in self.workspace.facts.symbols:
            known[symbol.side].add(symbol.symbol_id)
        for fact in self.workspace.facts.facts:
            if fact.kind == FactKind.call:
                internal = [item for item in fact.target.targets if item in known[fact.side]]
                # Creating an object also runs its initializer.
                internal += [
                    item + ".__init__"
                    for item in internal
                    if item + ".__init__" in known[fact.side]
                ]
                graph[fact.side].setdefault(fact.symbol_id, set()).update(internal)
        return graph

    @cached_property
    def _called_by(self) -> dict[str, set[str]]:
        """The head call graph the other way round: a definition to those that call it."""
        found: dict[str, set[str]] = {}
        for caller, callees in self.calls[HEAD].items():
            for callee in callees:
                found.setdefault(callee, set()).add(caller)
        return found

    def _possible_entries(self, business_map: BusinessMap, placement: _Placement) -> list[dict]:
        """Functions no code calls that lead to changed code and start no flow.

        The map is drawn from the entries it knows. A way in that nothing registers in a
        form the analyzers read leaves no flow for a change to land on, so the change
        looks covered by the flows that happen to exist. These are the places to check.
        """
        workspace = self.workspace
        mapped = {entry.symbol_id for flow in business_map.flows for entry in flow.entries}
        changed: dict[str, list[str]] = {}
        for change in self.diff.changes:
            if not change.is_test:
                for symbol in placement._symbols(change):
                    changed.setdefault(symbol, []).append(change.change_id)
        leading = _closure(changed, self._called_by, REACH_DEPTH)
        found = []
        for entry in sorted(workspace.entries().values(), key=lambda item: item.symbol_id):
            if (
                entry.detection != "root_heuristic"
                or entry.symbol_id in mapped
                or entry.symbol_id not in leading
            ):
                continue
            reach = _closure([entry.symbol_id], self.calls[HEAD], REACH_DEPTH)
            ids = {item for symbol in reach & changed.keys() for item in changed[symbol]}
            found.append(
                {
                    "entry_id": entry.entry_id,
                    "symbol_id": entry.symbol_id,
                    "change_ids": [
                        change.change_id for change in self.diff.changes if change.change_id in ids
                    ],
                }
            )
        return found

    @cached_property
    def callers(self) -> dict:
        """Call facts of one side by the definition they lead to."""
        found = {BASE: {}, HEAD: {}}
        for fact in self.workspace.facts.facts:
            if fact.kind == FactKind.call:
                for target in fact.target.targets:
                    found[fact.side].setdefault(target, []).append(fact)
        return found

    @cached_property
    def base_entries(self) -> set[str]:
        return {
            entry.symbol_id
            for entry in self.workspace.facts.entries
            if entry.side == BASE and entry.detection == "adapter"
        }

    @cached_property
    def tests(self) -> dict[str, CodeTest]:
        return {item.test_id: item for item in self.workspace.facts.tests if item.side == HEAD}

    @cached_property
    def _routes(self) -> list[tuple[str | None, re.Pattern, str]]:
        """HTTP routes of the head side: method, a pattern for request paths, the handler."""
        found = []
        for entry in self.workspace.entries().values():
            path = entry.attributes.get("path") if entry.kind == "http_route" else None
            segments = [part for part in (path or "").split("/") if part]
            if not any(not _PATH_PARAMETER.match(part) for part in segments):
                continue
            pattern = "/".join(
                "[^/]+" if _PATH_PARAMETER.match(part) else re.escape(part) for part in segments
            )
            # A router may be mounted under a prefix, so the route matches as a suffix.
            found.append(
                (
                    entry.attributes.get("method"),
                    re.compile(rf"(?:^|/){pattern}/?$"),
                    entry.symbol_id,
                )
            )
        return found

    @cached_property
    def _test_calls(self) -> dict[str, set[str]]:
        """Head calls as tests make them: a request to a route path calls its handler."""
        graph = {symbol: set(targets) for symbol, targets in self.calls[HEAD].items()}
        if not self._routes:
            return graph
        test_paths = {
            item.path
            for item in self.workspace.snapshot.capture.manifest.files
            if item.side == HEAD and item.kind == "test"
        }
        for fact in self.workspace.facts.facts:
            if fact.side != HEAD or fact.kind != FactKind.call:
                continue
            if fact.symbol_id.partition("#")[0] not in test_paths:
                continue
            for method, literal in _HTTP_CALL.findall(fact.text):
                requested = re.sub(r"\{[^}]*\}", "x", literal)
                for wanted, pattern, handler in self._routes:
                    if wanted and wanted.lower() != method.lower():
                        continue
                    if pattern.search(requested):
                        graph.setdefault(fact.symbol_id, set()).add(handler)
        return graph

    @cached_property
    def _direct(self) -> dict[str, list[str]]:
        """Head tests by the definitions they call themselves, or request by route."""
        found: dict[str, list[str]] = {}
        for test_id in sorted(self.tests):
            for symbol in sorted(self._test_calls.get(self.tests[test_id].symbol_id, ())):
                found.setdefault(symbol, []).append(test_id)
        return found

    @cached_property
    def _reached(self) -> dict[str, list[str]]:
        """Head tests by the definitions they call, directly or through other calls."""
        found: dict[str, list[str]] = {}
        for test_id in sorted(self.tests):
            symbol_id = self.tests[test_id].symbol_id
            reached = _closure([symbol_id], self._test_calls, TEST_DEPTH + 1) - {symbol_id}
            for symbol in reached:
                found.setdefault(symbol, []).append(test_id)
        return found

    # ----- tests ---------------------------------------------------------------------

    def _case(self, test_id: str, related: bool) -> dict:
        test = self.tests[test_id]
        tags = ["related" if related else "agent_identified"]
        if test.assertions:
            tags.append("assertion_found")
        return {"test_id": test_id, "tags": tags, "evidence_ids": list(test.evidence_ids)}

    def _related(self, change: RawChange, symbols) -> list[str]:
        return sorted({test for symbol in symbols for test in self._reached.get(symbol, ())})

    def static_tests(self, change: RawChange, symbols) -> dict | None:
        """What the test sources alone say about a change."""
        if change.is_test:
            return None
        blank = {"basis": [], "execution_data": "not_collected"}
        if not self.tests:
            return {
                **blank,
                "verdict": "not_reached",
                "basis": ["static_fact"],
                "note": "The snapshot contains no test functions.",
            }
        if not symbols:
            return {
                **blank,
                "verdict": "unknown",
                "note": "The code no longer exists on the head side; check the tests of the "
                "code that used to call it.",
            }
        related = self._related(change, symbols)
        if not related:
            return {
                **blank,
                "verdict": "unknown",
                "note": "No test was found that calls this code or requests a route leading "
                "to it. A test may still reach it in a way static analysis does not follow.",
            }
        more = f" {len(related) - MAX_CASES} more tests are not listed." * (
            len(related) > MAX_CASES
        )
        return {
            **blank,
            "verdict": "reached_only",
            "basis": ["static_fact"],
            "note": "These tests call the changed code. Static analysis cannot tell whether "
            "their inputs take the changed path or whether they assert on its result." + more,
            "items": [self._case(test_id, True) for test_id in related[:MAX_CASES]],
        }

    def assessed_tests(self, change, symbols, verdict: ChangeAssessment) -> tuple[dict, list]:
        """An agent's coverage verdict, checked against the tests that exist."""
        static = self.static_tests(change, symbols)
        if verdict.verdict is None or static is None:
            return static, []
        named, problems = [], []
        for test_id in verdict.test_ids:
            known = test_id if test_id in self.tests else f"head::{test_id}"
            if known in self.tests:
                named.append(known)
                continue
            name = test_id.rpartition("#")[2]
            near = [key for key in sorted(self.tests) if key.endswith("#" + name)][:5]
            hint = f" Close matches: {', '.join(near)}." if near else ""
            problems.append(
                (
                    "test_ids",
                    "unknown_test",
                    f"No test {test_id} on the head side. A test id is "
                    f"`head::<path>#<function>`.{hint}",
                )
            )
        if problems:
            return static, problems
        related = self._related(change, symbols)
        named = list(dict.fromkeys(named)) or related[:MAX_CASES]
        items = [self._case(test_id, test_id in related) for test_id in named]
        basis = ["static_fact"] * any(test_id in related for test_id in named)
        result = {
            "verdict": verdict.verdict,
            "basis": [*basis, "agent_assessment"],
            "execution_data": "not_collected",
            "note": verdict.note,
            "items": items,
        }
        if verdict.verdict == "covered" and not any(
            "assertion_found" in item["tags"] for item in items
        ):
            problems.append(
                (
                    "verdict",
                    "covered_needs_assertion",
                    "covered needs a test that asserts on the result; none of the tests "
                    "named here contains an assertion. Use reached_only and say what is missing.",
                )
            )
        if verdict.verdict == "reached_only" and not items:
            problems.append(
                (
                    "test_ids",
                    "reached_only_needs_test",
                    "reached_only needs at least one test that reaches the change; name it in "
                    "`test_ids`, or use not_reached.",
                )
            )
        if verdict.verdict == "not_reached":
            # A test that calls the changed function itself reaches it. One that only gets
            # there through other calls may be cut off by a stub, which the agent can judge.
            direct = sorted({test for symbol in symbols for test in self._direct.get(symbol, ())})
            if direct:
                problems.append(
                    (
                        "verdict",
                        "tests_reach_change",
                        "These tests call the changed code themselves: "
                        + ", ".join(direct[:5])
                        + ". Use reached_only and say what they miss.",
                    )
                )
            elif verdict.test_ids:
                problems.append(
                    (
                        "test_ids",
                        "not_reached_lists_tests",
                        "not_reached means no test reaches the change, so it names none. "
                        "Describe near misses, such as tests that replace the changed function "
                        "with a stub, in `note`.",
                    )
                )
            result.update(basis=["agent_assessment"], items=[])
        return result, problems

    # ----- stored assessments --------------------------------------------------------

    @property
    def _store(self):
        return self.workspace.root / "changes" / "accepted.json"

    def assessments(self) -> dict[str, dict]:
        if not self._store.is_file():
            return {}
        return json.loads(self._store.read_text(encoding="utf-8"))["assessments"]

    # ----- report --------------------------------------------------------------------

    def _unanalyzed(self) -> tuple[list[dict], list[dict]]:
        """Changed files no analyzer covered, and the limitations that follow from them."""
        files = {(item.side, item.path): item for item in self.workspace.facts.files}
        listed, limits, broken = [], [], []
        for delta in self.workspace.snapshot.capture.file_diff.changes:
            change = delta.change
            path = change.head_path or change.base_path
            sides = [
                files.get((side, name))
                for side, name in ((BASE, change.base_path), (HEAD, change.head_path))
                if name is not None
            ]
            failed = next((item for item in sides if item and item.status == "unsupported"), None)
            if failed is not None:
                reason = f"Could not be analyzed: {failed.reason}"
                broken.append(path)
            elif not any(sides):
                reason = "Configuration file; not analyzed for behaviour."
            else:
                continue
            listed.append({"path": path, "change": change.change_type, "reason": _short(reason)})
        listing = self.workspace.root / "changed-files.json"
        outside = {"total": 0, "files": []}
        if listing.is_file():
            outside = json.loads(listing.read_text(encoding="utf-8"))
        others = outside["files"]
        listed += [
            {**item, "reason": "Not a supported source language; not analyzed."} for item in others
        ]
        if broken:
            limits.append(
                {
                    "code": "changed_file_not_analyzed",
                    "message": "Changed source files could not be analyzed: "
                    + ", ".join(broken[:5])
                    + ".",
                    "affects_completeness": True,
                }
            )
        total = outside["total"]
        if total:
            limits.append(
                {
                    "code": "changed_files_outside_languages",
                    "message": f"{total} changed file{'s' * (total != 1)} outside the supported "
                    "languages: not analyzed.",
                    "affects_completeness": False,
                }
            )
        return listed[:MAX_UNANALYZED], limits

    def _removed_flows(self, business_map: BusinessMap) -> tuple[list[dict], set[str]]:
        """Skeletons of entries that exist only on the base side."""
        facts = self.workspace.facts
        kept = {entry.symbol_id for entry in facts.entries if entry.side == HEAD}
        present = {flow.flow_id for flow in business_map.flows}
        shown = shown_facts(facts, BASE)
        flows, cited = [], set()
        for entry in sorted(facts.entries, key=lambda item: item.symbol_id):
            symbol = self.diff.moved.get(entry.symbol_id, entry.symbol_id)
            if entry.side != BASE or entry.detection != "adapter" or symbol in kept:
                continue
            flow, evidence = skeleton_flow([entry], shown)
            if flow["flow_id"] in present or len(flows) >= MAX_REMOVED_FLOWS:
                continue
            flows.append(flow)
            cited |= evidence
        return flows, cited

    def build(self, business_map: BusinessMap) -> ChangeReport:
        return self._build(business_map, _Placement(self, business_map))

    def build_with_closest(self, business_map: BusinessMap) -> tuple[ChangeReport, dict]:
        """The report, and the changes still to be expanded by the flow closest to each."""
        placement = _Placement(self, business_map)
        report = self._build(business_map, placement)
        return report, self._closest(report, placement)

    def _closest(self, report: ChangeReport, placement: _Placement) -> dict[str, list[str]]:
        """Changes whose function no flow has expanded yet, by the flow closest to each.

        Such a change has no place, or sits on a step that merely calls its function.
        Flows that share the function would each have to expand it to carry the change.
        One is enough, and which one should not depend on the flow described first.
        """
        raw = {change.change_id: change for change in self.diff.changes}
        reached = {key for item in report.possibly_affected for key in item.change_ids}
        found: dict[str, list[str]] = {}
        for item in report.changes:
            place = item.projection
            if place.reason == CALLS or (
                place.status == "unassigned" and item.change_id in reached
            ):
                flow = placement.closest(raw[item.change_id])
                if flow is not None:
                    found.setdefault(flow, []).append(item.change_id)
        return found

    def for_flow(self, business_map: BusinessMap, flow_id: str) -> dict:
        """The changes as one flow task has to see them."""
        placement = _Placement(self, business_map)
        report = self._build(business_map, placement)
        closest = self._closest(report, placement)
        # The flow that describes each change, or is the one to do so.
        carried = {key: flow for flow, keys in closest.items() for key in keys}
        here: dict[str, list] = {}
        for item in report.changes:
            if item.projection.flow_id:
                carried.setdefault(item.change_id, item.projection.flow_id)
            here[item.change_id] = [
                target
                for target in (item.projection, *item.other_projections)
                if target.flow_id == flow_id
            ]
        # What this flow gets to without describing it: by its calls, or on a calling step.
        reached = {
            key
            for item in report.possibly_affected
            if item.flow_id == flow_id
            for key in item.change_ids
        } | {key for key, targets in here.items() if any(t.reason == CALLS for t in targets)}
        # The function to anchor a step in for each change this flow is to bring onto
        # the map: the one the change is in, or the nearest one that reads what it defines.
        raw = {change.change_id: change for change in self.diff.changes}
        calls = placement.calls_to.get(flow_id, {})
        inside: dict[str, list[str]] = {}
        for key in closest.get(flow_id, []):
            symbols = [symbol for symbol in placement._symbols(raw[key]) if symbol in calls]
            if symbols:
                nearest = min(symbols, key=lambda symbol: (calls[symbol], symbol))
                inside.setdefault(nearest, []).append(key)
        return {
            "placed": [key for key, targets in here.items() if targets],
            "closest_to": closest.get(flow_id, []),
            "expand": [
                {"symbol_id": symbol, "changes": inside[symbol]}
                for symbol in sorted(inside, key=lambda symbol: (calls[symbol], symbol))
            ],
            "on_other_flows": [
                {"flow": flow.name, "changes": keys}
                for flow in business_map.flows
                if flow.flow_id != flow_id
                and (
                    keys := [
                        key for key in here if key in reached and carried.get(key) == flow.flow_id
                    ]
                )
            ],
        }

    def _build(self, business_map: BusinessMap, placement: _Placement) -> ChangeReport:
        workspace, diff = self.workspace, self.diff
        assessments = self.assessments()
        flows = {flow.flow_id: flow for flow in business_map.flows}
        step_of_finding = {
            finding_id: (flow.flow_id, step.step_id)
            for flow in business_map.flows
            for step in flow.steps
            for finding_id in step.finding_ids
        }
        cited: set[str] = set()
        items, affected, touched, finding_status = [], {}, set(), {}
        for change in diff.changes:
            targets, reaching = placement.place(change)
            for flow_id in sorted(reaching):
                affected.setdefault(flow_id, []).append(change.change_id)
            touched.update(target["flow_id"] for target in targets if target.get("flow_id"))
            item = {
                "change_id": change.change_id,
                "kind": change.kind.value,
                "symbol_id": change.symbol_id,
                "projection": targets[0],
                "other_projections": targets[1:],
            }
            for name, part in (("before", change.before), ("after", change.after)):
                if part is not None:
                    item[name] = {
                        "side": part.side.value,
                        "text": part.text,
                        "anchor": part.anchor,
                        "evidence_ids": list(part.evidence_ids),
                    }
                    cited.update(part.evidence_ids)
            if change.details:
                item["detail"] = _short(" ".join(change.details), 2000)
            symbols = placement._symbols(change)
            stored = assessments.get(change.change_id)
            if stored is None:
                tests = self.static_tests(change, symbols)
            else:
                verdict = ChangeAssessment.model_validate(stored)
                tests, _ = self.assessed_tests(change, symbols, verdict)
                item["explanation"] = {"summary": verdict.summary}
                if verdict.short_summary:
                    item["explanation"]["short_summary"] = verdict.short_summary
                if verdict.effect:
                    item["explanation"]["effect"] = verdict.effect
            if tests is not None:
                item["tests"] = tests
                cited.update(ref for case in tests.get("items", ()) for ref in case["evidence_ids"])
            if change.after is not None:
                found = []
                for finding in business_map.findings:
                    refs = [workspace.evidence(ref) for ref in finding.evidence_ids]
                    if any(
                        ref.path == change.after.path
                        and ref.range.start_line <= change.after.end[0]
                        and change.after.start[0] <= ref.range.end_line
                        for ref in refs
                    ):
                        found.append(finding.finding_id)
                        introduced = change.kind in _ADDED_KINDS
                        if introduced or finding.finding_id not in finding_status:
                            finding_status[finding.finding_id] = (
                                "introduced" if introduced else "persisting"
                            )
                if found:
                    item["finding_ids"] = found
            items.append(item)
        # Everything in a flow whose entry was added came with this change.
        added = {
            symbol
            for change in diff.changes
            if change.kind == ChangeKind.symbol_added
            for symbol in change.head_symbols
        }
        for flow in business_map.flows:
            if all(entry.symbol_id in added for entry in flow.entries):
                for step in flow.steps:
                    finding_status.update(dict.fromkeys(step.finding_ids, "introduced"))
        finding_changes = []
        for finding in business_map.findings:
            if finding.finding_id in finding_status:
                where = step_of_finding.get(finding.finding_id)
                entry = {
                    "status": finding_status[finding.finding_id],
                    "finding": finding.model_dump(mode="json", exclude_none=True),
                }
                if where:
                    entry.update(flow_id=where[0], step_id=where[1])
                finding_changes.append(entry)
                cited.update(finding.evidence_ids)
        removed_flows, removed_refs = self._removed_flows(business_map)
        cited |= removed_refs
        unanalyzed, limitations = self._unanalyzed()
        waiting = [flows[key].name for key in sorted(touched) if flows[key].stage == "skeleton"]
        if waiting:
            limitations.append(
                {
                    "code": "affected_flow_not_synthesized",
                    "message": "Changes are placed on flows that are still a static skeleton: "
                    + ", ".join(waiting[:5])
                    + ".",
                    "affects_completeness": True,
                }
            )
        if diff.truncated:
            limitations.append(
                {
                    "code": "changes_truncated",
                    "message": f"More changes were found than the {len(diff.changes)} listed.",
                    "affects_completeness": True,
                }
            )
        if diff.skipped_files:
            limitations.append(
                {
                    "code": "source_comparison_skipped",
                    "message": "Too large to compare line by line: "
                    + ", ".join(diff.skipped_files[:5])
                    + ".",
                    "affects_completeness": True,
                }
            )
        limitations.append(
            {
                "code": "no_execution_data",
                "message": "No test was run and no coverage data was imported; test verdicts "
                "come from reading source.",
                "affects_completeness": False,
            }
        )
        session = workspace.session
        document = {
            "snapshot_id": business_map.snapshot_id,
            "base_ref": session.get("base_ref"),
            "base_revision": session.get("base_revision"),
            "head_ref": session.get("head_ref"),
            "head_revision": session.get("head_revision"),
            "changes": items,
            "removed_flows": removed_flows,
            "possibly_affected": [
                {
                    "flow_id": flow_id,
                    "change_ids": change_ids,
                    "reason": "Reaches the changed code through calls, but no step of this "
                    "flow is anchored on it.",
                }
                for flow_id, change_ids in sorted(affected.items())
            ],
            "possible_entries": self._possible_entries(business_map, placement),
            "unanalyzed_changes": unanalyzed,
            "finding_changes": finding_changes,
            "limitations": limitations,
            "evidence": [
                (workspace.evidence(key) or diff.evidence[key]).model_dump(mode="json")
                for key in sorted(cited)
            ],
        }
        try:
            report = ChangeReport.model_validate({**document, "analysis_status": "complete"})
        except ValidationError:
            report = ChangeReport.model_validate({**document, "analysis_status": "partial"})
        validate_change_report_against_map(report, business_map)
        return report

    # ----- the change task -----------------------------------------------------------

    def _side(self, part) -> dict | None:
        if part is None:
            return None
        return {
            "text": part.text,
            "path": part.path,
            "start_line": part.start[0],
            "end_line": part.end[0],
            "evidence_id": part.evidence_ids[0],
        }

    def _views(self, items, business_map: BusinessMap, *, for_task: bool = True) -> list[dict]:
        """Changes as an agent or a script reads them: both sides, the place, the tests.

        For the change task a view carries the last accepted assessment as `previous`;
        the plain listing shows the accepted explanation instead.
        """
        assessments = self.assessments()
        raw = {change.change_id: change for change in self.diff.changes}
        flows = {flow.flow_id: flow for flow in business_map.flows}
        steps = {step.step_id: step.name for flow in business_map.flows for step in flow.steps}

        def place(target) -> dict:
            removed = target.removed_step.name if target.removed_step else None
            return {
                "status": target.status.value,
                "flow": flows[target.flow_id].name if target.flow_id else None,
                "step": steps.get(target.step_id) if target.step_id else removed,
                "reason": target.reason,
            }

        views = []
        for item in items:
            change = raw[item.change_id]
            view = {
                "change_id": item.change_id,
                "kind": item.kind.value,
                "symbol_id": item.symbol_id,
                "before": self._side(change.before),
                "after": self._side(change.after),
                "placement": place(item.projection),
            }
            if for_task:
                view["previous"] = assessments.get(item.change_id)
            else:
                view["explanation"] = (
                    item.explanation.model_dump(mode="json", exclude={"support"}, exclude_none=True)
                    if item.explanation
                    else None
                )
            if item.other_projections:
                view["also_placed"] = [place(target) for target in item.other_projections]
            if item.detail:
                view["detail"] = item.detail
            if item.tests is not None:
                view["tests"] = {
                    "verdict": item.tests.verdict.value,
                    "basis": [value.value for value in item.tests.basis],
                    "note": item.tests.note,
                    "tests": [
                        {
                            "test_id": case.test_id,
                            "evidence_id": case.evidence_ids[0],
                            "assertions": list(self.tests[case.test_id].assertions[:5]),
                        }
                        for case in item.tests.items
                    ],
                }
            views.append(view)
        return views

    def context(self, business_map: BusinessMap) -> dict:
        """The changes still to explain, with both sides and the tests that reach them."""
        report = self.build(business_map)
        assessments = self.assessments()
        placed = [item for item in report.changes if item.projection.status != "unassigned"]
        waiting = [item for item in report.owed() if item.change_id not in assessments]
        shown = (waiting or report.changes)[:CONTEXT_LIMIT]
        return {
            "task_id": CHANGE_TASK,
            "kind": "change",
            "state": "pending" if waiting else "validated",
            "analysis_status": report.analysis_status,
            "changes_total": len(report.changes),
            "changes_placed": len(placed),
            "changes_waiting": len(waiting),
            # Up to this many per call; submit them and ask again for the rest.
            "changes_listed": len(shown),
            "changes": self._views(shown, business_map),
            "tests_total": len(self.tests),
            "rules": list(RULES),
        }

    def summary(self, business_map: BusinessMap) -> dict:
        """The whole change report in a compact form, readable without an agent."""
        placement = _Placement(self, business_map)
        report = self._build(business_map, placement)
        closest = self._closest(report, placement)
        flows = {flow.flow_id: flow.name for flow in business_map.flows}
        placed = [item for item in report.changes if item.projection.status != "unassigned"]
        return {
            "analysis_status": report.analysis_status,
            "changes_total": len(report.changes),
            "changes_placed": len(placed),
            "changes_waiting": sum(1 for item in report.owed() if item.explanation is None),
            "changes": self._views(report.changes, business_map, for_task=False),
            "possibly_affected": [
                {"flow": flows[item.flow_id], "changes": list(item.change_ids)}
                for item in report.possibly_affected
            ],
            # Changes whose function no flow has expanded yet, under the one flow that
            # reaches each through the fewest calls: the flow to describe that code on.
            "closest_flow": [
                {"flow": flow.name, "changes": closest[flow.flow_id]}
                for flow in business_map.flows
                if flow.flow_id in closest
            ],
            # Uncalled functions that lead to the changes and have no flow.
            "possible_entries": [item.symbol_id for item in report.possible_entries],
            "removed_flows": [flow.name for flow in report.removed_flows],
            # Observations an agent recorded on the map, as far as this change touches them.
            "risk_findings": [
                {
                    "status": item.status,
                    "source": item.finding.source.value,
                    "statement": item.finding.statement,
                }
                for item in report.finding_changes
            ],
            "unanalyzed_changes": [
                item.model_dump(mode="json") for item in report.unanalyzed_changes
            ],
            "limitations": [
                {
                    "code": item.code,
                    "message": item.message,
                    "blocks_complete": item.affects_completeness,
                }
                for item in report.limitations
            ],
        }

    def check(self, raw) -> tuple[dict[str, dict], list[tuple[str, str, str]]]:
        """Validate a submission. Returns the assessments to store, or the problems."""
        submission = ChangeSubmission.model_validate(raw)
        known = {change.change_id: change for change in self.diff.changes}
        placement = _Placement(self, self.workspace.stored_map())
        accepted, problems = {}, []
        for index, item in enumerate(submission.changes):
            where = f"changes[{index}]"
            change = known.get(item.change_id)
            if change is None:
                problems.append(
                    (where + ".change_id", "unknown_change", f"No change {item.change_id}.")
                )
                continue
            if change.is_test and item.verdict is not None:
                problems.append(
                    (
                        where + ".verdict",
                        "verdict_on_test",
                        "A change to a test carries no coverage verdict of itself.",
                    )
                )
                continue
            _, found = self.assessed_tests(change, placement._symbols(change), item)
            problems += [(f"{where}.{field}", code, message) for field, code, message in found]
            accepted[item.change_id] = item.model_dump(mode="json", exclude_none=True)
        return accepted, problems

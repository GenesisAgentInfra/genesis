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
from collections import Counter
from functools import cached_property
from pathlib import PurePosixPath

from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import (
    ChangeKind,
    ChangeReport,
    validate_change_report_against_map,
)
from genesis_contracts.facts import CodeEntry, CodeFact, CodeTest, FactKind
from genesis_contracts.map_tasks import ChangeAssessment, ChangeSubmission
from pydantic import ValidationError

from .carried import read_carried
from .fact_diff import BASE, HEAD, FactDiff, RawChange, _innermost, diff_facts
from .loop import CHANGE_TASK
from .python_entries import entry_id
from .python_facts import canonical_python
from .skeleton import _evaluation_order, _short, shown_facts, skeleton_flow
from .store import left_out_limitation, untracked_folders_limitation

CONTEXT_LIMIT = 30
# How many possible entries `status` and `diff` list at a time.
POSSIBLE_ENTRY_LIMIT = 20
REACH_DEPTH = 6
TEST_DEPTH = 4
MAX_PROJECTIONS = 6
MAX_CASES = 20
MAX_REMOVED_FLOWS = 20
MAX_UNANALYZED = 100
# How many changed functions the unchanged callers are listed for, and how many
# callers each: enough to read in the risk pass, not a call graph.
CALLER_SYMBOLS = 15
CALLERS_SHOWN = 3
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
# The reason the facts give a function handed to another call, and an argparse subparser.
_HANDED = "Handed to "
_SUBCOMMAND = re.compile(r"\.add_parser\(\s*[\"']([^\"']+)[\"']")
NO_ENTRY = "No entry on the map reaches this code through calls static analysis resolved."
UNRESOLVED = (
    "No resolved call leads here from an entry on the map; {count} that could not be "
    "resolved may lead here, such as {example}."
)
# Why a call into this code base's own modules could not be resolved, as the resolver
# words it. A receiver of unknown type is dynamic by nature and is not among these.
_LOCAL_FAILURES = (
    "Target is absent from captured module",
    "Local module member is not captured",
    "Ambiguous module across source roots",
    "Captured or omitted local module was not analyzed",
    "Imported module has dynamic namespace mutation",
    "Relative import escapes configured package roots",
    "Cyclic re-export or import alias",
    "Captured namespace package may shadow this external import",
)
# Problems that concern the tests an explanation names, whichever change it is about.
_ABOUT_THE_TESTS = {"unknown_test", "covered_names_tests"}
RULES = (
    "`before` and `after` are the frozen text of each side: read both before explaining a "
    "change. A side marked `excerpt` is shorter than its lines (a definition's header, a "
    "block cut at 800 characters, a statement put on one line): read it in full with "
    "`genesis map read --session <id> --evidence <id>`. For the code around a change, read the files at the "
    "two revisions of the session or a diff between them; when the head side is the working "
    "tree, check what you quote against the frozen text.",
    "`summary` says in business terms what is different; `effect` says what that means for "
    "the flow. Do not describe line edits.",
    "Give a `verdict` only after reading the listed tests. A verdict answers one question: "
    "would a test fail if the change were undone? covered: a test runs the changed code "
    "and would fail if the change were undone; name it in `test_ids`. reached_only: tests "
    "run the code but would not fail if the change were undone, because their input misses "
    "the changed path or they check nothing it affects; say what is missing in `note`. "
    "not_reached: no test reaches it. unknown: you could not tell; say why.",
    "A statement that runs on every call, such as an added argument or assignment, is "
    "covered by a test that runs the code and would fail without it. An input value no "
    "test uses is not a missed path.",
    "An added definition is judged as a whole: covered when a test runs it and would fail "
    "without it. Name in `note` the branches no test takes; they do not make it reached_only.",
    "A test counts when the project's default test command runs it. Tests skipped by "
    "default do not count: a skip mark, a skipif whose condition holds in a normal run (such "
    "as a missing environment variable or credential), a marker the default configuration "
    "deselects. Name them in `note` and judge by the other tests. Needing the network or a "
    "model download does not by itself exclude a test; you may say so in `note`.",
    "For a change that replaces code (both sides present), undoing it puts the `before` side "
    "back: take the test's input through the `before` side. When the old code gives the same "
    "outcome for that input (the same exception, the same value, the same call), the test "
    "still passes and does not make the change covered; a test that checks only an "
    "exception type or a field name often passes on both sides. covered needs a test whose "
    "input gets a different outcome on the two sides.",
    "For removed code, the changed path is the input the removed code used to handle. "
    "covered: a test gives such an input and would fail if the removed code were put back. "
    "reached_only: tests run the function but never with such an input. Code that replaces "
    "it is a change of its own: do not copy the verdict from one to the other. The same "
    "holds when another function now does what the removed code did: the input still has "
    "to go through the function the code was removed from. A test that calls only the "
    "other function is a near miss: describe it in `note`.",
    "One `source_*` change can hold several values, such as two limits set on neighbouring "
    "lines of a function. covered needs, for each value, a test that would fail if that "
    "value were undone. When only some have one, use reached_only and name the others in "
    "`note`.",
    "`test_ids` names the tests your verdict rests on; the tests static analysis linked "
    "stay listed after them. You may name a test static analysis did not link, for example "
    "one that goes through an HTTP client.",
    "A verdict answers only whether a test would fail. What the tests leave unchecked goes "
    "in its `note`, not into `risks`.",
    "No test was run. Never state that a test passed or that a path executed.",
    "Leave `verdict` out to keep the static result shown under `tests`: it reads as called "
    "by tests, not assessed.",
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


def checked(item) -> bool:
    """Whether a possible entry was looked at: left out of the plan for any reason but budget."""
    return item.skipped is not None and item.skipped != "budget"


def unchecked_entries(report: ChangeReport) -> dict:
    """The possible entries still to check, as `status` and `diff` both list them.

    One the plan left out for a reason other than budget has been checked: the report
    keeps it, and it is no longer listed. Each item has the `entry_id` a plan skips or uses it by and
    the `symbol_id` a plan proposes it by.
    """
    undecided = [item for item in report.possible_entries if not checked(item)]
    return {
        "possible_entries": [
            item.model_dump(mode="json", exclude_none=True)
            for item in undecided[:POSSIBLE_ENTRY_LIMIT]
        ],
        "possible_entries_total": len(undecided),
    }


def _bound(targets) -> list[str]:
    """The plain names an assignment binds, also inside tuples and lists."""
    found = []
    for target in targets:
        if isinstance(target, ast.Name):
            found.append(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            found += _bound(target.elts)
        elif isinstance(target, ast.Starred):
            found += _bound([target.value])
    return found


def _assigned(nodes) -> list[tuple[int, int, tuple[str, ...]]]:
    """The assignments among `nodes` that bind plain names: first line, last line, names."""
    found = []
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        else:
            continue
        names = tuple(dict.fromkeys(_bound(targets)))
        if names:
            found.append((node.lineno, node.end_lineno or node.lineno, names))
    return found


class _ModuleScope(ast.NodeVisitor):
    """Names a module binds, and names it reads while it is imported.

    Function bodies run later and are skipped; decorators, defaults, annotations, base
    classes and class bodies run at import and count.
    """

    def __init__(self):
        self.bound: Counter = Counter()
        self.read: set[str] = set()
        # Names read inside functions, which run at import only when something is called.
        self.read_later: set[str] = set()
        self.calls = False
        self.star = False
        self.classes = 0

    def _bind(self, name: str) -> None:
        if not self.classes:
            self.bound[name] += 1

    def _later(self, nodes) -> None:
        """Code that runs when a function is called: what it reads and rebinds."""
        for node in nodes:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                    self.read_later.add(inner.id)
                elif isinstance(inner, ast.Global):
                    for name in inner.names:
                        self.bound[name] += 1

    def visit_FunctionDef(self, node) -> None:
        self._bind(node.name)
        for item in node.decorator_list:
            self.visit(item)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._later(node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node) -> None:
        self.visit(node.args)
        self._later([node.body])

    def visit_Call(self, node) -> None:
        self.calls = True
        self.generic_visit(node)

    def visit_ExceptHandler(self, node) -> None:
        if node.name:
            self._bind(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node) -> None:
        if node.name:
            self._bind(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node) -> None:
        if node.name:
            self._bind(node.name)

    def visit_MatchMapping(self, node) -> None:
        if node.rest:
            self._bind(node.rest)
        self.generic_visit(node)

    def visit_ClassDef(self, node) -> None:
        self._bind(node.name)
        for item in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(item)
        self.classes += 1
        for item in node.body:
            self.visit(item)
        self.classes -= 1

    def visit_Name(self, node) -> None:
        if isinstance(node.ctx, ast.Load):
            self.read.add(node.id)
        else:
            self._bind(node.id)

    def visit_Import(self, node) -> None:
        for alias in node.names:
            self._bind((alias.asname or alias.name).partition(".")[0])

    def visit_ImportFrom(self, node) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.star = True
            else:
                self._bind(alias.asname or alias.name)


def _order_free(node, bound) -> bool:
    """Whether an assignment gives the same result wherever it stands in its module.

    It binds plain names, and its value calls nothing and reads no name the module binds.
    """
    if not isinstance(node, ast.Assign):
        return False
    for target in node.targets:
        for part in ast.walk(target):
            if isinstance(part, ast.Attribute | ast.Subscript):
                return False
    for part in ast.walk(node.value):
        if isinstance(part, ast.Call | ast.Await | ast.Yield | ast.YieldFrom | ast.NamedExpr):
            return False
        if isinstance(part, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp):
            return False
        if isinstance(part, ast.GeneratorExp):
            return False
        if isinstance(part, ast.Name) and part.id in bound:
            return False
    return True


def _lines(text: str) -> list[str]:
    """The non-blank lines of a text, stripped: what a side shows, line by line."""
    return [line.strip() for line in text.split("\n") if line.strip()]


def _terminal(statements) -> bool:
    """Whether a list of statements always leaves by `return` or `raise`."""
    if not statements:
        return False
    last = statements[-1]
    if isinstance(last, ast.Return | ast.Raise):
        return True
    if isinstance(last, ast.If):
        return _terminal(last.body) and _terminal(last.orelse)
    return False


def _shadowed(node) -> set[str]:
    """The names a function, lambda or comprehension binds for itself."""
    found = set()
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
        arguments = node.args
        every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        every += [item for item in (arguments.vararg, arguments.kwarg) if item]
        found |= {item.arg for item in every}
        declared = set()
        body = node.body if isinstance(node.body, list) else [node.body]
        for statement in body:
            for inner in ast.walk(statement):
                if isinstance(inner, ast.Global | ast.Nonlocal):
                    declared |= set(inner.names)
                elif isinstance(inner, ast.Name) and not isinstance(inner.ctx, ast.Load):
                    found.add(inner.id)
        found -= declared
    elif isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
        for generator in node.generators:
            for inner in ast.walk(generator.target):
                if isinstance(inner, ast.Name):
                    found.add(inner.id)
    return found


def _loads(tree, holder):
    """Each load of a plain name inside one function, with whether it sits in a function
    written inside it and the line ranges of the loops around it."""
    if tree is None:
        return
    name = holder.symbol_id.rpartition("#")[2].rpartition(".")[2]
    first, last = holder.range.start_line, holder.range.end_line
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    found = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, functions)
            and node.name == name
            and first <= node.lineno <= (node.end_lineno or node.lineno) <= last
        ),
        None,
    )
    if found is None:
        return

    scopes = (*functions, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

    def walk(node, inner, loops, hidden):
        children = list(ast.iter_child_nodes(node))
        if isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
            # The first iterable is read where the comprehension stands, outside it.
            first = node.generators[0].iter
            yield from walk_one(first, inner, loops, hidden - _shadowed(node))
            children = [child for child in children if child is not node.generators[0]]
            children += [
                part for part in ast.iter_child_nodes(node.generators[0]) if part is not first
            ]
        for child in children:
            yield from walk_one(child, inner, loops, hidden)

    def walk_one(child, inner, loops, hidden):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            if child.id not in hidden:
                yield child, inner, loops
            return
        if isinstance(child, scopes):
            hidden = hidden | _shadowed(child)
        deeper = inner or isinstance(child, (*functions, ast.Lambda))
        around = loops
        if isinstance(child, ast.For | ast.AsyncFor | ast.While):
            around = (*loops, (child.lineno, child.end_lineno or child.lineno))
        yield from walk(child, deeper, around, hidden)

    yield from walk(found, False, (), frozenset())


def _exit_after(tree, holder, line: int) -> int | None:
    """The last line from which code after it can no longer see an assignment on `line`.

    When the assignment sits in a block that always ends in `return` or `raise`, code
    after that block runs only when the block did not, so it reads another value.
    """
    if tree is None:
        return None
    name = holder.symbol_id.rpartition("#")[2].rpartition(".")[2]
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
            and holder.range.start_line <= node.lineno <= holder.range.end_line
        ),
        None,
    )
    if function is None:
        return None
    ends = []
    for node in ast.walk(function):
        for field in ("body", "orelse", "finalbody", "handlers"):
            block = getattr(node, field, None)
            if node is function or not isinstance(block, list) or not block:
                continue
            statements = [item for item in block if isinstance(item, ast.stmt)]
            if not statements:
                continue
            start = statements[0].lineno
            end = statements[-1].end_lineno or statements[-1].lineno
            if start <= line <= end and _terminal(statements):
                ends.append(end)
    return min(ends, default=None)


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
        # Changes no resolved call leads to: how many unresolved calls may lead to each.
        self.unresolved: dict[str, int] = {}
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
            own = () if change.module_level else (change.symbol_id,)
            return tuple(dict.fromkeys((*users, *own)))
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
        """Names a change defines, or sits inside the definition of.

        A word added to a set that runs over several lines, or a sentence changed in a
        long string, does not show the name it belongs to. The assignment around it does.
        Inside a function only an added or modified source line counts: a changed
        condition, call or block is placed by its own facts.
        """
        if change.is_test:
            return ()
        # A function's own name is followed only while the assignment is still there:
        # once it is removed, the code that reads the name reads another definition.
        if not change.module_level and (
            change.kind not in _SOURCE_KINDS or change.after is None or self._holder(change) is None
        ):
            return ()
        part = change.after or change.before
        found = _ASSIGNED.findall(part.text) if change.kind in _SOURCE_KINDS else []
        assigned = self.analysis.assignments(part.side, part.path, local=not change.module_level)
        for first, last, names in assigned:
            if first <= part.end[0] and part.start[0] <= last:
                found += names
        return tuple(dict.fromkeys(found))

    def _holder(self, change: RawChange):
        """The head function a change is written inside, when it is inside one."""
        symbol = self.analysis.workspace.symbols.get(change.symbol_id)
        return symbol if symbol is not None and symbol.kind == "function" else None

    def _reading(self, change: RawChange) -> tuple[list, list]:
        """Where head code reads a name the change defines: by facts, and by lines."""
        cache = self.__dict__.setdefault("_read", {})
        if change.change_id not in cache:
            analysis, part = self.analysis, change.after or change.before
            facts, lines = [], []
            names = self._names(change)
            if names and not change.module_level:
                facts, lines = self._reading_inside(change, names)
                names = ()
            for name in names:
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

    def _reading_inside(self, change: RawChange, names) -> tuple[list, list]:
        """Where a function reads a name it assigns itself: by facts, and by lines.

        The name is the function's own, so only its body counts, with the functions
        written inside it. A line reads the name where the code loads it, not where the
        word stands in a string or a key. It sees this assignment when it comes after
        it, sits in a function written inside, or sits in a loop around the assignment.
        """
        analysis, part = self.analysis, change.after
        holder = self._holder(change)
        nested = holder.symbol_id + "."
        functions = [
            item
            for item in analysis.symbols_in(HEAD, holder.path)
            if item.kind == "function"
            and (item.symbol_id == holder.symbol_id or item.symbol_id.startswith(nested))
        ]
        own = {item.symbol_id for item in functions}
        first, last = part.start[0], part.end[0]
        tree = analysis.tree(HEAD, holder.path)
        stop = _exit_after(tree, holder, first)
        loads = []
        for node, inner, loops in _loads(tree, holder):
            line = node.lineno
            if first <= line <= last or (stop is not None and line > stop and not inner):
                continue
            if line > last or inner or any(start <= first and last <= end for start, end in loops):
                loads.append((node.id, line))
        facts, lines = [], []
        for name in names:
            seen = sorted({line for found, line in loads if found == name})
            facts += [
                (name, fact)
                for fact in analysis.facts_in(HEAD, holder.path)
                if fact.symbol_id in own
                and any(fact.range.start_line <= line <= fact.range.end_line for line in seen)
            ]
            for line in seen:
                reader = _innermost(functions, line)
                if reader is not None:
                    lines.append((name, reader.symbol_id, line))
        return facts, lines

    def _users(self, change: RawChange) -> list[tuple[str, CodeFact]]:
        """Head facts that refer to a name a change defines."""
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
            # The step is shown on a flow that already draws the code that called it, or
            # else on the one that calls it most directly, as `closest` picks a flow for
            # shared code; the others only reached it.
            drawn = {spot[1] for caller in callers for spot in self.in_symbol.get(caller, ())}
            ranked = sorted(
                (
                    flow not in drawn,
                    min(calls[caller] for caller in callers & calls.keys()),
                    self.first_entry[flow],
                    flow,
                )
                for flow, calls in self.calls_to.items()
                if callers & calls.keys()
            )
            if ranked:
                removed = {
                    "step_id": "step_" + change.before.anchor[3:19],
                    "name": _short(change.before.text.splitlines()[-1], 200),
                }
                nearest = ranked[0][-1]
                return [{"status": "removed_step", "flow_id": nearest, "removed_step": removed}], {
                    row[-1] for row in ranked[1:]
                }
        if reaching:
            return [
                _unassigned(
                    "No step on the map covers this code; flows that can reach it are listed "
                    "as possibly affected."
                )
            ], reaching
        # No resolved call leads here. That is not the same as no call at all.
        might = analysis.unresolved_into(symbols)
        if might:
            self.unresolved[change.change_id] = len(might)
            count = f"{len(might)} call{'s' * (len(might) != 1)}"
            return [_unassigned(UNRESOLVED.format(count=count, example=_where(might[0])))], set()
        return [_unassigned(NO_ENTRY)], set()


_LANDING = {FactKind.breaks, FactKind.continues, FactKind.returns}
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module, ast.Lambda)


def _landing(tree: ast.Module | None, lines: list[str], kind: FactKind, line: int) -> dict | None:
    """The statement a `break` or `continue` on `line` leads to: its line and text."""
    if tree is None:
        return None
    parents: dict[int, ast.AST] = {}
    jump = None
    wanted = ast.Break if kind == FactKind.breaks else ast.Continue
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
        if isinstance(node, wanted) and node.lineno == line:
            jump = node
    loop = parents.get(id(jump)) if jump is not None else None
    while loop is not None and not isinstance(loop, (*_LOOPS, *_SCOPES)):
        loop = parents.get(id(loop))
    if not isinstance(loop, _LOOPS):
        return None

    def at(node) -> dict:
        return {"line": node.lineno, "text": _short(lines[node.lineno - 1].strip(), 120)}

    if kind == FactKind.continues:
        return at(loop)
    # After the loop: the statement that follows it, or, when it ends a block, whatever
    # follows that block. An outer loop goes round again; the end of a function returns.
    node = loop
    while True:
        parent = parents.get(id(node))
        if parent is None:
            return None
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list) and node in block:
                index = block.index(node)
                if index + 1 < len(block):
                    return at(block[index + 1])
                if isinstance(parent, _LOOPS) and field == "body":
                    return at(parent)
                break
        if isinstance(parent, _SCOPES):
            return {"line": node.end_lineno, "text": "the end of the function: it returns"}
        node = parent


def _callee(text: str) -> str | None:
    """The name a call calls: the last name before its arguments."""
    names = re.findall(r"[A-Za-z_]\w*", text.split("(", 1)[0])
    return names[-1] if names else None


def _where(fact: CodeFact) -> str:
    return (
        f"`{_short(fact.text, 80)}` in {fact.symbol_id.partition('#')[0]}:{fact.range.start_line}"
    )


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
            assignments=self.assignments,
            movable=self.movable,
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

    def tree(self, side, path: str) -> ast.Module | None:
        """The parsed source of a Python file, or None when it is not one or does not parse."""
        cache = self.__dict__.setdefault("_trees", {})
        if (side, path) not in cache:
            try:
                source = self.workspace.snapshot.source.read_text(side, path)
                parsed = ast.parse(source.removeprefix("\ufeff")) if path.endswith(".py") else None
            except (SyntaxError, ValueError, KeyError, RecursionError):
                parsed = None
            cache[(side, path)] = parsed
        return cache[(side, path)]

    def assignments(
        self, side, path: str, *, local: bool = False
    ) -> list[tuple[int, int, tuple[str, ...]]]:
        """Assignments of a Python file: first line, last line, names.

        The module's own by default; with `local`, those written anywhere below it.
        """
        if local:
            cache = self.__dict__.setdefault("_assigned_below", {})
            if (side, path) not in cache:
                tree = self.tree(side, path)
                top = {id(node) for node in tree.body} if tree is not None else set()
                nodes = [node for node in ast.walk(tree) if id(node) not in top] if tree else []
                cache[(side, path)] = _assigned(nodes)
            return cache[(side, path)]
        return self._module(side, path)[0]

    def movable(self, side, path: str) -> set[int]:
        """First lines of the module-level assignments that may move without changing what
        the module does.

        Such an assignment binds plain names to a value that reads and calls nothing of
        the module: literals, and names the module does not bind. Each name it binds is
        bound only there, and nothing reads it while the module is imported. That rules
        out decorators, defaults, class bodies and other assignments that read it, and,
        when the module calls anything at import, every function that reads it. An
        `import *` could rebind any name, so then no assignment qualifies.
        """
        return self._module(side, path)[1]

    def _module(self, side, path: str) -> tuple[list, set[int]]:
        cache = self.__dict__.setdefault("_module_names", {})
        if (side, path) not in cache:
            tree = self.tree(side, path)
            if tree is None:
                cache[(side, path)] = ([], set())
            else:
                scope = _ModuleScope()
                scope.visit(tree)
                read = scope.read | (scope.read_later if scope.calls else set())
                free = {
                    node.lineno
                    for node in tree.body
                    if not scope.star
                    and _order_free(node, scope.bound)
                    and all(
                        scope.bound[name] == 1 and name not in read for name in _bound(node.targets)
                    )
                }
                cache[(side, path)] = (_assigned(tree.body), free)
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
        return self._graph()

    def _graph(self, skip=frozenset()) -> dict:
        """The call graph of both sides, leaving out the call facts in `skip`."""
        graph = {BASE: {}, HEAD: {}}
        known = {BASE: set(), HEAD: set()}
        for symbol in self.workspace.facts.symbols:
            known[symbol.side].add(symbol.symbol_id)
        for fact in self.workspace.facts.facts:
            if fact.kind == FactKind.call and (fact.side, fact.fingerprint) not in skip:
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
    def _dispatch(self) -> tuple[dict[str, list[tuple[frozenset[str], str]]], frozenset]:
        """Head handlers that run only for one argparse subcommand.

        `p = sub.add_parser("voice")` then `p.set_defaults(func=cmd_voice)` hands
        `cmd_voice` over, so the facts read it as a deferred call. But the function that
        builds the parser never calls it: `main` does, when the command line says `voice`.
        Returns, by the function that registers them, the subcommand names and the
        handler; and the call facts that hand them over.
        """
        found: dict[str, list[tuple[frozenset[str], str]]] = {}
        facts = set()
        for fact in self.workspace.facts.facts:
            reason = fact.target.reason if fact.kind == FactKind.call else None
            if fact.side != HEAD or not fact.deferred or not (reason or "").startswith(_HANDED):
                continue
            receiver = reason[len(_HANDED) :].rsplit("; it runs", 1)[0]
            holder, _, method = receiver.rpartition(".")
            if method != "set_defaults":
                continue
            names = set(_SUBCOMMAND.findall(holder))
            if not names and holder.isidentifier():
                names = {self._subparser(fact, holder)} - {None}
            if names:
                facts.add((fact.side, fact.fingerprint))
                for target in fact.target.targets:
                    found.setdefault(fact.symbol_id, []).append((frozenset(names), target))
        return found, frozenset(facts)

    def _subparser(self, fact: CodeFact, name: str) -> str | None:
        """The subcommand of the parser a local name holds where `fact` hands a handler over.

        The last assignment to the name before that line in the same definition counts:
        `p = sub.add_parser("voice")` gives `voice`; any other value gives nothing.
        """
        path = fact.symbol_id.partition("#")[0]
        cache = self.__dict__.setdefault("_parsers", {})
        if path not in cache:
            tree = self.tree(HEAD, path)
            found = []
            for node in ast.walk(tree) if tree is not None else ():
                if not isinstance(node, ast.Assign | ast.AnnAssign):
                    continue
                value = node.value
                command = None
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "add_parser"
                    and value.args
                    and isinstance(value.args[0], ast.Constant)
                    and isinstance(value.args[0].value, str)
                ):
                    command = value.args[0].value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                found += [(node.lineno, bound, command) for bound in _bound(targets)]
            cache[path] = sorted(found, key=lambda item: item[0])
        symbol = self.workspace.symbols.get(fact.symbol_id)
        first = symbol.range.start_line if symbol is not None else 1
        command = None
        for line, bound, value in cache[path]:
            if first <= line < fact.range.start_line and bound == name:
                command = value
        return command

    def _words(self, test_id: str) -> frozenset[str]:
        """The words of the string literals a test function writes, its decorators included."""
        test = self.tests[test_id]
        symbol = self.workspace.symbols.get(test.symbol_id)
        path = test.symbol_id.partition("#")[0]
        tree = self.tree(HEAD, path)
        if symbol is None or tree is None:
            return frozenset()
        cache = self.__dict__.setdefault("_literals", {})
        if path not in cache:
            cache[path] = [
                (node.lineno, node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            ]
        span = symbol.range
        return frozenset(
            word
            for line, text in cache[path]
            if span.start_line <= line <= span.end_line
            for word in text.split()
        )

    @cached_property
    def unresolved(self) -> list[CodeFact]:
        """Head calls into this code base's own modules that could not be resolved."""
        return [
            fact
            for fact in self.workspace.facts.facts
            if fact.side == HEAD
            and fact.kind == FactKind.call
            and fact.target.status == "unknown"
            and any(text in (fact.target.reason or "") for text in _LOCAL_FAILURES)
        ]

    @cached_property
    def _unresolved_by_name(self) -> dict[str, list[CodeFact]]:
        """Unresolved calls outside the tests, by the name they call."""
        tests = {
            item.path
            for item in self.workspace.snapshot.capture.manifest.files
            if item.side == HEAD and item.kind == "test"
        }
        found: dict[str, list[CodeFact]] = {}
        for fact in self.unresolved:
            name = _callee(fact.text)
            if name and fact.symbol_id.partition("#")[0] not in tests:
                found.setdefault(name, []).append(fact)
        return found

    def unresolved_into(self, symbols) -> list[CodeFact]:
        """Unresolved calls that may lead to these head definitions.

        A call counts when the name it calls is the name of one of them, or of a
        definition that leads to them through resolved calls. Matching by name finds
        too many rather than too few: a change wrongly found here only asks for one
        more explanation, while one missed would look unreachable without a word.
        """
        if not symbols or not self._unresolved_by_name:
            return []
        leading = _closure(symbols, self._called_by, REACH_DEPTH)
        names = {
            part
            for symbol in leading
            for part in symbol.partition("#")[2].split(".")
            if part and part != "<module>"
        }
        found = {
            fact.fingerprint: fact
            for name in names
            for fact in self._unresolved_by_name.get(name, ())
            if fact.symbol_id not in leading
        }
        return sorted(found.values(), key=lambda fact: (fact.symbol_id, fact.range.start_line))

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
        # A candidate the plan left out has been looked at: it stays listed, with the reason.
        decided = {item.entry_id: item for item in business_map.coverage.skipped_entries}
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
                    **(
                        {
                            "skipped": decided[entry.entry_id].reason,
                            "note": decided[entry.entry_id].note,
                        }
                        if entry.entry_id in decided
                        else {}
                    ),
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
        """Head calls as tests make them: a request to a route path calls its handler.

        A handler registered for one subcommand is left out: whether a test gets to it
        depends on the command line the test gives, which `_reached` checks per test.
        """
        _, handed = self._dispatch
        calls = self._graph(handed)[HEAD] if handed else self.calls[HEAD]
        graph = {symbol: set(targets) for symbol, targets in calls.items()}
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
    def _reached(self) -> dict[str, dict[str, int]]:
        """Head tests by the definitions they call, directly or through other calls: how
        many calls away each test is.

        A handler registered for an argparse subcommand counts only for a test whose
        string literals name that subcommand.
        """
        graph = self._test_calls
        dispatch, _ = self._dispatch
        found: dict[str, dict[str, int]] = {}
        for test_id in sorted(self.tests):
            symbol_id = self.tests[test_id].symbol_id
            words = self._words(test_id) if dispatch else frozenset()
            distances, frontier = {symbol_id: 0}, [symbol_id]
            for calls in range(1, TEST_DEPTH + 2):
                following = []
                for symbol in frontier:
                    chosen = [target for names, target in dispatch.get(symbol, ()) if names & words]
                    for target in (*graph.get(symbol, ()), *chosen):
                        if target not in distances:
                            distances[target] = calls
                            following.append(target)
                frontier = following
            for symbol, calls in distances.items():
                if symbol != symbol_id:
                    found.setdefault(symbol, {})[test_id] = calls
        return found

    @cached_property
    def _changed_tests(self) -> set[str]:
        """Head tests this change adds or edits: the likeliest to be about it."""
        kinds = {ChangeKind.test_added, ChangeKind.test_modified}
        return {
            f"head::{change.symbol_id}"
            for change in self.diff.changes
            if change.is_test and change.kind in kinds
        }

    # ----- tests ---------------------------------------------------------------------

    def _case(self, test_id: str, related: bool, assessed: bool = False) -> dict:
        test = self.tests[test_id]
        tags = ["related" if related else "agent_identified"]
        if assessed:
            tags.append("assessed")
        if test.assertions:
            tags.append("assertion_found")
        return {"test_id": test_id, "tags": tags, "evidence_ids": list(test.evidence_ids)}

    def _related(self, change: RawChange, symbols) -> list[str]:
        """Tests that reach a change, the most relevant first.

        First the tests this change adds or edits, then by how many calls away a test is
        (one: it calls the changed definition itself), tests with an assertion before
        those without, then by id.
        """
        reach: dict[str, int] = {}
        for symbol in symbols:
            for test_id, calls in self._reached.get(symbol, {}).items():
                reach[test_id] = min(calls, reach.get(test_id, calls))
        changed = self._changed_tests
        ranked = sorted(
            reach,
            key=lambda test_id: (
                test_id not in changed,
                reach[test_id],
                not self.tests[test_id].assertions,
                test_id,
            ),
        )
        self.__dict__.setdefault("_reach_of", {})[change.change_id] = {
            test_id: {"calls_away": reach[test_id], "changed_with_it": test_id in changed}
            for test_id in ranked
        }
        return ranked

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
            # The viewer translates this note by its exact text.
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
        named = list(dict.fromkeys(named))
        # The tests the verdict rests on come first; the static links stay after them.
        items = [self._case(test_id, test_id in related, assessed=True) for test_id in named]
        items += [self._case(test_id, True) for test_id in related if test_id not in named][
            : max(0, MAX_CASES - len(items))
        ]
        static = any(test_id in related for test_id in named) or (not named and related)
        judged = items[: len(named)] or items
        result = {
            "verdict": verdict.verdict,
            "basis": [*["static_fact"] * bool(static), "agent_assessment"],
            "execution_data": "not_collected",
            "note": verdict.note,
            "items": items,
        }
        if verdict.verdict == "covered" and not named:
            problems.append(
                (
                    "test_ids",
                    "covered_names_tests",
                    "covered names in `test_ids` the tests that run the change and would fail "
                    "if it were undone.",
                )
            )
        elif verdict.verdict == "covered" and not any(
            "assertion_found" in item["tags"] for item in judged
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

    def risks(self) -> dict[str, dict]:
        """Risks an agent submitted with the changes, by their id."""
        if not self._store.is_file():
            return {}
        return json.loads(self._store.read_text(encoding="utf-8")).get("risks", {})

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
        # A file left out for a reason of its own, such as its folder, says which.
        listed += [
            {"reason": "Not a supported source language; not analyzed.", **item} for item in others
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
        unread = outside.get("not_read", 0)
        total = outside["total"] - unread
        if total:
            limits.append(
                {
                    "code": "changed_files_outside_languages",
                    "message": f"{total} changed file{'s' * (total != 1)} outside the supported "
                    "languages: not analyzed.",
                    "affects_completeness": False,
                }
            )
        if unread:
            limits.append(
                {
                    "code": "changed_files_not_read",
                    "message": f"{unread} changed file{'s' * (unread != 1)} that no snapshot "
                    "reads, such as one in a dependency, build or cache folder, or over a size "
                    "limit: not analyzed. Each names its reason.",
                    "affects_completeness": False,
                }
            )
        if outside.get("left_out"):
            limits.append(left_out_limitation(outside["left_out"]))
        if outside.get("untracked_by_folder"):
            limits.append(untracked_folders_limitation(outside["untracked_by_folder"]))
        untracked = outside.get("untracked")
        if untracked and untracked["total"]:
            count, readable = untracked["total"], untracked["analyzable"]
            names = untracked["files"][:5]
            more = ", ..." if count > len(names) else ""
            limits.append(
                {
                    "code": "untracked_files_left_out",
                    "message": f"{count} untracked file{'s' * (count != 1)} left out of the "
                    "comparison"
                    + (f", {readable} of them source Genesis analyzes" if readable else "")
                    + ": "
                    + ", ".join(names)
                    + more
                    + ". If they belong to the change, run `prepare` again with "
                    "`--include-untracked`; `--exclude PATH` leaves one out on purpose.",
                    # Source left out may hold changes the report does not show.
                    "affects_completeness": bool(readable),
                }
            )
        return listed[:MAX_UNANALYZED], limits

    def _base_carried(self) -> dict[str, CodeEntry]:
        """The entries carried from a map, found at head or not, as base-side entries that
        cite the function itself, by entry id. One whose function the base lacks, as one
        from a map of other code, is left out."""
        base = {item.symbol_id: item for item in self.workspace.facts.symbols if item.side == BASE}
        carried = read_carried(self.workspace.root)
        found = {}
        for raw in (*carried.get("entries", ()), *carried.get("not_found_entries", ())):
            symbol = base.get(raw["symbol_id"])
            if symbol is None or symbol.kind != "function" or not symbol.evidence_ids:
                continue
            found[entry_id(symbol.symbol_id)] = CodeEntry.model_validate(
                {
                    **{key: raw[key] for key in ("kind", "framework", "attributes") if key in raw},
                    "entry_id": entry_id(symbol.symbol_id),
                    "symbol_id": symbol.symbol_id,
                    "detection": "agent_proposed",
                    "evidence_ids": list(symbol.evidence_ids),
                    "side": BASE.value,
                }
            )
        return found

    def _carried_removed(self, carried: dict[str, CodeEntry]) -> list[CodeEntry]:
        """Entries carried from a map whose function this change removed, of the `carried`
        ones (see `_base_carried`): the flow the map gave each is gone too. One whose
        function the base lacks has no flow to show removed."""
        head = {item.symbol_id for item in self.workspace.facts.symbols if item.side == HEAD}
        found = []
        for raw in read_carried(self.workspace.root).get("not_found_entries", ()):
            entry = carried.get(entry_id(raw["symbol_id"]))
            if entry is None or self.diff.moved.get(entry.symbol_id, entry.symbol_id) in head:
                continue
            found.append(entry)
        return found

    def _removed_flows(self, business_map: BusinessMap) -> tuple[list[dict], set[str]]:
        """Skeletons of entries that exist only on the base side, those carried from a map
        included. One that the map this session started from gave a flow together with
        other entries is shown as that flow, with all of them as the base has them, so
        that the flow keeps the id the map gave it; that flow is shown once. An entry the
        map proposed is shown as proposed, as at head, unless the analyzers recognise its
        function at base as more than a function nothing calls."""
        facts = self.workspace.facts
        kept = {entry.symbol_id for entry in facts.entries if entry.side == HEAD}
        taken = {flow.flow_id for flow in business_map.flows}
        shown = shown_facts(facts, BASE)
        flows, cited = [], set()
        removed = {
            entry.symbol_id: entry
            for entry in facts.entries
            if entry.side == BASE
            and entry.detection == "adapter"
            and self.diff.moved.get(entry.symbol_id, entry.symbol_id) not in kept
        }
        carried = self._base_carried()
        for entry in self._carried_removed(carried):
            removed.setdefault(entry.symbol_id, entry)
        found = {item.entry_id: item for item in facts.entries if item.side == BASE}
        known = {
            **found,
            **{
                key: item
                for key, item in carried.items()
                if key not in found or found[key].detection == "root_heuristic"
            },
        }
        groups = {key: group for group in self.workspace.carried_groups for key in group}
        for _, entry in sorted(removed.items()):
            members = [known.get(key) for key in dict.fromkeys(groups.get(entry.entry_id, ()))]
            if len(members) < 2 or any(item is None for item in members):
                members = [entry]
            flow, evidence = skeleton_flow(members, shown)
            if flow["flow_id"] in taken or len(flows) >= MAX_REMOVED_FLOWS:
                continue
            taken.add(flow["flow_id"])
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
            if placement.unresolved.get(change.change_id):
                item["unresolved_calls"] = placement.unresolved[change.change_id]
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
        known = {change.change_id for change in diff.changes}
        unanalyzed, limitations = self._unanalyzed()
        listed = {item["path"] for item in unanalyzed}
        risks, hidden = [], []
        for key, risk in sorted(self.risks().items()):
            if set(risk["change_ids"]) <= known and set(risk.get("paths", ())) <= listed:
                risks.append({"risk_id": key, **risk})
            else:
                hidden.append(key)
        cited.update(ref for risk in risks for ref in risk.get("evidence_ids", ()))
        if hidden:
            # Running `prepare` again with other folders left out keeps the session and
            # its accepted risks, but a file a risk names may no longer be listed.
            named = ", ".join(hidden[:5]) + (", ..." if len(hidden) > 5 else "")
            one = len(hidden) == 1
            limitations.append(
                {
                    "code": "risks_not_shown",
                    "message": f"{len(hidden)} accepted risk{'' if one else 's'} "
                    f"name{'s' if one else ''} changes or changed files the report no longer "
                    f"lists, and {'is' if one else 'are'} not shown, such as after `prepare` "
                    f"with other `--exclude` folders: {named}.",
                    "affects_completeness": False,
                }
            )
        waiting = [flows[key].name for key in sorted(touched) if flows[key].stage == "skeleton"]
        if waiting:
            named = ", ".join(waiting[:5]) + (", ..." if len(waiting) > 5 else "")
            # A session with no plan set out to explain the changes, not to describe flows:
            # its report is complete once they are explained. A plan takes on its flows.
            planned = workspace.plan is not None
            limitations.append(
                {
                    "code": "affected_flow_not_synthesized",
                    "message": (
                        f"Changes are placed on flows that are still a static skeleton: {named}."
                        if planned
                        else "No flow was described: changes are placed on flows that are "
                        f"still a static skeleton: {named}. This does not keep the report "
                        "from being complete; describe these flows to see the changes in "
                        "business steps."
                    ),
                    "affects_completeness": planned,
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
        if self.unresolved:
            # The most common reason, by its first call, stands for all of them.
            reasons = Counter(fact.target.reason for fact in self.unresolved)
            reason = reasons.most_common(1)[0][0]
            example = next(fact for fact in self.unresolved if fact.target.reason == reason)
            count = len(self.unresolved)
            owed = sum(1 for item in items if item.get("unresolved_calls"))
            limitations.append(
                {
                    "code": "unresolved_local_calls",
                    "message": _short(
                        f"{count} call{'s' * (count != 1)} into this code base's own modules "
                        f"could not be resolved, such as {_where(example)} ({reason}). Code "
                        "reached only through such calls looks unreachable, and its tests may "
                        "not be linked."
                        + (
                            f" {owed} change{'s' * (owed != 1)} may be reached this way and "
                            "need an explanation."
                            if owed
                            else ""
                        ),
                        2000,
                    ),
                    "affects_completeness": False,
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
            "risks": risks,
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
        """One side of a change. `excerpt` marks a text shorter than the lines it cites.

        A definition shows its header, a long block is cut, and a statement written over
        several lines is shown on one: then `genesis map read` gives the full lines.
        """
        if part is None:
            return None
        view = {
            "text": part.text,
            "path": part.path,
            "start_line": part.start[0],
            "end_line": part.end[0],
            "evidence_id": part.evidence_ids[0],
        }
        full = self.workspace.read(part.evidence_ids[0])
        if full["truncated"] or _lines(full["text"]) != _lines(part.text):
            view["excerpt"] = True
        return view

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
            # Two sides that read the same cannot show what changed: read both in full.
            if view["before"] and view["after"] and change.before.text == change.after.text:
                view["before"]["excerpt"] = view["after"]["excerpt"] = True
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
            if item.unresolved_calls:
                view["unresolved_calls"] = item.unresolved_calls
            landing = self.lands_on(change)
            if landing:
                view["lands_on"] = landing
            if item.tests is not None:
                reach = self.__dict__.get("_reach_of", {}).get(item.change_id, {})
                view["tests"] = {
                    "verdict": item.tests.verdict.value,
                    "basis": [value.value for value in item.tests.basis],
                    "note": item.tests.note,
                    "tests": [
                        {
                            "test_id": case.test_id,
                            "evidence_id": case.evidence_ids[0],
                            "assertions": list(self.tests[case.test_id].assertions[:5]),
                            # How many calls away from the change, and whether this change
                            # edits the test; unset for a test static analysis did not link.
                            **reach.get(
                                case.test_id, {"calls_away": None, "changed_with_it": False}
                            ),
                            **({"named": True} if "assessed" in case.tags else {}),
                        }
                        for case in item.tests.items
                    ],
                }
            views.append(view)
        return views

    def lands_on(self, change: RawChange) -> list[dict]:
        """Where each new `break`, `continue` or `return` of a change takes the code.

        The code that runs next is not part of the change, so neither the diff nor the
        change shows it. `break` goes on after its loop, `continue` back to the loop
        header, `return` to the callers. Only for a definition both sides have: in a
        new one there is no earlier path to leave.
        """
        pairs = self.diff.same.get(change.symbol_id)
        if change.is_test or change.after is None or pairs is None:
            return []
        kept = set(pairs.values())
        part = change.after
        found = []
        for fact in self.ordered(HEAD, change.symbol_id):
            if fact.kind not in _LANDING or fact.fingerprint in kept:
                continue
            line = fact.range.start_line
            inside = part.start[0] <= line <= part.end[0]
            in_loop = change.kind == ChangeKind.loop_bound_changed and part.anchor in fact.loops
            if not (inside or in_loop):
                continue
            item = {"jump": _short(fact.text, 80), "line": line}
            if fact.kind == FactKind.returns:
                callers = [
                    {
                        "path": caller.symbol_id.partition("#")[0],
                        "line": caller.range.start_line,
                        "text": _short(caller.text, 120),
                    }
                    for caller in self.callers[HEAD].get(change.symbol_id, ())[:3]
                ]
                item["callers"] = callers
            else:
                lines = self.workspace.snapshot.source.read_text(HEAD, part.path).split("\n")
                after = _landing(self.tree(HEAD, part.path), lines, fact.kind, line)
                if after is None:
                    continue
                item["next"] = {"path": part.path, **after}
            found.append(item)
        return found

    @cached_property
    def _changed_lines(self) -> dict[str, list[tuple[int, int]]]:
        """The head-side lines each file's changes cover."""
        found: dict[str, list[tuple[int, int]]] = {}
        for change in self.diff.changes:
            if change.after is not None:
                found.setdefault(change.after.path, []).append(
                    (change.after.start[0], change.after.end[0])
                )
            for side, path, first, last in change.covers:
                if side == HEAD:
                    found.setdefault(path, []).append((first, last))
        return found

    def unchanged_callers(self, report: ChangeReport) -> list[dict]:
        """For each changed function, the code that calls it and is not itself changed.

        The changes show what is different; what the callers do with it is outside the
        diff. A call in a loop runs once per item, so those come first, with the loop.
        Tests are left out: they are listed with each change.
        """
        tests = {
            item.path
            for item in self.workspace.snapshot.capture.manifest.files
            if item.side == HEAD and item.kind == "test"
        }
        raw = {change.change_id: change for change in self.diff.changes}
        changed: dict[str, list[str]] = {}
        for item in report.changes:
            change = raw.get(item.change_id)
            if change is None or change.is_test or change.after is None:
                continue
            if item.symbol_id.endswith("#<module>"):
                continue
            changed.setdefault(item.symbol_id, []).append(item.change_id)
        loops = self.workspace.by_fingerprint

        def untouched(fact) -> bool:
            path = fact.symbol_id.partition("#")[0]
            line = fact.range.start_line
            return path not in tests and not any(
                first <= line <= last for first, last in self._changed_lines.get(path, ())
            )

        def shown(fact) -> dict:
            item = {
                "path": fact.symbol_id.partition("#")[0],
                "line": fact.range.start_line,
                "text": _short(fact.text, 120),
            }
            loop = loops.get(fact.loops[-1]) if fact.loops else None
            if loop is not None:
                item["loop"] = _short(loop.text, 80)
            return item

        found = []
        for symbol, change_ids in changed.items():
            calls = [fact for fact in self.callers[HEAD].get(symbol, ()) if untouched(fact)]
            if not calls:
                continue
            calls.sort(key=lambda fact: (not fact.loops, fact.symbol_id, fact.range.start_line))
            found.append(
                {
                    "symbol_id": symbol,
                    "change_ids": change_ids[:5],
                    "callers": [shown(fact) for fact in calls[:CALLERS_SHOWN]],
                    "callers_total": len(calls),
                }
            )
        found.sort(key=lambda item: ("loop" not in item["callers"][0], item["symbol_id"]))
        return found[:CALLER_SYMBOLS]

    def context(self, business_map: BusinessMap) -> dict:
        """The changes still to explain, with both sides and the tests that reach them."""
        report = self.build(business_map)
        placed = [item for item in report.changes if item.projection.status != "unassigned"]
        waiting = [item for item in report.owed() if item.explanation is None]
        # Then the changes no flow reaches, which need no explanation for the report to
        # be complete but still say nothing until they have one, then the explained ones.
        owed = {item.change_id for item in waiting}
        rest = [
            item
            for item in report.changes
            if item.explanation is None and item.change_id not in owed
        ]
        done = [item for item in report.changes if item.explanation is not None]
        shown = [*waiting, *rest, *done][:CONTEXT_LIMIT]
        return {
            "task_id": CHANGE_TASK,
            "kind": "change",
            "state": "pending" if waiting else "validated",
            "analysis_status": report.analysis_status,
            "changes_total": len(report.changes),
            "changes_placed": len(placed),
            "changes_waiting": len(waiting),
            # Every change without an explanation, including those no flow reaches.
            "changes_unexplained": len(waiting) + len(rest),
            # Up to this many per call, unexplained first; submit them and ask again.
            "changes_listed": len(shown),
            "changes": self._views(shown, business_map),
            # Outside the changes: who calls the changed functions, for the risk pass.
            "unchanged_callers": self.unchanged_callers(report),
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
            # Uncalled functions that lead to the changes and have no flow, as `status`
            # lists them: a plan needs the entry id to skip one or give it a flow.
            **unchecked_entries(report),
            "removed_flows": [flow.name for flow in report.removed_flows],
            # Risks an agent submitted with the changes: its own reading.
            "risks": [
                item.model_dump(mode="json", exclude={"support"}, exclude_none=True)
                for item in report.risks
            ],
            # Accepted risks the report leaves out, by the id that withdraws them.
            **self._risks_not_shown(report),
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

    def _risks_not_shown(self, report: ChangeReport) -> dict:
        """The accepted risks `report` leaves out, as the limitation `risks_not_shown`
        counts them: they name files it no longer lists."""
        shown = {item.risk_id for item in report.risks}
        hidden = [
            {
                "risk_id": key,
                "statement": risk["statement"],
                **({"paths": risk["paths"]} if risk.get("paths") else {}),
            }
            for key, risk in sorted(self.risks().items())
            if key not in shown
        ]
        return {"risks_not_shown": hidden} if hidden else {}

    def check(self, raw) -> tuple[dict[str, dict], list[tuple[str, str, str]]]:
        """Validate a submission. Returns the assessments to store, or the problems."""
        submission = ChangeSubmission.model_validate(raw)
        known = {change.change_id: change for change in self.diff.changes}
        placement = _Placement(self, self.workspace.stored_map())
        accepted, problems = {}, []
        for index, item in enumerate(submission.changes):
            stored = item.model_dump(mode="json", exclude_none=True, exclude={"change_ids"})
            # A problem about the tests named, not about one change, is said once per item.
            said = set()
            for at, change_id in item.places():
                # One change of several is named at its place in `change_ids`.
                where = f"changes[{index}]" + ("" if item.change_id else f".{at[0]}[{at[1]}]")
                change = known.get(change_id)
                if change is None:
                    named = where + (".change_id" if item.change_id else "")
                    problems.append((named, "unknown_change", f"No change {change_id}."))
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
                for field, code, message in found:
                    if code in _ABOUT_THE_TESTS and (field, code, message) in said:
                        continue
                    said.add((field, code, message))
                    problems.append((f"{where}.{field}", code, message))
                accepted[change_id] = {**stored, "change_id": change_id}
        # A risk names analyzed code by its changes, and a changed file Genesis did not
        # analyze by its path as `unanalyzed_changes` lists it. Files left out on purpose,
        # in `.genesis/` or a folder passed to `--exclude`, are not listed there.
        listed = {item["path"] for item in self._unanalyzed()[0]} if submission.risks else set()
        for index, risk in enumerate(submission.risks):
            missing = [key for key in risk.change_ids if key not in known]
            if missing:
                problems.append(
                    (
                        f"risks[{index}].change_ids",
                        "unknown_change",
                        f"No change {', '.join(missing)}.",
                    )
                )
            for position, path in enumerate(risk.paths):
                if path not in listed:
                    problems.append(
                        (
                            f"risks[{index}].paths[{position}]",
                            "not_in_unanalyzed_changes",
                            f"{path} is not listed under `unanalyzed_changes`: `paths` names "
                            "only files listed there, and analyzed code is named by its change "
                            "in `change_ids`.",
                        )
                    )
        stored = self.risks()
        for index, key in enumerate(submission.withdrawn_risks):
            if key not in stored:
                problems.append(
                    (f"withdrawn_risks[{index}]", "unknown_risk", f"No accepted risk {key}.")
                )
        return accepted, problems

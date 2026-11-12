"""Python adapter: turn an existing extraction into language-neutral facts.

Reuses the parsed syntax trees and the call resolution of the Python extractor,
and adds what the map workflow needs on top: position-independent fingerprints,
the branch each fact sits on, enclosing loops, and returns and raises.

Limits: lambda bodies are not descended into, and `try`/`except` is not modelled as
a branch. A call in a decorator or default value belongs to the enclosing scope, so
it carries no guards of the decorated function.
"""

from __future__ import annotations

import io
import keyword
import re
import tokenize
from collections import Counter
from dataclasses import dataclass, field

import libcst as cst
from genesis_contracts.facts import (
    CallBoundary,
    CodeFact,
    CodeSymbol,
    CodeTest,
    FactKind,
    FactSet,
    FileFacts,
    GuardRef,
    Language,
)
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.models import ReferenceRange, Resolution
from libcst.metadata import MetadataWrapper, PositionProvider

from genesis_ci.business_map.python_entries import _is_test_path, detect_python_entries
from genesis_ci.python.extract import Extraction, ParsedFile

_LAYOUT_TOKENS = {
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.COMMENT,
    tokenize.ENDMARKER,
}
_UNRESOLVED = Resolution(status="unknown", reason="No resolution recorded for this call")
_OPENERS, _CLOSERS = {"(", "[", "{"}, {")", "]", "}"}
MAX_SOURCE_ROOTS = 200
# Calls that check something without an `assert` statement.
_ASSERTING_CALL = re.compile(
    r"(pytest\.(raises|warns|fail|approx)|self\.(assert|fail)\w*|[\w.]+\.assert_\w+)\("
)


def _without_trailing_commas(tokens: list[str]) -> list[str]:
    """Drop the comma before a closing bracket, which formatters add and remove freely.

    The comma of a one-element tuple such as `(x,)` stays: it changes the value.
    """
    kept: list[str] = []
    # Per open bracket: the bracket, whether it follows a callee, commas seen inside it.
    open_brackets: list[list] = []
    for token in tokens:
        if token in _OPENERS:
            before = kept[-1] if kept else ""
            called = before in {")", "]"} or (
                before.isidentifier() and not keyword.iskeyword(before)
            )
            open_brackets.append([token, called, 0])
        elif token == "," and open_brackets:
            open_brackets[-1][2] += 1
        elif token in _CLOSERS and open_brackets:
            bracket, called, commas = open_brackets.pop()
            if kept and kept[-1] == "," and (bracket != "(" or called or commas > 1):
                kept.pop()
        kept.append(token)
    return kept


def canonical_python(text: str) -> str:
    """Render source so that formatting-only edits leave it unchanged.

    Tokens are joined by single spaces. String literal contents are kept exactly;
    comments, line breaks and a formatter's trailing commas are dropped.
    """
    try:
        tokens = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type not in _LAYOUT_TOKENS and token.string
        ]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return " ".join(text.split())
    return " ".join(_without_trailing_commas(tokens))


def python_source_roots(paths) -> tuple[str, ...]:
    """Folders that absolute imports are resolved from, found from the files themselves.

    A top-level package is importable from the folder that holds it, so `pkg/src/app/`
    with an `__init__.py` makes `pkg/src` a root. Without this, code in a `src` layout
    or a monorepo cannot be linked to the tests and callers that import it.
    """
    packages = {
        path.rpartition("/")[0]
        for path in paths
        if path.rpartition("/")[2] in {"__init__.py", "__init__.pyi"} and "/" in path
    }
    parents = {package.rpartition("/")[0] for package in packages}
    roots = sorted(parent for parent in parents if parent and parent not in packages)
    return tuple(dict.fromkeys((".", "src", *roots)))[:MAX_SOURCE_ROOTS]


def call_boundary(target: Resolution) -> CallBoundary:
    # Calling an SDK client object keeps an `instance:` marker on its external target.
    targets = tuple(item.removeprefix("instance:") for item in target.targets)
    if not targets:
        return CallBoundary.unknown
    if all(item.startswith("builtin:") for item in targets):
        return CallBoundary.builtin
    if all(item.startswith("external:") for item in targets):
        return CallBoundary.external
    if not any(item.startswith(("builtin:", "external:", "module:")) for item in targets):
        return CallBoundary.internal
    return CallBoundary.unknown


@dataclass
class _Frame:
    """Branch and loop context of one function, class or module body."""

    conditions: list[str] = field(default_factory=list)
    matches: list[str] = field(default_factory=list)
    loop_ids: list[str] = field(default_factory=list)
    guards: list[GuardRef] = field(default_factory=list)
    loops: list[str] = field(default_factory=list)


class _Collector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, file: ParsedFile, registry, calls: dict):
        # `calls` maps the source span of a call to its index among the file's parsed calls.
        self.file, self.registry, self.calls = file, registry, calls
        # Repeated facts of one symbol are told apart by an ordinal. A symbol never
        # spans files, so counting per file is counting per symbol.
        self.ordinals: Counter = Counter()
        self.names: list[str] = []
        self.frames = [_Frame()]
        self.facts: list[CodeFact] = []
        # For a call fact, by its position in `facts`: the parsed call it stands for.
        self.parsed_call: dict[int, int] = {}
        self.refs = {}
        # Where a decorated definition really starts: at its first decorator.
        self.decorated: dict[str, tuple[int, int]] = {}
        self.bom = int(file.raw_text.startswith("﻿"))

    @property
    def frame(self) -> _Frame:
        return self.frames[-1]

    @property
    def owner(self) -> str:
        return self.file.path + "#" + (".".join(self.names) or "<module>")

    def text(self, node) -> str:
        return self.file.module.code_for_node(node)

    def span(self, start, end=None) -> ReferenceRange:
        first = self.get_metadata(PositionProvider, start).start
        last = self.get_metadata(PositionProvider, end or start).end
        return ReferenceRange(
            start_line=first.line,
            end_line=last.line,
            start_column=first.column + (self.bom if first.line == 1 else 0),
            end_column=last.column + (self.bom if last.line == 1 else 0),
        )

    def emit(self, kind, span, text, *, symbol=None, **call) -> str:
        symbol = symbol or self.owner
        canonical = canonical_python(text)
        key = (self.file.side, symbol, kind, canonical)
        ordinal = self.ordinals[key]
        self.ordinals[key] += 1
        fingerprint = fact_fingerprint(
            symbol=symbol, kind=kind.value, text=canonical, ordinal=ordinal
        )
        ref = self.registry.register(self.file.side, self.file.path, span)
        self.refs[ref.evidence_id] = ref
        in_scope = symbol == self.owner
        self.facts.append(
            CodeFact(
                fingerprint=fingerprint,
                kind=kind,
                side=self.file.side,
                language=Language.python,
                symbol_id=symbol,
                text=text.strip()[:12000],
                ordinal=ordinal,
                range=span,
                evidence_ids=(ref.evidence_id,),
                guards=tuple(self.frame.guards) if in_scope else (),
                loops=tuple(self.frame.loops) if in_scope else (),
                **call,
            )
        )
        return fingerprint

    def _enter_scope(self, node) -> None:
        self.names.append(node.name.value)
        self.frames.append(_Frame())
        if node.decorators:
            first = self.get_metadata(PositionProvider, node.decorators[0]).start
            self.decorated[self.owner] = (first.line, first.column)

    def _leave_scope(self) -> None:
        self.names.pop()
        self.frames.pop()

    def visit_FunctionDef(self, node) -> None:
        self._enter_scope(node)

    def leave_FunctionDef(self, node) -> None:
        self._leave_scope()

    def visit_ClassDef(self, node) -> None:
        self._enter_scope(node)

    def leave_ClassDef(self, node) -> None:
        self._leave_scope()

    def visit_Lambda(self, node) -> bool:
        return False

    def visit_If(self, node) -> None:
        self.frame.conditions.append(
            self.emit(
                FactKind.condition,
                self.span(node.test),
                self.text(node.test),
                branches=("true", "false"),
            )
        )

    def visit_If_body(self, node) -> None:
        self.frame.guards.append(GuardRef(fingerprint=self.frame.conditions[-1], branch="true"))

    def leave_If_body(self, node) -> None:
        self.frame.guards.pop()

    def visit_If_orelse(self, node) -> None:
        if node.orelse is not None:
            self.frame.guards.append(
                GuardRef(fingerprint=self.frame.conditions[-1], branch="false")
            )

    def leave_If_orelse(self, node) -> None:
        if node.orelse is not None:
            self.frame.guards.pop()

    def leave_If(self, node) -> None:
        self.frame.conditions.pop()

    def _case_label(self, case) -> str:
        label = "case " + self.text(case.pattern)
        if case.guard is not None:
            label += " if " + self.text(case.guard)
        return label[:2000]

    def visit_Match(self, node) -> None:
        text = "match " + self.text(node.subject)
        labels = [self._case_label(case) for case in node.cases]
        if "case _" not in labels:
            labels.append("no case matched")
        self.frame.matches.append(
            self.emit(FactKind.condition, self.span(node.subject), text, branches=tuple(labels))
        )

    def leave_Match(self, node) -> None:
        self.frame.matches.pop()

    def visit_MatchCase(self, node) -> None:
        self.frame.guards.append(
            GuardRef(fingerprint=self.frame.matches[-1], branch=self._case_label(node))
        )

    def leave_MatchCase(self, node) -> None:
        self.frame.guards.pop()

    def _loop(self, node, header_end, text) -> None:
        self.frame.loop_ids.append(
            self.emit(FactKind.loop, self.span(node, header_end), text, branches=("loop", "exit"))
        )

    def visit_While(self, node) -> None:
        self._loop(node, node.test, "while " + self.text(node.test))

    def visit_For(self, node) -> None:
        text = "for " + self.text(node.target) + " in " + self.text(node.iter)
        self._loop(node, node.iter, text)

    def visit_While_body(self, node) -> None:
        self.frame.loops.append(self.frame.loop_ids[-1])
        self.frame.guards.append(GuardRef(fingerprint=self.frame.loop_ids[-1], branch="loop"))

    def leave_While_body(self, node) -> None:
        self.frame.loops.pop()
        self.frame.guards.pop()

    def leave_While(self, node) -> None:
        self.frame.loop_ids.pop()

    visit_For_body = visit_While_body
    leave_For_body = leave_While_body
    leave_For = leave_While

    def visit_Call(self, node) -> None:
        span = self.span(node)
        index = self.calls.get(_span_key(span))
        parsed = self.file.calls[index] if index is not None else None
        if index is not None:
            self.parsed_call[len(self.facts)] = index
        # Targets are resolved once every file is known; `python_facts` fills them in.
        self.emit(
            FactKind.call,
            span,
            self.text(node),
            symbol=parsed.symbol_id if parsed else None,
            target=_UNRESOLVED,
            awaited=bool(parsed and parsed.awaited),
            boundary=CallBoundary.unknown,
        )

    def visit_Return(self, node) -> None:
        value = "" if node.value is None else " " + self.text(node.value)
        self.emit(FactKind.returns, self.span(node), "return" + value)

    def visit_Break(self, node) -> None:
        self.emit(FactKind.breaks, self.span(node), "break")

    def visit_Continue(self, node) -> None:
        self.emit(FactKind.continues, self.span(node), "continue")

    def visit_Raise(self, node) -> None:
        value = "" if node.exc is None else " " + self.text(node.exc)
        self.emit(FactKind.raises, self.span(node), "raise" + value)


def _with_decorators(span: ReferenceRange, start: tuple[int, int] | None) -> ReferenceRange:
    """A definition's range, starting at its first decorator when it has one."""
    if start is None or start[0] >= span.start_line:
        return span
    return span.model_copy(update={"start_line": start[0], "start_column": start[1]})


def _span_key(span: ReferenceRange):
    return (span.start_line, span.start_column, span.end_line, span.end_column)


def _tests(extraction: Extraction, symbols, facts: list[CodeFact]) -> list[CodeTest]:
    """Test functions as source: the repository functions they call and their assertions."""
    known = {(symbol.side, symbol.symbol_id) for symbol in symbols}
    called: dict[tuple, set[str]] = {}
    for fact in facts:
        if fact.kind == FactKind.call:
            internal = {t for t in fact.target.targets if (fact.side, t) in known}
            called.setdefault((fact.side, fact.symbol_id), set()).update(internal)
    asserted: dict[tuple, list[str]] = {}
    for item in extraction.analysis.assertions:
        asserted.setdefault((item.side, item.symbol_id), []).append(item.expression.text[:400])
    for fact in facts:
        if fact.kind == FactKind.call and _ASSERTING_CALL.match(fact.text):
            asserted.setdefault((fact.side, fact.symbol_id), []).append(fact.text[:400])
    found = []
    for symbol in symbols:
        name = symbol.qualified_name.rsplit(".", 1)[-1]
        if symbol.kind != "function" or not name.startswith("test") or not symbol.evidence_ids:
            continue
        if not _is_test_path(symbol.path):
            continue
        key = (symbol.side, symbol.symbol_id)
        found.append(
            CodeTest(
                test_id=f"{symbol.side.value}::{symbol.symbol_id}",
                side=symbol.side,
                symbol_id=symbol.symbol_id,
                called_symbol_ids=tuple(sorted(called.get(key, ()))),
                assertions=tuple(asserted.get(key, ())[:40]),
                evidence_ids=symbol.evidence_ids,
            )
        )
    return found


def collect_file(file: ParsedFile, wrapper: MetadataWrapper, registry) -> dict:
    """The facts of one parsed file, gathered while its syntax tree exists.

    Meant as the `collect` hook of `extract_python`, so that the tree is visited where it
    was parsed and never has to leave that process. Call targets are still unresolved.
    """
    spans = {}
    for index, call in enumerate(file.calls):
        located = [registry.get(ref) for ref in call.evidence_ids]
        located = [ref for ref in located if ref is not None]
        if located:
            spans[_span_key(located[0].range)] = index
    collector = _Collector(file, registry, spans)
    wrapper.visit(collector)
    return {
        "facts": collector.facts,
        "parsed_call": collector.parsed_call,
        "refs": collector.refs,
        "decorated": collector.decorated,
    }


def python_facts(extraction: Extraction) -> FactSet:
    """Convert every parsed Python file of an extraction into language-neutral facts."""
    analysis = extraction.analysis
    catalog = {ref.evidence_id: ref for ref in analysis.evidence}
    refs = {}
    facts: list[CodeFact] = []
    decorated: dict[tuple, tuple[int, int]] = {}
    for key in sorted(extraction.files, key=lambda item: (item[0].value, item[1])):
        file = extraction.files[key]
        gathered = extraction.collected.get(key)
        if gathered is None:
            wrapper = MetadataWrapper(file.module, unsafe_skip_copy=True)
            gathered = collect_file(file, wrapper, extraction.registry)
        for index, fact in enumerate(gathered["facts"]):
            call = gathered["parsed_call"].get(index)
            if call is not None:
                target = file.calls[call].target
                fact = fact.model_copy(update={"target": target, "boundary": call_boundary(target)})
            facts.append(fact)
        refs.update(gathered["refs"])
        decorated.update(
            ((file.side, name), value) for name, value in gathered["decorated"].items()
        )
    symbols = {}
    for symbol in analysis.symbols:
        # A redefinition replaces the earlier one at run time; facts of both stay distinct.
        symbols[(symbol.side, symbol.symbol_id)] = CodeSymbol(
            symbol_id=symbol.symbol_id,
            side=symbol.side,
            language=Language.python,
            path=symbol.path,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            is_async=symbol.is_async,
            decorators=tuple(item.text for item in symbol.decorators),
            source_digest=symbol.source_digest,
            range=_with_decorators(symbol.range, decorated.get((symbol.side, symbol.symbol_id))),
            evidence_ids=symbol.evidence_ids,
        )
        refs.update((ref, catalog[ref]) for ref in symbol.evidence_ids)
    facts.sort(
        key=lambda item: (
            item.side.value,
            item.symbol_id.split("#")[0],
            item.range.start_line,
            item.range.start_column or 0,
            item.kind.value,
            item.ordinal,
        )
    )
    ordered = tuple(symbols[key] for key in sorted(symbols, key=lambda k: (k[0].value, k[1])))
    entries, cited = detect_python_entries(extraction, ordered, facts)
    refs.update(cited)
    tests = _tests(extraction, ordered, facts)
    return FactSet(
        snapshot_id=analysis.snapshot_id,
        symbols=ordered,
        facts=tuple(facts),
        entries=tuple(entries),
        tests=tuple(tests),
        files=tuple(
            FileFacts(
                path=item.path,
                side=item.side,
                language=Language.python,
                status="analyzed" if item.syntax.status == "analyzed" else "unsupported",
                reason=item.syntax.reason,
            )
            for item in analysis.coverage
        ),
        evidence=tuple(refs[key] for key in sorted(refs)),
    )

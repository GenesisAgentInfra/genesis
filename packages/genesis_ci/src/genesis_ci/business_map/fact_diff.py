"""Fact-level diff between the base and head side of one frozen snapshot.

Deterministic and model-free. Facts are matched by fingerprint, which does not depend
on position, so moving or reformatting code changes nothing. What is left over on each
side is paired into modifications when the text is similar, and reported as added or
removed otherwise.

Facts cover conditions, calls, loops and results. Everything else that changed
(assignments, defaults, decorators, docstrings) is found by a line comparison of each
changed file and reported as a source change, so no edit goes unlisted.

A fact that repeats inside one function shares its text with its repeats, and its
fingerprint only counts them. Repeats are therefore matched by where they are: the ones
on a line that reads the same on both sides first, the rest in order between those.

Limits: a repeat whose own line was edited is matched by order, which is a guess when
repeats were added or removed next to it. A function that is moved and edited at once is
reported as removed and added.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from genesis_contracts.change_report import ChangeKind
from genesis_contracts.facts import CodeFact, CodeSymbol, FactKind, FactSet
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.models import EvidenceRef, EvidenceSide, ReferenceRange

from .skeleton import _evaluation_order, _short

BASE, HEAD = EvidenceSide.base, EvidenceSide.head
SIMILAR = 0.6
PAIR_BUDGET = 4000
LINE_BUDGET = 25_000_000
MAX_CHANGES = 300
TEXT_LIMIT = 800
_JUMPS = {FactKind.breaks, FactKind.continues}
_KINDS = {
    FactKind.condition: ("condition_added", "condition_removed", "condition_modified"),
    FactKind.call: ("call_added", "call_removed", "call_modified"),
    FactKind.loop: ("loop_added", "loop_removed", "loop_bound_changed"),
    FactKind.returns: ("result_added", "result_removed", "result_modified"),
    FactKind.raises: ("result_added", "result_removed", "result_modified"),
}
_CALL_KINDS = {ChangeKind.call_added, ChangeKind.call_removed, ChangeKind.call_modified}
# A branch or loop that came or went as a whole, by the side it exists on.
_BLOCK_KINDS = {
    EvidenceSide.head: {ChangeKind.condition_added, ChangeKind.loop_added},
    EvidenceSide.base: {ChangeKind.condition_removed, ChangeKind.loop_removed},
}
HEADER_LINES = 8
_COMMENT = {"python": "#", "typescript": "//"}
# Lines that only open or close a block say nothing by themselves.
_STRUCTURAL = re.compile(r"^(?:[^\w]|\b(?:else|try|finally|pass|do)\b)*$")


@dataclass
class Part:
    """One side of a change: what the code says there and where it is."""

    side: EvidenceSide
    text: str
    anchor: str
    evidence_ids: tuple[str, ...]
    path: str
    start: tuple[int, int]
    end: tuple[int, int]

    @property
    def lines(self) -> range:
        return range(self.start[0], self.end[0] + 1)


@dataclass
class RawChange:
    kind: ChangeKind
    symbol_id: str
    before: Part | None = None
    after: Part | None = None
    # Fact fingerprints the change covers, for placing it on a map.
    base_anchors: set[str] = field(default_factory=set)
    head_anchors: set[str] = field(default_factory=set)
    # Whole symbols the change covers: an added, removed or moved definition.
    base_symbols: tuple[str, ...] = ()
    head_symbols: tuple[str, ...] = ()
    # Enclosing conditions and loops, innermost last, on the side the code exists.
    guards: tuple[str, ...] = ()
    details: list[str] = field(default_factory=list)
    # Further source ranges this change accounts for: side, path, first line, last line.
    covers: list[tuple] = field(default_factory=list)
    is_test: bool = False
    module_level: bool = False

    @property
    def change_id(self) -> str:
        identity = "\0".join(
            (
                self.kind.value,
                self.symbol_id,
                self.before.anchor if self.before else "",
                self.after.anchor if self.after else "",
            )
        )
        return "chg_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


@dataclass
class FactDiff:
    changes: list[RawChange]
    evidence: dict[str, EvidenceRef]
    # Base symbol id to head symbol id, for definitions that only moved.
    moved: dict[str, str]
    # For each definition whose facts were compared: base fingerprint to head fingerprint
    # of every fact that stayed. The two differ where a repeat came or went before it.
    same: dict[str, dict[str, str]] = field(default_factory=dict)
    truncated: bool = False
    skipped_files: tuple[str, ...] = ()


def _flat(text: str) -> str:
    return " ".join(text.split())[:300]


def _span(span: ReferenceRange) -> tuple[tuple[int, int], tuple[int, int]]:
    end_column = 10**9 if span.end_column is None else span.end_column
    return (span.start_line, span.start_column or 0), (span.end_line, end_column)


def _fact_part(fact: CodeFact) -> Part:
    start, end = _span(fact.range)
    return Part(
        side=fact.side,
        text=_short(fact.text, TEXT_LIMIT),
        anchor=fact.fingerprint,
        evidence_ids=fact.evidence_ids,
        path=fact.symbol_id.partition("#")[0],
        start=start,
        end=end,
    )


def _inside(inner: Part | None, outer: Part | None) -> bool:
    if inner is None or outer is None or inner.path != outer.path:
        return False
    if (inner.start, inner.end) == (outer.start, outer.end):
        return False
    return outer.start <= inner.start and inner.end <= outer.end


def _ancestors(symbol_id: str):
    path, _, name = symbol_id.partition("#")
    while "." in name:
        name = name.rsplit(".", 1)[0]
        yield f"{path}#{name}"


def _pair(old: list[CodeFact], new: list[CodeFact]) -> list[tuple[CodeFact, CodeFact]]:
    """Pair leftover facts of one kind whose text is similar enough to be one edit."""
    if not old or not new or len(old) * len(new) > PAIR_BUDGET:
        return []
    scored = []
    for i, before in enumerate(old):
        for j, after in enumerate(new):
            score = SequenceMatcher(
                None, _flat(before.text), _flat(after.text), autojunk=False
            ).ratio()
            if score >= SIMILAR:
                scored.append((-score, abs(i - j), i, j))
    pairs, used_old, used_new = [], set(), set()
    for _, _, i, j in sorted(scored):
        if i not in used_old and j not in used_new:
            used_old.add(i)
            used_new.add(j)
            pairs.append((old[i], new[j]))
    return pairs


def _targets(fact: CodeFact, moved: dict[str, str]) -> frozenset[str]:
    return frozenset(moved.get(item, item) for item in fact.target.targets)


def _family(fact: CodeFact, canonical) -> tuple:
    """What a fact has in common with its repeats in one definition: its kind and text.

    The fingerprint confirms that the text is the one it was made from. Where it is not,
    as for text cut at the storage limit, the fact is matched by its fingerprint alone.
    """
    text = canonical(fact.text)
    made = fact_fingerprint(
        symbol=fact.symbol_id, kind=fact.kind.value, text=text, ordinal=fact.ordinal
    )
    return (fact.kind, text) if made == fact.fingerprint else (fact.kind, fact.fingerprint)


def _where(fact: CodeFact) -> tuple[int, int]:
    return fact.range.start_line, fact.range.start_column or 0


def _same_statements(base: dict, head: dict, canonical: dict, kept: dict[int, int]) -> dict:
    """Base fingerprint to head fingerprint for the facts of one definition that stayed.

    A fingerprint tells the repeats of one text apart by counting them, so it names the
    same statement on both sides only while no repeat came or went before it. Repeats
    are matched by where they are instead. `kept` maps a base line to its head line for
    the lines that read the same on both sides.
    """
    if not any(fact.ordinal for fact in (*base.values(), *head.values())):
        return {fingerprint: fingerprint for fingerprint in base.keys() & head.keys()}
    families: dict[tuple, tuple[list[CodeFact], list[CodeFact]]] = {}
    for side, facts in enumerate((base, head)):
        for fact in facts.values():
            render = canonical.get(fact.language.value, _plain)
            families.setdefault(_family(fact, render), ([], []))[side].append(fact)
    same: dict[str, str] = {}
    for old, new in families.values():
        old.sort(key=_where)
        new.sort(key=_where)
        # A statement on a line that did not change is the statement that was there.
        waiting: dict[int, list[int]] = {}
        for index, fact in enumerate(new):
            waiting.setdefault(fact.range.start_line, []).append(index)
        fixed: list[tuple[int, int]] = []
        for index, fact in enumerate(old):
            there = waiting.get(kept.get(fact.range.start_line, 0))
            if there and (not fixed or there[0] > fixed[-1][1]):
                fixed.append((index, there.pop(0)))
        # What is left between two of those is taken in order, as far as it goes.
        pairs, first_old, first_new = list(fixed), 0, 0
        for last_old, last_new in (*fixed, (len(old), len(new))):
            pairs += zip(range(first_old, last_old), range(first_new, last_new), strict=False)
            first_old, first_new = last_old + 1, last_new + 1
        for index_old, index_new in pairs:
            same[old[index_old].fingerprint] = new[index_new].fingerprint
    return same


def _symbol_changes(
    symbol_id: str, base: dict, head: dict, moved: dict, same: dict[str, str]
) -> list[RawChange]:
    """Changes among the facts of one definition that exists on both sides.

    `same` pairs the facts that stayed: base fingerprint to head fingerprint.
    """
    back = {after: before for before, after in same.items()}
    gone = sorted((base[fp] for fp in base.keys() - same.keys()), key=_evaluation_order)
    new = sorted((head[fp] for fp in head.keys() - back.keys()), key=_evaluation_order)
    module_level = symbol_id.endswith("#<module>")
    changes: list[RawChange] = []

    def add(kind: str, before: CodeFact | None, after: CodeFact | None) -> RawChange:
        shown = after or before
        change = RawChange(
            kind=ChangeKind(kind),
            symbol_id=symbol_id,
            before=_fact_part(before) if before else None,
            after=_fact_part(after) if after else None,
            base_anchors={before.fingerprint} if before else set(),
            head_anchors={after.fingerprint} if after else set(),
            guards=tuple(guard.fingerprint for guard in shown.guards),
            module_level=module_level,
        )
        changes.append(change)
        return change

    for kind, (added, removed, modified) in _KINDS.items():
        old = [fact for fact in gone if fact.kind == kind]
        fresh = [fact for fact in new if fact.kind == kind]
        pairs = _pair(old, fresh)
        paired = {id(fact) for pair in pairs for fact in pair}
        for before, after in pairs:
            add(modified, before, after)
        for fact in old:
            if id(fact) not in paired:
                add(removed, fact, None)
        for fact in fresh:
            if id(fact) not in paired:
                add(added, None, fact)

    # The same expression can lead somewhere else, for example after an import changed.
    for fingerprint in sorted(same):
        before, after = base[fingerprint], head[same[fingerprint]]
        if before.kind != FactKind.call:
            continue
        was, now = _targets(before, moved), frozenset(after.target.targets)
        if was and now and was != now:
            change = add("call_target_changed", before, after)
            change.details.append(
                f"Now resolves to {', '.join(sorted(now))}; before: {', '.join(sorted(was))}."
            )

    # A condition or loop whose text is unchanged but whose behaviour is not. Notes are
    # kept by the base fingerprint of the condition or loop they are about.
    notes: dict[str, list[str]] = {}
    shifted: dict[str, list[CodeFact]] = {}
    for fact, verb in (*((fact, "removed") for fact in gone), *((fact, "added") for fact in new)):
        if fact.kind not in _JUMPS or not fact.loops:
            continue
        loop = fact.loops[-1] if fact.side == BASE else back.get(fact.loops[-1])
        if loop in same:
            notes.setdefault(loop, []).append(f"`{fact.text}` {verb} inside the loop.")
    repeated_base = Counter((fact.kind, _flat(fact.text)) for fact in base.values())
    repeated_head = Counter((fact.kind, _flat(fact.text)) for fact in head.values())
    for fingerprint in sorted(same):
        before, after = base[fingerprint], head[same[fingerprint]]
        key = (before.kind, _flat(before.text))
        if before.kind in _JUMPS or repeated_base[key] > 1 or repeated_head[key] > 1:
            continue
        # An added, removed or modified guard is already reported and explains the move,
        # so only the guards that stayed are compared.
        was = {guard.fingerprint: guard.branch for guard in before.guards}
        now = {
            back[guard.fingerprint]: guard.branch
            for guard in after.guards
            if guard.fingerprint in back
        }
        for guard in sorted(was.keys() | now.keys()):
            if guard not in same or was.get(guard) == now.get(guard):
                continue
            moved_from = f"branch '{was[guard]}'" if guard in was else "outside it"
            moved_to = f"branch '{now[guard]}'" if guard in now else "outside it"
            notes.setdefault(guard, []).append(
                f"`{_short(before.text, 80)}` moved from {moved_from} to {moved_to}."
            )
            shifted.setdefault(guard, []).extend((before, after))
    for guard in sorted(notes):
        kind = "loop_bound_changed" if base[guard].kind == FactKind.loop else "condition_modified"
        change = add(kind, base[guard], head[same[guard]])
        change.details.extend(dict.fromkeys(notes[guard]))
        change.covers.extend(
            (fact.side, change.before.path, fact.range.start_line, fact.range.end_line)
            for fact in shifted.get(guard, ())
        )

    # An expression nested in another changed expression is the same edit: keep the outer.
    by_size = sorted(changes, key=_size)
    dropped: set[int] = set()

    def same(inner: Part | None, outer: Part | None) -> bool:
        return (
            inner is not None
            and outer is not None
            and (inner.path, inner.start, inner.end) == (outer.path, outer.start, outer.end)
        )

    for change in by_size:
        # `if f(x):` is a condition and a call over the same text: keep the condition.
        whole = change.kind in _CALL_KINDS
        outer = next(
            (
                other
                for other in by_size
                if other is not change
                and id(other) not in dropped
                and (
                    _inside(change.after, other.after)
                    or _inside(change.before, other.before)
                    or (
                        whole
                        and other.kind not in _CALL_KINDS
                        and (same(change.after, other.after) or same(change.before, other.before))
                    )
                )
            ),
            None,
        )
        if outer is None or change.details:
            continue
        outer.base_anchors |= change.base_anchors
        outer.head_anchors |= change.head_anchors
        dropped.add(id(change))
    return [change for change in changes if id(change) not in dropped]


def _size(change: RawChange) -> tuple:
    part = change.after or change.before
    return (part.end[0] - part.start[0], part.end[1] - part.start[1], part.start)


class _Sources:
    """Reads frozen text and mints evidence for ranges no fact covers."""

    def __init__(self, source, catalog: dict[str, EvidenceRef]):
        self.source, self.catalog = source, catalog
        self.minted: dict[str, EvidenceRef] = {}
        self._aligned: dict[str, list | None] = {}
        self._kept: dict[str, dict[int, int]] = {}

    def lines(self, side, path) -> list[str]:
        return self.source.read_text(side, path).split("\n")

    def aligned(self, path) -> list | None:
        """How the lines of a file line up between the sides, indentation aside.

        None when the file is too large to compare line by line.
        """
        if path not in self._aligned:
            old = [line.strip() for line in self.lines(BASE, path)]
            new = [line.strip() for line in self.lines(HEAD, path)]
            self._aligned[path] = (
                None
                if len(old) * len(new) > LINE_BUDGET
                else SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
            )
        return self._aligned[path]

    def kept(self, path) -> dict[int, int]:
        """Base line to head line, for the lines that read the same on both sides."""
        if path not in self._kept:
            self._kept[path] = {
                i1 + offset + 1: j1 + offset + 1
                for tag, i1, i2, j1, _ in self.aligned(path) or ()
                if tag == "equal"
                for offset in range(i2 - i1)
            }
        return self._kept[path]

    def cite(self, side, path, first: int, last: int) -> str:
        ref = self.source.evidence(side, path, ReferenceRange(start_line=first, end_line=last))
        if ref.evidence_id not in self.catalog:
            self.minted[ref.evidence_id] = ref
        return ref.evidence_id


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block_text(lines: list[str], first: int, last: int) -> str:
    chosen = [line.rstrip() for line in lines[first - 1 : last]]
    depth = min((_indent(line) for line in chosen if line.strip()), default=0)
    text = "\n".join(line[depth:] for line in chosen)
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def _header(symbol: CodeSymbol, lines: list[str]) -> str:
    """The lines that introduce a definition: its decorators and its signature line."""
    name = symbol.qualified_name.rsplit(".", 1)[-1]
    first = symbol.range.start_line
    last = min(first + HEADER_LINES, symbol.range.end_line)
    for number in range(first, last + 1):
        # The name as it is being defined, not as it may appear inside a decorator.
        if re.search(rf"\b{re.escape(name)}\s*[(:=<{{]", lines[number - 1]):
            return _block_text(lines, first, number)
    return f"{symbol.kind} {symbol.qualified_name}"


def _symbol_part(symbol: CodeSymbol, sources: _Sources, label: str | None = None) -> Part:
    start, end = _span(symbol.range)
    if symbol.kind == "module":
        evidence = sources.cite(symbol.side, symbol.path, 1, 1)
    else:
        # The whole definition, decorators included: they often carry the business meaning.
        evidence = sources.cite(symbol.side, symbol.path, start[0], end[0])
    text = label or _header(symbol, sources.lines(symbol.side, symbol.path))
    return Part(
        side=symbol.side,
        text=_short(text, TEXT_LIMIT) if label else text,
        anchor=fact_fingerprint(symbol=symbol.symbol_id, kind="symbol", text=symbol.kind),
        evidence_ids=(evidence,),
        path=symbol.path,
        start=start,
        end=end,
    )


def _fold_blocks(changes: list[RawChange], by_symbol, sources: _Sources) -> list[RawChange]:
    """Report a branch or loop that came or went once, with everything inside it.

    A new `if` with a `raise` under it is one edit to a reader, not a condition and a
    result. The change keeps the identity of the condition or loop and shows the block.
    """
    absorbed: set[int] = set()
    for side, kinds in _BLOCK_KINDS.items():

        def part(change: RawChange, side=side) -> Part | None:
            return change.after if side == HEAD else change.before

        def only_here(change: RawChange, side=side) -> bool:
            other = change.before if side == HEAD else change.after
            return part(change) is not None and other is None

        blocks = sorted(
            (change for change in changes if change.kind in kinds),
            key=lambda change: (part(change).path, part(change).start),
        )
        for change in blocks:
            if id(change) in absorbed:
                continue
            head = part(change)
            lines = sources.lines(side, head.path)
            first, last = head.start[0], head.end[0]
            guarded = by_symbol[side].get(change.symbol_id, {}).values()
            for fact in guarded:
                if any(guard.fingerprint == head.anchor for guard in fact.guards):
                    last = max(last, fact.range.end_line)
            # The body is whatever follows more deeply indented than the opening line.
            depth = _indent(lines[first - 1])
            while last < len(lines) and (not lines[last].strip() or _indent(lines[last]) > depth):
                last += 1
            while last > head.end[0] and not lines[last - 1].strip():
                last -= 1
            for other in changes:
                inner = part(other)
                if (
                    other is change
                    or id(other) in absorbed
                    or other.details
                    or other.is_test
                    or not only_here(other)
                    or inner.path != head.path
                    or not first <= inner.start[0] <= inner.end[0] <= last
                ):
                    continue
                absorbed.add(id(other))
                change.base_anchors |= other.base_anchors
                change.head_anchors |= other.head_anchors
                change.base_symbols += other.base_symbols
                change.head_symbols += other.head_symbols
            block = Part(
                side=side,
                text=_block_text(lines, first, last),
                anchor=head.anchor,
                evidence_ids=(sources.cite(side, head.path, first, last),),
                path=head.path,
                start=(first, 0),
                end=(last, 10**9),
            )
            if side == HEAD:
                change.after = block
            else:
                change.before = block
    return [change for change in changes if id(change) not in absorbed]


def _innermost(symbols: list[CodeSymbol], line: int) -> CodeSymbol | None:
    holding = [s for s in symbols if s.range.start_line <= line <= s.range.end_line]
    return min(holding, key=lambda s: s.range.end_line - s.range.start_line, default=None)


def _plain(text: str) -> str:
    return " ".join(text.split())


def _source_changes(path, by_path, covered, sources, comment, canonical) -> list[RawChange]:
    """Changed lines of one file that no reported fact change accounts for."""
    old_lines, new_lines = sources.lines(BASE, path), sources.lines(HEAD, path)
    opcodes = sources.aligned(path)
    if opcodes is None:
        raise OverflowError(path)
    old = [line.strip() for line in old_lines]
    new = [line.strip() for line in new_lines]

    def left(lines, first, last, side):
        return [
            number
            for number in range(first + 1, last + 1)
            if lines[number - 1]
            and not lines[number - 1].startswith(comment)
            and not _STRUCTURAL.match(lines[number - 1])
            and number not in covered[side]
        ]

    def part(side, numbers, raw, symbol, ordinal):
        chosen = [raw[number - 1].rstrip() for number in numbers]
        indent = min(len(line) - len(line.lstrip()) for line in chosen)
        text = "\n".join(line[indent:] for line in chosen)
        return Part(
            side=side,
            text=text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…",
            anchor=fact_fingerprint(
                symbol=symbol.symbol_id, kind="source", text=_flat(text), ordinal=ordinal
            ),
            evidence_ids=(sources.cite(side, path, numbers[0], numbers[-1]),),
            path=path,
            start=(numbers[0], 0),
            end=(numbers[-1], 10**9),
        )

    changes, seen = [], Counter()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        gone, fresh = left(old, i1, i2, BASE), left(new, j1, j2, HEAD)
        if not gone and not fresh:
            continue
        # The same tokens laid out differently are not a change.
        if canonical("\n".join(old_lines[i1:i2])) == canonical("\n".join(new_lines[j1:j2])):
            continue
        side, line = (HEAD, fresh[0]) if fresh else (BASE, gone[0])
        symbol = _innermost(by_path[side], line)
        if symbol is None:
            continue
        kind = (
            "source_modified" if gone and fresh else ("source_added" if fresh else "source_removed")
        )
        seen[(symbol.symbol_id, kind)] += 1
        ordinal = seen[(symbol.symbol_id, kind)] - 1
        before_symbol = _innermost(by_path[BASE], gone[0]) if gone else None
        changes.append(
            RawChange(
                kind=ChangeKind(kind),
                symbol_id=symbol.symbol_id,
                before=part(BASE, gone, old_lines, before_symbol or symbol, ordinal)
                if gone
                else None,
                after=part(HEAD, fresh, new_lines, symbol, ordinal) if fresh else None,
                module_level=symbol.kind != "function",
            )
        )
    return changes


def diff_facts(
    facts: FactSet,
    source,
    *,
    test_paths: frozenset[tuple[EvidenceSide, str]] = frozenset(),
    renames: dict[str, str] | None = None,
    canonical: dict[str, object] | None = None,
) -> FactDiff:
    """Every change between the two sides of `facts`, in a stable order.

    `canonical` maps a language to a function that renders source so that layout does
    not matter; without one, only whitespace is ignored.
    """
    renames = renames or {}
    canonical = canonical or {}
    sources = _Sources(source, {ref.evidence_id: ref for ref in facts.evidence})
    symbols: dict[EvidenceSide, dict[str, CodeSymbol]] = {BASE: {}, HEAD: {}}
    for symbol in facts.symbols:
        symbols[symbol.side][symbol.symbol_id] = symbol
    by_symbol: dict[EvidenceSide, dict[str, dict[str, CodeFact]]] = {BASE: {}, HEAD: {}}
    for fact in facts.facts:
        by_symbol[fact.side].setdefault(fact.symbol_id, {})[fact.fingerprint] = fact
    base, head = symbols[BASE], symbols[HEAD]

    def is_test(symbol: CodeSymbol) -> bool:
        return (symbol.side, symbol.path) in test_paths

    # Definitions that only moved: a renamed file keeps every name, anything else has to
    # be the only definition with that name and content on both sides.
    moved: dict[str, str] = {}
    for old_path, new_path in renames.items():
        for symbol_id in base:
            path, _, name = symbol_id.partition("#")
            if path == old_path and f"{new_path}#{name}" in head:
                moved[symbol_id] = f"{new_path}#{name}"
    groups: dict[tuple, tuple[list, list]] = {}
    for side, own, other in ((0, base, head), (1, head, base)):
        for symbol_id, symbol in own.items():
            if symbol.kind == "module" or symbol_id in other:
                continue
            if symbol_id in moved or symbol_id in moved.values():
                continue
            key = (symbol.kind, symbol.source_digest, symbol.qualified_name.rsplit(".", 1)[-1])
            groups.setdefault(key, ([], []))[side].append(symbol_id)
    for old_ids, new_ids in groups.values():
        if len(old_ids) == len(new_ids) == 1:
            moved[old_ids[0]] = new_ids[0]
    arrived = set(moved.values())
    gone = {key for key in base if key not in head and key not in moved}
    new = {key for key in head if key not in base and key not in arrived}

    def top(symbol_id: str, among) -> bool:
        return not any(parent in among for parent in _ancestors(symbol_id))

    def family(symbol_id: str, own) -> tuple[str, ...]:
        return tuple(sorted(key for key in own if key == symbol_id or symbol_id in _ancestors(key)))

    def anchors(symbol_ids, side) -> set[str]:
        return {fp for symbol_id in symbol_ids for fp in by_symbol[side].get(symbol_id, ())}

    changes: list[RawChange] = []
    for old_path, new_path in sorted(renames.items()):
        before, after = base.get(f"{old_path}#<module>"), head.get(f"{new_path}#<module>")
        if before is None or after is None or is_test(after):
            continue
        members = family(after.symbol_id, head) + tuple(
            key for key in head if key.startswith(new_path + "#")
        )
        changes.append(
            RawChange(
                kind=ChangeKind.symbol_moved,
                symbol_id=after.symbol_id,
                before=_symbol_part(before, sources, f"file {old_path}"),
                after=_symbol_part(after, sources, f"file {new_path}"),
                head_symbols=tuple(dict.fromkeys(members)),
                head_anchors=anchors(members, HEAD),
                module_level=True,
            )
        )
    renamed = {f"{path}#" for path in renames}
    for old_id, new_id in sorted(moved.items()):
        if any(old_id.startswith(prefix) for prefix in renamed):
            continue
        before, after = base[old_id], head[new_id]
        if is_test(after) or not top(old_id, moved):
            continue
        members = family(new_id, head)
        changes.append(
            RawChange(
                kind=ChangeKind.symbol_moved,
                symbol_id=new_id,
                before=_symbol_part(before, sources, f"{before.kind} {old_id}"),
                after=_symbol_part(after, sources, f"{after.kind} {new_id}"),
                base_symbols=family(old_id, base),
                head_symbols=members,
                head_anchors=anchors(members, HEAD),
            )
        )
    for own, among, side, kind in (
        (base, gone, BASE, ChangeKind.symbol_removed),
        (head, new, HEAD, ChangeKind.symbol_added),
    ):
        for symbol_id in sorted(among):
            symbol = own[symbol_id]
            if symbol.kind == "module" or is_test(symbol) or not top(symbol_id, among):
                continue
            members = family(symbol_id, own)
            part = _symbol_part(symbol, sources)
            changes.append(
                RawChange(
                    kind=kind,
                    symbol_id=symbol_id,
                    before=part if side == BASE else None,
                    after=part if side == HEAD else None,
                    base_symbols=members if side == BASE else (),
                    head_symbols=members if side == HEAD else (),
                    base_anchors=anchors(members, BASE) if side == BASE else set(),
                    head_anchors=anchors(members, HEAD) if side == HEAD else set(),
                )
            )

    # Test code is reported per function, never fact by fact.
    functions_changed = {
        key
        for key in base.keys() & head.keys()
        if base[key].kind == "function" and base[key].source_digest != head[key].source_digest
    }
    for own, among, side, kind in (
        (base, gone, BASE, ChangeKind.test_removed),
        (head, new, HEAD, ChangeKind.test_added),
        (head, functions_changed, HEAD, ChangeKind.test_modified),
    ):
        for symbol_id in sorted(among):
            symbol = own[symbol_id]
            if symbol.kind != "function" or not is_test(symbol):
                continue
            if any(
                parent in among and own[parent].kind == "function"
                for parent in _ancestors(symbol_id)
            ):
                continue
            label = f"test {symbol.qualified_name}"
            before = base.get(symbol_id) if kind != ChangeKind.test_added else None
            after = head.get(symbol_id) if kind != ChangeKind.test_removed else None
            changes.append(
                RawChange(
                    kind=kind,
                    symbol_id=symbol_id,
                    before=_symbol_part(before, sources, label) if before else None,
                    after=_symbol_part(after, sources, label) if after else None,
                    is_test=True,
                )
            )

    whole = [
        change
        for change in changes
        if change.kind in {ChangeKind.symbol_added, ChangeKind.symbol_removed}
    ]
    stayed: dict[str, dict[str, str]] = {}
    for symbol_id in sorted(base.keys() & head.keys()):
        if is_test(head[symbol_id]):
            continue
        old_facts = by_symbol[BASE].get(symbol_id, {})
        new_facts = by_symbol[HEAD].get(symbol_id, {})
        # Same facts under different branches are a change too, so compare whenever the
        # definition's text differs, not only when a fact appeared or disappeared.
        if (
            old_facts.keys() != new_facts.keys()
            or base[symbol_id].source_digest != head[symbol_id].source_digest
            or any(
                fact.kind == FactKind.call
                and _targets(fact, moved) != frozenset(new_facts[fp].target.targets)
                for fp, fact in old_facts.items()
            )
        ):
            pairs = _same_statements(
                old_facts, new_facts, canonical, sources.kept(head[symbol_id].path)
            )
            stayed[symbol_id] = pairs
            for change in _symbol_changes(symbol_id, old_facts, new_facts, moved, pairs):
                # A decorator of an added or removed function is part of that definition.
                holder = next(
                    (
                        other
                        for other in whole
                        if _inside(change.before, other.before)
                        or _inside(change.after, other.after)
                    ),
                    None,
                )
                if holder is None:
                    changes.append(change)
                else:
                    holder.base_anchors |= change.base_anchors
                    holder.head_anchors |= change.head_anchors

    # Whatever else changed in a file, line by line, outside the ranges reported so far.
    covered: dict[EvidenceSide, dict[str, set[int]]] = {BASE: {}, HEAD: {}}

    def cover(side, path, first, last):
        covered[side].setdefault(path, set()).update(range(first, last + 1))

    for change in changes:
        for part in (change.before, change.after):
            if part is not None and change.kind != ChangeKind.symbol_moved:
                cover(part.side, part.path, part.start[0], part.end[0])
        for extra in change.covers:
            cover(*extra)
    languages = {(item.side, item.path): item.language.value for item in facts.files}

    def rendered(symbol: CodeSymbol) -> str:
        lines = sources.lines(symbol.side, symbol.path)
        text = "\n".join(lines[symbol.range.start_line - 1 : symbol.range.end_line])
        return canonical.get(languages.get((symbol.side, symbol.path)), _plain)(text)

    # A definition with the same content on both sides only moved, in the file or out of it.
    same = {key: key for key in base.keys() & head.keys()}
    for old_id, new_id in {**same, **moved}.items():
        before, after = base[old_id], head[new_id]
        if before.kind == "module" or is_test(after):
            continue
        if before.source_digest == after.source_digest or rendered(before) == rendered(after):
            cover(BASE, before.path, before.range.start_line, before.range.end_line)
            cover(HEAD, after.path, after.range.start_line, after.range.end_line)
    for side in (BASE, HEAD):
        for facts_of in by_symbol[side].values():
            for fact in facts_of.values():
                if fact.kind in _JUMPS:
                    cover(
                        side,
                        fact.symbol_id.partition("#")[0],
                        fact.range.start_line,
                        fact.range.end_line,
                    )
    by_path: dict[EvidenceSide, dict[str, list[CodeSymbol]]] = {BASE: {}, HEAD: {}}
    for side in (BASE, HEAD):
        for symbol in symbols[side].values():
            by_path[side].setdefault(symbol.path, []).append(symbol)
    analyzed = {(item.side, item.path) for item in facts.files if item.status == "analyzed"}
    skipped = []
    for path in sorted(path for side, path in analyzed if side == HEAD):
        if (BASE, path) not in analyzed or (HEAD, path) in test_paths:
            continue
        if source.read_text(BASE, path) == source.read_text(HEAD, path):
            continue
        try:
            changes.extend(
                _source_changes(
                    path,
                    {side: by_path[side].get(path, []) for side in (BASE, HEAD)},
                    {side: covered[side].get(path, set()) for side in (BASE, HEAD)},
                    sources,
                    _COMMENT.get(languages[(HEAD, path)], "#"),
                    canonical.get(languages[(HEAD, path)], _plain),
                )
            )
        except OverflowError:
            skipped.append(path)

    changes = _fold_blocks(changes, by_symbol, sources)

    def order(change: RawChange):
        part = change.after or change.before
        return (change.is_test, part.path, part.start, change.kind.value, change.symbol_id)

    changes.sort(key=order)
    return FactDiff(
        changes=changes[:MAX_CHANGES],
        evidence=sources.minted,
        moved=moved,
        same=stayed,
        truncated=len(changes) > MAX_CHANGES,
        skipped_files=tuple(skipped),
    )

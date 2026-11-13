from __future__ import annotations

import hashlib
import re
from functools import lru_cache

from genesis_contracts import EvidenceRef
from genesis_contracts.models import SourceExcerpt


class FrozenSnapshotReader:
    """Read evidence only from captured text; never fall through to a live worktree."""

    def __init__(
        self, evidence: tuple[EvidenceRef, ...], excerpts: tuple[SourceExcerpt, ...]
    ) -> None:
        self._evidence = {item.evidence_id: item for item in evidence}
        self._excerpts = {item.evidence_id: item for item in excerpts}
        if len(self._evidence) != len(evidence):
            raise ValueError("evidence_id values must be unique")
        if len(self._excerpts) != len(excerpts):
            raise ValueError("excerpt evidence_id values must be unique")
        if not self._excerpts.keys() <= self._evidence.keys():
            raise ValueError("excerpt has no matching evidence reference")
        for evidence_id, excerpt in self._excerpts.items():
            actual = "sha256:" + hashlib.sha256(excerpt.text.encode("utf-8")).hexdigest()
            if actual != self._evidence[evidence_id].snippet_digest:
                raise ValueError(f"snippet digest mismatch for {evidence_id}")

    def evidence_catalog(self) -> tuple[EvidenceRef, ...]:
        return tuple(self._evidence.values())

    def read_excerpt(self, evidence_id: str) -> SourceExcerpt:
        try:
            return self._excerpts[evidence_id]
        except KeyError as error:
            raise KeyError(f"no captured excerpt for evidence_id {evidence_id}") from error


_PHYSICAL_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|$)")
_LINE_ENDING = re.compile(r"(?:\r\n|\r|\n)$")


def physical_lines(text: str) -> tuple[str, ...]:
    """The lines of a source text, each with its line ending.

    str.splitlines also splits Unicode separators and form feeds. Those are source
    characters, not newlines in Python's physical line numbering.
    """
    return tuple(match.group() for match in _PHYSICAL_LINE.finditer(text) if match.group())


@lru_cache(maxsize=64)
def _recent_lines(text: str) -> tuple[str, ...]:
    return physical_lines(text)


def slice_source(text, span):
    """1-based inclusive lines, zero-based Unicode columns, exclusive end column.

    Missing columns mean the entire first/last line, without final line ending.
    Internal line endings are preserved, including CRLF.
    """
    return slice_lines(_recent_lines(text), span)


def slice_lines(lines, span):
    """`slice_source` for a text that is already split, so many ranges cost one split."""
    if span.start_line > len(lines) or span.end_line > len(lines):
        raise ValueError("evidence range exceeds file lines")
    chosen = lines[span.start_line - 1 : span.end_line]
    contents = [_LINE_ENDING.sub("", line) for line in chosen]
    start = span.start_column if span.start_column is not None else 0
    end = span.end_column if span.end_column is not None else len(contents[-1])
    if start > len(contents[0]) or end > len(contents[-1]):
        raise ValueError("evidence column exceeds line length")
    if len(chosen) == 1:
        if end < start:
            raise ValueError("evidence range is reversed")
        return contents[0][start:end]
    return chosen[0][start:] + "".join(chosen[1:-1]) + contents[-1][:end]

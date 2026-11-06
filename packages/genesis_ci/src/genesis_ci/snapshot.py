from __future__ import annotations

import hashlib
from typing import Protocol

from genesis_contracts import EvidenceRef
from genesis_contracts.models import SourceExcerpt


class SnapshotReader(Protocol):
    def evidence_catalog(self) -> tuple[EvidenceRef, ...]: ...

    def read_excerpt(self, evidence_id: str) -> SourceExcerpt: ...


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

    def read_selected(self, evidence_ids: tuple[str, ...]) -> tuple[SourceExcerpt, ...]:
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("selected evidence IDs must be unique")
        return tuple(self.read_excerpt(evidence_id) for evidence_id in evidence_ids)

    @classmethod
    def from_directory(cls, root, manifest, evidence):
        """Capture manifest bytes once; validate paths, digests, and source ranges."""
        from pathlib import Path

        root = Path(root).absolute()
        captured = {}
        for file in manifest.files:
            path = root / file.side.value / file.path
            for candidate in (path, *path.parents):
                if candidate.is_symlink():
                    raise ValueError("snapshot inputs cannot use symlinks")
            raw = path.read_bytes()
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            if digest != file.content_digest:
                raise ValueError(f"file digest mismatch: {file.side}/{file.path}")
            captured[(file.side, file.path)] = (raw.decode("utf-8"), file.kind)
        excerpts = []
        for ref in evidence:
            if ref.snapshot_id != manifest.snapshot_id:
                raise ValueError("evidence snapshot mismatch")
            source = captured.get((ref.side, ref.path))
            if source is None or source[1] != ref.kind:
                raise ValueError("evidence is absent from manifest or kind differs")
            text = slice_source(source[0], ref.range)
            excerpts.append(SourceExcerpt(evidence_id=ref.evidence_id, text=text))
        return cls(evidence, tuple(excerpts))


def slice_source(text, span):
    """1-based inclusive lines, zero-based Unicode columns, exclusive end column.

    Missing columns mean the entire first/last line, without final line ending.
    Internal line endings are preserved, including CRLF.
    """
    import re

    # str.splitlines also splits Unicode separators and form feeds. Those are
    # source characters, not newlines in Python's physical line numbering.
    lines = [
        match.group() for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text) if match.group()
    ]
    if span.start_line > len(lines) or span.end_line > len(lines):
        raise ValueError("evidence range exceeds file lines")
    chosen = lines[span.start_line - 1 : span.end_line]
    contents = [re.sub(r"(?:\r\n|\r|\n)$", "", line) for line in chosen]
    start = span.start_column if span.start_column is not None else 0
    end = span.end_column if span.end_column is not None else len(contents[-1])
    if start > len(contents[0]) or end > len(contents[-1]):
        raise ValueError("evidence column exceeds line length")
    if len(chosen) == 1:
        if end < start:
            raise ValueError("evidence range is reversed")
        return contents[0][start:end]
    return chosen[0][start:] + "".join(chosen[1:-1]) + contents[-1][:end]

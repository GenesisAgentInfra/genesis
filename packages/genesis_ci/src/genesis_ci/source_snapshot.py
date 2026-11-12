"""Immutable bytes for A2, and an evidence-registration view for B4."""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Mapping

from genesis_contracts.models import (
    EvidenceRef,
    EvidenceSide,
    ReferenceRange,
    SnapshotManifest,
    SourceExcerpt,
    evidence_id_for,
    validate_repo_path,
)

from .snapshot import FrozenSnapshotReader, physical_lines, slice_lines


def content_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class FrozenSourceSnapshot:
    """Copies its input mapping; reads never access Git or the working directory."""

    def __init__(
        self, manifest: SnapshotManifest, files: Mapping[tuple[EvidenceSide, str], bytes]
    ) -> None:
        catalog = {(item.side, item.path): item for item in manifest.files}
        if set(files) != set(catalog):
            raise ValueError("frozen files must match manifest exactly")
        captured = {}
        for key, raw in files.items():
            if not isinstance(raw, bytes):
                raise TypeError("frozen file content must be immutable bytes")
            if content_digest(raw) != catalog[key].content_digest:
                raise ValueError("frozen file digest mismatch")
            captured[key] = raw
        self._manifest = manifest
        self._files = MappingProxyType(captured)
        self._catalog = MappingProxyType(catalog)
        # Decoded text and its lines, kept per file: evidence is cut from the same file
        # thousands of times, and decoding or splitting it each time dominated analysis.
        self._texts: dict[tuple[EvidenceSide, str], str] = {}
        self._lines: dict[tuple[EvidenceSide, str], tuple[str, ...]] = {}

    @property
    def manifest(self) -> SnapshotManifest:
        return self._manifest

    def list_files(self, side: EvidenceSide) -> tuple[str, ...]:
        return tuple(sorted(path for file_side, path in self._files if file_side == side))

    def read_bytes(self, side: EvidenceSide, path: str) -> bytes:
        validate_repo_path(path)
        try:
            return self._files[(side, path)]
        except KeyError as error:
            raise KeyError(f"file not captured: {side}/{path}") from error

    def read_text(self, side: EvidenceSide, path: str) -> str:
        # UTF-8 is the initial supported capture encoding; preserve BOM and CRLF.
        key = (side, path)
        if key not in self._texts:
            self._texts[key] = self.read_bytes(side, path).decode("utf-8")
        return self._texts[key]

    def slice(self, side: EvidenceSide, path: str, span: ReferenceRange) -> str:
        """The text of one range of a captured file."""
        key = (side, path)
        if key not in self._lines:
            self._lines[key] = physical_lines(self.read_text(side, path))
        return slice_lines(self._lines[key], span)

    def evidence(self, side: EvidenceSide, path: str, span: ReferenceRange) -> EvidenceRef:
        return _evidence_ref(
            self.manifest.snapshot_id,
            side,
            path,
            span,
            self.slice(side, path, span),
            self._catalog[(side, path)].kind,
        )


def _evidence_ref(snapshot_id: str, side, path: str, span, snippet: str, kind) -> EvidenceRef:
    digest = content_digest(snippet.encode("utf-8"))
    return EvidenceRef(
        evidence_id=evidence_id_for(
            snapshot_id=snapshot_id, side=side, path=path, range=span, digest=digest
        ),
        snapshot_id=snapshot_id,
        side=side,
        path=path,
        range=span,
        snippet_digest=digest,
        kind=kind,
    )


class SingleFileSource:
    """The evidence view of one captured file, for analyzing it in another process.

    It yields the same references as the whole snapshot would for that file.
    """

    def __init__(self, snapshot_id: str, side: EvidenceSide, path: str, raw: bytes, kind):
        self._snapshot_id, self._key, self._kind = snapshot_id, (side, path), kind
        self._lines = physical_lines(raw.decode("utf-8"))

    def evidence(self, side: EvidenceSide, path: str, span: ReferenceRange) -> EvidenceRef:
        if (side, path) != self._key:
            raise KeyError(f"file not captured: {side}/{path}")
        snippet = slice_lines(self._lines, span)
        return _evidence_ref(self._snapshot_id, side, path, span, snippet, self._kind)


class EvidenceRegistry:
    """A2 registers located evidence; freeze() gives B4 the existing reader interface."""

    def __init__(self, source: FrozenSourceSnapshot) -> None:
        self._source = source
        self._refs: dict[str, EvidenceRef] = {}

    def register(self, side: EvidenceSide, path: str, span: ReferenceRange) -> EvidenceRef:
        ref = self._source.evidence(side, path, span)
        self._refs[ref.evidence_id] = ref
        return ref

    def get(self, evidence_id: str) -> EvidenceRef | None:
        return self._refs.get(evidence_id)

    def refs(self) -> dict[str, EvidenceRef]:
        return dict(self._refs)

    def adopt(self, refs: dict[str, EvidenceRef]) -> None:
        """Take over references registered for one file in another process."""
        self._refs.update(refs)

    def freeze(self) -> FrozenSnapshotReader:
        refs = tuple(self._refs[key] for key in sorted(self._refs))
        excerpts = tuple(
            SourceExcerpt(
                evidence_id=ref.evidence_id,
                text=self._source.slice(ref.side, ref.path, ref.range),
            )
            for ref in refs
        )
        return FrozenSnapshotReader(refs, excerpts)

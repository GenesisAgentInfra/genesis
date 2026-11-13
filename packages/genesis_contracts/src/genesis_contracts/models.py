from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=False, allow_inf_nan=False
    )


class SectionStatus(StrEnum):
    analyzed = "analyzed"
    insufficient_context = "insufficient_context"
    unsupported = "unsupported"


class EvidenceSide(StrEnum):
    base = "base"
    head = "head"


class EvidenceKind(StrEnum):
    code = "code"
    intent = "intent"
    flow = "flow"
    test = "test"
    config = "config"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"


class ReferenceRange(ContractModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: int | None = Field(default=None, ge=0)
    end_column: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def range_is_ordered(self) -> ReferenceRange:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if (
            self.end_line == self.start_line
            and self.start_column is not None
            and self.end_column is not None
            and self.end_column < self.start_column
        ):
            raise ValueError("end_column must be >= start_column on a single line")
        return self


class EvidenceRef(ContractModel):
    evidence_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    side: EvidenceSide
    path: str = Field(min_length=1)
    range: ReferenceRange
    snippet_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: EvidenceKind

    @model_validator(mode="after")
    def safe_relative_path(self) -> EvidenceRef:
        validate_repo_path(self.path)
        expected_id = evidence_id_for(
            snapshot_id=self.snapshot_id,
            side=self.side,
            path=self.path,
            range=self.range,
            digest=self.snippet_digest,
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match its snapshot, path, range, and digest")
        return self


def validate_repo_path(path: str) -> None:
    if not path or any(ord(char) < 32 for char in path):
        raise ValueError("path must not be empty or contain control characters")
    if path.startswith(("/", "\\")) or "\\" in path or re.match(r"^[A-Za-z]:", path):
        raise ValueError("path must be a repository-relative POSIX path")
    if any(segment in {"", ".", ".."} for segment in path.split("/")):
        raise ValueError("path contains an invalid segment")


def evidence_id_for(
    *, snapshot_id: str, side: EvidenceSide, path: str, range: ReferenceRange, digest: str
) -> str:
    identity = "\0".join(
        (
            snapshot_id,
            side.value,
            path,
            str(range.start_line),
            str(range.end_line),
            str(range.start_column),
            str(range.end_column),
            digest,
        )
    )
    return "ev_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


class FileIdentity(ContractModel):
    path: str = Field(min_length=1)
    side: EvidenceSide
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: EvidenceKind

    @model_validator(mode="after")
    def safe_relative_path(self) -> FileIdentity:
        validate_repo_path(self.path)
        return self


def snapshot_id_for(
    *,
    base_revision: str | None,
    head_revision: str | None,
    files: tuple[FileIdentity, ...],
) -> str:
    identity = {
        "base_revision": base_revision,
        "head_revision": head_revision,
        "files": [
            item.model_dump(mode="json")
            for item in sorted(
                files, key=lambda item: (item.side.value, item.path, item.kind.value)
            )
        ],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SnapshotManifest(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    base_revision: str | None = None
    head_revision: str | None = None
    files: tuple[FileIdentity, ...]
    integrity_status: Literal["complete", "partial"]
    omitted_inputs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identity_matches_manifest(self) -> SnapshotManifest:
        file_keys = [(item.side, item.path) for item in self.files]
        if len(file_keys) != len(set(file_keys)):
            raise ValueError("snapshot file identities must be unique by side and path")
        expected = snapshot_id_for(
            base_revision=self.base_revision,
            head_revision=self.head_revision,
            files=self.files,
        )
        if self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match the version identities and file manifest")
        return self


class CapabilityStatus(ContractModel):
    status: SectionStatus
    reason: str | None = None
    analyzed_scope: str | None = None

    @model_validator(mode="after")
    def explain_missing_capability(self) -> CapabilityStatus:
        if self.status != SectionStatus.analyzed and not self.reason:
            raise ValueError("unsupported/incomplete capability requires a reason")
        return self


class Limitation(ContractModel):
    code: str
    message: str
    evidence_ids: tuple[str, ...] = ()
    affects_completeness: bool = False


class Resolution(ContractModel):
    status: Literal["resolved", "candidate", "unknown"]
    targets: tuple[str, ...] = ()
    reason: str | None = None

    @model_validator(mode="after")
    def explain_resolution(self) -> Resolution:
        if self.status != "resolved" and not self.reason:
            raise ValueError("candidate/unknown resolution requires a reason")
        if self.status == "unknown" and self.targets:
            raise ValueError("unknown resolution cannot assert targets; use candidate")
        return self


class SymbolFact(ContractModel):
    symbol_id: str
    side: EvidenceSide
    kind: Literal["function", "class", "module"]
    is_async: bool = False
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ImportFact(ContractModel):
    import_id: str
    side: EvidenceSide
    module: str
    imported_name: str | None = None
    alias: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class CallFact(ContractModel):
    call_id: str
    side: EvidenceSide
    caller_symbol_id: str
    expression: str
    target: Resolution
    awaited: bool
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ExpressionFact(ContractModel):
    fact_id: str
    side: EvidenceSide
    symbol_id: str
    expression: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class UnresolvedFact(ContractModel):
    unresolved_id: str
    feature: Literal["import", "call", "tool", "prompt", "control_flow", "test", "other"]
    reason: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class FactPack(ContractModel):
    coverage: CapabilityStatus
    functions: tuple[SymbolFact, ...] = ()
    imports: tuple[ImportFact, ...] = ()
    calls: tuple[CallFact, ...] = ()
    conditions: tuple[ExpressionFact, ...] = ()
    awaits: tuple[ExpressionFact, ...] = ()
    prompt_refs: tuple[ExpressionFact, ...] = ()
    tool_refs: tuple[ExpressionFact, ...] = ()
    unresolved: tuple[UnresolvedFact, ...] = ()


class FileChange(ContractModel):
    change_type: Literal["added", "modified", "deleted", "renamed"]
    base_path: str | None = None
    head_path: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_sides(self) -> FileChange:
        for path in (self.base_path, self.head_path):
            if path is not None:
                validate_repo_path(path)
        expected = {
            "added": (False, True),
            "deleted": (True, False),
            "modified": (True, True),
            "renamed": (True, True),
        }[self.change_type]
        if (self.base_path is not None, self.head_path is not None) != expected:
            raise ValueError("file change paths do not match change_type")
        return self


class ChangeSet(ContractModel):
    files: tuple[FileChange, ...]
    changed_symbol_ids: tuple[str, ...]
    unresolved: tuple[str, ...] = ()


class SourceExcerpt(ContractModel):
    evidence_id: str
    text: str


def validate_evidence_refs(
    *, snapshot_id: str, evidence: tuple[EvidenceRef, ...], evidence_ids: tuple[str, ...]
) -> None:
    by_id = {item.evidence_id: item for item in evidence}
    if len(by_id) != len(evidence):
        raise ValueError("evidence_id values must be unique")
    invalid = sorted(set(evidence_ids) - by_id.keys())
    if invalid:
        raise ValueError(f"unknown evidence_id values: {', '.join(invalid)}")
    if any(item.snapshot_id != snapshot_id for item in evidence):
        raise ValueError("evidence reference snapshot_id does not match analysis snapshot")

"""Local A1 contracts. These are not exported in the public or HTTP schemas."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .models import (
    CapabilityStatus,
    ContractModel,
    EvidenceKind,
    EvidenceSide,
    FileChange,
    SnapshotManifest,
    validate_repo_path,
)


class SnapshotInput(ContractModel):
    path: str
    kind: EvidenceKind

    @model_validator(mode="after")
    def relative_path(self) -> SnapshotInput:
        validate_repo_path(self.path)
        return self


class SnapshotLimits(ContractModel):
    max_files: int = Field(default=5000, gt=0)
    max_file_bytes: int = Field(default=1_048_576, gt=0)
    max_total_bytes: int = Field(default=32 * 1_048_576, gt=0)
    max_metadata_bytes: int = Field(default=16 * 1_048_576, gt=0)
    git_timeout_seconds: int = Field(default=30, gt=0)
    worktree_attempts: int = Field(default=2, ge=1, le=3)


class SnapshotSpec(ContractModel):
    """base is mandatory; head=None means the final working directory content."""

    base: str = Field(min_length=1)
    head: str | None = Field(default=None, min_length=1)
    include_untracked: bool = False
    inputs: tuple[SnapshotInput, ...] = ()
    exclude_paths: tuple[str, ...] = ()
    limits: SnapshotLimits = Field(default_factory=SnapshotLimits)

    @model_validator(mode="after")
    def validate_selection(self) -> SnapshotSpec:
        if self.head is not None and self.include_untracked:
            raise ValueError("include_untracked applies only to worktree snapshots")
        if len({item.path for item in self.inputs}) != len(self.inputs):
            raise ValueError("explicit input paths must be unique")
        for path in self.exclude_paths:
            validate_repo_path(path)
        return self


class SnapshotOmission(ContractModel):
    side: EvidenceSide
    path: str
    reason: Literal[
        "excluded",
        "secret_path",
        "outside_scope",
        "symlink",
        "submodule",
        "special_file",
        "binary",
        "unsupported_encoding",
        "file_budget",
        "total_budget",
        "count_budget",
        "missing_input",
        "untracked_not_selected",
    ]
    affects_completeness: bool

    @model_validator(mode="after")
    def safe_path(self) -> SnapshotOmission:
        validate_repo_path(self.path)
        return self


class FileDelta(ContractModel):
    change: FileChange
    base_mode: Literal["100644", "100755"] | None = None
    head_mode: Literal["100644", "100755"] | None = None

    @model_validator(mode="after")
    def mode_matches_side(self) -> FileDelta:
        if (self.base_mode is None) != (self.change.base_path is None):
            raise ValueError("base mode must correspond to base path")
        if (self.head_mode is None) != (self.change.head_path is None):
            raise ValueError("head mode must correspond to head path")
        return self


class FileDiff(ContractModel):
    """File-stage comparison only: deliberately has no changed_symbol_ids field."""

    changes: tuple[FileDelta, ...]
    coverage: CapabilityStatus
    symbol_status: Literal["not_analyzed"] = "not_analyzed"
    rename_detection: Literal["unique_exact_content"] = "unique_exact_content"


class CapturedMode(ContractModel):
    side: EvidenceSide
    path: str
    mode: Literal["100644", "100755"]


class SnapshotCapture(ContractModel):
    format_version: Literal[1] = 1
    spec: SnapshotSpec
    manifest: SnapshotManifest
    head_commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    modes: tuple[CapturedMode, ...]
    file_diff: FileDiff
    omissions: tuple[SnapshotOmission, ...]
    worktree_consistency: Literal["not_applicable", "two_matching_reads"]

    @model_validator(mode="after")
    def coherent_capture(self) -> SnapshotCapture:
        files = {(item.side, item.path): item for item in self.manifest.files}
        modes = {(item.side, item.path): item.mode for item in self.modes}
        if len(modes) != len(self.modes) or modes.keys() != files.keys():
            raise ValueError("capture mode catalog must match manifest files exactly")
        omitted = tuple(
            f"{item.side.value}:{item.path}:{item.reason}"
            for item in self.omissions
            if item.affects_completeness
        )
        if self.manifest.omitted_inputs != omitted:
            raise ValueError("manifest omissions must match capture omissions")
        if self.manifest.integrity_status != ("partial" if omitted else "complete"):
            raise ValueError("capture integrity must reflect omitted inputs")
        expected_coverage = "insufficient_context" if omitted else "analyzed"
        if self.file_diff.coverage.status != expected_coverage:
            raise ValueError("file diff coverage must reflect omitted inputs")
        if self.spec.head is not None:
            if (
                self.worktree_consistency != "not_applicable"
                or self.manifest.head_revision != self.head_commit
            ):
                raise ValueError("commit capture must preserve its resolved head identity")
        else:
            if self.worktree_consistency != "two_matching_reads":
                raise ValueError("worktree capture requires matching reads")
            identity = json.dumps(
                {
                    "anchor": self.head_commit,
                    "files": [
                        [path, modes[(side, path)], files[(side, path)].content_digest]
                        for side, path in sorted(files)
                        if side == EvidenceSide.head
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            expected = "worktree:" + hashlib.sha256(identity.encode()).hexdigest()
            if self.manifest.head_revision != expected:
                raise ValueError("worktree identity does not match captured content and modes")
        seen: set[tuple[EvidenceSide, str]] = set()
        for delta in self.file_diff.changes:
            for side, path, mode in (
                (EvidenceSide.base, delta.change.base_path, delta.base_mode),
                (EvidenceSide.head, delta.change.head_path, delta.head_mode),
            ):
                if path is None:
                    continue
                key = (side, path)
                if key in seen or key not in files or modes[key] != mode:
                    raise ValueError("file delta repeats or misidentifies a captured file")
                if any(
                    item.affects_completeness
                    and (path == item.path or path.startswith(item.path + "/"))
                    for item in self.omissions
                ):
                    raise ValueError("file delta cannot assert changes for omitted input")
                seen.add(key)
        return self

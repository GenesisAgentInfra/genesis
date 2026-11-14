"""Versioned local snapshot artifacts, with digest verification on every load."""

from __future__ import annotations

import json
import os
from pathlib import Path

from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotCapture, SnapshotLimits

from .git_snapshot import CapturedSnapshot, SnapshotError, _read_worktree
from .source_snapshot import FrozenSourceSnapshot


def save_snapshot(snapshot: CapturedSnapshot, destination: Path) -> None:
    """Write a new private directory. Refuse to replace an existing artifact."""
    destination = destination.absolute()
    if any(path.is_symlink() for path in destination.parents):
        raise SnapshotError("artifact_symlink", "Artifact parent paths cannot use symlinks.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700, exist_ok=False)
    blobs = destination / "blobs"
    blobs.mkdir(mode=0o700)
    written = set()
    for file in snapshot.capture.manifest.files:
        digest = file.content_digest.removeprefix("sha256:")
        if digest in written:
            continue
        with (blobs / digest).open("xb") as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(snapshot.source.read_bytes(file.side, file.path))
        written.add(digest)
    # Metadata is the completion marker; partial writes never look like complete captures.
    payload = json.dumps(snapshot.capture.model_dump(mode="json"), ensure_ascii=False, indent=2)
    with (destination / "snapshot.json").open("x", encoding="utf-8") as stream:
        os.chmod(stream.fileno(), 0o600)
        stream.write(payload + "\n")


def load_snapshot(destination: Path, *, limits: SnapshotLimits | None = None) -> CapturedSnapshot:
    """Loading is repository-independent and never falls back to live files."""
    limits = limits or SnapshotLimits()
    root = destination.absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise SnapshotError("artifact_symlink", "Artifact paths cannot use symlinks.")
    raw, _, reason = _read_worktree(root, "snapshot.json", limits.max_metadata_bytes)
    if raw is None or reason:
        raise SnapshotError("invalid_artifact", "Snapshot metadata is missing or exceeds limits.")
    capture = SnapshotCapture.model_validate_json(raw)
    # The limits count distinct content, as capturing does: both sides of a change
    # name mostly the same blobs, and each is stored and read once.
    if len({item.content_digest for item in capture.manifest.files}) > limits.max_files:
        raise SnapshotError("invalid_artifact", "Snapshot file count exceeds loader limits.")
    expected_keys = {(item.side, item.path) for item in capture.manifest.files}
    modes = {(item.side, item.path) for item in capture.modes}
    if len(modes) != len(capture.modes) or modes != expected_keys:
        raise SnapshotError("invalid_artifact", "Snapshot mode catalog differs from manifest.")
    files: dict[tuple[EvidenceSide, str], bytes] = {}
    blobs: dict[str, bytes] = {}
    total = 0
    for file in capture.manifest.files:
        if file.content_digest not in blobs:
            path = "blobs/" + file.content_digest.removeprefix("sha256:")
            raw, _, reason = _read_worktree(
                root, path, min(limits.max_file_bytes, limits.max_total_bytes - total)
            )
            if raw is None or reason:
                raise SnapshotError(
                    "invalid_artifact", "Snapshot blob is missing, unsafe, or exceeds limits."
                )
            blobs[file.content_digest] = raw
            total += len(raw)
        files[(file.side, file.path)] = blobs[file.content_digest]
    source = FrozenSourceSnapshot(capture.manifest, files)
    return CapturedSnapshot(capture, source)

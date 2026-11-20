"""Prepare a session by freezing source files of any language. Nothing is parsed."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path, PurePosixPath

from genesis_contracts.models import EvidenceKind, EvidenceSide
from genesis_contracts.snapshot import SnapshotLimits, SnapshotSpec

from genesis_ci.business_map.store import (
    OTHER_CHANGE_LIMIT,
    keep_private,
    other_changes,
    session_root,
    write_json,
)
from genesis_ci.git_snapshot import _Git, capture_snapshot
from genesis_ci.size import left_out as size_left_out
from genesis_ci.snapshot_store import save_snapshot

# What counts as source to read. Data, documents and lock files are left out: a flow
# is described from code, and a change to another file is listed by name only.
SOURCE_SUFFIXES = frozenset(
    "c cc clj cpp cs dart erl ex exs go h hpp java jl js jsx kt kts lua m mjs cjs mm php pl "
    "py r rb rs scala sh sql svelte swift ts tsx vue".split()
)
_TEST_FOLDERS = {"test", "tests", "__tests__", "spec", "specs", "e2e"}
_TEST_MARKS = (".test.", ".spec.", "_test.", "_spec.")


class NoSource(ValueError):
    """The repository has no source file the snapshot can hold."""

    code = "unsupported_repository"


def is_test_path(path: str) -> bool:
    folders = path.lower().split("/")
    name = folders.pop()
    return (
        bool(_TEST_FOLDERS & set(folders))
        or name.startswith("test_")
        or any(mark in name for mark in _TEST_MARKS)
    )


def _is_source(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.rpartition(".")[2] in SOURCE_SUFFIXES and ".min." not in name


def source_paths(repo: Path, base: str | None, head: str | None, untracked: bool) -> list[str]:
    """Every source path either side of the comparison has, by name alone."""
    git = _Git(repo, SnapshotLimits())
    found: set[str] = set()
    for ref in (base, head):
        if ref is not None:
            found.update(git.tree(git.revision(ref)))
    if head is None:
        listings = [("ls-files", "-z")]
        if untracked:
            listings.append(("ls-files", "--others", "--exclude-standard", "-z"))
        for listing in listings:
            found.update(
                raw.decode("utf-8", "replace") for raw in git.run(*listing).split(b"\0") if raw
            )
    return sorted(path for path in found if _is_source(path))


def prepare(
    repo: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    include_untracked: bool = False,
    exclude: tuple[str, ...] = (),
    max_files: int | None = None,
) -> dict:
    """Freeze the source of both sides and open a session. No model is called."""
    repo = repo.expanduser().resolve(strict=True)
    paths = source_paths(repo, base, head, include_untracked)
    spec = SnapshotSpec(
        base=base,
        head=head,
        include_untracked=include_untracked,
        exclude_paths=exclude,
        **({"limits": SnapshotLimits(max_files=max_files)} if max_files else {}),
        inputs=[
            {"path": path, "kind": EvidenceKind.test if is_test_path(path) else EvidenceKind.code}
            for path in paths
        ],
    )
    snapshot = capture_snapshot(repo, spec)
    manifest = snapshot.capture.manifest
    frozen = [item.path for item in manifest.files if item.side == EvidenceSide.head]
    if not frozen:
        raise NoSource("No source file could be read from this repository.")
    # The Python workflow names a session by the same snapshot; the two never share one.
    identity = hashlib.sha256(("agent\0" + manifest.snapshot_id).encode("utf-8")).hexdigest()
    session_id = "ses_" + identity[:16]
    root = session_root(repo, session_id)
    keep_private(repo)
    session = {
        "format_version": 1,
        "session_id": session_id,
        "engine": "agent",
        "snapshot_id": manifest.snapshot_id,
        "mode": "map" if base is None else "change",
        "base_revision": manifest.base_revision,
        "head_revision": manifest.head_revision,
        "integrity_status": manifest.integrity_status,
    }
    missing = size_left_out(snapshot.capture)
    if missing:
        session["files_over_size_limit"] = missing
    if base is not None:
        others = other_changes(
            repo,
            manifest.base_revision,
            snapshot.capture.head_commit if head is not None else None,
            {item.path for item in manifest.files},
        )
        session.update(base_ref=base, head_ref=head)
        write_json(
            root / "changed-files.json",
            {"total": len(others), "files": others[:OTHER_CHANGE_LIMIT]},
        )
    if not (root / "snapshot").exists():
        # Later commands read source only from this frozen copy, never from the live tree.
        save_snapshot(snapshot, root / "snapshot")
    write_json(root / "session.json", session)
    from .workspace import Workspace

    workspace = Workspace(repo, session_id)
    resumed = workspace.plan is not None
    business_map = workspace.assemble()
    suffixes = Counter(PurePosixPath(path).suffix.lower() for path in frozen)
    return {
        **session,
        "analysis_status": business_map.analysis_status,
        "resumed": resumed,
        "session_path": str(root),
        "files": len(frozen),
        "file_types": dict(suffixes.most_common(5)),
        "flows": len(business_map.flows),
        "steps": sum(len(flow.steps) for flow in business_map.flows),
        **workspace.change_counts(),
    }

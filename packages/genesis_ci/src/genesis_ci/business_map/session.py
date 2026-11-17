"""Prepare a session from Python source: snapshot, static facts and the skeleton map."""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path

from genesis_contracts.facts import FactSet
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec

from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_ci.python.extract import gc_paused
from genesis_ci.snapshot_store import save_snapshot

from .python_facts import collect_file, python_facts, python_source_roots
from .skeleton import build_skeleton
from .store import (
    OTHER_CHANGE_LIMIT,
    evidence_bundle,
    keep_private,
    other_changes,
    session_root,
    write_json,
    write_text,
)

# A map that skips the largest modules of a project misses its core. Real projects
# have source files of several thousand lines, far above the limits the report
# pipeline uses, so the map workflow reads whatever the snapshot itself accepted.
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_NODES = 1_000_000
# Parsing and visiting files is the bulk of the work and independent per file. A small
# repository is done before a pool of processes has started, so it stays in one.
PARALLEL_FILES = 64
MAX_WORKERS = 8


class UnsupportedRepository(ValueError):
    """The repository has no source in a supported language."""

    code = "unsupported_repository"


def _tracked_extensions(repo: Path) -> list[str]:
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True, timeout=30
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return []
    counts = Counter(Path(name).suffix.lower() for name in listing.split("\0") if name)
    return [f"{suffix or '(none)'}: {count}" for suffix, count in counts.most_common(5)]


def _workers(files) -> int:
    """How many processes to analyze source files in. `GENESIS_WORKERS` overrides it."""
    configured = os.environ.get("GENESIS_WORKERS", "")
    if configured.isdigit():
        return max(1, int(configured))
    sources = sum(1 for item in files if item.path.endswith((".py", ".pyi")))
    if sources < PARALLEL_FILES:
        return 1
    return max(1, min(os.cpu_count() or 1, MAX_WORKERS))


def prepare(
    repo: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    include_untracked: bool = False,
    exclude: tuple[str, ...] = (),
) -> dict:
    """Freeze a snapshot, extract facts and write the static skeleton. No model is called."""
    repo = repo.expanduser().resolve(strict=True)
    spec = SnapshotSpec(
        base=base, head=head, include_untracked=include_untracked, exclude_paths=exclude
    )
    snapshot = capture_snapshot(repo, spec)
    roots = python_source_roots(item.path for item in snapshot.capture.manifest.files)
    options = PythonOptions(
        source_roots=roots, max_file_bytes=MAX_SOURCE_BYTES, max_nodes=MAX_SOURCE_NODES
    )
    extraction = extract_python(
        snapshot,
        options,
        workers=_workers(snapshot.capture.manifest.files),
        collect=collect_file,
        # The fact set built from it is validated as a whole below.
        validate=False,
    )
    with gc_paused():
        facts = python_facts(extraction)
    analyzed = [item for item in facts.files if item.side == "head" and item.status == "analyzed"]
    if not analyzed:
        found = ", ".join(_tracked_extensions(repo)) or "no tracked files"
        raise UnsupportedRepository(
            "No Python source could be analyzed; `--engine agent` reads other languages. "
            f"Most common tracked file types: {found}."
        )
    skeleton = build_skeleton(facts)
    manifest = snapshot.capture.manifest
    session_id = "ses_" + manifest.snapshot_id.removeprefix("sha256:")[:16]
    root = session_root(repo, session_id)
    keep_private(repo)
    session = {
        "format_version": 1,
        "session_id": session_id,
        "engine": "python",
        "snapshot_id": manifest.snapshot_id,
        "mode": "map" if base is None else "change",
        "base_revision": manifest.base_revision,
        "head_revision": manifest.head_revision,
        "integrity_status": manifest.integrity_status,
    }
    if base is not None:
        others = other_changes(
            repo,
            manifest.base_revision,
            snapshot.capture.head_commit if head is not None else None,
            {item.path for item in manifest.files},
        )
        session.update(base_ref=base, head_ref=head)
        # Names only, kept beside the session so they do not crowd every status output.
        write_json(
            root / "changed-files.json",
            {"total": len(others), "files": others[:OTHER_CHANGE_LIMIT]},
        )
    if not (root / "snapshot").exists():
        # Later commands read source only from this frozen copy, never from the live tree.
        save_snapshot(snapshot, root / "snapshot")
    write_json(root / "session.json", session)
    # Read by programs only, and large: written compactly, straight from the model.
    write_text(root / "facts.json", facts.model_dump_json(exclude_none=True) + "\n")
    from .workspace import Workspace

    resumed = (root / "plan.json").is_file()
    if resumed:
        # Same content, same session: keep the plan and every accepted flow.
        workspace = Workspace(repo, session_id)
        skeleton = workspace.assemble()
        report = workspace.stored_report()
    else:
        write_json(root / "business-map.json", skeleton.model_dump(mode="json", exclude_none=True))
        bundle = evidence_bundle(snapshot, skeleton.evidence)
        write_json(root / "evidence-bundle.json", bundle.model_dump(mode="json"))
        # In a change session the first report is placed on the skeleton.
        report = Workspace(repo, session_id).refresh_change() if base is not None else None
    change = {}
    if report is not None:
        change = {
            "change_status": report.analysis_status,
            "changes": len(report.changes),
            "changes_placed": sum(
                1 for item in report.changes if item.projection.status != "unassigned"
            ),
            "changed_files_not_analyzed": len(report.unanalyzed_changes),
        }
    entries = Counter(entry.detection.value for entry in facts.entries if entry.side == "head")
    unsupported = [item.path for item in facts.files if item.status == "unsupported"]
    return {
        **session,
        "analysis_status": skeleton.analysis_status,
        "resumed": resumed,
        "session_path": str(root),
        "files_analyzed": len(analyzed),
        "files_unsupported": sorted(set(unsupported)),
        "entries": {"adapter": 0, "root_heuristic": 0, **dict(sorted(entries.items()))},
        "flows": len(skeleton.flows),
        "steps": sum(len(flow.steps) for flow in skeleton.flows),
        "limitations": [item.code for item in skeleton.limitations],
        **change,
    }


def load_facts(repo: Path, session_id: str) -> FactSet:
    root = session_root(repo.expanduser().resolve(strict=True), session_id)
    return FactSet.model_validate_json((root / "facts.json").read_text(encoding="utf-8"))

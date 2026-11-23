"""Prepare a session from Python source: snapshot, static facts and the skeleton map."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from genesis_contracts.business_map import MapMode
from genesis_contracts.facts import CodeEntry, FactSet
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotLimits, SnapshotSpec

from genesis_ci.git_snapshot import (
    SnapshotError,
    capture_snapshot,
    changed_paths,
    may_capture,
    tracked_paths,
    untracked_paths,
)
from genesis_ci.python import extract_python
from genesis_ci.python.extract import gc_paused
from genesis_ci.size import left_out as size_left_out
from genesis_ci.snapshot_store import save_snapshot

from .carried import CARRIED, carry, check_planned, latest_map, named_map, read_carried, reported
from .python_facts import collect_file, python_facts, python_source_roots
from .skeleton import build_skeleton
from .store import (
    OTHER_CHANGE_LIMIT,
    evidence_bundle,
    keep_commit_digests,
    keep_private,
    other_changes,
    session_root,
    unread_reason,
    unread_untracked,
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
        listing = tracked_paths(repo)
    except SnapshotError:
        return []
    counts = Counter(Path(name).suffix.lower() for name in listing)
    return [f"{suffix or '(none)'}: {count}" for suffix, count in counts.most_common(5)]


def _other_languages(repo: Path, spec: SnapshotSpec) -> dict | None:
    """Source files in languages the Python engine does not read, counted by file type.

    One run reads a project one way. When most of what it is asked about is in another
    language, the Python engine covers a minority of it and the agent engine is the
    better choice: the result says so, so that the choice does not rest on a guess. A
    map is asked about the whole project; a review only about the files it changes.
    Only files a capture can read are counted, as the agent engine would read them:
    nothing in `.genesis/`, a dependency, build or cache folder, or `--exclude`.
    """
    from genesis_ci.agent_map.session import _is_source, source_paths

    base, head = spec.base, spec.head
    try:
        if base is None:
            paths = source_paths(repo, base, head, spec.include_untracked, spec.exclude_paths)
        else:
            changed = [path for _, path in changed_paths(repo, base, head)]
            if head is None and spec.include_untracked:
                changed += untracked_paths(repo, spec)
            paths = sorted(
                {path for path in changed if _is_source(path) and may_capture(path, spec)}
            )
    except SnapshotError:
        return None
    python = sum(1 for path in paths if path.endswith((".py", ".pyi")))
    others = Counter(
        Path(path).suffix.lower() for path in paths if not path.endswith((".py", ".pyi"))
    )
    if not others:
        return None
    total = sum(others.values())
    found = {
        "scope": "project" if base is None else "changed",
        "python_files": python,
        "other_files": total,
        "by_type": dict(others.most_common(5)),
    }
    if total > python:
        what = "source files" if base is None else "changed source files"
        found["note"] = (
            f"{total} {what} are in other languages and {python} in Python; this run "
            "reads the Python files only. Run prepare again with --engine agent to read "
            "them all."
        )
    return found


def _workers(files) -> int:
    """How many processes to analyze source files in. `GENESIS_WORKERS` overrides it."""
    configured = os.environ.get("GENESIS_WORKERS", "")
    if configured.isdigit():
        return max(1, int(configured))
    sources = sum(1 for item in files if item.path.endswith((".py", ".pyi")))
    if sources < PARALLEL_FILES:
        return 1
    return max(1, min(os.cpu_count() or 1, MAX_WORKERS))


def _untracked(repo: Path, spec: SnapshotSpec) -> list[str]:
    try:
        return unread_untracked(repo, spec)
    except SnapshotError:
        return []


def prepare(
    repo: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    include_untracked: bool = False,
    exclude: tuple[str, ...] = (),
    max_files: int | None = None,
    entries_from: str | Path | None = None,
) -> dict:
    """Freeze a snapshot, extract facts and write the static skeleton. No model is called.

    `entries_from` names a `business-map.json` whose agent-proposed entries and flows the
    session starts from. Without it, a review starts from those of the latest map session
    that proposed entries or gave several entries one flow.
    """
    repo = repo.expanduser().resolve(strict=True)
    # Read before the long part, so that a wrong file is refused at once.
    named = named_map(repo, entries_from) if entries_from is not None else None
    spec = SnapshotSpec(
        base=base,
        head=head,
        include_untracked=include_untracked,
        exclude_paths=exclude,
        **({"limits": SnapshotLimits(max_files=max_files)} if max_files else {}),
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
    manifest = snapshot.capture.manifest
    session_id = "ses_" + manifest.snapshot_id.removeprefix("sha256:")[:16]
    root = session_root(repo, session_id)
    planned = (root / "plan.json").is_file()
    # A review starts from the entries and flows of the latest map that proposed entries
    # or grouped them, or from those of the map named. Once a plan exists, the entries it
    # was made with stay as they are.
    carried = {}
    if planned:
        if named is not None:
            check_planned(root, session_id, named)
    elif named is not None:
        carried = carry(named, facts, snapshot.source)
    elif base is not None:
        found = latest_map(repo)
        carried = carry(found, facts, snapshot.source) if found else {}
        if not any(carried.get(key) for key in ("entries", "not_found", "groups")):
            carried = {}
    skeleton = build_skeleton(
        facts,
        carried=tuple(CodeEntry.model_validate(item) for item in carried.get("entries", ())),
        minted=tuple(carried.get("evidence", ())),
        groups=tuple(tuple(group) for group in carried.get("groups", ())),
    )
    keep_private(repo)
    session = {
        "format_version": 1,
        "session_id": session_id,
        "engine": "python",
        "snapshot_id": manifest.snapshot_id,
        "mode": "map" if base is None else "change",
        "base_revision": manifest.base_revision,
        "head_revision": manifest.head_revision,
        "worktree_dirty": snapshot.worktree_dirty,
        "integrity_status": manifest.integrity_status,
    }
    missing = size_left_out(snapshot.capture)
    if missing:
        session["files_over_size_limit"] = missing
    counted = {}
    if base is not None:
        captured = {item.path for item in manifest.files}
        omitted = {item.path: item.reason for item in snapshot.capture.omissions}
        others, folders = other_changes(
            repo,
            manifest.base_revision,
            snapshot.capture.head_commit if head is not None else None,
            captured,
            spec,
            omitted,
        )
        if folders:
            counted["left_out"] = folders
        untracked = _untracked(repo, spec) if head is None else []
        if include_untracked:
            # New files of the change that are not source: listed as added, by name,
            # after the changed tracked files, so that a cut list keeps those.
            listed = {item["path"] for item in others}
            others = [
                *others,
                *(
                    {
                        "path": path,
                        "change": "added",
                        **(
                            {"reason": reason}
                            if (reason := unread_reason(path, spec, omitted))
                            else {}
                        ),
                    }
                    for path in sorted(untracked)
                    if path not in captured and path not in listed
                ),
            ]
        elif untracked:
            # Never left out without a word. Those Genesis would analyze come first.
            readable = {
                item.path
                for item in snapshot.capture.omissions
                if item.reason == "untracked_not_selected"
            }
            ordered = sorted(untracked, key=lambda path: (path not in readable, path))
            counted["untracked"] = {
                "total": len(untracked),
                "analyzable": len(readable & set(untracked)),
                "files": ordered[:OTHER_CHANGE_LIMIT],
            }
        session.update(base_ref=base, head_ref=head)
        # Those listed for a reason other than their language.
        unread = sum(1 for item in others if "reason" in item)
        if unread:
            counted["not_read"] = unread
        # Names only, kept beside the session so they do not crowd every status output.
        write_json(
            root / "changed-files.json",
            {"total": len(others), "files": others[:OTHER_CHANGE_LIMIT], **counted},
        )
    if not (root / "snapshot").exists():
        # Later commands read source only from this frozen copy, never from the live tree.
        save_snapshot(snapshot, root / "snapshot")
    write_json(root / "session.json", session)
    keep_commit_digests(root, snapshot)
    # Read by programs only, and large: written compactly, straight from the model.
    write_text(root / "facts.json", facts.model_dump_json(exclude_none=True) + "\n")
    from .workspace import Workspace

    if planned:
        carried = read_carried(root)
    elif carried:
        write_json(root / CARRIED, {key: carried[key] for key in carried if key != "evidence"})
    else:
        (root / CARRIED).unlink(missing_ok=True)
    # Same content, same session: the plan, every accepted flow and every accepted
    # explanation of a change are kept, and the result says so.
    resumed = planned or (root / "changes" / "accepted.json").is_file()
    if planned:
        workspace = Workspace(repo, session_id)
        skeleton = workspace.assemble()
        report = workspace.stored_report()
    else:
        if carried.get("evidence"):
            Workspace(repo, session_id).adopt_evidence(
                {ref.evidence_id: ref for ref in carried["evidence"]}
            )
        skeleton = skeleton.model_copy(update={"mode": MapMode(session["mode"])})
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
        if "untracked" in counted:
            change["untracked_left_out"] = counted["untracked"]["total"]
    entries = Counter(entry.detection.value for entry in facts.entries if entry.side == "head")
    unsupported = [item.path for item in facts.files if item.status == "unsupported"]
    other = _other_languages(repo, spec)
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
        **({"carried_entries": reported(carried)} if carried else {}),
        **({"other_languages": other} if other else {}),
    }


def load_facts(repo: Path, session_id: str) -> FactSet:
    root = session_root(repo.expanduser().resolve(strict=True), session_id)
    return FactSet.model_validate_json((root / "facts.json").read_text(encoding="utf-8"))

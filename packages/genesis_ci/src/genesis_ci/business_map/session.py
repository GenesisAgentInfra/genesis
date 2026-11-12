"""Local session: one frozen analysis of a repository, kept under `.genesis/`.

`sessions/` and `out/` hold source text and stay private; `prepare` makes sure Git
ignores them. Everything is written to a temporary file and renamed into place.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle, validate_evidence_bundle
from genesis_contracts.facts import FactSet
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec

from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_ci.python.extract import gc_paused
from genesis_ci.snapshot import slice_source
from genesis_ci.snapshot_store import save_snapshot

from .python_facts import collect_file, python_facts, python_source_roots
from .skeleton import build_skeleton

PRIVATE_DIRECTORIES = ("sessions/", "out/")
ARTIFACTS = ("business-map.json", "evidence-bundle.json")
OTHER_CHANGE_LIMIT = 100
# A map that skips the largest modules of a project misses its core. Real projects
# have source files of several thousand lines, far above the limits the report
# pipeline uses, so the map workflow reads whatever the snapshot itself accepted.
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_NODES = 1_000_000
# Parsing and visiting files is the bulk of the work and independent per file. A small
# repository is done before a pool of processes has started, so it stays in one.
PARALLEL_FILES = 64
MAX_WORKERS = 8
_GIT_STATUS = {"A": "added", "D": "deleted"}


class UnsupportedRepository(ValueError):
    """The repository has no source in a supported language."""

    code = "unsupported_repository"


def session_root(repo: Path, session_id: str) -> Path:
    if not session_id.startswith("ses_") or not session_id[4:].isalnum():
        raise ValueError("invalid session id")
    return repo / ".genesis" / "sessions" / session_id


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, data) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _keep_private(repo: Path) -> None:
    ignore = repo / ".genesis" / ".gitignore"
    present = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    missing = [line for line in PRIVATE_DIRECTORIES if line not in present]
    if missing:
        write_text(ignore, "\n".join([*present, *missing]) + "\n")


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


def _other_changes(repo: Path, base: str, head: str | None, captured: set[str]) -> list[dict]:
    """Files changed between the two revisions that the snapshot did not capture.

    Only their names are read. They are listed in the change report so that a change
    outside the analyzed languages is never mistaken for no change.
    """
    command = ["git", "diff", "--name-status", "--no-renames", "-z", base]
    try:
        listing = subprocess.run(
            [*command, *([head] if head else []), "--"],
            cwd=repo,
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return []
    fields = listing.split("\0")
    found = []
    for status, path in zip(fields[::2], fields[1::2], strict=False):
        if path and path not in captured and not path.startswith(".genesis/"):
            found.append({"path": path, "change": _GIT_STATUS.get(status[:1], "modified")})
    return sorted(found, key=lambda item: item["path"])


def evidence_bundle(snapshot, evidence) -> EvidenceBundle:
    """Excerpts of the frozen source for every cited evidence reference."""
    bundle = EvidenceBundle(
        snapshot_id=snapshot.capture.manifest.snapshot_id,
        excerpts=[
            {
                "evidence_id": ref.evidence_id,
                "text": slice_source(snapshot.source.read_text(ref.side, ref.path), ref.range),
            }
            for ref in evidence
        ],
    )
    validate_evidence_bundle(bundle, tuple(evidence))
    return bundle


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
            "No Python source could be analyzed; other languages are not supported yet. "
            f"Most common tracked file types: {found}."
        )
    skeleton = build_skeleton(facts)
    manifest = snapshot.capture.manifest
    session_id = "ses_" + manifest.snapshot_id.removeprefix("sha256:")[:16]
    root = session_root(repo, session_id)
    _keep_private(repo)
    session = {
        "format_version": 1,
        "session_id": session_id,
        "snapshot_id": manifest.snapshot_id,
        "mode": "map" if base is None else "change",
        "base_revision": manifest.base_revision,
        "head_revision": manifest.head_revision,
        "integrity_status": manifest.integrity_status,
    }
    if base is not None:
        others = _other_changes(
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


def load(repo: Path, session_id: str) -> tuple[dict, BusinessMap, EvidenceBundle]:
    """Read and re-validate what a session has stored."""
    root = session_root(repo.expanduser().resolve(strict=True), session_id)
    if not (root / "session.json").is_file():
        raise FileNotFoundError(f"no such session: {session_id}")
    session = json.loads((root / "session.json").read_text(encoding="utf-8"))
    business_map = BusinessMap.model_validate_json(
        (root / "business-map.json").read_text(encoding="utf-8")
    )
    bundle = EvidenceBundle.model_validate_json(
        (root / "evidence-bundle.json").read_text(encoding="utf-8")
    )
    if session.get("snapshot_id") != business_map.snapshot_id:
        raise ValueError("session and map come from different snapshots")
    return session, business_map, bundle


def load_report(repo: Path, session_id: str) -> ChangeReport | None:
    """The change report of a change session; nothing for a plain map session."""
    path = session_root(repo.expanduser().resolve(strict=True), session_id) / "change-report.json"
    if not path.is_file():
        return None
    return ChangeReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_facts(repo: Path, session_id: str) -> FactSet:
    root = session_root(repo.expanduser().resolve(strict=True), session_id)
    return FactSet.model_validate_json((root / "facts.json").read_text(encoding="utf-8"))


def publish(repo: Path, session_id: str, files: dict[str, str]) -> Path:
    """Write rendered output for a session and mirror it to the stable `latest` path."""
    repo = repo.expanduser().resolve(strict=True)
    session_root(repo, session_id)
    out = repo / ".genesis" / "out" / session_id
    for name, text in files.items():
        write_text(out / name, text)
    latest = repo / ".genesis" / "out" / "latest"
    staging = latest.with_name("latest.tmp")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(out, staging)
    shutil.rmtree(latest, ignore_errors=True)
    os.replace(staging, latest)
    return latest

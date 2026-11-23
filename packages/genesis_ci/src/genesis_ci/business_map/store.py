"""Session files under `.genesis/`: what every way of building a map shares.

`sessions/` and `out/` hold source text and stay private; a session makes sure Git
ignores them. Everything is written to a temporary file and renamed into place.
Nothing here knows how a map was analyzed.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from pathlib import Path

from genesis_contracts.business_map import BusinessMap, MapMode
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle, validate_evidence_bundle
from genesis_contracts.snapshot import SnapshotSpec

from genesis_ci.git_snapshot import SnapshotError, changed_paths, left_out_by, untracked_names
from genesis_ci.snapshot import slice_source

PRIVATE_DIRECTORIES = ("sessions/", "out/")
IGNORE_FILE = ".genesis/.gitignore"
OTHER_CHANGE_LIMIT = 100
LISTED_FOLDERS = 5
_GIT_STATUS = {"A": "added", "D": "deleted"}


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


def keep_private(repo: Path) -> None:
    ignore = repo / IGNORE_FILE
    present = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    missing = [line for line in PRIVATE_DIRECTORIES if line not in present]
    if missing:
        write_text(ignore, "\n".join([*present, *missing]) + "\n")


def other_changes(
    repo: Path, base: str, head: str | None, captured: set[str], spec: SnapshotSpec
) -> tuple[list[dict], dict]:
    """Files changed between the two revisions that the snapshot did not capture.

    Only their names are read, the way the snapshot reads Git: no hook or fsmonitor
    runs and the index is not written. They are listed in the change report so that a
    change outside the analyzed languages is never mistaken for no change. Those in a
    folder left out on purpose, Genesis's own `.genesis/` or one passed to `--exclude`,
    are counted by that folder instead: they are not what the change is about, and one
    by one they could crowd its files out of the list. A dependency, build or cache
    folder is no such choice, and a change there, such as to a release script, can
    matter: its files are listed like any other.
    """
    try:
        listing = changed_paths(repo, base, head, spec.limits)
    except SnapshotError:
        return [], {}
    found, folders = [], Counter()
    for status, path in listing:
        if path in captured:
            continue
        folder = left_out_by(path, spec)
        if folder is not None:
            folders[folder] += 1
        else:
            found.append({"path": path, "change": _GIT_STATUS.get(status[:1], "modified")})
    if head is None:
        # Against the working tree, new files in those folders count too. Git does not
        # list what it ignores, such as the sessions, and the `.gitignore` that ignores
        # them is Genesis's own, not part of the change.
        try:
            new = untracked_names(repo, spec.limits)
        except SnapshotError:
            new = []
        listed = {path for _, path in listing}
        for path in new:
            folder = left_out_by(path, spec)
            if folder is not None and path not in listed and path != IGNORE_FILE:
                folders[folder] += 1
    left_out = {}
    if folders:
        left_out = {"total": folders.total(), "folders": dict(folders.most_common(LISTED_FOLDERS))}
    return sorted(found, key=lambda item: item["path"]), left_out


def left_out_limitation(left_out: dict) -> dict:
    """The note a change report carries for the changed files `other_changes` counted."""
    count = left_out["total"]
    shown = left_out["folders"]
    folders = ", ".join(f"{folder}: {number}" for folder, number in shown.items())
    more = ", ..." if sum(shown.values()) < count else ""
    return {
        "code": "changed_files_left_out",
        "message": f"{count} changed file{'s' * (count != 1)} in `.genesis/` or in folders "
        f"passed to `--exclude`: not analyzed ({folders}{more}).",
        "affects_completeness": False,
    }


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


def map_source(session: dict, capture, side: str) -> dict | None:
    """The code a published map was read from: its commit and the digest of each file.

    Nothing when the session does not know whether the files read differ from their
    commit: it was prepared by an earlier version, and preparing again tells.
    """
    if side == "base":
        revision, dirty = capture.manifest.base_revision, False
    else:
        revision, dirty = capture.head_commit, session.get("worktree_dirty")
    if revision is None or dirty is None:
        return None
    omitted = any(item.startswith(side + ":") for item in capture.manifest.omitted_inputs)
    files = sorted(capture.manifest.files, key=lambda item: item.path)
    return {
        "revision": revision,
        "worktree_dirty": dirty,
        "integrity_status": "partial" if omitted else "complete",
        "files": {item.path: item.content_digest for item in files if item.side == side},
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
    if session.get("mode") == "change" and business_map.mode != "change":
        # Stored before maps said which kind they are.
        business_map = business_map.model_copy(update={"mode": MapMode.change})
    return session, business_map, bundle


def load_report(repo: Path, session_id: str) -> ChangeReport | None:
    """The change report of a change session; nothing for a plain map session."""
    path = session_root(repo.expanduser().resolve(strict=True), session_id) / "change-report.json"
    if not path.is_file():
        return None
    return ChangeReport.model_validate_json(path.read_text(encoding="utf-8"))


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

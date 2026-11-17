"""Session files under `.genesis/`: what every way of building a map shares.

`sessions/` and `out/` hold source text and stay private; a session makes sure Git
ignores them. Everything is written to a temporary file and renamed into place.
Nothing here knows how a map was analyzed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle, validate_evidence_bundle

from genesis_ci.snapshot import slice_source

PRIVATE_DIRECTORIES = ("sessions/", "out/")
OTHER_CHANGE_LIMIT = 100
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
    ignore = repo / ".genesis" / ".gitignore"
    present = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    missing = [line for line in PRIVATE_DIRECTORIES if line not in present]
    if missing:
        write_text(ignore, "\n".join([*present, *missing]) + "\n")


def other_changes(repo: Path, base: str, head: str | None, captured: set[str]) -> list[dict]:
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

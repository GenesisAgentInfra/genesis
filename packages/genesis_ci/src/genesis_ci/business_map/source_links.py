"""GitHub evidence links, pinned to the captured commit and checked against local Git.

No network access is needed. Uncommitted excerpts link to the captured committed file
without line anchors, explicitly labelled as a different version by the viewer.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from genesis_contracts.models import EvidenceRef
from genesis_contracts.snapshot import SnapshotCapture, SnapshotLimits

from genesis_ci.git_snapshot import SnapshotError, _Git
from genesis_ci.snapshot import slice_source


def github_repository(remote: str) -> str | None:
    remote = remote.strip()
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote.removeprefix("git@github.com:")
    parsed = urlsplit(remote)
    if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
        return None
    path = parsed.path.strip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        return None
    return "https://github.com/" + path


def github_source_links(
    repo: Path, capture: SnapshotCapture, evidence: tuple[EvidenceRef, ...]
) -> dict[str, dict]:
    git = _Git(repo, SnapshotLimits())
    try:
        repository = github_repository(git.run("remote", "get-url", "origin").decode())
    except (SnapshotError, UnicodeError, ValueError):
        return {}
    if repository is None:
        return {}
    links = {}
    published: dict[str, bool] = {}
    files: dict[tuple[str, str], str | None] = {}
    for ref in evidence:
        revision = capture.manifest.base_revision if ref.side == "base" else capture.head_commit
        if not revision or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            continue
        if revision not in published:
            try:
                published[revision] = bool(
                    git.run(
                        "for-each-ref",
                        "--format=%(refname)",
                        "--contains=" + revision,
                        "refs/remotes/origin/",
                    ).strip()
                )
            except SnapshotError:
                published[revision] = False
        if not published[revision]:
            continue
        key = (revision, ref.path)
        if key not in files:
            try:
                files[key] = git.run(
                    "show", f"{revision}:{ref.path}", limit=git.limits.max_file_bytes
                ).decode("utf-8")
            except (SnapshotError, UnicodeError):
                files[key] = None
        text = files[key]
        if text is None:
            continue
        try:
            snippet = slice_source(text, ref.range)
            exact = "sha256:" + hashlib.sha256(snippet.encode()).hexdigest() == ref.snippet_digest
        except ValueError:
            exact = False
        url = f"{repository}/blob/{revision}/{quote(ref.path, safe='/')}"
        if exact:
            url += f"#L{ref.range.start_line}"
            if ref.range.end_line != ref.range.start_line:
                url += f"-L{ref.range.end_line}"
        links[ref.evidence_id] = {"url": url, "exact": exact}
    return links

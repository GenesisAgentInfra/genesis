"""How much a run reads, before it starts and after it is done.

`prepare` parses every source file it freezes and prints nothing until it is finished,
so a large project needs a warning first: `estimate` counts the files by name, which
takes seconds, and says roughly how long the run will take. After the run,
`left_out` lists the files a limit kept out, so that a result never looks complete
when part of the project was not read.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from genesis_contracts.snapshot import SnapshotCapture, SnapshotLimits

from .git_snapshot import SnapshotError, _Git, changed_paths

# Seconds of `prepare` per source file read, measured on an 8-core machine. A review
# reads both sides of every file and resolves calls across them: about three times a map.
SECONDS_PER_FILE = {"map": 0.14, "change": 0.42}
MEASURED_WORKERS = 8
# Above this, the run takes long enough that the user should hear it first.
TELL_USER_SECONDS = 120
SIZE_REASONS = ("count_budget", "file_budget", "total_budget")
LISTED = 20


def _python(path: str) -> bool:
    return path.endswith((".py", ".pyi"))


def estimate(
    repo: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    include_untracked: bool = False,
    max_files: int | None = None,
) -> dict:
    """The source files a run would read, and roughly how long `prepare` takes on them."""
    from .agent_map.session import _is_source, source_paths

    repo = repo.expanduser().resolve(strict=True)
    # Refuse the way `prepare` would: a folder outside Git, or a repository with no
    # commit, has nothing a run can freeze, and a count of 0 would read as an answer.
    git = _Git(repo, SnapshotLimits())
    try:
        git.run("rev-parse", "--show-toplevel")
    except SnapshotError as error:
        if error.code != "git_read_failed":
            raise
        raise SnapshotError(
            "git_read_failed",
            f"Git could not open {repo} as a repository. Most often it is not inside one: "
            "run `git init` there and commit the files, then try again. If it is a "
            "repository, check that it is owned by the current user.",
        ) from error
    for ref in (base, head or "HEAD"):
        if ref is not None:
            git.revision(ref)
    head_paths = source_paths(repo, None, head, include_untracked and base is None)
    python = [path for path in head_paths if _python(path)]
    engine = "python" if python else "agent"
    read = python if python else head_paths
    mode = "map" if base is None else "change"
    changed = 0
    if base is not None:
        changed = sum(
            1
            for _, path in changed_paths(repo, base, head)
            if (_python(path) if engine == "python" else _is_source(path))
        )
    limit = max_files or SnapshotLimits().max_files
    # A review stores what both sides share once: the head plus what differs.
    counted = len(read) + changed
    workers = max(1, min(os.cpu_count() or 1, MEASURED_WORKERS))
    seconds = round(
        len(read) * SECONDS_PER_FILE[mode] * MEASURED_WORKERS / workers if engine == "python" else 0
    )
    result = {
        "engine": engine,
        "mode": mode,
        "source_files": len(read),
        **({"changed_source_files": changed} if base is not None else {}),
        "file_limit": limit,
        "over_limit": counted > limit,
        "estimated_seconds": seconds,
        "tell_user": seconds >= TELL_USER_SECONDS or counted > limit,
        "largest_folders": dict(
            Counter(path.split("/", 1)[0] if "/" in path else "." for path in read).most_common(5)
        ),
    }
    if engine == "agent":
        result["note"] = (
            "The agent engine only freezes files: prepare takes seconds, and the time goes "
            "into reading the code yourself."
        )
    if counted > limit:
        result["note"] = (
            f"{counted} source files are above the limit of {limit}: files beyond it would "
            "be left out. Pass --max-files to read more, or --exclude to leave folders out."
        )
    return result


def left_out(capture: SnapshotCapture) -> dict | None:
    """The files a size limit kept out of the snapshot, by reason; none when all were read."""
    found: dict[str, str] = {}
    for item in capture.omissions:
        if item.reason in SIZE_REASONS:
            found.setdefault(item.path, item.reason)
    if not found:
        return None
    reasons = Counter(found.values())
    return {
        "total": len(found),
        "by_reason": {reason: reasons[reason] for reason in SIZE_REASONS if reasons[reason]},
        "file_limit": capture.spec.limits.max_files,
        "files": [f"{path} ({reason})" for path, reason in sorted(found.items())[:LISTED]],
    }


def limitation(missing: dict) -> dict:
    """The limitation a result carries when a size limit kept files out."""
    parts = []
    reasons = missing["by_reason"]
    if reasons.get("count_budget"):
        parts.append(
            f"{reasons['count_budget']} beyond the limit of {missing['file_limit']} source "
            "files (prepare --max-files reads more)"
        )
    if reasons.get("file_budget"):
        parts.append(
            f"{reasons['file_budget']} larger than 1 MB, usually generated or vendored code"
        )
    if reasons.get("total_budget"):
        parts.append(f"{reasons['total_budget']} beyond the total size limit")
    shown = ", ".join(missing["files"][:5])
    return {
        "code": "files_over_size_limit",
        "message": f"{missing['total']} source files were not read: "
        + "; ".join(parts)
        + f". This result does not cover them. For example: {shown}.",
        "affects_completeness": True,
    }

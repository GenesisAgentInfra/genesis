"""Read-only Git/worktree capture. No checkout, hooks, filters, imports, or customer tests."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from genesis_contracts.models import (
    EvidenceKind,
    EvidenceSide,
    FileChange,
    FileIdentity,
    SnapshotManifest,
    snapshot_id_for,
    validate_repo_path,
)
from genesis_contracts.snapshot import (
    CapturedMode,
    FileDelta,
    FileDiff,
    SnapshotCapture,
    SnapshotLimits,
    SnapshotOmission,
    SnapshotSpec,
)

from .source_snapshot import FrozenSourceSnapshot, content_digest

BASE = EvidenceSide.base
HEAD = EvidenceSide.head
_EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tox",
    ".nox",
}
_CONFIG_NAMES = {
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "setup.cfg",
    "pytest.ini",
    "tox.ini",
    ".python-version",
}
_REGULAR = {"100644", "100755"}


class SnapshotError(ValueError):
    """Expected capture failure with a stable, non-secret diagnostic code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class _ChangedDuringCapture(Exception):
    pass


@dataclass(frozen=True)
class _Entry:
    mode: str
    oid: str | None
    size: int | None


@dataclass(frozen=True)
class CapturedSnapshot:
    capture: SnapshotCapture
    source: FrozenSourceSnapshot


class _Git:
    def __init__(self, root: Path, limits: SnapshotLimits):
        self.root = root
        self.limits = limits
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_OPTIONAL_LOCKS="0",
            GIT_TERMINAL_PROMPT="0",
            GIT_NO_LAZY_FETCH="1",
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_ATTR_NOSYSTEM="1",
            LC_ALL="C",
        )

    def run(self, *args: str, limit: int | None = None) -> bytes:
        limit = self.limits.max_metadata_bytes if limit is None else limit
        command = [
            "git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "core.quotePath=false",
            *args,
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=self.root,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise SnapshotError("git_unavailable", "Unable to start Git.") from error
        chunks: list[bytes] = []
        count = 0
        deadline = time.monotonic() + self.limits.git_timeout_seconds
        try:
            # Drain both pipes with a shared hard output budget before accumulating bytes.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SnapshotError("git_timeout", "Git exceeded the capture timeout.")
                    for key, _ in selector.select(timeout=min(remaining, 0.2)):
                        block = os.read(key.fileobj.fileno(), min(65536, limit - count + 1))
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        count += len(block)
                        if count > limit:
                            raise SnapshotError(
                                "metadata_budget", "Git output exceeded its byte budget."
                            )
                        if key.data:
                            chunks.append(block)
            remaining = max(0.001, deadline - time.monotonic())
            try:
                returncode = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise SnapshotError("git_timeout", "Git exceeded the capture timeout.") from error
            if returncode:
                raise SnapshotError(
                    "git_read_failed", "Git could not read the repository or object."
                )
            return b"".join(chunks)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()

    def revision(self, ref: str) -> str:
        try:
            raw = self.run("rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        except SnapshotError as error:
            if error.code != "git_read_failed":
                raise
            raise SnapshotError(
                "revision_unavailable",
                "Requested revision is unavailable; supply an existing local commit.",
            ) from error
        revision = raw.decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
            raise SnapshotError("invalid_revision", "Git returned an invalid commit identity.")
        return revision

    def tree(self, revision: str) -> dict[str, _Entry]:
        result = {}
        for row in self.run("ls-tree", "-r", "-l", "-z", "--full-tree", revision).split(b"\0"):
            if not row:
                continue
            meta, raw_path = row.split(b"\t", 1)
            mode, kind, oid, size = meta.split()
            path = _path(raw_path)
            result[path] = _Entry(mode.decode(), oid.decode(), None if size == b"-" else int(size))
        return result


def _path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8")
        validate_repo_path(path)
    except (ValueError, UnicodeDecodeError) as error:
        raise SnapshotError(
            "unsupported_path", "A Git path is not a safe UTF-8 POSIX path."
        ) from error
    return path


# File types a symbolic link can point at without hiding analyzable source.
_DOCUMENT_SUFFIXES = frozenset(
    "md mdx rst txt adoc pdf png jpg jpeg gif svg ico webp csv tsv json yaml yml toml "
    "cfg ini lock html css".split()
)


def _kind(path: str, spec: SnapshotSpec) -> tuple[EvidenceKind | None, str | None]:
    parts = path.split("/")
    name = parts[-1]
    lowered = name.lower()
    # Explicit inputs cannot override secret/generated-path exclusions.
    if (
        lowered == ".env"
        or lowered.startswith(".env.")
        or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".keystore"))
        or lowered in {"id_rsa", "id_ed25519", "credentials", "credentials.json", ".netrc"}
        or any(part in {".ssh", ".aws", ".gnupg"} for part in parts)
    ):
        return None, "secret_path"
    if (
        any(part in _EXCLUDED for part in parts)
        or (".genesis" in parts and path != ".genesis/flows.yaml")
        or any(path == prefix or path.startswith(prefix + "/") for prefix in spec.exclude_paths)
    ):
        return None, "excluded"
    explicit = {item.path: item.kind for item in spec.inputs}
    if path in explicit:
        return explicit[path], None
    if path == ".genesis/flows.yaml":
        return EvidenceKind.flow, None
    if name.endswith((".py", ".pyi")):
        is_test = (
            "tests" in parts
            or "test" in parts
            or name == "conftest.py"
            or name.startswith("test_")
            or name.endswith("_test.py")
        )
        return EvidenceKind.test if is_test else EvidenceKind.code, None
    if name in _CONFIG_NAMES or fnmatch.fnmatch(name, "requirements*.txt"):
        return EvidenceKind.config, None
    return None, "outside_scope"


def _worktree_listing(
    git: _Git, anchor_tree: dict[str, _Entry]
) -> tuple[dict[str, _Entry], set[str]]:
    # Sparse files cannot be mistaken for actual deletions.
    tracked = dict(anchor_tree)
    for row in git.run("ls-files", "--stage", "-z").split(b"\0"):
        if not row:
            continue
        meta, raw_path = row.split(b"\t", 1)
        mode, oid, stage = meta.split()
        if stage != b"0":
            raise SnapshotError(
                "unmerged_index", "Resolve merge conflicts before capturing the worktree."
            )
        tracked[_path(raw_path)] = _Entry(mode.decode(), oid.decode(), None)
    for row in git.run("ls-files", "-t", "-z").split(b"\0"):
        if row.startswith(b"S "):
            raise SnapshotError(
                "sparse_worktree",
                "Sparse worktrees are not supported for live capture; use two commits.",
            )
    others = {
        _path(row)
        for row in git.run("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if row
    }
    return tracked, others


def _read_worktree(
    root: Path, path: str, limit: int
) -> tuple[bytes | None, str | None, str | None]:
    """Open every component relative to a directory FD, never follow a symlink."""
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(directory)
        parts = path.split("/")
        for part in parts[:-1]:
            try:
                directory = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
            except FileNotFoundError:
                return None, None, None
            except OSError:
                return None, None, "symlink"
            descriptors.append(directory)
        try:
            info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return None, None, None
        if stat.S_ISLNK(info.st_mode):
            return None, None, "symlink"
        if not stat.S_ISREG(info.st_mode):
            return None, None, "special_file"
        if info.st_size > limit:
            return None, None, "file_budget"
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError as error:
            raise _ChangedDuringCapture() from error
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise _ChangedDuringCapture()
        raw = bytearray()
        while len(raw) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        try:
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError as error:
            raise _ChangedDuringCapture() from error

        def signature(item):
            return (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mode,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        if (
            signature(info) != signature(before)
            or signature(before) != signature(after)
            or signature(after) != signature(current)
        ):
            raise _ChangedDuringCapture()
        if len(raw) > limit:
            return None, None, "file_budget"
        mode = "100755" if before.st_mode & stat.S_IXUSR else "100644"
        return bytes(raw), mode, None
    except (PermissionError, OSError) as error:
        raise SnapshotError(
            "worktree_unreadable", "A selected worktree input could not be read."
        ) from error
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


@dataclass
class _Selection:
    files: dict[str, bytes]
    kinds: dict[str, EvidenceKind]
    modes: dict[str, str]
    omissions: list[SnapshotOmission]


def _collect(
    git: _Git,
    entries: dict[str, _Entry],
    spec: SnapshotSpec,
    side: EvidenceSide,
    *,
    live: bool = False,
    untracked: set[str] | None = None,
    starting_bytes: int = 0,
    starting_files: int = 0,
) -> _Selection:
    untracked = untracked or set()
    explicit = {item.path for item in spec.inputs}
    selected = _Selection({}, {}, {}, [])
    total_bytes = starting_bytes
    total_files = starting_files
    # An explicit missing input is recorded only if absent on both sides by the caller.
    paths = sorted(entries.keys() | untracked | explicit)

    def omit(path: str, reason: str, affects: bool):
        selected.omissions.append(
            SnapshotOmission(side=side, path=path, reason=reason, affects_completeness=affects)
        )

    for path in paths:
        kind, exclusion = _kind(path, spec)
        entry = entries.get(path)
        if kind is None:
            if entry and entry.mode in {"120000", "160000"} and exclusion == "outside_scope":
                # A link named like a document, such as `GUIDE.md`, cannot stand for
                # source. Any other link may be a directory of code.
                suffix = path.rsplit("/", 1)[-1].rpartition(".")[2].lower()
                document = entry.mode == "120000" and suffix in _DOCUMENT_SUFFIXES
                omit(path, "symlink" if entry.mode == "120000" else "submodule", not document)
            else:
                omit(path, exclusion, path in explicit)
            continue
        if entry is None and not live:
            continue
        if (
            live
            and path in untracked
            and path not in entries
            and path not in explicit
            and not spec.include_untracked
        ):
            omit(path, "untracked_not_selected", True)
            continue
        if entry and entry.mode == "160000":
            omit(path, "submodule", True)
            continue
        if not live and entry.mode not in _REGULAR:
            omit(path, "symlink" if entry.mode == "120000" else "special_file", True)
            continue
        if total_files >= spec.limits.max_files:
            omit(path, "count_budget", True)
            continue
        if not live and entry.size > spec.limits.max_file_bytes:
            omit(path, "file_budget", True)
            continue
        if not live and total_bytes + entry.size > spec.limits.max_total_bytes:
            omit(path, "total_budget", True)
            continue
        if live:
            remaining = spec.limits.max_total_bytes - total_bytes
            raw, mode, reason = _read_worktree(
                git.root, path, min(spec.limits.max_file_bytes, remaining)
            )
            if reason:
                if reason == "file_budget" and remaining < spec.limits.max_file_bytes:
                    reason = "total_budget"
                omit(path, reason, True)
                continue
            if raw is None:  # An actual deletion, not a placeholder empty file.
                continue
        else:
            raw = git.run("cat-file", "blob", entry.oid, limit=entry.size + 1)
            if len(raw) != entry.size:
                raise SnapshotError("object_size_mismatch", "Git object size changed unexpectedly.")
            mode = entry.mode
        if b"\0" in raw:
            omit(path, "binary", True)
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            omit(path, "unsupported_encoding", True)
            continue
        # Git LFS pointer bytes are not the original source.
        if raw.startswith(b"version https://git-lfs.github.com/spec/v1"):
            omit(path, "binary", True)
            continue
        selected.files[path] = raw
        selected.kinds[path] = kind
        selected.modes[path] = mode
        total_bytes += len(raw)
        total_files += 1
    return selected


def _diff(base: _Selection, head: _Selection, omissions: list[SnapshotOmission]) -> FileDiff:
    uncertain = {item.path for item in omissions if item.affects_completeness}

    def comparable(paths):
        return {
            path
            for path in paths
            if not any(path == omitted or path.startswith(omitted + "/") for omitted in uncertain)
        }

    before = comparable(base.files)
    after = comparable(head.files)
    deltas = []
    for path in sorted(before & after):
        if base.files[path] != head.files[path] or base.modes[path] != head.modes[path]:
            deltas.append(
                FileDelta(
                    change=FileChange(change_type="modified", base_path=path, head_path=path),
                    base_mode=base.modes[path],
                    head_mode=head.modes[path],
                )
            )
    deleted, added = set(before - after), set(after - before)
    # Conservative rename correspondence. Edited or ambiguous copies remain add/delete.
    old_by_content: dict[tuple[str, str], list[str]] = {}
    new_by_content: dict[tuple[str, str], list[str]] = {}
    for paths, selection, groups in (
        (deleted, base, old_by_content),
        (added, head, new_by_content),
    ):
        for path in sorted(paths):
            groups.setdefault(
                (content_digest(selection.files[path]), selection.modes[path]), []
            ).append(path)
    for identity in sorted(old_by_content.keys() & new_by_content.keys()):
        old, new = old_by_content[identity], new_by_content[identity]
        if len(old) == len(new) == 1:
            deleted.remove(old[0])
            added.remove(new[0])
            deltas.append(
                FileDelta(
                    change=FileChange(change_type="renamed", base_path=old[0], head_path=new[0]),
                    base_mode=base.modes[old[0]],
                    head_mode=head.modes[new[0]],
                )
            )
    deltas.extend(
        FileDelta(
            change=FileChange(change_type="deleted", base_path=path), base_mode=base.modes[path]
        )
        for path in sorted(deleted)
    )
    deltas.extend(
        FileDelta(
            change=FileChange(change_type="added", head_path=path), head_mode=head.modes[path]
        )
        for path in sorted(added)
    )
    deltas.sort(
        key=lambda item: (item.change.base_path or item.change.head_path, item.change.change_type)
    )
    return FileDiff(
        changes=tuple(deltas),
        coverage={
            "status": "insufficient_context" if uncertain else "analyzed",
            "reason": "Selected files were omitted; their changes are unresolved."
            if uncertain
            else None,
            "analyzed_scope": "Captured Python/config/flow/explicit inputs; exact unique renames only.",
        },
    )


def capture_snapshot(repo: Path, spec: SnapshotSpec) -> CapturedSnapshot:
    """Capture a repository root.

    A base that is named but missing is an error. Without a base only the head side
    is captured, and the file diff stays empty instead of calling every file added.
    """
    root = repo.expanduser().resolve(strict=True)
    git = _Git(root, spec.limits)
    top = Path(os.fsdecode(git.run("rev-parse", "--show-toplevel")).rstrip("\n")).resolve()
    if top != root:
        raise SnapshotError(
            "repository_root_required", "Pass the repository root, not a nested directory."
        )
    base_revision = git.revision(spec.base) if spec.base is not None else None
    # Pin both commit refs before doing potentially slow file collection.
    resolved_head = (
        (base_revision if spec.head == spec.base else git.revision(spec.head))
        if spec.head is not None
        else None
    )
    base = (
        _collect(git, git.tree(base_revision), spec, BASE)
        if base_revision is not None
        else _Selection({}, {}, {}, [])
    )
    starting = {
        "starting_bytes": sum(map(len, base.files.values())),
        "starting_files": len(base.files),
    }
    if spec.head is not None:
        head_revision = resolved_head
        head_entries = git.tree(head_revision)
        head = _collect(git, head_entries, spec, HEAD, **starting)
        consistency = "not_applicable"
    else:
        for _ in range(spec.limits.worktree_attempts):
            try:
                anchor = git.revision("HEAD")
                anchor_tree = git.tree(anchor)
                listing, others = _worktree_listing(git, anchor_tree)
                first = _collect(git, listing, spec, HEAD, live=True, untracked=others, **starting)
                second_listing, second_others = _worktree_listing(git, anchor_tree)
                second = _collect(
                    git, second_listing, spec, HEAD, live=True, untracked=second_others, **starting
                )
                if (
                    listing != second_listing
                    or others != second_others
                    or first != second
                    or git.revision("HEAD") != anchor
                ):
                    raise _ChangedDuringCapture()
                head = second
                break
            except _ChangedDuringCapture:
                continue
        else:
            raise SnapshotError(
                "worktree_changed",
                "Working files or Git index changed during capture; retry when editing stops.",
            )
        # Include HEAD provenance and captured modes, not unselected file contents.
        identity = json.dumps(
            {
                "anchor": anchor,
                "files": [
                    [path, head.modes[path], content_digest(head.files[path])]
                    for path in sorted(head.files)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        head_revision = "worktree:" + hashlib.sha256(identity.encode()).hexdigest()
        consistency = "two_matching_reads"
    omissions = [*base.omissions, *head.omissions]
    for item in spec.inputs:
        if (
            item.path not in base.files
            and item.path not in head.files
            and not any(om.path == item.path for om in omissions)
        ):
            omissions.append(
                SnapshotOmission(
                    side=HEAD, path=item.path, reason="missing_input", affects_completeness=True
                )
            )
    omissions.sort(key=lambda item: (item.side.value, item.path, item.reason))
    files = tuple(
        FileIdentity(
            side=side,
            path=path,
            kind=selection.kinds[path],
            content_digest=content_digest(selection.files[path]),
        )
        for side, selection in ((BASE, base), (HEAD, head))
        for path in sorted(selection.files)
    )
    omitted = tuple(
        f"{item.side.value}:{item.path}:{item.reason}"
        for item in omissions
        if item.affects_completeness
    )
    manifest = SnapshotManifest(
        snapshot_id=snapshot_id_for(
            base_revision=base_revision, head_revision=head_revision, files=files
        ),
        base_revision=base_revision,
        head_revision=head_revision,
        files=files,
        integrity_status="partial" if omitted else "complete",
        omitted_inputs=omitted,
    )
    capture = SnapshotCapture(
        spec=spec,
        manifest=manifest,
        head_commit=head_revision if spec.head is not None else anchor,
        modes=tuple(
            CapturedMode(side=side, path=path, mode=selection.modes[path])
            for side, selection in ((BASE, base), (HEAD, head))
            for path in sorted(selection.files)
        ),
        file_diff=_diff(base if base_revision is not None else head, head, omissions),
        omissions=tuple(omissions),
        worktree_consistency=consistency,
    )
    source = FrozenSourceSnapshot(
        manifest,
        {
            (side, path): raw
            for side, selection in ((BASE, base), (HEAD, head))
            for path, raw in selection.files.items()
        },
    )
    return CapturedSnapshot(capture, source)

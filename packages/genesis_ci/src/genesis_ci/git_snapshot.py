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
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
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
    # Whether the head side read differs from the commit it was read on. Known when the
    # capture is taken; a snapshot loaded from disk does not carry it.
    worktree_dirty: bool | None = None
    # The digest of a file as its commit holds it, for each file read from the working
    # tree that is the commit's file but not byte for byte: the checkout converted it,
    # such as its line endings. Known when the capture is taken, like `worktree_dirty`.
    commit_digests: dict[str, str] = field(default_factory=dict)


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

    def run(self, *args: str, limit: int | None = None, stdin: bytes | None = None) -> bytes:
        """Git's output for `args`, fed `stdin` if given, within the byte and time budgets."""
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
                stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise SnapshotError("git_unavailable", "Unable to start Git.") from error
        chunks: list[bytes] = []
        count = 0
        pending = memoryview(stdin or b"")
        deadline = time.monotonic() + self.limits.git_timeout_seconds
        try:
            # Drain both pipes with a shared hard output budget before accumulating bytes,
            # and feed the input as Git takes it, so that neither side waits on the other.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                if process.stdin is not None:
                    if pending:
                        os.set_blocking(process.stdin.fileno(), False)
                        selector.register(process.stdin, selectors.EVENT_WRITE, None)
                    else:
                        process.stdin.close()
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SnapshotError("git_timeout", "Git exceeded the capture timeout.")
                    for key, _ in selector.select(timeout=min(remaining, 0.2)):
                        if key.data is None:
                            try:
                                pending = pending[os.write(key.fd, pending[:65536]) :]
                            except BlockingIOError:
                                continue
                            except BrokenPipeError:
                                # Git stopped reading; its exit status tells why.
                                pending = pending[len(pending) :]
                            if not pending:
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                            continue
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
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            process.stdout.close()
            process.stderr.close()

    def revision(self, ref: str) -> str:
        try:
            raw = self.run("rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        except SnapshotError as error:
            if error.code != "git_read_failed":
                raise
            message = (
                "This repository has no commit yet. Commit the files once, then run the "
                "command again."
                if ref == "HEAD"
                else f"Revision {ref} is not a commit in the local clone. Fetch it, or pass "
                "an existing local commit."
            )
            raise SnapshotError("revision_unavailable", message) from error
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


def left_out_by(path: str, spec: SnapshotSpec) -> str | None:
    """The folder, or path, by which `path` is left out on purpose: one `spec` excludes,
    or Genesis's own `.genesis/` (all but its `flows.yaml`). None when neither applies.
    """
    for prefix in spec.exclude_paths:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    parts = path.split("/")
    if ".genesis" not in parts or path == ".genesis/flows.yaml":
        return None
    return "/".join(parts[: parts.index(".genesis") + 1])


def excluded_by(path: str, spec: SnapshotSpec) -> str | None:
    """The folder, or path, by which every capture leaves `path` out, whatever it is asked
    to read: one `left_out_by` names, or a dependency, build or cache folder. None when
    no such rule applies.
    """
    folder = left_out_by(path, spec)
    if folder is not None:
        return folder
    parts = path.split("/")
    for index, part in enumerate(parts):
        if part in _EXCLUDED:
            return "/".join(parts[: index + 1])
    return None


def cache_folder(path: str) -> str | None:
    """The innermost dependency, build or cache folder `path` lies in, or None."""
    parts = path.split("/")[:-1]
    for index in range(len(parts), 0, -1):
        if parts[index - 1] in _EXCLUDED:
            return "/".join(parts[:index])
    return None


def may_capture(path: str, spec: SnapshotSpec) -> bool:
    """Whether a capture can read `path` at all: it is no secret, and no rule of
    `excluded_by` leaves it out. Whether one does depends on what it is asked to read."""
    return _exclusion(path, spec) is None


def is_secret(path: str) -> bool:
    """Whether `path` is named like a secret, which no capture reads or lists."""
    parts = path.split("/")
    lowered = parts[-1].lower()
    return (
        lowered == ".env"
        or lowered.startswith(".env.")
        or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".keystore"))
        or lowered in {"id_rsa", "id_ed25519", "credentials", "credentials.json", ".netrc"}
        or any(part in {".ssh", ".aws", ".gnupg"} for part in parts)
    )


def _exclusion(path: str, spec: SnapshotSpec) -> str | None:
    """Why no capture reads `path`, whatever it is asked to read, or None."""
    # Explicit inputs cannot override secret/generated-path exclusions.
    if is_secret(path):
        return "secret_path"
    if excluded_by(path, spec) is not None:
        return "excluded"
    return None


def _explicit(spec: SnapshotSpec) -> dict[str, EvidenceKind]:
    """The kind of each input `spec` lists, by path. A spec may list every source file
    of a project, so a caller that asks about many paths builds this once."""
    return {item.path: item.kind for item in spec.inputs}


def _kind(
    path: str, spec: SnapshotSpec, explicit: dict[str, EvidenceKind] | None = None
) -> tuple[EvidenceKind | None, str | None]:
    exclusion = _exclusion(path, spec)
    if exclusion is not None:
        return None, exclusion
    name = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    if explicit is None:
        explicit = _explicit(spec)
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
) -> tuple[dict[str, _Entry], set[str], set[str]]:
    """The tracked files, by path, the untracked ones Git does not ignore, and the
    tracked ones Git is told not to check, whose index entry cannot vouch for them:
    marked `assume-unchanged`, as `core.ignoreStat` marks every file it adds."""
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
    unchecked = set()
    # `-v` tags an assume-unchanged file in lower case.
    for row in git.run("ls-files", "-v", "-z").split(b"\0"):
        if row[:2] in {b"S ", b"s "}:
            raise SnapshotError(
                "sparse_worktree",
                "Sparse worktrees are not supported for live capture; use two commits.",
            )
        if row[:1].islower():
            unchecked.add(_path(row[2:]))
    others = {
        _path(row)
        for row in git.run("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if row
    }
    return tracked, others, unchecked


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
    # Tracked files a working-tree read found deleted: gone, not left out.
    deleted: set[str] = field(default_factory=set)


def _collect(
    git: _Git,
    entries: dict[str, _Entry],
    spec: SnapshotSpec,
    side: EvidenceSide,
    *,
    live: bool = False,
    untracked: set[str] | None = None,
    other: _Selection | None = None,
    other_oids: dict[str, str | None] | None = None,
) -> _Selection:
    """Select and read the files of one side.

    The file and byte budgets count distinct content. `other` is the side captured
    before this one: it has used part of the budgets, and a file here with the same
    content at the same path is already paid for. Two sides of a change are almost
    the same files, and charging both would let half as large a repository through
    for a change as for a map.
    """
    untracked = untracked or set()
    kinds = _explicit(spec)
    explicit = kinds.keys()
    selected = _Selection({}, {}, {}, [])
    paid = other.files if other is not None else {}
    paid_oids = other_oids or {}
    total_bytes = sum(map(len, paid.values()))
    total_files = len(paid)
    # An explicit missing input is recorded only if absent on both sides by the caller.
    paths = sorted(entries.keys() | untracked | explicit)

    def omit(path: str, reason: str, affects: bool):
        selected.omissions.append(
            SnapshotOmission(side=side, path=path, reason=reason, affects_completeness=affects)
        )

    for path in paths:
        kind, exclusion = _kind(path, spec, kinds)
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
        full = total_files >= spec.limits.max_files
        remaining = spec.limits.max_total_bytes - total_bytes
        if live:
            # Whether a file repeats the other side is known only once it is read.
            known = paid.get(path)
            if known is None and full:
                omit(path, "count_budget", True)
                continue
            limit = spec.limits.max_file_bytes
            raw, mode, reason = _read_worktree(
                git.root, path, limit if known is not None else min(limit, remaining)
            )
            if reason:
                if reason == "file_budget" and known is None and remaining < limit:
                    reason = "total_budget"
                omit(path, reason, True)
                continue
            if raw is None:  # An actual deletion, not a placeholder empty file.
                if entry is not None:
                    selected.deleted.add(path)
                continue
            repeated = raw == known
            if not repeated and (full or len(raw) > remaining):
                omit(path, "count_budget" if full else "total_budget", True)
                continue
        else:
            repeated = path in paid and paid_oids.get(path) == entry.oid
            if full and not repeated:
                omit(path, "count_budget", True)
                continue
            if entry.size > spec.limits.max_file_bytes:
                omit(path, "file_budget", True)
                continue
            if entry.size > remaining and not repeated:
                omit(path, "total_budget", True)
                continue
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
        if not repeated:
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


def _differs(
    stored: _StoredBlobs,
    head: _Selection,
    listed: dict[str, _Listed] | None,
    unchecked: set[str],
    tree: dict[str, _Entry],
    spec: SnapshotSpec,
    reads: Callable[[str], bool] | None = None,
) -> tuple[bool, dict[str, str]]:
    """Whether the files read from the working tree differ from the commit they were read
    on, and the digest of the commit's bytes for each file read that is the commit's
    file but not byte for byte.

    A file edited, added or deleted counts, a changed file mode does not. Neither does a
    file of the commit that the capture left out for a reason of its own, such as size,
    nor bytes Git would store as the commit has them, such as line endings it converts.
    A file of the commit counts as deleted when it was not read and the capture would
    read it, by its own rules or by `reads`.

    `listed` is what `git diff-index` lists against the commit, or None when Git could
    not list it. Git's index tells, as for `git status`, which files are as the commit
    has them without reading them again; only those it cannot vouch for are compared
    byte by byte, and so are the `unchecked` ones, which Git is told not to look at.
    Such a file that a filter driver converts, such as one git-crypt unlocked, counts
    as changed: the driver is a command of the repository and never runs here. `git
    status` refreshes the index, after which it is known again. Without `listed`,
    every file is compared byte by byte.
    """
    dirty = False
    converted, compared = {}, {}
    for path, raw in head.files.items():
        entry = tree.get(path)
        if entry is None:
            dirty = True
            continue
        found = listed.get(path) if listed is not None else None
        vouched = listed is not None and found is None and path not in unchecked
        if found is not None and found.new_oid.strip("0") and found.new_oid != entry.oid:
            # The index holds other content, and the file is as the index has it.
            dirty = True
        elif _raw_blob_id(raw, len(entry.oid)) == entry.oid:
            continue
        elif vouched:
            converted[path] = (entry, raw)
        else:
            compared[path] = (entry, raw)
    stored.read_attributes(path for path, (_, raw) in compared.items() if b"\r\n" in raw)
    for path, (entry, raw) in compared.items():
        if stored.same(path, raw, entry.oid):
            converted[path] = (entry, raw)
        else:
            dirty = True
    # Outside the scope is no reason of its own: it is what `reads` may widen.
    left_out = {item.path for item in head.omissions if item.reason != "outside_scope"}
    kinds = _explicit(spec)
    # A file Git is told not to check is not listed when it is deleted; the read knows.
    gone = (
        tree
        if listed is None
        else {path for path, item in listed.items() if item.status == "D"} | head.deleted
    )
    dirty = dirty or any(
        path not in head.files
        and path not in left_out
        and path in tree
        and tree[path].mode in _REGULAR
        and (_kind(path, spec, kinds)[0] is not None or (reads is not None and reads(path)))
        for path in gone
    )
    return dirty, stored.digests(converted)


def capture_snapshot(
    repo: Path, spec: SnapshotSpec, *, reads: Callable[[str], bool] | None = None
) -> CapturedSnapshot:
    """Capture a repository root.

    A base that is named but missing is an error. Without a base only the head side
    is captured, and the file diff stays empty instead of calling every file added.

    `reads` names, by path, the files a caller that lists its own inputs would ask to
    read were they listed. A file of the commit the working tree is read on that it
    names, and that was not read, makes the working tree differ from that commit: a
    caller that lists the index does not see a file removed from it with `git rm`.
    """
    root = repo.expanduser().resolve(strict=True)
    git = _Git(root, spec.limits)
    try:
        raw_top = git.run("rev-parse", "--show-toplevel")
    except SnapshotError as error:
        if error.code != "git_read_failed":
            raise
        raise SnapshotError(
            "git_read_failed",
            f"Git could not open {root} as a repository. Most often it is not inside one: "
            "run `git init` there and commit the files, then try again. If it is a "
            "repository, check that it is owned by the current user.",
        ) from error
    top = Path(os.fsdecode(raw_top).rstrip("\n")).resolve()
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
    base_entries = git.tree(base_revision) if base_revision is not None else {}
    base = (
        _collect(git, base_entries, spec, BASE)
        if base_revision is not None
        else _Selection({}, {}, {}, [])
    )
    starting = {
        "other": base,
        "other_oids": {path: base_entries[path].oid for path in base.files},
    }
    if spec.head is not None:
        head_revision = resolved_head
        head_entries = git.tree(head_revision)
        head = _collect(git, head_entries, spec, HEAD, **starting)
        consistency = "not_applicable"
        dirty, committed = False, {}
    else:
        stored = _StoredBlobs(git)
        for _ in range(spec.limits.worktree_attempts):
            try:
                anchor = git.revision("HEAD")
                anchor_tree = git.tree(anchor)
                listing, others, unchecked = _worktree_listing(git, anchor_tree)
                first = _collect(git, listing, spec, HEAD, live=True, untracked=others, **starting)
                # Between the two reads, so that what Git lists is of the files read.
                listed = _index_listing(stored, anchor)
                second_listing, second_others, second_unchecked = _worktree_listing(
                    git, anchor_tree
                )
                second = _collect(
                    git, second_listing, spec, HEAD, live=True, untracked=second_others, **starting
                )
                if (
                    listing != second_listing
                    or others != second_others
                    or unchecked != second_unchecked
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
        dirty, committed = _differs(stored, head, listed, unchecked, anchor_tree, spec, reads)
    omissions = [*base.omissions, *head.omissions]
    for item in spec.inputs:
        if (
            item.path not in base.files
            and item.path not in head.files
            and item.path not in head.deleted
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
    return CapturedSnapshot(capture, source, dirty, committed)


# ----- names only ----------------------------------------------------------------------
#
# A change session lists by name the changed files a capture did not read. They are read
# the way a capture reads: no hook, filter or fsmonitor runs, and the index is never
# written. A plain `git diff` against the working tree refreshes the index and writes it
# back even with optional locks off, so the working tree is compared through
# `diff-index`, which only reads it. That still re-reads a file whose index entry its
# timestamps cannot vouch for, through the clean filter its attributes name, so every
# filter driver the repository configures is switched off for it.


def _names(raw: bytes) -> list[str]:
    """The paths of a NUL-separated listing; a path that is not safe is skipped."""
    found = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            found.append(_path(item))
        except SnapshotError:
            continue
    return found


def tracked_paths(repo: Path, limits: SnapshotLimits | None = None) -> list[str]:
    """The paths in the index."""
    git = _Git(repo.expanduser().resolve(strict=True), limits or SnapshotLimits())
    return _names(git.run("ls-files", "-z"))


def untracked_names(repo: Path, limits: SnapshotLimits | None = None) -> list[str]:
    """Working files Git neither tracks nor ignores, every one of them."""
    git = _Git(repo.expanduser().resolve(strict=True), limits or SnapshotLimits())
    return _names(git.run("ls-files", "--others", "--exclude-standard", "-z"))


def untracked_paths(repo: Path, spec: SnapshotSpec) -> list[str]:
    """Working files Git neither tracks nor ignores, less those no capture would read.

    Secrets, caches, `.genesis/` and the paths `spec` excludes are left out: including
    untracked files would not bring them in either.
    """
    return [path for path in untracked_names(repo, spec.limits) if may_capture(path, spec)]


def _without_filters(git: _Git) -> list[str]:
    """`-c` options that turn off every filter driver the repository configures."""
    names = set()
    for item in git.run("config", "--list", "-z").split(b"\0"):
        key = item.split(b"\n", 1)[0].decode("utf-8", "replace")
        if key.startswith("filter.") and key.count(".") >= 2:
            names.add(key[len("filter.") : key.rindex(".")])
    options = []
    for name in sorted(names):
        if "=" in name:
            raise SnapshotError("unsafe_config", "A filter driver could not be switched off.")
        for setting in ("clean=", "process=", "required=false"):
            options += ["-c", f"filter.{name}.{setting}"]
    return options


def _raw_blob_id(raw: bytes, length: int) -> str:
    """The Git id of these bytes as a blob, in the hash whose ids have `length` digits."""
    digest = hashlib.sha256() if length == 64 else hashlib.sha1(usedforsecurity=False)
    digest.update(b"blob %d\0" % len(raw))
    digest.update(raw)
    return digest.hexdigest()


_LINE_ENDING_ATTRIBUTES = ("text", "eol", "crlf")
# Control characters Git's test of text counts against it (convert.c); NUL is apart.
_NONPRINTABLE = bytes([*range(1, 8), 11, *range(14, 27), *range(28, 32), 127])


def _user_autocrlf(git: _Git) -> str | None:
    """`core.autocrlf` as the user's own Git has it, from every configuration file Git
    reads, or None when none sets it. Reading a setting runs nothing."""
    reader = _Git(git.root, git.limits)
    for key in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        reader.env.pop(key, None)
        if key in os.environ:
            reader.env[key] = os.environ[key]
    try:
        raw = reader.run("config", "--get", "core.autocrlf")
    except SnapshotError as error:
        if error.code != "git_read_failed":
            raise
        return None
    value = raw.decode("utf-8", "replace").strip().lower()
    if value in {"true", "yes", "on", "1"}:
        return "true"
    if value in {"false", "no", "off", "0", ""}:
        return "false"
    return "input" if value == "input" else None


def _git_text(raw: bytes) -> bool:
    """Whether Git takes `raw` for text where it guesses (convert.c): no NUL, no CR but
    in a CRLF, and few other control characters."""
    if b"\0" in raw or b"\r" in raw.replace(b"\r\n", b""):
        return False
    nonprintable = len(raw) - len(raw.translate(None, _NONPRINTABLE))
    printable = len(raw) - raw.count(b"\r") - raw.count(b"\n") - nonprintable
    # A final end-of-file character does not count.
    nonprintable -= raw.endswith(b"\x1a")
    return printable >> 7 >= nonprintable


def _converts_line_endings(attributes: dict[str, str], autocrlf: str | None, raw: bytes) -> bool:
    """Whether Git turns each CRLF of `raw` into LF when it stores it, by the `text`,
    `eol` and legacy `crlf` attributes of its path and `core.autocrlf` (convert.c)."""
    action = attributes["text"]
    if action == "unspecified":
        action = attributes["crlf"]
    if action == "unset":
        return False
    if action in {"set", "input"}:
        return True
    if action != "auto" and attributes["eol"] in {"lf", "crlf"}:
        return True
    if action == "auto" or autocrlf in {"true", "input"}:
        return _git_text(raw)
    return False


def _index_listing(stored: _StoredBlobs, base: str) -> dict[str, _Listed] | None:
    """What `git diff-index` lists between `base` and the working tree, or None when Git
    cannot list it within the budgets."""
    try:
        return stored.listed(base)
    except SnapshotError as error:
        if error.code not in {"git_read_failed", "metadata_budget"}:
            raise
        return None


@dataclass(frozen=True)
class _Listed:
    """One path of a raw `git diff-index` or `git diff-tree` listing."""

    status: str
    new_mode: str
    old_oid: str
    new_oid: str


def _listing(raw: bytes) -> dict[str, _Listed]:
    """The paths of a raw, NUL-separated listing, in Git's order; one not safe is skipped."""
    fields = raw.split(b"\0")
    found = {}
    for meta, raw_path in zip(fields[::2], fields[1::2], strict=False):
        parts = meta.decode("ascii", "replace").lstrip(":").split()
        if len(parts) != 5:
            continue
        _, new_mode, old_oid, new_oid, status = parts
        try:
            path = _path(raw_path)
        except SnapshotError:
            continue
        found[path] = _Listed(status, new_mode, old_oid, new_oid)
    return found


class _StoredBlobs:
    """Whether working-tree bytes are a blob as Git would store them at their path.

    A checkout converts what it writes: line endings (`eol`, `text`, `core.autocrlf`),
    `ident` and `working-tree-encoding`. `core.autocrlf` is read once from the user's
    own Git configuration, which every other command here leaves unread, as Git for
    Windows sets it there. Bytes whose own id is not the blob's are first compared with
    each CRLF turned into LF, which needs no process, when that is what Git does at
    their path: by its `text`, `eol` and `crlf` attributes and `core.autocrlf`, as
    `convert.c` decides. Bytes that still differ are given to `git hash-object --path`,
    which converts them back the way `git add` would. Those conversions are built into
    Git; every filter driver the repository configures is switched off, so no command
    of the repository runs, and nothing is written. Bytes Git cannot convert are not
    the blob.
    """

    def __init__(self, git: _Git):
        self.git = git
        self._options: list[str] | None = None
        # The line-ending attributes of paths, by path; None where Git could not tell.
        self._attributes: dict[str, dict[str, str] | None] = {}
        # The bytes of blobs met on the way, by id.
        self.blobs: dict[str, bytes] = {}

    @cached_property
    def autocrlf(self) -> str | None:
        return _user_autocrlf(self.git)

    @property
    def options(self) -> list[str]:
        if self._options is None:
            self._options = _without_filters(self.git)
            if self.autocrlf is not None:
                self._options += ["-c", "core.autocrlf=" + self.autocrlf]
        return self._options

    def read_attributes(self, paths) -> None:
        """Read the line-ending attributes of `paths` from Git in one go."""
        paths = sorted(set(paths) - self._attributes.keys())
        if not paths:
            return
        self._attributes.update(dict.fromkeys(paths))
        try:
            raw = self.git.run(
                "check-attr",
                "-z",
                "--stdin",
                *_LINE_ENDING_ATTRIBUTES,
                stdin=b"".join(path.encode() + b"\0" for path in paths),
            )
        except SnapshotError as error:
            if error.code not in {"git_read_failed", "metadata_budget"}:
                raise
            return
        fields = raw.split(b"\0")
        found: dict[str, dict[str, str]] = {}
        for path, name, value in zip(fields[::3], fields[1::3], fields[2::3], strict=False):
            found.setdefault(path.decode("utf-8", "replace"), {})[name.decode()] = value.decode()
        for path in paths:
            if found.get(path, {}).keys() >= set(_LINE_ENDING_ATTRIBUTES):
                self._attributes[path] = found[path]

    def listed(self, base: str) -> dict[str, _Listed]:
        """What `git diff-index` lists between `base` and the working tree.

        A file Git's index vouches for is not listed when it is as `base` has it. One
        whose timestamps the index cannot vouch for is listed with no new id; Git does
        not read it.
        """
        # Submodules are compared by the commit recorded, never by running Git in them.
        return _listing(
            self.git.run(
                *self.options,
                "diff-index",
                "--no-renames",
                "--ignore-submodules=dirty",
                "-z",
                base,
                "--",
            )
        )

    def _normalized(self, raw: bytes, oid: str) -> bool:
        """Whether `raw` with each CRLF turned into LF is the blob `oid`."""
        if b"\r\n" not in raw:
            return False
        normalized = raw.replace(b"\r\n", b"\n")
        if _raw_blob_id(normalized, len(oid)) != oid:
            return False
        self.blobs[oid] = normalized
        return True

    def _line_endings(self, path: str, raw: bytes, oid: str) -> bool:
        """Whether Git turns each CRLF of `raw` into LF at `path`, which gives the blob."""
        if b"\r\n" not in raw:
            return False
        self.read_attributes([path])
        attributes = self._attributes.get(path)
        return (
            attributes is not None
            and _converts_line_endings(attributes, self.autocrlf, raw)
            and self._normalized(raw, oid)
        )

    def same(self, path: str, raw: bytes, oid: str) -> bool:
        if _raw_blob_id(raw, len(oid)) == oid or self._line_endings(path, raw, oid):
            return True
        try:
            found = self.git.run(
                *self.options,
                "-c",
                "core.safecrlf=false",
                "hash-object",
                "--stdin",
                "--path=" + path,
                stdin=raw,
            )
        except SnapshotError as error:
            if error.code != "git_read_failed":
                raise
            return False
        return found.decode("ascii", "replace").strip() == oid

    def _read_blobs(self, oids: list[str], sizes: dict[str, int | None]) -> None:
        """Read the blobs `oids` from Git in one go. What Git cannot give within the
        budgets, or does not have, as in a partial clone, is skipped."""
        limit = sum((sizes[oid] or self.git.limits.max_file_bytes) + len(oid) + 32 for oid in oids)
        try:
            raw = self.git.run(
                "cat-file",
                "--batch",
                stdin="".join(oid + "\n" for oid in oids).encode(),
                limit=limit,
            )
        except SnapshotError as error:
            if error.code not in {"git_read_failed", "metadata_budget"}:
                raise
            return
        position = 0
        for oid in oids:
            end = raw.find(b"\n", position)
            header = raw[position:end].split() if end >= 0 else []
            if header[1:] == [b"missing"]:
                position = end + 1
                continue
            if len(header) != 3 or header[0] != oid.encode() or header[1] != b"blob":
                return
            size = int(header[2])
            self.blobs[oid] = raw[end + 1 : end + 1 + size]
            position = end + 2 + size

    def digests(self, converted: dict[str, tuple[_Entry, bytes]]) -> dict[str, str]:
        """The digest of each blob, by path, given with the bytes it was read as.

        Blobs not met yet are read from Git in one go. One it cannot read is left out.
        """
        for entry, raw in converted.values():
            if entry.oid not in self.blobs:
                self._normalized(raw, entry.oid)
        missing = sorted({entry.oid for entry, _ in converted.values()} - self.blobs.keys())
        if missing:
            self._read_blobs(missing, {entry.oid: entry.size for entry, _ in converted.values()})
        return {
            path: content_digest(self.blobs[entry.oid])
            for path, (entry, _) in sorted(converted.items())
            if entry.oid in self.blobs
        }


def changed_paths(
    repo: Path, base: str, head: str | None, limits: SnapshotLimits | None = None
) -> list[tuple[str, str]]:
    """`(status, path)` for each path that differs between `base` and `head`.

    Without `head` the other side is the working tree. `status` is Git's letter (`A`,
    `D`, `M`, `T`). A tracked file whose metadata changed since the index last saw it
    is compared here from its bytes as Git would store them, with no filter driver: one
    that matches the base is not listed, one larger than the file budget or that cannot
    be read is listed as modified.
    """
    root = repo.expanduser().resolve(strict=True)
    limits = limits or SnapshotLimits()
    git = _Git(root, limits)
    stored = None
    if head is not None:
        listed = _listing(
            git.run("diff-tree", "-r", "--no-renames", "--no-commit-id", "-z", base, head, "--")
        )
    else:
        stored = _StoredBlobs(git)
        listed = stored.listed(base)

    def unread(item: _Listed) -> bool:
        return (
            stored is not None
            and not item.new_oid.strip("0")
            and item.status in {"M", "T"}
            and item.new_mode in _REGULAR
        )

    if stored is not None:
        stored.read_attributes(path for path, item in listed.items() if unread(item))
    found = []
    for path, item in listed.items():
        if unread(item):
            try:
                current, _, _ = _read_worktree(root, path, limits.max_file_bytes)
            except (SnapshotError, _ChangedDuringCapture):
                current = None
            if current is not None and stored.same(path, current, item.old_oid):
                continue
        found.append((item.status, path))
    return found

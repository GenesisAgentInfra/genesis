"""Install the bundled Genesis skill without changing agent policies or credentials."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

SKILL_NAME = "genesis"
# Earlier releases installed the skill under these names; an untouched copy is replaced.
LEGACY_SKILL_NAMES = ("genesis-review",)
ASSET_FILES = ("SKILL.md", "agents/openai.yaml", "scripts/run_genesis.py")
MANIFEST = ".genesis-skill.json"


class Agent(StrEnum):
    codex = "codex"
    claude = "claude"
    both = "both"


class Scope(StrEnum):
    user = "user"
    project = "project"


def skill_destinations(agent: Agent, scope: Scope, repo: Path | None) -> tuple[Path, ...]:
    if scope == Scope.project:
        if repo is None:
            raise ValueError(
                "Project scope requires --repo pointing to your application's Git root."
            )
        root = repo.expanduser().resolve(strict=True)
        if not root.is_dir() or not (root / ".git").exists():
            raise ValueError("--repo must be an existing Git root, including a linked worktree.")
    else:
        if repo is not None:
            raise ValueError("--repo applies only to --scope project.")
        root = Path.home().resolve()
    agents = (Agent.codex, Agent.claude) if agent == Agent.both else (agent,)
    return tuple(
        root / (".agents" if item == Agent.codex else ".claude") / "skills" / SKILL_NAME
        for item in agents
    )


def _assert_regular_path(path: Path) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError(f"Skill destination cannot contain symbolic links: {path}")


def _installed_files(destination: Path) -> dict[str, bytes]:
    _assert_regular_path(destination)
    if not destination.is_dir():
        raise ValueError(f"Skill destination is not a directory: {destination}")
    result = {}
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Skill contains a symbolic link: {destination}")
        if path.is_dir():
            continue
        if not path.is_file() or path.stat().st_size > 262144:
            raise ValueError(f"Skill contains an unexpected file: {destination}")
        result[path.relative_to(destination).as_posix()] = path.read_bytes()
    return result


def _payload() -> dict[str, bytes]:
    resource = files("genesis_ci").joinpath("assets/skills", SKILL_NAME)
    content = {name: resource.joinpath(name).read_bytes() for name in ASSET_FILES}
    content["runtime.json"] = (
        json.dumps({"format_version": 1, "python": str(Path(sys.executable).absolute())}, indent=2)
        + "\n"
    ).encode()
    # Generated installation is machine-specific. Teams should install per host.
    content[".gitignore"] = b"*\n"
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    content[MANIFEST] = (
        json.dumps({"managed_by": "genesis-cli", "format_version": 1, "files": hashes}, indent=2)
        + "\n"
    ).encode()
    return content


def _can_update(content: dict[str, bytes]) -> bool:
    try:
        manifest = json.loads(content[MANIFEST])
        expected = {
            name: hashlib.sha256(data).hexdigest()
            for name, data in content.items()
            if name != MANIFEST
        }
        return (
            isinstance(manifest, dict)
            and manifest.get("managed_by") == "genesis-cli"
            and manifest.get("format_version") == 1
            and manifest.get("files") == expected
        )
    except (ValueError, KeyError, TypeError):
        return False


def _legacy_installs(destination: Path) -> list[tuple[Path, bool]]:
    """Earlier-named skills beside a destination, and whether Genesis may remove each."""
    found = []
    for name in LEGACY_SKILL_NAMES:
        legacy = destination.with_name(name)
        if legacy.is_symlink() or not legacy.is_dir():
            continue
        try:
            removable = _can_update(_installed_files(legacy))
        except ValueError:
            removable = False
        found.append((legacy, removable))
    return found


def install_skills(
    agent: Agent, scope: Scope, repo: Path | None, *, update: bool = False, dry_run: bool = False
) -> list[tuple[Path, str]]:
    desired = _payload()
    planned = []
    legacy = []
    # Preflight every target before writing either agent's files.
    for destination in skill_destinations(agent, scope, repo):
        _assert_regular_path(destination)
        action = "install"
        if destination.exists():
            current = _installed_files(destination)
            if current == desired:
                action = "unchanged"
            elif not update or not _can_update(current):
                raise ValueError(
                    f"Skill already exists or was edited: {destination}. "
                    "Use --update for an unmodified Genesis-managed install; "
                    "otherwise preserve/move your existing skill first."
                )
            else:
                action = "update"
        planned.append((destination, action))
        legacy += _legacy_installs(destination)
    renamed = [
        (path, f"remove (renamed to {SKILL_NAME})" if removable else "kept (edited or not ours)")
        for path, removable in legacy
    ]
    if dry_run:
        return planned + renamed
    for destination, action in planned:
        if action == "unchanged":
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assert_regular_path(destination)
        staging = Path(tempfile.mkdtemp(prefix=".genesis-skill-", dir=destination.parent))
        backup = None
        installed = False
        try:
            for name, data in desired.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o600)
            if action == "update":
                # Keep the old directory intact until the replacement is ready.
                if not _can_update(_installed_files(destination)):
                    raise ValueError("Skill changed during installation; nothing replaced.")
                backup = staging.with_name(staging.name + "-previous")
                destination.rename(backup)
            elif destination.exists():
                raise ValueError("Skill appeared during installation; nothing replaced.")
            try:
                staging.rename(destination)
                installed = True
            except OSError:
                if backup is not None:
                    backup.rename(destination)
                    backup = None
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
            if installed and backup is not None and backup.exists():
                shutil.rmtree(backup)
    # Only after every new skill is in place, and only copies Genesis installed and nobody edited.
    for path, removable in legacy:
        if removable and _can_update(_installed_files(path)):
            shutil.rmtree(path)
    return planned + renamed


def skill_status(agent: Agent, scope: Scope, repo: Path | None) -> list[tuple[Path, str]]:
    result = []
    desired = _payload()
    for destination in skill_destinations(agent, scope, repo):
        _assert_regular_path(destination)
        if not destination.exists():
            state = "not installed"
        else:
            content = _installed_files(destination)
            state = "installed (current)" if content == desired else "different or locally edited"
        result.append((destination, state))
        result += [
            (path, f"earlier name; run install to replace it with {SKILL_NAME}")
            for path, _ in _legacy_installs(destination)
        ]
    return result

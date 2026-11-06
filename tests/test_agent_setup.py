"""Exercise installation and the actual CLI runner without model/network access."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from genesis_ci import agent_setup
from genesis_ci.agent_setup import Agent, Scope, install_skills, skill_destinations
from genesis_ci.cli import app
from genesis_ci.snapshot_store import load_snapshot
from test_git_snapshot import commit, git, write
from test_public_trial import mock_service
from typer.testing import CliRunner


@pytest.fixture
def user_home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(Path, "home", lambda: root)
    return root


def test_user_install_registers_both_agents_and_is_idempotent(user_home):
    result = CliRunner().invoke(app, ["agent", "install", "--agent", "both"])
    assert result.exit_code == 0, result.output
    expected = [user_home / name / "skills/genesis-review" for name in (".agents", ".claude")]
    for directory in expected:
        frontmatter = (directory / "SKILL.md").read_text().split("---", 2)[1]
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == directory.name
        assert metadata["description"]
        runtime = json.loads((directory / "runtime.json").read_text())
        assert runtime == {"format_version": 1, "python": str(Path(sys.executable).absolute())}
        ui = yaml.safe_load((directory / "agents/openai.yaml").read_text())
        assert ui["policy"]["allow_implicit_invocation"] is True
        assert "$genesis-review" in ui["interface"]["default_prompt"]
    before = {str(p): p.stat().st_mtime_ns for d in expected for p in d.rglob("*")}
    again = CliRunner().invoke(app, ["agent", "install", "--agent", "both"])
    assert again.exit_code == 0 and again.output.count("unchanged:") == 2
    assert before == {str(p): p.stat().st_mtime_ns for d in expected for p in d.rglob("*")}
    status = CliRunner().invoke(app, ["agent", "status"])
    assert status.exit_code == 0 and status.output.count("installed (current)") == 2
    assert not (user_home / ".config").exists()


def test_dry_run_and_status_do_not_write(user_home):
    result = CliRunner().invoke(app, ["agent", "install", "--agent", "both", "--dry-run"])
    assert result.exit_code == 0 and "Would install" in result.output
    status = CliRunner().invoke(app, ["agent", "status"])
    assert status.exit_code == 0 and status.output.count("not installed") == 2
    assert list(user_home.iterdir()) == []


def test_project_install_leaves_instructions_and_settings_intact(source_repo, user_home):
    instructions = {
        "AGENTS.md": "Existing rules\n",
        "CLAUDE.md": "Existing policy\n",
        ".claude/settings.json": '{"permissions": {}}\n',
    }
    for path, content in instructions.items():
        write(source_repo, path, content)
    result = CliRunner().invoke(
        app,
        ["agent", "install", "--agent", "both", "--scope", "project", "--repo", str(source_repo)],
    )
    assert result.exit_code == 0, result.output
    for path, content in instructions.items():
        assert (source_repo / path).read_text() == content
    assert list(user_home.iterdir()) == []
    # Machine-specific Python paths cannot accidentally enter an ordinary git add.
    assert b"runtime.json" not in git(source_repo, "status", "--short", "--untracked-files=all")


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--agent", "other"],
        ["--agent", "codex", "--scope", "project"],
        ["--agent", "codex", "--repo", "."],
    ],
)
def test_invalid_install_selection_makes_no_changes(user_home, flags):
    result = CliRunner().invoke(app, ["agent", "install", *flags])
    assert result.exit_code != 0
    assert list(user_home.iterdir()) == []


def test_project_scope_requires_an_existing_git_root(tmp_path):
    with pytest.raises(ValueError, match="Git root"):
        skill_destinations(Agent.codex, Scope.project, tmp_path)


def test_project_scope_accepts_linked_worktree(source_repo, tmp_path):
    write(source_repo, "app.py", "value = 1\n")
    commit(source_repo)
    worktree = tmp_path / "linked-worktree"
    git(source_repo, "worktree", "add", "--detach", str(worktree))
    assert (worktree / ".git").is_file()
    [(destination, action)] = install_skills(Agent.codex, Scope.project, worktree)
    assert action == "install" and destination.is_relative_to(worktree)


def test_preflight_preserves_existing_skills_and_does_not_partially_install(user_home):
    existing = user_home / ".claude/skills/genesis-review"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("My custom skill")
    result = CliRunner().invoke(app, ["agent", "install", "--agent", "both", "--update"])
    assert result.exit_code == 1
    assert (existing / "SKILL.md").read_text() == "My custom skill"
    assert not (user_home / ".agents").exists()


def test_update_refreshes_only_unmodified_managed_skill(user_home, monkeypatch):
    [(destination, _)] = install_skills(Agent.codex, Scope.user, None)
    original_payload = agent_setup._payload

    def new_payload():
        desired = original_payload()
        # Simulate an upgraded bundle without changing the original on disk.
        desired["SKILL.md"] += b"\nNew release guidance.\n"
        manifest = json.loads(desired[agent_setup.MANIFEST])
        manifest["files"]["SKILL.md"] = hashlib.sha256(desired["SKILL.md"]).hexdigest()
        desired[agent_setup.MANIFEST] = json.dumps(manifest).encode()
        return desired

    monkeypatch.setattr(agent_setup, "_payload", new_payload)
    with pytest.raises(ValueError, match="--update"):
        install_skills(Agent.codex, Scope.user, None)
    assert install_skills(Agent.codex, Scope.user, None, update=True) == [(destination, "update")]
    assert b"New release guidance" in (destination / "SKILL.md").read_bytes()
    (destination / "SKILL.md").write_text("User edits")
    with pytest.raises(ValueError, match="edited"):
        install_skills(Agent.codex, Scope.user, None, update=True)
    assert (destination / "SKILL.md").read_text() == "User edits"


def test_update_failure_restores_previous_install(user_home, monkeypatch):
    [(destination, _)] = install_skills(Agent.codex, Scope.user, None)
    previous = (destination / "runtime.json").read_bytes()
    monkeypatch.setattr(agent_setup.sys, "executable", "/different/python")
    real_rename = Path.rename

    def fail_replacement(self, target):
        if self.name.startswith(".genesis-skill-") and not self.name.endswith("-previous"):
            raise OSError("Simulated replacement failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_replacement)
    with pytest.raises(OSError):
        install_skills(Agent.codex, Scope.user, None, update=True)
    assert (destination / "runtime.json").read_bytes() == previous


def test_symlink_target_is_not_overwritten(user_home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (user_home / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        install_skills(Agent.codex, Scope.user, None)
    assert list(outside.iterdir()) == []


def test_runner_uses_pinned_environment_not_customer_modules(user_home, source_repo, tmp_path):
    [(directory, _)] = install_skills(Agent.codex, Scope.user, None)
    runner = directory / "scripts/run_genesis.py"
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run(): return 2\n")
    write(source_repo, "genesis_ci.py", "raise RuntimeError('CUSTOMER_CODE_EXECUTED')\n")
    write(source_repo, "sitecustomize.py", "raise RuntimeError('CUSTOMER_CODE_EXECUTED')\n")
    output = tmp_path / "offline report with spaces"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(runner),
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--offline",
            "--output",
            str(output),
        ],
        cwd=source_repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "CUSTOMER_CODE_EXECUTED" not in result.stdout + result.stderr
    report = json.loads((output / "report.json").read_text())
    assert report["scope"]["base_revision"] == base
    assert report["scope"]["execution_mode"] == "offline"
    assert (output / "summary.md").is_file()
    invalid = subprocess.run(
        [
            sys.executable,
            "-I",
            str(runner),
            "analyze",
            "--repo",
            str(tmp_path / "missing"),
            "--offline",
        ],
        cwd=source_repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert invalid.returncode == 1


def test_runner_missing_runtime_explains_reinstall(user_home, tmp_path):
    [(directory, _)] = install_skills(Agent.claude, Scope.user, None)
    (directory / "runtime.json").unlink()
    result = subprocess.run(
        [sys.executable, "-I", str(directory / "scripts/run_genesis.py"), "version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Reinstall" in result.stderr and "Traceback" not in result.stderr


def test_documented_preview_replay_sends_frozen_source_not_later_edits(
    source_repo, tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))
    for name in ("GENESIS_API_KEY", "GENESIS_SERVICE_URL", "GITHUB_EVENT_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("No live HTTP allowed")
    )
    sent = mock_service(monkeypatch)
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run(): return 2\n")
    preview, result_path = tmp_path / "preview", tmp_path / "result"
    first = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--preview-only",
            "--output",
            str(preview),
        ],
    )
    assert first.exit_code == 2 and sent == [], first.output
    original = json.loads((preview / "request.json").read_text())
    snapshot = load_snapshot(preview / "snapshot")
    write(source_repo, "app.py", "def run(): return 'AFTER_PREVIEW_UNAPPROVED'\n")
    second = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--snapshot",
            str(preview / "snapshot"),
            "--accept-send",
            "--output",
            str(result_path),
        ],
    )
    assert second.exit_code in {0, 2}, second.output
    assert [request.url.path for request in sent] == ["/capabilities", "/v1/analyze"]
    submitted = json.loads(sent[1].content)
    assert submitted["snapshot_id"] == snapshot.capture.manifest.snapshot_id
    assert submitted["snapshot_id"] == original["snapshot_id"]
    for field in ("excerpts", "evidence", "facts"):
        assert submitted[field] == original[field]
    assert b"AFTER_PREVIEW_UNAPPROVED" not in sent[1].content
    report = json.loads((result_path / "report.json").read_text())
    assert report["scope"]["execution_mode"] == "semantic"

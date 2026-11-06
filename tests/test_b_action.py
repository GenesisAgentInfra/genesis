import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from test_git_snapshot import commit, write

ROOT = Path(__file__).resolve().parents[1]


def test_action_installer_cannot_import_customer_pip_module(tmp_path):
    import yaml

    marker = "CUSTOMER_PIP_EXECUTED"
    (tmp_path / "pip.py").write_text(f'print("{marker}")\n')
    steps = yaml.safe_load((ROOT / "action/action.yml").read_text())["runs"]["steps"]
    install = next(
        step["run"] for step in steps if step.get("name") == "Install isolated pinned CLI"
    )
    command = shlex.split(next(line for line in install.splitlines() if "-m pip " in line))
    # Exercise the real installer invocation, substituting --version to avoid a download.
    command = [sys.executable, *command[1 : command.index("pip") + 1], "--version"]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(tmp_path)),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert marker not in result.stdout + result.stderr


def test_action_runs_real_cli_offline_for_fork_and_delivers_partial_report(source_repo, tmp_path):
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run(): return 2\n")
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": "This is an agent claim, not acceptance.",
                    "base": {"sha": base, "repo": {"full_name": "owner/project"}},
                    "head": {"repo": {"full_name": "contributor/project"}},
                }
            }
        )
    )
    summary, outputs = tmp_path / "summary.md", tmp_path / "outputs"
    env = dict(
        os.environ,
        GITHUB_EVENT_NAME="pull_request",
        GITHUB_EVENT_PATH=str(event),
        GENESIS_ACTION_REPO=str(source_repo),
        GENESIS_ACTION_BASE=base,
        GENESIS_API_KEY="fork-must-never-send",
        GENESIS_SERVICE_URL="https://ci.example.test",
        RUNNER_TEMP=str(tmp_path),
        GITHUB_STEP_SUMMARY=str(summary),
        GITHUB_OUTPUT=str(outputs),
    )
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "action/run.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "analysis-status=partial" in outputs.read_text()
    assert "当前 PR 上下文不允许发送代码" in summary.read_text()
    assert "fork-must-never-send" not in summary.read_text() + result.stdout + result.stderr
    directory = next(
        line.split("=", 1)[1]
        for line in outputs.read_text().splitlines()
        if line.startswith("report-directory=")
    )
    local = json.loads((Path(directory) / "local-analysis.json").read_text())
    assert any(item["nature"] == "agent_claim" for item in local["intents"])
    assert not any(source_repo.glob("genesis-ci-intent-*.md"))

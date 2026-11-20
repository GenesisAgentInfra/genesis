"""What the CLI tells a person or an agent when it refuses, and what `version` prints."""

import errno
import json

import pytest
from genesis_ci import cli
from genesis_ci.cli import app
from test_git_snapshot import write
from typer.testing import CliRunner


def refusal(*arguments):
    result = CliRunner().invoke(app, ["map", *arguments])
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["error"]


def test_a_folder_outside_git_is_named_as_the_cause(tmp_path):
    folder = tmp_path / "plain"
    write(folder, "app.py", "value = 1\n")
    error = refusal("prepare", "--repo", str(folder))
    assert error["code"] == "git_read_failed"
    assert "Git could not open" in error["message"] and "git init" in error["message"]


def test_a_repository_without_a_commit_is_named_as_the_cause(source_repo):
    write(source_repo, "app.py", "value = 1\n")
    error = refusal("prepare", "--repo", str(source_repo))
    assert error["code"] == "revision_unavailable"
    assert "no commit yet" in error["message"]
    # A revision the user did name is the one the message points at.
    error = refusal("prepare", "--repo", str(source_repo), "--base", "no-such-branch")
    assert error["code"] == "revision_unavailable"
    assert "no-such-branch is not a commit" in error["message"]


@pytest.mark.parametrize(
    "problem",
    [
        PermissionError(errno.EACCES, "Permission denied", ".genesis"),
        OSError(errno.EROFS, "Read-only file system", ".genesis"),
    ],
)
def test_a_directory_genesis_cannot_write_is_reported_as_such(source_repo, monkeypatch, problem):
    from genesis_ci.business_map import session

    def refuse(*args, **kwargs):
        raise problem

    monkeypatch.setattr(session, "prepare", refuse)
    error = refusal("prepare", "--repo", str(source_repo), "--engine", "python")
    assert error["code"] == "cannot_write"
    assert ".genesis/" in error["message"]


def test_query_without_a_target_is_a_json_refusal(source_repo):
    error = refusal("query", "--repo", str(source_repo), "--session", "ses_x")
    assert error["code"] == "invalid_option"
    assert "--symbol" in error["message"] and "--search" in error["message"]


class _Distribution:
    def __init__(self, direct_url):
        self.direct_url = direct_url

    def read_text(self, name):
        return self.direct_url if name == "direct_url.json" else None


@pytest.mark.parametrize(
    ("direct_url", "expected"),
    [
        (
            json.dumps(
                {
                    "url": "https://example.invalid/genesis.git",
                    "vcs_info": {"vcs": "git", "commit_id": "1a2b3c4d5e6f" + "0" * 28},
                }
            ),
            "genesis-ci 0.1.0 (commit 1a2b3c4)",
        ),
        (json.dumps({"url": "file:///src", "dir_info": {"editable": True}}), "genesis-ci 0.1.0"),
        (None, "genesis-ci 0.1.0"),
        ("not json", "genesis-ci 0.1.0"),
    ],
)
def test_version_names_the_commit_it_was_installed_from(monkeypatch, direct_url, expected):
    from importlib import metadata

    monkeypatch.setattr(cli, "__version__", "0.1.0")
    monkeypatch.setattr(metadata, "distribution", lambda name: _Distribution(direct_url))
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0 and result.stdout.strip() == expected


def test_every_option_of_every_command_has_help():
    import typer.main

    def walk(command):
        yield command
        for child in getattr(command, "commands", {}).values():
            yield from walk(child)

    missing = [
        f"{command.name} {param.opts[0]}"
        for command in walk(typer.main.get_command(app))
        for param in command.params
        if param.param_type_name == "option" and not param.help
    ]
    assert missing == []

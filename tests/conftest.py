import os

import pytest
from test_git_snapshot import git


@pytest.fixture
def source_repo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Static Test")
    git(root, "config", "user.email", "static@example.invalid")
    return root


@pytest.fixture(autouse=True)
def no_user_git_configuration(monkeypatch):
    """A capture reads `core.autocrlf` from the Git configuration of the user running it;
    every test starts from none, whatever the machine it runs on has."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

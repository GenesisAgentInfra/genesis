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

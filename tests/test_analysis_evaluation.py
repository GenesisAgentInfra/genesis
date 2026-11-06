"""The offline corpus must only mutate its own disposable repositories."""

import json
import os
import subprocess
import sys
from pathlib import Path

from test_git_snapshot import commit, git, write

ROOT = Path(__file__).resolve().parents[1]


def test_analysis_evaluation_ignores_inherited_git_repository_overrides(source_repo):
    write(source_repo, "app.py", "value = 1\n")
    original_head = commit(source_repo)
    write(source_repo, "app.py", "value = 2\n")
    git(source_repo, "add", "app.py")
    write(source_repo, "app.py", "value = 3\n")
    metadata = {name: (source_repo / ".git" / name).read_bytes() for name in ("config", "index")}
    process_env = dict(
        os.environ,
        GIT_DIR=str(source_repo / ".git"),
        GIT_WORK_TREE=str(source_repo),
        GIT_INDEX_FILE=str(source_repo / ".git/index"),
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate_analysis.py"), "--case", "01-new-model-call"],
        cwd=ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    for name, original in metadata.items():
        assert (source_repo / ".git" / name).read_bytes() == original
    assert git(source_repo, "rev-parse", "HEAD").decode().strip() == original_head
    assert (source_repo / "app.py").read_text() == "value = 3\n"
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["passed"] == summary["total"] == 1

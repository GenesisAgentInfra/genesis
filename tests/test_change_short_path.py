"""A change session with no plan: prepare, diff, explain the changes, render."""

import os
import time

import genesis_ci.business_map.changes as changes_module
import pytest
from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from test_change_analysis import BASE, HEAD, SUBMIT_TEST, assessed, by_kind, two_commits
from test_git_snapshot import commit, git, write
from test_map_loop import planned

SKELETON = "affected_flow_not_synthesized"
UNTRACKED = "untracked_files_left_out"
APP = {"app/__init__.py": "", "app/core.py": "def run():\n    return 1\n"}


@pytest.fixture
def change(source_repo):
    return two_commits(source_repo, BASE, HEAD)[0]


def report_of(repo, result):
    return Workspace(repo, result["session_id"]).stored_report()


def limitation(report, code):
    return next((item for item in report.limitations if item.code == code), None)


def test_listing_other_changed_files_runs_no_hook_and_writes_no_index(source_repo, tmp_path):
    marker = tmp_path / "executed"
    files = {
        **APP,
        "docs/guide.md": "old\n",
        "docs/notes.md": "same\n",
        "docs/readme.txt": "kept\n",
        ".gitattributes": "*.md filter=evil\n*.txt filter=other\n",
    }
    for path, text in files.items():
        write(source_repo, path, text)
    commit(source_repo)
    git(source_repo, "config", "core.fsmonitor", f"touch {marker}")
    git(source_repo, "config", "filter.evil.clean", f"touch {marker}")
    git(source_repo, "config", "filter.other.process", f"touch {marker}")
    git(source_repo, "config", "filter.other.required", "true")
    write(source_repo, "docs/guide.md", "new\n")
    write(source_repo, "app/core.py", APP["app/core.py"].replace("1", "2"))
    # The index no longer matches the files' metadata, one of them only touched: a
    # refresh would rewrite it. Every other entry is newer than the index itself, so
    # Git re-reads those files, through their filters, to tell whether they changed.
    later = time.time() + 60
    for path in ("docs/guide.md", "docs/notes.md", "app/core.py"):
        os.utime(source_repo / path, (later, later))
    index = source_repo / ".git" / "index"
    os.utime(index, (later - 3600, later - 3600))
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    result = prepare(source_repo, base="HEAD")
    assert not marker.exists()
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    # A file only touched is no change; one whose bytes differ is listed by name.
    report = report_of(source_repo, result)
    assert [(item.path, item.change) for item in report.unanalyzed_changes] == [
        ("docs/guide.md", "modified")
    ]


def test_status_offers_the_change_task_without_a_plan(change):
    status = change.status()
    assert status["plan"] is None and status["change"]["changes_waiting"] == 4
    assert status["next_task"] == CHANGE_TASK
    result = change.submit(CHANGE_TASK, assessed(change.stored_report(), SUBMIT_TEST))
    assert result["status"] == "accepted" and result["changes_waiting"] == 0
    assert change.status()["next_task"] is None


def test_prepare_again_says_it_kept_the_explanations(source_repo):
    workspace, first = two_commits(source_repo, BASE, HEAD)
    assert first["resumed"] is False
    condition = by_kind(workspace.stored_report(), "condition_modified").change_id
    summary = "阈值改为包含 100。"
    entry = {"change_id": condition, "summary": summary}
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    again = prepare(source_repo, base="base", head="HEAD")
    assert again["session_id"] == first["session_id"] and again["resumed"] is True
    kept = by_kind(report_of(source_repo, again), "condition_modified")
    assert kept.explanation.summary == summary


def test_a_report_without_a_plan_says_no_flow_was_described(change):
    result = change.submit(CHANGE_TASK, assessed(change.stored_report(), SUBMIT_TEST))
    # Every change is explained; only the flows the changes sit on are not described.
    assert result["changes_waiting"] == 0 and result["analysis_status"] == "partial"
    assert result["limitations"] == [SKELETON]
    message = limitation(change.stored_report(), SKELETON).message
    assert message.startswith("No flow was described: changes are placed on flows that")
    assert "POST /reports · submit_report" in message and "do not depend on it" in message
    # With a plan, the flows it has not described yet are named as before.
    planned(change)
    message = limitation(change.stored_report(), SKELETON).message
    assert message.startswith("Changes are placed on flows that are still a static skeleton")


def test_the_change_context_lists_unexplained_changes_first(change, monkeypatch):
    report = change.stored_report()
    owed = [item.change_id for item in report.owed()]
    rest = [item.change_id for item in report.changes if item.change_id not in owed]
    context = change.context(CHANGE_TASK)
    assert (context["changes_waiting"], context["changes_unexplained"]) == (4, 8)
    # The changes a flow reaches first, then those no flow reaches.
    assert [view["change_id"] for view in context["changes"]] == [*owed, *rest]
    change.submit(CHANGE_TASK, assessed(report, SUBMIT_TEST))
    context = change.context(CHANGE_TASK)
    assert (context["state"], context["changes_waiting"]) == ("validated", 0)
    assert context["changes_unexplained"] == len(rest) == 4
    listed = context["changes"]
    assert [view["change_id"] for view in listed] == [*rest, *owed]
    assert [view["previous"] is None for view in listed] == [True] * 4 + [False] * 4
    # Paged, each call starts with what still has no explanation.
    monkeypatch.setattr(changes_module, "CONTEXT_LIMIT", 2)
    first = change.context(CHANGE_TASK)
    assert [view["change_id"] for view in first["changes"]] == rest[:2]
    entries = [{"change_id": key, "summary": "说明"} for key in rest[:2]]
    assert change.submit(CHANGE_TASK, {"changes": entries})["status"] == "accepted"
    second = change.context(CHANGE_TASK)
    assert [view["change_id"] for view in second["changes"]] == rest[2:]
    assert second["changes_unexplained"] == 2


def test_untracked_files_left_out_are_named_in_the_report(source_repo):
    for path, text in APP.items():
        write(source_repo, path, text)
    commit(source_repo)
    write(source_repo, "app/core.py", APP["app/core.py"].replace("1", "2"))
    write(source_repo, "notes.txt", "draft\n")
    result = prepare(source_repo, base="HEAD")
    assert result["untracked_left_out"] == 1
    found = limitation(report_of(source_repo, result), UNTRACKED)
    assert not found.affects_completeness
    assert found.message.startswith("1 untracked file left out of the comparison: notes.txt.")
    # Source left out may hold changes, so the report cannot be complete without it.
    write(source_repo, "app/extra.py", "def extra():\n    return 3\n")
    result = prepare(source_repo, base="HEAD")
    report = report_of(source_repo, result)
    found = limitation(report, UNTRACKED)
    assert found.affects_completeness and report.analysis_status == "partial"
    assert found.message.startswith(
        "2 untracked files left out of the comparison, 1 of them source Genesis analyzes: "
        "app/extra.py, notes.txt. If they belong to the change, run `prepare` again with "
        "`--include-untracked`"
    )
    status = Workspace(source_repo, result["session_id"]).status()["change"]
    assert UNTRACKED in status["limitations"]
    # Included, they belong to the change: source is analyzed, the rest listed by name.
    result = prepare(source_repo, base="HEAD", include_untracked=True)
    report = report_of(source_repo, result)
    assert "untracked_left_out" not in result and limitation(report, UNTRACKED) is None
    assert [(item.path, item.change) for item in report.unanalyzed_changes] == [
        ("notes.txt", "added")
    ]
    assert any(item.symbol_id.startswith("app/extra.py#") for item in report.changes)

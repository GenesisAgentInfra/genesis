"""Risks an agent sees in a change, and where a new jump in the code lands."""

import re

from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.business_map.render import render_summary
from test_change_analysis import by_kind, two_commits
from test_map_loop import codes

FETCH = """def fetch(urls):
    results = []
    for url in urls:
{guard}        results.append(get(url))
    record_failure()
    return results


def get(url):
    return url


def record_failure():
    return None


def total(values):
{early}    return sum(values)


def report():
    return total([1])
"""
BASE = {"app/__init__.py": "", "app/fetch.py": FETCH.format(guard="", early="")}
HEAD = {
    **BASE,
    "app/fetch.py": FETCH.format(
        guard="        if not url:\n            break\n",
        early="    if not values:\n        return 0\n",
    ),
}


def view_of(workspace, change_id):
    return next(
        item for item in workspace.context(CHANGE_TASK)["changes"] if item["change_id"] == change_id
    )


def test_a_new_break_or_return_shows_the_unchanged_code_it_lands_on(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    report = workspace.stored_report()
    stop = by_kind(report, "condition_added", "#fetch")
    # After the loop, the code that runs next is not part of any change.
    assert view_of(workspace, stop.change_id)["lands_on"] == [
        {
            "jump": "break",
            "line": 5,
            "next": {"path": "app/fetch.py", "line": 7, "text": "record_failure()"},
        }
    ]
    early = by_kind(report, "condition_added", "#total")
    assert view_of(workspace, early.change_id)["lands_on"] == [
        {
            "jump": "return 0",
            "line": 21,
            "callers": [{"path": "app/fetch.py", "line": 26, "text": "total([1])"}],
        }
    ]


def test_risks_are_submitted_with_the_changes_and_shown_apart(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    stop = by_kind(workspace.stored_report(), "condition_added", "#fetch").change_id
    risk = {
        "statement": "空地址会提前结束循环，后面的地址都不再抓取，随后照样记一次失败。",
        "severity": "medium",
        "change_ids": [stop],
        "evidence": [
            {"path": "app/fetch.py", "start_line": 7, "end_line": 7, "quote": "record_failure()"}
        ],
    }
    result = workspace.submit(CHANGE_TASK, {"risks": [risk]})
    assert result["status"] == "accepted" and result["risks"] == 1
    # The same risk submitted again replaces the first.
    assert workspace.submit(CHANGE_TASK, {"risks": [risk]})["risks"] == 1
    report = workspace.stored_report()
    [found] = report.risks
    assert found.statement == risk["statement"] and found.change_ids == (stop,)
    assert found.severity == "medium" and found.support == "agent_synthesis"
    assert {ref.path for ref in report.evidence if ref.evidence_id in found.evidence_ids} == {
        "app/fetch.py"
    }
    summary = render_summary(workspace.stored_map(), report)
    assert "## Risks seen in the changes (agent reading)" in summary
    # Pasted into a pull request, the risk names the code it cites, not a change id.
    assert f"- medium: {risk['statement']} (at app/fetch.py:7)" in summary
    assert stop not in summary
    assert not re.search(r"\b1 (changes|flows)\b", summary)
    assert workspace.change_summary()["risks"][0]["statement"] == risk["statement"]

    def refused(**fields):
        result = workspace.submit(CHANGE_TASK, {"risks": [{**risk, **fields}]})
        assert result["status"] == "rejected"
        return codes(result)

    assert refused(change_ids=["chg_missing"]) == [("risks[0].change_ids", "unknown_change")]
    assert refused(severity="high")[0][1] == "invalid_literal_error"
    assert workspace.submit(CHANGE_TASK, {})["status"] == "rejected"

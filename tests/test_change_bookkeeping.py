"""What it takes to hand Genesis the explanations and risks of a change."""

import json

from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.cli import app
from test_change_analysis import by_kind, two_commits
from test_change_risks import BASE, HEAD
from test_map_loop import (
    API,
    REVIEW,
    codes,
    planned,
    src,
    submit_flow,
    workspace,  # noqa: F401  (fixture)
)
from typer.testing import CliRunner


def changes_of(work):
    report = work.stored_report()
    return (
        by_kind(report, "condition_added", "#fetch").change_id,
        by_kind(report, "condition_added", "#total").change_id,
    )


def risk(change_id, start, quote):
    return {
        "statement": "空地址会提前结束循环，后面的地址都不再抓取。",
        "change_ids": [change_id],
        "evidence": [
            {"path": "app/fetch.py", "start_line": start, "end_line": start, "quote": quote}
        ],
    }


def test_a_quote_cited_a_few_lines_off_is_found_near_the_lines_given(source_repo):
    work, _ = two_commits(source_repo, BASE, HEAD)
    stop, _ = changes_of(work)
    # `record_failure()` is on line 7; the citation says line 5.
    result = work.submit(CHANGE_TASK, {"risks": [risk(stop, 5, "record_failure()")]})
    assert result["status"] == "accepted"
    assert result["evidence_moved"] == [
        {"path": "risks[0].evidence[0]", "cited": [5, 5], "found": [7, 7]}
    ]
    [found] = work.stored_report().risks
    [ref] = [
        item for item in work.stored_report().evidence if item.evidence_id in found.evidence_ids
    ]
    assert (ref.range.start_line, ref.range.end_line) == (7, 7)
    # Six lines away is too far: the citation is refused as before.
    far = work.submit(CHANGE_TASK, {"risks": [risk(stop, 12, "results.append(get(url))")]})
    assert codes(far) == [("risks[0].evidence[0]", "quote_not_found")]


def test_a_submission_can_be_read_from_standard_input(source_repo):
    work, _ = two_commits(source_repo, BASE, HEAD)
    stop, _ = changes_of(work)
    common = ["--repo", str(source_repo), "--session", work.session["session_id"]]
    answer = json.dumps({"risks": [risk(stop, 7, "record_failure()")]}, ensure_ascii=False)
    result = CliRunner().invoke(
        app, ["map", "submit", *common, "--task", CHANGE_TASK, "--input", "-"], input=answer
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "accepted"
    assert len(work.stored_report().risks) == 1


def test_one_explanation_can_cover_the_parts_of_one_change_in_behaviour(source_repo):
    work, _ = two_commits(source_repo, BASE, HEAD)
    stop, early = changes_of(work)
    entry = {
        "change_ids": [stop, early],
        "summary": "空输入不再往下处理。",
        "verdict": "not_reached",
        "note": "没有测试调用 fetch 或 total。",
    }
    result = work.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "accepted" and result["assessed"] == 2
    report = work.stored_report()
    for change_id in (stop, early):
        [item] = [change for change in report.changes if change.change_id == change_id]
        assert item.explanation.summary == "空输入不再往下处理。"
        assert item.tests.verdict == "not_reached"
    # A problem with one of the changes names that change at its place in the list.
    refused = work.submit(CHANGE_TASK, {"changes": [{**entry, "change_ids": [stop, "chg_x"]}]})
    assert codes(refused) == [("changes[0].change_ids[1]", "unknown_change")]
    assert refused["errors"][0]["item"] == "change chg_x"
    # A change is explained once per submission, alone or in a group.
    twice = {"changes": [entry, {"change_id": early, "summary": "x"}]}
    assert codes(work.submit(CHANGE_TASK, twice))[0][1] == "invalid_duplicate"
    both = {**entry, "change_id": stop}
    assert work.submit(CHANGE_TASK, {"changes": [both]})["status"] == "rejected"


def test_an_observation_is_found_near_its_lines_and_a_step_is_not(workspace):  # noqa: F811
    task = planned(workspace)["提交报销"]
    submission = submit_flow(workspace, task)
    # `while True` is on line 7 of the review module; the observation says 9 to 10.
    submission["observations"][0]["evidence"] = [src(REVIEW, 9, "while True", 10)]
    result = workspace.submit(task, submission)
    assert result["status"] == "accepted"
    assert result["evidence_moved"] == [
        {"path": "observations[0].evidence[0]", "cited": [9, 10], "found": [7, 8]}
    ]
    # A step's lines decide what it anchors, so they still have to be right.
    submission["steps"][4]["evidence"] = [src(API, 13, '"pending_approval"')]
    assert codes(workspace.submit(task, submission)) == [
        ("steps[4].evidence[0]", "quote_not_found")
    ]


def test_the_skill_reads_for_risks_in_a_pass_of_its_own():
    import re
    from importlib.resources import files

    text = files("genesis_ci").joinpath("assets/skills/genesis/SKILL.md").read_text()
    step = text.split("4. Read for risks", 1)[1].split("5. `render`", 1)[0]
    for angle in (
        "**Inputs.**",
        "**The same input, before and after.**",
        "**Failures.**",
        "**Other readers.**",
        "**Files Genesis does not analyze**",
    ):
        assert angle in step
    assert "once the explanations are accepted" in step and "a submission of its own" in step
    # A gap in the tests is the verdict's business, not a risk.
    assert "a gap in the tests (it goes in the verdict's `note`)" in step
    assert "tests do not probe" not in text
    example = json.loads(re.findall(r"```json\n(.*?)```", text, re.S)[3])
    assert all("test" not in item["statement"] for item in example["risks"])

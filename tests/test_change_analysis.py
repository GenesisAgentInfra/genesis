"""Change analysis: the fact diff, its placement on the map, and the change task."""

import json

import pytest
from genesis_ci.business_map.changes import CHANGE_TASK, CITED, NEAREST_REMOVED
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import LoopError, Workspace
from genesis_ci.cli import app
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.map_tasks import MapPlan
from test_git_snapshot import commit, git, write
from test_map_loop import API, FILES, REVIEW, approve_flow, codes, planned, src, submit_flow
from typer.testing import CliRunner

STORE = "expense/store.py"
TEST_SUBMIT = "tests/test_submit.py"
TEST_STORE = "tests/test_store.py"
SUBMIT_TEST = "head::tests/test_submit.py#test_submit_report_status"
SMOKE_TEST = "head::tests/test_submit.py#test_submit_smoke"
STORE_TEST = "head::tests/test_store.py#test_save_status_records_the_status"
HEAD = {
    **FILES,
    TEST_SUBMIT: """import pytest

from expense.api import submit_report


@pytest.mark.parametrize("amount", [50, 500])
async def test_submit_report_status(amount):
    result = await submit_report({"id": "r1", "amount": amount})
    assert result["status"] in {"approved", "pending_approval"}


async def test_submit_smoke():
    await submit_report({"id": "r2", "amount": 1})
""",
    TEST_STORE: """from expense.store import REPORTS, save_status


def test_save_status_records_the_status():
    save_status("r1", "approved")
    assert REPORTS["r1"]["status"] == "approved"
""",
    "docs/guide.md": "new\n",
}
# Base: a lower, exclusive threshold; one model call; an extra status write; a version
# route and an archive helper that the head no longer has.
BASE = {
    **HEAD,
    API: HEAD[API]
    .replace("THRESHOLD = 100", "THRESHOLD = 50")
    .replace("amount >= THRESHOLD", "amount > THRESHOLD")
    .replace(
        '    save_status(report_id, "approved")\n',
        '    save_status(report_id, "reviewed")\n    save_status(report_id, "approved")\n',
    )
    + '\n\n@router.get("/version")\ndef version():\n    return {"version": 1}\n',
    REVIEW: """from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    response = await client.responses.create(model="gpt-5", input=str(report))
    return response.output_text
""",
    STORE: HEAD[STORE].replace(
        "def nightly_cleanup():\n    REPORTS.clear()\n",
        "def archive_reports():\n    return dict(REPORTS)\n\n\n"
        "def nightly_cleanup():\n    archive_reports()\n    REPORTS.clear()\n",
    ),
    TEST_STORE: HEAD[TEST_STORE].replace('== "approved"', "is not None"),
    "docs/guide.md": "old\n",
}


def two_commits(repo, base, head):
    for path, text in base.items():
        write(repo, path, text)
    commit(repo)
    git(repo, "tag", "base")
    for path in base.keys() - head.keys():
        (repo / path).unlink()
    for path, text in head.items():
        write(repo, path, text)
    commit(repo)
    result = prepare(repo, base="base", head="HEAD")
    return Workspace(repo, result["session_id"]), result


@pytest.fixture
def change(source_repo):
    return two_commits(source_repo, BASE, HEAD)[0]


def diff(repo, base, head):
    """Changes between two versions of a small package, as comparable tuples."""
    wrap = {"app/__init__.py": ""}
    workspace, _ = two_commits(repo, {**wrap, **base}, {**wrap, **head})
    return [
        (
            item.kind.value,
            item.before.text if item.before else None,
            item.after.text if item.after else None,
        )
        for item in workspace.stored_report().changes
    ], workspace.stored_report()


def by_kind(report, kind, tail=""):
    found = [item for item in report.changes if item.kind == kind and item.symbol_id.endswith(tail)]
    assert len(found) == 1, [(item.kind.value, item.symbol_id) for item in report.changes]
    return found[0]


def test_prepare_lists_every_change_without_any_agent_work(source_repo):
    workspace, result = two_commits(source_repo, BASE, HEAD)
    assert result["mode"] == "change" and result["change_status"] == "partial"
    report = workspace.stored_report()
    listed = sorted((item.kind.value, item.symbol_id.partition("#")[2]) for item in report.changes)
    assert listed == [
        ("call_removed", "approve_report"),
        ("call_removed", "nightly_cleanup"),
        ("condition_modified", "submit_report"),
        ("loop_added", "review_with_model"),
        ("source_modified", "<module>"),
        ("symbol_removed", "archive_reports"),
        ("symbol_removed", "version"),
        ("test_modified", "test_save_status_records_the_status"),
    ]
    assert result["changes"] == 8
    # The new loop is one change that shows everything that came with it.
    assert by_kind(report, "loop_added").after.text == (
        "while True:\n"
        '    response = await client.responses.create(model="gpt-5", input=str(report))\n'
        "    if response.output_text:\n"
        "        return response.output_text"
    )
    assert report.base_ref == "base" and report.head_ref == "HEAD"
    assert report.base_revision != report.head_revision
    threshold = by_kind(report, "source_modified")
    assert (threshold.before.text, threshold.after.text) == ("THRESHOLD = 50", "THRESHOLD = 100")
    condition = by_kind(report, "condition_modified")
    assert (condition.before.text, condition.after.text) == (
        "amount > THRESHOLD",
        "amount >= THRESHOLD",
    )
    assert condition.before.side == "base" and condition.after.side == "head"
    # A file outside the analyzed languages is listed, never silently dropped.
    assert [(item.path, item.change) for item in report.unanalyzed_changes] == [
        ("docs/guide.md", "modified")
    ]
    assert [flow.entries[0].attributes["path"] for flow in report.removed_flows] == ["/version"]
    limits = {item.code: item.affects_completeness for item in report.limitations}
    assert limits == {
        "changed_files_outside_languages": False,
        "affected_flow_not_synthesized": True,
        "no_execution_data": False,
    }


def test_formatting_and_reordering_are_not_changes(source_repo):
    base = {
        "app/core.py": "def first(x):\n    if x:\n        return compute(x, 1)\n    return 0\n\n\n"
        "def compute(a, b):\n    return a + b\n"
    }
    head = {
        "app/core.py": "def compute(a, b):\n    # add\n    return a + b\n\n\n"
        "def first(x):\n\n    if x:\n        return compute(\n            x,\n            1,\n        )\n"
        "    return 0\n"
    }
    changes, report = diff(source_repo, base, head)
    assert changes == []
    assert report.analysis_status == "complete"


def test_an_edit_nested_in_another_is_reported_once(source_repo):
    changes, _ = diff(
        source_repo,
        {"app/core.py": "def run(x):\n    return send(build(x, 1))\n"},
        {"app/core.py": "def run(x):\n    return send(build(x, 2))\n"},
    )
    assert changes == [("result_modified", "return send(build(x, 1))", "return send(build(x, 2))")]


def test_changes_the_text_alone_does_not_show_carry_a_detail(source_repo):
    base = {
        "app/core.py": "def run(items, flag):\n    for item in items:\n        handle(item)\n"
        "    if flag:\n        start()\n    else:\n        stop()\n"
    }
    head = {
        "app/core.py": "def run(items, flag):\n    for item in items:\n        handle(item)\n"
        "        break\n    if flag:\n        stop()\n    else:\n        start()\n"
    }
    _, report = diff(source_repo, base, head)
    loop = by_kind(report, "loop_bound_changed")
    assert loop.before.text == loop.after.text == "for item in items"
    assert "`break` added inside the loop." in loop.detail
    condition = by_kind(report, "condition_modified")
    assert "`start()` moved from branch 'true' to branch 'false'." in condition.detail
    assert "`stop()` moved from branch 'false' to branch 'true'." in condition.detail
    assert len(report.changes) == 2


def test_code_wrapped_in_a_new_condition_reports_only_the_condition(source_repo):
    changes, _ = diff(
        source_repo,
        {"app/core.py": "def run(x):\n    send(x)\n    return x\n"},
        {"app/core.py": "def run(x):\n    if x:\n        send(x)\n    return x\n"},
    )
    assert changes == [("condition_added", None, "if x:\n    send(x)")]


def test_definitions_that_only_moved_are_one_change(source_repo):
    body = "def helper(x):\n    if x:\n        return 1\n    return 2\n"
    changes, _ = diff(
        source_repo,
        {"app/old.py": body, "app/core.py": "def keep():\n    return 1\n"},
        {"app/new.py": body, "app/core.py": "def keep():\n    return 1\n"},
    )
    assert changes == [("symbol_moved", "file app/old.py", "file app/new.py")]


def test_a_function_moved_to_another_file_is_not_added_and_removed(source_repo):
    helper = "def helper(x):\n    if x:\n        return 1\n    return 2\n"
    changes, _ = diff(
        source_repo,
        {"app/a.py": "A = 1\n\n\n" + helper, "app/b.py": "B = 1\n"},
        {"app/a.py": "A = 1\n", "app/b.py": "B = 1\n\n\n" + helper},
    )
    assert changes == [("symbol_moved", "function app/a.py#helper", "function app/b.py#helper")]


def test_a_call_that_now_leads_elsewhere_is_reported(source_repo):
    files = {
        "app/a.py": "def helper():\n    return 1\n",
        "app/b.py": "def helper():\n    return 2\n",
    }
    use = "\n\ndef run():\n    return helper()\n"
    _, report = diff(
        source_repo,
        {**files, "app/core.py": "from .a import helper" + use},
        {**files, "app/core.py": "from .b import helper" + use},
    )
    target = by_kind(report, "call_target_changed")
    assert target.before.text == target.after.text == "helper()"
    assert "app/b.py#helper" in target.detail and "app/a.py#helper" in target.detail
    # The import line itself is listed too, as source.
    assert by_kind(report, "source_modified").after.text == "from .b import helper"


def test_source_that_is_not_a_fact_is_still_listed(source_repo):
    base = {
        "app/core.py": 'def run(x, retries=1):\n    """Run once."""\n    limit = 10\n    return x\n'
    }
    head = {
        "app/core.py": 'def run(x, retries=3):\n    """Run once."""\n    limit = 20\n'
        "    total = x\n    return x\n"
    }
    changes, _ = diff(source_repo, base, head)
    assert changes == [
        ("source_modified", "def run(x, retries=1):", "def run(x, retries=3):"),
        ("source_modified", "limit = 10", "limit = 20\ntotal = x"),
    ]


def test_a_new_function_is_one_change_beside_the_call_to_it(source_repo):
    changes, _ = diff(
        source_repo,
        {"app/core.py": "def run(x):\n    return x\n"},
        {
            "app/core.py": "def run(x):\n    audit(x)\n    return x\n\n\n"
            "def audit(x):\n    if x:\n        raise ValueError(x)\n"
        },
    )
    assert changes == [
        ("call_added", None, "audit(x)"),
        ("symbol_added", None, "def audit(x):"),
    ]


def assessed(report, tests):
    """One assessment per placed change, each with a verdict the test index allows."""
    found = []
    for item in report.changes:
        if item.projection.status == "unassigned":
            continue
        entry = {"change_id": item.change_id, "summary": f"说明 {item.kind.value}"}
        if item.tests.verdict == "reached_only":
            entry.update(
                verdict="reached_only",
                note="测试只用了 50 和 500，没有覆盖边界值，也没有断言审核次数。",
                test_ids=[tests],
            )
        else:
            entry.update(verdict="not_reached", note="没有测试调用审批接口。")
        found.append(entry)
    return {"changes": found}


def test_changes_are_placed_on_the_steps_of_the_head_map(change):
    tasks = planned(change)
    before = change.status()
    # The flows the changes land on come first, then the changes themselves.
    assert before["change"]["analysis_status"] == "partial"
    assert before["next_task"] in tasks.values()
    change.submit(tasks["提交报销"], submit_flow(change, tasks["提交报销"]))
    change.submit(tasks["经理审批"], approve_flow(change, tasks["经理审批"]))
    status = change.status()
    assert status["analysis_status"] == "complete"
    assert status["next_task"] == CHANGE_TASK
    assert status["change"]["changes_placed"] == 4 and status["change"]["changes_waiting"] == 4
    assert status["change"]["limitations"] == []
    assert [(flow["name"], flow["stage"]) for flow in status["change"]["affected_flows"]] == [
        ("提交报销", "synthesized"),
        ("经理审批", "synthesized"),
    ]
    assert all(flow["entry_ids"] for flow in before["change"]["affected_flows"])
    report = change.stored_report()
    stored = change.stored_map()
    names = {step.step_id: step.name for flow in stored.flows for step in flow.steps}

    def placed(kind, tail=""):
        target = by_kind(report, kind, tail).projection
        return names.get(target.step_id), target.reason

    assert placed("condition_modified") == ("根据金额选择处理路径", None)
    step, reason = placed("source_modified")
    assert step == "根据金额选择处理路径" and "`THRESHOLD`" in reason
    assert placed("loop_added") == ("模型审核", None)
    assert placed("call_removed", "#approve_report") == ("检查是否待审批", NEAREST_REMOVED)
    for kind, tail in (("call_removed", "#nightly_cleanup"), ("symbol_removed", "#version")):
        target = by_kind(report, kind, tail).projection
        assert target.status == "unassigned" and target.reason
    assert "removed flows" in by_kind(report, "symbol_removed", "#version").projection.reason
    assert by_kind(report, "test_modified").tests is None
    # The agent's observation cites the loop this change added.
    assert [(item.status, item.finding.statement) for item in report.finding_changes] == [
        ("introduced", "模型审核在没有次数上限的循环里调用模型。")
    ]
    assert by_kind(report, "loop_added").finding_ids == (
        report.finding_changes[0].finding.finding_id,
    )


def test_static_test_evidence_never_claims_more_than_a_call_path(change):
    report = change.stored_report()
    condition = by_kind(report, "condition_modified").tests
    assert condition.verdict == "reached_only" and condition.basis == ("static_fact",)
    assert condition.execution_data == "not_collected"
    cases = {case.test_id: case.tags for case in condition.items}
    assert cases == {
        SUBMIT_TEST: ("related", "assertion_found"),
        SMOKE_TEST: ("related",),
    }
    # The constant is related to the tests of the code that uses it.
    assert by_kind(report, "source_modified").tests.verdict == "reached_only"
    removed = by_kind(report, "call_removed", "#approve_report").tests
    assert removed.verdict == "unknown" and removed.note.startswith("No test was found")
    assert removed.items == ()


def test_the_change_task_takes_explanations_and_checks_verdicts(change):
    tasks = planned(change)
    change.submit(tasks["提交报销"], submit_flow(change, tasks["提交报销"]))
    change.submit(tasks["经理审批"], approve_flow(change, tasks["经理审批"]))
    context = change.context(CHANGE_TASK)
    assert context["state"] == "pending" and context["changes_waiting"] == 4
    view = next(item for item in context["changes"] if item["kind"] == "condition_modified")
    assert view["before"]["text"] == "amount > THRESHOLD"
    assert view["placement"] == {
        "status": "projected",
        "flow": "提交报销",
        "step": "根据金额选择处理路径",
        "reason": None,
    }
    assert view["tests"]["verdict"] == "reached_only"
    assert {item["test_id"] for item in view["tests"]["tests"]} == {SUBMIT_TEST, SMOKE_TEST}
    # Both sides can be read back through the session.
    assert "amount > THRESHOLD" in change.read(view["before"]["evidence_id"])["text"]
    assert change.read(view["before"]["evidence_id"])["side"] == "base"

    report = change.stored_report()
    condition = by_kind(report, "condition_modified").change_id
    approve = by_kind(report, "call_removed", "#approve_report").change_id

    def refused(**fields):
        entry = {"change_id": condition, "summary": "阈值改为包含 100。", **fields}
        result = change.submit(CHANGE_TASK, {"changes": [entry]})
        assert result["status"] == "rejected" and result["accepted_version_kept"]
        return codes(result)

    assert refused(change_id="chg_missing") == [("changes[0].change_id", "unknown_change")]
    # A verdict without a note explaining it is not a valid submission.
    assert refused(verdict="covered") == [("changes[0]", "invalid_value_error")]
    assert refused(verdict="covered", note="x", test_ids=["head::nope"]) == [
        ("changes[0].test_ids", "unknown_test")
    ]
    wrong = {"change_id": condition, "summary": "x", "verdict": "covered", "note": "x"}
    wrong["test_ids"] = ["tests/other.py#test_submit_report_status"]
    message = change.submit(CHANGE_TASK, {"changes": [wrong]})["errors"][0]["message"]
    assert "`head::<path>#<function>`" in message and SUBMIT_TEST in message
    assert refused(verdict="not_reached", note="x", test_ids=[STORE_TEST]) == [
        ("changes[0].verdict", "tests_reach_change")
    ]
    assert refused(verdict="covered", note="x", test_ids=[SMOKE_TEST]) == [
        ("changes[0].verdict", "covered_needs_assertion")
    ]
    assert refused(verdict="not_reached", note="x") == [
        ("changes[0].verdict", "tests_reach_change")
    ]
    assert change.stored_report().changes == report.changes

    # The side prefix of a test id may be left out.
    result = change.submit(CHANGE_TASK, assessed(report, SUBMIT_TEST.removeprefix("head::")))
    assert result["status"] == "accepted" and result["assessed"] == 4
    assert result["analysis_status"] == "complete" and result["changes_waiting"] == 0
    final = change.stored_report()
    item = by_kind(final, "condition_modified")
    assert item.explanation.summary == "说明 condition_modified"
    assert item.tests.verdict == "reached_only"
    assert item.tests.basis == ("static_fact", "agent_assessment")
    assert [case.test_id for case in item.tests.items] == [SUBMIT_TEST]
    gone = by_kind(final, "call_removed", "#approve_report")
    # Nothing static supports it, so the basis is the agent's assessment alone.
    assert gone.tests.verdict == "not_reached" and gone.tests.items == ()
    assert gone.tests.basis == ("agent_assessment",)
    status = change.status()
    assert status["next_task"] is None and status["change"]["analysis_status"] == "complete"
    assert change.context(CHANGE_TASK)["state"] == "validated"

    # A test the static index did not link can be named; it is marked as the agent's.
    named = {
        "change_id": approve,
        "summary": "审批不再写入 reviewed 状态。",
        "effect": "状态直接变为 approved。",
        "verdict": "covered",
        "note": "存储测试断言了最终状态。",
        "test_ids": [STORE_TEST],
    }
    assert change.submit(CHANGE_TASK, {"changes": [named]})["status"] == "accepted"
    gone = by_kind(change.stored_report(), "call_removed", "#approve_report")
    assert gone.tests.verdict == "covered" and gone.tests.basis == ("agent_assessment",)
    assert gone.tests.items[0].tags == ("agent_identified", "assertion_found")
    assert gone.explanation.effect == "状态直接变为 approved。"
    # Earlier assessments of other changes are kept.
    assert by_kind(change.stored_report(), "loop_added").explanation is not None


def test_a_flow_that_only_reaches_changed_code_is_listed_apart(source_repo):
    base = {
        "app/api.py": "from fastapi import APIRouter\n\nfrom .core import outer\n\n"
        'router = APIRouter()\n\n\n@router.get("/a")\ndef a():\n    return outer()\n',
        "app/core.py": "def outer():\n    return inner()\n\n\ndef inner():\n    return 1\n",
    }
    head = {**base, "app/core.py": base["app/core.py"].replace("return 1", "return 2")}
    _, report = diff(source_repo, base, head)
    item = by_kind(report, "result_modified")
    assert item.projection.status == "unassigned"
    assert "possibly affected" in item.projection.reason
    assert [(entry.change_ids, bool(entry.reason)) for entry in report.possibly_affected] == [
        ((item.change_id,), True)
    ]
    # Nothing is placed, so nothing needs an explanation.
    assert report.analysis_status == "complete"


def test_a_removed_function_points_at_the_flows_that_called_it(source_repo):
    base = {
        "app/api.py": "from fastapi import APIRouter\n\nfrom .core import audit\n\n"
        'router = APIRouter()\n\n\n@router.get("/a")\ndef a():\n    audit()\n    return 1\n',
        "app/core.py": "def audit():\n    return 1\n\n\ndef other():\n    return 2\n",
    }
    head = {
        "app/api.py": base["app/api.py"]
        .replace("from .core import audit\n\n", "")
        .replace("    audit()\n", ""),
        "app/core.py": "def other():\n    return 2\n",
    }
    _, report = diff(source_repo, base, head)
    removed = by_kind(report, "symbol_removed").projection
    assert removed.status == "removed_step" and removed.removed_step.name == "def audit():"
    call = by_kind(report, "call_removed").projection
    assert call.status == "projected" and call.reason == NEAREST_REMOVED


def test_cli_runs_a_change_session_end_to_end(source_repo, tmp_path, monkeypatch):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    session = workspace.session["session_id"]
    monkeypatch.setenv("GENESIS_NO_BROWSER", "1")
    runner = CliRunner()

    def run(*args):
        result = runner.invoke(
            app, ["map", *args, "--repo", str(source_repo), "--session", session]
        )
        return result.exit_code, result.stdout

    code, out = run("render")
    assert code == 2 and json.loads(out)["change_status"] == "partial"
    # Without any agent work the changes, their place and the static tests are there.
    code, out = run("diff")
    listed = json.loads(out)
    assert code == 0 and listed["changes_total"] == 8 and listed["changes_placed"] == 4
    assert listed["removed_flows"] == ["GET /version · version"]
    assert [item["path"] for item in listed["unanalyzed_changes"]] == ["docs/guide.md"]
    static = next(item for item in listed["changes"] if item["kind"] == "condition_modified")
    assert static["tests"]["verdict"] == "reached_only" and static["explanation"] is None
    assert "other_changed_files" not in listed and "previous" not in static
    assert static["placement"]["step"] == "amount >= THRESHOLD"
    tasks = planned(workspace)
    workspace.submit(tasks["提交报销"], submit_flow(workspace, tasks["提交报销"]))
    workspace.submit(tasks["经理审批"], approve_flow(workspace, tasks["经理审批"]))
    code, out = run("context", "--task", CHANGE_TASK)
    assert code == 0 and json.loads(out)["changes_waiting"] == 4
    answer = tmp_path / "changes.json"
    answer.write_text(json.dumps({"changes": [{"change_id": "chg_x", "summary": "x"}]}))
    code, out = run("submit", "--task", CHANGE_TASK, "--input", str(answer))
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "unknown_change"
    answer.write_text(
        json.dumps(assessed(workspace.stored_report(), SUBMIT_TEST), ensure_ascii=False)
    )
    code, out = run("submit", "--task", CHANGE_TASK, "--input", str(answer))
    assert code == 0 and json.loads(out)["analysis_status"] == "complete"
    code, out = run("render")
    result = json.loads(out)
    assert code == 0 and result["change_status"] == "complete"
    out_dir = source_repo / ".genesis" / "out" / "latest"
    assert result["change_report"] == str(out_dir / "change-report.json")
    code, out = run("diff")
    explained = next(i for i in json.loads(out)["changes"] if i["kind"] == "condition_modified")
    assert explained["explanation"] == {"summary": "说明 condition_modified"}
    ChangeReport.model_validate_json((out_dir / "change-report.json").read_text())
    page = (out_dir / "graph.html").read_text()
    assert "Genesis map with changes" in page and "amount &gt;= THRESHOLD" in page
    assert "说明 condition_modified" in page and "reached only" in page
    assert "docs/guide.md" in page and "no execution data collected" in page
    # The page is the map: a change is shown inside the step it belongs to, in a flow
    # that is open and counted, and only what has no step is listed apart.
    names = {s.name: s.step_id for flow in workspace.stored_map().flows for s in flow.steps}
    step = page.split(f'id="{names["根据金额选择处理路径"]}"')[1].split("</li>")[0]
    assert step.count('class="delta"') == 2 and "说明 source_modified" in step
    assert "THRESHOLD = 50" in step and "amount &gt; THRESHOLD" in step
    untouched = page.split(f'id="{names["标记为待审批"]}"')[1].split("</li>")[0]
    assert 'class="delta"' not in untouched
    assert page.count('<details class="flow"') == 3 and page.count("3 changes") >= 1
    flow_id = workspace.stored_map().flows[0].flow_id
    assert f'<details class="flow" id="{flow_id}" open>' in page
    assert f'<a href="#{flow_id}">提交报销</a>: 3 changes' in page
    apart = page.split('id="off-map"')[1]
    assert apart.count('class="delta"') == 4 and "archive_reports()" in apart
    assert page.index("Changes on the map") < page.index(flow_id) < page.index('id="off-map"')
    summary = (out_dir / "summary.md").read_text()
    assert (
        "## Changes on the map" in summary and "### 提交报销\n\n- 根据金额选择处理路径\n" in summary
    )
    assert "## Removed flows" in summary and "(tests: reached only)" in summary
    assert "## Changes not on the map\n\n- symbol removed in expense/api.py#version" in summary
    assert "  - This code is not reachable from any entry on the map." in summary
    assert "- Compared base (" in summary and ") with HEAD (" in summary
    assert "    - tests: " + SUBMIT_TEST in summary and "    - 测试只用了 50 和 500" in summary
    assert "    - placement: This step's code refers to `THRESHOLD`" in summary
    assert "- 提交报销 (7 steps, synthesized, changed)" in summary
    assert "covered: a test takes the changed path" in summary
    assert "Compared base (" in page and "1 changed file outside the supported languages" in page
    # The changes come before the map they are placed on.
    assert summary.index("## Changes on") < summary.index("# Map") < summary.index("## 报销")
    assert "before · expense/api.py:13" in page and "after · expense/api.py:13" in page
    code, out = run("render", "--share")
    shared = (out_dir / "graph.share.html").read_text()
    assert code == 0 and "<pre>" not in shared and "amount &gt;= THRESHOLD" in shared


def test_a_map_session_has_no_change_task(source_repo):
    for path, text in HEAD.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    assert "change" not in workspace.status()
    assert workspace.stored_report() is None
    for call in (
        lambda: workspace.context(CHANGE_TASK),
        lambda: workspace.submit(CHANGE_TASK, {"changes": []}),
        workspace.change_summary,
    ):
        with pytest.raises(LoopError, match="--base REV") as refusal:
            call()
        assert refusal.value.code == "not_a_change_session"


def test_the_change_example_in_the_bundled_skill_is_accepted(change):
    import re
    from importlib.resources import files

    text = files("genesis_ci").joinpath("assets/skills/genesis/SKILL.md").read_text()
    example = json.loads(re.findall(r"```json\n(.*?)```", text, re.S)[2])
    result = change.submit(CHANGE_TASK, example)
    assert result["status"] == "accepted" and result["assessed"] == 2, result
    report = change.stored_report()
    assert by_kind(report, "condition_modified").tests.verdict == "reached_only"
    assert by_kind(report, "call_removed", "#approve_report").tests.verdict == "not_reached"


def test_swapping_the_two_branches_of_a_condition_is_a_change(source_repo):
    # No fact appears or disappears; only the branch each call sits on differs.
    _, report = diff(
        source_repo,
        {
            "app/core.py": "def run(flag):\n    if flag:\n        start()\n    else:\n        stop()\n"
        },
        {
            "app/core.py": "def run(flag):\n    if flag:\n        stop()\n    else:\n        start()\n"
        },
    )
    assert [item.kind.value for item in report.changes] == ["condition_modified"]
    assert "`start()` moved from branch 'true' to branch 'false'." in report.changes[0].detail


def test_a_branch_that_came_or_went_is_one_change_with_its_body(source_repo):
    plain = "def refund(order):\n    pay(order)\n    return 1\n"
    guarded = (
        "def refund(order):\n"
        '    if order["total"] > 500:\n'
        '        log = "refused"\n'
        '        raise PermissionError("needs a manager")\n'
        "    pay(order)\n"
        "    return 1\n"
    )
    block = (
        'if order["total"] > 500:\n'
        '    log = "refused"\n'
        '    raise PermissionError("needs a manager")'
    )
    added, report = diff(source_repo, {"app/core.py": plain}, {"app/core.py": guarded})
    assert added == [("condition_added", None, block)]
    # The evidence is the whole block, not only the condition.
    cited = report.changes[0].after.evidence_ids[0]
    ref = next(item for item in report.evidence if item.evidence_id == cited)
    assert (ref.range.start_line, ref.range.end_line) == (2, 4)


def test_a_removed_loop_is_one_change_too(source_repo):
    looped = (
        "def run(x):\n    for item in x:\n        if item:\n            send(item)\n    return 1\n"
    )
    removed, _ = diff(
        source_repo, {"app/core.py": looped}, {"app/core.py": "def run(x):\n    return 1\n"}
    )
    assert removed == [("loop_removed", "for item in x:\n    if item:\n        send(item)", None)]


def test_a_call_that_is_the_whole_condition_is_not_listed_twice(source_repo):
    changes, _ = diff(
        source_repo,
        {"app/core.py": "def price(order):\n    total = 10\n    return total\n"},
        {
            "app/core.py": "def price(order):\n    total = 10\n"
            '    if order.get("coupon"):\n        total = round(total * 0.9, 2)\n    return total\n'
        },
    )
    assert changes == [
        ("condition_added", None, 'if order.get("coupon"):\n    total = round(total * 0.9, 2)')
    ]


SHOP = {
    "shop/__init__.py": "",
    "shop/api.py": """from fastapi import APIRouter

from .payments import charge

router = APIRouter()
LIMIT = 50


@router.post("/orders")
def create_order(order):
    if order["total"] >= LIMIT:
        return {"shipping": 0}
    charge(order["total"])
    return {"shipping": 5}


@router.post("/orders/{order_id}/refund")
def refund_order(order_id):
    return {"refunded": order_id}
""",
    "shop/payments.py": "def charge(amount):\n    return gateway(amount)\n\n\n"
    "def gateway(amount):\n    return amount\n",
    "tests/test_api.py": """from fastapi import FastAPI
from fastapi.testclient import TestClient

from shop.api import router

app = FastAPI()
app.include_router(router, prefix="/api")
client = TestClient(app)


def test_order():
    response = client.post("/api/orders", json={"total": 20})
    assert response.json()["shipping"] == 5


def test_refund():
    order_id = "o1"
    assert client.post(f"/api/orders/{order_id}/refund").status_code == 200


def test_other_method_and_path():
    assert client.get("/api/orders").status_code == 405
    assert client.post("/api/health").status_code == 404
""",
}


def test_tests_that_request_a_route_are_linked_to_its_handler(source_repo):
    head = {
        **SHOP,
        "shop/api.py": SHOP["shop/api.py"]
        .replace("LIMIT = 50", "LIMIT = 75")
        .replace('{"refunded": order_id}', '{"refunded": order_id, "ok": True}'),
        "shop/payments.py": SHOP["shop/payments.py"].replace(
            "return amount\n", "return amount * 100\n"
        ),
    }
    workspace, _ = two_commits(source_repo, SHOP, head)
    report = workspace.stored_report()

    def linked(kind, tail=""):
        tests = by_kind(report, kind, tail).tests
        return tests.verdict.value, [case.test_id.partition("#")[2] for case in tests.items]

    # The path may be mounted under a prefix and may be built with an f-string; the
    # method has to match.
    assert linked("source_modified") == ("reached_only", ["test_order"])
    assert linked("result_modified", "#refund_order") == ("reached_only", ["test_refund"])
    assert linked("result_modified", "#gateway") == ("reached_only", ["test_order"])

    def verdict(kind, tail=""):
        entry = {
            "change_id": by_kind(report, kind, tail).change_id,
            "summary": "x",
            "verdict": "not_reached",
            "note": "The test stubs the payment call.",
        }
        return workspace.submit(CHANGE_TASK, {"changes": [entry]})

    # A test that requests the route itself reaches the handler; that cannot be denied.
    assert codes(verdict("result_modified", "#refund_order")) == [
        ("changes[0].verdict", "tests_reach_change")
    ]
    # Reaching code only through other calls can be cut off, which the agent may judge.
    assert verdict("result_modified", "#gateway")["status"] == "accepted"
    judged = by_kind(workspace.stored_report(), "result_modified", "#gateway").tests
    assert (judged.verdict, judged.basis, judged.items) == (
        "not_reached",
        ("agent_assessment",),
        (),
    )


SENDER = """from fastapi import APIRouter

router = APIRouter()


@router.post("/send")
def send_order(order):
    priced = compute(order)
    fee = 5
    deliver(priced + fee)
    return {"ok": True}


def compute(order):
    return order["total"]


def deliver(amount):
    return amount
"""
STATUS_ROUTE = """

@router.get("/status")
def status():
    return deliver(0)
"""


def test_source_changes_go_to_the_step_citing_them_and_a_new_flow_owns_its_findings(source_repo):
    base = {"app/__init__.py": "", "app/api.py": SENDER}
    head = {**base, "app/api.py": SENDER.replace("fee = 5", "fee = 7") + STATUS_ROUTE}
    workspace, _ = two_commits(source_repo, base, head)
    entries = {item.symbol_id.partition("#")[2]: item for item in workspace.entries().values()}
    plan = {
        "flows": [
            {"key": "send", "entry_ids": [entries["send_order"].entry_id]},
            {"key": "status", "entry_ids": [entries["status"].entry_id]},
        ]
    }
    planned_tasks = workspace.save_plan(MapPlan.model_validate(plan))["tasks"]
    tasks = {task["flow_key"]: task["task_id"] for task in planned_tasks}

    def line(number, quote, end=None):
        return src("app/api.py", number, quote, end)

    def trigger(task):
        return workspace.context(task)["entries"][0]["anchor"]

    sent = {
        "name": "发送订单",
        "steps": [
            {
                "key": "in",
                "name": "收到订单",
                "kind": "trigger",
                "anchors": [trigger(tasks["send"])],
                "evidence": [line(6, "/send", 7)],
            },
            {
                "key": "price",
                "name": "计算金额",
                "kind": "action",
                "evidence": [line(8, "compute(order)")],
            },
            {
                "key": "ship",
                "name": "加上运费并发货",
                "kind": "action",
                "evidence": [line(9, "fee =", 10)],
            },
            {"key": "done", "name": "完成", "kind": "result", "evidence": [line(11, "return")]},
        ],
        "edges": [
            {"source": "in", "target": "price", "relation": "sequence"},
            {"source": "price", "target": "ship", "relation": "sequence"},
            {"source": "ship", "target": "done", "relation": "sequence"},
        ],
    }
    result = workspace.submit(tasks["send"], sent)
    assert result["status"] == "accepted", result
    looked = {
        "name": "查询状态",
        "steps": [
            {
                "key": "in",
                "name": "收到查询",
                "kind": "trigger",
                "anchors": [trigger(tasks["status"])],
                "evidence": [line(22, "/status", 23)],
            },
            {
                "key": "out",
                "name": "返回状态",
                "kind": "result",
                "evidence": [line(24, "deliver(0)")],
            },
        ],
        "edges": [{"source": "in", "target": "out", "relation": "sequence"}],
        "observations": [
            {
                "statement": "查询会触发一次发货调用。",
                "step": "out",
                "evidence": [line(18, "def deliver", 19)],
            }
        ],
    }
    result = workspace.submit(tasks["status"], looked)
    assert result["status"] == "accepted", result
    report = workspace.stored_report()
    names = {s.step_id: s.name for flow in workspace.stored_map().flows for s in flow.steps}
    fee = by_kind(report, "source_modified").projection
    # The nearest earlier step is "计算金额", but "加上运费并发货" cites the changed line.
    assert (names[fee.step_id], fee.reason) == ("加上运费并发货", CITED)
    route = by_kind(report, "symbol_added")
    assert route.after.text == '@router.get("/status")\ndef status():'
    assert names[route.projection.step_id] == "收到查询" and route.projection.reason is None
    # The observation cites unchanged code, but its whole flow is new.
    assert [(item.status, item.finding.statement) for item in report.finding_changes] == [
        ("introduced", "查询会触发一次发货调用。")
    ]


def test_removed_steps_and_reaching_flows_are_shown_on_their_flows(source_repo):
    from genesis_ci.business_map.render import render_html, render_summary

    base = {
        "app/__init__.py": "",
        "app/api.py": "from fastapi import APIRouter\n\nfrom .core import audit, outer\n\n"
        'router = APIRouter()\n\n\n@router.get("/a")\ndef a():\n    audit()\n    return outer()\n',
        "app/core.py": "def audit():\n    return 1\n\n\ndef outer():\n    return inner()\n\n\n"
        "def inner():\n    return 1\n",
    }
    head = {
        "app/__init__.py": "",
        "app/api.py": base["app/api.py"]
        .replace("import audit, outer", "import outer")
        .replace("    audit()\n", ""),
        "app/core.py": "def outer():\n    return inner()\n\n\ndef inner():\n    return 2\n",
    }
    workspace, _ = two_commits(source_repo, base, head)
    report, stored = workspace.stored_report(), workspace.stored_map()
    flow_id = stored.flows[0].flow_id
    assert by_kind(report, "symbol_removed").projection.status == "removed_step"
    reaching = by_kind(report, "result_modified")
    assert reaching.projection.status == "unassigned"
    page = render_html(stored, None, report)
    inside = page.split(f'<details class="flow" id="{flow_id}" open>')[1].split("</details>")[0]
    # The step that is gone closes the flow it belonged to, with the change on it.
    assert '<li class="step removed">' in inside and "def audit():" in inside
    assert "possibly affected" in inside and f'href="#{reaching.change_id}"' in inside
    # Off the map: the change two calls away, and the import line that went with it.
    apart = [item.kind.value for item in report.changes if item.projection.status == "unassigned"]
    assert apart == ["source_modified", "result_modified"]
    assert page.split('id="off-map"')[1].count('class="delta"') == 2
    summary = render_summary(stored, report)
    assert "- removed: def audit():" in summary
    assert "## Flows that can reach changed code" in summary

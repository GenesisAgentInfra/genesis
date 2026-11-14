"""The agent loop: plan, context, query, submit and the map assembled from them."""

import copy
import json

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import LoopError, Workspace
from genesis_ci.cli import app
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.map_tasks import MapPlan
from test_git_snapshot import commit, write
from typer.testing import CliRunner

API = "expense/api.py"
REVIEW = "expense/review.py"
FILES = {
    "expense/__init__.py": "",
    API: """from fastapi import APIRouter

from .review import review_with_model
from .store import load_report, save_status

router = APIRouter()
THRESHOLD = 100


@router.post("/reports")
async def submit_report(report):
    amount = report["amount"]
    if amount >= THRESHOLD:
        verdict = await review_with_model(report)
        save_status(report["id"], "pending_approval")
        return {"status": "pending_approval", "review": verdict}
    save_status(report["id"], "approved")
    return {"status": "approved"}


@router.post("/reports/{report_id}/approve")
async def approve_report(report_id):
    report = load_report(report_id)
    if report["status"] != "pending_approval":
        raise ValueError("report is not waiting for approval")
    save_status(report_id, "approved")
    return {"status": "approved", "id": report_id}


@router.get("/healthz")
def healthz():
    return {"ok": True}
""",
    REVIEW: """from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    while True:
        response = await client.responses.create(model="gpt-5", input=str(report))
        if response.output_text:
            return response.output_text
""",
    "expense/store.py": """REPORTS = {}


def save_status(report_id, status):
    REPORTS.setdefault(report_id, {})["status"] = status


def load_report(report_id):
    return REPORTS[report_id]


def nightly_cleanup():
    REPORTS.clear()
""",
}


def src(path, line, quote, end=None):
    return {"path": path, "start_line": line, "end_line": end or line, "quote": quote}


@pytest.fixture
def workspace(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    session = prepare(source_repo, head="HEAD")["session_id"]
    return Workspace(source_repo, session)


def entry(workspace, name):
    return next(item for item in workspace.entries().values() if item.symbol_id.endswith(name))


def planned(workspace):
    """An agent plan: two flows in one domain, the health check skipped."""
    plan = MapPlan.model_validate(
        {
            "domains": [{"key": "expense", "name": "报销"}],
            "flows": [
                {
                    "key": "submit",
                    "name": "提交报销",
                    "domain": "expense",
                    "entry_ids": [entry(workspace, "#submit_report").entry_id],
                },
                {
                    "key": "approve",
                    "name": "经理审批",
                    "domain": "expense",
                    "entry_ids": [entry(workspace, "#approve_report").entry_id],
                },
            ],
            "skipped": [
                {"entry_id": entry(workspace, "#healthz").entry_id, "reason": "infrastructure"}
            ],
        }
    )
    status = workspace.save_plan(plan)
    return {task["name"]: task["task_id"] for task in status["tasks"]}


def submit_flow(workspace, task_id):
    context = workspace.context(task_id)
    return {
        "name": "提交报销",
        "summary": "金额达到阈值时先由模型审核，否则自动批准。",
        "steps": [
            {
                "key": "recv",
                "name": "收到报销提交",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 10, '@router.post("/reports")', 11)],
            },
            {
                "key": "choose",
                "name": "根据金额选择处理路径",
                "kind": "decision",
                "evidence": [src(API, 13, "amount >= THRESHOLD")],
            },
            {
                "key": "review",
                "name": "模型审核",
                "kind": "external",
                "evidence": [
                    src(API, 14, "review_with_model(report)"),
                    src(REVIEW, 7, "while True", 10),
                ],
            },
            {
                "key": "pending",
                "name": "标记为待审批",
                "kind": "action",
                "evidence": [src(API, 15, '"pending_approval"')],
            },
            {
                "key": "ret_pending",
                "name": "返回待审批结果",
                "kind": "result",
                "evidence": [src(API, 16, '"review": verdict')],
            },
            {
                "key": "auto",
                "name": "自动批准",
                "kind": "action",
                "evidence": [src(API, 17, 'save_status(report["id"], "approved")')],
            },
            {
                "key": "ret_ok",
                "name": "返回已批准结果",
                "kind": "result",
                "evidence": [src(API, 18, 'return {"status": "approved"}')],
            },
        ],
        "edges": [
            {"source": "recv", "target": "choose", "relation": "sequence"},
            {
                "source": "choose",
                "target": "review",
                "relation": "branch",
                "branch": "true",
                "label": "达到阈值",
            },
            {
                "source": "choose",
                "target": "auto",
                "relation": "branch",
                "branch": "false",
                "label": "低于阈值",
            },
            {"source": "review", "target": "pending", "relation": "sequence"},
            {"source": "pending", "target": "ret_pending", "relation": "sequence"},
            {"source": "auto", "target": "ret_ok", "relation": "sequence"},
        ],
        "observations": [
            {
                "statement": "模型审核在没有次数上限的循环里调用模型。",
                "severity": "medium",
                "step": "review",
                "evidence": [src(REVIEW, 7, "while True", 8)],
            }
        ],
    }


def approve_flow(workspace, task_id):
    context = workspace.context(task_id)
    return {
        "name": "经理审批",
        "steps": [
            {
                "key": "recv",
                "name": "经理发起审批",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 21, "/approve", 22)],
            },
            {
                "key": "check",
                "name": "检查是否待审批",
                "kind": "decision",
                "evidence": [
                    src(API, 23, "load_report(report_id)"),
                    src(API, 24, 'report["status"]'),
                ],
            },
            {
                "key": "reject",
                "name": "拒绝",
                "kind": "result",
                "evidence": [src(API, 25, "raise ValueError")],
            },
            {
                "key": "done",
                "name": "返回已批准结果",
                "kind": "result",
                "evidence": [
                    src(API, 26, 'save_status(report_id, "approved")'),
                    src(API, 27, '"id": report_id'),
                ],
            },
        ],
        "edges": [
            {"source": "recv", "target": "check", "relation": "sequence"},
            {"source": "check", "target": "reject", "relation": "branch", "branch": "true"},
            {"source": "check", "target": "done", "relation": "branch", "branch": "false"},
        ],
    }


def codes(result):
    return [(item["path"], item["code"]) for item in result["errors"]]


def test_default_plan_makes_one_task_per_framework_entry(workspace):
    assert workspace.status()["plan"] is None
    with pytest.raises(LoopError, match="genesis map plan"):
        workspace.context("task_missing")
    status = workspace.save_plan(None)
    assert status["plan"] == "default" and len(status["tasks"]) == 3
    assert {task["state"] for task in status["tasks"]} == {"pending"}
    assert status["coverage"]["entries_planned"] == 3
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    assert {flow.stage for flow in stored.flows} == {"skeleton"}
    assert [domain.support for domain in stored.domains] == ["path_grouping"]


def test_agent_plan_groups_skips_and_can_propose_entries(workspace):
    tasks = planned(workspace)
    status = workspace.status()
    assert set(tasks) == {"提交报销", "经理审批"} and status["plan"] == "agent"
    coverage = status["coverage"]
    assert (coverage["entries_planned"], coverage["entries_skipped"]) == (2, 1)
    assert coverage["entries_unhandled"] == len(workspace.entries()) - 3
    proposal = {
        "symbol_id": "expense/store.py#nightly_cleanup",
        "kind": "scheduled",
        "reason": "由外部定时器调用",
        "evidence": [src("expense/store.py", 12, "def nightly_cleanup")],
    }
    plan = MapPlan.model_validate(
        {
            "flows": [{"key": "cleanup", "name": "夜间清理", "entry_ids": ["entry_placeholder"]}],
            "proposed_entries": [proposal],
        }
    )
    with pytest.raises(LoopError) as refused:
        workspace.save_plan(plan)
    # The candidate may be proposed; the flow names an entry that does not exist.
    assert [item["code"] for item in refused.value.errors] == ["unknown_entry"]
    known = {**proposal, "symbol_id": "expense/api.py#submit_report"}
    with pytest.raises(LoopError) as refused:
        workspace.save_plan(MapPlan.model_validate({"proposed_entries": [known]}))
    assert refused.value.errors[0]["code"] == "already_an_entry"
    hidden = {**proposal, "symbol_id": "expense/store.py#missing"}
    with pytest.raises(LoopError) as refused:
        workspace.save_plan(MapPlan.model_validate({"proposed_entries": [hidden]}))
    assert refused.value.errors[0]["code"] == "unknown_symbol"
    # A refused plan leaves the accepted one in place.
    assert workspace.status()["plan"] == "agent"


def test_a_proposed_entry_stays_usable_in_the_plans_that_follow(workspace):
    proposal = {
        "symbol_id": "expense/store.py#load_report",
        "kind": "public_api",
        "reason": "由报表脚本直接调用",
        "evidence": [src("expense/store.py", 8, "def load_report")],
    }
    first = workspace.save_plan(MapPlan.model_validate({"proposed_entries": [proposal]}))
    proposed = entry(workspace, "#load_report")
    assert proposed.detection == "agent_proposed"
    # The plan that proposes an entry answers with its id.
    assert proposed.entry_id in [item["entry_id"] for item in first["entries"]]
    # The next plan uses that id and does not propose the entry again.
    flow = {"key": "load", "name": "查看报销", "entry_ids": [proposed.entry_id]}
    status = workspace.save_plan(MapPlan.model_validate({"flows": [flow]}))
    assert [task["name"] for task in status["tasks"]] == ["查看报销"]
    assert entry(workspace, "#load_report").attributes == {"reason": "由报表脚本直接调用"}
    # So does a plan that sets it aside, and proposing it again replaces the reason.
    skip = {"entry_id": proposed.entry_id, "reason": "out_of_scope"}
    workspace.save_plan(MapPlan.model_validate({"skipped": [skip]}))
    again = {**proposal, "reason": "由对账任务调用"}
    workspace.save_plan(MapPlan.model_validate({"flows": [flow], "proposed_entries": [again]}))
    assert entry(workspace, "#load_report").attributes == {"reason": "由对账任务调用"}
    # A plan that no longer mentions the entry withdraws it.
    planned(workspace)
    assert proposed.entry_id not in workspace.entries()
    with pytest.raises(LoopError) as refused:
        workspace.save_plan(MapPlan.model_validate({"flows": [flow]}))
    assert [item["code"] for item in refused.value.errors] == ["unknown_entry"]


def test_context_lists_what_the_flow_has_to_account_for(workspace):
    tasks = planned(workspace)
    context = workspace.context(tasks["提交报销"], claim=True)
    assert context["entries"][0]["attributes"] == {"method": "POST", "path": "/reports"}
    # A definition is shown from its first decorator.
    assert context["source"][0]["text"].startswith(
        '@router.post("/reports")\nasync def submit_report'
    )
    units = [
        (item["unit"], item["kind"], item["text"].split("(")[0]) for item in context["accountable"]
    ]
    # The entry's own conditions and results, then each function it calls, once.
    assert units == [
        ("fact", "condition", "amount >= THRESHOLD"),
        ("fact", "return", 'return {"status": "pending_approval", "review": verdict}'),
        ("fact", "return", 'return {"status": "approved"}'),
        ("function", "call", "review_with_model"),
        ("function", "call", "save_status"),
    ]
    assert context["accountable"][0]["branches"] == ["true", "false"]
    review, save = context["accountable"][3:]
    assert review["function"] == ["expense/review.py#review_with_model"]
    # How much one step would hide, and what the function reaches outside the code.
    assert review["inside"] == {"conditions": 1, "loops": 1, "results": 1, "reaches": ["openai"]}
    assert save["calls"] == 2 and save["inside"]["reaches"] == []
    assert context["callees"] == [
        "expense/review.py#review_with_model",
        "expense/store.py#save_status",
    ]
    assert workspace.status()["tasks"][0]["state"] == "claimed"
    with pytest.raises(LoopError, match="holds this task"):
        workspace.context(tasks["提交报销"], claim=True)


def test_observation_category_survives_submission_without_changing_severity(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    submission = submit_flow(workspace, task)
    submission["observations"][0]["category"] = "reliability"
    result = workspace.submit(task, submission)
    assert result["status"] == "accepted"
    finding = workspace.stored_map().findings[0]
    assert finding.category == "reliability"
    assert finding.severity == "medium"


def test_step_contract_survives_submission_and_viewer_payload(workspace):
    from genesis_ci.business_map.view import view_payload

    task = planned(workspace)["提交报销"]
    submission = submit_flow(workspace, task)
    contract = {
        "input": {"type": "object", "properties": {"amount": {"type": "number"}}},
        "output": {"type": "boolean", "description": "amount >= THRESHOLD"},
    }
    submission["steps"][1]["contract"] = contract
    submission["steps"][1]["evidence"] += [
        src(API, 7, "THRESHOLD = 100"),
        src(API, 12, 'amount = report["amount"]'),
    ]
    accepted = workspace.submit(task, submission)
    assert accepted["status"] == "accepted"
    payload = view_payload(workspace.stored_map())
    step = next(
        step
        for flow in payload["map"]["flows"]
        for step in flow["steps"]
        if step["step_id"] == accepted["steps"]["choose"]
    )
    assert step["contract"] == contract
    assert len(step["evidence_ids"]) == 3


def test_unknown_step_cannot_supply_a_contract_without_evidence(workspace):
    task = planned(workspace)["提交报销"]
    submission = submit_flow(workspace, task)
    submission["steps"].append(
        {
            "key": "unknown_contract",
            "name": "外部服务",
            "kind": "external",
            "resolution": "unknown",
            "reason": "没有源码。",
            "contract": {"input": "报销单", "output": "批准结果"},
        }
    )
    result = workspace.submit(task, submission)
    assert result["status"] == "rejected"
    assert ("steps[7].evidence", "evidence_required") in codes(result)


def test_accepted_flows_assemble_into_a_complete_map(workspace):
    tasks = planned(workspace)
    first = workspace.submit(tasks["提交报销"], submit_flow(workspace, tasks["提交报销"]))
    assert (first["status"], first["analysis_status"]) == ("accepted", "partial")
    assert first["accounting"] == {
        "accountable": 8,
        "covered": 8,
        "omitted": 0,
        "unaccounted": 0,
        "truncated": False,
    }
    again = workspace.submit(tasks["提交报销"], submit_flow(workspace, tasks["提交报销"]))
    assert again["steps"] == first["steps"] and len(set(first["steps"].values())) == 7
    second = workspace.submit(tasks["经理审批"], approve_flow(workspace, tasks["经理审批"]))
    assert second["analysis_status"] == "complete"
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    assert stored.analysis_status == "complete"
    assert [(domain.name, domain.support) for domain in stored.domains] == [
        ("报销", "agent_synthesis")
    ]
    submit = next(flow for flow in stored.flows if flow.name == "提交报销")
    assert submit.stage == "synthesized" and submit.flow_id == first["flow_id"]
    branch = next(
        edge for edge in submit.edges if edge.condition and edge.condition.branch == "true"
    )
    assert (branch.support, branch.condition.label) == ("static_fact", "达到阈值")
    review = next(step for step in submit.steps if step.name == "模型审核")
    assert len(review.anchors) >= 3 and len(review.finding_ids) == 1
    assert stored.findings[0].source == "agent_observation"
    status = workspace.status()
    assert status["next_task"] is None and status["coverage"]["tasks_validated"] == 2


def test_one_bad_citation_is_reported_once_and_keeps_the_accepted_version(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    good = submit_flow(workspace, task)
    bad = copy.deepcopy(good)
    bad["steps"][1]["evidence"] = [src(API, 13, "amount > THRESHOLD")]
    refused = workspace.submit(task, bad)
    assert refused["status"] == "rejected"
    assert codes(refused) == [("steps[1].evidence[0]", "quote_not_found")]
    assert workspace.status()["tasks"][0]["state"] == "failed"
    assert workspace.submit(task, good)["status"] == "accepted"
    assert workspace.submit(task, bad)["status"] == "rejected"
    assert workspace.status()["tasks"][0]["state"] == "validated"


def test_submissions_cannot_claim_more_than_the_facts_support(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    base = submit_flow(workspace, task)

    def refused(mutate):
        changed = copy.deepcopy(base)
        mutate(changed)
        result = workspace.submit(task, changed)
        assert result["status"] == "rejected"
        return codes(result)

    assert refused(lambda d: d["steps"][3].update(anchors=["fp_" + "0" * 24])) == [
        ("steps[3].anchors", "unknown_anchor")
    ]
    assert refused(lambda d: d["steps"][3].update(evidence=[src(API, 1, "from fastapi")])) == [
        ("steps[3]", "step_not_anchored")
    ]
    assert refused(lambda d: d["steps"][3].update(evidence=[src("missing.py", 1, "x")])) == [
        ("steps[3].evidence[0]", "file_not_in_snapshot")
    ]
    assert refused(lambda d: d["steps"][3].update(evidence=[src(API, 900, "x")])) == [
        ("steps[3].evidence[0]", "range_out_of_bounds")
    ]
    assert refused(lambda d: d["edges"][1].update(branch="maybe")) == [
        ("edges[1].branch", "unknown_branch")
    ]
    assert refused(
        lambda d: d["edges"][3].update(
            source="pending", target="review", relation="branch", branch="true"
        )
    ) == [("edges[3].branch", "unknown_branch")]
    assert refused(
        lambda d: d.update(omitted=[{"anchor": "fp_" + "0" * 24, "reason": "logging"}])
    ) == [("omitted[0].anchor", "unknown_anchor")]
    assert refused(lambda d: d["steps"][3].update(resolution="candidate")) == [
        ("steps[3].reason", "reason_required")
    ]
    assert refused(lambda d: d["steps"].append(d["steps"][0])) == [
        ("steps[7].key", "invalid_duplicate")
    ]
    assert refused(lambda d: d["edges"][4].update(target="archive")) == [
        ("edges[4].target", "invalid_reference")
    ]


def test_unsupported_relations_must_be_submitted_as_candidates(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    data = submit_flow(workspace, task)
    data["steps"].append(
        {
            "key": "cleanup",
            "name": "夜间清理",
            "kind": "action",
            "evidence": [src("expense/store.py", 13, "REPORTS.clear()")],
            "resolution": "candidate",
            "reason": "没有找到调用它的代码。",
        }
    )
    data["edges"].append({"source": "ret_ok", "target": "cleanup", "relation": "sequence"})
    refused = workspace.submit(task, data)
    assert codes(refused) == [("edges[6]", "edge_not_supported")]
    data["edges"][-1].update(resolution="candidate", reason="时间上可能在之后，代码没有体现。")
    accepted = workspace.submit(task, data)
    assert accepted["status"] == "accepted"
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    flow = next(item for item in stored.flows if item.name == "提交报销")
    assert (flow.edges[-1].support, flow.edges[-1].resolution) == ("agent_synthesis", "candidate")


def test_facts_left_out_are_listed_until_used_or_omitted_with_a_reason(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    data = submit_flow(workspace, task)
    # One step for the whole review: nothing inside it has to be accounted for.
    data["steps"][2]["evidence"] = [src(API, 14, "review_with_model(report)")]
    data["observations"] = []
    folded = workspace.submit(task, data)
    assert folded["status"] == "accepted" and folded["accounting"]["accountable"] == 5
    assert folded["accounting"]["unaccounted"] == 0
    # A step anchored inside the review expands it: the rest of it is now accountable.
    data["steps"][2]["evidence"].append(src(REVIEW, 7, "while True"))
    partial = workspace.submit(task, data)
    assert partial["status"] == "accepted" and partial["accounting"]["unaccounted"] == 2
    left = [item["fingerprint"] for item in partial["unaccounted"]]
    assert [(item["unit"], item["kind"]) for item in partial["unaccounted"]] == [
        ("await", "call"),
        ("fact", "condition"),
    ]
    workspace.submit(tasks["经理审批"], approve_flow(workspace, tasks["经理审批"]))
    assert workspace.status()["analysis_status"] == "partial"
    data["omitted"] = [
        {"anchor": fp, "reason": "merged_into_step", "note": "模型审核的内部细节"} for fp in left
    ]
    complete = workspace.submit(task, data)
    assert complete["accounting"] == {
        "accountable": 8,
        "covered": 6,
        "omitted": 2,
        "unaccounted": 0,
        "truncated": False,
    }
    assert complete["analysis_status"] == "complete"
    used = copy.deepcopy(data)
    used["steps"][2]["anchors"] = [left[0]]
    assert codes(workspace.submit(task, used)) == [("omitted[0].anchor", "omitted_but_used")]


def test_queries_read_only_the_frozen_snapshot(workspace):
    symbol = workspace.query_symbol("expense/review.py#review_with_model")
    assert symbol["callers"] == ["expense/api.py#submit_report"]
    assert symbol["source"]["text"].startswith("async def review_with_model")
    with pytest.raises(LoopError) as missing:
        workspace.query_symbol("expense/api.py#review_with_model")
    assert "expense/review.py#review_with_model" in missing.value.errors[0]["message"]
    write(workspace.repo, API, FILES[API].replace("pending_approval", "waiting"))
    found = workspace.search("pending_approval")
    assert [(item["path"], item["line"]) for item in found["matches"]] == [
        (API, 15),
        (API, 16),
        (API, 24),
    ]
    text = workspace.read(found["matches"][0]["evidence_id"])
    assert "pending_approval" in text["text"] and text["path"] == API
    # Evidence registered by a search can be cited by id from another process.
    reopened = Workspace(workspace.repo, workspace.session["session_id"])
    assert reopened.read(found["matches"][0]["evidence_id"]) == text
    with pytest.raises(LoopError, match="No evidence"):
        workspace.read("ev_missing")
    with pytest.raises(LoopError):
        workspace.search("  ")


def test_cli_reports_refusals_as_json_with_exit_code_one(workspace, tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_NO_BROWSER", "1")
    runner = CliRunner()
    common = ["--repo", str(workspace.repo), "--session", workspace.session["session_id"]]
    planned = runner.invoke(app, ["map", "plan", *common])
    task = json.loads(planned.stdout)["next_task"]
    assert planned.exit_code == 0
    context = runner.invoke(app, ["map", "context", *common, "--task", task])
    assert context.exit_code == 0 and json.loads(context.stdout)["task_id"] == task
    bad = tmp_path / "submission.json"
    bad.write_text(json.dumps({"name": "x", "steps": []}))
    refused = runner.invoke(app, ["map", "submit", *common, "--task", task, "--input", str(bad)])
    assert refused.exit_code == 1 and json.loads(refused.stdout)["status"] == "rejected"
    unknown = runner.invoke(app, ["map", "context", *common, "--task", "task_none"])
    assert unknown.exit_code == 1 and json.loads(unknown.stdout)["error"]["code"] == "unknown_task"
    both = runner.invoke(app, ["map", "query", *common])
    assert both.exit_code != 0
    assert runner.invoke(app, ["map", "status", *common]).exit_code == 0
    assert runner.invoke(app, ["map", "render", *common]).exit_code == 2


def test_edges_must_follow_the_control_structure(workspace):
    tasks = planned(workspace)
    task = tasks["提交报销"]
    base = submit_flow(workspace, task)

    def refused(*edge):
        changed = copy.deepcopy(base)
        fields = dict(zip(("source", "target", "relation", "branch"), edge))
        changed["edges"].append(fields)
        result = workspace.submit(task, changed)
        assert result["status"] == "rejected", edge
        return codes(result)

    last = "edges[6]"
    # A result ends its path: nothing follows a return, not even the other branch.
    assert refused("ret_ok", "review", "sequence") == [(last, "edge_not_supported")]
    assert refused("ret_ok", "recv", "sequence") == [(last, "edge_not_supported")]
    assert refused("ret_pending", "auto", "sequence") == [(last, "edge_not_supported")]
    # The two sides of a condition do not flow into each other, and order matters.
    assert refused("pending", "auto", "sequence") == [(last, "edge_not_supported")]
    assert refused("pending", "choose", "sequence") == [(last, "edge_not_supported")]
    # A branch has to lead where the edge points.
    assert refused("choose", "auto", "branch", "true") == [(last, "branch_target_not_reachable")]
    assert refused("choose", "ret_pending", "branch", "false") == [
        (last, "branch_target_not_reachable")
    ]
    approve = tasks["经理审批"]
    flow = approve_flow(workspace, approve)
    flow["edges"].append({"source": "reject", "target": "done", "relation": "sequence"})
    assert codes(workspace.submit(approve, flow)) == [("edges[3]", "edge_not_supported")]
    # Skipping over steps along a real path is fine.
    skipping = copy.deepcopy(base)
    skipping["edges"].append({"source": "recv", "target": "ret_ok", "relation": "sequence"})
    skipping["edges"].append(
        {"source": "choose", "target": "pending", "relation": "branch", "branch": "true"}
    )
    assert workspace.submit(task, skipping)["status"] == "accepted"


def test_preparing_unchanged_code_again_keeps_accepted_work(workspace):
    tasks = planned(workspace)
    workspace.submit(tasks["提交报销"], submit_flow(workspace, tasks["提交报销"]))
    workspace.submit(tasks["经理审批"], approve_flow(workspace, tasks["经理审批"]))
    again = prepare(workspace.repo, head="HEAD")
    assert again["session_id"] == workspace.session["session_id"]
    assert (again["resumed"], again["analysis_status"]) == (True, "complete")
    status = Workspace(workspace.repo, again["session_id"]).status()
    assert status["coverage"]["tasks_validated"] == 2 and status["next_task"] is None


def test_status_orders_the_work_and_counts_refusals(workspace):
    before = workspace.status()
    assert (before["plan"], before["analysis_status"]) == (None, "partial")
    assert (
        before["coverage"]["entries_total"]
        == len(before["entries"]) + before["root_candidates_total"]
    )
    tasks = planned(workspace)
    first, second = tasks["提交报销"], tasks["经理审批"]
    assert workspace.status()["next_task"] == first
    bad = submit_flow(workspace, first)
    bad["steps"][1]["evidence"] = [src(API, 13, "not there")]
    for expected in (1, 2):
        refused = workspace.submit(first, bad)
        assert (refused["rejections"], refused["accepted_version_kept"]) == (expected, False)
    status = workspace.status()
    # A refused task does not hide the untouched one.
    assert status["next_task"] == second
    assert [(item["state"], item["rejections"]) for item in status["tasks"]] == [
        ("failed", 2),
        ("pending", 0),
    ]
    workspace.submit(second, approve_flow(workspace, second))
    assert workspace.status()["next_task"] == first
    partial = submit_flow(workspace, first)
    # Expands the review function with a single anchor and leaves the rest of it open.
    partial["steps"][2]["evidence"] = [
        src(API, 14, "review_with_model(report)"),
        src(REVIEW, 7, "while True"),
    ]
    partial["observations"] = []
    workspace.submit(first, partial)
    status = workspace.status()
    # Accepted, but something is still unaccounted: the task stays the next thing to do.
    assert status["tasks"][0]["state"] == "validated" and status["next_task"] == first
    assert workspace.submit(first, bad)["accepted_version_kept"] is True
    workspace.submit(first, submit_flow(workspace, first))
    assert workspace.status()["next_task"] is None


def test_map_and_summary_record_what_is_skipped_and_uncertain(workspace):
    from genesis_ci.business_map.render import render_html, render_summary

    tasks = planned(workspace)
    data = submit_flow(workspace, tasks["提交报销"])
    data["steps"].append(
        {
            "key": "notify",
            "name": "通知报销人",
            "kind": "external",
            "resolution": "unknown",
            "reason": "没有找到发送通知的代码。",
        }
    )
    data["edges"].append(
        {
            "source": "pending",
            "target": "notify",
            "relation": "call",
            "resolution": "unknown",
            "reason": "没有静态调用关系。",
        }
    )
    workspace.submit(tasks["提交报销"], data)
    workspace.submit(tasks["经理审批"], approve_flow(workspace, tasks["经理审批"]))
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    # Uncertain items do not make the map partial; they are listed instead.
    assert stored.analysis_status == "complete"
    skipped = stored.coverage.skipped_entries
    assert [(item.symbol_id, item.reason) for item in skipped] == [
        ("expense/api.py#healthz", "infrastructure")
    ]
    summary = render_summary(stored)
    assert (
        "## Uncertain" in summary and "通知报销人 (unknown) - 没有找到发送通知的代码。" in summary
    )
    assert "标记为待审批 -> 通知报销人 (unknown)" in summary
    assert "## Skipped entries" in summary and "expense/api.py#healthz: infrastructure" in summary
    assert "## Risk findings" in summary and "medium (agent observation)" in summary
    assert "Skipped entries" in render_html(stored)


def test_bundled_skill_examples_are_accepted_and_leave_nothing_unaccounted(workspace):
    import re
    from importlib.resources import files

    text = files("genesis_ci").joinpath("assets/skills/genesis/SKILL.md").read_text()
    plan, flow, _ = (json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.S))
    status = workspace.save_plan(MapPlan.model_validate(plan))
    assert status["status"] == "accepted" and status["tasks"][0]["flow_key"] == "submit"
    result = workspace.submit(status["next_task"], flow)
    assert result["status"] == "accepted", result
    assert result["accounting"]["unaccounted"] == 0 and result["accounting"]["omitted"] == 1
    assert result["analysis_status"] == "complete"


def test_a_label_on_any_edge_is_kept_and_shown(workspace):
    from genesis_ci.business_map.render import render_html

    tasks = planned(workspace)
    data = submit_flow(workspace, tasks["提交报销"])
    data["edges"][3]["label"] = "审核完成"
    assert workspace.submit(tasks["提交报销"], data)["status"] == "accepted"
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    labels = [edge.label for flow in stored.flows for edge in flow.edges if edge.label]
    assert labels == ["审核完成"] and "审核完成" in render_html(stored)


def test_a_step_on_lines_without_any_fact_is_told_so(workspace):
    tasks = planned(workspace)
    data = submit_flow(workspace, tasks["提交报销"])
    data["steps"].append(
        {
            "key": "read",
            "name": "读取金额",
            "kind": "action",
            "evidence": [src(API, 12, "amount =")],
        }
    )
    result = workspace.submit(tasks["提交报销"], data)
    assert codes(result) == [("steps[7]", "step_not_anchored")]
    assert "a plain assignment has none" in result["errors"][0]["message"]


SERVICE_APP = {
    "shop/__init__.py": "",
    "shop/api.py": """from fastapi import APIRouter
from pydantic import Field

from .store import save

router = APIRouter()


class Reply:
    note = Field("", description="shown to the user")

    def __init__(self, data):
        if not data:
            raise ValueError("nothing to reply with")
        self.data = data


@router.post("/orders")
def create_order(order):
    saved = save(
        order,
        mode="create",
    )
    return Reply(saved)
""",
    "shop/store.py": "def save(order, mode):\n    return {**order, 'mode': mode}\n",
}


def test_creating_an_object_accounts_for_its_initializer_not_its_class_body(source_repo):
    for path, text in SERVICE_APP.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    context = workspace.context(task)
    listed = [(item["unit"], item["text"].split("(")[0]) for item in context["accountable"]]
    assert listed == [("fact", "return Reply"), ("function", "save"), ("function", "Reply")]
    # Building a reply runs its initializer. The field declaration in the class body ran
    # when the module was imported and is nowhere on the list.
    reply = context["accountable"][2]
    assert reply["function"] == ["shop/api.py#Reply.__init__"]
    assert reply["inside"] == {"conditions": 1, "loops": 0, "results": 1, "reaches": []}
    assert "shop/api.py#Reply.__init__" in context["callees"]


def test_a_call_written_over_several_lines_is_cited_by_its_first_line(source_repo):
    for path, text in SERVICE_APP.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    context = workspace.context(task)
    flow = {
        "name": "下单",
        "steps": [
            {
                "key": "in",
                "name": "收到订单",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src("shop/api.py", 18, '@router.post("/orders")', 19)],
            },
            {
                "key": "save",
                "name": "保存订单",
                "kind": "action",
                "evidence": [src("shop/api.py", 20, "saved = save(")],
            },
            {
                "key": "out",
                "name": "返回结果",
                "kind": "result",
                "evidence": [
                    src("shop/api.py", 24, "return Reply(saved)"),
                    src("shop/api.py", 13, "not data", 14),
                ],
            },
        ],
        "edges": [
            {"source": "in", "target": "save", "relation": "sequence"},
            {"source": "save", "target": "out", "relation": "sequence"},
        ],
    }
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result
    assert result["accounting"]["unaccounted"] == 0


BIG_APP = {
    "shop/__init__.py": "",
    "shop/api.py": """import stripe
from datetime import datetime
from fastapi import APIRouter

from .rules import check_order, log_order

router = APIRouter()


@router.post("/orders")
def create_order(order):
    log_order(order)
    check_order(order)
    stripe.Charge.create(amount=order["total"])
    stripe.Receipt.create(order=order["id"])
    log_order(order)
    return {"at": datetime.now().isoformat()}
""",
    "shop/rules.py": "def check_order(order):\n"
    + "".join(
        f"    if order.get('f{index}') is None:\n        raise ValueError('f{index} is required')\n"
        for index in range(5)
    )
    + "    return order\n\n\ndef log_order(order):\n    return None\n",
}


def test_called_functions_and_outside_systems_are_accounted_for_once(source_repo):
    from genesis_ci.business_map.render import render_html

    for path, text in BIG_APP.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    context = workspace.context(task)
    listed = [
        (item["unit"], item.get("system") or item["text"].split("(")[0])
        for item in context["accountable"]
    ]
    # Two calls to one function, two to one payment provider: one unit each. Reading the
    # clock is no outside system.
    assert listed == [
        ("fact", 'return {"at": datetime.now'),
        ("function", "log_order"),
        ("function", "check_order"),
        ("system", "stripe"),
    ]
    by_name = {name: item for (_, name), item in zip(listed, context["accountable"], strict=True)}
    assert by_name["log_order"]["calls"] == 2 and by_name["stripe"]["calls"] == 2
    assert by_name["check_order"]["inside"] == {
        "conditions": 5,
        "loops": 0,
        "results": 6,
        "reaches": [],
    }
    assert workspace.query_symbol("shop/rules.py#check_order")["inside"]["conditions"] == 5

    flow = {
        "name": "下单",
        "steps": [
            {
                "key": "in",
                "name": "收到订单",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src("shop/api.py", 10, '@router.post("/orders")', 11)],
            },
            {
                "key": "check",
                "name": "校验订单",
                "kind": "action",
                "evidence": [src("shop/api.py", 13, "check_order(order)")],
            },
            {
                "key": "pay",
                "name": "向支付渠道收款",
                "kind": "external",
                "evidence": [src("shop/api.py", 14, "stripe.Charge.create(")],
            },
            {
                "key": "out",
                "name": "返回下单时间",
                "kind": "result",
                "evidence": [src("shop/api.py", 17, "return")],
            },
        ],
        "edges": [
            {"source": "in", "target": "check", "relation": "sequence"},
            {"source": "check", "target": "pay", "relation": "sequence"},
            {"source": "pay", "target": "out", "relation": "sequence"},
        ],
        "omitted": [{"anchor": by_name["log_order"]["fingerprint"], "reason": "logging"}],
    }
    # One step for a function with eleven conditions and results inside needs a reason.
    refused = workspace.submit(task, flow)
    assert codes(refused) == [("steps[1].unexpanded_reason", "unexpanded_reason_required")]
    assert "5 conditions, 0 loops and 6 results" in refused["errors"][0]["message"]
    flow["steps"][1]["unexpanded_reason"] = "逐项必填校验，对业务链路来说是一步。"
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result
    assert result["accounting"] == {
        "accountable": 4,
        "covered": 3,
        "omitted": 1,
        "unaccounted": 0,
        "truncated": False,
    }
    stored = BusinessMap.model_validate_json((workspace.root / "business-map.json").read_text())
    check = next(step for step in stored.flows[0].steps if step.name == "校验订单")
    assert [
        (item.symbol_id, item.conditions, item.results, item.reason) for item in check.unexpanded
    ] == [("shop/rules.py#check_order", 5, 6, "逐项必填校验，对业务链路来说是一步。")]
    page = render_html(stored)
    assert "not expanded" in page and "5 conditions" in page and "逐项必填校验" in page

    def refused_omission(anchor):
        changed = copy.deepcopy(flow)
        changed["omitted"].append({"anchor": anchor, "reason": "logging"})
        return codes(workspace.submit(task, changed))

    calls = workspace.query_symbol("shop/api.py#create_order")["facts"]
    again = next(
        item["fingerprint"]
        for item in calls
        if item["text"].startswith("log_order")
        and item["fingerprint"] != by_name["log_order"]["fingerprint"]
    )
    assert refused_omission(again) == [("omitted[1].anchor", "already_omitted")]
    inside = workspace.query_symbol("shop/rules.py#check_order")["facts"][0]["fingerprint"]
    # The inside of a function that one step stands for needs no entry. Leaving it out
    # is taken as it is, and the result says that nothing was recorded for it.
    unneeded = copy.deepcopy(flow)
    unneeded["omitted"].append({"anchor": inside, "reason": "logging"})
    taken = workspace.submit(task, unneeded)
    assert taken["status"] == "accepted" and taken["accounting"]["omitted"] == 1
    assert [(item["path"], item["anchor"]) for item in taken["ignored"]] == [("omitted[1]", inside)]
    # Anchoring a step inside it expands it: its conditions and results now count.
    flow["steps"][1]["evidence"].append(src("shop/rules.py", 2, "order.get('f0') is None", 3))
    expanded = workspace.submit(task, flow)
    assert expanded["status"] == "accepted"
    assert (
        expanded["accounting"]["accountable"] == 14 and expanded["accounting"]["unaccounted"] == 8
    )
    assert {item["symbol_id"] for item in expanded["unaccounted"]} == {"shop/rules.py#check_order"}


def outlined(workspace, **approve):
    """A plan that names both flows; `approve` overrides what it says about the second."""
    plan = {
        "domains": [{"key": "expense", "name": "报销"}],
        "flows": [
            {
                "key": "approve",
                "name": "经理审批",
                "summary": "经理批准一张处于待审批状态的报销单。",
                "tier": "supporting",
                "domain": "expense",
                "entry_ids": [entry(workspace, "#approve_report").entry_id],
                **approve,
            },
            {
                "key": "submit",
                "name": "提交报销",
                "domain": "expense",
                "entry_ids": [entry(workspace, "#submit_report").entry_id],
            },
        ],
    }
    return workspace.save_plan(MapPlan.model_validate(plan))


def test_a_planned_flow_carries_its_name_summary_and_tier_until_it_is_described(workspace):
    status = outlined(workspace)
    tasks = {task["flow_key"]: task for task in status["tasks"]}
    assert (tasks["approve"]["name"], tasks["approve"]["tier"]) == ("经理审批", "supporting")
    assert tasks["submit"]["tier"] == "primary"
    flows = {flow.name: flow for flow in workspace.stored_map().flows}
    approve = flows["经理审批"]
    # Named by the plan, with the static structure underneath.
    assert approve.stage == "skeleton" and approve.name_from_plan
    assert approve.summary == "经理批准一张处于待审批状态的报销单。"
    assert approve.tier == "supporting" and approve.support == "static_fact"
    assert flows["提交报销"].name_from_plan and flows["提交报销"].summary is None
    # Once described, the accepted name and summary stand and the tier stays.
    workspace.submit(
        tasks["approve"]["task_id"], approve_flow(workspace, tasks["approve"]["task_id"])
    )
    accepted = next(
        flow for flow in workspace.stored_map().flows if flow.flow_id == approve.flow_id
    )
    assert accepted.stage == "synthesized" and not accepted.name_from_plan
    assert accepted.tier == "supporting"


def test_the_business_processes_are_offered_before_the_supporting_flows(workspace):
    status = outlined(workspace)
    tasks = {task["flow_key"]: task["task_id"] for task in status["tasks"]}
    # The supporting flow is listed first in the plan and still waits its turn.
    assert status["next_task"] == tasks["submit"]
    workspace.submit(tasks["submit"], submit_flow(workspace, tasks["submit"]))
    assert workspace.status()["next_task"] == tasks["approve"]


def test_an_agent_plan_must_name_its_flows_and_the_default_plan_keeps_source_labels(workspace):
    unnamed = {
        "flows": [{"key": "submit", "entry_ids": [entry(workspace, "#submit_report").entry_id]}]
    }
    with pytest.raises(LoopError) as refused:
        workspace.save_plan(MapPlan.model_validate(unnamed))
    assert [item["code"] for item in refused.value.errors] == ["name_required"]
    workspace.save_plan(None)
    flows = workspace.stored_map().flows
    assert not any(flow.name_from_plan for flow in flows)
    assert any(flow.name == "POST /reports · submit_report" for flow in flows)


def test_the_summary_lists_the_outline_with_supporting_flows_last(workspace):
    from genesis_ci.business_map.render import render_html, render_summary

    outlined(workspace)
    summary = render_summary(workspace.stored_map())
    first = summary.index("- 提交报销 (not described yet)")
    second = summary.index(
        "- 经理审批: 经理批准一张处于待审批状态的报销单。 (not described yet, supporting)"
    )
    assert first < second
    page = render_html(workspace.stored_map())
    assert "not described yet" in page and "supporting" in page


def test_a_problem_found_before_any_check_of_the_code_is_named_too(workspace):
    tasks = planned(workspace)
    flow = submit_flow(workspace, tasks["提交报销"])
    flow["steps"][2]["anchors"] = ["not a fingerprint"]
    flow["edges"][3]["relation"] = "branch"
    refused = workspace.submit(tasks["提交报销"], flow)
    assert [(item["path"], item["code"], item.get("item")) for item in refused["errors"]] == [
        ("steps[2].anchors[0]", "invalid_string_pattern_mismatch", "step review"),
        ("edges[3]", "invalid_value_error", "edge review -> pending"),
    ]

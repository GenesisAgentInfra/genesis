"""Generate synthetic business-map samples; never execute fixture source code.

The samples describe one small expense application. Three map-only samples show it
fully synthesized, as a static skeleton, and partially synthesized. A change sample
adds a base snapshot, a change report and an evidence bundle. They are contract
examples written by hand, not output of an analyzer or a model.
"""

import hashlib
import json
from pathlib import Path

from genesis_ci.snapshot import slice_source
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport, validate_change_report_against_map
from genesis_contracts.evidence_bundle import EvidenceBundle, validate_evidence_bundle
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.models import (
    EvidenceRef,
    EvidenceSide,
    FileIdentity,
    ReferenceRange,
    SnapshotManifest,
    evidence_id_for,
    snapshot_id_for,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "business-map"
HEAD = EvidenceSide.head
BASE = EvidenceSide.base
API = "src/expense/api.py"
TESTS = "tests/test_submit.py"
REVIEW = "src/expense/review.py"
SUBMIT = API + "#submit_report"
APPROVE = API + "#approve_report"
MODEL = REVIEW + "#review_with_model"

SOURCES = {
    API: """from fastapi import APIRouter

from .review import review_with_model
from .store import load_report, save_status

router = APIRouter()
THRESHOLD = 100


@router.post("/reports")
async def submit_report(report):
    amount = report["amount"]
    logger.info("report received")
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
""",
    REVIEW: """from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    while True:
        response = await client.responses.create(model="gpt-5", input=str(report))
        if response.output_text:
            return response.output_text
""",
    "src/expense/store.py": """REPORTS = {}


def save_status(report_id, status):
    REPORTS.setdefault(report_id, {})["status"] = status


def load_report(report_id):
    return REPORTS[report_id]
""",
}


def digest(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fp(symbol, kind, text, ordinal=0):
    return fact_fingerprint(symbol=symbol, kind=kind, text=text, ordinal=ordinal)


class Evidence:
    """Register evidence by quoting a source line, so the samples survive edits here."""

    def __init__(self, snapshot_id, sources=None, side=HEAD):
        self.snapshot_id = snapshot_id
        self.sources = SOURCES if sources is None else sources
        self.side = side
        self.refs = {}

    def cite(self, path, quote, lines=1, kind="code"):
        text = self.sources[path]
        matches = [i for i, line in enumerate(text.split("\n"), 1) if quote in line]
        if len(matches) != 1:
            raise SystemExit(f"quote must match exactly one line in {path}: {quote!r}")
        span = ReferenceRange(start_line=matches[0], end_line=matches[0] + lines - 1)
        snippet = digest(slice_source(text, span))
        ref = EvidenceRef(
            evidence_id=evidence_id_for(
                snapshot_id=self.snapshot_id,
                side=self.side,
                path=path,
                range=span,
                digest=snippet,
            ),
            snapshot_id=self.snapshot_id,
            side=self.side,
            path=path,
            range=span,
            snippet_digest=snippet,
            kind=kind,
        )
        self.refs[ref.evidence_id] = ref
        return ref.evidence_id

    def catalog(self):
        return [self.refs[key].model_dump(mode="json") for key in sorted(self.refs)]


def step(step_id, name, kind, anchors, evidence, *, static=False, findings=()):
    return {
        "step_id": step_id,
        "name": name,
        "kind": kind,
        "support": "static_fact" if static else "agent_synthesis",
        "resolution": "resolved",
        "anchors": list(anchors),
        "evidence_ids": list(evidence),
        "finding_ids": list(findings),
    }


def edge(source, target, relation, anchors, evidence, *, condition=None):
    item = {
        "source": source,
        "target": target,
        "relation": relation,
        "support": "static_fact",
        "resolution": "resolved",
        "anchors": list(anchors),
        "evidence_ids": list(evidence),
    }
    if condition:
        item["condition"] = condition
    return item


def facts(ev, threshold="amount >= THRESHOLD"):
    """Anchors and evidence for the facts the samples refer to."""
    spec = {
        "submit_entry": (SUBMIT, "entry", "POST /reports", API, '@router.post("/reports")', 2),
        "submit_log": (SUBMIT, "call", 'logger.info("report received")', API, "logger.info", 1),
        "threshold": (SUBMIT, "condition", threshold, API, threshold, 1),
        "review_call": (
            SUBMIT,
            "call",
            "review_with_model(report)",
            API,
            "await review_with_model",
            1,
        ),
        "save_pending": (
            SUBMIT,
            "call",
            'save_status(report["id"], "pending_approval")',
            API,
            '"pending_approval")',
            1,
        ),
        "return_pending": (
            SUBMIT,
            "return",
            '{"status": "pending_approval", "review": verdict}',
            API,
            '"review": verdict',
            1,
        ),
        "save_approved": (
            SUBMIT,
            "call",
            'save_status(report["id"], "approved")',
            API,
            'save_status(report["id"], "approved")',
            1,
        ),
        "return_approved": (
            SUBMIT,
            "return",
            '{"status": "approved"}',
            API,
            'return {"status": "approved"}',
            1,
        ),
        "approve_entry": (
            APPROVE,
            "entry",
            "POST /reports/{report_id}/approve",
            API,
            "/approve",
            2,
        ),
        "load_report": (
            APPROVE,
            "call",
            "load_report(report_id)",
            API,
            "load_report(report_id)",
            1,
        ),
        "pending_check": (
            APPROVE,
            "condition",
            'report["status"] != "pending_approval"',
            API,
            'report["status"] !=',
            1,
        ),
        "reject": (
            APPROVE,
            "raise",
            'ValueError("report is not waiting for approval")',
            API,
            "raise ValueError",
            1,
        ),
        "approve_save": (
            APPROVE,
            "call",
            'save_status(report_id, "approved")',
            API,
            'save_status(report_id, "approved")',
            1,
        ),
        "approve_return": (
            APPROVE,
            "return",
            '{"status": "approved", "id": report_id}',
            API,
            '"id": report_id',
            1,
        ),
        "model_loop": (MODEL, "loop", "while True", REVIEW, "while True", 4),
    }
    return {
        key: (fp(symbol, kind, text), ev.cite(path, quote, lines))
        for key, (symbol, kind, text, path, quote, lines) in spec.items()
    }


def entry(entry_id, symbol, route, evidence):
    return {
        "entry_id": entry_id,
        "symbol_id": symbol,
        "kind": "http_route",
        "detection": "adapter",
        "framework": "fastapi",
        "attributes": {"method": "POST", "path": route},
        "evidence_ids": [evidence],
    }


def loop_finding(f):
    anchor, ref = f["model_loop"]
    return {
        "finding_id": "find_loop_no_count_bound",
        "source": "rule",
        "rule": "loop_no_count_bound",
        "severity": "medium",
        "statement": "模型调用位于没有静态次数上限的循环中。",
        "anchors": [anchor],
        "evidence_ids": [ref],
        "condition": "只识别静态可见的循环与调用；运行时的提前退出不在判断范围内。",
    }


def submit_edges(f):
    a = {key: value[0] for key, value in f.items()}
    e = {key: value[1] for key, value in f.items()}
    cond = {"label": "达到阈值", "branch": "true", "anchor": a["threshold"]}
    other = {"label": "低于阈值", "branch": "false", "anchor": a["threshold"]}
    return [
        edge(
            "step_submit_received",
            "step_choose_path",
            "sequence",
            [a["submit_entry"], a["threshold"]],
            [e["threshold"]],
        ),
        edge(
            "step_choose_path", "step_model_review", "branch", [], [e["threshold"]], condition=cond
        ),
        edge(
            "step_choose_path", "step_auto_approve", "branch", [], [e["threshold"]], condition=other
        ),
        edge(
            "step_model_review",
            "step_mark_pending",
            "sequence",
            [a["review_call"], a["save_pending"]],
            [e["save_pending"]],
        ),
        edge(
            "step_mark_pending",
            "step_return_pending",
            "sequence",
            [a["save_pending"], a["return_pending"]],
            [e["return_pending"]],
        ),
        edge(
            "step_auto_approve",
            "step_return_approved",
            "sequence",
            [a["save_approved"], a["return_approved"]],
            [e["return_approved"]],
        ),
    ]


def submit_flow(f, *, static, account_log):
    """`static` renders the skeleton; `account_log` says how the logging call is treated."""
    a = {key: value[0] for key, value in f.items()}
    e = {key: value[1] for key, value in f.items()}
    names = (
        {
            "received": "POST /reports",
            "choose": "amount >= THRESHOLD",
            "review": "review_with_model(report)",
            "pending": 'save_status(report["id"], "pending_approval")',
            "return_pending": 'return {"status": "pending_approval", ...}',
            "auto": 'save_status(report["id"], "approved")',
            "return_approved": 'return {"status": "approved"}',
        }
        if static
        else {
            "received": "收到报销提交",
            "choose": "根据金额选择处理路径",
            "review": "模型审核",
            "pending": "标记为待审批",
            "return_pending": "返回待审批结果",
            "auto": "自动批准",
            "return_approved": "返回已批准结果",
        }
    )
    review_findings = (
        ["find_loop_no_count_bound"]
        if static
        else [
            "find_loop_no_count_bound",
            "find_review_failure_unhandled",
        ]
    )
    steps = [
        step(
            "step_submit_received",
            names["received"],
            "trigger",
            [a["submit_entry"]],
            [e["submit_entry"]],
            static=static,
        ),
        step(
            "step_choose_path",
            names["choose"],
            "decision",
            [a["threshold"]],
            [e["threshold"]],
            static=static,
        ),
        step(
            "step_model_review",
            names["review"],
            "external",
            [a["review_call"], a["model_loop"]],
            [e["review_call"], e["model_loop"]],
            static=static,
            findings=review_findings,
        ),
        step(
            "step_mark_pending",
            names["pending"],
            "action",
            [a["save_pending"]],
            [e["save_pending"]],
            static=static,
        ),
        step(
            "step_return_pending",
            names["return_pending"],
            "result",
            [a["return_pending"]],
            [e["return_pending"]],
            static=static,
        ),
        step(
            "step_auto_approve",
            names["auto"],
            "action",
            [a["save_approved"]],
            [e["save_approved"]],
            static=static,
        ),
        step(
            "step_return_approved",
            names["return_approved"],
            "result",
            [a["return_approved"]],
            [e["return_approved"]],
            static=static,
        ),
    ]
    edges = submit_edges(f)
    accounting = {"accountable": 8, "covered": 7, "omitted": 0, "unaccounted": 0}
    omitted, unaccounted = [], []
    if account_log == "shown":
        steps.insert(
            1,
            step(
                "step_submit_log",
                'logger.info("report received")',
                "action",
                [a["submit_log"]],
                [e["submit_log"]],
                static=True,
            ),
        )
        accounting["covered"] = 8
    elif account_log == "omitted":
        omitted = [{"anchor": a["submit_log"], "reason": "logging"}]
        accounting["omitted"] = 1
    else:
        unaccounted = [a["submit_log"]]
        accounting["unaccounted"] = 1
    return {
        "flow_id": "flow_submit_report",
        "name": "POST /reports · submit_report" if static else "提交报销",
        **(
            {}
            if static
            else {
                "summary": "员工提交报销单；金额达到阈值时先由模型审核，再等待经理审批，否则自动批准。"
            }
        ),
        "stage": "skeleton" if static else "synthesized",
        "support": "static_fact" if static else "agent_synthesis",
        "entries": [entry("entry_submit_report", SUBMIT, "/reports", e["submit_entry"])],
        "steps": steps,
        "edges": edges,
        "accounting": accounting,
        "omitted": omitted,
        "unaccounted": unaccounted,
    }


def approve_flow(f, *, static):
    a = {key: value[0] for key, value in f.items()}
    e = {key: value[1] for key, value in f.items()}
    names = (
        {
            "received": "POST /reports/{report_id}/approve",
            "load": "load_report(report_id)",
            "check": 'report["status"] != "pending_approval"',
            "reject": 'raise ValueError("report is not waiting for approval")',
            "save": 'save_status(report_id, "approved")',
            "done": 'return {"status": "approved", ...}',
        }
        if static
        else {
            "received": "经理发起审批",
            "load": "读取报销单",
            "check": "检查是否处于待审批状态",
            "reject": "拒绝：报销单不在待审批状态",
            "save": "标记为已批准",
            "done": "返回已批准结果",
        }
    )
    rejected = {"label": "不在待审批状态", "branch": "true", "anchor": a["pending_check"]}
    waiting = {"label": "处于待审批状态", "branch": "false", "anchor": a["pending_check"]}
    return {
        "flow_id": "flow_approve_report",
        "name": "POST /reports/{report_id}/approve · approve_report" if static else "经理审批",
        **({} if static else {"summary": "经理批准一张处于待审批状态的报销单。"}),
        "stage": "skeleton" if static else "synthesized",
        "support": "static_fact" if static else "agent_synthesis",
        "entries": [
            entry(
                "entry_approve_report", APPROVE, "/reports/{report_id}/approve", e["approve_entry"]
            )
        ],
        "steps": [
            step(
                "step_approve_received",
                names["received"],
                "trigger",
                [a["approve_entry"]],
                [e["approve_entry"]],
                static=static,
            ),
            step(
                "step_load_report",
                names["load"],
                "action",
                [a["load_report"]],
                [e["load_report"]],
                static=static,
            ),
            step(
                "step_check_pending",
                names["check"],
                "decision",
                [a["pending_check"]],
                [e["pending_check"]],
                static=static,
            ),
            step(
                "step_reject",
                names["reject"],
                "result",
                [a["reject"]],
                [e["reject"]],
                static=static,
            ),
            step(
                "step_mark_approved",
                names["save"],
                "action",
                [a["approve_save"]],
                [e["approve_save"]],
                static=static,
            ),
            step(
                "step_approve_done",
                names["done"],
                "result",
                [a["approve_return"]],
                [e["approve_return"]],
                static=static,
            ),
        ],
        "edges": [
            edge(
                "step_approve_received",
                "step_load_report",
                "sequence",
                [a["approve_entry"], a["load_report"]],
                [e["load_report"]],
            ),
            edge(
                "step_load_report",
                "step_check_pending",
                "sequence",
                [a["load_report"], a["pending_check"]],
                [e["pending_check"]],
            ),
            edge(
                "step_check_pending",
                "step_reject",
                "branch",
                [],
                [e["pending_check"]],
                condition=rejected,
            ),
            edge(
                "step_check_pending",
                "step_mark_approved",
                "branch",
                [],
                [e["pending_check"]],
                condition=waiting,
            ),
            edge(
                "step_mark_approved",
                "step_approve_done",
                "sequence",
                [a["approve_save"], a["approve_return"]],
                [e["approve_return"]],
            ),
        ],
        "accounting": {"accountable": 5, "covered": 5, "omitted": 0, "unaccounted": 0},
    }


def document(snapshot_id, ev, **fields):
    data = {
        "schema_version": "0.1.0",
        "snapshot_id": snapshot_id,
        "side": "head",
        **fields,
        "evidence": ev.catalog(),
    }
    return BusinessMap.model_validate(data).model_dump(mode="json", exclude_none=True)


def complete(snapshot_id, sources=None, threshold="amount >= THRESHOLD"):
    ev = Evidence(snapshot_id, sources)
    f = facts(ev, threshold)
    observation = {
        "finding_id": "find_review_failure_unhandled",
        "source": "agent_observation",
        "severity": "low",
        "statement": "模型审核调用失败时没有处理，异常会直接中断提交。",
        "evidence_ids": [f["review_call"][1]],
        "gap": "只读取了这一处调用；上层框架是否统一处理异常不在已读取范围内。",
    }
    link = {
        "link_id": "link_submit_to_approve",
        "source": {"flow_id": "flow_submit_report", "step_id": "step_mark_pending"},
        "target": {"flow_id": "flow_approve_report", "step_id": "step_check_pending"},
        "relation": "state_handoff",
        "name": "写入“待审批”状态",
        "support": "agent_synthesis",
        "resolution": "candidate",
        "reason": "两条流程通过同一个状态值衔接，静态分析无法确认运行时的先后。",
        "source_evidence_ids": [f["save_pending"][1]],
        "target_evidence_ids": [f["pending_check"][1]],
    }
    return document(
        snapshot_id,
        ev,
        analysis_status="complete",
        domains=[
            {
                "domain_id": "domain_expense",
                "name": "报销",
                "support": "agent_synthesis",
                "flow_ids": ["flow_submit_report", "flow_approve_report"],
            }
        ],
        flows=[submit_flow(f, static=False, account_log="omitted"), approve_flow(f, static=False)],
        links=[link],
        findings=[loop_finding(f), observation],
        coverage={
            "scope": "规划中的 2 条流程，覆盖全部 2 个框架入口。",
            "entries_total": 2,
            "entries_planned": 2,
            "entries_skipped": 0,
            "entries_unhandled": 0,
            "tasks_total": 3,
            "tasks_validated": 3,
            "tasks_pending": 0,
        },
    )


def skeleton(snapshot_id):
    ev = Evidence(snapshot_id)
    f = facts(ev)
    return document(
        snapshot_id,
        ev,
        analysis_status="partial",
        domains=[
            {
                "domain_id": "domain_src_expense",
                "name": "src/expense",
                "support": "path_grouping",
                "flow_ids": ["flow_submit_report", "flow_approve_report"],
            }
        ],
        flows=[submit_flow(f, static=True, account_log="shown"), approve_flow(f, static=True)],
        findings=[loop_finding(f)],
        coverage={
            "scope": "静态骨架，尚未归纳业务含义。",
            "entries_total": 2,
            "entries_planned": 0,
            "entries_skipped": 0,
            "entries_unhandled": 2,
            "tasks_total": 0,
            "tasks_validated": 0,
            "tasks_pending": 0,
        },
    )


def partial(snapshot_id):
    ev = Evidence(snapshot_id)
    f = facts(ev)
    submit = submit_flow(f, static=False, account_log="unaccounted")
    submit["steps"].append(
        {
            "step_id": "step_notify_unknown",
            "name": "通知处理（未解析）",
            "kind": "external",
            "support": "agent_synthesis",
            "resolution": "unknown",
            "reason": "待审批之后是否发送通知取决于运行时注册的处理器，已读取的代码中找不到它的目标。",
        }
    )
    submit["edges"].append(
        {
            "source": "step_mark_pending",
            "target": "step_notify_unknown",
            "relation": "call",
            "support": "agent_synthesis",
            "resolution": "unknown",
            "reason": "没有静态调用关系可以确认这一步。",
        }
    )
    submit["steps"][2]["finding_ids"] = ["find_loop_no_count_bound"]
    failed = {
        "code": "task_failed",
        "message": "“经理审批”的归纳提交未通过校验，保留静态骨架。",
        "affects_completeness": True,
    }
    return document(
        snapshot_id,
        ev,
        analysis_status="partial",
        domains=[
            {
                "domain_id": "domain_expense",
                "name": "报销",
                "support": "agent_synthesis",
                "flow_ids": ["flow_submit_report", "flow_approve_report"],
            }
        ],
        flows=[
            submit,
            {
                # Not described yet: the plan's name and summary over the static structure.
                **approve_flow(f, static=True),
                "name": "经理审批",
                "summary": "经理批准一张处于待审批状态的报销单。",
                "name_from_plan": True,
                "limitations": [failed],
            },
        ],
        findings=[loop_finding(f)],
        coverage={
            "scope": "规划中的 2 条流程；其中 1 条归纳失败，跨流程连接尚未处理。",
            "entries_total": 2,
            "entries_planned": 2,
            "entries_skipped": 0,
            "entries_unhandled": 0,
            "tasks_total": 3,
            "tasks_validated": 1,
            "tasks_pending": 1,
            "tasks_failed": 1,
        },
    )


OLD_THRESHOLD, NEW_THRESHOLD = "amount >= THRESHOLD", "amount > THRESHOLD"
TEST_SOURCE = """import pytest

from expense.api import submit_report


@pytest.mark.parametrize("amount", [50, 500])
async def test_submit_report_status(amount):
    result = await submit_report({"id": "r1", "amount": amount})
    assert result["status"] in {"approved", "pending_approval"}
"""
# Base: inclusive threshold, a single model call. Head: exclusive threshold, a retry loop.
BASE_SOURCES = {
    **SOURCES,
    REVIEW: """from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    response = await client.responses.create(model="gpt-5", input=str(report))
    return response.output_text
""",
    TESTS: TEST_SOURCE,
}
HEAD_SOURCES = {
    **SOURCES,
    API: SOURCES[API].replace(OLD_THRESHOLD, NEW_THRESHOLD),
    TESTS: TEST_SOURCE,
}


def change_report(snapshot_id, head_map):
    base = Evidence(snapshot_id, BASE_SOURCES, BASE)
    head = Evidence(snapshot_id, HEAD_SOURCES, HEAD)
    f = facts(head, NEW_THRESHOLD)
    case_id = "head::" + TESTS + "#test_submit_report_status"
    case = head.cite(TESTS, "async def test_submit_report_status", 3, kind="test")
    findings = {item["finding_id"]: item for item in head_map["findings"]}
    on_review = {"flow_id": "flow_submit_report", "step_id": "step_model_review"}
    threshold = {
        "change_id": "chg_threshold_condition",
        "kind": "condition_modified",
        "symbol_id": SUBMIT,
        "before": {
            "side": "base",
            "text": OLD_THRESHOLD,
            "anchor": fp(SUBMIT, "condition", OLD_THRESHOLD),
            "evidence_ids": [base.cite(API, OLD_THRESHOLD)],
        },
        "after": {
            "side": "head",
            "text": NEW_THRESHOLD,
            "anchor": f["threshold"][0],
            "evidence_ids": [f["threshold"][1]],
        },
        "projection": {
            "status": "projected",
            "flow_id": "flow_submit_report",
            "step_id": "step_choose_path",
        },
        "explanation": {
            "summary": "分流条件从“大于等于阈值”改为“大于阈值”。",
            "effect": "金额恰好等于阈值的报销从模型审核路径转入自动批准路径。",
        },
        "tests": {
            "verdict": "reached_only",
            "basis": ["static_fact", "agent_assessment"],
            "execution_data": "not_collected",
            "note": "有 1 个参数化测试调用了提交报销，取值为 50 和 500，未发现取值等于阈值的用例。",
            "items": [
                {
                    "test_id": case_id,
                    "tags": ["related", "assertion_found"],
                    "evidence_ids": [case],
                }
            ],
        },
    }
    loop = {
        "change_id": "chg_review_loop",
        "kind": "loop_added",
        "symbol_id": MODEL,
        "after": {
            "side": "head",
            "text": "while True",
            "anchor": f["model_loop"][0],
            "evidence_ids": [f["model_loop"][1]],
        },
        "projection": {"status": "projected", **on_review},
        "explanation": {
            "summary": "模型审核改为循环调用，直到模型返回内容为止。",
            "effect": "模型一直不返回内容时，提交请求不会结束。",
        },
        "tests": {
            "verdict": "reached_only",
            "basis": ["static_fact"],
            "execution_data": "not_collected",
            "note": "测试经由提交报销间接触达模型审核，未发现针对重复调用的断言。",
            "items": [{"test_id": case_id, "tags": ["related"], "evidence_ids": [case]}],
        },
        "finding_ids": ["find_loop_no_count_bound"],
    }
    refs = {**base.refs, **head.refs}
    data = {
        "schema_version": "0.1.0",
        "snapshot_id": snapshot_id,
        "analysis_status": "complete",
        "changes": [threshold, loop],
        "unanalyzed_changes": [
            {
                "path": "docs/policy.md",
                "change": "modified",
                "reason": "不是受支持的源码文件，未做事实分析。",
            }
        ],
        "finding_changes": [
            {
                "status": "introduced",
                "finding": findings["find_loop_no_count_bound"],
                **on_review,
            },
            {
                "status": "persisting",
                "finding": findings["find_review_failure_unhandled"],
                **on_review,
            },
        ],
        "evidence": [refs[key].model_dump(mode="json") for key in sorted(refs)],
    }
    report = ChangeReport.model_validate(data)
    validate_change_report_against_map(report, BusinessMap.model_validate(head_map))
    return report.model_dump(mode="json", exclude_none=True)


def evidence_bundle(snapshot_id, *documents):
    """Excerpts for every evidence reference the given documents cite."""
    sources = {BASE: BASE_SOURCES, HEAD: HEAD_SOURCES}
    refs = {}
    for item in documents:
        for raw in item["evidence"]:
            refs[raw["evidence_id"]] = EvidenceRef.model_validate(raw)
    bundle = EvidenceBundle(
        snapshot_id=snapshot_id,
        excerpts=[
            {"evidence_id": key, "text": slice_source(sources[ref.side][ref.path], ref.range)}
            for key, ref in sorted(refs.items())
        ],
    )
    validate_evidence_bundle(bundle, tuple(refs.values()))
    return bundle.model_dump(mode="json")


def change_sample():
    out = OUT / "change"
    sides = {BASE: BASE_SOURCES, HEAD: HEAD_SOURCES}
    files = tuple(
        FileIdentity(
            path=path,
            side=side,
            kind="test" if path == TESTS else "code",
            content_digest=digest(text),
        )
        for side, sources in sides.items()
        for path, text in sources.items()
    )
    revisions = {
        "base_revision": "fixture-expense-change-base",
        "head_revision": "fixture-expense-change-head",
    }
    snapshot = SnapshotManifest(
        snapshot_id=snapshot_id_for(files=files, **revisions),
        files=files,
        integrity_status="complete",
        **revisions,
    )
    for side, sources in sides.items():
        for path, text in sources.items():
            write(out / side.value / path, text)
    head_map = complete(snapshot.snapshot_id, HEAD_SOURCES, NEW_THRESHOLD)
    report = change_report(snapshot.snapshot_id, head_map)
    documents = {
        "snapshot": snapshot.model_dump(mode="json"),
        "business-map": head_map,
        "change-report": report,
        "evidence-bundle": evidence_bundle(snapshot.snapshot_id, head_map, report),
    }
    for name, data in documents.items():
        write(out / f"{name}.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    files = tuple(
        FileIdentity(path=path, side=HEAD, kind="code", content_digest=digest(text))
        for path, text in SOURCES.items()
    )
    revisions = {"base_revision": None, "head_revision": "fixture-expense-head"}
    snapshot = SnapshotManifest(
        snapshot_id=snapshot_id_for(files=files, **revisions),
        files=files,
        integrity_status="complete",
        **revisions,
    )
    for path, text in SOURCES.items():
        write(OUT / "head" / path, text)
    write(OUT / "snapshot.json", json.dumps(snapshot.model_dump(mode="json"), indent=2) + "\n")
    samples = {"complete": complete, "skeleton": skeleton, "partial": partial}
    for name, build in samples.items():
        text = json.dumps(build(snapshot.snapshot_id), ensure_ascii=False, indent=2) + "\n"
        write(OUT / f"expense-{name}.json", text)
    change_sample()


if __name__ == "__main__":
    main()

"""A path into an `except` block is the agent's reading: the CLI has no fact to check it by."""

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from genesis_contracts.map_tasks import MapPlan
from test_git_snapshot import commit, write
from test_map_loop import entry, src

API = "pay/api.py"
FILES = {
    "pay/__init__.py": "",
    API: """from fastapi import APIRouter

from .gateway import charge, note_failure, settle

router = APIRouter()


@router.post("/orders")
def create_order(order):
    try:
        receipt = charge(order)
        return {"status": "paid", "receipt": receipt}
    except TimeoutError:
        return {"status": "retry_later"}


@router.post("/refunds")
def refund(order):
    try:
        charge(order)
    except TimeoutError:
        note_failure(order)
    return {"status": "done"}


@router.post("/captures")
def capture(order):
    try:
        receipt = charge(order)
    except TimeoutError:
        note_failure(order)
        raise
    settle(receipt)
    return {"status": "captured"}
""",
    "pay/gateway.py": 'def charge(order):\n    return order["id"]\n\n\n'
    "def note_failure(order):\n    return None\n\n\n"
    "def settle(receipt):\n    return None\n",
}


@pytest.fixture
def tasks(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    plan = {
        "flows": [
            {
                "key": "order",
                "name": "下单支付",
                "entry_ids": [entry(workspace, "#create_order").entry_id],
            },
            {"key": "refund", "name": "退款", "entry_ids": [entry(workspace, "#refund").entry_id]},
            {
                "key": "capture",
                "name": "扣款",
                "entry_ids": [entry(workspace, "#capture").entry_id],
            },
        ]
    }
    status = workspace.save_plan(MapPlan.model_validate(plan))
    return workspace, {task["name"]: task["task_id"] for task in status["tasks"]}


def order_flow(workspace, task_id, **handler):
    context = workspace.context(task_id)
    return {
        "name": "下单支付",
        "summary": "向支付网关扣款，超时则让用户稍后重试。",
        "steps": [
            {
                "key": "recv",
                "name": "收到订单",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 8, '@router.post("/orders")', 9)],
            },
            {
                "key": "charge",
                "name": "向支付网关扣款",
                "kind": "action",
                "evidence": [src(API, 11, "charge(order)")],
            },
            {
                "key": "paid",
                "name": "返回已支付",
                "kind": "result",
                "evidence": [src(API, 12, '"status": "paid"')],
            },
            {
                "key": "retry",
                "name": "返回稍后重试",
                "kind": "result",
                "evidence": [src(API, 14, '"retry_later"')],
            },
        ],
        "edges": [
            {"source": "recv", "target": "charge", "relation": "sequence"},
            {"source": "charge", "target": "paid", "relation": "sequence"},
            {
                "source": "charge",
                "target": "retry",
                "relation": "exception",
                "label": "网关超时",
                **handler,
            },
        ],
    }


def refund_flow(workspace, task_id, **handler):
    context = workspace.context(task_id)
    return {
        "name": "退款",
        "summary": "向支付网关退款，超时时记一笔失败。",
        "steps": [
            {
                "key": "recv",
                "name": "收到退款请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 17, '@router.post("/refunds")', 18)],
            },
            {
                "key": "charge",
                "name": "向支付网关退款",
                "kind": "action",
                "evidence": [src(API, 20, "charge(order)")],
            },
            {
                "key": "note",
                "name": "记录失败",
                "kind": "action",
                "evidence": [src(API, 22, "note_failure(order)")],
            },
            {
                "key": "done",
                "name": "返回完成",
                "kind": "result",
                "evidence": [src(API, 23, '"status": "done"')],
            },
        ],
        "edges": [
            {"source": "recv", "target": "charge", "relation": "sequence"},
            {"source": "charge", "target": "done", "relation": "sequence"},
            {"source": "charge", "target": "note", "relation": "exception", **handler},
            {"source": "note", "target": "done", "relation": "sequence"},
        ],
    }


def handler_edge(workspace, flow_name):
    flow = next(item for item in workspace.stored_map().flows if item.name == flow_name)
    return next(edge for edge in flow.edges if edge.relation == "exception")


def test_a_path_into_a_handler_is_accepted_as_written_and_kept_as_a_candidate(tasks):
    workspace, ids = tasks
    # The `try` body ends in a `return`, so no control path leads on to the handler.
    result = workspace.submit(ids["下单支付"], order_flow(workspace, ids["下单支付"]))
    assert result["status"] == "accepted", result.get("errors")
    edge = handler_edge(workspace, "下单支付")
    assert (edge.resolution, edge.support) == ("candidate", "agent_synthesis")
    assert edge.label == "网关超时" and edge.evidence_ids
    # Nothing was said about it, so the map says why it is no more than a candidate.
    assert "not analyzed" in edge.reason


def test_a_handler_the_code_runs_into_is_still_not_a_checked_fact(tasks):
    workspace, ids = tasks
    # Here the handler follows the `try` body in source order. That is not what the
    # edge claims, so it is not taken as support for it.
    said = {"reason": "网关超时时记一笔失败。"}
    result = workspace.submit(ids["退款"], refund_flow(workspace, ids["退款"], **said))
    assert result["status"] == "accepted", result.get("errors")
    edge = handler_edge(workspace, "退款")
    assert (edge.resolution, edge.support) == ("candidate", "agent_synthesis")
    assert edge.reason == "网关超时时记一笔失败。"
    # Claiming it resolved changes nothing; calling it unknown is kept.
    claimed = refund_flow(workspace, ids["退款"], resolution="resolved")
    assert workspace.submit(ids["退款"], claimed)["status"] == "accepted"
    assert handler_edge(workspace, "退款").resolution == "candidate"
    unknown = refund_flow(workspace, ids["退款"], resolution="unknown", reason="没有读到处理代码")
    assert workspace.submit(ids["退款"], unknown)["status"] == "accepted"
    assert handler_edge(workspace, "退款").resolution == "unknown"


def capture_flow(workspace, task_id):
    """A handler that ends in `raise`, and the code that runs when nothing was raised."""
    context = workspace.context(task_id)
    return {
        "name": "扣款",
        "summary": "向支付网关扣款并结算；网关超时时记一笔失败，把错误交给调用方。",
        "steps": [
            {
                "key": "recv",
                "name": "收到扣款请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 26, '@router.post("/captures")', 27)],
            },
            {
                "key": "charge",
                "name": "向支付网关扣款",
                "kind": "action",
                "evidence": [src(API, 29, "charge(order)")],
            },
            {
                "key": "note",
                "name": "记录失败",
                "kind": "action",
                "evidence": [src(API, 31, "note_failure(order)")],
            },
            {
                "key": "failed",
                "name": "把超时错误交给调用方",
                "kind": "result",
                "evidence": [src(API, 32, "raise")],
            },
            {
                "key": "settle",
                "name": "结算",
                "kind": "action",
                "evidence": [src(API, 33, "settle(receipt)")],
            },
            {
                "key": "done",
                "name": "返回已扣款",
                "kind": "result",
                "evidence": [src(API, 34, '"captured"')],
            },
        ],
        "edges": [
            {"source": "recv", "target": "charge", "relation": "sequence"},
            # Nothing was raised: on to the code after the `try`, past the handler.
            {"source": "charge", "target": "settle", "relation": "sequence"},
            {"source": "charge", "target": "note", "relation": "exception", "label": "网关超时"},
            {"source": "note", "target": "failed", "relation": "sequence"},
            {"source": "settle", "target": "done", "relation": "sequence"},
        ],
    }


def test_code_after_a_try_is_reached_past_a_handler_that_ends_the_path(tasks):
    workspace, ids = tasks
    result = workspace.submit(ids["扣款"], capture_flow(workspace, ids["扣款"]))
    assert result["status"] == "accepted", result.get("errors")
    flow = next(item for item in workspace.stored_map().flows if item.name == "扣款")
    names = {step.step_id: step.name for step in flow.steps}
    assert {
        (names[edge.source], names[edge.target]): (edge.relation, edge.support, edge.resolution)
        for edge in flow.edges
    } == {
        ("收到扣款请求", "向支付网关扣款"): ("sequence", "static_fact", "resolved"),
        ("向支付网关扣款", "结算"): ("sequence", "static_fact", "resolved"),
        ("向支付网关扣款", "记录失败"): ("exception", "agent_synthesis", "candidate"),
        ("记录失败", "把超时错误交给调用方"): ("sequence", "static_fact", "resolved"),
        ("结算", "返回已扣款"): ("sequence", "static_fact", "resolved"),
    }


def test_a_handler_is_entered_by_an_exception_edge_and_by_nothing_else(tasks):
    workspace, ids = tasks
    # Nothing leads into a handler in the order of the source, even when it does not
    # end the path: only an exception does, and that is what the edge has to say.
    flow = refund_flow(workspace, ids["退款"])
    flow["edges"][2]["relation"] = "sequence"
    refused = workspace.submit(ids["退款"], flow)
    assert [(item["path"], item["code"]) for item in refused["errors"]] == [
        ("edges[2]", "edge_not_supported")
    ]
    flow = capture_flow(workspace, ids["扣款"])
    flow["edges"].append({"source": "failed", "target": "settle", "relation": "sequence"})
    refused = workspace.submit(ids["扣款"], flow)
    assert [(item["path"], item["code"]) for item in refused["errors"]] == [
        ("edges[5]", "edge_not_supported")
    ]


def test_the_static_structure_keeps_a_handler_off_the_path_too(tasks):
    workspace, _ = tasks
    # Before anyone describes it: the flow of the entry as the facts alone give it.
    fresh = Workspace(workspace.repo, workspace.session["session_id"])
    fresh.save_plan(None)
    flow = next(
        item for item in fresh.stored_map().flows if item.entries[0].symbol_id.endswith("#capture")
    )
    names = {step.step_id: step.name for step in flow.steps}
    links = {(names[edge.source], names[edge.target]) for edge in flow.edges}
    assert ("charge(order)", "settle(receipt)") in links
    assert not [pair for pair in links if pair[1] == "note_failure(order)"]
    assert ("note_failure(order)", "raise") in links

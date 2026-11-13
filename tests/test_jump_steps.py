"""`break` and `continue` only say where a loop goes next: no step can stand on them."""

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from test_git_snapshot import commit, write
from test_map_loop import codes, src

API = "sync/api.py"
SYMBOL = API + "#sync_orders"
FILES = {
    "sync/__init__.py": "",
    API: """from fastapi import APIRouter

from .remote import fetch_page, store

router = APIRouter()


@router.post("/sync")
def sync_orders(account):
    pages = []
    for cursor in range(10):
        page = fetch_page(account, cursor)
        if not page:
            break
        if page["skip"]:
            continue
        pages.append(page)
    store(account, pages)
    return {"pages": len(pages)}
""",
    "sync/remote.py": "def fetch_page(account, cursor):\n    return {}\n\n\n"
    "def store(account, pages):\n    return None\n",
}


@pytest.fixture
def synced(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def jump(workspace, text):
    return next(fact for fact in workspace.by_symbol[SYMBOL] if fact.text == text)


def sync_flow(workspace, task_id):
    """The loop as the code runs it: each jump is the edge its condition takes."""
    context = workspace.context(task_id)
    return {
        "name": "同步订单",
        "summary": "逐页拉取订单，拉完后保存。",
        "steps": [
            {
                "key": "recv",
                "name": "收到同步请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 8, '@router.post("/sync")', 9)],
            },
            {
                "key": "pages",
                "name": "逐页处理",
                "kind": "decision",
                "evidence": [src(API, 11, "for cursor in range(10)")],
            },
            {
                "key": "fetch",
                "name": "拉取一页订单",
                "kind": "action",
                "evidence": [src(API, 12, "fetch_page(account, cursor)")],
            },
            {
                "key": "empty",
                "name": "这一页是否为空",
                "kind": "decision",
                "evidence": [src(API, 13, "if not page")],
            },
            {
                "key": "skip",
                "name": "这一页是否跳过",
                "kind": "decision",
                "evidence": [src(API, 15, 'page["skip"]')],
            },
            {
                "key": "store",
                "name": "保存订单",
                "kind": "action",
                "evidence": [src(API, 18, "store(account, pages)")],
            },
            {
                "key": "done",
                "name": "返回页数",
                "kind": "result",
                "evidence": [src(API, 19, "return")],
            },
        ],
        "edges": [
            {"source": "recv", "target": "pages", "relation": "sequence"},
            {"source": "pages", "target": "fetch", "relation": "branch", "branch": "loop"},
            {"source": "fetch", "target": "empty", "relation": "sequence"},
            # `break`: the branch leaves the loop for the step after it.
            {
                "source": "empty",
                "target": "store",
                "relation": "branch",
                "branch": "true",
                "label": "没有更多订单",
            },
            {"source": "empty", "target": "skip", "relation": "branch", "branch": "false"},
            # `continue`: the branch goes back to the loop.
            {
                "source": "skip",
                "target": "pages",
                "relation": "branch",
                "branch": "true",
                "label": "跳过这一页",
            },
            {"source": "skip", "target": "pages", "relation": "branch", "branch": "false"},
            {"source": "pages", "target": "store", "relation": "branch", "branch": "exit"},
            {"source": "store", "target": "done", "relation": "sequence"},
        ],
    }


def test_a_jump_is_described_by_the_edge_its_condition_takes(synced):
    workspace, task = synced
    result = workspace.submit(task, sync_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    assert result["accounting"]["unaccounted"] == 0


def test_a_query_lists_no_fact_a_step_cannot_stand_on(synced):
    workspace, task = synced
    queried = workspace.query_symbol(SYMBOL)
    assert "break" in queried["source"]["text"]
    kinds = {fact["kind"] for fact in queried["facts"]}
    assert kinds == {"loop", "call", "condition", "return"}
    # The task context makes the same choice.
    context = workspace.context(task)
    listed = {fact["kind"] for fact in (*context["accountable"], *context["other_facts"])}
    assert not listed & {"break", "continue"}


@pytest.mark.parametrize("text", ["break", "continue"])
def test_a_step_anchored_on_a_jump_is_refused_for_that_and_nothing_else(synced, text):
    workspace, task = synced
    flow = sync_flow(workspace, task)
    source = "empty" if text == "break" else "skip"
    flow["steps"].append(
        {
            "key": "stop",
            "name": "停止拉取",
            "kind": "action",
            "anchors": [jump(workspace, text).fingerprint],
            "evidence": [src(API, 14 if text == "break" else 16, text)],
        }
    )
    # What an agent draws around such a step: into it on the branch, and on from it.
    taken = next(
        edge for edge in flow["edges"] if edge["source"] == source and edge.get("branch") == "true"
    )
    onward = taken["target"]
    taken["target"] = "stop"
    flow["edges"].append({"source": "stop", "target": onward, "relation": "sequence"})
    result = workspace.submit(task, flow)
    assert result["status"] == "rejected"
    # Not the two reachability errors that follow from it: those say nothing about why.
    assert codes(result) == [("steps[7].anchors", "anchor_not_a_step")]
    assert f"`{text}`" in result["errors"][0]["message"]

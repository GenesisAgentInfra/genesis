"""Drawings the skill describes for cases that are easy to get wrong.

One function called twice in a flow, a call in a loop header, the way back to a loop,
a function handed to a thread, and a loop that anchors a step which is no decision.
"""

import copy

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from test_git_snapshot import commit, write
from test_map_loop import codes, src

API = "batch/api.py"
WORK = "batch/work.py"
FILES = {
    "batch/__init__.py": "",
    API: """import threading

from fastapi import APIRouter

from .store import mark_started
from .work import clean, load_items, run_batch

router = APIRouter()


@router.post("/batches")
def start_batch(batch):
    names = clean(batch["names"])
    tags = clean(batch["tags"])
    for item in load_items(batch):
        mark_started(item)
    worker = threading.Thread(target=run_batch, args=(names, tags))
    worker.start()
    return {"started": True}
""",
    WORK: """from .store import drop_empty, fetch, save_result


def clean(values):
    kept = drop_empty(values)
    return sorted(kept)


def load_items(batch):
    items = fetch(batch)
    if not items:
        return []
    return items


def run_batch(names, tags):
    for name in names:
        save_result(name, tags)
    save_result("done", tags)
""",
    "batch/store.py": "def drop_empty(values):\n    return values\n\n\n"
    "def fetch(batch):\n    return []\n\n\n"
    "def mark_started(item):\n    return None\n\n\n"
    "def save_result(name, tags):\n    return None\n",
}


TIDY = "tidy/api.py"
RULES = "tidy/rules.py"
# A function called first thing in the body of two loops.
TIDY_FILES = {
    "tidy/__init__.py": "",
    TIDY: """from fastapi import APIRouter

from .rules import keep
from .store import finish, store

router = APIRouter()


@router.post("/tidy")
def tidy(batch):
    for name in batch["names"]:
        kept = keep(name)
        store(kept)
    for tag in batch["tags"]:
        keep(tag)
    return finish(batch)
""",
    RULES: """from .store import rename

RESERVED = {"id", "name"}


def keep(value):
    if value in RESERVED:
        return rename(value)
    return value
""",
    "tidy/store.py": "def rename(value):\n    return 'x_' + value\n\n\n"
    "def store(value):\n    return None\n\n\n"
    "def finish(batch):\n    return {'done': True}\n",
}
SOURCES = {**FILES, **TIDY_FILES}


def at(path, needle):
    """The line of `path` that holds `needle`, so the samples can be read without counting."""
    lines = SOURCES[path].splitlines()
    return next(index for index, text in enumerate(lines, 1) if needle in text)


def cite(path, needle, quote=None):
    return src(path, at(path, needle), quote or needle)


@pytest.fixture
def batching(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def fact(workspace, symbol, kind, starts):
    listed = workspace.query_symbol(symbol)["facts"]
    return next(
        item["fingerprint"]
        for item in listed
        if item["kind"] == kind and item["text"].startswith(starts)
    )


def batch_flow(workspace, task_id):
    """Every case at once, drawn the way the skill says."""
    context = workspace.context(task_id)
    entry = "batch/api.py#start_batch"
    return {
        "name": "发起一批处理",
        "steps": [
            {
                "key": "recv",
                "name": "收到批处理请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [
                    src(API, at(API, "@router.post"), "@router.post", at(API, "def start"))
                ],
            },
            # The same function called twice: a step at each place it is called from.
            {
                "key": "names",
                "name": "整理名称",
                "kind": "action",
                "evidence": [cite(API, 'clean(batch["names"])')],
            },
            {
                "key": "tags",
                "name": "整理标签",
                "kind": "action",
                "evidence": [cite(API, 'clean(batch["tags"])')],
            },
            # Its inside is drawn once.
            {
                "key": "drop",
                "name": "去掉空值",
                "kind": "action",
                "evidence": [cite(WORK, "drop_empty(values)")],
            },
            # A call in a loop header: the call and the loop are a step each.
            {
                "key": "load",
                "name": "读取这一批的条目",
                "kind": "action",
                "anchors": [fact(workspace, entry, "call", "load_items")],
                "evidence": [cite(API, "load_items(batch)")],
            },
            {
                "key": "fetch",
                "name": "从存储取出条目",
                "kind": "action",
                "evidence": [cite(WORK, "fetch(batch)")],
            },
            {
                "key": "none",
                "name": "是否没有条目",
                "kind": "decision",
                "evidence": [cite(WORK, "if not items")],
            },
            {
                "key": "each",
                "name": "逐个处理条目",
                "kind": "decision",
                "anchors": [fact(workspace, entry, "loop", "for item")],
                "evidence": [cite(API, "for item in", "for item in")],
            },
            {
                "key": "mark",
                "name": "标记为已开始",
                "kind": "action",
                "evidence": [cite(API, "mark_started(item)")],
            },
            # A function handed to a thread.
            {
                "key": "spawn",
                "name": "起后台线程执行这一批",
                "kind": "action",
                "evidence": [cite(API, "threading.Thread(", "target=run_batch")],
            },
            {
                "key": "started",
                "name": "告知已开始",
                "kind": "result",
                "evidence": [cite(API, "return {")],
            },
            # A loop that anchors a step which decides nothing.
            {
                "key": "write",
                "name": "逐个保存结果",
                "kind": "action",
                "evidence": [
                    src(
                        WORK, at(WORK, "for name in"), "for name in names", at(WORK, "(name, tags)")
                    )
                ],
            },
            {
                "key": "finish",
                "name": "记下这一批已完成",
                "kind": "action",
                "evidence": [cite(WORK, 'save_result("done"')],
            },
        ],
        "edges": [
            {"source": "recv", "target": "names", "relation": "sequence"},
            # In from both places, and back to what each of them does next.
            {"source": "names", "target": "drop", "relation": "call"},
            {"source": "drop", "target": "tags", "relation": "sequence"},
            {"source": "tags", "target": "drop", "relation": "call"},
            {"source": "drop", "target": "load", "relation": "sequence"},
            # The call runs once, and the function it enters leads back to the loop.
            {"source": "load", "target": "fetch", "relation": "call"},
            {"source": "fetch", "target": "none", "relation": "sequence"},
            {"source": "none", "target": "each", "relation": "branch", "branch": "true"},
            {"source": "none", "target": "each", "relation": "branch", "branch": "false"},
            {"source": "each", "target": "mark", "relation": "branch", "branch": "loop"},
            {"source": "mark", "target": "each", "relation": "loop"},
            {"source": "each", "target": "spawn", "relation": "branch", "branch": "exit"},
            # The caller does not wait for the thread: it goes on, and the thread's work
            # ends where it ends.
            {"source": "spawn", "target": "write", "relation": "call"},
            {"source": "spawn", "target": "started", "relation": "sequence"},
            {"source": "write", "target": "finish", "relation": "sequence"},
        ],
    }


def stored_edges(workspace):
    flow = workspace.stored_map().flows[0]
    keys = {step.step_id: step for step in flow.steps}
    return flow, {
        (keys[edge.source].name, keys[edge.target].name, edge.relation): edge for edge in flow.edges
    }


def test_the_drawings_the_skill_describes_are_accepted_as_facts(batching):
    workspace, task = batching
    result = workspace.submit(task, batch_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    assert result["accounting"]["unaccounted"] == 0, result["unaccounted"]
    flow, edges = stored_edges(workspace)
    # Checked against the code, every one of them: nothing here is a candidate.
    assert {(edge.support, edge.resolution) for edge in flow.edges} == {("static_fact", "resolved")}
    # One function, called from two places, drawn once.
    assert [step.name for step in flow.steps].count("去掉空值") == 1
    assert ("整理名称", "去掉空值", "call") in edges and ("整理标签", "去掉空值", "call") in edges
    # The way back to the loop keeps its own relation.
    assert ("标记为已开始", "逐个处理条目", "loop") in edges
    # A step on a loop need not be a decision.
    write_step = next(step for step in flow.steps if step.name == "逐个保存结果")
    kinds = {workspace.by_fingerprint[anchor].kind for anchor in write_step.anchors}
    assert (write_step.kind, kinds) == ("action", {"loop", "call"})


def test_a_call_in_a_loop_header_may_also_be_one_step_that_stands_for_the_function(batching):
    workspace, task = batching
    flow = batch_flow(workspace, task)
    # Not expanded: the line is cited, and the call and the loop both anchor the step.
    flow["steps"] = [step for step in flow["steps"] if step["key"] not in {"load", "fetch", "none"}]
    each = next(step for step in flow["steps"] if step["key"] == "each")
    del each["anchors"]
    flow["edges"] = [
        edge
        for edge in flow["edges"]
        if not {edge["source"], edge["target"]} & {"load", "fetch", "none"}
    ] + [{"source": "drop", "target": "each", "relation": "sequence"}]
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    assert result["accounting"]["unaccounted"] == 0, result["unaccounted"]
    stored, _ = stored_edges(workspace)
    step = next(item for item in stored.steps if item.name == "逐个处理条目")
    assert sorted(workspace.by_fingerprint[anchor].kind for anchor in step.anchors) == [
        "call",
        "loop",
    ]
    assert [item.symbol_id for item in step.unexpanded] == ["batch/work.py#load_items"]


def test_only_a_decision_step_shows_the_branches_of_its_loop(batching):
    workspace, task = batching
    flow = copy.deepcopy(batch_flow(workspace, task))
    flow["edges"].append(
        {"source": "write", "target": "finish", "relation": "branch", "branch": "exit"}
    )
    result = workspace.submit(task, flow)
    assert codes(result) == [("edges[15].branch", "unknown_branch")]
    assert "decision step" in result["errors"][0]["message"]


def test_a_caller_that_waits_for_the_function_it_handed_over_may_draw_the_way_back(batching):
    workspace, task = batching
    flow = batch_flow(workspace, task)
    # Whether the caller waits cannot be told from the code's structure: both are taken.
    flow["edges"].append({"source": "finish", "target": "started", "relation": "sequence"})
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")


@pytest.fixture
def tidying(source_repo):
    for path, text in TIDY_FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def tidy_flow(workspace, task_id):
    """Two loops whose bodies begin with a call to the same expanded function."""
    context = workspace.context(task_id)
    return {
        "name": "整理一批名称和标签",
        "steps": [
            {
                "key": "recv",
                "name": "收到整理请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [
                    src(TIDY, at(TIDY, "@router.post"), "@router.post", at(TIDY, "def tidy"))
                ],
            },
            {
                "key": "names",
                "name": "逐个处理名称",
                "kind": "decision",
                "evidence": [cite(TIDY, "for name in")],
            },
            # The inside of the function, drawn once. Neither call to it has a step.
            {
                "key": "reserved",
                "name": "是否是保留字",
                "kind": "decision",
                "evidence": [cite(RULES, "if value in RESERVED")],
            },
            {
                "key": "rename",
                "name": "给保留字改名",
                "kind": "action",
                "evidence": [cite(RULES, "return rename(value)")],
            },
            {
                "key": "store",
                "name": "保存名称",
                "kind": "action",
                "evidence": [cite(TIDY, "store(kept)")],
            },
            {
                "key": "tags",
                "name": "逐个处理标签",
                "kind": "decision",
                "evidence": [cite(TIDY, "for tag in")],
            },
            {
                "key": "done",
                "name": "告知已整理完",
                "kind": "result",
                "evidence": [cite(TIDY, "return finish(batch)")],
            },
        ],
        "edges": [
            {"source": "recv", "target": "names", "relation": "sequence"},
            # Into the function by the loop's own branch: the decision keeps its branch.
            {"source": "names", "target": "reserved", "relation": "branch", "branch": "loop"},
            {"source": "reserved", "target": "rename", "relation": "branch", "branch": "true"},
            # Out of it to what each caller runs next.
            {"source": "reserved", "target": "store", "relation": "branch", "branch": "false"},
            {"source": "rename", "target": "store", "relation": "sequence"},
            {"source": "store", "target": "names", "relation": "loop"},
            {"source": "names", "target": "tags", "relation": "branch", "branch": "exit"},
            {"source": "tags", "target": "reserved", "relation": "branch", "branch": "loop"},
            # The second loop has nothing after the call: the function leads back to it.
            {"source": "reserved", "target": "tags", "relation": "branch", "branch": "false"},
            {"source": "rename", "target": "tags", "relation": "loop"},
            {"source": "tags", "target": "done", "relation": "branch", "branch": "exit"},
        ],
    }


def test_a_branch_that_begins_with_a_call_enters_the_function_by_its_own_branch_edge(tidying):
    workspace, task = tidying
    result = workspace.submit(task, tidy_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    assert result["accounting"]["unaccounted"] == 0, result["unaccounted"]
    flow, edges = stored_edges(workspace)
    assert {(edge.support, edge.resolution) for edge in flow.edges} == {("static_fact", "resolved")}
    # Both loops keep the branch that goes into their body, and it lands inside the function.
    for loop in ("逐个处理名称", "逐个处理标签"):
        entering = edges[(loop, "是否是保留字", "branch")]
        assert entering.condition.branch == "loop"
    assert [step.name for step in flow.steps].count("是否是保留字") == 1
    # The function is expanded by the steps inside it: no step stands for it at a call.
    stood_for = {item.symbol_id for step in flow.steps for item in step.unexpanded}
    assert "tidy/rules.py#keep" not in stood_for


def test_a_call_edge_in_place_of_that_branch_is_taken_but_the_decision_loses_the_branch(tidying):
    workspace, task = tidying
    flow = tidy_flow(workspace, task)
    flow["edges"][1] = {"source": "names", "target": "reserved", "relation": "call"}
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    _, edges = stored_edges(workspace)
    assert ("逐个处理名称", "是否是保留字", "call") in edges
    # Nothing on the map says any more which outcome of the loop leads into the function.
    leaving = {
        edge.condition.branch
        for (source, _, _), edge in edges.items()
        if source == "逐个处理名称" and edge.condition
    }
    assert leaving == {"exit"}

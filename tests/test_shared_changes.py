"""Code two flows share is described on one of them: the CLI says which one is closest."""

from genesis_ci.business_map.changes import CALLS, CHANGE_TASK
from genesis_contracts.map_tasks import MapPlan
from test_change_analysis import by_kind, two_commits
from test_map_loop import entry, src

API = "notify/api.py"
SERVICE = "notify/service.py"
BASE = {
    "notify/__init__.py": "",
    API: """from fastapi import APIRouter

from .jobs import run_job
from .service import send_digest

router = APIRouter()


@router.post("/digests")
def post_digest(user):
    return send_digest(user)


@router.post("/jobs")
def post_job(user):
    return run_job(user)
""",
    "notify/jobs.py": "from .service import send_digest\n\n\n"
    "def run_job(user):\n    return send_digest(user)\n",
    SERVICE: """def send_digest(user):
    digest = build_digest(user)
    return deliver(digest)


def build_digest(user):
    if user.get("muted"):
        return None
    return {"to": user["email"], "items": 3}


def deliver(digest):
    return digest is not None
""",
}
# One change, two calls from `post_digest` and three from `post_job`.
HEAD = {**BASE, SERVICE: BASE[SERVICE].replace('"items": 3', '"items": 5')}


def listed(workspace, key):
    """Changes by the last word of the flow they are listed under, in the order given."""
    return {
        item["flow"].rsplit(" ", 1)[-1]: item["changes"] for item in workspace.change_summary()[key]
    }


def planned(workspace, *names):
    plan = {
        "flows": [
            {"key": name, "name": name, "entry_ids": [entry(workspace, "#" + name).entry_id]}
            for name in names
        ]
    }
    status = workspace.save_plan(MapPlan.model_validate(plan))
    return {task["name"]: task["task_id"] for task in status["tasks"]}


def digest_flow(workspace, task_id, *, expanded):
    """The digest flow, with one step for `send_digest` or with the way to the change."""
    context = workspace.context(task_id)
    flow = {
        "name": "post_digest",
        "steps": [
            {
                "key": "recv",
                "name": "收到发送摘要的请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 9, '@router.post("/digests")', 10)],
            },
            {
                "key": "send",
                "name": "发送摘要",
                "kind": "result",
                "evidence": [src(API, 11, "send_digest(user)")],
            },
        ],
        "edges": [{"source": "recv", "target": "send", "relation": "sequence"}],
    }
    if expanded:
        flow["steps"] += [
            {
                "key": "build",
                "name": "生成摘要内容",
                "kind": "action",
                "evidence": [src(SERVICE, 2, "build_digest(user)")],
            },
            {
                "key": "muted",
                "name": "用户是否已静音",
                "kind": "decision",
                "evidence": [src(SERVICE, 7, 'user.get("muted")')],
            },
            {
                "key": "items",
                "name": "摘要包含最近的条目",
                "kind": "action",
                "evidence": [src(SERVICE, 9, '"items": 5')],
            },
            {
                "key": "deliver",
                "name": "投递摘要",
                "kind": "action",
                "evidence": [src(SERVICE, 3, "deliver(digest)")],
            },
        ]
        flow["edges"] += [
            {"source": "send", "target": "build", "relation": "call"},
            {"source": "build", "target": "muted", "relation": "call"},
            {"source": "muted", "target": "items", "relation": "branch", "branch": "false"},
            {"source": "muted", "target": "deliver", "relation": "branch", "branch": "true"},
            {"source": "items", "target": "deliver", "relation": "sequence"},
        ]
    return flow


def test_a_change_no_step_covers_is_marked_on_the_flow_closest_to_it(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    change = by_kind(workspace.stored_report(), "result_modified").change_id
    # Both flows reach it; one of them is named as the flow to describe it on.
    assert listed(workspace, "possibly_affected") == {
        "post_digest": [change],
        "post_job": [change],
    }
    assert listed(workspace, "closest_flow") == {"post_digest": [change]}


def test_the_closest_flow_does_not_depend_on_the_order_of_the_plan(source_repo):
    # Here both entries call the shared function themselves: two calls from each.
    direct = {**BASE, API: BASE[API].replace("run_job(user)", "send_digest(user)")}
    workspace, _ = two_commits(source_repo, direct, {**direct, SERVICE: HEAD[SERVICE]})
    change = by_kind(workspace.stored_report(), "result_modified").change_id
    planned(workspace, "post_job", "post_digest")
    assert list(listed(workspace, "possibly_affected")) == ["post_job", "post_digest"]
    # A tie goes to the entry that sorts first, whichever flow the plan names first.
    assert listed(workspace, "closest_flow") == {"post_digest": [change]}


def test_a_flow_task_says_which_changes_to_bring_onto_it(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    change = by_kind(workspace.stored_report(), "result_modified").change_id
    # Before any plan the flow to describe is already named, by the label of its entry.
    before = workspace.status()
    assert [flow["name"] for flow in before["change"]["affected_flows"]] == [
        "POST /digests · post_digest"
    ]
    assert before["change"]["changes_waiting"] == 1
    tasks = planned(workspace, "post_job", "post_digest")
    # It is offered first, although the plan lists the other flow before it, and the
    # change task does not come up while it is still to be described.
    assert workspace.status()["next_task"] == tasks["post_digest"]
    # The flow that is to carry the change is told which function to expand for it.
    wanted = [{"symbol_id": "notify/service.py#build_digest", "changes": [change]}]
    assert workspace.context(tasks["post_digest"])["change"] == {
        "placed": [],
        "closest_to": [change],
        "expand": wanted,
        "on_other_flows": [],
    }
    assert workspace.context(tasks["post_job"])["change"] == {
        "placed": [],
        "closest_to": [],
        "expand": [],
        "on_other_flows": [{"flow": "post_digest", "changes": [change]}],
    }
    # One step standing for the shared function leaves the change where it was.
    folded = workspace.submit(
        tasks["post_digest"], digest_flow(workspace, tasks["post_digest"], expanded=False)
    )
    assert folded["status"] == "accepted", folded.get("errors")
    assert workspace.context(tasks["post_digest"])["change"]["closest_to"] == [change]
    assert workspace.context(tasks["post_digest"])["change"]["expand"] == wanted
    # Expanding the way to it places the change, and nothing is left to bring anywhere.
    expanded = workspace.submit(
        tasks["post_digest"], digest_flow(workspace, tasks["post_digest"], expanded=True)
    )
    assert expanded["status"] == "accepted", expanded.get("errors")
    assert workspace.context(tasks["post_digest"])["change"] == {
        "placed": [change],
        "closest_to": [],
        "expand": [],
        "on_other_flows": [],
    }
    assert workspace.context(tasks["post_job"])["change"] == {
        "placed": [],
        "closest_to": [],
        "expand": [],
        "on_other_flows": [{"flow": "post_digest", "changes": [change]}],
    }
    assert listed(workspace, "possibly_affected") == {"post_job": [change]}
    assert listed(workspace, "closest_flow") == {}


def test_a_change_on_steps_that_only_call_its_function_still_has_one_closest_flow(source_repo):
    # Both entries call `send_digest` themselves, and the change is inside it.
    direct = {**BASE, API: BASE[API].replace("run_job(user)", "send_digest(user)")}
    changed = direct[SERVICE].replace("return deliver(digest)", "return deliver(digest) or None")
    workspace, _ = two_commits(source_repo, direct, {**direct, SERVICE: changed})
    item = by_kind(workspace.stored_report(), "result_modified")
    # No flow has a step inside the function: the change shows on both calling steps.
    assert item.projection.reason == CALLS and len(item.other_projections) == 1
    tasks = planned(workspace, "post_job", "post_digest")
    assert listed(workspace, "closest_flow") == {"post_digest": [item.change_id]}
    assert workspace.context(tasks["post_digest"])["change"] == {
        "placed": [item.change_id],
        "closest_to": [item.change_id],
        "expand": [{"symbol_id": "notify/service.py#send_digest", "changes": [item.change_id]}],
        "on_other_flows": [],
    }
    # The other flow keeps the change on its calling step and is told who expands it.
    assert workspace.context(tasks["post_job"])["change"] == {
        "placed": [item.change_id],
        "closest_to": [],
        "expand": [],
        "on_other_flows": [{"flow": "post_digest", "changes": [item.change_id]}],
    }


def test_a_flow_task_names_the_function_each_of_its_changes_is_in(source_repo):
    # A constant one function reads, a result in that function's neighbour, and a
    # result one call nearer to the entry.
    constant = "ITEMS = 3\n\n\n" + BASE[SERVICE].replace('"items": 3', '"items": ITEMS')
    base = {**BASE, SERVICE: constant}
    changed = (
        constant.replace("ITEMS = 3", "ITEMS = 5")
        .replace("digest is not None", "digest is not None or False")
        .replace("return deliver(digest)", "return deliver(digest) or None")
    )
    workspace, _ = two_commits(source_repo, base, {**base, SERVICE: changed})
    report = workspace.stored_report()
    limit = by_kind(report, "source_modified").change_id
    sent = by_kind(report, "result_modified", "#send_digest").change_id
    delivered = by_kind(report, "result_modified", "#deliver").change_id
    tasks = planned(workspace, "post_digest")
    change = workspace.context(tasks["post_digest"])["change"]
    assert sorted(change["closest_to"]) == sorted([limit, sent, delivered])
    # Nearest to the entry first. The constant is listed under the function that reads it.
    assert change["expand"] == [
        {"symbol_id": "notify/service.py#send_digest", "changes": [sent]},
        {"symbol_id": "notify/service.py#build_digest", "changes": [limit]},
        {"symbol_id": "notify/service.py#deliver", "changes": [delivered]},
    ]
    # A step inside one of them takes its change off the list and leaves the others.
    flow = digest_flow(workspace, tasks["post_digest"], expanded=False)
    flow["steps"].append(
        {
            "key": "deliver",
            "name": "投递摘要",
            "kind": "action",
            "evidence": [src(SERVICE, 6, "deliver(digest)")],
        }
    )
    flow["edges"].append({"source": "send", "target": "deliver", "relation": "call"})
    result = workspace.submit(tasks["post_digest"], flow)
    assert result["status"] == "accepted", result.get("errors")
    left = workspace.context(tasks["post_digest"])["change"]
    assert sent in left["placed"] and sent not in left["closest_to"]
    assert [item["symbol_id"] for item in left["expand"]] == [
        "notify/service.py#build_digest",
        "notify/service.py#deliver",
    ]


def test_a_session_without_a_base_has_no_change_block(source_repo):
    from genesis_ci.business_map.session import prepare
    from genesis_ci.business_map.workspace import Workspace
    from test_git_snapshot import commit, write

    for path, text in BASE.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    assert "change" not in workspace.context(task)


def test_a_function_one_flow_expands_is_still_one_step_in_the_flow_beside_it(source_repo):
    direct = {**BASE, API: BASE[API].replace("run_job(user)", "send_digest(user)")}
    workspace, _ = two_commits(source_repo, direct, {**direct, SERVICE: HEAD[SERVICE]})
    tasks = planned(workspace, "post_job", "post_digest")
    digest = digest_flow(workspace, tasks["post_digest"], expanded=True)
    assert workspace.submit(tasks["post_digest"], digest)["status"] == "accepted"
    context = workspace.context(tasks["post_job"])
    job = {
        "name": "post_job",
        "steps": [
            {
                "key": "recv",
                "name": "收到任务请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 14, '@router.post("/jobs")', 15)],
            },
            {
                "key": "send",
                "name": "发送摘要",
                "kind": "result",
                "evidence": [src(API, 16, "send_digest(user)")],
            },
        ],
        "edges": [{"source": "recv", "target": "send", "relation": "sequence"}],
    }
    assert workspace.submit(tasks["post_job"], job)["status"] == "accepted"
    # Each flow goes by its own steps. The flow with steps inside the function has it
    # expanded, and its step on the call is unmarked; in the flow beside it the step on
    # the same call still stands for the function.
    assert {
        flow.name: [item.symbol_id for step in flow.steps for item in step.unexpanded]
        for flow in workspace.stored_map().flows
    } == {
        "post_job": ["notify/service.py#send_digest"],
        "post_digest": ["notify/service.py#deliver"],
    }


def test_describing_a_flow_places_a_change_and_only_an_explanation_settles_it(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    change = by_kind(workspace.stored_report(), "result_modified").change_id
    tasks = planned(workspace, "post_job", "post_digest")

    def counters():
        status, shown = workspace.status()["change"], workspace.change_summary()
        counted = (status["changes_placed"], status["changes_waiting"])
        assert counted == (shown["changes_placed"], shown["changes_waiting"])
        return counted

    # Within reach of a flow and not yet on it: waiting from the start.
    assert counters() == (0, 1)
    digest = digest_flow(workspace, tasks["post_digest"], expanded=True)
    assert workspace.submit(tasks["post_digest"], digest)["status"] == "accepted"
    # Describing the flow gives the change a place; it still waits for an explanation.
    assert counters() == (1, 1)
    explained = {"changes": [{"change_id": change, "summary": "摘要的条目数从 3 条改为 5 条。"}]}
    assert workspace.submit(CHANGE_TASK, explained)["status"] == "accepted"
    assert counters() == (1, 0)


CONSTANT = "ITEMS = 3\n\n\n" + BASE[SERVICE].replace('"items": 3', '"items": ITEMS')


def test_a_constant_another_flow_reads_first_leaves_the_closest_flow_and_is_named_there(
    source_repo,
):
    base = {**BASE, SERVICE: CONSTANT}
    workspace, _ = two_commits(
        source_repo, base, {**base, SERVICE: CONSTANT.replace("ITEMS = 3", "ITEMS = 5")}
    )
    change = by_kind(workspace.stored_report(), "source_modified").change_id
    tasks = planned(workspace, "post_digest", "post_job")
    # The digest flow gets to the function that reads the constant in fewer calls.
    assert listed(workspace, "closest_flow") == {"post_digest": [change]}
    reading = src(SERVICE, 12, "ITEMS")
    context = workspace.context(tasks["post_job"])
    job = {
        "name": "post_job",
        "steps": [
            {
                "key": "recv",
                "name": "收到任务请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 14, '@router.post("/jobs")', 15)],
            },
            {
                "key": "run",
                "name": "执行任务",
                "kind": "result",
                "evidence": [src(API, 16, "run_job(user)")],
            },
            {
                "key": "items",
                "name": "摘要包含最近的条目",
                "kind": "action",
                "evidence": [reading],
            },
        ],
        "edges": [
            {"source": "recv", "target": "run", "relation": "sequence"},
            {"source": "run", "target": "items", "relation": "call"},
        ],
    }
    assert workspace.submit(tasks["post_job"], job)["status"] == "accepted"
    # The job flow now has a step on the code that reads it. The digest flow is no
    # longer asked to expand anything for it, and is told which flow carries it.
    assert workspace.context(tasks["post_digest"])["change"] == {
        "placed": [],
        "closest_to": [],
        "expand": [],
        "on_other_flows": [{"flow": "post_job", "changes": [change]}],
    }
    assert listed(workspace, "closest_flow") == {}
    # A step of its own on the same code puts the change on it as well; the plan's order
    # decides which flow shows it first.
    digest = digest_flow(workspace, tasks["post_digest"], expanded=False)
    digest["steps"].append(
        {"key": "items", "name": "摘要包含最近的条目", "kind": "action", "evidence": [reading]}
    )
    digest["edges"].append({"source": "send", "target": "items", "relation": "call"})
    assert workspace.submit(tasks["post_digest"], digest)["status"] == "accepted"
    item = by_kind(workspace.stored_report(), "source_modified")
    flows = {flow.flow_id: flow.name for flow in workspace.stored_map().flows}
    assert flows[item.projection.flow_id] == "post_digest"
    assert [flows[target.flow_id] for target in item.other_projections] == ["post_job"]

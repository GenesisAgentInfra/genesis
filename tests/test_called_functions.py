"""Into a called function and back out, and leaving out what needed no entry."""

import copy

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from test_git_snapshot import commit, write
from test_map_loop import codes, src

API = "quote/api.py"
PRICING = "quote/pricing.py"
FILES = {
    "quote/__init__.py": "",
    API: """import logging

from fastapi import APIRouter

from .pricing import price_order
from .store import save_quote

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/quotes")
def create_quote(order):
    logger.info("quote requested")
    quote = price_order(order)
    save_quote(quote)
    return {"total": quote["total"]}
""",
    PRICING: """from .store import load_discount


def price_order(order):
    total = sum(order["lines"])
    if order.get("coupon"):
        total -= load_discount(order["coupon"])
        return {"total": total, "discounted": True}
    return {"total": total, "discounted": False}
""",
    "quote/store.py": "def load_discount(coupon):\n    return 5\n\n\n"
    "def save_quote(quote):\n    return None\n",
}


@pytest.fixture
def quoting(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def quote_flow(workspace, task_id):
    """The pricing function expanded: a `call` edge in, and its ends lead back to the caller."""
    context = workspace.context(task_id)
    return {
        "name": "报价",
        "summary": "为订单计价，有优惠券时先减去优惠，然后保存报价。",
        "steps": [
            {
                "key": "recv",
                "name": "收到报价请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 12, '@router.post("/quotes")', 13)],
            },
            {
                "key": "price",
                "name": "为订单计价",
                "kind": "action",
                "evidence": [src(API, 15, "price_order(order)")],
            },
            {
                "key": "coupon",
                "name": "订单是否带优惠券",
                "kind": "decision",
                "evidence": [src(PRICING, 6, 'order.get("coupon")')],
            },
            {
                "key": "discount",
                "name": "减去优惠金额",
                "kind": "action",
                "evidence": [src(PRICING, 7, "load_discount(")],
            },
            {
                "key": "save",
                "name": "保存报价",
                "kind": "action",
                "evidence": [src(API, 16, "save_quote(quote)")],
            },
            {
                "key": "done",
                "name": "返回报价金额",
                "kind": "result",
                "evidence": [src(API, 17, "return")],
            },
        ],
        "edges": [
            {"source": "recv", "target": "price", "relation": "sequence"},
            {"source": "price", "target": "coupon", "relation": "call"},
            {"source": "coupon", "target": "discount", "relation": "branch", "branch": "true"},
            # Out of the function again: on to what the caller does next.
            {"source": "discount", "target": "save", "relation": "sequence"},
            {
                "source": "coupon",
                "target": "save",
                "relation": "branch",
                "branch": "false",
                "label": "没有优惠券",
            },
            {"source": "save", "target": "done", "relation": "sequence"},
        ],
    }


def log_call(workspace, task_id):
    """A fact of the entry function that nothing obliges a flow to mention."""
    listed = workspace.context(task_id)["other_facts"]
    return next(fact for fact in listed if fact["text"].startswith("logger.info"))


def test_a_called_function_is_entered_by_a_call_edge_and_left_for_the_callers_next_step(quoting):
    workspace, task = quoting
    result = workspace.submit(task, quote_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    # The returns inside the called function are not steps, and nothing asks for them.
    assert result["accounting"]["unaccounted"] == 0
    flow = workspace.stored_map().flows[0]
    assert {(edge.relation, edge.support, edge.resolution) for edge in flow.edges} == {
        ("sequence", "static_fact", "resolved"),
        ("call", "static_fact", "resolved"),
        ("branch", "static_fact", "resolved"),
    }


def test_the_way_back_must_lead_to_code_after_the_call(quoting):
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    flow["edges"].append({"source": "discount", "target": "recv", "relation": "sequence"})
    assert codes(workspace.submit(task, flow)) == [("edges[6]", "edge_not_supported")]


def test_leaving_out_a_fact_that_needs_no_entry_is_accepted_and_said(quoting):
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    logged = log_call(workspace, task)
    flow["omitted"] = [{"anchor": logged["fingerprint"], "reason": "logging"}]
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    # Nothing had to account for it, so it is not counted or stored as an omission.
    assert result["accounting"]["omitted"] == 0
    assert workspace.stored_map().flows[0].omitted == ()
    assert [(item["path"], item["anchor"]) for item in result["ignored"]] == [
        ("omitted[0]", logged["fingerprint"])
    ]
    assert "needs no entry" in result["ignored"][0]["message"]
    # A submission that leaves out nothing unneeded says nothing about it.
    assert "ignored" not in workspace.submit(task, quote_flow(workspace, task))


def test_leaving_out_a_fingerprint_no_fact_has_is_still_refused(quoting):
    workspace, task = quoting
    flow = copy.deepcopy(quote_flow(workspace, task))
    flow["omitted"] = [{"anchor": "fp_" + "0" * 24, "reason": "logging"}]
    result = workspace.submit(task, flow)
    assert codes(result) == [("omitted[0].anchor", "unknown_anchor")]


SCAN = "scan/api.py"
CHECKS = "scan/checks.py"
SCAN_FILES = {
    "scan/__init__.py": "",
    SCAN: """from fastapi import APIRouter

from .checks import run_checks
from .store import publish

router = APIRouter()


@router.post("/scans")
def start_scan(skill):
    report = run_checks(skill)
    publish(report)
    return {"ok": report["ok"]}
""",
    # The work is three calls down, behind two functions that only pass it on.
    CHECKS: """from .store import load_rules


def run_checks(skill):
    return _guarded(skill)


def _guarded(skill):
    return verify(skill)


def verify(skill):
    rules = load_rules(skill)
    if not rules:
        return {"ok": True, "findings": []}
    return {"ok": False, "findings": rules}
""",
    "scan/store.py": "def load_rules(skill):\n    return []\n\n\n"
    "def publish(report):\n    return None\n",
}


@pytest.fixture
def scanning(source_repo):
    for path, text in SCAN_FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def scan_flow(workspace, task_id):
    """Steps in the entry and three calls down, none in the two functions between."""
    context = workspace.context(task_id)
    return {
        "name": "扫描技能",
        "steps": [
            {
                "key": "recv",
                "name": "收到扫描请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(SCAN, 9, '@router.post("/scans")', 10)],
            },
            {
                "key": "check",
                "name": "运行检查",
                "kind": "action",
                "evidence": [src(SCAN, 11, "run_checks(skill)")],
            },
            {
                "key": "rules",
                "name": "读取这个技能适用的规则",
                "kind": "action",
                "evidence": [src(CHECKS, 13, "load_rules(skill)")],
            },
            {
                "key": "empty",
                "name": "是否没有适用的规则",
                "kind": "decision",
                "evidence": [src(CHECKS, 14, "if not rules")],
            },
            {
                "key": "publish",
                "name": "发布报告",
                "kind": "action",
                "evidence": [src(SCAN, 12, "publish(report)")],
            },
            {
                "key": "done",
                "name": "返回是否通过",
                "kind": "result",
                "evidence": [src(SCAN, 13, "return")],
            },
        ],
        "edges": [
            {"source": "recv", "target": "check", "relation": "sequence"},
            {"source": "check", "target": "rules", "relation": "call"},
            {"source": "rules", "target": "empty", "relation": "sequence"},
            {
                "source": "empty",
                "target": "publish",
                "relation": "branch",
                "branch": "true",
                "label": "没有规则，直接通过",
            },
            {
                "source": "empty",
                "target": "publish",
                "relation": "branch",
                "branch": "false",
                "label": "带着发现返回",
            },
            {"source": "publish", "target": "done", "relation": "sequence"},
        ],
    }


def test_the_way_in_and_out_may_pass_functions_that_have_no_step(scanning):
    workspace, task = scanning
    result = workspace.submit(task, scan_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    flow = workspace.stored_map().flows[0]
    # Checked against the calls, not taken on trust: none of these is a candidate.
    assert {(edge.relation, edge.support, edge.resolution) for edge in flow.edges} == {
        ("sequence", "static_fact", "resolved"),
        ("call", "static_fact", "resolved"),
        ("branch", "static_fact", "resolved"),
    }
    assert [edge.condition.label for edge in flow.edges if edge.condition] == [
        "没有规则，直接通过",
        "带着发现返回",
    ]


def test_a_way_out_through_several_functions_still_has_to_follow_the_call(scanning):
    workspace, task = scanning
    flow = scan_flow(workspace, task)
    # Back to before the call that led down there.
    flow["edges"].append({"source": "rules", "target": "recv", "relation": "sequence"})
    # And into a function the publishing step never gets to.
    flow["edges"].append({"source": "publish", "target": "rules", "relation": "call"})
    assert codes(workspace.submit(task, flow)) == [
        ("edges[6]", "edge_not_supported"),
        ("edges[7]", "edge_not_supported"),
    ]


LABEL = "label/api.py"
LABEL_FILES = {
    "label/__init__.py": "",
    LABEL: """from fastapi import APIRouter

from .codes import build_code
from .i18n import translate

router = APIRouter()


@router.post("/labels")
def make_label(order):
    code = build_code(order)
    return {
        "code": code,
        "title": translate("label.title"),
    }
""",
    "label/codes.py": "def build_code(order):\n    return order['id']\n",
    # Big enough inside that a step standing for it has to say why one step is enough.
    "label/i18n.py": "def translate(key):\n"
    + "".join(f"    if key == 'k{index}':\n        return 'v{index}'\n" for index in range(5))
    + "    return key\n",
}


@pytest.fixture
def labelling(source_repo):
    for path, text in LABEL_FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    return workspace, workspace.save_plan(None)["tasks"][0]["task_id"]


def label_flow(workspace, task_id):
    """The last step cites its whole `return`, which has a helper call on a later line."""
    context = workspace.context(task_id)
    helper = next(unit for unit in context["accountable"] if unit["text"].startswith("translate"))
    return {
        "name": "生成标签",
        "steps": [
            {
                "key": "recv",
                "name": "收到生成标签的请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(LABEL, 9, '@router.post("/labels")', 10)],
            },
            {
                "key": "code",
                "name": "生成标签编码",
                "kind": "action",
                "evidence": [src(LABEL, 11, "build_code(order)")],
            },
            {
                "key": "done",
                "name": "返回标签",
                "kind": "result",
                "evidence": [src(LABEL, 12, "return {", 15)],
            },
        ],
        "edges": [
            {"source": "recv", "target": "code", "relation": "sequence"},
            {"source": "code", "target": "done", "relation": "sequence"},
        ],
        "omitted": [
            {"anchor": helper["fingerprint"], "reason": "instrumentation", "note": "界面文字翻译"}
        ],
    }, helper["fingerprint"]


def test_a_call_a_cited_range_picks_up_gives_way_to_its_omission(labelling):
    workspace, task = labelling
    flow, helper = label_flow(workspace, task)
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    assert result["accounting"] == {
        "accountable": 3,
        "covered": 2,
        "omitted": 1,
        "unaccounted": 0,
        "truncated": False,
    }
    done = next(step for step in workspace.stored_map().flows[0].steps if step.name == "返回标签")
    # The step is the `return`. It does not stand for the helper the submission leaves out.
    assert helper not in done.anchors and not done.unexpanded


def test_naming_an_anchor_and_leaving_it_out_is_still_a_contradiction(labelling):
    workspace, task = labelling
    flow, helper = label_flow(workspace, task)
    flow["steps"][2]["anchors"] = [helper]
    assert codes(workspace.submit(task, flow)) == [
        ("omitted[0].anchor", "omitted_but_used"),
        ("steps[2].unexpanded_reason", "unexpanded_reason_required"),
    ]


def test_without_the_omission_the_step_stands_for_what_its_range_holds(labelling):
    workspace, task = labelling
    flow, _ = label_flow(workspace, task)
    flow["omitted"] = []
    assert codes(workspace.submit(task, flow)) == [
        ("steps[2].unexpanded_reason", "unexpanded_reason_required")
    ]


def test_functions_too_big_to_fold_without_a_reason_are_named_up_front(labelling, quoting):
    workspace, task = labelling
    # Known before anything is submitted, not from the refusal of a step that folds it.
    context = workspace.context(task)
    assert context["large_callees"] == ["label/i18n.py#translate"]
    assert workspace.query_symbol("label/api.py#make_label")["large_callees"] == [
        "label/i18n.py#translate"
    ]
    assert workspace.query_symbol("label/codes.py#build_code")["large_callees"] == []


def test_a_step_on_a_line_that_only_calls_a_built_in_rests_on_that_call(quoting):
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    # `total = sum(order["lines"])`: the only fact on the line is a call to a built-in.
    flow["steps"].append(
        {
            "key": "total",
            "name": "合计订单金额",
            "kind": "action",
            "evidence": [src(PRICING, 5, "sum(")],
        }
    )
    flow["edges"][1] = {"source": "price", "target": "total", "relation": "call"}
    flow["edges"].append({"source": "total", "target": "coupon", "relation": "sequence"})
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    stored = workspace.stored_map().flows[0]
    total = next(step for step in stored.steps if step.name == "合计订单金额")
    summed = workspace.by_fingerprint[total.anchors[0]]
    assert (len(total.anchors), summed.boundary, summed.text) == (
        1,
        "builtin",
        'sum(order["lines"])',
    )
    # It is a place in the code like any other: the edges around it are checked.
    assert {edge.support for edge in stored.edges} == {"static_fact"}


def test_a_built_in_call_beside_another_fact_is_still_left_out_of_the_anchors(quoting):
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    # `return {"total": quote["total"]}` shares its range with nothing else here, while
    # the pricing step below cites a line with a real call next to `sum(...)`.
    flow["steps"][2]["evidence"] = [src(PRICING, 5, "sum(", 7)]
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    coupon = next(step for step in workspace.stored_map().flows[0].steps if step.kind == "decision")
    kinds = {workspace.by_fingerprint[anchor].boundary for anchor in coupon.anchors}
    assert "builtin" not in kinds


def test_a_query_says_what_expanding_the_function_adds(quoting, labelling):
    workspace, _ = quoting
    # Before any step is anchored inside it: what such a step would make accountable.
    adds = workspace.query_symbol("quote/pricing.py#price_order")["expands_to"]
    assert [(unit["unit"], unit["text"].split("(")[0]) for unit in adds] == [
        ("fact", "order.get"),
        ("function", "load_discount"),
    ]
    assert adds[0]["kind"] == "condition" and adds[1]["function"] == [
        "quote/store.py#load_discount"
    ]
    # A function that calls nothing and decides nothing adds nothing.
    assert workspace.query_symbol("quote/store.py#load_discount")["expands_to"] == []
    workspace, _ = labelling
    adds = workspace.query_symbol("label/api.py#make_label")["expands_to"]
    assert [unit["function"][0].split("#")[-1] for unit in adds] == ["build_code", "translate"]
    assert adds[1]["inside"]["conditions"] == 5

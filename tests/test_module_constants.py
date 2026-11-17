"""A change to a module-level constant lands on the code that reads the constant."""

import pytest
from genesis_ci.business_map.changes import NEAREST_REMOVED
from test_change_analysis import two_commits
from test_map_loop import entry, src

RULES = "shop/rules.py"
API = "shop/api.py"
BASE = {
    "shop/__init__.py": "",
    RULES: """RESERVED = frozenset({
    "id",
    "name",
})
PROMPT = \"\"\"You name products.
Never use the word id.
Keep it short.
\"\"\"
LIMIT = 10
""",
    API: """from fastapi import APIRouter

from .rules import (
    LIMIT,
    PROMPT,
    RESERVED,
)

router = APIRouter()


@router.post("/names")
def suggest_name(product):
    if product["name"] in RESERVED:
        return {"error": "reserved"}
    text = f"{PROMPT} Product: {product['name']}"
    return {"prompt": text[:LIMIT]}
""",
}
# One more reserved word inside the set, and one sentence inside the prompt: neither
# changed line names the constant it belongs to, and both are read in another file.
HEAD = {
    **BASE,
    RULES: BASE[RULES]
    .replace('    "name",\n', '    "name",\n    "graph_id",\n')
    .replace("Never use the word id.", "Never use the words id or graph_id."),
}


def changed(report, word):
    found = [
        item
        for item in report.changes
        if item.symbol_id.endswith("rules.py#<module>") and word in (item.after or item.before).text
    ]
    assert len(found) == 1, [
        (item.kind.value, (item.after or item.before).text) for item in report.changes
    ]
    return found[0]


def name_flow(workspace, task_id):
    context = workspace.context(task_id)
    return {
        "name": "给商品起名",
        "steps": [
            {
                "key": "recv",
                "name": "收到起名请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(API, 12, '@router.post("/names")', 13)],
            },
            {
                "key": "reserved",
                "name": "商品名是否是保留字",
                "kind": "decision",
                "evidence": [src(API, 14, "in RESERVED")],
            },
            {
                "key": "refuse",
                "name": "拒绝保留字",
                "kind": "result",
                "evidence": [src(API, 15, '"reserved"')],
            },
            {
                "key": "done",
                "name": "拼出提示词并返回",
                "kind": "result",
                "evidence": [src(API, 16, "PROMPT", 17)],
            },
        ],
        "edges": [
            {"source": "recv", "target": "reserved", "relation": "sequence"},
            {"source": "reserved", "target": "refuse", "relation": "branch", "branch": "true"},
            {"source": "reserved", "target": "done", "relation": "branch", "branch": "false"},
        ],
    }


def test_a_change_inside_a_constant_lands_on_the_code_that_reads_it(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    report = workspace.stored_report()
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    # The set is read by a condition in another file, which imports its name.
    word = changed(report, '"graph_id"')
    assert word.projection.status == "projected"
    assert names[word.projection.step_id].startswith('product["name"] in RESERVED')
    assert "refers to `RESERVED`" in word.projection.reason
    # The prompt is read by a plain assignment, which is no fact. Before anyone has
    # described the flow, the change sits on the function that reads it.
    sentence = changed(report, "graph_id.")
    assert sentence.projection.status == "projected"
    assert "reads `PROMPT`" in sentence.projection.reason
    assert report.possibly_affected == ()


def test_a_step_that_cites_the_reading_line_takes_the_change(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    result = workspace.submit(task, name_flow(workspace, task))
    assert result["status"] == "accepted", result.get("errors")
    report = workspace.stored_report()
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    sentence = changed(report, "graph_id.")
    assert names[sentence.projection.step_id] == "拼出提示词并返回"
    assert "refers to `PROMPT`" in sentence.projection.reason
    assert names[changed(report, '"graph_id"').projection.step_id] == "商品名是否是保留字"


def test_a_constant_nothing_reads_stays_off_the_map(source_repo):
    head = {
        **BASE,
        RULES: BASE[RULES].replace("LIMIT = 10", "LIMIT = 10\nUNUSED = frozenset({\n    1,\n})"),
    }
    later = {**head, RULES: head[RULES].replace("    1,\n", "    1,\n    2,\n")}
    workspace, _ = two_commits(source_repo, head, later)
    item = changed(workspace.stored_report(), "2")
    assert item.projection.status == "unassigned"
    assert item.projection.reason.startswith("No entry on the map reaches this code")


TRIM = "shop/trim.py"
# Names assigned inside a function: one read by a condition, one by a plain assignment,
# one set in the middle of a value that runs over several lines.
LOCAL = {
    "shop/__init__.py": "",
    TRIM: """from fastapi import APIRouter

router = APIRouter()


@router.post("/catalog")
def tidy_catalog(catalog):
    max_items = 10
    labels = {
        "empty": "none",
        "full": "all",
    }
    suffix = " (new)"
    for item in catalog["items"]:
        item["name"] = item["name"].strip()
    if len(catalog["items"]) > max_items:
        return {"error": labels["full"]}
    title = catalog["title"] + suffix
    return {"title": title, "items": catalog["items"]}


@router.post("/count")
def count_catalog(catalog):
    max_items = 3
    return len(catalog["items"]) > max_items
""",
}
LOCAL_HEAD = {
    **LOCAL,
    TRIM: LOCAL[TRIM]
    .replace("max_items = 10", "max_items = 20")
    .replace('" (new)"', '" (updated)"')
    .replace('"full": "all",', '"full": "too many",'),
}


def local_change(report, word):
    found = [
        item
        for item in report.changes
        if item.symbol_id.endswith("#tidy_catalog") and word in (item.after or item.before).text
    ]
    assert len(found) == 1, [
        (item.kind.value, item.symbol_id, (item.after or item.before).text)
        for item in report.changes
    ]
    return found[0]


def test_a_name_assigned_inside_a_function_lands_on_the_code_that_reads_it(source_repo):
    workspace, _ = two_commits(source_repo, LOCAL, LOCAL_HEAD)
    report = workspace.stored_report()
    stored = workspace.stored_map()
    names = {step.step_id: step.name for flow in stored.flows for step in flow.steps}
    tidy = next(
        flow for flow in stored.flows if flow.entries[0].symbol_id.endswith("#tidy_catalog")
    )
    # Not the nearest step by position, which is the way in: the condition that reads it.
    limit = local_change(report, "max_items = 20")
    assert names[limit.projection.step_id].startswith('len(catalog["items"]) > max_items')
    assert "refers to `max_items`" in limit.projection.reason
    # The other function has a name spelled the same; it is another name.
    assert limit.projection.flow_id == tidy.flow_id and limit.other_projections == ()
    # Read by a plain assignment, which is no fact: the step nearest to that line.
    suffix = local_change(report, "(updated)")
    assert "reads `suffix`" in suffix.projection.reason
    assert names[suffix.projection.step_id].startswith('len(catalog["items"]) > max_items')
    # The changed line does not show the name it belongs to; the assignment around it does.
    label = local_change(report, "too many")
    assert "refers to `labels`" in label.projection.reason
    assert 'labels["full"]' in names[label.projection.step_id]


def test_a_step_that_cites_the_line_reading_a_local_name_takes_the_change(source_repo):
    workspace, _ = two_commits(source_repo, LOCAL, LOCAL_HEAD)
    wanted = entry(workspace, "#tidy_catalog").entry_id
    task = next(
        item["task_id"]
        for item in workspace.save_plan(None)["tasks"]
        if wanted in item["entry_ids"]
    )
    context = workspace.context(task)
    flow = {
        "name": "整理商品目录",
        "steps": [
            {
                "key": "recv",
                "name": "收到整理请求",
                "kind": "trigger",
                "anchors": [context["entries"][0]["anchor"]],
                "evidence": [src(TRIM, 6, '@router.post("/catalog")', 7)],
            },
            {
                "key": "strip",
                "name": "逐个去掉名称两端的空白",
                "kind": "action",
                "evidence": [src(TRIM, 14, "for item in", 15)],
            },
            {
                "key": "many",
                "name": "条目是否超过上限",
                "kind": "decision",
                "evidence": [src(TRIM, 16, "> max_items")],
            },
            {
                "key": "refuse",
                "name": "告知条目太多",
                "kind": "result",
                "evidence": [src(TRIM, 17, 'labels["full"]')],
            },
            {
                "key": "done",
                "name": "补上标题后缀并返回",
                "kind": "result",
                "evidence": [src(TRIM, 18, "+ suffix", 19)],
            },
        ],
        "edges": [
            {"source": "recv", "target": "strip", "relation": "sequence"},
            {"source": "strip", "target": "many", "relation": "sequence"},
            {"source": "many", "target": "refuse", "relation": "branch", "branch": "true"},
            {"source": "many", "target": "done", "relation": "branch", "branch": "false"},
        ],
    }
    result = workspace.submit(task, flow)
    assert result["status"] == "accepted", result.get("errors")
    report = workspace.stored_report()
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    assert names[local_change(report, "max_items = 20").projection.step_id] == "条目是否超过上限"
    suffix = local_change(report, "(updated)")
    assert names[suffix.projection.step_id] == "补上标题后缀并返回"
    assert "refers to `suffix`" in suffix.projection.reason
    assert names[local_change(report, "too many").projection.step_id] == "告知条目太多"


def test_a_removed_assignment_is_not_followed_to_code_that_reads_another_definition(source_repo):
    # The module has a name spelled like the function's own. Taking the function's
    # assignment away leaves the line that read it reading the module's.
    shadowed = LOCAL[TRIM].replace(
        "router = APIRouter()\n", 'router = APIRouter()\nsuffix = " (old)"\n'
    )
    removed = shadowed.replace('    suffix = " (new)"\n', "")
    workspace, _ = two_commits(source_repo, {**LOCAL, TRIM: shadowed}, {**LOCAL, TRIM: removed})
    (item,) = [
        change
        for change in workspace.stored_report().changes
        if change.symbol_id.endswith("#tidy_catalog")
    ]
    assert item.kind == "source_removed" and item.after is None
    assert item.projection.reason == NEAREST_REMOVED


PRICES = "shop/prices.py"
ORDERS = "shop/orders.py"
SHIPPING = {
    "shop/__init__.py": "",
    PRICES: "FEE = 5\n",
    ORDERS: """from fastapi import APIRouter

from .prices import FEE

router = APIRouter()


@router.post("/orders")
def create_order(order):
    if order["total"] < FEE:
        return {"error": "too small"}
    return {"ok": True}
""",
    "tests/test_orders.py": """from shop.orders import create_order


def test_small_order_is_refused():
    assert create_order({"total": 1}) == {"error": "too small"}
""",
}
# One edit sets three constants; a new route reads two of them, and its test asserts nothing.
SHIPPING_HEAD = {
    **SHIPPING,
    PRICES: 'FEE = 7\nFREE_FROM = 100\nLABELS = {\n    "free": "free shipping",\n'
    '    "paid": "standard",\n}\n',
    ORDERS: SHIPPING[ORDERS].replace("import FEE", "import FEE, FREE_FROM, LABELS")
    + """

@router.post("/quote")
def quote(order):
    if order["total"] >= FREE_FROM:
        return {"shipping": LABELS["free"]}
    return {"shipping": "paid"}
""",
    "tests/test_orders.py": SHIPPING["tests/test_orders.py"].replace(
        "import create_order", "import create_order, quote"
    )
    + '\n\ndef test_quote_runs():\n    quote({"total": 1})\n',
}


def test_constants_changed_in_one_edit_each_land_on_their_own_reader(source_repo):
    workspace, _ = two_commits(source_repo, SHIPPING, SHIPPING_HEAD)
    report = workspace.stored_report()
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    found = {
        (item.after or item.before).text.split(" = ")[0]: item
        for item in report.changes
        if item.symbol_id == PRICES + "#<module>"
    }
    assert sorted(found) == ["FEE", "FREE_FROM", "LABELS"]
    assert [found[name].kind.value for name in ("FEE", "FREE_FROM", "LABELS")] == [
        "source_modified",
        "source_added",
        "source_added",
    ]
    readers = {"FEE": "< FEE", "FREE_FROM": ">= FREE_FROM", "LABELS": 'LABELS["free"]'}
    tests = {
        "FEE": ["test_small_order_is_refused"],
        "FREE_FROM": ["test_quote_runs"],
        "LABELS": ["test_quote_runs"],
    }
    for name, item in found.items():
        # Each lands on the code that reads it, and carries the tests of that code alone.
        assert readers[name] in names[item.projection.step_id], (name, item.projection)
        assert f"refers to `{name}`" in item.projection.reason
        assert [case.test_id.rsplit("#", 1)[-1] for case in item.tests.items] == tests[name]
    # No flow is left merely "possibly affected" by a constant it reads on a step.
    assert report.possibly_affected == ()


def test_a_function_whose_name_starts_like_the_holder_is_not_inside_it(source_repo):
    # `tidy_catalog_count` is a function of its own, not one written inside `tidy_catalog`.
    renamed = {TRIM: LOCAL[TRIM].replace("def count_catalog", "def tidy_catalog_count")}
    test = (
        "from shop.trim import tidy_catalog_count\n\n\ndef test_count_only():\n"
        "    assert tidy_catalog_count({'items': []}) is False\n"
    )
    base = {**LOCAL, **renamed, "tests/test_count.py": test}
    head = {
        **LOCAL_HEAD,
        TRIM: LOCAL_HEAD[TRIM].replace("def count_catalog", "def tidy_catalog_count"),
    }
    workspace, _ = two_commits(source_repo, base, {**head, "tests/test_count.py": test})
    limit = local_change(workspace.stored_report(), "max_items = 20")
    assert limit.other_projections == ()
    assert [case.test_id for case in limit.tests.items] == []


REASSIGNED = """from fastapi import APIRouter

router = APIRouter()


def save(order):
    return order


def notify(order):
    return order


@router.post("/orders")
def place_order(order):
    status = order["status"]
    if status == "draft":
        return {"error": "draft"}
    if order["status"] == "held":
        return {"error": "held"}
    save(order)
    notify(order)
    status = "saved"
    return {"status": status}
"""


def test_a_local_name_lands_on_code_after_it_and_not_on_a_key_spelled_like_it(source_repo):
    files = {"shop/__init__.py": "", "shop/orders.py": REASSIGNED}
    head = {**files, "shop/orders.py": REASSIGNED.replace('"saved"', '"created"')}
    workspace, _ = two_commits(source_repo, files, head)
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    (item,) = [
        change
        for change in workspace.stored_report().changes
        if change.symbol_id.endswith("#place_order")
    ]
    # The earlier condition reads the first value, and the second only has the word as a
    # key: the code that reads this value is the return after it.
    assert names[item.projection.step_id].startswith("return")
    assert "refers to `status`" in item.projection.reason


SHADOWED = """from fastapi import APIRouter

router = APIRouter()


def notify(order):
    return order


@router.post("/orders")
def place_order(order):
    item = "default"
    status = "new"
    notify(order)
    order["items"].sort(key=lambda status: status["rank"])
    return {"items": [item for item in order["items"]]}
"""


@pytest.mark.parametrize("old, new", [('"default"', '"fallback"'), ('"new"', '"fresh"')])
def test_a_name_bound_again_in_a_lambda_or_comprehension_is_not_a_reader(source_repo, old, new):
    files = {"shop/__init__.py": "", "shop/orders.py": SHADOWED}
    workspace, _ = two_commits(
        source_repo, files, {**files, "shop/orders.py": SHADOWED.replace(old, new)}
    )
    (item,) = [
        change
        for change in workspace.stored_report().changes
        if change.symbol_id.endswith("#place_order")
    ]
    # The lambda's parameter and the comprehension's variable are names of their own.
    assert "refers to" not in item.projection.reason and "reads" not in item.projection.reason


EARLY = """from fastapi import APIRouter

router = APIRouter()


def save(order):
    return order


@router.post("/orders")
def total_of(order):
    total = order["total"]
    save(order)
    if order["vip"]:
        total = total * 0.8
        return {"vip": total}
    if total > 100:
        return {"big": True}
    return {"total": total}
"""


def test_a_value_set_in_a_branch_that_returns_is_not_read_after_it(source_repo):
    files = {"shop/__init__.py": "", "shop/orders.py": EARLY}
    workspace, _ = two_commits(
        source_repo, files, {**files, "shop/orders.py": EARLY.replace("0.8", "0.7")}
    )
    names = {
        step.step_id: step.name for flow in workspace.stored_map().flows for step in flow.steps
    }
    (item,) = [
        change
        for change in workspace.stored_report().changes
        if change.symbol_id.endswith("#total_of")
    ]
    # The branch returns, so `total > 100` never sees this value; the return inside does.
    assert "total > 100" not in names[item.projection.step_id]


def test_a_local_name_in_a_file_with_a_byte_order_mark_is_placed_as_usual(source_repo):
    marked = {TRIM: "\ufeff" + LOCAL[TRIM]}
    workspace, _ = two_commits(
        source_repo,
        {**LOCAL, **marked},
        {**LOCAL_HEAD, TRIM: "\ufeff" + LOCAL_HEAD[TRIM]},
    )
    limit = local_change(workspace.stored_report(), "max_items = 20")
    assert "refers to `max_items`" in limit.projection.reason

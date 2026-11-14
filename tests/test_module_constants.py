"""A change to a module-level constant lands on the code that reads the constant."""

from test_change_analysis import two_commits
from test_map_loop import src

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
    assert "not reachable" in item.projection.reason

"""A trigger step cites how its flow is entered; those lines are evidence, not anchors."""

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from genesis_contracts.map_tasks import MapPlan
from test_git_snapshot import commit, write
from test_map_loop import src

AGENT = "desk/agent.py"
CLI = "desk/cli.py"
WEB = "desk/web.py"
LEDGER = "desk/ledger.py"
FILES = {
    "desk/__init__.py": "",
    AGENT: """from desk import intents


class Agent:
    def handle(self, message, customer):
        intent = intents.classify(message)
        if intent == "refund":
            return self._refund(customer)
        if intent == "status":
            return self._status(customer)
        return self._escalate(message)

    def _refund(self, customer):
        if not customer:
            return "no account"
        return "refunded"

    def _status(self, customer):
        return "shipped"

    def _escalate(self, message):
        return "ticket"
""",
    "desk/intents.py": """def classify(message):
    if "refund" in message:
        return "refund"
    return "other"
""",
    CLI: """import argparse


def cmd_ask(args):
    if not args.customer:
        return 2
    return 0


def cmd_ping(args):
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="desk")
    sub = parser.add_subparsers()
    ask = sub.add_parser("ask")
    ask.set_defaults(func=cmd_ask)
    sub.add_parser("ping").set_defaults(func=cmd_ping)
    return parser
""",
    WEB: """from flask import Flask


def create_app(config=None):
    app = Flask(__name__)
    if config:
        app.config.update(config)

    @app.route("/ping")
    def ping():
        if not config:
            return "pong"
        return "configured"

    return app
""",
    LEDGER: """def reconcile(batch):
    if not batch:
        return 0
    total = add_up(batch)
    return total


def add_up(batch):
    return sum(batch)
""",
}
REFUND = "desk/agent.py#Agent._refund"
# The refund handler, proposed with the dispatcher lines in handle() that call it.
PROPOSAL = {
    "symbol_id": REFUND,
    "kind": "handler",
    "reason": "handle() runs it when the message is a refund request.",
    "evidence": [src(AGENT, 7, 'if intent == "refund":', 8)],
}


@pytest.fixture
def desk(source_repo):
    for path, text in FILES.items():
        write(source_repo, path, text)
    commit(source_repo)
    return Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])


def plan(workspace, symbol_id, proposal=None):
    """One flow for the entry of `symbol_id`, proposed in a plan of its own when asked."""
    if proposal is not None:
        workspace.save_plan(MapPlan.model_validate({"proposed_entries": [proposal]}))
    entry = next(item for item in workspace.entries().values() if item.symbol_id == symbol_id)
    flow = {"key": "f", "name": "流程", "entry_ids": [entry.entry_id]}
    return workspace.save_plan(MapPlan.model_validate({"flows": [flow]}))["tasks"][0]["task_id"]


def decided(trigger, path, decision, yes, no):
    """A trigger, one decision and a result on each branch: (line, quote) for each step."""
    steps = [
        ("check", "decision", decision),
        ("yes", "result", yes),
        ("no", "result", no),
    ]
    return {
        "name": "流程",
        "steps": [
            {"key": "recv", "name": "收到请求", "kind": "trigger", **trigger},
            *(
                {"key": key, "name": key, "kind": kind, "evidence": [src(path, *at)]}
                for key, kind, at in steps
            ),
        ],
        "edges": [
            {"source": "recv", "target": "check", "relation": "sequence"},
            {"source": "check", "target": "yes", "relation": "branch", "branch": "true"},
            {"source": "check", "target": "no", "relation": "branch", "branch": "false"},
        ],
    }


SHAPES = {
    # Where the entry's evidence lies: the branch of a dispatcher in handle(), a
    # registration in build_parser(), and a route decorator that runs in create_app().
    "proposed": (
        REFUND,
        PROPOSAL,
        (AGENT, 7),
        (AGENT, (14, "if not customer:"), (15, 'return "no account"'), (16, 'return "refunded"')),
    ),
    "registered": (
        "desk/cli.py#cmd_ask",
        None,
        (CLI, 18),
        (CLI, (5, "if not args.customer:"), (6, "return 2"), (7, "return 0")),
    ),
    "factory": (
        "desk/web.py#create_app.ping",
        None,
        (WEB, 9),
        (WEB, (11, "if not config:"), (12, 'return "pong"'), (13, 'return "configured"')),
    ),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_lines_that_lead_into_an_entry_do_not_pull_their_function_into_its_flow(desk, shape):
    symbol_id, proposal, (path, line), lines = SHAPES[shape]
    task = plan(desk, symbol_id, proposal)
    entry = desk.context(task)["entries"][0]
    # The context hands out lines outside the entry function as the entry's evidence.
    ref = desk.evidence(entry["evidence_ids"][0])
    assert (ref.path, ref.range.start_line) == (path, line)
    trigger = {"anchors": [entry["anchor"]], "evidence": [{"evidence_id": ref.evidence_id}]}
    result = desk.submit(task, decided(trigger, *lines))
    assert result["status"] == "accepted", result
    # The function around those lines runs before the flow starts: nothing of it is owed.
    assert result["accounting"]["unaccounted"] == 0, result["unaccounted"]
    assert result["accounting"]["accountable"] == 3
    flow = desk.stored_map().flows[0]
    assert flow.steps[0].anchors == (entry["anchor"],)
    # The step still shows the reader how the flow is entered.
    assert flow.steps[0].evidence_ids == (ref.evidence_id,)
    # Citing the definition line instead gives the same flow.
    by_definition = {**trigger, "evidence": [src(path, lines[1][0] - 1, "def ")]}
    again = desk.submit(task, decided(by_definition, *lines))
    assert (again["accounting"], again["steps"]) == (result["accounting"], result["steps"])


def test_a_trigger_that_cites_the_whole_entry_does_not_account_for_it(desk):
    # A root candidate planned as it is: its evidence is the whole function.
    task = plan(desk, "desk/ledger.py#reconcile")
    entry = desk.context(task)["entries"][0]
    ref = desk.evidence(entry["evidence_ids"][0])
    assert (ref.range.start_line, ref.range.end_line) == (1, 5)
    trigger = {"anchors": [entry["anchor"]], "evidence": [{"evidence_id": ref.evidence_id}]}
    data = decided(trigger, LEDGER, (2, "if not batch:"), (3, "return 0"), (5, "return total"))
    data["steps"].pop()
    data["edges"].pop()
    result = desk.submit(task, data)
    assert result["status"] == "accepted", result
    # Adding the batch up and its total were never described, and the map says so.
    owed = sorted(unit["text"] for unit in result["unaccounted"])
    assert owed == ["add_up(batch)", "return total"]
    assert result["analysis_status"] == "partial"


def test_a_step_without_the_entry_anchor_still_takes_the_facts_it_cites(desk):
    # Expanding the caller stays possible, by anchoring a step on its facts on purpose.
    task = plan(desk, REFUND, PROPOSAL)
    anchor = desk.context(task)["entries"][0]["anchor"]
    lines = (
        AGENT,
        (14, "if not customer:"),
        (15, 'return "no account"'),
        (16, 'return "refunded"'),
    )
    data = decided({"anchors": [anchor], "evidence": [src(AGENT, 13, "def _refund")]}, *lines)
    data["steps"].insert(
        1,
        {
            "key": "which",
            "name": "是退款请求吗",
            "kind": "decision",
            "evidence": [src(AGENT, 7, 'if intent == "refund":')],
        },
    )
    data["edges"][0] = {
        "source": "recv",
        "target": "which",
        "relation": "sequence",
        "resolution": "candidate",
        "reason": "handle() checks the intent before it calls the handler.",
    }
    data["edges"].insert(
        1, {"source": "which", "target": "check", "relation": "branch", "branch": "true"}
    )
    result = desk.submit(task, data)
    assert result["status"] == "accepted", result
    assert {unit["symbol_id"] for unit in result["unaccounted"]} == {"desk/agent.py#Agent.handle"}

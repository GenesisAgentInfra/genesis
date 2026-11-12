"""A function handed to another call, or called in a lambda, is followed as a deferred call."""

import pytest
from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.facts import CodeFact, FactKind
from genesis_contracts.models import EvidenceSide, Resolution
from genesis_contracts.snapshot import SnapshotSpec
from pydantic import ValidationError
from test_git_snapshot import commit, write

HEAD = EvidenceSide.head

WORKER = """class Research:
    def run(self, question):
        if not question:
            return None
        return self.answer(question)

    def answer(self, question):
        return question


def notify(result):
    return result


def cleanup():
    return None


class Report:
    pass
"""
API = """import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter

from worker import Report, Research, cleanup, notify

router = APIRouter()
executor = ThreadPoolExecutor()


def retry(operation):
    return operation()


@router.post("/research")
async def research(question, callback=None):
    agent = Research()
    result = await asyncio.to_thread(agent.run, question)
    if result:
        executor.submit(notify, result)
    retry(cleanup)
    thread = threading.Thread(target=lambda: notify(agent.answer(question)), daemon=True)
    thread.start()
    isinstance(result, Report)
    retry(callback)
    sorted([question], key=str.lower)
    return notify(result)
"""


def facts_of(root, files):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    extraction = extract_python(capture_snapshot(root, SnapshotSpec(base=head, head=head)))
    return python_facts(extraction)


@pytest.fixture
def calls(source_repo):
    found = facts_of(source_repo, {"worker.py": WORKER, "api.py": API})
    return {
        (fact.text, fact.deferred): fact
        for fact in found.facts
        if fact.side == HEAD and fact.kind == FactKind.call and fact.symbol_id == "api.py#research"
    }


def test_a_function_passed_as_an_argument_is_a_deferred_call_to_it(calls):
    handed = calls[("agent.run", True)]
    assert (handed.target.status, handed.target.targets) == (
        "candidate",
        ("worker.py#Research.run",),
    )
    assert handed.boundary == "internal" and not handed.awaited
    assert handed.target.reason.startswith("Handed to asyncio.to_thread")
    # It sits at the argument, inside the call that receives it.
    outer = calls[("asyncio.to_thread(agent.run, question)", False)]
    assert handed.range.start_line == outer.range.start_line
    assert outer.range.start_column < handed.range.start_column
    # A helper of the code base receives one the same way as a library does.
    assert calls[("cleanup", True)].target.targets == ("worker.py#cleanup",)
    assert "retry" in calls[("cleanup", True)].target.reason
    # It keeps the branch the receiving call is on.
    submitted = calls[("notify", True)]
    assert submitted.target.targets == ("worker.py#notify",)
    assert [guard.branch for guard in submitted.guards] == ["true"]


def test_only_references_to_functions_of_the_code_base_count(calls):
    texts = {text for text, deferred in calls if deferred}
    # A class, an untyped parameter and a builtin method are not functions to follow.
    assert not {"Report", "callback", "str.lower", "result", "question"} & texts
    # The direct call is still an ordinary call.
    direct = calls[("notify(result)", False)]
    assert (direct.target.status, direct.deferred) == ("resolved", False)


def test_a_call_inside_a_lambda_is_deferred_and_never_resolved(calls):
    inner = calls[("agent.answer(question)", True)]
    assert inner.target.targets == ("worker.py#Research.answer",)
    outer = calls[("notify(agent.answer(question))", True)]
    assert (outer.target.status, outer.target.targets) == ("candidate", ("worker.py#notify",))
    assert "lambda" in outer.target.reason


def test_a_deferred_fact_cannot_claim_a_resolved_target(calls):
    fact = calls[("cleanup", True)]
    with pytest.raises(ValidationError):
        CodeFact.model_validate(
            {
                **fact.model_dump(mode="json"),
                "target": Resolution(status="resolved", targets=fact.target.targets).model_dump(),
            }
        )


def test_a_flow_accounts_for_the_function_it_hands_over(source_repo):
    for path, text in {"worker.py": WORKER, "api.py": API}.items():
        write(source_repo, path, text)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo, head="HEAD")["session_id"])
    task = workspace.save_plan(None)["tasks"][0]["task_id"]
    context = workspace.context(task)
    handed = {
        unit["text"]: unit
        for unit in context["accountable"]
        if unit.get("unit") == "function" and unit.get("deferred")
    }
    assert handed["agent.run"]["function"] == ["worker.py#Research.run"]
    assert handed["agent.run"]["inside"]["conditions"] == 1
    assert "note" in handed["agent.run"]
    assert "worker.py#Research.run" in context["callees"]
    # The function handed over is reached from the entry, so it is not a root of its own.
    roots = {item["symbol_id"] for item in workspace.status()["root_candidates"]}
    assert "worker.py#cleanup" not in roots and "worker.py#notify" not in roots


PASSING = {
    "engine.py": """class Engine:
    def run(self, question):
        return question

    def stop(self):
        return None


class Spare:
    def run(self, question):
        return None
""",
    "app.py": """import asyncio

from engine import Engine, Spare


async def in_background(agent, question, annotated: Spare = None):
    annotated.run(question)
    return await asyncio.to_thread(agent.run, question)


def finish(agent, done):
    done()
    return agent.stop()


class Session:
    def __init__(self, engine, label):
        self.engine = engine
        self.label = label

    def ask(self, question):
        self.label.strip()
        return self.engine.run(question)


def again(node, depth):
    node.run(depth)
    return again(node, depth - 1)


async def handle(question):
    agent = Engine()
    session = Session(agent, "x")
    session.ask(question)
    finish(done=agent.stop, agent=agent)
    again(agent, 3)
    return await in_background(agent, question, Engine())
""",
    "tests/test_app.py": """from app import finish, in_background


class FakeEngine:
    def run(self, question):
        return "fake"

    def stop(self):
        return None


def test_finish():
    assert finish(FakeEngine(), print) is None


async def test_background():
    await in_background(FakeEngine(), "q")
""",
}


def test_an_unannotated_parameter_is_typed_by_what_callers_pass(source_repo):
    found = facts_of(source_repo, PASSING)
    calls = {
        (fact.symbol_id.partition("#")[2], fact.text): fact
        for fact in found.facts
        if fact.side == HEAD and fact.kind == FactKind.call and fact.symbol_id.startswith("app.py")
    }
    # The object handed to the helper is known from the one place that calls it.
    handed = calls[("in_background", "agent.run")]
    assert (handed.deferred, handed.target.targets) == (True, ("engine.py#Engine.run",))
    # A keyword argument is matched by name; a function passed in is followed when called.
    assert calls[("finish", "agent.stop()")].target.targets == ("engine.py#Engine.stop",)
    assert calls[("finish", "done()")].target.targets == ("engine.py#Engine.stop",)
    # Through a constructor the value reaches the attribute it is stored in.
    asked = calls[("Session.ask", "self.engine.run(question)")]
    assert (asked.target.status, asked.target.targets) == ("candidate", ("engine.py#Engine.run",))
    # A string literal is no object to follow, and an annotation wins over the callers.
    assert calls[("Session.ask", "self.label.strip()")].target.status == "unknown"
    assert calls[("in_background", "annotated.run(question)")].target.targets == (
        "engine.py#Spare.run",
    )
    # A function that passes its parameter on to itself still ends.
    assert calls[("again", "node.run(depth)")].target.targets == ("engine.py#Engine.run",)
    # What a test passes is a double: it never becomes a target of product code.
    targets = {target for fact in calls.values() for target in fact.target.targets}
    assert not [target for target in targets if target.startswith("tests/")]

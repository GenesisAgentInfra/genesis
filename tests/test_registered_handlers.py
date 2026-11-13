"""Entries nothing decorates: handler classes listed together, and uncalled functions
that lead to changed code."""

import pytest
from genesis_ci.business_map.skeleton import build_skeleton
from genesis_contracts.map_tasks import MapPlan
from test_change_analysis import two_commits
from test_map_loop import entry
from test_python_entries import entries

BASE = """from abc import ABC, abstractmethod


class Command(ABC):
    @property
    @abstractmethod
    def name(self): ...

    @abstractmethod
    def run(self, message): ...

    def describe(self):
        return self.name
"""
REFUND = """from .base import Command
from .ledger import refund


class RefundCommand(Command):
    @property
    def name(self):
        return "refund"

    def run(self, message):
        return refund(message)


class PartialRefundCommand(RefundCommand):
    @property
    def name(self):
        return "partial-refund"
"""
BALANCE = """from .base import Command
from .ledger import balance


class BalanceCommand(Command):
    @property
    def name(self):
        return "balance"

    def run(self, message):
        return balance(message)
"""
LEDGER = "def refund(order):\n    return order\n\n\ndef balance(account):\n    return 0\n"
IMPORTS = "from .balance import BalanceCommand\nfrom .refund import PartialRefundCommand, RefundCommand\n\n"
DISPATCH = """

def dispatch(name, message):
    for command in COMMANDS:
        if command().name == name:
            return command().run(message)
"""
RUN = {"bot/refund.py#RefundCommand.run", "bot/balance.py#BalanceCommand.run"}


def bot(registry, base=BASE):
    return {
        "bot/__init__.py": "",
        "bot/base.py": base,
        "bot/refund.py": REFUND,
        "bot/balance.py": BALANCE,
        "bot/ledger.py": LEDGER,
        "bot/registry.py": IMPORTS + registry,
    }


def handlers(found):
    return {key: item for key, item in found.items() if item.kind == "handler"}


def test_classes_listed_together_under_an_abstract_base_are_entries(source_repo):
    found, facts = entries(
        source_repo, bot("COMMANDS = [RefundCommand, BalanceCommand]\n" + DISPATCH)
    )
    assert set(handlers(found)) == RUN
    refund = found["bot/refund.py#RefundCommand.run"]
    assert (refund.detection, refund.framework) == ("adapter", None)
    assert refund.attributes == {"registry": "COMMANDS", "base": "Command"}
    # It cites the line that lists the class, not only the method.
    cited = {ref.evidence_id: ref for ref in facts.evidence}
    assert any(cited[ref].path == "bot/registry.py" for ref in refund.evidence_ids)
    # A property is not something a dispatcher runs, and the base only declares the method.
    assert found["bot/refund.py#RefundCommand.name"].detection == "root_heuristic"
    assert found["bot/base.py#Command.run"].detection == "root_heuristic"


@pytest.mark.parametrize(
    "registry",
    [
        "COMMANDS = (RefundCommand, BalanceCommand)\n",
        "COMMANDS = [RefundCommand(), BalanceCommand()]\n",
        "class Dispatcher:\n    commands = [RefundCommand, BalanceCommand]\n",
    ],
)
def test_the_list_may_be_a_tuple_hold_instances_or_sit_on_a_class(source_repo, registry):
    found, _ = entries(source_repo, bot(registry))
    assert set(handlers(found)) == RUN


def test_a_dictionary_names_its_handlers(source_repo):
    registry = 'COMMANDS = {"refund": RefundCommand, "balance": BalanceCommand}\n'
    found, facts = entries(source_repo, bot(registry))
    assert set(handlers(found)) == RUN
    assert found["bot/balance.py#BalanceCommand.run"].attributes == {
        "registry": "COMMANDS",
        "base": "Command",
        "name": "balance",
    }
    # The key is how the outside names it, so the skeleton starts with it.
    triggers = {flow.steps[0].name for flow in build_skeleton(facts).flows}
    assert triggers == {
        "handler balance · BalanceCommand.run",
        "handler refund · RefundCommand.run",
    }


def test_a_base_that_raises_not_implemented_declares_a_handler_too(source_repo):
    base = (
        "class Command:\n    def run(self, message):\n        raise NotImplementedError\n\n"
        "    def describe(self):\n        return 'command'\n"
    )
    found, _ = entries(source_repo, bot("COMMANDS = [RefundCommand, BalanceCommand]\n", base))
    assert set(handlers(found)) == RUN


def test_an_inherited_implementation_is_the_entry(source_repo):
    found, _ = entries(source_repo, bot("COMMANDS = [PartialRefundCommand, BalanceCommand]\n"))
    # `PartialRefundCommand` does not define `run`; what runs is its parent's.
    assert set(handlers(found)) == RUN


@pytest.mark.parametrize(
    "registry",
    [
        # One class is not a registry.
        "COMMANDS = [RefundCommand]\n",
        # Not everything listed is a class.
        "COMMANDS = [RefundCommand, BalanceCommand, 'help']\n",
        # The base is listed too, and it implements nothing.
        "from .base import Command\n\nCOMMANDS = [Command, RefundCommand, BalanceCommand]\n",
        # A list built inside a function is not a registration.
        "def build():\n    commands = [RefundCommand, BalanceCommand]\n    return commands\n",
    ],
)
def test_other_lists_are_not_registries(source_repo, registry):
    found, _ = entries(source_repo, bot(registry))
    assert not handlers(found)


def test_classes_without_an_abstract_method_are_not_handlers(source_repo):
    files = {
        "app/__init__.py": "",
        "app/errors.py": "class AppError(Exception):\n    def code(self):\n        return 1\n\n\n"
        "class NotFound(AppError):\n    def code(self):\n        return 404\n\n\n"
        "class Denied(AppError):\n    def code(self):\n        return 403\n\n\n"
        "RETRYABLE = (NotFound, Denied)\n",
    }
    found, _ = entries(source_repo, files)
    assert not handlers(found)


def test_a_registry_in_test_code_registers_nothing(source_repo):
    files = bot("")
    files["tests/test_bot.py"] = (
        "from bot.balance import BalanceCommand\nfrom bot.refund import RefundCommand\n\n"
        "COMMANDS = [RefundCommand, BalanceCommand]\n"
    )
    found, _ = entries(source_repo, files)
    assert not handlers(found)


def test_a_call_from_a_test_does_not_make_a_function_called(source_repo):
    files = {
        "jobs.py": "def nightly():\n    return settle()\n\n\ndef settle():\n    return 1\n",
        "tests/test_jobs.py": "from jobs import nightly\n\n\ndef test_nightly():\n"
        "    assert nightly() == 1\n",
    }
    found, _ = entries(source_repo, files)
    # Only a test calls `nightly`, so production code still has no way into it.
    assert found["jobs.py#nightly"].detection == "root_heuristic"
    assert "jobs.py#settle" not in found


def test_a_change_under_a_registered_handler_lands_on_its_flow(source_repo):
    base = bot("COMMANDS = [RefundCommand, BalanceCommand]\n" + DISPATCH)
    head = {**base, "bot/ledger.py": LEDGER.replace("return order", "return [order]")}
    workspace, result = two_commits(source_repo, base, head)
    assert result["entries"]["adapter"] == 2
    refund = entry(workspace, "#RefundCommand.run")
    # No plan, no proposal: the handler already has a flow for the change to land on.
    affected = workspace.status()["change"]["affected_flows"]
    assert [flow["entry_ids"] for flow in affected] == [[refund.entry_id]]
    flow = next(
        item for item in workspace.stored_map().flows if item.entries[0].entry_id == refund.entry_id
    )
    assert flow.steps[0].name == "handler · RefundCommand.run"


JOBS = """from .core import settle


def nightly():
    return settle(None)


def unrelated():
    return 0
"""
OFF_MAP = {
    "app/__init__.py": "",
    "app/api.py": "from fastapi import APIRouter\n\nfrom .core import settle\n\n"
    'router = APIRouter()\n\n\n@router.post("/settle")\ndef settle_now(order):\n'
    "    return settle(order)\n",
    "app/core.py": "def settle(order):\n    return 1\n",
    "app/jobs.py": JOBS,
    "tests/test_jobs.py": "from app.jobs import nightly\n\n\ndef test_nightly():\n"
    "    assert nightly() == 1\n",
}


def test_an_uncalled_function_that_leads_to_a_change_is_offered_as_an_entry(source_repo):
    head = {**OFF_MAP, "app/core.py": OFF_MAP["app/core.py"].replace("return 1", "return 2")}
    workspace, _ = two_commits(source_repo, OFF_MAP, head)
    report = workspace.stored_report()
    (change,) = report.changes
    # The route's flow takes the change. The job reaches the same code and has no flow;
    # `unrelated` has none either, but does not lead there.
    nightly = entry(workspace, "#nightly")
    assert [(item.entry_id, item.change_ids) for item in report.possible_entries] == [
        (nightly.entry_id, (change.change_id,))
    ]
    listed = workspace.status()["change"]["possible_entries"]
    assert listed == [
        {
            "entry_id": nightly.entry_id,
            "symbol_id": "app/jobs.py#nightly",
            "change_ids": [change.change_id],
        }
    ]
    # Proposing it says what kind of entry it is; from then on it is not a candidate.
    proposal = {
        "symbol_id": "app/jobs.py#nightly",
        "kind": "scheduled",
        "reason": "由外部定时器每晚调用",
        "evidence": [
            {"path": "app/jobs.py", "start_line": 4, "end_line": 4, "quote": "def nightly"}
        ],
    }
    now = {
        "key": "now",
        "name": "立即结算",
        "entry_ids": [entry(workspace, "#settle_now").entry_id],
    }
    workspace.save_plan(MapPlan.model_validate({"flows": [now], "proposed_entries": [proposal]}))
    proposed = entry(workspace, "#nightly")
    assert (proposed.kind, proposed.detection) == ("scheduled", "agent_proposed")
    assert workspace.status()["change"]["possible_entries"] == []
    # Given a flow, the change lands on it as well.
    job = {"key": "nightly", "name": "夜间结算", "entry_ids": [nightly.entry_id]}
    workspace.save_plan(MapPlan.model_validate({"flows": [now, job]}))
    change = workspace.status()["change"]
    assert len(change["affected_flows"]) == 2 and change["possible_entries_total"] == 0

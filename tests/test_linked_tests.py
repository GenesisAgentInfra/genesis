"""Which tests a change lists: the most relevant first, and kept beside an agent's choice."""

import genesis_ci.business_map.changes as changes_module
from genesis_ci.business_map.changes import CHANGE_TASK
from test_change_analysis import by_kind, two_commits

CLI = "cli/main.py"
MAIN = """import argparse


def cmd_voice(args):
{voice}    return "plain"


def cmd_setup(args):
    return "setup"


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    p = sub.add_parser("setup")
    p.set_defaults(func=cmd_setup)
    p = sub.add_parser("voice")
    p.add_argument("--pretty", action="store_true")
    p.set_defaults(func=cmd_voice)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
"""
PRETTY = '    if args.pretty:\n        return "pretty"\n'
TESTS = {
    # Runs another subcommand: `main` builds the parser that registers `cmd_voice`, but
    # this argv never selects it.
    "tests/test_a_setup.py": "from cli.main import main\n\n\n"
    'def test_setup():\n    assert main(["setup"]) == "setup"\n',
    "tests/test_b_runs.py": "from argparse import Namespace\n\nfrom cli.main import cmd_voice\n\n\n"
    "def test_cmd_voice_runs():\n    cmd_voice(Namespace(pretty=False))\n",
    "tests/test_voice.py": "from cli.main import main\n\n\n"
    'def test_voice():\n    assert main(["voice", "--pretty"]) == "pretty"\n',
    "tests/test_z_direct.py": "from argparse import Namespace\n\nfrom cli.main import cmd_voice\n\n\n"
    'def test_cmd_voice_direct():\n    assert cmd_voice(Namespace(pretty=False)) == "plain"\n',
}
NEW_TEST = {
    "tests/test_zz_new.py": "import pytest\n\nfrom cli.main import main\n\n\n"
    '@pytest.mark.parametrize("argv", ["voice --pretty"])\n'
    "def test_pretty_flag(argv):\n"
    '    assert main(argv.split()) == "pretty"\n',
}
BASE = {"cli/__init__.py": "", CLI: MAIN.format(voice=""), **TESTS}
HEAD = {**BASE, CLI: MAIN.format(voice=PRETTY), **NEW_TEST}
NEW = "head::tests/test_zz_new.py#test_pretty_flag"
DIRECT = "head::tests/test_z_direct.py#test_cmd_voice_direct"
RUNS = "head::tests/test_b_runs.py#test_cmd_voice_runs"
VOICE = "head::tests/test_voice.py#test_voice"
SETUP = "head::tests/test_a_setup.py#test_setup"


def linked(item):
    return [case.test_id for case in item.tests.items]


def test_tests_of_this_change_and_direct_callers_come_first(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    branch = by_kind(workspace.stored_report(), "condition_added")
    # A test added with the change first, then by calls away, asserting tests before
    # those that assert nothing; the test of another subcommand is not linked at all.
    assert linked(branch) == [NEW, DIRECT, RUNS, VOICE]
    view = next(
        item
        for item in workspace.context(CHANGE_TASK)["changes"]
        if item["change_id"] == branch.change_id
    )
    assert [
        (item["test_id"], item["calls_away"], item["changed_with_it"])
        for item in view["tests"]["tests"]
    ] == [(NEW, 3, True), (DIRECT, 1, False), (RUNS, 1, False), (VOICE, 3, False)]


def test_the_list_is_cut_after_the_most_relevant_tests(source_repo, monkeypatch):
    monkeypatch.setattr(changes_module, "MAX_CASES", 2)
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    branch = by_kind(workspace.stored_report(), "condition_added")
    assert linked(branch) == [NEW, DIRECT]
    assert branch.tests.note.endswith("2 more tests are not listed.")


def test_naming_tests_keeps_the_static_links_after_them(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    branch = by_kind(workspace.stored_report(), "condition_added")
    entry = {
        "change_id": branch.change_id,
        "summary": "新增 --pretty 输出。",
        "verdict": "covered",
        "note": "test_voice 传了 --pretty 并断言输出，去掉这个分支会失败。",
        "test_ids": [VOICE],
    }
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    tests = by_kind(workspace.stored_report(), "condition_added").tests
    assert [(case.test_id, case.tags) for case in tests.items] == [
        (VOICE, ("related", "assessed", "assertion_found")),
        (NEW, ("related", "assertion_found")),
        (DIRECT, ("related", "assertion_found")),
        (RUNS, ("related",)),
    ]
    assert tests.basis == ("static_fact", "agent_assessment")


AGENT = """class Agent:
    def handle(self, message):
        return self._reply(message)

    def _reply(self, message):
{reply}"""
UNITTEST = """import unittest

from shop.agent import Agent


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.agent = Agent()

    def test_handle(self):
        self.assertEqual(self.agent.handle("hi"), "hi")
"""


def test_a_test_case_reaches_the_code_its_set_up_object_runs(source_repo):
    base = {
        "shop/__init__.py": "",
        "shop/agent.py": AGENT.format(reply="        return message\n"),
        "tests/test_agent.py": UNITTEST,
    }
    branch = '        if not message:\n            return "empty"\n        return message\n'
    head = {**base, "shop/agent.py": AGENT.format(reply=branch)}
    workspace, _ = two_commits(source_repo, base, head)
    change = by_kind(workspace.stored_report(), "condition_added")
    # unittest runs setUp before each test, so the test calls `handle` on what it made.
    assert change.tests.verdict == "reached_only"
    assert linked(change) == ["head::tests/test_agent.py#AgentTest.test_handle"]
    view = next(
        item
        for item in workspace.context(CHANGE_TASK)["changes"]
        if item["change_id"] == change.change_id
    )
    assert [item["calls_away"] for item in view["tests"]["tests"]] == [2]

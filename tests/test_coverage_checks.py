"""Source-backed coverage submissions; analyzed fixtures are never executed."""

import json

import pytest
from genesis_ci.agent_map.session import prepare as prepare_agent
from genesis_ci.agent_map.workspace import Workspace as AgentWorkspace
from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.business_map.render import render_html, render_summary
from genesis_ci.business_map.view import view_payload
from genesis_contracts.change_report import ChangeReport
from test_change_analysis import by_kind, two_commits
from test_git_snapshot import commit, write
from test_map_loop import codes

PRICE = "def price(quantity, unit):\n    return quantity * unit{fee}\n"
TEST_ID = "head::tests/test_price.py#test_price"


def python_case(repo, body):
    base = {
        "app.py": PRICE.format(fee=""),
        "tests/test_price.py": "from app import price\n\ndef test_price():\n" + body,
    }
    workspace, _ = two_commits(repo, base, {**base, "app.py": PRICE.format(fee=" + quantity % 2")})
    item = by_kind(workspace.stored_report(), "result_modified")
    entry = {
        "change_id": item.change_id,
        "summary": "An odd quantity adds a fee of one.",
        "verdict": "covered",
        "note": "The test checks the price.",
        "test_ids": [TEST_ID],
    }
    return workspace, entry


def check(assertion="price(1, 5) == 6", test_id=TEST_ID):
    return {
        "test_id": test_id,
        "assertion": assertion,
        "scenario": "One unit priced at 5.",
        "detects": "The assertion expects 6; undoing the fee returns 5.",
    }


@pytest.mark.parametrize(
    "body",
    [
        "    assert price(2, 5) == 10\n",
        "    price(1, 5)\n    assert True\n",
        "    assert 1 == 1\n",
    ],
)
def test_bare_covered_claims_do_not_upgrade_static_results(source_repo, body):
    workspace, entry = python_case(source_repo, body)
    before = workspace.stored_report()
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "rejected"
    assert codes(result) == [("changes[0].checks", "covered_needs_checks")]
    assert workspace.stored_report() == before
    # Reading the even-input fixture supports reached_only, without executing it.
    entry.update(verdict="reached_only", note="The assertion does not detect the added fee.")
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    assert by_kind(workspace.stored_report(), "result_modified").tests.verdict == "reached_only"


def test_checks_are_bound_to_the_named_frozen_test(source_repo):
    workspace, entry = python_case(source_repo, "    assert price(1, 5) == 6\n")
    entry["checks"] = [check(test_id="head::tests/other.py#test_other")]
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert ("changes[0].checks[0].test_id", "check_names_test") in codes(result)
    entry["checks"] = [check("price(2, 5) == 10")]
    # Changing the live test cannot make invented evidence valid in this session.
    write(source_repo, "tests/test_price.py", "def test_price():\n    assert price(2, 5) == 10\n")
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert codes(result) == [("changes[0].checks[0].assertion", "assertion_not_found")]


@pytest.mark.parametrize(
    "assertion",
    ["True", "1 == 1", "'ok'", "[1, 2]", "'ok' == 'ok'", "2 * 3 == 6"],
)
def test_vacuous_assertions_cannot_support_complete_covered_submissions(source_repo, assertion):
    workspace, entry = python_case(source_repo, f"    price(1, 5)\n    assert {assertion}\n")
    before = workspace.stored_report()
    # All fields are supplied, with authentic assertion text. The claim still has
    # no assertion that observes the call's result; prose cannot make it evidence.
    entry["checks"] = [check(assertion)]
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "rejected"
    assert codes(result) == [("changes[0].checks[0].assertion", "vacuous_assertion")]
    assert workspace.stored_report() == before
    entry.update(verdict="reached_only", note="The assertion reads no result of the call.")
    entry.pop("checks")
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"


@pytest.mark.parametrize(
    ("body", "assertion"),
    [
        ("    actual = price(1, 5)\n    assert actual == 6\n", "actual == 6"),
        ("    seen = []\n    seen.append(price(1, 5))\n    assert seen == [6]\n", "seen == [6]"),
        ("    if price(1, 5) != 6:\n        assert False\n", "False"),
        ("    if price(1, 5) != 6:\n        assert 0 == 1\n", "0 == 1"),
        # A captured assertion may end at 400 characters. Its visible literal
        # prefix cannot establish that the complete expression is vacuous.
        (f"    assert True{' ' * 396}and price(1, 5) == 6\n", "True"),
        (
            "    import pytest\n    if price(1, 5) != 6:\n        pytest.fail('wrong price')\n",
            "pytest.fail('wrong price')",
        ),
        (
            "    import unittest\n    self = unittest.TestCase()\n"
            "    self.assertEqual(price(1, 5), 6)\n",
            "self.assertEqual(price(1, 5), 6)",
        ),
        (
            "    from unittest.mock import Mock\n    recorded = Mock()\n"
            "    recorded(price(1, 5))\n    recorded.assert_called_once_with(6)\n",
            "recorded.assert_called_once_with(6)",
        ),
        (
            "    import pytest\n    with pytest.raises(ZeroDivisionError):\n"
            "        1 / (price(1, 5) - 6)\n",
            "pytest.raises(ZeroDivisionError)",
        ),
    ],
)
def test_indirect_and_framework_assertions_remain_eligible(source_repo, body, assertion):
    workspace, entry = python_case(source_repo, body)
    entry["checks"] = [check(assertion)]
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"


def test_supported_check_is_preserved_as_an_agent_assessment(source_repo):
    workspace, entry = python_case(source_repo, "    assert price(1, 5) == 6\n")
    entry["test_ids"] = [TEST_ID.removeprefix("head::")]
    entry["checks"] = [check("assert price( 1,5 ) == 6", TEST_ID.removeprefix("head::"))]
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    report, head = workspace.stored_report(), workspace.stored_map()
    tests = by_kind(report, "result_modified").tests
    assert tests.verdict == "covered" and tests.execution_data == "not_collected"
    assert "agent_assessment" in tests.basis
    assert tests.checks[0].test_id == TEST_ID
    summary = render_summary(head, report)
    assert "tests: assessed as covered" in summary
    assert entry["checks"][0]["assertion"] in summary
    assert check()["detects"] in summary
    assert "assessed as covered" in render_html(head, None, report)
    # Sharing a report must not expose the newly added source quotation.
    shared = view_payload(head, None, report)
    shared_tests = next(item["tests"] for item in shared["report"]["changes"] if item["tests"])
    assert "assertion" not in shared_tests["checks"][0]
    assert "<pre>" not in render_html(head, None, report)
    # A rejected replacement keeps the accepted version, including its checks.
    entry.pop("checks")
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "rejected"
    assert workspace.stored_report() == report
    # Previously saved reports remain readable, with no invented check evidence.
    legacy = report.model_dump(mode="json")
    for item in legacy["changes"]:
        if item["tests"]:
            item["tests"].pop("checks")
    assert by_kind(ChangeReport.model_validate(legacy), "result_modified").tests.checks == ()
    saved = workspace.root / "changes" / "accepted.json"
    raw = json.loads(saved.read_text())
    raw["assessments"][entry["change_id"]].pop("checks")
    saved.write_text(json.dumps(raw))
    workspace._publish(head)
    assert by_kind(workspace.stored_report(), "result_modified").tests.checks == ()


def test_other_languages_require_a_head_side_assertion_quote(source_repo):
    write(source_repo, "price.ts", "export const price = (q, unit) => q * unit;\n")
    assertion = "expect(price(1, 5)).toBe(6)"
    test_source = f'test("odd quantity", () => {{ {assertion}; }});\n'
    write(source_repo, "tests/price.test.ts", test_source)
    commit(source_repo)
    write(source_repo, "price.ts", "export const price = (q, unit) => q * unit + q % 2;\n")
    result = prepare_agent(source_repo, base="HEAD")
    workspace = AgentWorkspace(source_repo, result["session_id"])
    item = workspace._stored_report().changes[0]
    test = {
        "name": "odd quantity",
        "asserts": True,
        "evidence": [
            {"path": "tests/price.test.ts", "start_line": 1, "end_line": 1, "quote": assertion}
        ],
    }
    entry = {
        "change_id": item.change_id,
        "summary": "Odd quantities incur a fee.",
        "verdict": "covered",
        "note": "The odd quantity test checks the fee.",
        "tests": [test],
    }
    before = workspace._stored_report()
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert codes(result) == [("changes[0].tests[0].check", "covered_needs_checks")]
    test["check"] = {key: value for key, value in check(assertion).items() if key != "test_id"}
    test["check"]["assertion"] = "expect(price(2, 5)).toBe(10)"
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert codes(result) == [("changes[0].tests[0].check.assertion", "assertion_not_found")]
    test["check"]["assertion"] = assertion
    test["evidence"][0]["side"] = "base"
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert ("changes[0].tests[0].check.assertion", "assertion_not_found") in codes(result)
    assert workspace._stored_report() == before
    test["evidence"][0]["side"] = "head"
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    tests = workspace._stored_report().changes[0].tests
    assert tests.checks[0].assertion == assertion
    assert tests.basis == ("agent_assessment",)


def test_an_asserts_flag_does_not_replace_source_evidence(source_repo):
    write(source_repo, "price.ts", "export const price = () => 1;\n")
    source = 'test("smoke", () => { price(); });'
    write(source_repo, "tests/price.test.ts", source)
    commit(source_repo)
    write(source_repo, "price.ts", "export const price = () => 2;\n")
    session = prepare_agent(source_repo, base="HEAD")
    workspace = AgentWorkspace(source_repo, session["session_id"])
    entry = {
        "change_id": workspace._stored_report().changes[0].change_id,
        "summary": "Price is now two.",
        "verdict": "covered",
        "note": "The smoke test reaches price.",
        "tests": [
            {
                "name": "smoke",
                "asserts": True,
                "evidence": [
                    {"path": "tests/price.test.ts", "start_line": 1, "end_line": 1, "quote": source}
                ],
                "check": {
                    "assertion": "expect(price()).toBe(2)",
                    "scenario": "Call price.",
                    "detects": "Expect two.",
                },
            }
        ],
    }
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert codes(result) == [("changes[0].tests[0].check.assertion", "assertion_not_found")]

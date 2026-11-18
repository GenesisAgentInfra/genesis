"""Coverage verdicts: judged by whether a test would fail, and shown with their basis."""

from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.business_map.render import VERDICT_LEGEND, render_html, render_summary
from test_change_analysis import SMOKE_TEST, SUBMIT_TEST, by_kind
from test_change_short_path import change  # noqa: F401  (fixture)
from test_map_loop import codes


def test_the_rules_judge_a_verdict_by_whether_a_test_would_fail(change):  # noqa: F811
    rules = " ".join(change.context(CHANGE_TASK)["rules"])
    assert "would fail if the change were undone" in rules
    # A test counts when the default test command runs it: a skip on a missing
    # credential excludes it, needing the network alone does not.
    assert "the project's default test command runs it" in rules
    assert "missing environment variable or credential" in rules
    assert "Needing the network or a model download does not by itself exclude a test" in rules
    assert "need the network" not in rules
    # Replaced code: the test's input goes through the old side as well.
    assert "take the test's input through the `before` side" in rules
    assert "a different outcome on the two sides" in rules
    # A gap in the tests belongs in the note, not among the risks.
    assert "not into `risks`" in rules
    # A new definition is one change: one verdict for the whole, its gaps in the note.
    assert "An added definition is judged as a whole" in rules
    assert "would fail if the change were undone" in VERDICT_LEGEND


def test_covered_names_the_tests_that_would_fail(change):  # noqa: F811
    condition = by_kind(change.stored_report(), "condition_modified").change_id
    entry = {"change_id": condition, "summary": "阈值改为包含 100。", "verdict": "covered"}
    entry["note"] = "参数化测试覆盖了这个条件。"
    result = change.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "rejected"
    assert codes(result) == [("changes[0].test_ids", "covered_names_tests")]
    entry["test_ids"] = [SUBMIT_TEST]
    assert change.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"


def test_a_static_result_is_not_shown_as_tests_missing_the_path(change):  # noqa: F811
    report, head = change.stored_report(), change.stored_map()
    condition = by_kind(report, "condition_modified")
    assert condition.tests.verdict == "reached_only" and condition.tests.basis == ("static_fact",)
    summary = render_summary(head, report)
    # Nobody read the tests yet: static analysis only found tests that call the code.
    assert "(tests: called by tests, not assessed)" in summary
    assert "(tests: reached only)" not in summary
    assert "called by tests, not assessed" in render_html(head, None, report)
    entry = {
        "change_id": condition.change_id,
        "summary": "阈值改为包含 100。",
        "verdict": "reached_only",
        "note": "测试只用了 50 和 500，没有取值等于阈值的用例。",
        "test_ids": [SUBMIT_TEST],
    }
    assert change.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    summary = render_summary(change.stored_map(), change.stored_report())
    assert "阈值改为包含 100。 (tests: reached only)" in summary
    # The named test is told apart from the other tests static analysis linked.
    assert f"    - tests: {SUBMIT_TEST}; also linked: {SMOKE_TEST}" in summary

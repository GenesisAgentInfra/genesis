"""A statement that repeats inside one function is matched to itself across a change.

Repeats share their text, so a fingerprint tells them apart by counting. The count of a
statement moves when a repeat is added or removed before it; the diff has to follow the
statement, not the count.
"""

from test_change_analysis import by_kind, diff, two_commits


def lines(report, part):
    ref = next(item for item in report.evidence if item.evidence_id == part.evidence_ids[0])
    return ref.range.start_line, ref.range.end_line


def test_a_repeat_added_earlier_is_reported_where_it_was_added(source_repo):
    base = 'def run(report):\n    send(report)\n    return build(error=report.get("error"))\n'
    head = (
        "def run(report):\n"
        '    cause = report.get("error")\n'
        "    send(report)\n"
        '    return build(error=report.get("error"))\n'
    )
    changes, report = diff(source_repo, {"app/core.py": base}, {"app/core.py": head})
    assert changes == [("call_added", None, 'report.get("error")')]
    # The new line, not the untouched last line that reads the same.
    assert lines(report, report.changes[0].after) == (2, 2)


def test_a_repeat_inside_an_edited_statement_leaves_the_others_alone(source_repo):
    base = (
        "def run(report):\n"
        "    if not report:\n"
        '        return fail(cause=report.get("code"))\n'
        '    return build(error=report.get("error"))\n'
    )
    head = base.replace('get("code")', 'get("error")')
    changes, _ = diff(source_repo, {"app/core.py": base}, {"app/core.py": head})
    # The call that became a repeat sits in the edited line, which already reports it.
    assert changes == [
        (
            "result_modified",
            'return fail(cause=report.get("code"))',
            'return fail(cause=report.get("error"))',
        )
    ]


TIMEOUT = (
    '        return Result(\n            status="timeout",\n            partial=True,\n        )\n'
)
TWICE = (
    "def run(question, deadline):\n"
    "    if question.late:\n" + TIMEOUT + "    work(question)\n"
    "    if deadline.passed:\n" + TIMEOUT + '    return Result(status="ok")\n'
)


def test_an_edited_repeat_is_compared_with_the_statement_it_was(source_repo):
    edited = TIMEOUT.replace("partial=True,\n", 'partial=True,\n            stage="question",\n')
    head = TWICE.replace(TIMEOUT, edited, 1)
    _, report = diff(source_repo, {"app/core.py": TWICE}, {"app/core.py": head})
    change = by_kind(report, "result_modified")
    assert 'stage="question"' in change.after.text
    # The first of the two identical returns was edited; the second did not move.
    assert lines(report, change.before) == (3, 6)
    assert lines(report, change.after) == (3, 7)
    assert len(report.changes) == 1


def test_a_removed_repeat_is_the_one_that_is_gone(source_repo):
    base = "def run(x):\n    save(x)\n    check(x)\n    save(x)\n    return x\n"
    head = "def run(x):\n    check(x)\n    save(x)\n    return x\n"
    changes, report = diff(source_repo, {"app/core.py": base}, {"app/core.py": head})
    assert changes == [("call_removed", "save(x)", None)]
    assert lines(report, report.changes[0].before) == (2, 2)


def test_a_repeated_condition_added_earlier_does_not_disturb_the_ones_after_it(source_repo):
    base = (
        "def run(x):\n"
        "    if x:\n"
        "        first()\n"
        "    middle()\n"
        "    if x:\n"
        "        second()\n"
        "    return 1\n"
    )
    head = base.replace("def run(x):\n", "def run(x):\n    if x:\n        zero()\n")
    changes, report = diff(source_repo, {"app/core.py": base}, {"app/core.py": head})
    # Only the new branch: nothing under the two old ones moved to another branch.
    assert changes == [("condition_added", None, "if x:\n    zero()")]
    assert lines(report, report.changes[0].after) == (2, 3)


def test_removed_code_under_a_repeated_condition_stays_under_that_condition(source_repo):
    api = (
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n"
        '@router.get("/run")\n'
        "def run(x):\n"
        "    if x:\n"
        "        first()\n"
        "    middle()\n"
        "    if x:\n"
        "        second()\n"
        "        third()\n"
        "    return 1\n"
    )
    head = api.replace("def run(x):\n", "def run(x):\n    if x:\n        zero()\n").replace(
        "        third()\n", ""
    )
    workspace, _ = two_commits(
        source_repo,
        {"app/__init__.py": "", "app/api.py": api},
        {"app/__init__.py": "", "app/api.py": head},
    )
    report, stored = workspace.stored_report(), workspace.stored_map()
    removed = by_kind(report, "call_removed")
    assert removed.before.text == "third()" and removed.projection.status == "projected"
    step = next(
        step
        for flow in stored.flows
        for step in flow.steps
        if step.step_id == removed.projection.step_id
    )
    # The last of three identical conditions on the head side: the one above `second()`.
    under = [workspace.by_fingerprint[anchor] for anchor in step.anchors]
    assert [fact.range.start_line for fact in under] == [13]

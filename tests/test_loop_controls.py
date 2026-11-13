"""Loop controls the extractor records: where a break, continue, return or raise sits."""

import pytest
from genesis_ci.python.validate import validate_python
from test_python_analysis import analyze, calls

PREFIX = "from openai import OpenAI\nclient = OpenAI()\n"
MODEL = 'client.responses.create(model="x", input="hi")'


def controls(result):
    return [control for control in result.analysis.loop_controls if control.side == "head"]


def head_loops(result):
    return [loop for loop in result.analysis.loops if loop.side == "head"]


def test_branch_polarity_of_return_continue_and_break(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent(done, retry):
    while True:
        response = {MODEL}
        if done:
            return response
        elif retry:
            continue
        else:
            break
"""
        },
    )
    found = {control.kind: control for control in controls(result)}
    assert found["return"].conditions == ("if true: done",)
    assert found["continue"].conditions == ("if false: done", "if true: retry")
    assert found["break"].conditions == ("if false: done", "if false: retry")


def test_nearest_break_all_return_and_nested_function_boundary(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        {MODEL}
        for _ in range(3):
            if ready:
                break
            if done:
                return 1
            def nested():
                return 2
"""
        },
    )
    outer, inner = head_loops(result)
    assert [(c.kind, c.loop_ids) for c in controls(result)] == [
        ("break", (inner.loop_id,)),
        ("return", (outer.loop_id, inner.loop_id)),
    ]
    assert all(c.expression != "return 2" for c in controls(result))


def test_for_else_calls_and_break_belong_only_to_outer_loop(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        for _ in range(3):
            pass
        else:
            {MODEL}
            break
"""
        },
    )
    outer, _inner = head_loops(result)
    model = next(call for call in calls(result) if call.callee.text == "client.responses.create")
    assert model.loop_ids == (outer.loop_id,)
    assert controls(result)[0].loop_ids == (outer.loop_id,)
    assert "loop else after normal completion" in controls(result)[0].conditions


def test_try_except_finally_and_raise_are_caveated(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        {MODEL}
        try:
            raise ValueError("retry")
        except ValueError:
            continue
        finally:
            if done:
                return 1
"""
        },
    )
    found = controls(result)
    raised = next(c for c in found if c.kind == "raise")
    assert "try body" in raised.conditions
    assert any("caught" in caveat for caveat in raised.caveats)
    assert any("finally" in caveat for caveat in raised.caveats)
    returned = next(c for c in found if c.kind == "return")
    assert returned.conditions == ("finally body", "if true: done")


def test_match_guard_and_context_exit_evidence(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent(state):
    while True:
        {MODEL}
        with context():
            match state:
                case "done" if allowed:
                    break
"""
        },
    )
    control = controls(result)[0]
    assert control.conditions == ('match state case "done"', "guard true: allowed")
    assert any("Context manager" in caveat for caveat in control.caveats)
    texts = [result.registry.freeze().read_excerpt(ref).text for ref in control.evidence_ids]
    assert "allowed" in texts and "break" in texts


def test_validator_rejects_control_cross_loop_owner(source_repo):
    result = analyze(
        source_repo,
        {"app.py": PREFIX + f"def agent():\n    while True:\n        {MODEL}\n        break\n"},
    )
    item = result.analysis.loop_controls[0]
    bad = item.model_copy(update={"loop_ids": ("absent-loop",)})
    altered = result.analysis.model_copy(
        update={"loop_controls": (bad, *result.analysis.loop_controls[1:])}
    )
    with pytest.raises(ValueError, match="loop references"):
        validate_python(altered)


def test_try_star_and_nested_loop_else_return(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        {MODEL}
        try:
            raise ExceptionGroup("x", [])
        except* ValueError:
            recover()
        for _ in range(2):
            pass
        else:
            return 1
"""
        },
    )
    found = controls(result)
    outer, _inner = head_loops(result)
    assert next(c for c in found if c.kind == "return").loop_ids == (outer.loop_id,)
    assert any("caught" in reason for c in found if c.kind == "raise" for reason in c.caveats)


@pytest.mark.parametrize("exit_statement", ["break", "return response"])
def test_straight_line_loop_records_its_single_pass_exit(source_repo, exit_statement):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        response = {MODEL}
        {exit_statement}
"""
        },
    )
    [loop] = head_loops(result)
    [control] = controls(result)
    assert loop.single_pass_exit_id == control.control_id
    validate_python(result.analysis)


@pytest.mark.parametrize(
    "tail",
    [
        "if done:\n            break",
        "if retry:\n            continue\n        break",
        "try:\n            break\n        finally:\n            continue",
        "with context():\n            return response",
    ],
)
def test_conditional_or_overridden_exit_does_not_prove_single_pass(source_repo, tail):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    while True:
        response = {MODEL}
        {tail}
"""
        },
    )
    [loop] = head_loops(result)
    assert loop.single_pass_exit_id is None


@pytest.mark.parametrize(
    "start,op,stop,update,step",
    [
        (0, "<", 3, "i += 1", 1),
        (0, "<=", 3, "i += 2", 2),
        (5, ">", -1, "i -= 2", -2),
        (5, ">=", -1, "i += -2", -2),
        (-5, "<", 0, "i -= -2", 2),
    ],
)
def test_simple_local_counter_progression_and_evidence(source_repo, start, op, stop, update, step):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    i = {start}
    while i {op} {stop}:
        {MODEL}
        {update}
"""
        },
    )
    [loop] = head_loops(result)
    counter = loop.counter_progression
    assert (counter.variable, counter.start, counter.stop, counter.step, counter.comparison) == (
        "i",
        start,
        stop,
        step,
        op,
    )
    texts = [result.registry.freeze().read_excerpt(ref).text for ref in counter.evidence_ids]
    assert f"i = {start}" in texts and update in texts
    assert f"i {op} {stop}" in texts


@pytest.mark.parametrize(
    "prefix,condition,body",
    [
        ("i = 0", "i < LIMIT", "i += 1"),
        ("i = 0", "i < 3", "if retry:\n            continue\n        i += 1"),
        ("i = 0", "i < 3", "i += 0"),
        ("i = 0", "i < 3", "i -= 1"),
        ("i = 0", "i < 3", "i = reset()\n        i += 1"),
        ("i = 0", "i < 3", "consume(i)\n        i += 1"),
        ("global i\n    i = 0", "i < 3", "i += 1"),
        ("i = 0", "i < 3", "exec(code)\n        i += 1"),
    ],
)
def test_counter_rejects_dynamic_values_skipped_updates_and_nonlocal_state(
    source_repo, prefix, condition, body
):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    {prefix}
    while {condition}:
        {MODEL}
        {body}
"""
        },
    )
    [loop] = head_loops(result)
    assert loop.counter_progression is None

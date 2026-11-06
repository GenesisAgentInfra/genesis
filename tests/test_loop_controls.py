import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.patterns import detect_patterns
from genesis_ci.pipeline import analyze_snapshot
from genesis_ci.python.validate import validate_python
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write
from test_python_analysis import analyze, calls

PREFIX = "from openai import OpenAI\nclient = OpenAI()\n"
MODEL = 'client.responses.create(model="x", input="hi")'


def controls(result):
    return [control for control in result.analysis.loop_controls if control.side == "head"]


def loops(result):
    return [loop for loop in detect_patterns(result).loops if loop.side == "head"]


def test_branch_polarity_return_continue_and_stop_projection(source_repo):
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
    loop = loops(result)[0]
    assert loop.loop.iteration_bound.status == "unbounded"
    assert any("return under if true: done" in item for item in loop.loop.stop_conditions)
    assert not any(item.startswith("continue") for item in loop.loop.stop_conditions)
    assert loop.controls == tuple(controls(result))


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
    outer, inner = [loop for loop in result.analysis.loops if loop.side == "head"]
    assert [(c.kind, c.loop_ids) for c in controls(result)] == [
        ("break", (inner.loop_id,)),
        ("return", (outer.loop_id, inner.loop_id)),
    ]
    assert all(c.expression != "return 2" for c in controls(result))
    assert [c.kind for c in loops(result)[0].controls] == ["return"]


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
    outer, inner = [loop for loop in result.analysis.loops if loop.side == "head"]
    model = next(call for call in calls(result) if call.callee.text == "client.responses.create")
    assert model.loop_ids == (outer.loop_id,)
    assert controls(result)[0].loop_ids == (outer.loop_id,)
    assert "loop else after normal completion" in controls(result)[0].conditions
    assert all(loop.loop.loop_id != inner.loop_id for loop in loops(result))


def test_iterable_call_outside_own_body_and_lambda_deferred(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    for value in {MODEL}:
        fn = lambda: {MODEL}
"""
        },
    )
    model_calls = [call for call in calls(result) if call.callee.text == "client.responses.create"]
    assert all(call.loop_ids == () for call in model_calls)
    assert loops(result) == []


@pytest.mark.parametrize("exit_statement", ["break", "return response"])
def test_straight_line_loop_has_at_most_one_iteration(source_repo, exit_statement):
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
    loop = loops(result)[0]
    assert loop.loop.iteration_bound.status == "bounded"
    assert loop.loop.iteration_bound.max_iterations == 1
    assert "not a termination" in loop.loop.iteration_bound.reason
    assert result.analysis.loop_controls
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
    assert loops(result)[0].loop.iteration_bound.status == "unbounded"


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
    assert loops(result)[0].loop.iteration_bound.status == "unbounded"


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


def test_control_diff_reaches_report_with_both_sides(source_repo):
    source = (
        PREFIX
        + f"""def agent(done):
    while True:
        {MODEL}
        if done:
            break
"""
    )
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", source.replace("break", "continue"))
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    finding = next(
        f for f in result.report.findings if f.finding_id.startswith("loop_controls_changed")
    )
    refs = {ref.evidence_id: ref for ref in result.local.evidence}
    assert {refs[ref].side.value for ref in finding.evidence_ids} == {"base", "head"}
    assert "not a loop exit" in finding.gap


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


@pytest.mark.parametrize(
    "start,op,stop,update,expected",
    [
        (0, "<", 3, "i += 1", 3),
        (0, "<=", 3, "i += 2", 2),
        (5, ">", -1, "i -= 2", 3),
        (5, ">=", -1, "i += -2", 4),
        (-5, "<", 0, "i -= -2", 3),
    ],
)
def test_simple_local_counter_bound_and_evidence(source_repo, start, op, stop, update, expected):
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
    loop = loops(result)[0]
    assert loop.loop.iteration_bound.max_iterations == expected
    texts = [
        result.registry.freeze().read_excerpt(ref).text
        for ref in loop.loop.iteration_bound.evidence_ids
    ]
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
    ir_loop = next(loop for loop in result.analysis.loops if loop.side == "head")
    assert ir_loop.counter_progression is None
    if loops(result):
        assert loops(result)[0].loop.iteration_bound.status == "unknown"


def test_zero_counter_and_false_while_are_not_unbounded(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"""def agent():
    i = 4
    while i < 3:
        {MODEL}
        i += 1
    while False:
        {MODEL}
        break
"""
        },
    )
    assert all(loop.loop.iteration_bound.status == "unknown" for loop in loops(result))
    assert all(loop.loop.iteration_bound.max_iterations is None for loop in loops(result))


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
    outer = loops(result)[0]
    assert next(c for c in found if c.kind == "return").loop_ids == (outer.loop.loop_id,)
    assert any("caught" in reason for c in found if c.kind == "raise" for reason in c.caveats)


def test_empty_iterator_stays_explicit_even_with_terminal_break(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + f"def agent():\n    for i in range(0):\n        {MODEL}\n        break\n"
        },
    )
    bound = loops(result)[0].loop.iteration_bound
    assert bound.status == "unknown" and "empty" in bound.reason


def test_pattern_control_validator_cannot_drop_return(source_repo):
    from genesis_ci.pattern_validation import validate_patterns

    result = analyze(
        source_repo,
        {"app.py": PREFIX + f"def agent():\n    while True:\n        {MODEL}\n        return 1\n"},
    )
    patterns = detect_patterns(result)
    item = patterns.loops[0].model_copy(update={"controls": ()})
    bad = patterns.model_copy(update={"loops": (item, *patterns.loops[1:])})
    with pytest.raises(ValueError, match="controls differ"):
        validate_patterns(result.analysis, bad)


def test_module_counter_and_nonlocal_callback_not_bounded(source_repo):
    source = (
        PREFIX
        + f"""i = 0
while i < 3:
    {MODEL}
    i += 1
def agent():
    def callback():
        nonlocal i
        i = 0
    i = 0
    while i < 3:
        {MODEL}
        callback()
        i += 1
"""
    )
    result = analyze(source_repo, {"app.py": source})
    assert all(loop.counter_progression is None for loop in result.analysis.loops)
    assert all(loop.loop.iteration_bound.status == "unknown" for loop in loops(result))


def test_counter_constant_change_detected_even_same_body_calls(source_repo):
    source = (
        PREFIX + f"def agent():\n    i = 0\n    while i < 3:\n        {MODEL}\n        i += 1\n"
    )
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", source.replace("i < 3", "i < 5"))
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    finding = next(
        f for f in result.report.findings if f.finding_id.startswith("loop_bound_changed")
    )
    assert "bounded:3" in finding.statement and "bounded:5" in finding.statement
    assert all(estimate.amount is None for estimate in result.report.estimates)


def test_loop_controls_survive_existing_b4_projection(source_repo):
    from genesis_ci.report import assemble_report
    from genesis_contracts.models import AnalysisRequest, SemanticAnalysisResponse
    from genesis_contracts.validation import validate_request_against_local

    source = (
        PREFIX
        + f"def agent(done):\n    while True:\n        {MODEL}\n        if done:\n            return 1\n"
    )
    analyze(source_repo, {"app.py": source})
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    result = analyze_snapshot(snapshot)
    local = result.local
    fields = (
        "change_set",
        "facts",
        "agent_loops",
        "impact_graph",
        "flows",
        "flow_impacts",
        "test_definitions",
        "intents",
        "evidence",
        "rule_findings",
        "estimates",
    )
    request = AnalysisRequest(
        request_id="loop-controls-handoff",
        snapshot_id=local.snapshot.snapshot_id,
        cli_version="0.5.0-static",
        **{field: getattr(local, field) for field in fields},
        excerpts=result.reader.read_selected(tuple(ref.evidence_id for ref in local.evidence)),
    )
    validate_request_against_local(local, request)
    response = SemanticAnalysisResponse(
        request_id=request.request_id,
        snapshot_id=request.snapshot_id,
        section_status=local.capabilities,
        semantic_version="test-only",
    )
    report = assemble_report(
        local,
        request,
        response,
        analyzer_version="0.5.0-static",
        rule_version="0.5.0-structural",
        parser_limitations=("Static loop controls",),
    )
    assert any(
        text.startswith("return under")
        for loop in request.agent_loops
        for text in loop.stop_conditions
    )
    assert report.analysis_status == "partial"
    assert all(estimate.amount is None for estimate in report.estimates)


def test_control_change_ignores_line_shifts(source_repo):
    source = (
        PREFIX
        + f"def agent(done):\n    while True:\n        {MODEL}\n        if done:\n            break\n"
    )
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "# moved lines\n\n" + source)
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert not any(
        finding.finding_id.startswith("loop_controls_changed") for finding in result.report.findings
    )

"""Selected changed code retains bounded lexical dependency source, not runtime values."""

from genesis_ci.context import ContextOptions, build_context
from genesis_contracts.validation import validate_request_against_local
from test_context_dependencies import captured


def test_changed_wrapper_retains_unchanged_helper_and_table_on_both_sides(source_repo):
    base = (
        "RATES = {'normal': 2.5, 'cached': 0.25}\n"
        "def lookup(kind):\n    return RATES[kind]\n"
        "def estimate(count, kind):\n"
        + "    print('detail')\n" * 30
        + "    return count * lookup(kind)\n"
    )
    local = captured(
        source_repo, {"pricing.py": base}, {"pricing.py": base.replace("count *", "(count + 1) *")}
    )
    request = build_context(
        local.local,
        local.reader,
        request_id="lexical-dependencies",
        options=ContextOptions(input_token_budget=6000),
    )
    validate_request_against_local(local.local, request)
    for side in ("base", "head"):
        assert any(
            ref.side == side and "RATES = {'normal': 2.5, 'cached': 0.25}" in excerpt.text
            for ref, excerpt in zip(request.evidence, request.excerpts)
        )
        assert any(
            f.side == side and f.symbol_id == "pricing.py#lookup" for f in request.facts.functions
        )
        assert any(
            f.side == side and f.symbol_id == "pricing.py#estimate" for f in request.facts.functions
        )
    assert all(call in local.local.facts.calls for call in request.facts.calls)
    assert all(edge in local.local.impact_graph.edges for edge in request.impact_graph.edges)


def test_lexical_source_does_not_promote_unknown_native_call_resolution(source_repo):
    base = (
        "TABLE = {'one': 2}\n"
        "def helper(key):\n    return TABLE[key]\n"
        "exec(dynamic_source)\n"
        "def wrapper(key):\n    first, second = (key, key)\n    return helper(first)\n"
    )
    local = captured(
        source_repo, {"app.py": base}, {"app.py": base.replace("helper(first)", "helper(second)")}
    )
    calls = [call for call in local.local.facts.calls if call.expression == "helper"]
    assert calls and all(call.target.status == "unknown" for call in calls)
    request = build_context(local.local, local.reader, request_id="unknown-stays-unknown")
    validate_request_against_local(local.local, request)
    assert any("TABLE = {'one': 2}" in excerpt.text for excerpt in request.excerpts)
    selected_calls = [call for call in request.facts.calls if call.expression == "helper"]
    assert selected_calls and all(
        call in calls and call.target.status == "unknown" for call in selected_calls
    )
    assert all(edge in local.local.impact_graph.edges for edge in request.impact_graph.edges)


def test_frozen_ast_failure_keeps_changed_code_and_fixed_limitation(source_repo, monkeypatch):
    from genesis_ci.context import dependencies

    base = "TABLE = {'one': 2}\ndef wrapper(key):\n    return TABLE[key]\n"
    local = captured(
        source_repo, {"app.py": base}, {"app.py": base.replace("TABLE[key]", "TABLE[key] + 1")}
    )

    def unsupported_source(*args, **kwargs):
        raise SyntaxError("PRIVATE_SOURCE_MARKER")

    monkeypatch.setattr(dependencies.ast, "parse", unsupported_source)
    request = build_context(local.local, local.reader, request_id="parser-boundary")
    validate_request_against_local(local.local, request)
    assert {f.side for f in request.facts.functions if f.symbol_id == "app.py#wrapper"} == {
        "base",
        "head",
    }
    assert "PRIVATE_SOURCE_MARKER" not in request.model_dump_json()
    assert (
        "Frozen source could not be inspected for lexical dependency context."
        in request.missing_context
    )


def test_dependency_span_selection_preserves_trailing_blank_module_lines(source_repo):
    base = "TABLE = {'one': 2}\ndef wrapper(key):\n    return TABLE[key]\n\n"
    local = captured(
        source_repo, {"app.py": base}, {"app.py": base.replace("TABLE[key]", "TABLE[key] + 1")}
    )
    request = build_context(local.local, local.reader, request_id="trailing-blank-line")
    validate_request_against_local(local.local, request)
    for side in ("base", "head"):
        assert any(
            ref.side == side and "TABLE = {'one': 2}" in excerpt.text
            for ref, excerpt in zip(request.evidence, request.excerpts)
        )

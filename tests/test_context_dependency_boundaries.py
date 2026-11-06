"""Lexical context is bounded source evidence, never a resolved runtime value."""

import pytest
from genesis_ci.context import ContextOptions, build_context
from genesis_contracts.validation import validate_request_against_local
from test_context_dependencies import captured


def changed_function(expression, *, parameters="value"):
    return (
        f"def calculate({parameters}):\n"
        + "    print('detail')\n" * 30
        + f"    return {expression}\n"
    )


def unrelated_prefix():
    # Keep the whole module beyond the excerpt cap and fill ordinary low-priority
    # tail capacity before the canary. Only dependency prioritization can admit it.
    return "".join(f"UNUSED_{index} = '{'ordinary context ' * 7}'\n" for index in range(180))


def selected_request(source_repo, before, after, *, options=None):
    result = captured(source_repo, {"calculation.py": before}, {"calculation.py": after})
    request = build_context(
        result.local,
        result.reader,
        request_id="dependency-boundary",
        options=options or ContextOptions(input_token_budget=6000),
    )
    validate_request_against_local(result.local, request)
    assert {
        fact.side
        for fact in request.facts.functions
        if fact.symbol_id == "calculation.py#calculate"
    } == {
        "base",
        "head",
    }
    assert all(call in result.local.facts.calls for call in request.facts.calls)
    assert all(edge in result.local.impact_graph.edges for edge in request.impact_graph.edges)
    return request


@pytest.mark.parametrize("shadow_kind", ["parameter", "local"])
def test_shadowed_name_does_not_pull_unrelated_global_definition(source_repo, shadow_kind):
    global_source = "LIMIT = {'UNRELATED_GLOBAL_CANARY': 25}\n"
    body = changed_function(
        "LIMIT['value'] + 1", parameters="LIMIT" if shadow_kind == "parameter" else "value"
    )
    if shadow_kind == "local":
        body = body.replace("    return", "    LIMIT = {'value': value}\n    return")
    before = unrelated_prefix() + global_source + body
    request = selected_request(source_repo, before, before.replace("+ 1", "+ 2"))
    assert all("UNRELATED_GLOBAL_CANARY" not in item.text for item in request.excerpts)


def test_rebound_global_is_not_presented_as_a_unique_dependency(source_repo):
    before = unrelated_prefix() + (
        "LIMIT = {'FIRST_BINDING_CANARY': 1}\n"
        "LIMIT = {'SECOND_BINDING_CANARY': 2}\n" + changed_function("LIMIT.get(value, 0) + 1")
    )
    request = selected_request(source_repo, before, before.replace("+ 1", "+ 2"))
    assert all("FIRST_BINDING_CANARY" not in item.text for item in request.excerpts)
    assert all("SECOND_BINDING_CANARY" not in item.text for item in request.excerpts)


@pytest.mark.parametrize(
    "assignment,expression",
    [
        ("ITEMS = [RATE for RATE in range(3)]", "len(ITEMS) + value + 1"),
        ("ITEMS = lambda RATE: RATE", "ITEMS(value) + 1"),
    ],
)
def test_nested_expression_local_name_does_not_pull_unrelated_module_binding(
    source_repo, assignment, expression
):
    before = (
        unrelated_prefix()
        + "RATE = 'UNRELATED_DEFINITION_CANARY'\n"
        + assignment
        + "\n"
        + changed_function(expression)
    )
    request = selected_request(source_repo, before, before.replace("+ 1", "+ 2"))
    assert all("UNRELATED_DEFINITION_CANARY" not in item.text for item in request.excerpts)


@pytest.mark.parametrize("cyclic", [False, True])
def test_alias_dependencies_terminate_and_keep_existing_source_evidence(source_repo, cyclic):
    definitions = (
        "TABLE = ALIAS\nALIAS = TABLE\n" if cyclic else "TABLE = {'ordinary': 2.5}\nALIAS = TABLE\n"
    )
    before = definitions + changed_function("ALIAS.get(value, 0) + 1")
    request = selected_request(source_repo, before, before.replace("+ 1", "+ 2"))
    for side in ("base", "head"):
        source = "\n".join(
            excerpt.text
            for ref, excerpt in zip(request.evidence, request.excerpts, strict=True)
            if ref.side == side
        )
        assert "ALIAS = TABLE" in source
        assert ("TABLE = ALIAS" if cyclic else "TABLE = {'ordinary': 2.5}") in source
    assert len({ref.evidence_id for ref in request.evidence}) == len(request.evidence)
    assert len(request.excerpts) <= 80


@pytest.mark.parametrize("restriction", ["secret", "oversized"])
def test_referenced_definition_filters_preserve_changed_function_pair(source_repo, restriction):
    literal = (
        "'sk-proj-" + "SyntheticSecretValue" * 2 + "'"
        if restriction == "secret"
        else repr("LARGE_DEPENDENCY_CANARY" * 800)
    )
    before = "VALUE = " + literal + "\n" + changed_function("len(VALUE) + 1")
    request = selected_request(source_repo, before, before.replace("+ 1", "+ 2"))
    text = "\n".join(excerpt.text for excerpt in request.excerpts)
    assert "SyntheticSecretValue" not in text
    assert "LARGE_DEPENDENCY_CANARY" not in text
    assert request.truncated


def test_excluded_dependency_file_never_enters_request_while_other_change_survives(source_repo):
    body = changed_function("value + 1")
    excluded = "TABLE = {'EXCLUDED_CANARY': 5}\ndef lookup():\n    return TABLE\n"
    result = captured(
        source_repo,
        {"calculation.py": body, "private_helpers.py": excluded},
        {
            "calculation.py": body.replace("+ 1", "+ 2"),
            "private_helpers.py": excluded.replace("5}", "6}"),
        },
    )
    request = build_context(
        result.local,
        result.reader,
        request_id="excluded-dependency",
        options=ContextOptions(exclude_paths=("private_helpers.py",)),
    )
    validate_request_against_local(result.local, request)
    assert {
        fact.side
        for fact in request.facts.functions
        if fact.symbol_id == "calculation.py#calculate"
    } == {
        "base",
        "head",
    }
    assert all(ref.path != "private_helpers.py" for ref in request.evidence)
    assert all("EXCLUDED_CANARY" not in item.text for item in request.excerpts)

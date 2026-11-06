"""Callback graph source is context, not a proven runtime call graph."""

import pytest
from genesis_ci.context import ContextOptions, build_context
from genesis_ci.context.registration import registration_bundles
from genesis_contracts.validation import validate_request_against_local
from test_context_dependencies import captured


def application():
    return (
        "from framework import Graph, Model\n"
        + "# unrelated documentation\n" * 650
        + """model = Model()
def remember(value):
    return model.invoke(value)
def review(value):
    return remember(value)
def generate(value):
    return model.invoke(value)
def route(value):
    return 'review' if value else 'end'
builder = Graph()
builder.add_node('generate', generate)
builder.add_node('review', review)
builder.add_conditional_edges('generate', route)
workflow = builder.compile()
outer = Graph().add_node('workflow', workflow)
app = outer.compile()
def unrelated(value):
    return 'UNRELATED_GRAPH_CANARY'
other = Graph()
other.add_node('review', unrelated)
"""
    )


def test_same_module_registration_retains_callbacks_and_direct_helper(source_repo):
    base = application()
    result = captured(
        source_repo,
        {"app.py": base},
        {"app.py": base.replace("return remember(value)", "return remember(value + 1)")},
    )
    request = build_context(result.local, result.reader, request_id="registration")
    validate_request_against_local(result.local, request)
    for side in ("base", "head"):
        source = "\n".join(
            e.text for ref, e in zip(request.evidence, request.excerpts) if ref.side == side
        )
        for marker in (
            "def remember",
            "def generate",
            "def route",
            "builder.add_conditional_edges",
            "outer = Graph()",
        ):
            assert marker in source
    bundles, callbacks = registration_bundles(result.local, result.reader, {"app.py#review"}, [])
    selected = "\n".join(
        result.reader.read_excerpt(ref).text for bundle in bundles for ref in bundle
    )
    assert "UNRELATED_GRAPH_CANARY" not in selected
    assert "app.py#unrelated" not in callbacks
    assert all(edge in result.local.impact_graph.edges for edge in request.impact_graph.edges)
    registration = [call for call in request.facts.calls if call.expression == "builder.add_node"]
    assert registration and all(call.target.status == "unknown" for call in registration)


@pytest.mark.parametrize(
    "options",
    [
        ContextOptions(exclude_paths=("app.py",)),
        ContextOptions(max_excerpts=3, input_token_budget=5000),
    ],
)
def test_registration_obeys_filters_and_budgets(source_repo, options):
    base = application()
    result = captured(
        source_repo,
        {"app.py": base},
        {"app.py": base.replace("return remember(value)", "return remember(value + 1)")},
    )
    request = build_context(
        result.local, result.reader, request_id="bounded-registration", options=options
    )
    validate_request_against_local(result.local, request)
    assert request.truncated
    assert len(request.excerpts) <= options.max_excerpts
    if options.exclude_paths:
        assert not request.excerpts


def test_registration_does_not_connect_string_labels_or_other_builder(source_repo):
    base = application().replace(
        "builder.add_node('review', review)", "builder.add_node('review', 'review')"
    )
    result = captured(
        source_repo,
        {"app.py": base},
        {"app.py": base.replace("return remember(value)", "return remember(value + 1)")},
    )
    bundles, callbacks = registration_bundles(result.local, result.reader, {"app.py#review"}, [])
    assert not bundles
    assert callbacks == {"app.py#review"}


def test_registration_bound_is_explicit_and_never_executes_source(source_repo):
    base = (
        "from framework import Graph\n"
        "def review(value):\n    return value\n"
        "builder = Graph()\nbuilder.add_node('review', review)\n"
        + "builder.add_edge('a', 'b')\n" * 40
        + "raise RuntimeError('SOURCE_MUST_NOT_RUN')\n"
    )
    result = captured(
        source_repo, {"app.py": base}, {"app.py": base.replace("return value", "return value + 1")}
    )
    missing = []
    bundles, _ = registration_bundles(result.local, result.reader, {"app.py#review"}, missing)
    assert bundles
    assert "Callback registration context reached its 32-statement limit." in missing


def test_large_auxiliary_prompt_does_not_displace_workflow_callbacks(source_repo):
    base = (
        application()
        .replace(
            "model = Model()",
            "PROMPT = " + repr("Auxiliary instructions. " * 300) + "\nmodel = Model()",
        )
        .replace("return model.invoke(value)", "return model.invoke(PROMPT + str(value))")
    )
    result = captured(
        source_repo,
        {"app.py": base},
        {"app.py": base.replace("return remember(value)", "return remember(value + 1)")},
    )
    request = build_context(
        result.local,
        result.reader,
        request_id="entry-before-prompt",
        options=ContextOptions(input_token_budget=9000),
    )
    validate_request_against_local(result.local, request)
    selected = {(f.side, f.symbol_id) for f in request.facts.functions}
    assert {
        (side, "app.py#" + name)
        for side in ("base", "head")
        for name in ("review", "remember", "generate", "route")
    } <= selected


def test_small_model_tool_binding_survives_large_prompt_dependency(source_repo):
    base = (
        application()
        .replace(
            "model = Model()",
            "PROMPT = "
            + repr("Auxiliary instructions. " * 300)
            + "\ntools = ['deliver', 'stop']\nmodel = Model().bind_tools(tools)",
        )
        .replace("return model.invoke(value)", "return model.invoke(PROMPT + str(value))")
    )
    result = captured(
        source_repo,
        {"app.py": base},
        {"app.py": base.replace("return remember(value)", "return remember(value + 1)")},
    )
    request = build_context(
        result.local,
        result.reader,
        request_id="binding-before-text",
        options=ContextOptions(input_token_budget=9000),
    )
    validate_request_against_local(result.local, request)
    for side in ("base", "head"):
        text = "\n".join(
            e.text for r, e in zip(request.evidence, request.excerpts) if r.side == side
        )
        assert "tools = ['deliver', 'stop']" in text
        assert "model = Model().bind_tools(tools)" in text
        assert "def generate" in text

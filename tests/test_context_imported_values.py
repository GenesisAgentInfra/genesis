"""Imported values are frozen source context, never evaluated configuration."""

import pytest
from genesis_ci.context import ContextOptions, build_context
from test_context_dependencies import captured
from test_context_direct_callees import assert_frozen_evidence

OPTIONS = (
    "from dataclasses import dataclass\n"
    "@dataclass\nclass RenderOptions:\n    prefix: str = 'internal: '\n"
    "options = RenderOptions()\n"
)


def test_values_sharing_one_import_keep_both_definition_bundles(source_repo):
    base = "from tuning import LEFT, RIGHT\ndef render(text):\n    return LEFT + RIGHT + text\n"
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": "LEFT = 'left:'\nRIGHT = ':right'\n"},
        {"entry.py": base.replace("LEFT + RIGHT + text", "LEFT + text + RIGHT")},
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="shared-import", options=options
    )
    assert_frozen_evidence(result, request, options)
    for side in ("base", "head"):
        text = "\n".join(
            e.text for ref, e in zip(request.evidence, request.excerpts) if ref.side == side
        )
        assert "LEFT = 'left:'" in text
        assert "RIGHT = ':right'" in text


def test_imported_definition_includes_base_class_and_constructor_defaults(source_repo):
    base = "from tuning import options\ndef render(text):\n    return options.prefix + text\n"
    tuning = (
        "LABEL = 'configured:'\n"
        "class PrefixDefaults:\n    prefix = LABEL\n"
        "class RenderOptions(PrefixDefaults):\n    pass\n"
        "def make_options(factory=RenderOptions):\n    return factory()\n"
        "options = make_options()\n"
    )
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": tuning},
        {"entry.py": base.replace("options.prefix + text", "text + options.prefix")},
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="definition-closure", options=options
    )
    assert_frozen_evidence(result, request, options)
    for side in ("base", "head"):
        text = "\n".join(
            e.text for ref, e in zip(request.evidence, request.excerpts) if ref.side == side
        )
        for definition in (
            "LABEL = 'configured:'",
            "class PrefixDefaults:",
            "class RenderOptions(PrefixDefaults):",
            "def make_options(factory=RenderOptions):",
            "options = make_options()",
        ):
            assert definition in text


def test_filtered_value_cycle_cannot_replace_priority_changed_body(source_repo):
    base = (
        "from tuning import RENDERERS\ndef render(text):\n    return RENDERERS[0](text)\n"
        + "# unrelated module notes\n" * 600
    )
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": "from entry import render\nRENDERERS = (render,)\n"},
        {"entry.py": base.replace("RENDERERS[0](text)", "RENDERERS[0](text.strip())")},
    )
    options = ContextOptions(exclude_paths=("tuning.py",))
    request = build_context(
        result.local, result.reader, request_id="filtered-cycle", options=options
    )
    assert_frozen_evidence(result, request, options)
    assert {
        fact.side for fact in request.facts.functions if fact.symbol_id == "entry.py#render"
    } == {"base", "head"}
    assert all(ref.path != "tuning.py" for ref in request.evidence)


@pytest.mark.parametrize(
    ("binding", "expression"),
    [
        ("from .tuning import options as style", "style.prefix"),
        ("from display.tuning import options", "options.prefix"),
        ("import display.tuning as tuning", "tuning.options.prefix"),
        ("from . import tuning", "tuning.options.prefix"),
    ],
)
def test_imported_value_and_constructor_source_survive_unchanged_callers(
    source_repo, binding, expression
):
    def source(delta):
        return (
            binding
            + f"\ndef render(text):\n    return {expression} + text + {delta!r}\n\n"
            + "".join(
                f'def caller_{i}(text):\n    """'
                + "Explain the rendering interface. " * 60
                + '"""\n    return render(text)\n\n'
                for i in range(18)
            )
        )

    result = captured(
        source_repo,
        {"display/__init__.py": "", "display/entry.py": source("!"), "display/tuning.py": OPTIONS},
        {"display/entry.py": source("?")},
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="imported-value", options=options
    )
    assert_frozen_evidence(result, request, options)
    selected = {ref.evidence_id: ref for ref in request.evidence}
    for side in ("base", "head"):
        text = "\n".join(e.text for e in request.excerpts if selected[e.evidence_id].side == side)
        assert binding in text
        assert "class RenderOptions:" in text
        assert "prefix: str = 'internal: '" in text
        assert "options = RenderOptions()" in text
    assert request.truncated
    assert all(edge in result.local.impact_graph.edges for edge in request.impact_graph.edges)


def test_imported_constant_tracks_both_frozen_versions_and_never_imports_customer_code(source_repo):
    base = "from tuning import SEPARATOR\ndef render(parts):\n    return SEPARATOR.join(parts)\n"
    result = captured(
        source_repo,
        {
            "entry.py": base,
            "tuning.py": "SEPARATOR = '::'\nraise AssertionError('do not import')\n",
        },
        {
            "entry.py": base.replace("join(parts)", "join(parts).strip()"),
            "tuning.py": "SEPARATOR = '|~|'\nraise AssertionError('do not import')\n",
        },
    )
    options = ContextOptions(input_token_budget=9000)
    request = build_context(
        result.local, result.reader, request_id="frozen-values", options=options
    )
    assert_frozen_evidence(result, request, options)
    refs = {ref.evidence_id: ref for ref in request.evidence}
    for side, value in (("base", "::"), ("head", "|~|")):
        assert any(
            refs[e.evidence_id].side == side and f"SEPARATOR = {value!r}" in e.text
            for e in request.excerpts
        )


@pytest.mark.parametrize(
    "kind", ["external", "ambiguous", "conditional", "rebound", "dynamic", "shadowed"]
)
def test_uncertain_imported_values_are_not_presented_as_resolved_dependencies(source_repo, kind):
    base = "from tuning import SEPARATOR\ndef render(parts):\n    return SEPARATOR.join(parts)\n"
    files = {"entry.py": base}
    if kind == "ambiguous":
        files.update({"a/tuning.py": "SEPARATOR = 'a'\n", "b/tuning.py": "SEPARATOR = 'b'\n"})
    elif kind == "conditional":
        files["tuning.py"] = "if runtime_switch():\n    SEPARATOR = 'conditional'\n"
    elif kind == "rebound":
        files["tuning.py"] = "SEPARATOR = 'first'\nSEPARATOR = 'second'\n"
    elif kind == "dynamic":
        files["tuning.py"] = "SEPARATOR = 'initial'\nexec(runtime_source())\n"
    elif kind == "shadowed":
        files["tuning.py"] = "SEPARATOR = 'unused-global'\n"
        base = base.replace("render(parts)", "render(parts, SEPARATOR)")
        files["entry.py"] = base
    result = captured(
        source_repo, files, {"entry.py": base.replace("join(parts)", "join(parts).strip()")}
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="uncertain-values", options=options
    )
    assert_frozen_evidence(result, request, options)
    assert not any(ref.path.endswith("tuning.py") for ref in request.evidence)
    assert all(edge in result.local.impact_graph.edges for edge in request.impact_graph.edges)
    if kind in {"ambiguous", "conditional", "rebound", "dynamic"}:
        assert any("Imported-value" in reason for reason in request.missing_context)


@pytest.mark.parametrize("restriction", ["excluded", "secret", "large", "count"])
def test_imported_value_context_respects_existing_filters_and_limits(source_repo, restriction):
    value = "synthetic" if restriction != "large" else "source context " * 1000
    if restriction == "secret":
        value = "sk-proj-" + "SyntheticPrivateValue" * 2
    base = "from tuning import PREFIX\ndef render(text):\n    return PREFIX + text\n"
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": f"PREFIX = {value!r}\n"},
        {"entry.py": base.replace("PREFIX + text", "text + PREFIX")},
    )
    options = ContextOptions(
        exclude_paths=("tuning.py",) if restriction == "excluded" else (),
        max_excerpts=2 if restriction == "count" else 80,
    )
    log = []
    request = build_context(
        result.local, result.reader, request_id="bounded-values", options=options, selection_log=log
    )
    assert_frozen_evidence(result, request, options)
    assert not any(ref.path == "tuning.py" for ref in request.evidence)
    assert request.truncated
    target_ids = {ref.evidence_id for ref in result.local.evidence if ref.path == "tuning.py"}
    assert any(
        entry["decision"] == "omitted" and target_ids.intersection(entry["evidence_ids"])
        for entry in log
    )


def test_definition_header_lambda_locals_do_not_pull_unrelated_imports(source_repo):
    base = "from tuning import options\ndef render(text):\n    return options.prefix + text\n"
    tuning = (
        "from unrelated import phantom\n"
        "class RenderOptions:\n    prefix = 'prefix:'\n"
        "def make(factory=(lambda phantom: phantom)(RenderOptions)):\n    return factory()\n"
        "options = make()\n"
    )
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": tuning, "unrelated.py": "phantom = 'UNRELATED_CANARY'\n"},
        {"entry.py": base.replace("options.prefix + text", "text + options.prefix")},
    )
    options = ContextOptions()
    request = build_context(result.local, result.reader, request_id="header-scope", options=options)
    assert_frozen_evidence(result, request, options)
    assert any("class RenderOptions:" in e.text for e in request.excerpts)
    assert not any(ref.path == "unrelated.py" for ref in request.evidence)


def test_dynamic_package_binding_does_not_fall_back_to_same_named_child_module(source_repo):
    base = "from palette import STYLE\ndef render(text):\n    return STYLE + text\n"
    result = captured(
        source_repo,
        {
            "entry.py": base,
            "palette/__init__.py": "STYLE = 'actual:'\ndef debugging():\n    return locals()\n",
            "palette/STYLE.py": "WRONG_CANDIDATE = 'unrelated'\n",
        },
        {"entry.py": base.replace("STYLE + text", "text + STYLE")},
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="dynamic-package", options=options
    )
    assert_frozen_evidence(result, request, options)
    assert not any(ref.path.startswith("palette/") for ref in request.evidence)
    assert any("dynamic module" in note for note in request.missing_context)


def test_unanalyzed_module_can_still_make_a_value_import_ambiguous(source_repo):
    base = "from tuning import SEPARATOR\ndef render(parts):\n    return SEPARATOR.join(parts)\n"
    result = captured(
        source_repo,
        {
            "entry.py": base,
            "a/tuning.py": "SEPARATOR = 'known:'\n",
            "b/tuning.py": "def invalid syntax\n",
        },
        {"entry.py": base.replace("join(parts)", "join(parts).strip()")},
    )
    options = ContextOptions()
    request = build_context(
        result.local, result.reader, request_id="unanalyzed-shadow", options=options
    )
    assert_frozen_evidence(result, request, options)
    assert not any(ref.path.endswith("tuning.py") for ref in request.evidence)
    assert any("ambiguous local module" in note for note in request.missing_context)


@pytest.mark.parametrize("scope", ["module", "method", "class-shadow"])
def test_root_callable_defaults_respect_the_enclosing_binding_scope(source_repo, scope):
    binding = "from tuning import PREFIX\n"
    body = "def render(text, prefix=PREFIX):\n    return prefix + text\n"
    if scope != "module":
        body = (
            "class Renderer:\n"
            + ("    PREFIX = 'class-local:'\n" if scope == "class-shadow" else "")
            + "\n".join("    " + line for line in body.splitlines())
            + "\n"
        )
    base = binding + body
    result = captured(
        source_repo,
        {"entry.py": base, "tuning.py": "PREFIX = 'from-default:'\n"},
        {"entry.py": base.replace("prefix + text", "prefix + text.strip()")},
    )
    options = ContextOptions()
    request = build_context(result.local, result.reader, request_id="root-default", options=options)
    assert_frozen_evidence(result, request, options)
    if scope == "class-shadow":
        assert not any(ref.path == "tuning.py" for ref in request.evidence)
    else:
        assert {ref.side for ref in request.evidence if ref.path == "tuning.py"} == {"base", "head"}

"""Changed bodies retain their statically evidenced integration context."""

import pytest
from genesis_ci.context import ContextOptions, build_context
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_request_against_local
from test_git_snapshot import git


def captured(source_repo, base, head):
    for name, text in base.items():
        (source_repo / name).parent.mkdir(parents=True, exist_ok=True)
        (source_repo / name).write_text(text)
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    for name, text in head.items():
        (source_repo / name).write_text(text)
    return analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))


def test_resolved_await_caller_retains_both_versions_before_call_details(source_repo):
    base = (
        "async def check(amount):\n" + "    print('detail')\n" * 30 + "    return amount >= 100\n"
    )
    local = captured(
        source_repo,
        {
            "policy.py": base,
            "entry.py": "from policy import check\nasync def submit(amount):\n    return await check(amount)\n",
        },
        {"policy.py": base.replace(">=", ">")},
    )
    request = build_context(
        local.local,
        local.reader,
        request_id="await-caller",
        options=ContextOptions(input_token_budget=4000),
    )
    validate_request_against_local(local.local, request)
    assert {f.side for f in request.facts.functions if f.symbol_id == "entry.py#submit"} == {
        "base",
        "head",
    }
    assert {f.side for f in request.facts.functions if f.symbol_id == "policy.py#check"} == {
        "base",
        "head",
    }


@pytest.mark.parametrize("same_file", [False, True])
def test_callback_registration_source_is_context_without_claiming_runtime_edges(
    source_repo, same_file
):
    base = "def route(state):\n    return 'accept' if state['amount'] >= 100 else 'review'\n"
    wiring = "from framework import Workflow\nworkflow = Workflow()\nworkflow.add_step('policy', route)\nworkflow.connect('policy', 'finish')\n"
    files = (
        {"policy.py": base + wiring}
        if same_file
        else {"policy.py": base, "entry.py": "from policy import route\n" + wiring}
    )
    files["unrelated.py"] = "def unrelated():\n    return 'UNRELATED_CONTEXT_CANARY'\n"
    changed = files["policy.py"].replace(">=", ">")
    local = captured(source_repo, files, {"policy.py": changed})
    request = build_context(local.local, local.reader, request_id="callback-context")
    validate_request_against_local(local.local, request)
    selected = "\n".join(excerpt.text for excerpt in request.excerpts)
    assert "workflow.add_step('policy', route)" in selected
    assert "workflow.connect('policy', 'finish')" in selected
    assert "UNRELATED_CONTEXT_CANARY" not in selected
    assert all(edge in local.local.impact_graph.edges for edge in request.impact_graph.edges)
    # Supplying registration source must not promote its unresolved receiver.
    registrations = [
        call for call in local.local.facts.calls if call.expression == "workflow.add_step"
    ]
    assert registrations and all(call.target.status == "unknown" for call in registrations)


@pytest.mark.parametrize(
    "import_line",
    [
        "from .policy import route as callback",
        "import package.policy as policy",
        "from . import policy",
    ],
)
def test_import_context_supports_alias_module_and_relative_spelling(source_repo, import_line):
    base = "def route(value):\n    return value >= 100\n"
    entry = (
        import_line
        + "\nregister('route', "
        + ("callback" if "callback" in import_line else "policy.route")
        + ")\n"
    )
    local = captured(
        source_repo,
        {"package/__init__.py": "", "package/policy.py": base, "package/entry.py": entry},
        {"package/policy.py": base.replace(">=", ">")},
    )
    request = build_context(local.local, local.reader, request_id="import-forms")
    validate_request_against_local(local.local, request)
    assert any(e.text == entry.rstrip("\n") for e in request.excerpts)


def test_ambiguous_import_suffix_does_not_select_an_arbitrary_module(source_repo):
    base = "def route(value):\n    return value >= 100\n"
    local = captured(
        source_repo,
        {
            "a/policy.py": base,
            "b/policy.py": base,
            "entry.py": "from policy import route\nregister(route)\n",
        },
        {"a/policy.py": base.replace(">=", ">")},
    )
    request = build_context(local.local, local.reader, request_id="ambiguous-module")
    assert "entry.py" not in {r.path for r in request.evidence}
    assert {f.side for f in request.facts.functions if f.symbol_id == "a/policy.py#route"} == {
        "base",
        "head",
    }


@pytest.mark.parametrize("restriction", ["excluded", "secret", "large"])
def test_import_context_keeps_existing_filters_and_prioritizes_changed_bodies(
    source_repo, restriction
):
    base = "def route(value):\n    return value >= 100\n"
    entry = "from policy import route\nregister(route)\n"
    if restriction == "secret":
        entry += "credential = 'sk-proj-" + "SyntheticPrivateValue" * 2 + "'\n"
    if restriction == "large":
        entry += "# explanatory source context\n" * 500
    local = captured(
        source_repo, {"policy.py": base, "entry.py": entry}, {"policy.py": base.replace(">=", ">")}
    )
    options = ContextOptions(exclude_paths=("entry.py",) if restriction == "excluded" else ())
    request = build_context(local.local, local.reader, request_id="bounded-module", options=options)
    validate_request_against_local(local.local, request)
    assert "entry.py" not in {r.path for r in request.evidence}
    assert {f.side for f in request.facts.functions if f.symbol_id == "policy.py#route"} == {
        "base",
        "head",
    }
    assert request.truncated
    assert any(
        "supporting module context omitted" in message for message in request.missing_context
    )

"""Resolved local dependencies must not wait behind every unchanged caller."""

import json

import pytest
from genesis_ci.context import ContextOptions, build_context
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.models import project_analysis_request
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_request_against_local
from genesis_tokenizer import count_fragments
from test_context_dependencies import captured
from test_git_snapshot import git, write


def assert_frozen_evidence(result, request, options):
    validate_request_against_local(result.local, request)
    original = {ref.evidence_id: ref for ref in result.local.evidence}
    assert all(original[ref.evidence_id] == ref for ref in request.evidence)
    assert all(result.reader.read_excerpt(item.evidence_id) == item for item in request.excerpts)
    assert len(request.excerpts) <= options.max_excerpts
    assert all(len(item.text) <= options.max_excerpt_chars for item in request.excerpts)
    payload = json.dumps(
        project_analysis_request(request), ensure_ascii=False, separators=(",", ":")
    )
    assert count_fragments((payload,)) <= options.payload_token_budget
    assert len(request.model_dump_json().encode("utf-8")) <= 524_288


def test_direct_callee_survives_many_unchanged_callers(source_repo):
    detail = (
        "This callback validates an incoming request and forwards it to the shared operation. " * 25
    )

    def source(delta):
        return (
            "from helper import audit_result\n\n"
            f"def changed(value):\n    return audit_result(value + {delta})\n\n"
            + "".join(
                f'def caller_{i:02d}(value):\n    """{detail}"""\n    return changed(value)\n\n'
                for i in range(18)
            )
        )

    result = captured(
        source_repo,
        {
            "a_flow.py": source(1),
            "helper.py": (
                "def audit_result(value):\n"
                "    if value < 0:\n        raise ValueError('negative value')\n"
                "    return {'accepted': value}\n"
            ),
        },
        {"a_flow.py": source(2)},
    )
    options = ContextOptions()
    request = build_context(result.local, result.reader, request_id="fan-in", options=options)
    assert_frozen_evidence(result, request, options)
    functions = {(fact.side.value, fact.symbol_id) for fact in request.facts.functions}
    assert {
        (side, symbol)
        for side in ("base", "head")
        for symbol in ("a_flow.py#changed", "helper.py#audit_result")
    } <= functions
    # This deliberately bounded request cannot retain every unchanged caller.
    assert request.truncated
    assert any("budget" in reason for reason in request.missing_context)


def test_awaited_direct_callee_pair_precedes_unchanged_caller_pair(source_repo):
    base = (
        "from helper import check\nasync def changed(value):\n    return await check(value + 1)\n"
    )
    result = captured(
        source_repo,
        {
            "app.py": base,
            "entry.py": "from app import changed\nasync def entry(value):\n    return await changed(value)\n",
            "helper.py": "async def check(value):\n    return {'accepted': value}\n",
        },
        {"app.py": base.replace("value + 1", "value + 2")},
    )
    options = ContextOptions(max_excerpts=4)
    request = build_context(result.local, result.reader, request_id="awaited", options=options)
    assert_frozen_evidence(result, request, options)
    assert {
        (fact.side.value, fact.symbol_id)
        for fact in request.facts.functions
        if fact.kind == "function"
    } == {
        (side, symbol)
        for side in ("base", "head")
        for symbol in ("app.py#changed", "helper.py#check")
    }


@pytest.mark.parametrize("resolution", ["dynamic", "ambiguous-import"])
def test_unknown_callee_does_not_select_an_arbitrary_local_body(source_repo, resolution):
    helper = "def finish(value):\n    return {'accepted': value}\n"
    write(source_repo, "helper.py", helper)
    if resolution == "ambiguous-import":
        base = "from helper import finish\ndef changed(value):\n    return finish(value + 1)\n"
        write(source_repo, "duplicate/helper.py", helper.replace("accepted", "alternative"))
        python_options = PythonOptions(source_roots=(".", "duplicate"))
    else:
        base = "def changed(value, callback):\n    return callback(value + 1)\n"
        python_options = PythonOptions()
    write(source_repo, "app.py", base)
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "synthetic baseline")
    write(source_repo, "app.py", base.replace("value + 1", "value + 2"))
    result = analyze_snapshot(
        capture_snapshot(source_repo, SnapshotSpec(base="HEAD")), python_options
    )
    calls = [call for call in result.local.facts.calls if call.caller_symbol_id == "app.py#changed"]
    assert calls and all(call.target.status == "unknown" for call in calls)
    options = ContextOptions()
    request = build_context(result.local, result.reader, request_id="unknown", options=options)
    assert_frozen_evidence(result, request, options)
    assert not any(ref.path.endswith("helper.py") for ref in request.evidence)
    assert all(edge in result.local.impact_graph.edges for edge in request.impact_graph.edges)
    assert all(call.target.status == "unknown" for call in request.facts.calls)

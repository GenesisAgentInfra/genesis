"""Behavior views must preserve branch evidence without inventing execution."""

import json

import pytest
from client_fixtures import input_fixture
from genesis_ci.behavior import build_behavior_view
from genesis_ci.context import ContextOptions, build_context, preview_request
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot, save_analysis
from genesis_contracts.models import (
    AnalysisRequest,
    EvidenceSide,
    LocalAnalysis,
    behavior_id_for,
    project_analysis_request,
)
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import (
    validate_analysis_request,
    validate_local_analysis,
    validate_request_against_local,
)
from test_git_snapshot import git


def analyze(source_repo, before, after=None):
    (source_repo / "app.py").write_bytes((before if after is not None else "# baseline\n").encode())
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_bytes((after if after is not None else before).encode())
    return analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))


def units(result, side="head", symbol="app.py#route"):
    return [
        unit
        for unit in result.local.behavior_view.units
        if unit.side == side and unit.symbol_id == symbol
    ]


def guards(unit):
    return [(item.text, item.truth) for item in unit.conditions]


def test_threshold_paths_preserve_each_revision_and_state_update(source_repo, tmp_path):
    def source(operator):
        return (
            "def route(expense):\n"
            f"    if expense['amount'] {operator} 100:\n"
            "        expense['status'] = 'pending_review'\n"
            "        return 'NEEDS_REVIEW'\n"
            "    expense['status'] = 'approved'\n"
            "    return 'AUTO_APPROVE'\n"
        )

    result = analyze(source_repo, source(">="), source(">"))
    head, base = units(result), units(result, "base")
    assert len(head) == len(base) == 4
    assert {u.result.kind for u in head} == {"state_update", "return"}
    review, auto = [u for u in head if u.result.kind == "return"]
    assert guards(review) == [("expense['amount'] > 100", True)]
    assert guards(auto) == [("expense['amount'] > 100", False)]
    assert [op.text for op in review.operations] == ["expense['status'] = 'pending_review'"]
    assert [op.text for op in auto.operations] == ["expense['status'] = 'approved'"]
    assert all(">=" in u.conditions[0].text for u in base)
    assert not ({u.unit_id for u in head} & {u.unit_id for u in base})
    request = build_context(result.local, result.reader, request_id="behavior")
    validate_request_against_local(result.local, request)
    assert len(request.behavior_view.units) == 8
    assert request.behavior_view.omitted_units == 0
    assert project_analysis_request(request)["selected_analysis"]["behavior_view"]["version"] == "1"
    destination = tmp_path / "saved"
    save_analysis(result, destination)
    assert json.loads(
        (destination / "behavior-view.json").read_text()
    ) == result.local.behavior_view.model_dump(mode="json")


def test_early_return_and_branch_merge_keep_separate_operations(source_repo):
    result = analyze(
        source_repo,
        """def route(ok, mode):
    if not ok:
        raise ValueError('invalid')
    if mode:
        value = one()
    else:
        value = two()
    return value
""",
    )
    paths = units(result)
    assert len(paths) == 3
    assert paths[0].result.kind == "raise"
    assert guards(paths[0]) == [("not ok", True)]
    returns = {unit.conditions[-1].truth: unit for unit in paths if unit.result.kind == "return"}
    assert guards(returns[True]) == [("not ok", False), ("mode", True)]
    assert guards(returns[False]) == [("not ok", False), ("mode", False)]
    assert [op.text for op in returns[True].operations] == ["value = one()"]
    assert [op.text for op in returns[False].operations] == ["value = two()"]


@pytest.mark.parametrize(
    "body",
    [
        "    while True:\n        break\n    return 1\n",
        "    match x:\n        case 1:\n            return True\n",
        "    if (yield True):\n        return 1\n",
    ],
)
def test_unsupported_control_never_leaks_a_misleading_partial_path(source_repo, body):
    result = analyze(source_repo, "def route(x):\n" + body)
    paths = units(result)
    assert len(paths) == 1 and paths[0].result is None
    assert not paths[0].operations and not paths[0].conditions
    assert paths[0].limitations
    assert result.local.facts.functions
    validate_analysis_request(build_context(result.local, result.reader, request_id="unsupported"))


@pytest.mark.parametrize(
    "body, kind",
    [
        ("    async with acquire():\n        return await work()\n", "context_region"),
        ("    try:\n        return 1\n    finally:\n        return 2\n", "exception_region"),
        (
            "    try:\n        await work()\n    except Exception:\n        return 'failed'\n    else:\n        return 'done'\n",
            "exception_region",
        ),
    ],
)
def test_regions_preserve_complete_source_without_inventing_outcomes(source_repo, body, kind):
    result = analyze(
        source_repo,
        "async def route():\n    before = 1\n" + body + "    while True:\n        break\n",
    )
    assert result.local.behavior_view.version == "2"
    unit = units(result)[0]
    assert unit.result is None and unit.limitations
    assert unit.operations[0].text == "before = 1"
    assert unit.operations[1].kind == kind
    assert unit.operations[1].text.strip() == body.strip()
    request = build_context(result.local, result.reader, request_id="regions")
    validate_analysis_request(request)
    old_server = build_context(
        result.local,
        result.reader,
        request_id="legacy",
        options=ContextOptions(behavior_view_versions=("1",)),
    )
    assert old_server.behavior_view is None
    assert old_server.excerpts
    with pytest.raises(ValueError, match="require behavior-view version 2"):
        validate_analysis_request(
            request.model_copy(
                update={"behavior_view": request.behavior_view.model_copy(update={"version": "1"})}
            )
        )
    with pytest.raises(ValueError, match="text differs"):
        validate_analysis_request(
            rewrite_unit(
                request,
                unit.model_copy(
                    update={
                        "operations": (
                            unit.operations[1].model_copy(update={"text": "return 'success'"}),
                        )
                    }
                ),
            )
        )


def test_destructuring_preserves_order_without_asserting_element_types(source_repo):
    result = analyze(
        source_repo,
        "async def route(work):\n    data, [image, *other] = await work()\n    return data\n",
    )
    unit = units(result)[0]
    assert unit.operations[0].text == "data, [image, *other] = await work()"
    assert unit.result.text == "return data"
    validate_analysis_request(build_context(result.local, result.reader, request_id="unpack"))


@pytest.mark.parametrize(
    "text",
    [
        "def route(x):\r\n    if x:\r\n        return '你好'\r\n    return 'no'\r\n",
        "\ufeffdef route(x): return '你好' if x else 'no'\n",
        "class Demo:\n    def route(self, x):\n        if x: return 1\n        return 2\n",
        "def route(x):\n    if x: one(); return 'yes'\n    elif x is None: return 'none'\n    return 'no'\n",
    ],
)
def test_exact_ranges_support_unicode_columns_crlf_and_compact_suites(source_repo, text):
    result = analyze(source_repo, text)
    assert result.local.behavior_view.units
    assert any(u.result is not None for u in result.local.behavior_view.units)
    validate_analysis_request(build_context(result.local, result.reader, request_id="ranges"))


def test_view_is_derived_without_reparsing_or_changing_original_analysis(source_repo, monkeypatch):
    result = analyze(source_repo, "def route(x):\n    return x\n")
    before = result.extraction.analysis.model_dump_json()
    evidence = result.reader.evidence_catalog()

    def forbid(*args, **kwargs):
        raise AssertionError("behavior building must reuse the existing parse")

    monkeypatch.setattr("libcst.parse_module", forbid)
    (source_repo / "app.py").write_text("invalid later working tree")
    assert build_behavior_view(result.extraction) == result.local.behavior_view
    assert result.extraction.analysis.model_dump_json() == before
    assert result.reader.evidence_catalog() == evidence


def rewrite_unit(request, unit):
    unit = unit.model_copy(update={"unit_id": behavior_id_for(request.snapshot_id, unit)})
    return request.model_copy(
        update={"behavior_view": request.behavior_view.model_copy(update={"units": (unit,)})}
    )


def test_service_rejects_fabricated_text_foreign_side_and_out_of_scope_ranges(source_repo):
    result = analyze(source_repo, "def route(x):\n    return x\n")
    request = build_context(result.local, result.reader, request_id="integrity")
    unit = request.behavior_view.units[0]
    fabricated = unit.model_copy(
        update={"result": unit.result.model_copy(update={"text": "return 'invented'"})}
    )
    with pytest.raises(ValueError, match="text differs"):
        validate_analysis_request(rewrite_unit(request, fabricated))
    with pytest.raises(ValueError, match="owning-function|side and path"):
        validate_analysis_request(
            rewrite_unit(
                request,
                unit.model_copy(
                    update={"side": EvidenceSide.base if unit.side == "head" else EvidenceSide.head}
                ),
            )
        )
    bad_span = unit.result.range.model_copy(update={"end_line": 100})
    with pytest.raises(ValueError, match="outside"):
        validate_analysis_request(
            rewrite_unit(
                request,
                unit.model_copy(
                    update={"result": unit.result.model_copy(update={"range": bad_span})}
                ),
            )
        )
    changed = unit.model_copy(update={"limitations": ("changed claim",)})
    with pytest.raises(ValueError, match="changed local behavior"):
        validate_request_against_local(result.local, rewrite_unit(request, changed))
    duplicate = request.model_copy(
        update={"behavior_view": request.behavior_view.model_copy(update={"units": (unit, unit)})}
    )
    with pytest.raises(ValueError, match="duplicate behavior"):
        validate_analysis_request(duplicate)


def test_budget_and_exclusions_keep_complete_units_and_original_source(source_repo):
    text = "def route(x):\n" + "    x = x + 1\n" * 25 + "    return x\n"
    result = analyze(source_repo, text, text.replace("+ 1", "+ 2"))
    # Enough for both original function bodies, but not both expanded views.
    options = ContextOptions(input_token_budget=6000)
    request = build_context(result.local, result.reader, request_id="budget", options=options)
    validate_request_against_local(result.local, request)
    assert {f.side.value for f in request.facts.functions if f.kind == "function"} == {
        "base",
        "head",
    }
    assert request.behavior_view.omitted_units > 0
    assert "omitted" in preview_request(request)
    assert all(
        set(u.scope_evidence_ids) <= {r.evidence_id for r in request.evidence}
        for u in request.behavior_view.units
    )
    excluded = build_context(
        result.local,
        result.reader,
        request_id="excluded",
        options=ContextOptions(exclude_paths=("app.py",)),
    )
    assert not excluded.behavior_view.units
    assert excluded.behavior_view.omitted_units == len(result.local.behavior_view.units)


def test_sensitive_source_does_not_leak_through_behavior_text(source_repo):
    result = analyze(
        source_repo,
        "def route():\n    api_key = 'sk-example12345678901234567890'\n    return api_key\n",
    )
    request = build_context(result.local, result.reader, request_id="sensitive")
    assert not request.behavior_view.units
    assert "sk-example12345678901234567890" not in request.model_dump_json()


def test_expansion_budget_falls_back_without_affecting_existing_facts(source_repo):
    text = "def route(x):\n" + "    if x:\n        x = x + 1\n" * 8 + "    return x\n"
    result = analyze(source_repo, text)
    paths = units(result)
    assert len(paths) == 1 and paths[0].result is None
    assert "budget" in paths[0].limitations[0]
    assert result.local.facts.conditions


def test_local_unit_cap_prioritizes_changed_symbols_on_both_sides(source_repo, monkeypatch):
    monkeypatch.setattr("genesis_ci.behavior.MAX_UNITS", 2)
    before = "def earlier():\n    return 0\n\ndef route():\n    return 1\n"
    result = analyze(source_repo, before, before.replace("return 1", "return 2"))
    assert {(unit.side.value, unit.symbol_id) for unit in result.local.behavior_view.units} == {
        ("base", "app.py#route"),
        ("head", "app.py#route"),
    }
    assert result.local.behavior_view.omitted_units == 2


def test_legacy_payloads_and_public_report_remain_compatible():
    data = input_fixture()
    local = LocalAnalysis.model_validate(data["local_analysis"])
    request = AnalysisRequest.model_validate(data["request"])
    validate_local_analysis(local)
    validate_analysis_request(request)
    assert local.behavior_view is request.behavior_view is None
    assert "behavior_view" not in local.model_dump()
    assert "behavior_view" not in request.model_dump()

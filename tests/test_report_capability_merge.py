"""Incomplete local analysis must not erase supported semantic review prose."""

import json
from pathlib import Path

import pytest
from genesis_ci.report import assemble_report, render_markdown, render_review_markdown
from genesis_contracts.models import (
    AnalysisRequest,
    CapabilityStatus,
    LocalAnalysis,
    SemanticAnalysisResponse,
)


def source_reports(local_status="insufficient_context", remote_status="analyzed"):
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/normal-five-sections/semantic.json").read_text()
    )
    local = LocalAnalysis.model_validate(data["local_analysis"])
    request = AnalysisRequest.model_validate(data["request"])
    semantic = SemanticAnalysisResponse.model_validate(data["semantic_response"])
    local = local.model_copy(
        update={
            "capabilities": local.capabilities.model_copy(
                update={
                    "cost_risk": CapabilityStatus(
                        status=local_status,
                        reason="Dynamic provider dispatch remains unresolved.",
                        analyzed_scope="Local call sites in the supplied snapshot.",
                    )
                }
            )
        }
    )
    semantic = semantic.model_copy(
        update={
            "section_status": semantic.section_status.model_copy(
                update={
                    "cost_risk": CapabilityStatus(
                        status=remote_status,
                        reason="The selected branch waits for the query result before returning.",
                        analyzed_scope="The selected function and its early return.",
                    )
                }
            )
        }
    )
    return local, request, semantic


def test_incomplete_report_keeps_local_limits_and_semantic_analysis_in_public_outputs():
    local, request, semantic = source_reports()
    originals = (local.model_dump_json(), request.model_dump_json(), semantic.model_dump_json())
    report = assemble_report(local, request, semantic)
    assert report.analysis_status == "partial"
    assert report.section_status.cost_risk.status == "insufficient_context"
    for output in (
        report.model_dump_json(),
        render_markdown(report),
        render_review_markdown(report, local),
    ):
        for source in (local.capabilities.cost_risk, semantic.section_status.cost_risk):
            assert source.reason in output
            assert source.analyzed_scope in output
    assert report.findings == (*local.rule_findings, *semantic.findings)
    assert report.suggestions == semantic.suggestions
    assert originals == (
        local.model_dump_json(),
        request.model_dump_json(),
        semantic.model_dump_json(),
    )


@pytest.mark.parametrize(
    "local_status,remote_status,expected",
    [
        ("unsupported", "analyzed", "unsupported"),
        ("insufficient_context", "unsupported", "unsupported"),
        ("analyzed", "insufficient_context", "insufficient_context"),
        ("analyzed", "analyzed", "analyzed"),
    ],
)
def test_report_preserves_strongest_local_or_remote_status_and_both_explanations(
    local_status, remote_status, expected
):
    local, request, semantic = source_reports(local_status, remote_status)
    report = assemble_report(local, request, semantic)
    merged = report.section_status.cost_risk
    assert merged.status == expected
    assert local.capabilities.cost_risk.reason in merged.reason
    assert semantic.section_status.cost_risk.reason in merged.reason
    assert local.capabilities.cost_risk.analyzed_scope in merged.analyzed_scope
    assert semantic.section_status.cost_risk.analyzed_scope in merged.analyzed_scope


def test_offline_report_preserves_local_scope_and_missing_service_explanation():
    local, request, _ = source_reports("unsupported")
    report = assemble_report(local, request, None)
    assert report.scope.execution_mode == "offline"
    assert report.section_status.cost_risk.status == "unsupported"
    assert local.capabilities.cost_risk.reason in report.section_status.cost_risk.reason
    assert "Semantic service unavailable" in report.section_status.cost_risk.reason
    assert local.capabilities.cost_risk.analyzed_scope in render_markdown(report)
    assert report.findings == local.rule_findings


def test_identical_explanations_are_not_duplicated_and_absent_text_remains_optional():
    local, request, semantic = source_reports()
    semantic = semantic.model_copy(
        update={
            "section_status": semantic.section_status.model_copy(
                update={"cost_risk": local.capabilities.cost_risk}
            )
        }
    )
    report = assemble_report(local, request, semantic)
    merged = report.section_status.cost_risk
    assert merged.reason.count(local.capabilities.cost_risk.reason) == 1
    assert merged.analyzed_scope.count(local.capabilities.cost_risk.analyzed_scope) == 1
    local = local.model_copy(
        update={
            "capabilities": local.capabilities.model_copy(
                update={"cost_risk": CapabilityStatus(status="analyzed")}
            )
        }
    )
    semantic = semantic.model_copy(
        update={
            "section_status": semantic.section_status.model_copy(
                update={"cost_risk": CapabilityStatus(status="analyzed")}
            )
        }
    )
    merged = assemble_report(local, request, semantic).section_status.cost_risk
    assert merged.status == "analyzed"
    assert merged.reason is None and merged.analyzed_scope is None

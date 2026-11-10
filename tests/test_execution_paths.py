"""Source/revision boundaries for inferred paths, without a model call."""

import copy
import json
from pathlib import Path

import httpx
import pytest
from genesis_ci.client import SemanticClient
from genesis_ci.report import assemble_report, render_markdown, render_review_markdown
from genesis_ci.report_summary import render_summary
from genesis_contracts.models import (
    AnalysisRequest,
    LocalAnalysis,
    SemanticAnalysisResponse,
    parse_analysis_response,
)
from genesis_contracts.schemas import public_schemas
from genesis_contracts.validation import validate_model_response, validate_public_response
from jsonschema import Draft202012Validator


def prepared():
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/normal-five-sections/semantic.json").read_text()
    )
    request = AnalysisRequest.model_validate(dict(data["request"], behavior_review_version="2"))
    ref = next(r for r in request.evidence if r.kind == "code" and r.side == "head")
    review = dict(
        version="2",
        coverage=dict(status="analyzed", analyzed_scope="Selected source only"),
        changes=[],
        paths=[
            dict(
                path_id="head-submit",
                side="head",
                scenario="Submit with notification",
                condition="Submission succeeds",
                entry_step_id="submit",
                steps=[
                    dict(
                        step_id="submit",
                        symbol=ref.path + "#submit_report",
                        kind="entrypoint",
                        description="Submit report",
                        evidence_ids=[ref.evidence_id],
                    ),
                    dict(
                        step_id="notify",
                        kind="external",
                        description="Wait for notification",
                        evidence_ids=[ref.evidence_id],
                    ),
                ],
                links=[
                    dict(
                        source="submit",
                        target="notify",
                        relation="await",
                        support="semantic_inference",
                        evidence_ids=[ref.evidence_id],
                    )
                ],
                outcome="Notification completes before returning",
                limitations=["Notification implementation is omitted"],
            )
        ],
    )
    for finding in data["semantic_response"]["findings"]:
        if "semantic_inference" not in finding["basis"]:
            finding["basis"].append("semantic_inference")
    output = dict(data["semantic_response"], behavior_review=review)
    return data, request, output


def test_path_survives_validation_serialization_and_all_reports():
    data, request, output = prepared()
    response = SemanticAnalysisResponse.model_validate(output)
    validate_model_response(request, response)
    report = assemble_report(
        LocalAnalysis.model_validate(data["local_analysis"]), request, response
    )
    validate_public_response(report)
    assert report.schema_version == "0.3.0"
    raw = report.model_dump(mode="json")
    Draft202012Validator(public_schemas("0.3.0")["analysis-response.schema.json"]).validate(raw)
    assert parse_analysis_response(raw) == report
    assert (
        report.findings
        and report.estimates == LocalAnalysis.model_validate(data["local_analysis"]).estimates
    )
    for text in (
        render_markdown(report),
        render_review_markdown(report, LocalAnalysis.model_validate(data["local_analysis"])),
        render_summary(report, LocalAnalysis.model_validate(data["local_analysis"])),
    ):
        assert "Wait for notification" in text
        assert "semantic_inference" in text or "语义推断" in text
        assert "Notification implementation is omitted" in text


@pytest.mark.parametrize(
    "damage",
    [
        "wrong_side",
        "test_evidence",
        "unknown_evidence",
        "wrong_symbol",
        "duplicate_path",
        "duplicate_step",
        "missing_endpoint",
        "unknown_link",
        "unknown_entry",
        "mismatched_version",
    ],
)
def test_path_does_not_silently_accept_false_provenance_or_connectivity(damage):
    _, request, output = prepared()
    path = output["behavior_review"]["paths"][0]
    step = path["steps"][0]
    if damage == "wrong_side":
        step["evidence_ids"] = [
            next(r.evidence_id for r in request.evidence if r.kind == "code" and r.side == "base")
        ]
    elif damage == "test_evidence":
        step["evidence_ids"] = [next(r.evidence_id for r in request.evidence if r.kind != "code")]
    elif damage == "unknown_evidence":
        step["evidence_ids"] = ["not-selected"]
    elif damage == "wrong_symbol":
        step["symbol"] = "another.py#submit"
    elif damage == "duplicate_path":
        output["behavior_review"]["paths"].append(copy.deepcopy(path))
    elif damage == "duplicate_step":
        path["steps"].append(copy.deepcopy(step))
    elif damage == "missing_endpoint":
        path["links"][0]["target"] = "absent"
    elif damage == "unknown_link":
        path["links"][0]["support"] = "unknown"
    elif damage == "unknown_entry":
        path.update(entry_step_id=None, limitations=[])
    else:
        request = request.model_copy(update={"behavior_review_version": "1"})
    with pytest.raises(ValueError):
        validate_model_response(request, SemanticAnalysisResponse.model_validate(output))


def test_unknown_link_keeps_steps_but_requires_specific_limit():
    _, request, output = prepared()
    path = output["behavior_review"]["paths"][0]
    path["links"][0].update(
        support="unknown", limitations=["Runtime provider selection is unavailable"]
    )
    path["entry_step_id"] = None
    path["outcome"] = None
    response = SemanticAnalysisResponse.model_validate(output)
    validate_model_response(request, response)
    assert len(response.behavior_review.paths[0].steps) == 2


@pytest.mark.parametrize(
    "declared,expected",
    [
        ({"behavior_review_versions": ["1", "2"]}, "2"),
        ({"behavior_review_version": "1"}, "1"),
        ({}, None),
        ({"behavior_review_versions": "2"}, None),
    ],
)
def test_negotiation_only_downgrades_approved_output(declared, expected):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=declared)

    client = SemanticClient(
        "https://example.invalid", "unused", transport=httpx.MockTransport(handler)
    )
    capabilities = client.capabilities()
    assert client.negotiate_review_version("2", capabilities) == expected
    assert client.negotiate_review_version(None, capabilities) is None
    assert client.negotiate_review_version("1", capabilities) != "2"
    assert len(seen) == 1 and "authorization" not in seen[0].headers


def test_negotiation_does_not_assume_v1_when_service_only_advertises_v2():
    assert (
        SemanticClient.negotiate_review_version(
            "1", {"behavior_review_versions": ("2",), "behavior_review_version": "2"}
        )
        is None
    )
    assert (
        SemanticClient.negotiate_review_version(
            "1", {"behavior_review_versions": ("1", "2"), "behavior_review_version": "2"}
        )
        == "1"
    )

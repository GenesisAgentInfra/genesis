import json
from pathlib import Path

import httpx
import pytest
from client_fixtures import flow_draft_request, mark_inferences
from genesis_contracts.models import AnalysisRequest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/normal-five-sections/semantic.json"


def test_client_uses_existing_contract_and_does_not_follow_redirects():
    from genesis_ci.client import SemanticClient, SemanticFailure

    data = json.loads(FIXTURE.read_text())
    mark_inferences(data)  # Production model output labels every finding as inference.
    request = AnalysisRequest.model_validate(data["request"])

    def service(received):
        assert received.url.path == "/v1/analyze"
        assert received.headers["Authorization"] == "Bearer test-key"
        assert json.loads(received.content) == request.model_dump(mode="json")
        return httpx.Response(200, json=data["semantic_response"])

    client = SemanticClient(
        "https://ci.example.test", "test-key", transport=httpx.MockTransport(service)
    )
    assert client.analyze(request).snapshot_id == request.snapshot_id
    redirect = SemanticClient(
        "https://ci.example.test",
        "test-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(307, headers={"Location": "https://other.example.test"})
        ),
    )
    with pytest.raises(SemanticFailure) as error:
        redirect.analyze(request)
    assert error.value.code == "service_unavailable"


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_inference",
        "base_only",
        "missing_claim",
        "no_evidence",
        "non_test",
        "no_suggestion_evidence",
    ],
)
def test_production_client_and_report_reject_unsupported_model_evidence(invalid):
    from genesis_ci.client import SemanticClient, SemanticFailure
    from genesis_ci.report import assemble_report
    from genesis_contracts.models import LocalAnalysis, SemanticAnalysisResponse

    data = json.loads(FIXTURE.read_text())
    mark_inferences(data)
    request = AnalysisRequest.model_validate(data["request"])
    response = data["semantic_response"]
    claim = next(f for f in response["findings"] if f["deviation"] == "unverified_claim")
    refs = {ref.evidence_id: ref for ref in request.evidence}
    base = next(
        ref.evidence_id for ref in request.evidence if ref.kind == "code" and ref.side == "base"
    )
    if invalid == "missing_inference":
        claim["basis"].remove("semantic_inference")
    elif invalid == "base_only":
        claim["evidence_ids"] = [
            base if refs[ref].kind == "code" else ref for ref in claim["evidence_ids"]
        ]
    elif invalid == "missing_claim":
        claim["basis"].remove("agent_claim")
    elif invalid == "no_evidence":
        claim.update(basis=["semantic_inference"], deviation=None, evidence_ids=[])
    elif invalid == "non_test":
        response["suggestions"][0]["existing_test_evidence_ids"] = [base]
    else:
        response["suggestions"][0]["evidence_ids"] = []
    # A claimed mock version must not downgrade the production client's policy.
    response["semantic_version"] = "0.1.0-mock"
    client = SemanticClient(
        "https://ci.example.test",
        "test-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)),
    )
    with pytest.raises(SemanticFailure) as error:
        client.analyze(request)
    assert error.value.code == "provider_output_invalid"
    with pytest.raises(ValueError):
        assemble_report(
            LocalAnalysis.model_validate(data["local_analysis"]),
            request,
            SemanticAnalysisResponse.model_validate(response),
            execution_mode="semantic",
        )


def test_client_rejects_empty_draft_from_a_service_without_the_new_check():
    from genesis_ci.client import SemanticClient, SemanticFailure

    request = flow_draft_request()
    client = SemanticClient(
        "https://ci.example.test",
        "test-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "request_id": request.request_id,
                    "snapshot_id": request.snapshot_id,
                    "flows": [],
                },
            )
        ),
    )
    with pytest.raises(SemanticFailure) as error:
        client.draft(request)
    assert error.value.code == "provider_output_invalid"

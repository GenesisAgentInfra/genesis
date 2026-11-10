"""Public contract consistency without importing a private server."""

import json
from pathlib import Path

from genesis_ci.report import assemble_report
from genesis_contracts.models import AnalysisRequest, LocalAnalysis, SemanticAnalysisResponse
from genesis_contracts.schemas import public_schemas
from genesis_contracts.validation import validate_analysis_request, validate_public_response
from jsonschema import Draft202012Validator


def test_synthetic_requests_and_reports_match_public_contracts():
    for path in (Path(__file__).parents[1] / "fixtures").glob("*/semantic.json"):
        data = json.loads(path.read_text())
        request = AnalysisRequest.model_validate(data["request"])
        validate_analysis_request(request)
        report = assemble_report(
            LocalAnalysis.model_validate(data["local_analysis"]),
            request,
            SemanticAnalysisResponse.model_validate(data["semantic_response"]),
        )
        validate_public_response(report)
        schema = public_schemas()["analysis-response.schema.json"]
        Draft202012Validator(schema).validate(report.model_dump(mode="json"))


def test_all_published_schema_versions_are_valid():
    for version in ("0.1.0", "0.2.0", "0.3.0"):
        for schema in public_schemas(version).values():
            Draft202012Validator.check_schema(schema)

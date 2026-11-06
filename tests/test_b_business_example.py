"""Run the documented synthetic business case through the installed offline CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from genesis_contracts.models import AnalysisResponse, LocalAnalysis
from genesis_contracts.validation import validate_public_response

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("include_source", (False, True))
def test_business_example_builds_two_frozen_versions_and_delivers_a_partial_review(
    tmp_path, include_source
):
    destination = tmp_path / "submit-report-example"
    command = [
        sys.executable,
        str(ROOT / "examples/submit-report/run.py"),
        "--output",
        str(destination),
    ]
    if include_source:
        command.append("--include-source-evidence")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = AnalysisResponse.model_validate_json((destination / "report/report.json").read_bytes())
    validate_public_response(report)
    local = LocalAnalysis.model_validate_json(
        (destination / "report/local-analysis.json").read_bytes()
    )
    assert report.scope.execution_mode == "offline"
    assert report.analysis_status == "partial"
    assert report.scope.base_revision != report.scope.head_revision
    assert any(item.nature == "user_intent" and "失败" in item.text for item in local.intents)
    assert any(item.nature == "agent_claim" for item in local.intents)
    assert local.flows[0].id == "submit-report"
    assert local.test_definitions
    assert any(item.kind == "code" and item.side == "base" for item in report.evidence)
    assert any(item.kind == "code" and item.side == "head" for item in report.evidence)
    markdown = (destination / "report/report.md").read_text()
    assert "## 流程：提交报告" in markdown
    assert "## 冻结版本前后对照" in markdown
    source_review = destination / "report/review-with-source.md"
    assert source_review.exists() is include_source
    if include_source:
        assert "await send_slack" in source_review.read_text()
    metadata = json.loads((destination / "case.json").read_text())
    assert metadata["synthetic"] is True
    assert metadata["customer_code_executed"] is False
    assert "SYNTHETIC_CODE_MUST_NOT_EXECUTE" not in result.stderr

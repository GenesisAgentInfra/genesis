"""Synthetic client transport fixtures; no server or model implementation."""

import json
from pathlib import Path

from genesis_contracts.models import AnalysisRequest, FlowDraftRequest


def mark_inferences(data):
    for finding in data["semantic_response"]["findings"]:
        if "semantic_inference" not in finding["basis"]:
            finding["basis"].append("semantic_inference")


def flow_draft_request():
    path = Path(__file__).parents[1] / "fixtures/normal-five-sections/semantic.json"
    request = AnalysisRequest.model_validate(json.loads(path.read_text())["request"])
    evidence = next(e for e in request.evidence if e.kind == "code" and e.side == "head")
    excerpt = next(e for e in request.excerpts if e.evidence_id == evidence.evidence_id)
    return FlowDraftRequest(
        request_id="draft-test",
        snapshot_id=request.snapshot_id,
        candidate_entries=("src/app.py#submit_report",),
        entry_evidence_ids=(evidence.evidence_id,),
        evidence=(evidence,),
        excerpts=(excerpt,),
    )


def input_fixture(name="normal-five-sections"):
    path = Path(__file__).parents[1] / "fixtures" / name / "semantic.json"
    return json.loads(path.read_text())

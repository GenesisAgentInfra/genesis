import hashlib

from pydantic import BaseModel

from .behavior_review import validate_behavior_review
from .behavior_validation import validate_behavior_projection, validate_behavior_view
from .models import (
    AnalysisRequest,
    AnalysisResponse,
    EvidenceKind,
    EvidenceRef,
    FlowDraftRequest,
    FlowDraftResponse,
    LocalAnalysis,
    SemanticAnalysisResponse,
    SourceExcerpt,
    canonical_review_digest,
    validate_evidence_refs,
)


def _refs(value: object) -> list[str]:
    if isinstance(value, BaseModel):
        refs: list[str] = []
        for name in type(value).model_fields:
            field_value = getattr(value, name)
            if name.endswith("evidence_ids") and isinstance(field_value, tuple):
                refs.extend(field_value)
            else:
                refs.extend(_refs(field_value))
        return refs
    if isinstance(value, (tuple, list)):
        return [ref for item in value for ref in _refs(item)]
    return []


def _unique(items: object, key: str) -> None:
    values = [getattr(item, key) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {key}")


def _ensure_refs(value: object, snapshot_id: str, evidence: tuple[EvidenceRef, ...]) -> None:
    validate_evidence_refs(
        snapshot_id=snapshot_id, evidence=evidence, evidence_ids=tuple(_refs(value))
    )


def validate_excerpts(
    snapshot_id: str, evidence: tuple[EvidenceRef, ...], excerpts: tuple[SourceExcerpt, ...]
) -> None:
    _ensure_refs((), snapshot_id, evidence)
    _unique(excerpts, "evidence_id")
    by_id = {item.evidence_id: item for item in evidence}
    if set(by_id) != {item.evidence_id for item in excerpts}:
        raise ValueError("each selected evidence reference requires exactly one excerpt")
    for excerpt in excerpts:
        digest = "sha256:" + hashlib.sha256(excerpt.text.encode("utf-8")).hexdigest()
        if digest != by_id[excerpt.evidence_id].snippet_digest:
            raise ValueError("excerpt digest mismatch")


def _validate_findings(
    findings: object, evidence: tuple[EvidenceRef, ...], estimates: object
) -> None:
    _unique(findings, "finding_id")
    estimate_ids = {item.estimate_id for item in estimates}
    by_id = {item.evidence_id: item for item in evidence}
    for finding in findings:
        if set(finding.estimate_ids) - estimate_ids:
            raise ValueError("finding refers to unknown estimate_id")
        kinds = {by_id[item].kind for item in finding.evidence_ids}
        if "code_fact" in finding.basis and not kinds & {
            EvidenceKind.code,
            EvidenceKind.test,
            EvidenceKind.config,
        }:
            raise ValueError("code_fact basis requires code, test, or config evidence")
        if finding.deviation and EvidenceKind.code not in kinds:
            raise ValueError("intent deviation requires code evidence for the checked scope")
        if {"user_intent", "agent_claim"} & set(finding.basis) and not kinds & {
            EvidenceKind.intent,
            EvidenceKind.flow,
        }:
            raise ValueError("intent basis requires intent or flow evidence")


def _validate_context(context: LocalAnalysis | AnalysisRequest) -> None:
    validate_behavior_view(context)
    _unique(context.intents, "intent_id")
    _unique(context.flows, "id")
    _unique(context.flow_impacts, "flow_id")
    _unique(context.test_definitions, "test_id")
    _unique(context.estimates, "estimate_id")
    _unique(context.agent_loops, "loop_id")
    _unique(context.facts.calls, "call_id")
    flows = {flow.id: flow for flow in context.flows}
    for intent in context.intents:
        if intent.source_type == "flow_acceptance":
            flow = flows.get(intent.flow_id)
            if flow is None or flow.status != "confirmed" or intent.text not in flow.acceptance:
                raise ValueError("flow acceptance intent must match a confirmed flow criterion")
    for impact in context.flow_impacts:
        if impact.flow_id not in flows:
            raise ValueError("flow impact refers to an unknown flow")
    for finding in context.rule_findings:
        if set(finding.flow_ids) - flows.keys():
            raise ValueError("finding refers to unknown flow_id")
    call_ids = {call.call_id for call in context.facts.calls}
    for loop in context.agent_loops:
        if set(loop.call_ids) - call_ids:
            raise ValueError("agent loop refers to unknown call_id")
    _validate_findings(context.rule_findings, context.evidence, context.estimates)


def validate_local_analysis(analysis: LocalAnalysis) -> None:
    _ensure_refs(analysis, analysis.snapshot.snapshot_id, analysis.evidence)
    manifest = {(item.side, item.path): item for item in analysis.snapshot.files}
    for ref in analysis.evidence:
        file = manifest.get((ref.side, ref.path))
        if file is None or file.kind != ref.kind:
            raise ValueError(
                "evidence is absent from the snapshot manifest or has a different kind"
            )
    _validate_context(analysis)


def validate_analysis_request(request: AnalysisRequest) -> None:
    validate_excerpts(request.snapshot_id, request.evidence, request.excerpts)
    _ensure_refs(request, request.snapshot_id, request.evidence)
    _validate_context(request)


def validate_request_against_local(local: LocalAnalysis, request: AnalysisRequest) -> None:
    validate_local_analysis(local)
    validate_analysis_request(request)
    validate_behavior_projection(local, request)
    if local.snapshot.snapshot_id != request.snapshot_id:
        raise ValueError("request snapshot_id differs from local snapshot")
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    if any(catalog.get(ref.evidence_id) != ref for ref in request.evidence):
        raise ValueError("request evidence differs from local evidence")
    # Selection may omit local objects, but cannot alter deterministic calculations or findings.
    for name in (
        "rule_findings",
        "estimates",
        "intents",
        "flows",
        "flow_impacts",
        "test_definitions",
        "agent_loops",
    ):
        if any(item not in getattr(local, name) for item in getattr(request, name)):
            raise ValueError(f"request changed local {name}")
    for name in (
        "functions",
        "imports",
        "calls",
        "conditions",
        "awaits",
        "prompt_refs",
        "tool_refs",
        "unresolved",
    ):
        if any(item not in getattr(local.facts, name) for item in getattr(request.facts, name)):
            raise ValueError(f"request changed local facts.{name}")
    for name in ("nodes", "edges"):
        if any(
            item not in getattr(local.impact_graph, name)
            for item in getattr(request.impact_graph, name)
        ):
            raise ValueError(f"request changed local graph.{name}")
    if set(request.change_set.changed_symbol_ids) - set(local.change_set.changed_symbol_ids):
        raise ValueError("request changed local changed symbols")
    if set(request.change_set.unresolved) - set(local.change_set.unresolved):
        raise ValueError("request invented change-set uncertainty")
    if any(item not in local.change_set.files for item in request.change_set.files):
        raise ValueError("request changed local change set")


def validate_semantic_response(
    request: AnalysisRequest, response: SemanticAnalysisResponse
) -> None:
    validate_analysis_request(request)
    if response.behavior_review is not None and request.behavior_review_version is None:
        raise ValueError("behavior review was not requested")
    if request.behavior_review_version is not None and response.behavior_review is None:
        raise ValueError("requested behavior review is missing")
    if (
        response.behavior_review is not None
        and response.behavior_review.version != request.behavior_review_version
    ):
        raise ValueError("behavior review version does not match the request")
    validate_behavior_review(
        response.behavior_review, request.evidence, (*request.rule_findings, *response.findings)
    )
    if response.review_receipt is not None:
        if (
            request.review_directives is None
            or response.review_receipt.sha256 != canonical_review_digest(request.review_directives)
            or response.review_receipt.semantic_version != response.semantic_version
        ):
            raise ValueError("review receipt does not match the request and semantic version")
    if request.request_id != response.request_id:
        raise ValueError("request_id mismatch")
    if request.snapshot_id != response.snapshot_id:
        raise ValueError("snapshot_id mismatch")
    _ensure_refs(response, request.snapshot_id, request.evidence)
    _validate_findings(response.findings, request.evidence, request.estimates)
    _unique((*request.rule_findings, *response.findings), "finding_id")
    _unique(response.suggestions, "suggestion_id")
    flows = {flow.id for flow in request.flows}
    user_ids = {
        ref
        for intent in request.intents
        if intent.nature == "user_intent"
        for ref in intent.evidence_ids
    }
    claim_ids = {
        ref
        for intent in request.intents
        if intent.nature == "agent_claim"
        for ref in intent.evidence_ids
    }
    for finding in response.findings:
        if set(finding.flow_ids) - flows:
            raise ValueError("semantic finding refers to unknown flow_id")
        for basis, ids in (("user_intent", user_ids), ("agent_claim", claim_ids)):
            if basis in finding.basis and not set(finding.evidence_ids) & ids:
                raise ValueError(f"{basis} basis must cite a matching classified source")


def validate_public_response(response: AnalysisResponse) -> None:
    validate_behavior_review(
        getattr(response, "behavior_review", None), response.evidence, response.findings
    )
    _ensure_refs(response, response.snapshot_id, response.evidence)
    _validate_findings(response.findings, response.evidence, response.estimates)
    _unique(response.estimates, "estimate_id")
    _unique(response.suggestions, "suggestion_id")
    if response.analysis_status == "complete" and (
        response.scope.execution_mode == "offline"
        or response.scope.omitted_inputs
        or any(item.affects_completeness for item in response.limitations)
        or (
            getattr(response, "behavior_review", None) is not None
            and response.behavior_review.coverage.status != "analyzed"
        )
    ):
        raise ValueError("complete report cannot have incomplete inputs or offline execution")


def validate_model_response(request: AnalysisRequest, response: SemanticAnalysisResponse) -> None:
    """Shared production checks for model output, on both service and CLI.

    The wire validator also supports the pinned deterministic mock fixtures;
    production callers additionally require model inference and scoped evidence.
    Never select this policy from a remote response's version or other fields.
    """
    validate_semantic_response(request, response)
    evidence = {ref.evidence_id: ref for ref in request.evidence}
    for finding in response.findings:
        if "semantic_inference" not in finding.basis or not finding.evidence_ids:
            raise ValueError("model findings require inference basis and selected evidence")
        if finding.deviation == "unverified_claim" and "agent_claim" not in finding.basis:
            raise ValueError("unverified claims require the original classified claim")
        if finding.deviation and (
            "code_fact" not in finding.basis
            or not any(
                evidence[ref].kind == "code" and evidence[ref].side == "head"
                for ref in finding.evidence_ids
            )
        ):
            raise ValueError("intent deviations require inspected head code evidence")
    for suggestion in response.suggestions:
        if not suggestion.evidence_ids:
            raise ValueError("verification suggestions require selected evidence")
        if any(evidence[ref].kind != "test" for ref in suggestion.existing_test_evidence_ids):
            raise ValueError("existing tests must cite test evidence")


def validate_flow_draft(request: FlowDraftRequest) -> None:
    validate_excerpts(request.snapshot_id, request.evidence, request.excerpts)
    _ensure_refs(request, request.snapshot_id, request.evidence)
    refs = {ref.evidence_id: ref for ref in request.evidence}
    for entry, evidence_id in zip(
        request.candidate_entries, request.entry_evidence_ids, strict=True
    ):
        ref = refs[evidence_id]
        if ref.path != entry.split("#")[0] or ref.side != "head" or ref.kind != "code":
            raise ValueError("candidate entry must reference head code at its entry path")


def validate_flow_draft_response(request: FlowDraftRequest, response: FlowDraftResponse) -> None:
    """A usable draft must preserve identity and name at least one selected entry."""
    validate_flow_draft(request)
    if response.request_id != request.request_id or response.snapshot_id != request.snapshot_id:
        raise ValueError("Draft response identity differs from request")
    if not response.flows:
        raise ValueError("Draft response must contain at least one flow")
    _unique(response.flows, "id")
    for flow in response.flows:
        if (
            not flow.name.strip()
            or not flow.description.strip()
            or len(set(flow.entries)) != len(flow.entries)
            or set(flow.entries) - set(request.candidate_entries)
        ):
            raise ValueError("draft has invalid or unknown entries")

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=False, allow_inf_nan=False
    )


class AnalysisStatus(StrEnum):
    complete = "complete"
    partial = "partial"
    failed = "failed"


class SectionStatus(StrEnum):
    analyzed = "analyzed"
    insufficient_context = "insufficient_context"
    unsupported = "unsupported"


class EvidenceSide(StrEnum):
    base = "base"
    head = "head"


class EvidenceKind(StrEnum):
    code = "code"
    intent = "intent"
    flow = "flow"
    test = "test"
    config = "config"


class EvidenceBasis(StrEnum):
    code_fact = "code_fact"
    semantic_inference = "semantic_inference"
    conditional_estimate = "conditional_estimate"
    user_intent = "user_intent"
    agent_claim = "agent_claim"


class FindingCategory(StrEnum):
    behavior_intent = "behavior_intent"
    flow_impact = "flow_impact"
    cost_risk = "cost_risk"
    acceptance_tests = "acceptance_tests"
    verification = "verification"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"


class IntentDeviation(StrEnum):
    missing_in_code = "missing_in_code"
    unrequested_change = "unrequested_change"
    unverified_claim = "unverified_claim"


class ServiceErrorCode(StrEnum):
    invalid_request = "invalid_request"
    invalid_api_key = "invalid_api_key"
    quota_exceeded = "quota_exceeded"
    request_too_large = "request_too_large"
    protocol_version_unsupported = "protocol_version_unsupported"
    fixture_request_mismatch = "fixture_request_mismatch"
    provider_error = "provider_error"
    provider_output_invalid = "provider_output_invalid"
    service_unavailable = "service_unavailable"
    analysis_timeout = "analysis_timeout"


class FlowStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"


class ReferenceRange(ContractModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: int | None = Field(default=None, ge=0)
    end_column: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def range_is_ordered(self) -> ReferenceRange:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if (
            self.end_line == self.start_line
            and self.start_column is not None
            and self.end_column is not None
            and self.end_column < self.start_column
        ):
            raise ValueError("end_column must be >= start_column on a single line")
        return self


class EvidenceRef(ContractModel):
    evidence_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    side: EvidenceSide
    path: str = Field(min_length=1)
    range: ReferenceRange
    snippet_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: EvidenceKind

    @model_validator(mode="after")
    def safe_relative_path(self) -> EvidenceRef:
        validate_repo_path(self.path)
        expected_id = evidence_id_for(
            snapshot_id=self.snapshot_id,
            side=self.side,
            path=self.path,
            range=self.range,
            digest=self.snippet_digest,
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match its snapshot, path, range, and digest")
        return self


def validate_repo_path(path: str) -> None:
    if not path or any(ord(char) < 32 for char in path):
        raise ValueError("path must not be empty or contain control characters")
    if path.startswith(("/", "\\")) or "\\" in path or re.match(r"^[A-Za-z]:", path):
        raise ValueError("path must be a repository-relative POSIX path")
    if any(segment in {"", ".", ".."} for segment in path.split("/")):
        raise ValueError("path contains an invalid segment")


def evidence_id_for(
    *, snapshot_id: str, side: EvidenceSide, path: str, range: ReferenceRange, digest: str
) -> str:
    identity = "\0".join(
        (
            snapshot_id,
            side.value,
            path,
            str(range.start_line),
            str(range.end_line),
            str(range.start_column),
            str(range.end_column),
            digest,
        )
    )
    return "ev_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


class FileIdentity(ContractModel):
    path: str = Field(min_length=1)
    side: EvidenceSide
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: EvidenceKind

    @model_validator(mode="after")
    def safe_relative_path(self) -> FileIdentity:
        validate_repo_path(self.path)
        return self


def snapshot_id_for(
    *,
    base_revision: str | None,
    head_revision: str | None,
    files: tuple[FileIdentity, ...],
) -> str:
    identity = {
        "base_revision": base_revision,
        "head_revision": head_revision,
        "files": [
            item.model_dump(mode="json")
            for item in sorted(
                files, key=lambda item: (item.side.value, item.path, item.kind.value)
            )
        ],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SnapshotManifest(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    base_revision: str | None = None
    head_revision: str | None = None
    files: tuple[FileIdentity, ...]
    integrity_status: Literal["complete", "partial"]
    omitted_inputs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identity_matches_manifest(self) -> SnapshotManifest:
        file_keys = [(item.side, item.path) for item in self.files]
        if len(file_keys) != len(set(file_keys)):
            raise ValueError("snapshot file identities must be unique by side and path")
        expected = snapshot_id_for(
            base_revision=self.base_revision,
            head_revision=self.head_revision,
            files=self.files,
        )
        if self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match the version identities and file manifest")
        return self


class CapabilityStatus(ContractModel):
    status: SectionStatus
    reason: str | None = None
    analyzed_scope: str | None = None

    @model_validator(mode="after")
    def explain_missing_capability(self) -> CapabilityStatus:
        if self.status != SectionStatus.analyzed and not self.reason:
            raise ValueError("unsupported/incomplete capability requires a reason")
        return self


class Finding(ContractModel):
    finding_id: str = Field(min_length=1)
    category: FindingCategory
    statement: str = Field(min_length=1)
    severity: Severity
    basis: tuple[EvidenceBasis, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...]
    deviation: IntentDeviation | None = None
    condition: str | None = None
    gap: str | None = None
    recommendation: str | None = None
    flow_ids: tuple[str, ...] = ()
    estimate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def claims_need_code_evidence(self) -> Finding:
        if set(self.basis) == {EvidenceBasis.agent_claim}:
            raise ValueError("agent_claim cannot be the sole basis of a finding")
        if (
            self.deviation == IntentDeviation.unverified_claim
            and EvidenceBasis.code_fact not in self.basis
        ):
            raise ValueError(
                "unverified claims must include code_fact evidence for the checked scope"
            )
        if (
            self.deviation == IntentDeviation.unrequested_change
            and EvidenceBasis.user_intent not in self.basis
        ):
            raise ValueError("unrequested changes must cite user intent")
        if (
            self.deviation == IntentDeviation.missing_in_code
            and EvidenceBasis.user_intent not in self.basis
        ):
            raise ValueError("missing-in-code findings must cite user intent")
        if EvidenceBasis.agent_claim in self.basis and not self.evidence_ids:
            raise ValueError("agent claims must be tied to source evidence")
        return self


class EstimateParameter(ContractModel):
    name: str
    value: float | None
    unit: str
    source: str | None = None
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def unknown_has_reason(self) -> EstimateParameter:
        if self.value is None and not self.unknown_reason:
            raise ValueError("unknown estimate parameters require unknown_reason")
        return self


class ImpactEstimate(ContractModel):
    estimate_id: str
    flow_ids: tuple[str, ...] = ()
    structural_signals: tuple[str, ...] = ()
    parameters: tuple[EstimateParameter, ...] = ()
    formula: str | None = None
    amount: float | None = None
    currency: str | None = None
    price_source: str | None = None
    price_date: str | None = None
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]


class VerificationSuggestion(ContractModel):
    suggestion_id: str
    scenario: str = Field(min_length=1)
    conditions: tuple[str, ...] = ()
    suggested_assertions: tuple[str, ...] = ()
    existing_test_evidence_ids: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)
    questions_for_user: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]


class AnalysisScope(ContractModel):
    base_revision: str | None = None
    head_revision: str | None = None
    analyzed_files: tuple[str, ...]
    omitted_inputs: tuple[str, ...] = ()
    parser_limitations: tuple[str, ...] = ()
    execution_mode: Literal["mock", "offline", "semantic"]


class SectionStatuses(ContractModel):
    behavior_intent: CapabilityStatus
    flow_impact: CapabilityStatus
    cost_risk: CapabilityStatus
    acceptance_tests: CapabilityStatus
    verification: CapabilityStatus


class Limitation(ContractModel):
    code: str
    message: str
    evidence_ids: tuple[str, ...] = ()
    affects_completeness: bool = False


class BehaviorChange(ContractModel):
    """Source-backed semantic comparison, never an inferred user requirement."""

    change_id: str = Field(min_length=1, max_length=128)
    scenario: str = Field(min_length=1, max_length=500)
    condition: str = Field(min_length=1, max_length=1000)
    before: str | None = Field(default=None, max_length=2000)
    after: str | None = Field(default=None, max_length=2000)
    before_evidence_ids: tuple[str, ...] = Field(default=(), max_length=16)
    after_evidence_ids: tuple[str, ...] = Field(default=(), max_length=16)
    explanation: str = Field(min_length=1, max_length=2000)
    impact: str = Field(min_length=1, max_length=2000)
    preserved_behavior: str | None = Field(default=None, max_length=1000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=24)
    finding_ids: tuple[str, ...] = Field(default=(), max_length=24)
    limitations: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def comparisons_need_sources(self):
        for text, refs in (
            (self.before, self.before_evidence_ids),
            (self.after, self.after_evidence_ids),
        ):
            if (text is not None) != bool(refs) or (text is not None and not text.strip()):
                raise ValueError("each described behavior side requires its own source evidence")
        if self.before is None and self.after is None:
            raise ValueError("behavior comparison requires at least one described side")
        if (self.before is None or self.after is None) and not self.limitations:
            raise ValueError("an unavailable behavior side requires an explicit limitation")
        return self


class BehaviorReview(ContractModel):
    version: Literal["1"] = "1"
    coverage: CapabilityStatus
    changes: tuple[BehaviorChange, ...] = Field(default=(), max_length=12)


class ExecutionStep(ContractModel):
    step_id: str = Field(min_length=1, max_length=128)
    symbol: str | None = Field(default=None, max_length=500)
    kind: Literal["entrypoint", "function", "model", "tool", "human", "external", "return", "raise"]
    description: str = Field(min_length=1, max_length=500)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class ExecutionLink(ContractModel):
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    relation: Literal["call", "await", "branch", "return", "raise", "human_wait"]
    condition: str | None = Field(default=None, max_length=500)
    support: Literal["semantic_inference", "unknown"] = "semantic_inference"
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    limitations: tuple[str, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def unknown_requires_explanation(self):
        if self.support == "unknown" and not self.limitations:
            raise ValueError("unknown execution link requires a limitation")
        return self


class ExecutionPath(ContractModel):
    """Semantic explanation of one revision, distinct from the static call graph."""

    path_id: str = Field(min_length=1, max_length=128)
    side: EvidenceSide
    scenario: str = Field(min_length=1, max_length=500)
    condition: str = Field(min_length=1, max_length=500)
    entry_step_id: str | None = Field(default=None, max_length=128)
    steps: tuple[ExecutionStep, ...] = Field(min_length=1, max_length=12)
    links: tuple[ExecutionLink, ...] = Field(default=(), max_length=16)
    outcome: str | None = Field(default=None, max_length=500)
    limitations: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_structure(self):
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate execution step_id")
        if self.entry_step_id is not None and self.entry_step_id not in ids:
            raise ValueError("execution entry must reference a step")
        if self.entry_step_id is None and not self.limitations:
            raise ValueError("unknown execution entry requires a limitation")
        if any(link.source not in ids or link.target not in ids for link in self.links):
            raise ValueError("execution link endpoint is missing")
        return self


class PathBehaviorReview(BehaviorReview):
    version: Literal["2"] = "2"
    paths: tuple[ExecutionPath, ...] = Field(max_length=6)


class AnalysisResponse(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    analysis_status: AnalysisStatus
    section_status: SectionStatuses
    scope: AnalysisScope
    findings: tuple[Finding, ...] = ()
    estimates: tuple[ImpactEstimate, ...] = ()
    suggestions: tuple[VerificationSuggestion, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    analyzer_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    semantic_version: str | None = None
    evidence: tuple[EvidenceRef, ...]

    @model_validator(mode="after")
    def complete_requires_analyzed_sections(self) -> AnalysisResponse:
        if self.analysis_status == AnalysisStatus.complete:
            for name in SectionStatuses.model_fields:
                if getattr(self.section_status, name).status != SectionStatus.analyzed:
                    raise ValueError("complete analysis requires every section to be analyzed")
        return self


class BehaviorAnalysisResponse(AnalysisResponse):
    """Opt-in public report v0.2.0; the v0.1.0 schema remains unchanged."""

    schema_version: Literal["0.2.0"] = "0.2.0"
    behavior_review: BehaviorReview


class PathAnalysisResponse(AnalysisResponse):
    schema_version: Literal["0.3.0"] = "0.3.0"
    behavior_review: PathBehaviorReview


def parse_analysis_response(data):
    model = {"0.2.0": BehaviorAnalysisResponse, "0.3.0": PathAnalysisResponse}.get(
        data.get("schema_version"), AnalysisResponse
    )
    return model.model_validate(data)


class IntentItem(ContractModel):
    intent_id: str
    source_type: Literal["task", "requirements", "flow_acceptance", "agent_plan", "pr_description"]
    nature: Literal["user_intent", "agent_claim"]
    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    flow_id: str | None = None
    conflict_group: str | None = None

    @model_validator(mode="after")
    def classify_source(self) -> IntentItem:
        expected = (
            "agent_claim" if self.source_type in {"agent_plan", "pr_description"} else "user_intent"
        )
        if self.nature != expected:
            raise ValueError("intent nature does not match source_type")
        if self.source_type == "flow_acceptance" and not self.flow_id:
            raise ValueError("flow acceptance requires a confirmed flow_id")
        return self


class Resolution(ContractModel):
    status: Literal["resolved", "candidate", "unknown"]
    targets: tuple[str, ...] = ()
    reason: str | None = None

    @model_validator(mode="after")
    def explain_resolution(self) -> Resolution:
        if self.status != "resolved" and not self.reason:
            raise ValueError("candidate/unknown resolution requires a reason")
        if self.status == "unknown" and self.targets:
            raise ValueError("unknown resolution cannot assert targets; use candidate")
        return self


class SymbolFact(ContractModel):
    symbol_id: str
    side: EvidenceSide
    kind: Literal["function", "class", "module"]
    is_async: bool = False
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ImportFact(ContractModel):
    import_id: str
    side: EvidenceSide
    module: str
    imported_name: str | None = None
    alias: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class CallFact(ContractModel):
    call_id: str
    side: EvidenceSide
    caller_symbol_id: str
    expression: str
    target: Resolution
    awaited: bool
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ExpressionFact(ContractModel):
    fact_id: str
    side: EvidenceSide
    symbol_id: str
    expression: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class UnresolvedFact(ContractModel):
    unresolved_id: str
    feature: Literal["import", "call", "tool", "prompt", "control_flow", "test", "other"]
    reason: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class FactPack(ContractModel):
    coverage: CapabilityStatus
    functions: tuple[SymbolFact, ...] = ()
    imports: tuple[ImportFact, ...] = ()
    calls: tuple[CallFact, ...] = ()
    conditions: tuple[ExpressionFact, ...] = ()
    awaits: tuple[ExpressionFact, ...] = ()
    prompt_refs: tuple[ExpressionFact, ...] = ()
    tool_refs: tuple[ExpressionFact, ...] = ()
    unresolved: tuple[UnresolvedFact, ...] = ()


class FileChange(ContractModel):
    change_type: Literal["added", "modified", "deleted", "renamed"]
    base_path: str | None = None
    head_path: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_sides(self) -> FileChange:
        for path in (self.base_path, self.head_path):
            if path is not None:
                validate_repo_path(path)
        expected = {
            "added": (False, True),
            "deleted": (True, False),
            "modified": (True, True),
            "renamed": (True, True),
        }[self.change_type]
        if (self.base_path is not None, self.head_path is not None) != expected:
            raise ValueError("file change paths do not match change_type")
        return self


class ChangeSet(ContractModel):
    files: tuple[FileChange, ...]
    changed_symbol_ids: tuple[str, ...]
    unresolved: tuple[str, ...] = ()


class LoopBound(ContractModel):
    status: Literal["bounded", "unbounded", "unknown"]
    max_iterations: int | None = Field(default=None, gt=0)
    reason: str
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def bound_is_explicit(self) -> LoopBound:
        if (self.status == "bounded") != (self.max_iterations is not None):
            raise ValueError("only bounded loops have max_iterations")
        return self


class AgentLoopFact(ContractModel):
    loop_id: str
    symbol_id: str
    call_ids: tuple[str, ...]
    model: Resolution
    prompt_evidence_ids: tuple[str, ...] = ()
    reachable_tools: Resolution
    dispatch: Resolution
    iteration_bound: LoopBound
    stop_conditions: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class GraphNode(ContractModel):
    node_id: str
    symbol_id: str | None = None
    kind: Literal["symbol", "call", "tool", "external", "unknown"]
    evidence_ids: tuple[str, ...]


class GraphEdge(ContractModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: Literal["calls", "imports", "awaits", "dispatches", "contains"]
    resolution: Literal["resolved", "candidate", "unknown"]
    reason: str
    condition: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ImpactGraph(ContractModel):
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @model_validator(mode="after")
    def valid_graph(self) -> ImpactGraph:
        nodes = {node.node_id for node in self.nodes}
        if len(nodes) != len(self.nodes) or len({edge.edge_id for edge in self.edges}) != len(
            self.edges
        ):
            raise ValueError("graph IDs must be unique")
        if any(edge.source_id not in nodes or edge.target_id not in nodes for edge in self.edges):
            raise ValueError("graph edge references an unknown node")
        return self


class FlowImpact(ContractModel):
    flow_id: str
    status: Literal["resolved", "candidate", "unknown"]
    entry_status: Literal["valid", "invalid", "unknown"]
    changed_symbol_ids: tuple[str, ...]
    reason: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class TestDefinition(ContractModel):
    test_id: str
    symbol_id: str
    assertions: tuple[str, ...]
    mocks: tuple[str, ...]
    association: Resolution
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class BehaviorSource(ContractModel):
    """Exact source inside a selected, enclosing function excerpt."""

    text: str = Field(min_length=1, max_length=12000)
    range: ReferenceRange
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=4)


class BehaviorCondition(BehaviorSource):
    truth: bool


class BehaviorOperation(BehaviorSource):
    kind: Literal["assignment", "expression", "context_region", "exception_region"]


class BehaviorResult(BehaviorSource):
    kind: Literal["return", "raise", "state_update"]


class BehaviorUnit(ContractModel):
    """A bounded lexical path view, never a runtime or business verdict."""

    unit_id: str = Field(pattern=r"^bu_[0-9a-f]{24}$")
    side: EvidenceSide
    path: str
    symbol_id: str
    scope_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    conditions: tuple[BehaviorCondition, ...] = Field(default=(), max_length=32)
    operations: tuple[BehaviorOperation, ...] = Field(default=(), max_length=32)
    result: BehaviorResult | None = None
    limitations: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_scope(self):
        validate_repo_path(self.path)
        if not self.symbol_id.startswith(self.path + "#"):
            raise ValueError("behavior symbol must belong to its source path")
        if self.result is None and not self.limitations:
            raise ValueError("behavior without a result must explain its limitation")
        return self


def behavior_id_for(snapshot_id: str, unit: BehaviorUnit | dict) -> str:
    data = (
        unit.model_dump(mode="json", exclude={"unit_id"})
        if isinstance(unit, BehaviorUnit)
        else dict(unit)
    )
    data.pop("unit_id", None)
    raw = json.dumps([snapshot_id, data], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "bu_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


class BehaviorView(ContractModel):
    version: Literal["1", "2"] = "1"
    units: tuple[BehaviorUnit, ...] = Field(default=(), max_length=512)
    omitted_units: int = Field(default=0, ge=0)
    limitations: tuple[str, ...] = (
        "Lexical candidate paths, not observed executions or proven feasible paths. Earlier operations may fail; return/raise expressions must complete.",
        "Operations preserve source order within a local path, not a complete causal or interprocedural data-flow slice. Expression-internal branches and effects remain in source.",
    )


class LocalAnalysis(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot: SnapshotManifest
    evidence: tuple[EvidenceRef, ...]
    intents: tuple[IntentItem, ...] = ()
    change_set: ChangeSet
    facts: FactPack
    agent_loops: tuple[AgentLoopFact, ...]
    impact_graph: ImpactGraph
    flows: tuple[FlowDefinition, ...]
    flow_impacts: tuple[FlowImpact, ...]
    test_definitions: tuple[TestDefinition, ...]
    rule_findings: tuple[Finding, ...] = ()
    estimates: tuple[ImpactEstimate, ...] = ()
    capabilities: SectionStatuses
    limitations: tuple[Limitation, ...] = ()
    behavior_view: BehaviorView | None = None

    @model_serializer(mode="wrap")
    def omit_unused_behavior_view(self, handler):
        data = handler(self)
        if self.behavior_view is None:
            data.pop("behavior_view", None)
        return data


class SourceExcerpt(ContractModel):
    evidence_id: str
    text: str


class ReviewDocument(ContractModel):
    """Reviewer goals and supporting references, never classified business intent."""

    role: Literal["instructions", "reference", "schema"]
    path: str = Field(min_length=1, max_length=1024)
    text: str = Field(max_length=262144)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid_identity(self) -> ReviewDocument:
        validate_repo_path(self.path)
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("review document content digest mismatch")
        return self


class ReviewDirectives(ContractModel):
    version: Literal["1"] = "1"
    documents: tuple[ReviewDocument, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_paths(self) -> ReviewDirectives:
        if len({doc.path for doc in self.documents}) != len(self.documents):
            raise ValueError("review document paths must be unique")
        return self


def canonical_review_digest(value: ReviewDirectives) -> str:
    encoded = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ReviewReceipt(ContractModel):
    """Service delivery attestation, not proof of model attention or review quality."""

    version: Literal["1"] = "1"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_version: str = Field(min_length=1)


class AnalysisRequest(ContractModel):
    protocol_version: Literal["0.1.0"] = "0.1.0"
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    snapshot_id: str = Field(min_length=1)
    cli_version: str = Field(min_length=1)
    change_set: ChangeSet
    facts: FactPack
    agent_loops: tuple[AgentLoopFact, ...]
    impact_graph: ImpactGraph
    flows: tuple[FlowDefinition, ...]
    flow_impacts: tuple[FlowImpact, ...]
    test_definitions: tuple[TestDefinition, ...]
    intents: tuple[IntentItem, ...] = ()
    evidence: tuple[EvidenceRef, ...]
    excerpts: tuple[SourceExcerpt, ...]
    rule_findings: tuple[Finding, ...] = ()
    estimates: tuple[ImpactEstimate, ...] = ()
    missing_context: tuple[str, ...] = ()
    truncated: bool = False
    input_token_budget: int = Field(default=40000, gt=0)
    review_directives: ReviewDirectives | None = None
    behavior_view: BehaviorView | None = None
    behavior_review_version: Literal["1", "2"] | None = None

    @model_serializer(mode="wrap")
    def omit_unused_review_channel(self, handler):
        data = handler(self)
        if self.review_directives is None:
            data.pop("review_directives", None)
        if self.behavior_view is None:
            data.pop("behavior_view", None)
        if self.behavior_review_version is None:
            data.pop("behavior_review_version", None)
        return data


def project_review_directives(review: ReviewDirectives) -> dict:
    """Separate downstream presentation contracts from model review material.

    Complete document bytes stay in the validated wire request and canonical digest.
    A model sees exact review instructions/references and only schema provenance;
    native service output remains governed by its own structured-output schema.
    """
    documents, schemas = [], []
    for document in review.documents:
        value = document.model_dump(mode="json")
        if document.role == "schema":
            schemas.append({name: value[name] for name in ("role", "path", "sha256")})
        else:
            documents.append(value)
    return {"version": review.version, "documents": documents, "schema_documents": schemas}


def project_analysis_request(request: AnalysisRequest) -> dict:
    """Canonical model input projection, shared by client budgeting and service."""
    selected = request.model_dump(mode="json")
    selected.pop("review_directives", None)
    # Integrity is checked against the full wire request before model admission.
    # Repeating two long hashes for every span spends context without conveying
    # review semantics. IDs, side, paths, ranges, kinds and exact text remain;
    # model citations are still validated against the original evidence catalog.
    selected["evidence"] = [
        ref.model_dump(mode="json", exclude={"snapshot_id", "snippet_digest"})
        for ref in request.evidence
    ]
    payload = {"selected_analysis": selected}
    if request.review_directives is not None:
        payload["reviewer_context"] = project_review_directives(request.review_directives)
    return payload


class SemanticAnalysisResponse(ContractModel):
    protocol_version: Literal["0.1.0"] = "0.1.0"
    request_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    findings: tuple[Finding, ...] = ()
    suggestions: tuple[VerificationSuggestion, ...] = ()
    section_status: SectionStatuses
    limitations: tuple[Limitation, ...] = ()
    semantic_version: str = Field(min_length=1)
    review_receipt: ReviewReceipt | None = None
    behavior_review: PathBehaviorReview | BehaviorReview | None = None

    @model_serializer(mode="wrap")
    def omit_unused_review_receipt(self, handler):
        data = handler(self)
        if self.review_receipt is None:
            data.pop("review_receipt", None)
        if self.behavior_review is None:
            data.pop("behavior_review", None)
        return data


class FlowAcceptance(ContractModel):
    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)


class FlowDefinition(ContractModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    status: FlowStatus
    entries: tuple[str, ...] = Field(min_length=1)
    acceptance: tuple[str, ...] = ()
    notes: str | None = None

    @model_validator(mode="after")
    def validate_flow(self) -> FlowDefinition:
        for entry in self.entries:
            validate_entry(entry)
        if len(set(self.entries)) != len(self.entries):
            raise ValueError("flow entries must be unique")
        if self.status == FlowStatus.draft and self.acceptance:
            raise ValueError("draft flows cannot provide acceptance criteria")
        return self


def validate_entry(entry: str) -> None:
    path, separator, symbol = entry.partition("#")
    validate_repo_path(path)
    if not separator or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", symbol):
        raise ValueError("entry must use repo/path.py#qualified.symbol")


class FlowsDocument(ContractModel):
    schema_version: Literal[1] = 1
    flows: tuple[FlowDefinition, ...] = ()

    @model_validator(mode="after")
    def unique_flow_ids(self) -> FlowsDocument:
        ids = [flow.id for flow in self.flows]
        if len(ids) != len(set(ids)):
            raise ValueError("flow ids must be unique")
        return self


class FlowDraftRequest(ContractModel):
    protocol_version: Literal["0.1.0"] = "0.1.0"
    request_id: str
    snapshot_id: str
    candidate_entries: tuple[str, ...]
    entry_evidence_ids: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    excerpts: tuple[SourceExcerpt, ...]

    @model_validator(mode="after")
    def validate_candidates(self) -> FlowDraftRequest:
        if not self.candidate_entries or len(self.candidate_entries) != len(
            self.entry_evidence_ids
        ):
            raise ValueError("each candidate entry requires its evidence_id")
        for entry in self.candidate_entries:
            validate_entry(entry)
        return self


class DraftFlow(ContractModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    description: str
    status: Literal["draft"] = "draft"
    entries: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> DraftFlow:
        for entry in self.entries:
            validate_entry(entry)
        return self


class FlowDraftResponse(ContractModel):
    protocol_version: Literal["0.1.0"] = "0.1.0"
    request_id: str
    snapshot_id: str
    flows: tuple[DraftFlow, ...]


class ServiceError(ContractModel):
    code: ServiceErrorCode
    message: str
    retryable: bool
    request_id: str


def validate_evidence_refs(
    *, snapshot_id: str, evidence: tuple[EvidenceRef, ...], evidence_ids: tuple[str, ...]
) -> None:
    by_id = {item.evidence_id: item for item in evidence}
    if len(by_id) != len(evidence):
        raise ValueError("evidence_id values must be unique")
    invalid = sorted(set(evidence_ids) - by_id.keys())
    if invalid:
        raise ValueError(f"unknown evidence_id values: {', '.join(invalid)}")
    if any(item.snapshot_id != snapshot_id for item in evidence):
        raise ValueError("evidence reference snapshot_id does not match analysis snapshot")


PublicJson = Annotated[
    AnalysisResponse | BehaviorAnalysisResponse | FlowsDocument, Field(discriminator=None)
]

LocalAnalysis.model_rebuild()
AnalysisRequest.model_rebuild()

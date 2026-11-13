"""Business map: business flows synthesized by a coding agent, grounded in static evidence.

Draft contract. The CLI writes this document; an agent never writes it directly.
Static facts and agent synthesis stay apart: `support` says where a statement comes
from, and `resolution` says how well the evidence supports it. Two fields are needed
because an inference can come from static resolution as well as from a model.

The map never states that code meets a requirement, that a test ran, or that a path
executed. Ordering shown between steps is a control relation supported by source.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .fingerprint import FINGERPRINT_PATTERN
from .models import (
    ContractModel,
    EvidenceRef,
    EvidenceSide,
    Limitation,
    Severity,
    validate_evidence_refs,
)

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Anchor = Annotated[str, Field(pattern=FINGERPRINT_PATTERN)]
SymbolId = Annotated[str, Field(min_length=1, max_length=1024)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Count = Annotated[int, Field(ge=0)]


class Support(StrEnum):
    """Where a statement comes from."""

    static_fact = "static_fact"
    agent_synthesis = "agent_synthesis"


class ResolutionStatus(StrEnum):
    """How well the evidence supports a statement."""

    resolved = "resolved"
    candidate = "candidate"
    unknown = "unknown"


class EntryKind(StrEnum):
    http_route = "http_route"
    cli_command = "cli_command"
    task = "task"
    scheduled = "scheduled"
    public_api = "public_api"
    agent_tool = "agent_tool"
    main = "main"
    root = "root"


class EntryDetection(StrEnum):
    adapter = "adapter"
    root_heuristic = "root_heuristic"
    agent_proposed = "agent_proposed"


class StepKind(StrEnum):
    trigger = "trigger"
    action = "action"
    decision = "decision"
    external = "external"
    result = "result"


class EdgeRelation(StrEnum):
    sequence = "sequence"
    branch = "branch"
    loop = "loop"
    exception = "exception"
    call = "call"


class LinkRelation(StrEnum):
    call = "call"
    async_task = "async_task"
    event = "event"
    state_handoff = "state_handoff"


class OmissionReason(StrEnum):
    logging = "logging"
    input_validation = "input_validation"
    error_handling = "error_handling"
    instrumentation = "instrumentation"
    merged_into_step = "merged_into_step"
    out_of_business_scope = "out_of_business_scope"


class FlowStage(StrEnum):
    """`skeleton` is the static structure before any synthesis."""

    skeleton = "skeleton"
    synthesized = "synthesized"


class FlowTier(StrEnum):
    """`primary` flows are the business processes a reader comes for: they decide
    something or have an effect. `supporting` flows are lookups and upkeep."""

    primary = "primary"
    supporting = "supporting"


class FindingSource(StrEnum):
    rule = "rule"
    agent_observation = "agent_observation"


class RiskCategory(StrEnum):
    """The kind of harm, independent of severity, lifecycle and test evidence."""

    reliability = "reliability"
    correctness = "correctness"
    data_integrity = "data_integrity"
    security = "security"
    performance = "performance"
    other = "other"


def _unique(values, label: str) -> None:
    values = list(values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class MapEntry(ContractModel):
    entry_id: Identifier
    symbol_id: SymbolId
    kind: EntryKind
    detection: EntryDetection
    framework: str | None = Field(default=None, max_length=64)
    attributes: dict[str, str] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class UnexpandedCall(ContractModel):
    """A function a step stands for as a whole: it is called here, its inside is not described.

    The counts say how much the step leaves out, and `reaches` which outside systems the
    function can get to. Both are static facts, so a reader can see what a step hides.
    """

    symbol_id: SymbolId
    conditions: Count = 0
    loops: Count = 0
    results: Count = 0
    reaches: tuple[str, ...] = ()
    reason: Text | None = None


class StepContract(ContractModel):
    """Source-backed I/O description, not a promise of runtime schema validation.

    The containing step's evidence supports these statements. Omit the contract when
    either side is unknown; do not infer required fields or validation from names.
    """

    input: Text
    output: Text
    constraints: Text | None = None


class MapStep(ContractModel):
    step_id: Identifier
    name: Name
    kind: StepKind
    support: Support
    resolution: ResolutionStatus
    reason: Text | None = None
    contract: StepContract | None = None
    anchors: tuple[Anchor, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    finding_ids: tuple[Identifier, ...] = ()
    unexpanded: tuple[UnexpandedCall, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_claim(self) -> MapStep:
        _unique(self.anchors, "step anchors")
        _unique((item.symbol_id for item in self.unexpanded), "unexpanded functions of a step")
        if self.resolution != ResolutionStatus.resolved and not self.reason:
            raise ValueError("a candidate or unknown step requires a reason")
        if self.resolution != ResolutionStatus.unknown and not self.evidence_ids:
            raise ValueError("a step needs code evidence unless it is an explicit unknown")
        if self.contract and not self.evidence_ids:
            raise ValueError("a step contract needs code evidence")
        if self.resolution == ResolutionStatus.resolved and not self.anchors:
            raise ValueError("a resolved step must be anchored in analyzer facts")
        if self.support == Support.static_fact and not self.anchors:
            raise ValueError("static_fact support requires analyzer fact anchors")
        return self


class EdgeCondition(ContractModel):
    label: Name
    branch: str | None = Field(default=None, max_length=200)
    anchor: Anchor


class MapEdge(ContractModel):
    """A control relation between two steps of one flow, never an observed execution."""

    source: Identifier
    target: Identifier
    relation: EdgeRelation
    condition: EdgeCondition | None = None
    # An agent's wording for the transition, for example "payment failed".
    label: Name | None = None
    support: Support
    resolution: ResolutionStatus
    reason: Text | None = None
    anchors: tuple[Anchor, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_claim(self) -> MapEdge:
        _unique(self.anchors, "edge anchors")
        anchored = bool(self.anchors or self.condition)
        if self.relation == EdgeRelation.branch and self.condition is None:
            raise ValueError("a branch edge requires its condition")
        if self.source == self.target and self.relation != EdgeRelation.loop:
            raise ValueError("only a loop edge may connect a step to itself")
        if self.resolution != ResolutionStatus.resolved and not self.reason:
            raise ValueError("a candidate or unknown edge requires a reason")
        if self.resolution != ResolutionStatus.unknown and not self.evidence_ids:
            raise ValueError("an edge needs code evidence unless it is an explicit unknown")
        if self.resolution == ResolutionStatus.resolved and not anchored:
            raise ValueError("a resolved edge must be anchored in analyzer facts")
        if self.support == Support.static_fact and not anchored:
            raise ValueError("static_fact support requires analyzer fact anchors")
        return self


class OmittedFact(ContractModel):
    """Something accountable the agent left out of the map, with its stated reason.

    The anchor is a fact of its own, or a call that stands for the function it calls or
    for the outside system it talks to.
    """

    anchor: Anchor
    reason: OmissionReason
    note: Text | None = None


class FlowAccounting(ContractModel):
    """Whether everything a flow has to account for is used, omitted with a reason, or neither.

    Counted in units, not in facts of a fixed call depth. The conditions, loops and
    results of the entry functions each count. So does every function called on the
    chain, once: it is expanded (its own conditions, loops and results then count too),
    stands as one step, or is omitted. Each outside system the chain talks to counts
    once. `truncated` means there were more units than the bound allows.
    """

    accountable: Count
    covered: Count
    omitted: Count
    unaccounted: Count
    truncated: bool = False

    @model_validator(mode="after")
    def counts_add_up(self) -> FlowAccounting:
        if self.covered + self.omitted + self.unaccounted != self.accountable:
            raise ValueError("covered, omitted and unaccounted must add up to accountable")
        return self


class MapFlow(ContractModel):
    flow_id: Identifier
    name: Name
    summary: Text | None = None
    stage: FlowStage
    support: Support
    tier: FlowTier = FlowTier.primary
    # A skeleton flow named by the plan: its name and summary are the agent's reading
    # of the entry points and no evidence has been checked for them yet.
    name_from_plan: bool = False
    entries: tuple[MapEntry, ...] = Field(min_length=1)
    steps: tuple[MapStep, ...] = ()
    edges: tuple[MapEdge, ...] = ()
    accounting: FlowAccounting
    omitted: tuple[OmittedFact, ...] = ()
    unaccounted: tuple[Anchor, ...] = ()
    finding_ids: tuple[Identifier, ...] = ()
    limitations: tuple[Limitation, ...] = ()

    @model_validator(mode="after")
    def flow_is_consistent(self) -> MapFlow:
        steps = {step.step_id: step for step in self.steps}
        _unique((step.step_id for step in self.steps), "step_id values in a flow")
        _unique((entry.entry_id for entry in self.entries), "entry_id values in a flow")
        _unique((item.anchor for item in self.omitted), "omitted anchors")
        _unique(self.unaccounted, "unaccounted anchors")
        if len(self.omitted) != self.accounting.omitted:
            raise ValueError("omitted facts do not match the accounting count")
        if len(self.unaccounted) != self.accounting.unaccounted:
            raise ValueError("unaccounted anchors do not match the accounting count")
        used = {anchor for step in self.steps for anchor in step.anchors}
        for edge in self.edges:
            if edge.source not in steps or edge.target not in steps:
                raise ValueError("an edge must connect two steps of its own flow")
            used.update(edge.anchors)
            if edge.condition is not None:
                used.add(edge.condition.anchor)
            if edge.relation == EdgeRelation.branch:
                source = steps[edge.source]
                if source.kind != StepKind.decision:
                    raise ValueError("a branch edge must leave a decision step")
                if edge.condition.anchor not in source.anchors:
                    raise ValueError("a branch condition must be anchored in its decision step")
        left_out = {item.anchor for item in self.omitted} | set(self.unaccounted)
        if left_out & used:
            raise ValueError("an anchor cannot be both used by the map and left out of it")
        if {item.anchor for item in self.omitted} & set(self.unaccounted):
            raise ValueError("an anchor cannot be both omitted and unaccounted")
        if self.stage == FlowStage.skeleton:
            if self.support != Support.static_fact or self.omitted:
                raise ValueError("a skeleton flow is static and omits nothing")
            if any(step.support != Support.static_fact for step in self.steps):
                raise ValueError("a skeleton flow contains only static steps")
        elif self.support != Support.agent_synthesis:
            raise ValueError("a synthesized flow is agent synthesis")
        elif self.name_from_plan:
            raise ValueError("a synthesized flow is named by its accepted description")
        return self


class MapDomain(ContractModel):
    """A grouping of flows. It has no code evidence of its own."""

    domain_id: Identifier
    name: Name
    support: Literal["agent_synthesis", "path_grouping"]
    flow_ids: tuple[Identifier, ...] = Field(min_length=1)


class LinkEnd(ContractModel):
    flow_id: Identifier
    step_id: Identifier | None = None


class MapLink(ContractModel):
    """How one flow leads into another. Both ends must cite code evidence."""

    link_id: Identifier
    source: LinkEnd
    target: LinkEnd
    relation: LinkRelation
    name: Name
    support: Support
    resolution: Literal["resolved", "candidate"]
    reason: Text | None = None
    anchors: tuple[Anchor, ...] = ()
    source_evidence_ids: tuple[str, ...] = Field(min_length=1)
    target_evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_matches_claim(self) -> MapLink:
        _unique(self.anchors, "link anchors")
        if self.source.flow_id == self.target.flow_id:
            raise ValueError("a link connects two different flows")
        if self.resolution == "candidate" and not self.reason:
            raise ValueError("a candidate link requires a reason")
        if self.resolution == "resolved" and not self.anchors:
            raise ValueError("a resolved link must be anchored in analyzer facts")
        if self.support == Support.static_fact:
            if not self.anchors:
                raise ValueError("static_fact support requires analyzer fact anchors")
            if self.relation not in {LinkRelation.call, LinkRelation.async_task}:
                raise ValueError("only call and async_task links can be static facts")
        return self


class MapFinding(ContractModel):
    """A risk finding from a local rule, or an agent observation shown apart from rules."""

    finding_id: Identifier
    source: FindingSource
    rule: str | None = Field(default=None, min_length=1, max_length=128)
    severity: Severity
    category: RiskCategory | None = None
    statement: Text
    anchors: tuple[Anchor, ...] = ()
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    condition: Text | None = None
    gap: Text | None = None

    @model_validator(mode="after")
    def source_matches_claim(self) -> MapFinding:
        _unique(self.anchors, "finding anchors")
        if self.source == FindingSource.rule:
            if not self.rule or not self.anchors:
                raise ValueError("a rule finding names its rule and its fact anchors")
        else:
            if self.rule is not None:
                raise ValueError("an agent observation does not claim a rule")
            if self.severity == Severity.high:
                raise ValueError("an agent observation cannot be rated high")
        return self


class SkippedEntry(ContractModel):
    """An entry deliberately left out of the map, with the reason given for it."""

    entry_id: Identifier
    symbol_id: SymbolId
    reason: str = Field(min_length=1, max_length=64)
    note: Text | None = None


class MapCoverage(ContractModel):
    """The declared scope of the analysis: what was planned, skipped and left unhandled."""

    scope: Text
    entries_total: Count
    entries_planned: Count
    entries_skipped: Count
    skipped_entries: tuple[SkippedEntry, ...] = ()
    entries_unhandled: Count
    tasks_total: Count
    tasks_validated: Count
    tasks_pending: Count
    tasks_failed: Count = 0
    limitations: tuple[Limitation, ...] = ()

    @model_validator(mode="after")
    def counts_add_up(self) -> MapCoverage:
        entries = self.entries_planned + self.entries_skipped + self.entries_unhandled
        if entries != self.entries_total:
            raise ValueError("planned, skipped and unhandled entries must add up to the total")
        if self.tasks_validated + self.tasks_pending + self.tasks_failed != self.tasks_total:
            raise ValueError("validated, pending and failed tasks must add up to the total")
        if self.skipped_entries and len(self.skipped_entries) != self.entries_skipped:
            raise ValueError("listed skipped entries must match the skipped count")
        return self


class BusinessMap(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    side: EvidenceSide
    analysis_status: Literal["complete", "partial"]
    domains: tuple[MapDomain, ...] = ()
    flows: tuple[MapFlow, ...] = ()
    links: tuple[MapLink, ...] = ()
    findings: tuple[MapFinding, ...] = ()
    unassigned_finding_ids: tuple[Identifier, ...] = ()
    coverage: MapCoverage
    limitations: tuple[Limitation, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def document_is_consistent(self) -> BusinessMap:
        flows = {flow.flow_id: flow for flow in self.flows}
        _unique((flow.flow_id for flow in self.flows), "flow_id values")
        _unique((domain.domain_id for domain in self.domains), "domain_id values")
        _unique((link.link_id for link in self.links), "link_id values")
        _unique((finding.finding_id for finding in self.findings), "finding_id values")
        _unique((step.step_id for flow in self.flows for step in flow.steps), "step_id values")
        _unique(
            (entry.entry_id for flow in self.flows for entry in flow.entries), "entry_id values"
        )
        _unique(
            (entry.symbol_id for flow in self.flows for entry in flow.entries),
            "entry symbols across flows",
        )
        grouped = [flow_id for domain in self.domains for flow_id in domain.flow_ids]
        _unique(grouped, "the domain of a flow")
        if set(grouped) - flows.keys():
            raise ValueError("a domain refers to an unknown flow")
        for link in self.links:
            for end in (link.source, link.target):
                flow = flows.get(end.flow_id)
                if flow is None:
                    raise ValueError("a link refers to an unknown flow")
                if end.step_id is not None and end.step_id not in {
                    step.step_id for step in flow.steps
                }:
                    raise ValueError("a link refers to a step outside its flow")
        self._check_findings()
        self._check_evidence()
        if self.analysis_status == "complete":
            self._check_complete()
        return self

    def _check_findings(self) -> None:
        known = {finding.finding_id for finding in self.findings}
        placed = [
            *(fid for flow in self.flows for fid in flow.finding_ids),
            *(fid for flow in self.flows for step in flow.steps for fid in step.finding_ids),
        ]
        referenced = {*placed, *self.unassigned_finding_ids}
        if referenced - known:
            raise ValueError("a finding reference points to an unknown finding")
        if set(placed) & set(self.unassigned_finding_ids):
            raise ValueError("a finding cannot be both placed on the map and unassigned")
        if known - referenced:
            raise ValueError("every finding is placed on a step or flow, or listed as unassigned")

    def _check_evidence(self) -> None:
        referenced = [
            *(ref for flow in self.flows for entry in flow.entries for ref in entry.evidence_ids),
            *(ref for flow in self.flows for step in flow.steps for ref in step.evidence_ids),
            *(ref for flow in self.flows for edge in flow.edges for ref in edge.evidence_ids),
            *(ref for flow in self.flows for item in flow.limitations for ref in item.evidence_ids),
            *(ref for link in self.links for ref in link.source_evidence_ids),
            *(ref for link in self.links for ref in link.target_evidence_ids),
            *(ref for finding in self.findings for ref in finding.evidence_ids),
            *(ref for item in self.limitations for ref in item.evidence_ids),
            *(ref for item in self.coverage.limitations for ref in item.evidence_ids),
        ]
        validate_evidence_refs(
            snapshot_id=self.snapshot_id, evidence=self.evidence, evidence_ids=tuple(referenced)
        )
        if any(ref.side != self.side for ref in self.evidence):
            raise ValueError("a map only cites evidence from its own side")

    def _check_complete(self) -> None:
        if self.coverage.tasks_pending or self.coverage.tasks_failed:
            raise ValueError("a complete map has no pending or failed tasks")
        for flow in self.flows:
            if flow.stage != FlowStage.synthesized:
                raise ValueError("a complete map has no skeleton flows left")
            if flow.accounting.unaccounted or flow.accounting.truncated:
                raise ValueError("a complete map has no unaccounted or truncated facts")
        limitations = (
            *self.limitations,
            *self.coverage.limitations,
            *(item for flow in self.flows for item in flow.limitations),
        )
        if any(item.affects_completeness for item in limitations):
            raise ValueError("a complete map has no limitation that affects completeness")

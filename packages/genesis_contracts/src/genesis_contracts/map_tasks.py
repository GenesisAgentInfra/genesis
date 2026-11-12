"""What a coding agent hands to the CLI: a plan, and one submission per flow task.

Draft contract. An agent never writes the map itself. It names things in business
language and points at code; the CLI checks every reference against the frozen
snapshot, assigns identities, and decides what counts as statically supported.

Evidence is cited either by an existing `evidence_id`, or by a source range with a
short `quote` from that range. The quote lets the CLI confirm the agent read the
same frozen content it is citing.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .business_map import (
    Anchor,
    EdgeRelation,
    EntryKind,
    Identifier,
    Name,
    OmissionReason,
    ResolutionStatus,
    StepKind,
    SymbolId,
    Text,
    _unique,
)
from .models import ContractModel, EvidenceSide, Severity, validate_repo_path

MAX_STEPS = 60
MAX_EDGES = 150
MAX_OBSERVATIONS = 8


class SkipReason(StrEnum):
    infrastructure = "infrastructure"
    test_helper = "test_helper"
    duplicate = "duplicate"
    out_of_scope = "out_of_scope"
    budget = "budget"


class EvidenceCite(ContractModel):
    """Either `evidence_id`, or `path` + line range + `quote` from the frozen source."""

    evidence_id: str | None = Field(default=None, min_length=1)
    side: EvidenceSide = EvidenceSide.head
    path: str | None = Field(default=None, min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, min_length=1, max_length=400)

    @model_validator(mode="after")
    def exactly_one_form(self) -> EvidenceCite:
        ranged = (self.path, self.start_line, self.end_line, self.quote)
        if self.evidence_id is not None:
            if any(value is not None for value in ranged):
                raise ValueError("cite an evidence_id or a source range, not both")
            return self
        if any(value is None for value in ranged):
            raise ValueError("a source range needs path, start_line, end_line and quote")
        validate_repo_path(self.path)
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class PlanDomain(ContractModel):
    key: Identifier
    name: Name


class PlanFlow(ContractModel):
    key: Identifier
    name: Name | None = None
    domain: Identifier | None = None
    entry_ids: tuple[Identifier, ...] = Field(min_length=1)


class PlanSkip(ContractModel):
    entry_id: Identifier
    reason: SkipReason
    note: Text | None = None


class ProposedEntry(ContractModel):
    """An entry the analyzers did not recognise, proposed with evidence."""

    symbol_id: SymbolId
    kind: EntryKind
    reason: Text
    evidence: tuple[EvidenceCite, ...] = Field(min_length=1)


class MapPlan(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    domains: tuple[PlanDomain, ...] = ()
    flows: tuple[PlanFlow, ...] = ()
    skipped: tuple[PlanSkip, ...] = ()
    proposed_entries: tuple[ProposedEntry, ...] = ()

    @model_validator(mode="after")
    def plan_is_consistent(self) -> MapPlan:
        _unique((item.key for item in self.domains), "domain keys")
        _unique((item.key for item in self.flows), "flow keys")
        _unique((item.symbol_id for item in self.proposed_entries), "proposed entry symbols")
        domains = {item.key for item in self.domains}
        if any(item.domain is not None and item.domain not in domains for item in self.flows):
            raise ValueError("a flow refers to an unknown domain key")
        assigned = [
            *(entry for flow in self.flows for entry in flow.entry_ids),
            *(item.entry_id for item in self.skipped),
        ]
        _unique(assigned, "the flow or skip decision of an entry")
        return self


class SubmittedStep(ContractModel):
    key: Identifier
    name: Name
    kind: StepKind
    evidence: tuple[EvidenceCite, ...] = ()
    anchors: tuple[Anchor, ...] = ()
    resolution: ResolutionStatus = ResolutionStatus.resolved
    reason: Text | None = None
    # Why one step is enough for a large function this step calls without describing it.
    unexpanded_reason: Text | None = None


class SubmittedEdge(ContractModel):
    source: Identifier
    target: Identifier
    relation: EdgeRelation
    branch: str | None = Field(default=None, min_length=1, max_length=200)
    label: Name | None = None
    evidence: tuple[EvidenceCite, ...] = ()
    resolution: ResolutionStatus = ResolutionStatus.resolved
    reason: Text | None = None

    @model_validator(mode="after")
    def branch_is_named(self) -> SubmittedEdge:
        if (self.relation == EdgeRelation.branch) != (self.branch is not None):
            raise ValueError("exactly the branch edges name the branch they take")
        return self


class SubmittedOmission(ContractModel):
    anchor: Anchor
    reason: OmissionReason
    note: Text | None = None


class SubmittedObservation(ContractModel):
    """A risk the agent noticed. Shown apart from rule findings and never rated high."""

    statement: Text
    severity: Literal[Severity.info, Severity.low, Severity.medium] = Severity.low
    step: Identifier
    evidence: tuple[EvidenceCite, ...] = Field(min_length=1)
    gap: Text | None = None


class ChangeAssessment(ContractModel):
    """An agent's reading of one change: what it means, and whether tests cover it.

    Leave `verdict` out to keep the static result. A verdict needs a `note` that says
    what the listed tests do or do not exercise; `test_ids` narrows the related tests to
    the ones the assessment is about.
    """

    change_id: Identifier
    summary: Text
    effect: Text | None = None
    verdict: Literal["covered", "reached_only", "not_reached", "unknown"] | None = None
    note: Text | None = None
    test_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verdict_is_explained(self) -> ChangeAssessment:
        _unique(self.test_ids, "test ids")
        if self.verdict is not None and not self.note:
            raise ValueError("a coverage verdict needs a note explaining it")
        if self.verdict is None and self.test_ids:
            raise ValueError("test ids belong to a coverage verdict")
        return self


class ChangeSubmission(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    changes: tuple[ChangeAssessment, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_assessment_per_change(self) -> ChangeSubmission:
        _unique((item.change_id for item in self.changes), "assessed change ids")
        return self


class FlowSubmission(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    name: Name
    summary: Text | None = None
    steps: tuple[SubmittedStep, ...] = Field(min_length=1, max_length=MAX_STEPS)
    edges: tuple[SubmittedEdge, ...] = Field(default=(), max_length=MAX_EDGES)
    omitted: tuple[SubmittedOmission, ...] = ()
    observations: tuple[SubmittedObservation, ...] = Field(default=(), max_length=MAX_OBSERVATIONS)

    @model_validator(mode="after")
    def references_resolve(self) -> FlowSubmission:
        keys = {step.key for step in self.steps}
        _unique((step.key for step in self.steps), "step keys")
        _unique((item.anchor for item in self.omitted), "omitted anchors")
        if any(edge.source not in keys or edge.target not in keys for edge in self.edges):
            raise ValueError("an edge refers to an unknown step key")
        if any(item.step not in keys for item in self.observations):
            raise ValueError("an observation refers to an unknown step key")
        return self

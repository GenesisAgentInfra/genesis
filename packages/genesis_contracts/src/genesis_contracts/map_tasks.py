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

from pydantic import Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

from .business_map import (
    Anchor,
    EdgeRelation,
    EntryKind,
    FlowTier,
    Identifier,
    Name,
    OmissionReason,
    ResolutionStatus,
    RiskCategory,
    StepContract,
    StepKind,
    SymbolId,
    Text,
)
from .models import ContractModel, EvidenceSide, Severity, validate_repo_path

MAX_STEPS = 60
MAX_EDGES = 150
MAX_OBSERVATIONS = 8


def place(parts) -> str:
    """Where in a submitted document something is, as problems name it: `steps[1].key`."""
    text = ""
    for part in parts:
        text += f"[{part}]" if isinstance(part, int) else ("." if text else "") + str(part)
    return text


def _missing(at: tuple, key: str, what: str) -> InitErrorDetails:
    """A reference to a key that nothing in the document has."""
    said = PydanticCustomError(
        "reference", "No {what} has the key '{key}'.", {"what": what, "key": key}
    )
    return InitErrorDetails(type=said, loc=at, input=key)


def _repeated(items) -> list[InitErrorDetails]:
    """One problem for each value that repeats an earlier one. `items` are (place, value)."""
    first: dict = {}
    found = []
    for at, value in items:
        if value in first:
            said = PydanticCustomError(
                "duplicate",
                "'{value}' is already used at {first}.",
                {"value": value, "first": place(first[value])},
            )
            found.append(InitErrorDetails(type=said, loc=at, input=value))
        else:
            first[value] = at
    return found


def _refuse(found: list[InitErrorDetails]) -> None:
    """Report problems between items at the items themselves.

    A `ValueError` raised by a model validator is placed at the model: it would say that
    some edge of the document is wrong without saying which one.
    """
    if found:
        raise ValidationError.from_exception_data("submission", found)


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
    """One business process and the entry points that start it.

    `name` is what a person would call it, and `summary` one sentence on what a user
    gets done with it; both are shown before the flow is described. The CLI requires a
    name in a plan an agent submits.
    """

    key: Identifier
    name: Name | None = None
    summary: Text | None = None
    tier: FlowTier = FlowTier.primary
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
        domains = {item.key for item in self.domains}
        # An entry starts one flow, or is skipped once.
        assigned = [
            *(
                (("flows", index, "entry_ids", position), entry)
                for index, flow in enumerate(self.flows)
                for position, entry in enumerate(flow.entry_ids)
            ),
            *(
                (("skipped", index, "entry_id"), item.entry_id)
                for index, item in enumerate(self.skipped)
            ),
        ]
        _refuse(
            [
                *_repeated(
                    (("domains", index, "key"), item.key) for index, item in enumerate(self.domains)
                ),
                *_repeated(
                    (("flows", index, "key"), item.key) for index, item in enumerate(self.flows)
                ),
                *_repeated(
                    (("proposed_entries", index, "symbol_id"), item.symbol_id)
                    for index, item in enumerate(self.proposed_entries)
                ),
                *(
                    _missing(("flows", index, "domain"), item.domain, "domain in this plan")
                    for index, item in enumerate(self.flows)
                    if item.domain is not None and item.domain not in domains
                ),
                *_repeated(assigned),
            ]
        )
        return self


class SubmittedStep(ContractModel):
    key: Identifier
    name: Name
    kind: StepKind
    evidence: tuple[EvidenceCite, ...] = ()
    anchors: tuple[Anchor, ...] = ()
    resolution: ResolutionStatus = ResolutionStatus.resolved
    reason: Text | None = None
    contract: StepContract | None = None
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
    category: RiskCategory | None = None
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
    short_summary: str | None = Field(default=None, min_length=1, max_length=120)
    effect: Text | None = None
    verdict: Literal["covered", "reached_only", "not_reached", "unknown"] | None = None
    note: Text | None = None
    test_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verdict_is_explained(self) -> ChangeAssessment:
        _refuse(_repeated((("test_ids", index), item) for index, item in enumerate(self.test_ids)))
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
        _refuse(
            _repeated(
                (("changes", index, "change_id"), item.change_id)
                for index, item in enumerate(self.changes)
            )
        )
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
        step = "step in this submission"
        _refuse(
            [
                *_repeated(
                    (("steps", index, "key"), item.key) for index, item in enumerate(self.steps)
                ),
                *_repeated(
                    (("omitted", index, "anchor"), item.anchor)
                    for index, item in enumerate(self.omitted)
                ),
                *(
                    _missing(("edges", index, end), key, step)
                    for index, edge in enumerate(self.edges)
                    for end, key in (("source", edge.source), ("target", edge.target))
                    if key not in keys
                ),
                *(
                    _missing(("observations", index, "step"), item.step, step)
                    for index, item in enumerate(self.observations)
                    if item.step not in keys
                ),
            ]
        )
        return self

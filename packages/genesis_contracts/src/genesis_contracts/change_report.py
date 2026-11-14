"""Change report: fact-level changes between two snapshots, projected onto the head map.

Draft contract. Changes come from a deterministic diff of static facts, never from
comparing two independently written summaries, so rewording a map does not create a
change. An agent adds only the explanation and the test coverage assessment.

A coverage verdict is graded and always carries its basis. No verdict states that a
test ran or passed; execution data is reported apart from whether assertions suffice.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .business_map import (
    Anchor,
    BusinessMap,
    Identifier,
    MapFinding,
    MapFlow,
    Name,
    SymbolId,
    Text,
    _unique,
)
from .models import (
    ContractModel,
    EvidenceRef,
    EvidenceSide,
    Limitation,
    validate_evidence_refs,
    validate_repo_path,
)


class ChangeKind(StrEnum):
    condition_added = "condition_added"
    condition_removed = "condition_removed"
    condition_modified = "condition_modified"
    call_added = "call_added"
    call_removed = "call_removed"
    call_modified = "call_modified"
    call_target_changed = "call_target_changed"
    result_added = "result_added"
    result_removed = "result_removed"
    result_modified = "result_modified"
    loop_added = "loop_added"
    loop_removed = "loop_removed"
    loop_bound_changed = "loop_bound_changed"
    symbol_added = "symbol_added"
    symbol_removed = "symbol_removed"
    symbol_moved = "symbol_moved"
    # Source that is not a condition, call, loop or result: assignments, defaults,
    # decorators, docstrings. Found by comparing lines, so nothing changed goes unlisted.
    source_added = "source_added"
    source_removed = "source_removed"
    source_modified = "source_modified"
    test_added = "test_added"
    test_removed = "test_removed"
    test_modified = "test_modified"


class ProjectionStatus(StrEnum):
    projected = "projected"
    removed_step = "removed_step"
    unassigned = "unassigned"


class CoverageVerdict(StrEnum):
    covered = "covered"
    reached_only = "reached_only"
    not_reached = "not_reached"
    unknown = "unknown"


class CoverageBasis(StrEnum):
    static_fact = "static_fact"
    agent_assessment = "agent_assessment"
    imported_coverage = "imported_coverage"


class CaseTag(StrEnum):
    """Static association between one test and the changed code."""

    related = "related"
    assertion_found = "assertion_found"
    fixture_or_mock_related = "fixture_or_mock_related"
    # Named by the assessing agent; static analysis found no call path to the change.
    agent_identified = "agent_identified"


class ChangeSide(ContractModel):
    """One side of a changed fact, filled in by the CLI from the fact diff."""

    side: EvidenceSide
    text: Text
    anchor: Anchor
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class RemovedStep(ContractModel):
    """A step of the previous map that no longer exists on the head side."""

    step_id: Identifier
    name: Name


class ChangeProjection(ContractModel):
    status: ProjectionStatus
    flow_id: Identifier | None = None
    step_id: Identifier | None = None
    removed_step: RemovedStep | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def target_matches_status(self) -> ChangeProjection:
        if self.status == ProjectionStatus.projected:
            if not (self.flow_id and self.step_id) or self.removed_step:
                raise ValueError("a projected change names a flow and one of its steps")
        elif self.status == ProjectionStatus.removed_step:
            if not (self.flow_id and self.removed_step) or self.step_id:
                raise ValueError("a removed-step projection names a flow and the removed step")
        else:
            if self.flow_id or self.step_id or self.removed_step:
                raise ValueError("an unassigned change has no map target")
            if not self.reason:
                raise ValueError("an unassigned change states why it has no map target")
        return self


class ChangeExplanation(ContractModel):
    """Business meaning of a change, written by an agent from both sides' evidence."""

    support: Literal["agent_synthesis"] = "agent_synthesis"
    summary: Text
    short_summary: str | None = Field(default=None, min_length=1, max_length=120)
    effect: Text | None = None


class CaseEvidence(ContractModel):
    """One test's relation to a change. `executed` stays unset without execution data."""

    test_id: str = Field(min_length=1, max_length=1024)
    tags: tuple[CaseTag, ...] = ()
    executed: bool | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def relation_is_stated(self) -> CaseEvidence:
        _unique(self.tags, "case tags")
        if not self.tags and not self.executed:
            raise ValueError("a listed test is statically related or was executed")
        return self


class CoverageAssessment(ContractModel):
    """Whether existing tests cover one change, graded and shown with its basis."""

    verdict: CoverageVerdict
    basis: tuple[CoverageBasis, ...] = ()
    execution_data: Literal["imported", "not_collected"]
    note: Text | None = None
    items: tuple[CaseEvidence, ...] = ()

    @model_validator(mode="after")
    def verdict_matches_evidence(self) -> CoverageAssessment:
        _unique(self.basis, "coverage basis")
        _unique((item.test_id for item in self.items), "tests in one assessment")
        executed = [item for item in self.items if item.executed]
        if self.execution_data == "not_collected":
            if any(item.executed is not None for item in self.items):
                raise ValueError("execution status needs imported execution data")
            if CoverageBasis.imported_coverage in self.basis:
                raise ValueError("imported_coverage basis needs imported execution data")
        elif CoverageBasis.imported_coverage in self.basis and not executed:
            raise ValueError("imported_coverage basis needs a test that executed the change")
        reaches = [
            item
            for item in self.items
            if item.executed or {CaseTag.related, CaseTag.agent_identified} & set(item.tags)
        ]
        named = any(CaseTag.agent_identified in item.tags for item in self.items)
        if named and CoverageBasis.agent_assessment not in self.basis:
            raise ValueError("a test named by an agent needs the agent_assessment basis")
        if self.verdict == CoverageVerdict.covered:
            if not any(CaseTag.assertion_found in item.tags for item in reaches):
                raise ValueError("covered needs a test that reaches the change and asserts on it")
            if not {CoverageBasis.agent_assessment, CoverageBasis.imported_coverage} & set(
                self.basis
            ):
                raise ValueError("covered needs evidence that test input takes the changed path")
        elif self.verdict == CoverageVerdict.reached_only:
            if not reaches or not self.basis:
                raise ValueError("reached_only needs a test that reaches the change")
            if not self.note:
                raise ValueError("reached_only states what is missing")
        elif self.verdict == CoverageVerdict.not_reached:
            if reaches:
                raise ValueError("not_reached cannot list a test that reaches the change")
            if not {CoverageBasis.static_fact, CoverageBasis.agent_assessment} & set(self.basis):
                raise ValueError("not_reached relies on the static test index or an assessment")
        elif not self.note:
            raise ValueError("an unknown verdict states what could not be analyzed")
        return self


_ADDED = {
    ChangeKind.condition_added,
    ChangeKind.call_added,
    ChangeKind.result_added,
    ChangeKind.loop_added,
    ChangeKind.symbol_added,
    ChangeKind.source_added,
    ChangeKind.test_added,
}
_REMOVED = {
    ChangeKind.condition_removed,
    ChangeKind.call_removed,
    ChangeKind.result_removed,
    ChangeKind.loop_removed,
    ChangeKind.symbol_removed,
    ChangeKind.source_removed,
    ChangeKind.test_removed,
}
_TEST_KINDS = {ChangeKind.test_added, ChangeKind.test_removed, ChangeKind.test_modified}


class ChangeItem(ContractModel):
    change_id: Identifier
    kind: ChangeKind
    symbol_id: SymbolId
    before: ChangeSide | None = None
    after: ChangeSide | None = None
    # What changed when the two texts alone do not show it.
    detail: Text | None = None
    projection: ChangeProjection
    # Further flows whose steps are anchored on the same changed code.
    other_projections: tuple[ChangeProjection, ...] = ()
    explanation: ChangeExplanation | None = None
    tests: CoverageAssessment | None = None
    finding_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def sides_match_kind(self) -> ChangeItem:
        if self.before is not None and self.before.side != EvidenceSide.base:
            raise ValueError("the before side of a change is the base snapshot")
        if self.after is not None and self.after.side != EvidenceSide.head:
            raise ValueError("the after side of a change is the head snapshot")
        if self.kind in _ADDED:
            if self.before is not None or self.after is None:
                raise ValueError("an added fact exists only on the head side")
        elif self.kind in _REMOVED:
            if self.after is not None or self.before is None:
                raise ValueError("a removed fact exists only on the base side")
        elif self.before is None or self.after is None:
            raise ValueError("a modified fact has both sides")
        if self.kind in _TEST_KINDS and self.tests is not None:
            raise ValueError("a change to a test carries no coverage assessment of itself")
        if any(item.status == ProjectionStatus.unassigned for item in self.other_projections):
            raise ValueError("a further projection names a place on the map")
        if self.other_projections and self.projection.status == ProjectionStatus.unassigned:
            raise ValueError("an unassigned change has no further projections")
        return self


class FindingChange(ContractModel):
    """How a risk finding relates to this change set."""

    status: Literal["introduced", "resolved", "persisting"]
    finding: MapFinding
    flow_id: Identifier | None = None
    step_id: Identifier | None = None


class PropagatedImpact(ContractModel):
    """A flow that can reach changed code through calls but has no step anchored on it."""

    flow_id: Identifier
    change_ids: tuple[Identifier, ...] = Field(min_length=1)
    reason: Text


class PossibleEntry(ContractModel):
    """A function no code calls that leads to changed code and starts no flow on the map.

    It may be a way in the analyzers did not recognise, or code nothing uses.
    """

    entry_id: Identifier
    symbol_id: SymbolId
    change_ids: tuple[Identifier, ...] = Field(min_length=1)


class UnanalyzedChange(ContractModel):
    """A changed file the analyzers could not turn into facts."""

    path: str = Field(min_length=1)
    change: Literal["added", "modified", "deleted", "renamed"]
    reason: Text

    @model_validator(mode="after")
    def safe_relative_path(self) -> UnanalyzedChange:
        validate_repo_path(self.path)
        return self


class ChangeReport(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    # What was compared: the names the user gave, and what they resolved to.
    base_ref: str | None = Field(default=None, min_length=1, max_length=400)
    base_revision: str | None = Field(default=None, min_length=1, max_length=400)
    head_ref: str | None = Field(default=None, min_length=1, max_length=400)
    head_revision: str | None = Field(default=None, min_length=1, max_length=400)
    analysis_status: Literal["complete", "partial"]
    changes: tuple[ChangeItem, ...] = ()
    removed_flows: tuple[MapFlow, ...] = ()
    possibly_affected: tuple[PropagatedImpact, ...] = ()
    possible_entries: tuple[PossibleEntry, ...] = ()
    unanalyzed_changes: tuple[UnanalyzedChange, ...] = ()
    finding_changes: tuple[FindingChange, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def document_is_consistent(self) -> ChangeReport:
        changes = {item.change_id for item in self.changes}
        findings = {item.finding.finding_id for item in self.finding_changes}
        _unique((item.change_id for item in self.changes), "change_id values")
        _unique((item.finding.finding_id for item in self.finding_changes), "finding_id values")
        _unique((flow.flow_id for flow in self.removed_flows), "removed flow_id values")
        if any(set(item.finding_ids) - findings for item in self.changes):
            raise ValueError("a change refers to a finding the report does not list")
        if any(set(item.change_ids) - changes for item in self.possibly_affected):
            raise ValueError("a propagated impact refers to an unknown change")
        if any(set(item.change_ids) - changes for item in self.possible_entries):
            raise ValueError("a possible entry refers to an unknown change")
        self._check_evidence()
        if self.analysis_status == "complete":
            self._check_complete()
        return self

    def _check_evidence(self) -> None:
        sided: list[tuple[EvidenceSide, str]] = []
        for item in self.changes:
            for part in (item.before, item.after):
                if part is not None:
                    sided.extend((part.side, ref) for ref in part.evidence_ids)
            if item.tests is not None:
                sided.extend(
                    (EvidenceSide.head, ref)
                    for case in item.tests.items
                    for ref in case.evidence_ids
                )
        for flow in self.removed_flows:
            refs = [
                *(ref for entry in flow.entries for ref in entry.evidence_ids),
                *(ref for step in flow.steps for ref in step.evidence_ids),
                *(ref for edge in flow.edges for ref in edge.evidence_ids),
                *(ref for item in flow.limitations for ref in item.evidence_ids),
            ]
            sided.extend((EvidenceSide.base, ref) for ref in refs)
        for item in self.finding_changes:
            side = EvidenceSide.base if item.status == "resolved" else EvidenceSide.head
            sided.extend((side, ref) for ref in item.finding.evidence_ids)
        unsided = [ref for item in self.limitations for ref in item.evidence_ids]
        validate_evidence_refs(
            snapshot_id=self.snapshot_id,
            evidence=self.evidence,
            evidence_ids=(*(ref for _, ref in sided), *unsided),
        )
        by_id = {ref.evidence_id: ref for ref in self.evidence}
        if any(by_id[ref].side != side for side, ref in sided):
            raise ValueError("evidence is cited on the wrong side of the change")

    def owed(self) -> tuple[ChangeItem, ...]:
        """The changes that have to be explained: on the map, or within reach of a flow.

        A change a flow can get to is not done with because no step covers it yet. It
        comes onto the map as its flow is described, or it is explained where it is.
        """
        reached = {key for item in self.possibly_affected for key in item.change_ids}
        return tuple(
            item
            for item in self.changes
            if item.projection.status != ProjectionStatus.unassigned or item.change_id in reached
        )

    def _check_complete(self) -> None:
        for item in self.owed():
            if item.explanation is None:
                raise ValueError(
                    "a complete report explains every change on the map or within reach of a flow"
                )
            placed = item.projection.status != ProjectionStatus.unassigned
            if placed and item.tests is None and item.kind not in _TEST_KINDS:
                raise ValueError("a complete report assesses coverage of every placed change")
        if any(item.affects_completeness for item in self.limitations):
            raise ValueError("a complete report has no limitation that affects completeness")


def validate_change_report_against_map(report: ChangeReport, head: BusinessMap) -> None:
    """Check that a report's map targets exist in the head map it was projected onto."""
    if head.side != EvidenceSide.head:
        raise ValueError("changes are projected onto a head-side map")
    if report.snapshot_id != head.snapshot_id:
        raise ValueError("the report and the map come from different snapshots")
    steps = {flow.flow_id: {step.step_id for step in flow.steps} for flow in head.flows}
    for item in report.changes:
        for target in (item.projection, *item.other_projections):
            if target.status == ProjectionStatus.unassigned:
                continue
            if target.flow_id not in steps:
                raise ValueError("a change is projected onto an unknown flow")
            if (
                target.status == ProjectionStatus.projected
                and target.step_id not in steps[target.flow_id]
            ):
                raise ValueError("a change is projected onto a step outside its flow")
            if target.status == ProjectionStatus.removed_step and (
                target.removed_step.step_id in steps[target.flow_id]
            ):
                raise ValueError("a removed step still exists on the head map")
    if any(item.flow_id not in steps for item in report.possibly_affected):
        raise ValueError("a propagated impact refers to an unknown flow")
    if {flow.flow_id for flow in report.removed_flows} & steps.keys():
        raise ValueError("a removed flow still exists on the head map")
    on_map = {finding.finding_id for finding in head.findings}
    for item in report.finding_changes:
        present = item.finding.finding_id in on_map
        if item.status == "resolved" and present:
            raise ValueError("a resolved finding is still on the head map")
        if item.status != "resolved" and not present:
            raise ValueError("an introduced or persisting finding is missing from the head map")

"""What a coding agent hands to the CLI for a repository no analyzer reads.

Draft contract. Here the agent finds the ways into the system and reads the changes
itself; there are no static facts to start from. The CLI still checks every citation
against the frozen snapshot and writes the same map and change report. A flow is
described with `map_tasks.FlowSubmission`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .business_map import EntryKind, FlowTier, Identifier, Name, Text
from .map_tasks import EvidenceCite, PlanDomain, _missing, _refuse, _repeated
from .models import ContractModel


class AgentEntry(ContractModel):
    """A way into the system the agent found, with the code that shows it.

    `name` is what starts it, as the code names it: `POST /orders`, `placeOrder`.
    """

    name: Name
    kind: EntryKind
    evidence: tuple[EvidenceCite, ...] = Field(min_length=1)


class AgentPlanFlow(ContractModel):
    """One business process a person would name, and the entries that start it."""

    key: Identifier
    name: Name
    summary: Text | None = None
    tier: FlowTier = FlowTier.primary
    domain: Identifier | None = None
    entries: tuple[AgentEntry, ...] = Field(min_length=1)


class AgentPlan(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    domains: tuple[PlanDomain, ...] = ()
    flows: tuple[AgentPlanFlow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def plan_is_consistent(self) -> AgentPlan:
        domains = {item.key for item in self.domains}
        _refuse(
            [
                *_repeated(
                    (("domains", index, "key"), item.key) for index, item in enumerate(self.domains)
                ),
                *_repeated(
                    (("flows", index, "key"), item.key) for index, item in enumerate(self.flows)
                ),
                *(
                    _missing(("flows", index, "domain"), item.domain, "domain in this plan")
                    for index, item in enumerate(self.flows)
                    if item.domain is not None and item.domain not in domains
                ),
            ]
        )
        return self


class CitedTest(ContractModel):
    """A test the agent read. `asserts` says it checks what the changed code produces."""

    name: str = Field(min_length=1, max_length=200)
    evidence: tuple[EvidenceCite, ...] = Field(min_length=1)
    asserts: bool = False


class AgentChangeAssessment(ContractModel):
    """An agent's reading of one change: what it means, and whether tests cover it."""

    change_id: Identifier
    summary: Text
    short_summary: str | None = Field(default=None, min_length=1, max_length=120)
    effect: Text | None = None
    verdict: Literal["covered", "reached_only", "not_reached", "unknown"] | None = None
    note: Text | None = None
    tests: tuple[CitedTest, ...] = ()

    @model_validator(mode="after")
    def verdict_is_explained(self) -> AgentChangeAssessment:
        _refuse(
            _repeated(
                (("tests", index, "name"), item.name) for index, item in enumerate(self.tests)
            )
        )
        if self.verdict is not None and not self.note:
            raise ValueError("a coverage verdict needs a note explaining it")
        if self.verdict is None and self.tests:
            raise ValueError("cited tests belong to a coverage verdict")
        return self


class AgentChangeSubmission(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    changes: tuple[AgentChangeAssessment, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_assessment_per_change(self) -> AgentChangeSubmission:
        _refuse(
            _repeated(
                (("changes", index, "change_id"), item.change_id)
                for index, item in enumerate(self.changes)
            )
        )
        return self

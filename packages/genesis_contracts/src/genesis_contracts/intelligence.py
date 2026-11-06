"""Local A3-A7 analysis details; projections keep the existing B4 contract."""

from __future__ import annotations

from typing import Literal

from .models import (
    AgentLoopFact,
    CapabilityStatus,
    ContractModel,
    EvidenceSide,
    FlowImpact,
    ImpactGraph,
    Resolution,
    TestDefinition,
)
from .python import LoopControl, ValueExpr


class ModelCall(ContractModel):
    call_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    provider: Literal["openai", "anthropic"]
    api: str
    resolution: Resolution
    model: ValueExpr
    prompt: tuple[ValueExpr, ...]
    tools: ValueExpr | None = None
    parameters: tuple[tuple[str, ValueExpr], ...]
    conditions: tuple[str, ...]
    loop_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class ToolDispatch(ContractModel):
    call_id: str
    kind: Literal["dictionary", "if", "match"]
    tool_name: str
    target: Resolution
    selector: str
    model_call_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]


class AgentLoop(ContractModel):
    side: EvidenceSide
    loop: AgentLoopFact
    dispatch_sites: tuple[ToolDispatch, ...] = ()
    controls: tuple[LoopControl, ...] = ()
    schema_complete: bool = False
    dispatch_complete: bool = False
    schema_tool_names: tuple[str, ...]
    dispatch_tool_names: tuple[str, ...]
    unmatched_schema_tools: tuple[str, ...]
    unmatched_dispatch_tools: tuple[str, ...]


class PatternAnalysis(ContractModel):
    model_calls: tuple[ModelCall, ...]
    loops: tuple[AgentLoop, ...]
    coverage: CapabilityStatus


class ImpactAnalysis(ContractModel):
    graph: ImpactGraph
    affected_symbols: tuple[tuple[EvidenceSide, str], ...]
    changed_symbols: tuple[tuple[EvidenceSide, str], ...]
    unresolved_calls: tuple[str, ...]
    coverage: CapabilityStatus


class FlowSideImpact(ContractModel):
    side: EvidenceSide
    impact: FlowImpact


class FixtureUse(ContractModel):
    name: str
    requested_by: str
    kind: Literal["parameter", "usefixtures", "autouse", "dependency"]
    resolution: Resolution
    evidence_ids: tuple[str, ...]


class MockUse(ContractModel):
    owner_symbol_id: str
    api: str
    target_text: str | None
    target: Resolution
    evidence_ids: tuple[str, ...]


class TestIndexEntry(ContractModel):
    side: EvidenceSide
    definition: TestDefinition
    called_symbol_ids: tuple[str, ...]
    asserted_symbol_ids: tuple[str, ...]
    fixture_parameters: tuple[str, ...] = ()
    fixture_candidates: tuple[str, ...] = ()
    mock_targets: tuple[str, ...] = ()
    fixture_uses: tuple[FixtureUse, ...] = ()
    fixture_called_symbol_ids: tuple[str, ...] = ()
    mocked_symbol_ids: tuple[str, ...] = ()
    mock_uses: tuple[MockUse, ...] = ()
    mock_assertions: tuple[str, ...] = ()
    parameterized_names: tuple[str, ...] = ()
    injected_mock_parameters: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class DependencyDeclaration(ContractModel):
    side: EvidenceSide
    path: str
    package: Literal["openai", "anthropic"]
    declaration: str
    kind: Literal["constraint", "lock_version"]
    evidence_ids: tuple[str, ...]


class DependencyAnalysis(ContractModel):
    declarations: tuple[DependencyDeclaration, ...]
    limitations: tuple[str, ...]


class UnassignedChange(ContractModel):
    side: EvidenceSide
    symbol_id: str
    reason: str
    evidence_ids: tuple[str, ...]


class FlowEntryPath(ContractModel):
    changed_symbol_id: str
    symbol_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class FlowEntryCandidate(ContractModel):
    candidate_id: str
    side: Literal[EvidenceSide.head] = EvidenceSide.head
    symbol_id: str
    status: Literal["candidate"] = "candidate"
    reason: str
    paths: tuple[FlowEntryPath, ...]
    evidence_ids: tuple[str, ...]


class FlowEntryDiscovery(ContractModel):
    candidates: tuple[FlowEntryCandidate, ...]
    unresolved_change_ids: tuple[str, ...]
    coverage: CapabilityStatus
    limitations: tuple[str, ...]

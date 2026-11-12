"""Language-neutral static facts shared by every language adapter.

Draft contract. One adapter per language parses source and emits these facts;
everything above the adapters (fact diff, map accounting, rules, rendering) reads
only this shape. Facts describe what the source says, never what ran.

A fact's fingerprint is its identity across snapshots. The adapter computes it from
a canonical rendering of the expression, so this contract cannot recompute it from
the displayed `text`; it only checks that fingerprints are unique within a side.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .business_map import Anchor, Count, MapEntry, SymbolId, _unique
from .models import (
    ContractModel,
    EvidenceRef,
    EvidenceSide,
    ReferenceRange,
    Resolution,
    validate_evidence_refs,
    validate_repo_path,
)


class Language(StrEnum):
    python = "python"
    typescript = "typescript"


class FactKind(StrEnum):
    condition = "condition"
    call = "call"
    loop = "loop"
    returns = "return"
    raises = "raise"
    breaks = "break"
    continues = "continue"


class CallBoundary(StrEnum):
    """Where a call leads, as far as static resolution can tell."""

    internal = "internal"
    external = "external"
    builtin = "builtin"
    unknown = "unknown"


class GuardRef(ContractModel):
    """An enclosing condition or loop, and the branch of it that a fact sits on.

    A loop body is the branch `loop`. Guards are listed outermost first, so their
    order is the nesting order of conditions and loops together.
    """

    fingerprint: Anchor
    branch: str = Field(min_length=1, max_length=2000)


class CodeSymbol(ContractModel):
    symbol_id: SymbolId
    side: EvidenceSide
    language: Language
    path: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1, max_length=1024)
    kind: Literal["module", "class", "function"]
    is_async: bool = False
    decorators: tuple[str, ...] = ()
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    range: ReferenceRange
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identity_is_repository_relative(self) -> CodeSymbol:
        validate_repo_path(self.path)
        if not self.symbol_id.startswith(self.path + "#"):
            raise ValueError("a symbol identity starts with its repository-relative path")
        return self


class CodeFact(ContractModel):
    fingerprint: Anchor
    kind: FactKind
    side: EvidenceSide
    language: Language
    symbol_id: SymbolId
    text: str = Field(min_length=1, max_length=12000)
    ordinal: Count
    range: ReferenceRange
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    guards: tuple[GuardRef, ...] = ()
    loops: tuple[Anchor, ...] = ()
    branches: tuple[str, ...] = ()
    target: Resolution | None = None
    awaited: bool = False
    boundary: CallBoundary | None = None
    # Written here and run by someone else: a function handed to another call as an
    # argument, or a call inside a lambda. When and whether it runs is up to the receiver.
    deferred: bool = False

    @model_validator(mode="after")
    def call_details_only_on_calls(self) -> CodeFact:
        is_call = self.kind == FactKind.call
        if is_call != (self.target is not None) or is_call != (self.boundary is not None):
            raise ValueError("exactly the call facts carry a target and a boundary")
        if self.awaited and not is_call:
            raise ValueError("only a call can be awaited")
        if self.deferred and (not is_call or self.target.status == "resolved"):
            raise ValueError("only a call can be deferred, and never as a resolved target")
        if self.branches and self.kind not in {FactKind.condition, FactKind.loop}:
            raise ValueError("only a condition or a loop has branches")
        return self


class CodeEntry(MapEntry):
    """A place where execution enters the code from outside, on one snapshot side."""

    side: EvidenceSide


class CodeTest(ContractModel):
    """A test function as source: what it calls and what it asserts. Never whether it ran."""

    test_id: str = Field(min_length=1, max_length=1100)
    side: EvidenceSide
    symbol_id: SymbolId
    called_symbol_ids: tuple[SymbolId, ...] = ()
    assertions: tuple[str, ...] = Field(default=(), max_length=40)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class FileFacts(ContractModel):
    """Whether one source file was turned into facts."""

    path: str = Field(min_length=1)
    side: EvidenceSide
    language: Language
    status: Literal["analyzed", "unsupported"]
    reason: str | None = None

    @model_validator(mode="after")
    def unsupported_has_reason(self) -> FileFacts:
        validate_repo_path(self.path)
        if self.status == "unsupported" and not self.reason:
            raise ValueError("an unsupported file states why")
        return self


class FactSet(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    symbols: tuple[CodeSymbol, ...] = ()
    facts: tuple[CodeFact, ...] = ()
    entries: tuple[CodeEntry, ...] = ()
    tests: tuple[CodeTest, ...] = ()
    files: tuple[FileFacts, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def facts_are_consistent(self) -> FactSet:
        _unique(((item.side, item.symbol_id) for item in self.symbols), "symbols on one side")
        _unique(((item.side, item.fingerprint) for item in self.facts), "fingerprints on one side")
        _unique(((item.side, item.path) for item in self.files), "files on one side")
        _unique(((item.side, item.entry_id) for item in self.entries), "entries on one side")
        _unique(((item.side, item.symbol_id) for item in self.entries), "entry symbols on one side")
        symbols = {(item.side, item.symbol_id) for item in self.symbols}
        kinds = {(item.side, item.symbol_id, item.fingerprint): item.kind for item in self.facts}
        for fact in self.facts:
            if (fact.side, fact.symbol_id) not in symbols:
                raise ValueError("a fact belongs to a symbol on its own side")
            for guard in fact.guards:
                key = (fact.side, fact.symbol_id, guard.fingerprint)
                if kinds.get(key) not in {FactKind.condition, FactKind.loop}:
                    raise ValueError("a guard refers to a condition or loop in the same symbol")
            for loop in fact.loops:
                if kinds.get((fact.side, fact.symbol_id, loop)) != FactKind.loop:
                    raise ValueError("an enclosing loop refers to a loop in the same symbol")
        if any((item.side, item.symbol_id) not in symbols for item in self.entries):
            raise ValueError("an entry belongs to a symbol on its own side")
        _unique(((item.side, item.test_id) for item in self.tests), "tests on one side")
        if any((item.side, item.symbol_id) not in symbols for item in self.tests):
            raise ValueError("a test belongs to a symbol on its own side")
        sided = [
            *((item.side, ref) for item in self.symbols for ref in item.evidence_ids),
            *((item.side, ref) for item in self.facts for ref in item.evidence_ids),
            *((item.side, ref) for item in self.entries for ref in item.evidence_ids),
            *((item.side, ref) for item in self.tests for ref in item.evidence_ids),
        ]
        validate_evidence_refs(
            snapshot_id=self.snapshot_id,
            evidence=self.evidence,
            evidence_ids=tuple(ref for _, ref in sided),
        )
        by_id = {ref.evidence_id: ref for ref in self.evidence}
        if any(by_id[ref].side != side for side, ref in sided):
            raise ValueError("a fact cites evidence from its own side")
        return self

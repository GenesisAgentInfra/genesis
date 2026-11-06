"""Typed local static-analysis IR. Not a public schema or an HTTP protocol extension."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import (
    CapabilityStatus,
    ChangeSet,
    ContractModel,
    EvidenceRef,
    EvidenceSide,
    FactPack,
    ReferenceRange,
    Resolution,
    validate_repo_path,
)


class PythonOptions(ContractModel):
    source_roots: tuple[str, ...] = (".", "src")
    max_file_bytes: int = Field(default=262144, gt=0)
    max_nodes: int = Field(default=50000, gt=0)
    max_expression_depth: int = Field(default=16, ge=1, le=32)
    max_graph_visits: int = Field(default=10000, gt=0)

    @model_validator(mode="after")
    def safe_roots(self) -> PythonOptions:
        for root in self.source_roots:
            if root != ".":
                validate_repo_path(root)
        if len(set(self.source_roots)) != len(self.source_roots):
            raise ValueError("source roots must be unique")
        return self


class NameOrigin(ContractModel):
    name: str
    source: Literal["local", "import", "builtin"]


class ValueExpr(ContractModel):
    kind: Literal[
        "name",
        "attribute",
        "call",
        "literal",
        "list",
        "tuple",
        "dict",
        "subscript",
        "await",
        "unknown",
    ]
    text: str
    scope: str | None = None
    position: tuple[int, int] | None = None
    origins: tuple[NameOrigin, ...] = ()
    value: str | int | float | bool | None = None
    attribute: str | None = None
    children: tuple[ValueExpr, ...] = ()
    entries: tuple[DictionaryEntry, ...] = ()
    arguments: tuple[CallArgument, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None


class DictionaryEntry(ContractModel):
    key: ValueExpr | None
    value: ValueExpr


class CallArgument(ContractModel):
    name: str | None = None
    spread: Literal["", "*", "**"] = ""
    value: ValueExpr


class PythonSymbol(ContractModel):
    symbol_id: str
    side: EvidenceSide
    path: str
    qualified_name: str
    kind: Literal["module", "function", "class"]
    is_async: bool = False
    decorators: tuple[ValueExpr, ...] = ()
    declaration_conditions: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    default_parameters: tuple[str, ...] = ()
    variadic_parameters: tuple[str, ...] = ()
    source_digest: str
    range: ReferenceRange
    evidence_ids: tuple[str, ...]


class BindingFact(ContractModel):
    binding_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    target: ValueExpr
    value: ValueExpr
    conditional: bool
    evidence_ids: tuple[str, ...]


class BranchGuard(ContractModel):
    branch_id: str
    kind: Literal["if", "match"]
    selector: ValueExpr
    names: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class ParsedCall(ContractModel):
    call_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    callee: ValueExpr
    expression: str | None = None
    arguments: tuple[CallArgument, ...]
    target: Resolution
    awaited: bool
    context_manager: bool = False
    conditions: tuple[str, ...]
    loop_ids: tuple[str, ...]
    branch_guards: tuple[BranchGuard, ...] = ()
    lexical_conditions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]


class LoopControl(ContractModel):
    control_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    kind: Literal["break", "continue", "return", "raise"]
    loop_ids: tuple[str, ...]
    expression: str
    conditions: tuple[str, ...]
    caveats: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]


class CounterProgression(ContractModel):
    variable: str
    start: int = Field(ge=-(10**12), le=10**12)
    stop: int = Field(ge=-(10**12), le=10**12)
    step: int = Field(ge=-(10**12), le=10**12)
    comparison: Literal["<", "<=", ">", ">="]
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def monotonic_step(self):
        if (
            not self.variable.isidentifier()
            or self.step == 0
            or ((self.comparison in {"<", "<="}) != (self.step > 0))
        ):
            raise ValueError("Counter progression requires a named, nonzero monotonic step")
        return self


class ParsedLoop(ContractModel):
    loop_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    kind: Literal["for", "while"]
    expression: ValueExpr
    target: ValueExpr | None = None
    is_async: bool
    break_conditions: tuple[str, ...]
    single_pass_exit_id: str | None = None
    counter_progression: CounterProgression | None = None
    evidence_ids: tuple[str, ...]


class AssertionFact(ContractModel):
    assertion_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    expression: ValueExpr
    evidence_ids: tuple[str, ...]


class FileCoverage(ContractModel):
    side: EvidenceSide
    path: str
    syntax: CapabilityStatus
    bindings: CapabilityStatus
    calls: CapabilityStatus


class ExceptionHandlerFact(ContractModel):
    handler_id: str
    side: EvidenceSide
    path: str
    symbol_id: str
    exception: str
    is_group: bool
    simple_fallthrough: bool
    conditions: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class PythonAnalysis(ContractModel):
    format_version: Literal[5] = 5
    snapshot_id: str
    parser_version: Literal["libcst-1.9.0"] = "libcst-1.9.0"
    options: PythonOptions
    source_roots: tuple[str, ...]
    symbols: tuple[PythonSymbol, ...]
    bindings: tuple[BindingFact, ...]
    calls: tuple[ParsedCall, ...]
    loops: tuple[ParsedLoop, ...]
    assertions: tuple[AssertionFact, ...]
    loop_controls: tuple[LoopControl, ...] = ()
    exception_handlers: tuple[ExceptionHandlerFact, ...] = ()
    coverage: tuple[FileCoverage, ...]
    facts: FactPack
    change_set: ChangeSet
    evidence: tuple[EvidenceRef, ...]


ValueExpr.model_rebuild()

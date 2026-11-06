"""Derive bounded condition/operation/result views from the existing parsed CST.

No reparse, customer execution, model call or mutation of the extraction is needed.
Source references reuse complete owning-function evidence; role ranges identify the
exact statements inside it. Existing facts/graphs remain the authoritative inputs.
"""

from dataclasses import dataclass

import libcst as cst
from genesis_contracts.models import (
    BehaviorCondition,
    BehaviorOperation,
    BehaviorResult,
    BehaviorUnit,
    BehaviorView,
    ReferenceRange,
    behavior_id_for,
)
from libcst.metadata import MetadataWrapper, PositionProvider

from .snapshot import slice_source

MAX_PATHS = 32
MAX_OPERATIONS = 32
MAX_UNITS = 512


class _Unsupported(ValueError):
    pass


class _Functions(cst.CSTVisitor):
    def __init__(self):
        self.nodes = []

    def visit_FunctionDef(self, node):
        self.nodes.append(node)


class _Suspension(cst.CSTVisitor):
    def __init__(self):
        self.found = False

    def visit_Yield(self, node):
        self.found = True

    def visit_Lambda(self, node):
        return False


@dataclass(frozen=True)
class _Path:
    conditions: tuple = ()
    operations: tuple = ()


class _Builder:
    def __init__(self, file, positions, symbol, snapshot_id):
        self.file, self.positions, self.symbol = file, positions, symbol
        self.snapshot_id = snapshot_id
        self.units = []

    def source(self, node):
        pos = self.positions[node]
        span = ReferenceRange(
            start_line=pos.start.line,
            start_column=pos.start.column
            + int(pos.start.line == 1 and self.file.raw_text.startswith("\ufeff")),
            end_line=pos.end.line,
            end_column=pos.end.column
            + int(pos.end.line == 1 and self.file.raw_text.startswith("\ufeff")),
        )
        text = slice_source(self.file.raw_text, span)
        if len(text) > 12000:
            raise _Unsupported("A behavior source expression exceeds the view budget.")
        return dict(text=text, range=span, evidence_ids=self.symbol.evidence_ids)

    def emit(self, path, result=None, limitations=()):
        if len(self.units) >= MAX_PATHS:
            raise _Unsupported("The function exceeds the bounded behavior-path budget.")
        unit = BehaviorUnit(
            unit_id="bu_" + "0" * 24,
            side=self.file.side,
            path=self.file.path,
            symbol_id=self.symbol.symbol_id,
            scope_evidence_ids=self.symbol.evidence_ids,
            conditions=path.conditions,
            operations=path.operations,
            result=result,
            limitations=limitations,
        )
        self.units.append(
            unit.model_copy(update={"unit_id": behavior_id_for(self.snapshot_id, unit)})
        )

    def operation(self, path, node, kind):
        if len(path.operations) >= MAX_OPERATIONS:
            raise _Unsupported("The function exceeds the bounded operation budget.")
        return _Path(
            path.conditions, (*path.operations, BehaviorOperation(kind=kind, **self.source(node)))
        )

    def guarded(self, path, test, truth):
        if len(path.conditions) >= MAX_PATHS:
            raise _Unsupported("The function exceeds the bounded condition budget.")
        return _Path(
            (*path.conditions, BehaviorCondition(truth=truth, **self.source(test))), path.operations
        )

    def suite(self, suite, paths):
        # SimpleStatementSuite covers `if flag: return value`, including semicolons.
        for statement in suite.body:
            if not paths:
                break
            if isinstance(statement, cst.SimpleStatementLine):
                for small in statement.body:
                    paths = self.small(small, paths)
            elif isinstance(statement, cst.BaseSmallStatement):
                paths = self.small(statement, paths)
            elif isinstance(statement, cst.If):
                paths = self.branch(statement, paths)
            elif isinstance(statement, (cst.With, cst.Try, cst.TryStar)):
                kind = "context_region" if isinstance(statement, cst.With) else "exception_region"
                for path in paths:
                    self.emit(
                        self.operation(path, statement, kind),
                        limitations=(
                            "This complete source region is retained without path expansion. Context entry/cleanup and exception/finally handling can alter control flow; enclosed results and following paths are not inferred.",
                        ),
                    )
                paths = []
            else:
                # Do not flatten loops, finally/with, match, nested scopes or imports
                # into a falsely complete path. Existing A-side facts still survive.
                raise _Unsupported(
                    f"{type(statement).__name__} is outside behavior-view v1 path expansion; inspect source and existing facts."
                )
            if len(paths) > MAX_PATHS:
                raise _Unsupported("The function exceeds the bounded behavior-path budget.")
        return paths

    def branch(self, node, paths):
        output = []
        for path in paths:
            output.extend(self.suite(node.body, [self.guarded(path, node.test, True)]))
            other = [self.guarded(path, node.test, False)]
            if isinstance(node.orelse, cst.If):
                other = self.branch(node.orelse, other)
            elif node.orelse is not None:
                other = self.suite(node.orelse.body, other)
            output.extend(other)
        return output

    def small(self, node, paths):
        suspension = _Suspension()
        node.visit(suspension)
        if suspension.found:
            raise _Unsupported("Generator suspension is outside behavior-view v1 path expansion.")
        if isinstance(node, (cst.Return, cst.Raise)):
            kind = "return" if isinstance(node, cst.Return) else "raise"
            for path in paths:
                self.emit(path, BehaviorResult(kind=kind, **self.source(node)))
            return []
        if isinstance(node, cst.Pass):
            return paths
        if isinstance(node, (cst.Assign, cst.AnnAssign, cst.AugAssign)):
            # A bare annotation evaluates differently from a value assignment.
            if isinstance(node, cst.AnnAssign) and node.value is None:
                raise _Unsupported("Bare annotations are not modeled as value assignments.")
            targets = (
                [t.target for t in node.targets] if isinstance(node, cst.Assign) else [node.target]
            )
            if any(isinstance(target, (cst.Attribute, cst.Subscript)) for target in targets):
                for path in paths:
                    self.emit(path, BehaviorResult(kind="state_update", **self.source(node)))
            return [self.operation(path, node, "assignment") for path in paths]
        if isinstance(node, cst.Expr):
            if isinstance(node.value, (cst.SimpleString, cst.ConcatenatedString)):
                return paths
            return [self.operation(path, node, "expression") for path in paths]
        raise _Unsupported(f"{type(node).__name__} is outside behavior-view v1 path expansion.")

    def build(self, function):
        try:
            suspension = _Suspension()
            function.body.visit(suspension)
            if suspension.found:
                raise _Unsupported(
                    "Generator suspension is outside behavior-view v1 path expansion."
                )
            active = self.suite(function.body, [_Path()])
            for path in active:
                self.emit(
                    path,
                    limitations=(
                        "No explicit return/raise anchors this remaining lexical path; its final outcome is not inferred.",
                    ),
                )
        except (_Unsupported, RecursionError) as error:
            # Discard partial expansion: e.g. return in a try can be replaced by
            # finally. Never preserve a misleading successful prefix as complete.
            self.units = []
            reason = (
                str(error)
                if isinstance(error, _Unsupported)
                else "Behavior nesting exceeds the traversal limit."
            )
            self.emit(_Path(), limitations=(reason,))
        return self.units


def build_behavior_view(extraction):
    ir = extraction.analysis
    catalog = {ref.evidence_id: ref for ref in ir.evidence}
    changed = set(ir.change_set.changed_symbol_ids)

    def priority(unit):
        return (
            unit.symbol_id not in changed,
            unit.symbol_id,
            unit.result.range.start_line if unit.result else 0,
            unit.side != "head",
            unit.unit_id,
        )

    units, omitted = [], 0
    for _, file in sorted(extraction.files.items(), key=lambda item: (item[0][1], item[0][0])):
        functions = _Functions()
        file.module.visit(functions)
        positions = MetadataWrapper(file.module, unsafe_skip_copy=True).resolve(PositionProvider)
        owners = {
            (symbol.range.start_line, symbol.range.start_column): symbol
            for symbol in file.symbols
            if symbol.kind == "function"
            and all(catalog[ref].kind == "code" for ref in symbol.evidence_ids)
        }
        for function in functions.nodes:
            pos = positions[function]
            column = pos.start.column + int(
                pos.start.line == 1 and file.raw_text.startswith("\ufeff")
            )
            symbol = owners.get((pos.start.line, column))
            if symbol is None:
                continue
            produced = _Builder(file, positions, symbol, ir.snapshot_id).build(function)
            # Keep the bounded best set across files/revisions. A large early
            # base file must not exhaust the cap before changed head functions.
            units.extend(produced)
            units.sort(key=priority)
            omitted += max(0, len(units) - MAX_UNITS)
            del units[MAX_UNITS:]
    version = (
        "2"
        if any(
            op.kind in {"context_region", "exception_region"}
            for unit in units
            for op in unit.operations
        )
        else "1"
    )
    return BehaviorView(version=version, units=tuple(units), omitted_units=omitted)

from __future__ import annotations

import gc
import hashlib
import math
from contextlib import contextmanager
from dataclasses import dataclass, field

import libcst as cst
from genesis_contracts.models import (
    CallFact,
    CapabilityStatus,
    ChangeSet,
    EvidenceSide,
    ExpressionFact,
    FactPack,
    ImportFact,
    ReferenceRange,
    Resolution,
    SymbolFact,
    UnresolvedFact,
)
from genesis_contracts.python import (
    AssertionFact,
    BindingFact,
    BranchGuard,
    CallArgument,
    DictionaryEntry,
    ExceptionHandlerFact,
    FileCoverage,
    LoopControl,
    NameOrigin,
    ParsedCall,
    ParsedLoop,
    PythonAnalysis,
    PythonOptions,
    PythonSymbol,
    ValueExpr,
)
from libcst.metadata import (
    MetadataWrapper,
    ParentNodeProvider,
    PositionProvider,
    QualifiedNameProvider,
)

from genesis_ci.git_snapshot import CapturedSnapshot
from genesis_ci.source_snapshot import EvidenceRegistry, SingleFileSource

from .control import ControlExtractor

ANALYZED = CapabilityStatus(status="analyzed", analyzed_scope="Supported static syntax only")


def incomplete(reason: str) -> CapabilityStatus:
    return CapabilityStatus(status="insufficient_context", reason=reason)


def unknown(reason: str) -> Resolution:
    return Resolution(status="unknown", reason=reason)


@dataclass
class ParsedFile:
    side: EvidenceSide
    path: str
    # Dropped once a `collect` hook has run or the file came back from a worker process.
    module: cst.Module | None
    raw_text: str
    symbols: list[PythonSymbol] = field(default_factory=list)
    bindings: list[BindingFact] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    loops: list[ParsedLoop] = field(default_factory=list)
    loop_controls: list[LoopControl] = field(default_factory=list)
    exception_handlers: list[ExceptionHandlerFact] = field(default_factory=list)
    assertions: list[AssertionFact] = field(default_factory=list)
    imports: list[ImportFact] = field(default_factory=list)
    conditions: list[ExpressionFact] = field(default_factory=list)
    awaits: list[ExpressionFact] = field(default_factory=list)
    unresolved: list[UnresolvedFact] = field(default_factory=list)
    exports: dict[str, tuple[NameOrigin, ...]] = field(default_factory=dict)
    wildcard_import: bool = False
    uncertain_imports: set[str] = field(default_factory=set)
    dynamic_namespace: bool = False
    mutable_values: bool = False


# Ways of using `globals()` or `locals()` that only look at the names.
_NAMESPACE_READS = {"get", "keys", "values", "items", "copy", "__contains__"}
_NAMESPACE_WRITES = {
    "update",
    "setdefault",
    "pop",
    "popitem",
    "clear",
    "__setitem__",
    "__delitem__",
}


class _Budget(cst.CSTVisitor):
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.count = 0

    def on_visit(self, node):
        self.count += 1
        if self.count > self.maximum:
            raise ValueError("Python node budget exceeded")
        return True


class Extractor(ControlExtractor, cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, QualifiedNameProvider, ParentNodeProvider)

    def __init__(self, file: ParsedFile, registry: EvidenceRegistry, options: PythonOptions):
        self.file, self.registry, self.options = file, registry, options
        self.stack: list[tuple[cst.CSTNode, str]] = []
        self.controls: list[tuple[cst.CSTNode, str]] = []
        self.barriers: list[int] = []
        self.line_count = len(file.raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))

    def span(self, node) -> ReferenceRange:
        position = self.get_metadata(PositionProvider, node)
        return ReferenceRange(
            start_line=position.start.line,
            end_line=position.end.line,
            start_column=position.start.column
            + int(position.start.line == 1 and self.file.raw_text.startswith("\ufeff")),
            end_column=position.end.column
            + int(position.end.line == 1 and self.file.raw_text.startswith("\ufeff")),
        )

    def refs(self, node):
        span = self.span(node)
        if span.end_line > self.line_count and span.end_column == 0:
            # Module's synthetic final newline is outside the frozen source.
            return ()
        return (self.registry.register(self.file.side, self.file.path, span).evidence_id,)

    def identifier(self, prefix, node):
        span = self.span(node)
        encoded = f"{self.file.side}:{self.file.path}:{prefix}:{span.model_dump_json()}"
        return prefix + "_" + hashlib.sha256(encoded.encode()).hexdigest()[:24]

    @property
    def owner(self):
        return self.file.path + "#" + (".".join(item[1] for item in self.stack) or "<module>")

    def text(self, node):
        return self.file.module.code_for_node(node)

    def origins(self, node):
        names = self.get_metadata(QualifiedNameProvider, node, set())
        return tuple(
            NameOrigin(name=item.name, source=item.source.name.lower())
            for item in sorted(names, key=lambda item: (item.source.name, item.name))
        )

    def expr(self, node, depth=0, with_evidence=True):
        text = self.text(node)
        refs = self.refs(node) if with_evidence else ()
        span = self.span(node)
        common = {
            "text": text,
            "evidence_ids": refs,
            "scope": self.execution_owner(node),
            "position": (span.start_line, span.start_column),
        }
        if depth >= self.options.max_expression_depth:
            return ValueExpr(kind="unknown", reason="Expression depth budget exceeded", **common)

        def child(item):
            return self.expr(item, depth + 1, False)

        if isinstance(node, cst.Name):
            if node.value in {"True", "False", "None"}:
                return ValueExpr(
                    kind="literal",
                    value={"True": True, "False": False, "None": None}[node.value],
                    **common,
                )
            return ValueExpr(kind="name", origins=self.origins(node), **common)
        if isinstance(node, cst.Attribute):
            return ValueExpr(
                kind="attribute",
                origins=self.origins(node),
                attribute=node.attr.value,
                children=(child(node.value),),
                **common,
            )
        if isinstance(node, (cst.SimpleString, cst.Integer, cst.Float)):
            value = node.evaluated_value
            if (
                isinstance(value, (str, int, float))
                and not isinstance(value, bytes)
                and not (isinstance(value, float) and not math.isfinite(value))
            ):
                return ValueExpr(kind="literal", value=value, **common)
        if (
            isinstance(node, cst.UnaryOperation)
            and isinstance(node.operator, (cst.Minus, cst.Plus))
            and isinstance(node.expression, cst.Integer)
        ):
            value = node.expression.evaluated_value * (
                -1 if isinstance(node.operator, cst.Minus) else 1
            )
            return ValueExpr(kind="literal", value=value, **common)
        if isinstance(node, cst.Call):
            return ValueExpr(
                kind="call",
                children=(child(node.func),),
                arguments=tuple(
                    CallArgument(
                        name=arg.keyword.value if arg.keyword else None,
                        spread=arg.star,
                        value=child(arg.value),
                    )
                    for arg in node.args
                ),
                **common,
            )
        if isinstance(node, (cst.List, cst.Tuple)):
            if all(isinstance(item, cst.Element) for item in node.elements):
                return ValueExpr(
                    kind="list" if isinstance(node, cst.List) else "tuple",
                    children=tuple(child(item.value) for item in node.elements),
                    **common,
                )
        if isinstance(node, cst.Dict):
            return ValueExpr(
                kind="dict",
                entries=tuple(
                    DictionaryEntry(
                        key=child(item.key) if isinstance(item, cst.DictElement) else None,
                        value=child(item.value),
                    )
                    for item in node.elements
                ),
                **common,
            )
        if isinstance(node, cst.Subscript):
            indices = tuple(
                child(element.slice.value)
                for element in node.slice
                if isinstance(element.slice, cst.Index)
            )
            return ValueExpr(kind="subscript", children=(child(node.value), *indices), **common)
        if isinstance(node, cst.Await):
            return ValueExpr(kind="await", children=(child(node.expression),), **common)
        nested = []
        if isinstance(node, cst.Comparison):
            nested = [node.left, *(item.comparator for item in node.comparisons)]
        elif isinstance(node, (cst.BinaryOperation, cst.BooleanOperation)):
            nested = [node.left, node.right]
        elif isinstance(node, (cst.UnaryOperation, cst.Await)):
            nested = [node.expression]
        return ValueExpr(
            kind="unknown",
            children=tuple(child(item) for item in nested),
            reason="Expression requires runtime evaluation or unsupported syntax",
            **common,
        )

    def visit_Module(self, node):
        text = node.code
        if text:
            # Register the actual whole file, not LibCST's synthetic EOF.
            raw_text = self.file.raw_text
            from genesis_ci.snapshot import slice_source

            physical = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if physical[-1] == "":
                physical.pop()
            if physical:
                span = ReferenceRange(
                    start_line=1,
                    end_line=len(physical),
                    start_column=0,
                    end_column=len(physical[-1]),
                )
                ref = self.registry.register(self.file.side, self.file.path, span)
                self.file.symbols.append(
                    PythonSymbol(
                        symbol_id=self.owner,
                        side=self.file.side,
                        path=self.file.path,
                        qualified_name="<module>",
                        kind="module",
                        source_digest=hashlib.sha256(
                            slice_source(raw_text, span).encode()
                        ).hexdigest(),
                        range=span,
                        evidence_ids=(ref.evidence_id,),
                    )
                )

    def _enter_symbol(self, node, kind):
        name = node.name.value
        self.stack.append((node, name))
        self.barriers.append(len(self.controls))
        params = ()
        if isinstance(node, cst.FunctionDef):
            p = node.params
            params = tuple(
                item.name.value for item in (*p.posonly_params, *p.params, *p.kwonly_params)
            )
            if isinstance(p.star_arg, cst.Param):
                params += (p.star_arg.name.value,)
            if p.star_kwarg:
                params += (p.star_kwarg.name.value,)
        self.file.symbols.append(
            PythonSymbol(
                symbol_id=self.owner,
                side=self.file.side,
                path=self.file.path,
                qualified_name=".".join(item[1] for item in self.stack),
                kind=kind,
                is_async=isinstance(node, cst.FunctionDef) and node.asynchronous is not None,
                decorators=tuple(self.expr(d.decorator) for d in node.decorators),
                declaration_conditions=tuple(text for _, text in self.controls),
                parameters=params,
                default_parameters=tuple(
                    item.name.value
                    for item in (
                        *node.params.posonly_params,
                        *node.params.params,
                        *node.params.kwonly_params,
                    )
                    if item.default is not None
                )
                if isinstance(node, cst.FunctionDef)
                else (),
                variadic_parameters=tuple(
                    item.name.value
                    for item in (node.params.star_arg, node.params.star_kwarg)
                    if isinstance(item, cst.Param)
                )
                if isinstance(node, cst.FunctionDef)
                else (),
                source_digest=hashlib.sha256(self.text(node).encode()).hexdigest(),
                range=self.span(node),
                evidence_ids=self.refs(node),
            )
        )

    def visit_FunctionDef(self, node):
        self._enter_symbol(node, "function")

    def leave_FunctionDef(self, node):
        self.stack.pop()
        self.barriers.pop()

    def visit_ClassDef(self, node):
        self._enter_symbol(node, "class")

    def leave_ClassDef(self, node):
        self.stack.pop()
        self.barriers.pop()

    def _namespace_mapping(self, node) -> bool:
        """Whether an expression exposes a namespace as a mapping that can rebind names."""
        if isinstance(node, cst.Call) and isinstance(node.func, cst.Name):
            return node.func.value in {"globals", "locals", "vars"}
        if isinstance(node, cst.Attribute):
            return node.attr.value == "__dict__" or (
                node.attr.value == "modules"
                and isinstance(node.value, cst.Name)
                and node.value.value == "sys"
            )
        return isinstance(node, cst.Name) and node.value == "__builtins__"

    def _is_sys_modules(self, node) -> bool:
        return (
            isinstance(node, cst.Attribute)
            and node.attr.value == "modules"
            and isinstance(node.value, cst.Name)
            and node.value.value == "sys"
        )

    def _replaced_module(self, target) -> str | None:
        """The module a `sys.modules["name"]` item names, when it is a plain literal."""
        if not self._is_sys_modules(target.value) or len(target.slice) != 1:
            return None
        index = target.slice[0].slice
        key = index.value if isinstance(index, cst.Index) else None
        if isinstance(key, cst.SimpleString) and not key.prefix:
            value = key.evaluated_value
            return value if isinstance(value, str) and value else None
        return None

    def _item_write(self, target) -> None:
        # Writing or deleting an item changes the indexed object, not the names of
        # this module. Only a write through a namespace mapping can rebind names.
        if not self._namespace_mapping(target.value):
            self.file.mutable_values = True
            return
        replaced = self._replaced_module(target)
        if replaced is None:
            self.file.dynamic_namespace = True
            return
        # Stubbing one named module, as tests do for optional dependencies, makes
        # imports of that module uncertain. It rebinds nothing else in this file.
        self.file.uncertain_imports.add(replaced)
        self.file.mutable_values = True

    def _namespace_read(self, parent, node) -> bool:
        """Whether `globals()` or `locals()` is only read where it stands."""
        if isinstance(parent, cst.Attribute) and parent.value is node:
            return parent.attr.value in _NAMESPACE_READS
        if isinstance(parent, cst.Subscript) and parent.value is node:
            # A stored item is an assignment target and is handled as an item write.
            return True
        if isinstance(parent, cst.Arg):
            return parent.star == "**"
        return isinstance(parent, cst.ComparisonTarget)

    def _attribute_write(self, target) -> None:
        """`setattr(target, ...)`: it changes that object, and this module only if it is one."""
        this_module = (
            isinstance(target, cst.Subscript)
            and self._is_sys_modules(target.value)
            and self._replaced_module(target) is None
        )
        if this_module or self._namespace_mapping(target):
            self.file.dynamic_namespace = True
            return
        if isinstance(target, cst.Subscript) and self._is_sys_modules(target.value):
            # An attribute of one named module is replaced: only that module is uncertain.
            self.file.uncertain_imports.add(self._replaced_module(target))
        for origin in self.origins(target):
            if origin.source == "import":
                self.file.uncertain_imports.add(origin.name)
        self.file.mutable_values = True

    def _binding(self, node, target, value, *, unpacked=False):
        # A tuple assignment only makes its assigned values unknown. It does not
        # invalidate unrelated imports/calls throughout the entire module.
        if isinstance(target, (cst.Tuple, cst.List)):
            for element in target.elements:
                if element is not None:
                    self._binding(node, element.value, value, unpacked=True)
            return
        if isinstance(target, cst.Attribute):
            for origin in self.origins(target):
                if origin.source == "import":
                    self.file.uncertain_imports.add(origin.name)
        if isinstance(target, cst.Subscript):
            self._item_write(target)
        elif not isinstance(target, (cst.Name, cst.Attribute)):
            self.file.dynamic_namespace = True

        self.file.bindings.append(
            BindingFact(
                binding_id=self.identifier("bind", target),
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.owner,
                target=self.expr(target),
                value=ValueExpr(
                    kind="unknown",
                    text=self.text(value),
                    reason="Destructured value requires iteration; element types are unknown",
                )
                if unpacked
                else self.expr(value),
                conditional=bool(self.controls[self.barriers[-1] if self.barriers else 0 :]),
                evidence_ids=self.refs(node),
            )
        )

    def visit_Assign(self, node):
        for target in node.targets:
            self._binding(node, target.target, node.value)

    def visit_AnnAssign(self, node):
        if node.value:
            self._binding(node, node.target, node.value)

    def visit_AugAssign(self, node):
        self.file.bindings.append(
            BindingFact(
                binding_id=self.identifier("bind", node.target),
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.owner,
                target=self.expr(node.target),
                value=ValueExpr(
                    kind="unknown",
                    text=self.text(node),
                    reason="Augmented assignment is state dependent",
                ),
                conditional=True,
                evidence_ids=self.refs(node),
            )
        )

    def visit_With(self, node):
        for item in node.items:
            if item.asname is None:
                continue
            target = item.asname.name
            self.file.bindings.append(
                BindingFact(
                    binding_id=self.identifier("bind", target),
                    side=self.file.side,
                    path=self.file.path,
                    symbol_id=self.owner,
                    target=self.expr(target),
                    value=ValueExpr(
                        kind="unknown",
                        text=self.text(item.item),
                        children=(self.expr(item.item),),
                        reason="Context manager __enter__ result is unknown",
                    ),
                    conditional=True,
                    evidence_ids=self.refs(item),
                )
            )

    def visit_NamedExpr(self, node):
        self._binding(node, node.target, node.value)

    def execution_owner(self, node):
        child = node
        parent = self.get_metadata(ParentNodeProvider, node, None)
        while parent is not None:
            if isinstance(parent, (cst.FunctionDef, cst.ClassDef)) and child is parent.body:
                index = next((i for i, item in enumerate(self.stack) if item[0] is parent), None)
                if index is not None:
                    return (
                        self.file.path + "#" + ".".join(item[1] for item in self.stack[: index + 1])
                    )
            child, parent = parent, self.get_metadata(ParentNodeProvider, parent, None)
        return self.file.path + "#<module>"

    def branch_guards(self, node):
        """Positive body guards only; never borrow an enclosing function's branch."""
        result = []
        child = node
        parent = self.get_metadata(ParentNodeProvider, child, None)
        while parent is not None:
            if isinstance(parent, (cst.FunctionDef, cst.ClassDef, cst.Lambda)):
                break
            if isinstance(parent, cst.If) and child is parent.body:
                test = parent.test
                if (
                    isinstance(test, cst.Comparison)
                    and len(test.comparisons) == 1
                    and isinstance(test.comparisons[0].operator, cst.Equal)
                ):
                    left, right = test.left, test.comparisons[0].comparator
                    for selector, literal in ((left, right), (right, left)):
                        if isinstance(literal, cst.SimpleString) and isinstance(
                            literal.evaluated_value, str
                        ):
                            result.append(
                                BranchGuard(
                                    branch_id=self.identifier("branch", parent),
                                    kind="if",
                                    selector=self.expr(selector),
                                    names=(literal.evaluated_value,),
                                    evidence_ids=self.refs(test),
                                )
                            )
                            break
            if isinstance(parent, cst.MatchCase) and child is parent.body:
                match = self.get_metadata(ParentNodeProvider, parent, None)
                patterns = [parent.pattern]
                if isinstance(parent.pattern, cst.MatchOr):
                    patterns = [element.pattern for element in parent.pattern.patterns]
                if isinstance(match, cst.Match) and all(
                    isinstance(p, cst.MatchValue)
                    and isinstance(p.value, cst.SimpleString)
                    and isinstance(p.value.evaluated_value, str)
                    for p in patterns
                ):
                    result.append(
                        BranchGuard(
                            branch_id=self.identifier("branch", parent),
                            kind="match",
                            selector=self.expr(match.subject),
                            names=tuple(p.value.evaluated_value for p in patterns),
                            evidence_ids=tuple(
                                sorted(
                                    {
                                        *self.refs(match.subject),
                                        *self.refs(parent.pattern),
                                        *(self.refs(parent.guard) if parent.guard else ()),
                                    }
                                )
                            ),
                        )
                    )
            child, parent = parent, self.get_metadata(ParentNodeProvider, parent, None)
        return tuple(result)

    def visit_Call(self, node):
        parent = self.get_metadata(ParentNodeProvider, node, None)
        if isinstance(node.func, cst.Name):
            name = node.func.value
            if name in {"exec", "eval"}:
                self.file.dynamic_namespace = True
            elif name in {"globals", "locals"} and not self._namespace_read(parent, node):
                self.file.dynamic_namespace = True
            elif name == "setattr" and node.args:
                self._attribute_write(node.args[0].value)
        if isinstance(node.func, cst.Attribute) and node.func.attr.value in _NAMESPACE_WRITES:
            holder = node.func.value
            if isinstance(holder, cst.Call) and self._namespace_mapping(holder):
                # `globals().update(...)` rebinds names without any assignment.
                self.file.dynamic_namespace = True
            elif self._is_sys_modules(holder) and node.args:
                # `sys.modules.setdefault("name", stub)` or `.pop("name")`.
                first = node.args[0].value
                if isinstance(first, cst.SimpleString) and not first.prefix:
                    self.file.uncertain_imports.add(first.evaluated_value)
        if isinstance(node.func, cst.Attribute) and node.func.attr.value in {
            "append",
            "extend",
            "insert",
            "pop",
            "remove",
            "clear",
            "update",
            "setdefault",
            "sort",
            "reverse",
            "__setitem__",
        }:
            self.file.mutable_values = True
        # Defaults and decorators execute in the enclosing scope, not the function body.
        self.file.calls.append(
            ParsedCall(
                call_id=self.identifier("call", node),
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.execution_owner(node),
                callee=self.expr(node.func),
                expression=self.text(node),
                arguments=tuple(
                    CallArgument(
                        name=arg.keyword.value if arg.keyword else None,
                        spread=arg.star,
                        value=self.expr(arg.value),
                    )
                    for arg in node.args
                ),
                target=unknown("Name resolution pending"),
                branch_guards=self.branch_guards(node),
                lexical_conditions=self.control_context(node)[0],
                awaited=isinstance(parent, cst.Await),
                context_manager=isinstance(parent, cst.WithItem) and parent.item is node,
                conditions=tuple(
                    text for _, text in self.controls[self.barriers[-1] if self.barriers else 0 :]
                ),
                loop_ids=self.active_loop_ids(node),
                evidence_ids=self.refs(node),
            )
        )

    def visit_If(self, node):
        self.file.conditions.append(
            ExpressionFact(
                fact_id=self.identifier("condition", node.test),
                side=self.file.side,
                symbol_id=self.owner,
                expression=self.text(node.test),
                evidence_ids=self.refs(node.test),
            )
        )
        self.controls.append((node, "branch of: " + self.text(node.test)))

    def leave_If(self, node):
        self.controls.pop()

    def visit_Try(self, node):
        self.controls.append((node, "try/except/finally region"))

    def leave_Try(self, node):
        self.controls.pop()

    def visit_TryStar(self, node):
        self.controls.append((node, "try*/except*/finally region"))

    def leave_TryStar(self, node):
        self.controls.pop()

    def _exception_handler(self, node):
        # Only a literal pass/ellipsis-only body proves syntactic fallthrough.
        if isinstance(node.body, cst.SimpleStatementSuite):
            statements = tuple(node.body.body)
        elif all(isinstance(line, cst.SimpleStatementLine) for line in node.body.body):
            statements = tuple(s for line in node.body.body for s in line.body)
        else:
            statements = ()
        fallthrough = bool(statements) and all(
            isinstance(s, cst.Pass)
            or (isinstance(s, cst.Expr) and isinstance(s.value, cst.Ellipsis))
            for s in statements
        )
        conditions, _, refs = self.control_context(node)
        self.file.exception_handlers.append(
            ExceptionHandlerFact(
                handler_id=self.identifier("handler", node),
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.execution_owner(node),
                exception=self.text(node.type) if node.type else "bare except",
                is_group=isinstance(node, cst.ExceptStarHandler),
                simple_fallthrough=fallthrough,
                conditions=conditions,
                evidence_ids=tuple(sorted({*self.refs(node), *refs})),
            )
        )

    def visit_ExceptHandler(self, node):
        self._exception_handler(node)

    def visit_ExceptStarHandler(self, node):
        self._exception_handler(node)

    def visit_Match(self, node):
        self.controls.append((node, "match region: " + self.text(node.subject)))

    def leave_Match(self, node):
        self.controls.pop()

    def _loop(self, node, expression, kind):
        loop_id = self.identifier("loop", node)
        self.controls.append((node, kind + ": " + self.text(expression)))
        self.file.loops.append(
            ParsedLoop(
                loop_id=loop_id,
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.owner,
                kind=kind,
                expression=self.expr(expression),
                target=self.expr(node.target) if isinstance(node, cst.For) else None,
                is_async=isinstance(node, cst.For) and node.asynchronous is not None,
                break_conditions=(),
                single_pass_exit_id=self.single_pass_exit(node),
                counter_progression=self.counter_progression(node),
                evidence_ids=self.refs(node),
            )
        )

    def visit_For(self, node):
        self._loop(node, node.iter, "for")

    def leave_For(self, node):
        self.controls.pop()

    def visit_While(self, node):
        self._loop(node, node.test, "while")

    def leave_While(self, node):
        self.controls.pop()

    def visit_Await(self, node):
        self.file.awaits.append(
            ExpressionFact(
                fact_id=self.identifier("await", node),
                side=self.file.side,
                symbol_id=self.owner,
                expression=self.text(node),
                evidence_ids=self.refs(node),
            )
        )

    def visit_Assert(self, node):
        self.file.assertions.append(
            AssertionFact(
                assertion_id=self.identifier("assert", node),
                side=self.file.side,
                path=self.file.path,
                symbol_id=self.owner,
                expression=self.expr(node.test),
                evidence_ids=self.refs(node),
            )
        )

    def visit_Import(self, node):
        for alias in node.names:
            module = self.text(alias.name)
            bound = alias.asname.name.value if alias.asname else module.split(".")[0]
            if self.controls:
                self.file.uncertain_imports.add(module if alias.asname else bound)
            self.file.imports.append(
                ImportFact(
                    import_id=self.identifier("import", alias),
                    side=self.file.side,
                    module=module,
                    alias=bound,
                    evidence_ids=self.refs(node),
                )
            )
            if not self.stack and not self.controls:
                self.file.exports[bound] = (
                    NameOrigin(name=module if alias.asname else bound, source="import"),
                )

    def visit_ImportFrom(self, node):
        module = "." * len(node.relative) + (self.text(node.module) if node.module else "")
        if isinstance(node.names, cst.ImportStar):
            self.file.wildcard_import = True
            self.file.unresolved.append(
                UnresolvedFact(
                    unresolved_id=self.identifier("unknown", node),
                    feature="import",
                    reason="Wildcard exports require runtime module semantics",
                    evidence_ids=self.refs(node),
                )
            )
            return
        for alias in node.names:
            name = self.text(alias.name)
            bound = alias.asname.name.value if alias.asname else name
            if self.controls:
                self.file.uncertain_imports.add(
                    module + ("" if module.endswith(".") else ".") + name
                )
            self.file.imports.append(
                ImportFact(
                    import_id=self.identifier("import", alias),
                    side=self.file.side,
                    module=module,
                    imported_name=name,
                    alias=bound,
                    evidence_ids=self.refs(node),
                )
            )
            if not self.stack and not self.controls:
                full = module + ("" if module.endswith(".") else ".") + name
                self.file.exports[bound] = (NameOrigin(name=full, source="import"),)

    def visit_Del(self, node):
        targets = (
            [item.value for item in node.target.elements]
            if isinstance(node.target, (cst.Tuple, cst.List))
            else [node.target]
        )
        unbinds_name = False
        # Inside a function `del name` drops a local. Only at module or class level does
        # it remove a name other code may resolve.
        local = any(isinstance(item[0], cst.FunctionDef) for item in self.stack)
        for target in targets:
            if isinstance(target, cst.Subscript):
                unbinds_name |= (
                    self._namespace_mapping(target.value) and self._replaced_module(target) is None
                )
                self._item_write(target)
            elif isinstance(target, cst.Attribute):
                for origin in self.origins(target):
                    if origin.source == "import":
                        self.file.uncertain_imports.add(origin.name)
            elif not local:
                unbinds_name = True
        if not unbinds_name:
            return
        self.file.dynamic_namespace = True
        self.file.unresolved.append(
            UnresolvedFact(
                unresolved_id=self.identifier("delete", node),
                feature="other",
                reason="Deletion can invalidate static name bindings",
                evidence_ids=self.refs(node),
            )
        )


@dataclass
class Extraction:
    analysis: PythonAnalysis
    registry: EvidenceRegistry
    files: dict[tuple[EvidenceSide, str], ParsedFile]
    resolver: object
    # What the `collect` hook of `extract_python` returned, by file.
    collected: dict = field(default_factory=dict)


def _extract_file(side, path, raw: bytes, options: PythonOptions, registry, collect):
    """Parse one file and run the extractor over it.

    Returns the parsed file (nothing when it could not be analyzed), its syntax status,
    and what `collect` made of the file while its syntax tree was at hand.
    """
    try:
        if len(raw) > options.max_file_bytes:
            raise ValueError("Python file byte budget exceeded")
        module = cst.parse_module(raw)
        module.visit(_Budget(options.max_nodes))
        wrapper = MetadataWrapper(module)
        result = ParsedFile(side, path, wrapper.module, raw.decode("utf-8"))
        wrapper.visit(Extractor(result, registry, options))
        collected = None
        if collect is not None:
            collected = collect(result, wrapper, registry)
            # The tree is large and whoever asked to collect has what it needs from it.
            result.module = None
        return result, ANALYZED, collected
    except (cst.ParserSyntaxError, RecursionError, ValueError) as error:
        # A budget error says which limit was hit; other errors only their kind.
        detail = str(error) if type(error) is ValueError else type(error).__name__
        syntax = CapabilityStatus(status="unsupported", reason=f"File not analyzed: {detail}")
        return None, syntax, None


def _extract_job(job):
    """One file in a worker process: the same extraction, with its own evidence registry."""
    side, path, raw, kind, snapshot_id, options, collect = job
    registry = EvidenceRegistry(SingleFileSource(snapshot_id, side, path, raw, kind))
    result, syntax, collected = _extract_file(side, path, raw, options, registry, collect)
    if result is not None:
        result.module = None
    return result, syntax, collected, registry.refs()


@contextmanager
def gc_paused():
    """Hold the cyclic garbage collector while building many plain objects.

    Analysis results are millions of small objects without reference cycles. Each
    collection walks all of them and frees nothing, which costs a large share of the
    run on a big repository. Reference counting still frees everything as usual.
    """
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


WORKER_TIMEOUT_SECONDS = 1800
SHARES_PER_WORKER = 4


def _extract_in_processes(jobs, workers: int):
    """Run the per-file work in several worker processes; nothing when that fails.

    Each worker is a fresh, isolated interpreter that gets a share of the files, the
    largest dealt out first so the shares are even. Results come back in job order.
    """
    import pickle
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor

    by_size = sorted(range(len(jobs)), key=lambda index: -len(jobs[index][2]))
    # More shares than workers: file size only roughly predicts the work, and a worker
    # that finishes early then takes another share instead of idling.
    count = min(len(jobs), workers * SHARES_PER_WORKER)
    shares = [by_size[start::count] for start in range(count)]
    command = [sys.executable, "-I", "-m", "genesis_ci.python.extract_worker"]

    def run(share):
        data = pickle.dumps([jobs[index] for index in share], protocol=pickle.HIGHEST_PROTOCOL)
        done = subprocess.run(
            command, input=data, capture_output=True, check=True, timeout=WORKER_TIMEOUT_SECONDS
        )
        return pickle.loads(done.stdout)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(run, shares))
    except (OSError, subprocess.SubprocessError, pickle.PickleError, EOFError, ImportError):
        # No worker could be started or one failed; the caller does the work itself.
        return None
    outcomes = [None] * len(jobs)
    for share, part in zip(shares, parts, strict=True):
        if len(part) != len(share):
            return None
        for index, outcome in zip(share, part, strict=True):
            outcomes[index] = outcome
    return outcomes


def extract_python(
    snapshot: CapturedSnapshot,
    options: PythonOptions | None = None,
    *,
    workers: int = 1,
    collect=None,
    validate: bool = True,
) -> Extraction:
    """Extract every captured Python file.

    Files are independent until call resolution, so with `workers` above one they are
    parsed and visited in separate processes; the result is the same either way.
    `collect(parsed_file, wrapper, registry)` runs for each analyzed file while its
    syntax tree exists and must be a module-level function; what it returns is kept in
    `Extraction.collected`, and the tree is dropped afterwards. `validate=False` skips
    the consistency check of the report pipeline's own data, for callers that only use
    what they collected and validate that themselves.
    """
    from .resolve import Resolver

    options = options or PythonOptions()
    registry = EvidenceRegistry(snapshot.source)
    sources = [
        file for file in snapshot.capture.manifest.files if file.path.endswith((".py", ".pyi"))
    ]
    outcomes = None
    if workers > 1 and len(sources) > 1:
        snapshot_id = snapshot.capture.manifest.snapshot_id
        jobs = [
            (
                file.side,
                file.path,
                snapshot.source.read_bytes(file.side, file.path),
                file.kind,
                snapshot_id,
                options,
                collect,
            )
            for file in sources
        ]
        with gc_paused():
            outcomes = _extract_in_processes(jobs, workers)
            for outcome in outcomes or ():
                registry.adopt(outcome[3])
    if outcomes is None:
        outcomes = [
            _extract_file(
                file.side,
                file.path,
                snapshot.source.read_bytes(file.side, file.path),
                options,
                registry,
                collect,
            )
            for file in sources
        ]
    parsed = {}
    collected = {}
    coverage = []
    for file, (result, syntax, gathered, *_) in zip(sources, outcomes, strict=True):
        if result is not None:
            parsed[(file.side, file.path)] = result
            if gathered is not None:
                collected[(file.side, file.path)] = gathered
        coverage.append(
            FileCoverage(
                side=file.side, path=file.path, syntax=syntax, bindings=syntax, calls=syntax
            )
        )
    # From here on only plain result objects are built.
    with gc_paused():
        unavailable = {(c.side, c.path) for c in coverage if c.syntax.status != "analyzed"}
        unavailable.update(
            (o.side, o.path) for o in snapshot.capture.omissions if o.path.endswith((".py", ".pyi"))
        )
        unavailable.update(
            (o.side, o.path + "/__init__.py")
            for o in snapshot.capture.omissions
            if o.reason == "submodule"
        )
        resolver = Resolver(parsed, options.source_roots, unavailable)
        for file in parsed.values():
            file.calls[:] = [
                call.model_copy(
                    update={
                        "target": resolver.callable_target(
                            resolver.resolve(call.callee, file.side, file.path), file.side
                        )
                    }
                )
                for call in file.calls
            ]
            for call in file.calls:
                if call.target.status != "resolved":
                    file.unresolved.append(
                        UnresolvedFact(
                            unresolved_id="unresolved_" + call.call_id,
                            feature="call",
                            reason=call.target.reason or "Candidate target",
                            evidence_ids=call.evidence_ids,
                        )
                    )
        coverage = [
            item.model_copy(
                update={
                    "calls": incomplete("Unresolved or candidate calls remain")
                    if (item.side, item.path) in parsed
                    and parsed[(item.side, item.path)].unresolved
                    else item.calls,
                    "bindings": incomplete(
                        "Binding values are conservative; conditional/reassigned/dynamic values may be unknown"
                    )
                    if (item.side, item.path) in parsed
                    and any(
                        b.conditional or b.value.kind in {"unknown", "subscript"}
                        for b in parsed[(item.side, item.path)].bindings
                    )
                    else item.bindings,
                }
            )
            for item in coverage
        ]
        symbols = tuple(symbol for file in parsed.values() for symbol in file.symbols)
        symbol_map = {}
        for symbol in symbols:
            symbol_map.setdefault((symbol.side, symbol.symbol_id), []).append(symbol)
        failed = {(item.side, item.path) for item in coverage if item.syntax.status != "analyzed"}
        uncertain = {item.path for item in snapshot.capture.omissions if item.affects_completeness}
        changed = set()
        # Without a baseline there is nothing to compare against, so nothing is changed.
        compared = snapshot.capture.manifest.base_revision is not None
        for sid in sorted({s.symbol_id for s in symbols}) if compared else ():
            path = sid.split("#")[0]
            if any(path == p or path.startswith(p + "/") for p in uncertain) or any(
                (side, path) in failed for side in EvidenceSide
            ):
                continue
            before, after = (
                symbol_map.get((EvidenceSide.base, sid)),
                symbol_map.get((EvidenceSide.head, sid)),
            )
            if (
                before is None
                or after is None
                or tuple(s.source_digest for s in before) != tuple(s.source_digest for s in after)
            ):
                changed.add(sid)
        unresolved = [f"{side.value}:{path}:syntax_unavailable" for side, path in sorted(failed)]
        unresolved += [
            f"{item.side.value}:{item.path}:{item.reason}"
            for item in snapshot.capture.omissions
            if item.affects_completeness
        ]
        files = list(parsed.values())
        all_calls = tuple(call for file in files for call in file.calls)
        fact_unresolved = tuple(item for file in files for item in file.unresolved)
        overall = (
            incomplete("Some input files or call targets could not be fully analyzed")
            if not coverage or failed or unresolved or fact_unresolved
            else ANALYZED
        )
        facts = FactPack(
            coverage=overall,
            functions=tuple(
                SymbolFact(
                    symbol_id=s.symbol_id,
                    side=s.side,
                    kind=s.kind,
                    is_async=s.is_async,
                    evidence_ids=s.evidence_ids,
                )
                for s in symbols
            ),
            imports=tuple(item for file in files for item in file.imports),
            calls=tuple(
                CallFact(
                    call_id=call.call_id,
                    side=call.side,
                    caller_symbol_id=call.symbol_id,
                    expression=call.callee.text,
                    target=call.target,
                    awaited=call.awaited,
                    evidence_ids=call.evidence_ids,
                )
                for call in all_calls
            ),
            conditions=tuple(item for file in files for item in file.conditions),
            awaits=tuple(item for file in files for item in file.awaits),
            unresolved=fact_unresolved,
        )
        analysis = PythonAnalysis(
            snapshot_id=snapshot.capture.manifest.snapshot_id,
            options=options,
            source_roots=options.source_roots,
            symbols=symbols,
            bindings=tuple(item for file in files for item in file.bindings),
            calls=all_calls,
            loops=tuple(item for file in files for item in file.loops),
            assertions=tuple(item for file in files for item in file.assertions),
            loop_controls=tuple(item for file in files for item in file.loop_controls),
            exception_handlers=tuple(item for file in files for item in file.exception_handlers),
            coverage=tuple(coverage),
            facts=facts,
            change_set=ChangeSet(
                files=tuple(item.change for item in snapshot.capture.file_diff.changes),
                changed_symbol_ids=tuple(sorted(changed)),
                unresolved=tuple(unresolved),
            ),
            evidence=registry.freeze().evidence_catalog(),
        )
        if validate:
            from .validate import validate_python

            validate_python(analysis)
        return Extraction(analysis, registry, parsed, resolver, collected)

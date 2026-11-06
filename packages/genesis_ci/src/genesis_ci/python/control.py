"""Lexical loop ownership and control-flow evidence, without evaluating paths."""

import libcst as cst
from genesis_contracts.python import CounterProgression, LoopControl
from libcst.metadata import ParentNodeProvider


class ControlExtractor:
    def ancestry(self, node):
        child = node
        parent = self.get_metadata(ParentNodeProvider, node, None)
        while parent is not None:
            # Defaults/decorators execute in the enclosing scope; deferred bodies do not.
            if isinstance(parent, cst.Lambda):
                break
            if isinstance(parent, (cst.FunctionDef, cst.ClassDef)) and child is parent.body:
                break
            yield child, parent
            child, parent = parent, self.get_metadata(ParentNodeProvider, parent, None)

    def active_loop_ids(self, node):
        """Outermost to innermost, only loop bodies (not iterable/test/else)."""
        active = []
        for child, parent in self.ancestry(node):
            if isinstance(parent, (cst.For, cst.While)) and child is parent.body:
                active.append(self.identifier("loop", parent))
        return tuple(reversed(active))

    def control_context(self, node):
        conditions, caveats, refs = [], [], set()
        for child, parent in self.ancestry(node):
            if isinstance(parent, cst.If):
                if child is parent.body:
                    conditions.append("if true: " + self.text(parent.test))
                    refs.update(self.refs(parent.test))
                elif child is parent.orelse:
                    conditions.append("if false: " + self.text(parent.test))
                    refs.update(self.refs(parent.test))
            elif isinstance(parent, cst.MatchCase) and child is parent.body:
                match = self.get_metadata(ParentNodeProvider, parent, None)
                if isinstance(match, cst.Match):
                    if parent.guard:
                        conditions.append("guard true: " + self.text(parent.guard))
                        refs.update(self.refs(parent.guard))
                    conditions.append(
                        "match " + self.text(match.subject) + " case " + self.text(parent.pattern)
                    )
                    refs.update(self.refs(match.subject))
                    refs.update(self.refs(parent.pattern))
            elif isinstance(parent, (cst.Try, cst.TryStar)):
                if child is parent.body:
                    conditions.append("try body")
                    if parent.handlers:
                        caveats.append("Exceptions can be caught by surrounding handlers")
                elif child is parent.orelse:
                    conditions.append("try else")
                if parent.finalbody:
                    caveats.append("A surrounding finally block can override control transfer")
            elif isinstance(parent, (cst.ExceptHandler, cst.ExceptStarHandler)):
                conditions.append("except " + (self.text(parent.type) if parent.type else "any"))
                if parent.type:
                    refs.update(self.refs(parent.type))
            elif isinstance(parent, cst.Finally):
                conditions.append("finally body")
            elif isinstance(parent, cst.With):
                caveats.append("Context manager exit can suppress or replace exceptions")
            elif isinstance(parent, (cst.For, cst.While)) and child is parent.orelse:
                conditions.append("loop else after normal completion")
        return tuple(reversed(conditions)), tuple(sorted(set(caveats))), refs

    def record_loop_control(self, node, kind):
        loop_ids = self.active_loop_ids(node)
        if kind in {"break", "continue"}:
            loop_ids = loop_ids[-1:]
        if not loop_ids:
            return
        conditions, caveats, refs = self.control_context(node)
        if kind == "raise":
            caveats = tuple(
                sorted({*caveats, "Explicit raise may be caught; it is not a proven loop exit"})
            )
        elif kind == "return":
            caveats = tuple(
                sorted(
                    {
                        *caveats,
                        "Return expression must complete; finally or context exit may override transfer",
                    }
                )
            )
        control = LoopControl(
            control_id=self.identifier("control", node),
            side=self.file.side,
            path=self.file.path,
            symbol_id=self.execution_owner(node),
            kind=kind,
            loop_ids=loop_ids,
            expression=self.text(node),
            conditions=conditions,
            caveats=caveats,
            evidence_ids=tuple(sorted({*self.refs(node), *refs})),
        )
        self.file.loop_controls.append(control)
        if kind == "break":
            index = next(i for i, loop in enumerate(self.file.loops) if loop.loop_id == loop_ids[0])
            loop = self.file.loops[index]
            self.file.loops[index] = loop.model_copy(
                update={
                    "break_conditions": (
                        *loop.break_conditions,
                        " / ".join(conditions) or "unconditional break",
                    )
                }
            )

    def visit_Break(self, node):
        self.record_loop_control(node, "break")

    def visit_Continue(self, node):
        self.record_loop_control(node, "continue")

    def visit_Return(self, node):
        self.record_loop_control(node, "return")

    def visit_Raise(self, node):
        self.record_loop_control(node, "raise")

    def single_pass_exit(self, loop):
        """A straight-line suite ending in break/return cannot start a second iteration."""
        if isinstance(loop.body, cst.SimpleStatementSuite):
            statements = list(loop.body.body)
        elif all(isinstance(line, cst.SimpleStatementLine) for line in loop.body.body):
            statements = [statement for line in loop.body.body for statement in line.body]
        else:
            return None
        if not statements or not isinstance(statements[-1], (cst.Break, cst.Return)):
            return None
        if any(
            isinstance(statement, (cst.Continue, cst.Break, cst.Return, cst.Raise))
            for statement in statements[:-1]
        ):
            return None
        return self.identifier("control", statements[-1])

    def counter_progression(self, loop):
        """Recognize only adjacent local integer initialization and a straight-line update."""
        if not isinstance(loop, cst.While) or not isinstance(loop.test, cst.Comparison):
            return None
        test = loop.test
        if not isinstance(test.left, cst.Name) or len(test.comparisons) != 1:
            return None
        comparison = {
            cst.LessThan: "<",
            cst.LessThanEqual: "<=",
            cst.GreaterThan: ">",
            cst.GreaterThanEqual: ">=",
        }.get(type(test.comparisons[0].operator))
        if comparison is None:
            return None
        block = self.get_metadata(ParentNodeProvider, loop, None)
        function = self.get_metadata(ParentNodeProvider, block, None) if block else None
        if (
            not isinstance(block, cst.IndentedBlock)
            or not isinstance(function, cst.FunctionDef)
            or function.body is not block
        ):
            return None
        index = next(i for i, node in enumerate(block.body) if node is loop)
        if index == 0 or not isinstance(block.body[index - 1], cst.SimpleStatementLine):
            return None
        previous = block.body[index - 1].body
        if (
            len(previous) != 1
            or not isinstance(previous[0], cst.Assign)
            or len(previous[0].targets) != 1
        ):
            return None
        initial = previous[0]
        variable = test.left.value
        if (
            not isinstance(initial.targets[0].target, cst.Name)
            or initial.targets[0].target.value != variable
        ):
            return None
        if isinstance(loop.body, cst.SimpleStatementSuite):
            statements = list(loop.body.body)
        elif all(isinstance(line, cst.SimpleStatementLine) for line in loop.body.body):
            statements = [statement for line in loop.body.body for statement in line.body]
        else:
            return None
        if not statements or not isinstance(statements[-1], cst.AugAssign):
            return None
        update = statements[-1]
        if (
            not isinstance(update.target, cst.Name)
            or update.target.value != variable
            or not isinstance(update.operator, (cst.AddAssign, cst.SubtractAssign))
        ):
            return None
        guard = CounterGuard(variable)
        function.body.visit(guard)
        if guard.unsafe:
            return None
        for statement in statements[:-1]:
            if not isinstance(statement, (cst.Expr, cst.Assign, cst.AnnAssign, cst.Pass)):
                return None
            names = CounterUse(variable)
            statement.visit(names)
            if names.found:
                return None
        values = [
            self.expr(node)
            for node in (initial.value, test.comparisons[0].comparator, update.value)
        ]
        if not all(
            value.kind == "literal"
            and isinstance(value.value, int)
            and not isinstance(value.value, bool)
            and abs(value.value) <= 10**12
            for value in values
        ):
            return None
        start, stop, step = (value.value for value in values)
        if isinstance(update.operator, cst.SubtractAssign):
            step = -step
        if step == 0 or (comparison in {"<", "<="}) != (step > 0):
            return None
        return CounterProgression(
            variable=variable,
            start=start,
            stop=stop,
            step=step,
            comparison=comparison,
            evidence_ids=tuple(sorted({*self.refs(initial), *self.refs(test), *self.refs(update)})),
        )


class CounterGuard(cst.CSTVisitor):
    def __init__(self, variable):
        self.variable, self.unsafe = variable, False

    def visit_Global(self, node):
        self.unsafe |= any(item.name.value == self.variable for item in node.names)

    def visit_Nonlocal(self, node):
        self.unsafe |= any(item.name.value == self.variable for item in node.names)

    def visit_Call(self, node):
        if isinstance(node.func, cst.Name) and node.func.value in {
            "exec",
            "eval",
            "locals",
            "globals",
        }:
            self.unsafe = True


class CounterUse(cst.CSTVisitor):
    def __init__(self, variable):
        self.variable, self.found = variable, False

    def visit_Name(self, node):
        self.found |= node.value == self.variable

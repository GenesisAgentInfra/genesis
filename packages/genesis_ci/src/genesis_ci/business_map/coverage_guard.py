"""Refute a small class of coverage claims from frozen Python source.

This is a veto on a cited assertion, never a coverage verdict. Only a direct call
with bounded integer arguments, a single-return function, and a plain comparison
are modeled. Unknown syntax or setup makes the guard abstain. No analyzed source
is imported, compiled into code, or executed.
"""

from __future__ import annotations

import ast
import operator
from functools import cached_property
from pathlib import PurePosixPath

from genesis_contracts.change_report import ChangeKind
from genesis_contracts.facts import FactKind

from .fact_diff import HEAD
from .python_facts import canonical_python

_ARITHMETIC = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_BUILTINS = {"round", "min", "max", "abs"}


class _Unknown(Exception):
    """Source or context is outside this guard's model."""


def _integer(value):
    if type(value) is not int or value.bit_length() > 64:
        raise _Unknown
    return value


def _body(node):
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _parameters(function):
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    if (
        function.decorator_list
        or function.returns
        or function.type_params
        or args.defaults
        or args.kw_defaults
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
        or any(arg.annotation for arg in positional)
    ):
        raise _Unknown
    return [arg.arg for arg in positional]


def _plain_module(tree, *, imports=False):
    """Decline import-time setup, rebinding, fixtures and test runner hooks."""
    if tree is None:
        raise _Unknown
    names = []
    for node in _body(tree):
        if isinstance(node, ast.FunctionDef):
            _parameters(node)
            if node.name.startswith(("setup_", "teardown_", "pytest_")):
                raise _Unknown
            names.append(node.name)
        elif imports and isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                raise _Unknown
            names.extend(alias.asname or alias.name for alias in node.names)
        elif not isinstance(node, ast.Pass):
            raise _Unknown
    if len(names) != len(set(names)):
        raise _Unknown


def _function(tree, name):
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(functions) != 1:
        raise _Unknown
    return functions[0]


class _Integers:
    """Fold an allowlist of integer syntax; never invoke a project callable."""

    def __init__(self, names, call):
        self.names, self.call = names, call
        self.budget = 128

    def value(self, node, depth=0):
        self.budget -= 1
        if self.budget < 0 or depth > 24:
            raise _Unknown
        if isinstance(node, ast.Constant):
            return _integer(node.value)
        if isinstance(node, ast.Name) and node.id in self.names:
            return _integer(self.names[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self.value(node.operand, depth + 1)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC:
            left, right = self.value(node.left, depth + 1), self.value(node.right, depth + 1)
            return _integer(_ARITHMETIC[type(node.op)](left, right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.keywords or len(node.args) > 8:
                raise _Unknown
            values = [self.value(arg, depth + 1) for arg in node.args]
            return _integer(self.call(node, values))
        raise _Unknown

    def comparison(self, node):
        if not isinstance(node, ast.Compare) or len(node.ops) > 8:
            raise _Unknown
        left = self.value(node.left)
        result = True
        for op, operand in zip(node.ops, node.comparators, strict=True):
            if type(op) not in _COMPARE:
                raise _Unknown
            right = self.value(operand)
            result = result and _COMPARE[type(op)](left, right)
            left = right
        return result


def _builtin(node, args):
    name = node.func.id
    if name == "round" and len(args) in {1, 2}:
        # Integer rounding at nonnegative precision is identity. Negative precision
        # and floating point rounding deliberately remain outside this model.
        if len(args) == 1 or 0 <= args[1] <= 64:
            return args[0]
    if name in {"min", "max"} and len(args) >= 2:
        return min(args) if name == "min" else max(args)
    if name == "abs" and len(args) == 1:
        return abs(args[0])
    raise _Unknown


class CoverageGuard:
    def __init__(self, analysis):
        self.analysis = analysis

    @cached_property
    def _files(self):
        return set(self.analysis.workspace.snapshot.source.list_files(HEAD))

    def _packages(self, path):
        for folder in PurePosixPath(path).parents:
            init = str(folder / "__init__.py")
            if init in self._files:
                tree = self.analysis.tree(HEAD, init)
                if tree is None or any(not isinstance(n, ast.Pass) for n in _body(tree)):
                    raise _Unknown

    def _target(self, part, name):
        tree = self.analysis.tree(part.side, part.path)
        _plain_module(tree)
        function = _function(tree, name)
        body = _body(function)
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            raise _Unknown
        statement = body[0]
        # Check the complete frozen statement, not a truncated fact excerpt. This
        # also rules out comparing a different return or reverting unrelated edits.
        if (statement.lineno, statement.col_offset) != part.start or (
            statement.end_lineno,
            statement.end_col_offset,
        ) != part.end:
            raise _Unknown
        parameters = _parameters(function)
        for node in ast.walk(statement):
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in _BUILTINS:
                    raise _Unknown
                if node.func.id in parameters or any(
                    isinstance(n, ast.FunctionDef) and n.name == node.func.id for n in tree.body
                ):
                    raise _Unknown
        return parameters, statement.value

    def refutes(self, change, test, assertion):
        """True only when the cited comparison accepts both modeled outcomes."""
        try:
            return self._refutes(change, test, assertion)
        except (_Unknown, ArithmeticError, RecursionError, ValueError, TypeError, KeyError):
            return False

    def _refutes(self, change, test, assertion):
        if (
            change.kind != ChangeKind.result_modified
            or not change.before
            or not change.after
            or change.before.path != change.after.path
            or any(PurePosixPath(path).name == "conftest.py" for path in self._files)
        ):
            return False
        path, _, name = change.symbol_id.partition("#")
        test_path, _, test_name = test.symbol_id.partition("#")
        for source_path in {path, test_path}:
            self._packages(source_path)
        before_args, before = self._target(change.before, name)
        after_args, after = self._target(change.after, name)
        if before_args != after_args:
            return False
        tree = self.analysis.tree(HEAD, test_path)
        _plain_module(tree, imports=True)
        function = _function(tree, test_name)
        statements = _body(function)
        if (
            _parameters(function)
            or len(statements) != 1
            or not isinstance(statements[0], ast.Assert)
        ):
            return False
        expression = statements[0].test
        if canonical_python(ast.unparse(expression)) != canonical_python(assertion):
            return False
        calls = [node for node in ast.walk(expression) if isinstance(node, ast.Call)]
        if len(calls) != 1 or not isinstance(calls[0].func, ast.Name):
            return False
        call = calls[0]
        resolved = [
            fact
            for fact in self.analysis.ordered(HEAD, test.symbol_id)
            if fact.kind == FactKind.call
            and (fact.range.start_line, fact.range.start_column) == (call.lineno, call.col_offset)
        ]
        if (
            len(resolved) != 1
            or resolved[0].target.status != "resolved"
            or resolved[0].target.targets != (change.symbol_id,)
        ):
            return False
        # Only a direct import of this definition is supported. Re-exports and
        # other imports can install setup or replace a binding at import time.
        module = path.removesuffix(".py").replace("/", ".")
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if (
                    node.level
                    or not node.module
                    or not (module == node.module or module.endswith("." + node.module))
                ):
                    return False
                for alias in node.names:
                    if (alias.asname or alias.name) == call.func.id and alias.name != name:
                        return False

        def outcome(return_value):
            def substitute(node, args):
                if node is not call or len(args) != len(after_args):
                    raise _Unknown
                return _Integers(dict(zip(after_args, args, strict=True)), _builtin).value(
                    return_value
                )

            return _Integers({}, substitute).comparison(expression)

        return outcome(after) and outcome(before)

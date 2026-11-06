"""Bounded lexical source dependencies; never resolves or evaluates runtime values."""

from __future__ import annotations

import ast
import re
import symtable
from collections import defaultdict, deque

from genesis_contracts.models import ReferenceRange
from genesis_contracts.validation import validate_excerpts


class _Writes(ast.NodeVisitor):
    """Names rebound by an unsupported module statement, excluding function locals."""

    def __init__(self):
        self.names = set()

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_FunctionDef(self, node):
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Import(self, node):
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        self.names.update(alias.asname or alias.name for alias in node.names)

    def visit_Subscript(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)) and isinstance(node.value, ast.Name):
            self.names.add(node.value.id)
        self.generic_visit(node)

    visit_Attribute = visit_Subscript


def _definitions(tree):
    definitions = defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name].append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            writes = _Writes()
            writes.visit(node)
            for name in writes.names:
                definitions[name].append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(target, ast.Name) for target in targets) and node.value is not None:
                scoped = any(
                    isinstance(
                        value,
                        (
                            ast.Lambda,
                            ast.ListComp,
                            ast.SetComp,
                            ast.DictComp,
                            ast.GeneratorExp,
                            ast.NamedExpr,
                        ),
                    )
                    for value in ast.walk(node.value)
                )
                for target in targets:
                    # These expressions introduce their own binding scope. Leave
                    # them unsupported rather than treating local names as globals.
                    definitions[target.id].append(None if scoped else node)
            else:
                writes = _Writes()
                writes.visit(node)
                for name in writes.names:
                    definitions[name].append(None)
        else:
            writes = _Writes()
            writes.visit(node)
            for name in writes.names:
                definitions[name].append(None)
        # A visible mutation makes a single original assignment insufficient
        # context. Do not present that original source as an immutable value.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            callee = node.value.func
            if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                definitions[callee.value.id].append(None)
    return definitions


def _scope_names(table):
    names = {
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_global() and symbol.is_referenced()
    }
    for child in table.get_children():
        names.update(_scope_names(child))
    return names


def _tables(root):
    result = defaultdict(list)

    def visit(table, prefix):
        for child in table.get_children():
            name = ".".join((*prefix, child.get_name()))
            result[name].append(child)
            visit(child, (*prefix, child.get_name()))

    visit(root, ())
    return result


def _range(node, text):
    lines = [
        match.group().rstrip("\r\n")
        for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
        if match.group()
    ]
    start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
    column = node.col_offset if start == node.lineno else 0
    return ReferenceRange(
        start_line=start,
        end_line=node.end_lineno,
        start_column=len(lines[start - 1].encode()[:column].decode()),
        end_column=len(lines[node.end_lineno - 1].encode()[: node.end_col_offset].decode()),
    )


def _covers(ref, span):
    r = ref.range
    return (r.start_line, r.start_column or 0) <= (span.start_line, span.start_column or 0) and (
        r.end_line,
        r.end_column if r.end_column is not None else 10**9,
    ) >= (span.end_line, span.end_column or 0)


def lexical_bundles(local, reader, roots, missing):
    """Select unique same-module definitions referenced by root callable scopes.

    Uses compiler scope analysis over validated frozen bytes, not Python imports.
    Original facts and unknown resolutions remain authoritative. Imported,
    conditional, rebound and unsupported bindings are not resolved by this pass.
    """
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    modules = {}
    for fact in local.facts.functions:
        if fact.kind != "module":
            continue
        ref = catalog[fact.evidence_ids[0]]
        module_roots = {
            f.symbol_id.split("#", 1)[1]
            for f in local.facts.functions
            if f.kind == "function"
            and f.side == fact.side
            and f.symbol_id in roots
            and catalog[f.evidence_ids[0]].path == ref.path
        }
        if not module_roots:
            continue
        excerpt = reader.read_excerpt(ref.evidence_id)
        validate_excerpts(local.snapshot.snapshot_id, (ref,), (excerpt,))
        if ref.range.start_line != 1 or ref.range.start_column not in {None, 0}:
            missing.append("Lexical dependency context requires a complete frozen module excerpt.")
            continue
        try:
            tree = ast.parse(excerpt.text)
            tables = _tables(symtable.symtable(excerpt.text, ref.path, "exec"))
        except (SyntaxError, ValueError, RecursionError):
            missing.append("Frozen source could not be inspected for lexical dependency context.")
            continue
        modules[(fact.side, ref.path)] = (excerpt.text, _definitions(tree), tables, module_roots)
    needed = set()
    for (side, path), (text, definitions, tables, module_roots) in modules.items():
        pending = deque(
            sorted(
                {
                    name
                    for root in module_roots
                    for table in tables.get(root, ())
                    for name in _scope_names(table)
                }
            )
        )
        visited = set()
        while pending:
            name = pending.popleft()
            if name in visited:
                continue
            if len(visited) >= 64:
                missing.append("Lexical dependency context reached its 64-name traversal limit.")
                break
            visited.add(name)
            candidates = definitions.get(name, [])
            if not candidates:
                continue
            if len(candidates) != 1 or candidates[0] is None:
                missing.append(
                    "Ambiguous or unsupported lexical dependency definitions were omitted."
                )
                continue
            node = candidates[0]
            # Ordinary imports are handled by existing extraction/resolution and
            # import-context selection. They are outside this same-module pass,
            # not evidence of omitted or ambiguous local definitions.
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            needed.add((path, name))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                pending.extend(
                    sorted(
                        {n for table in tables.get(name, ()) for n in _scope_names(table)} - visited
                    )
                )
            else:
                pending.extend(
                    sorted(
                        {
                            n.id
                            for n in ast.walk(node.value)
                            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        }
                        - visited
                    )
                )
    bundles = []
    for path, name in sorted(needed):
        refs = []
        for (side, candidate_path), (text, definitions, tables, module_roots) in sorted(
            modules.items()
        ):
            if path != candidate_path:
                continue
            nodes = definitions.get(name, [])
            if len(nodes) != 1 or nodes[0] is None:
                continue
            span = _range(nodes[0], text)
            candidates = [
                ref
                for ref in local.evidence
                if ref.side == side
                and ref.path == path
                and ref.kind == "code"
                and _covers(ref, span)
            ]
            if not candidates:
                missing.append(
                    "Lexical dependency definition has no complete existing source evidence."
                )
                continue
            # Prefer the narrow existing span; do not synthesize a new range.
            ref = min(
                candidates,
                key=lambda ref: (
                    len(reader.read_excerpt(ref.evidence_id).text),
                    ref.evidence_id,
                ),
            )
            refs.append(ref.evidence_id)
        if refs:
            bundles.append(tuple(dict.fromkeys(refs)))
    return bundles

"""Bounded supporting source for dynamic dispatch; never creates call edges.

Import/package provenance and lexical references are retrieval signals only.
All snippets come from the original frozen evidence catalogue and pass through
the caller's ordinary privacy, excerpt, token and byte budgets.
"""

from __future__ import annotations

import ast
import symtable
from collections import defaultdict, deque

from genesis_contracts.validation import validate_excerpts

from .dependencies import _scope_names, _tables

MAX_RELATED_FUNCTIONS = 32


def _import_matches(module, imported, owner, target_path, target_name):
    if imported != target_name:
        return False
    if module.startswith("."):
        dots = len(module) - len(module.lstrip("."))
        parts = owner.split("/")[:-1]
        if dots > len(parts):
            return False
        prefix = parts[: len(parts) - dots + 1]
        stem = "/".join([*prefix, *module[dots:].split(".")]).rstrip("/")
        # A package re-export can be absent from a bounded snapshot. Retain a
        # same-package reference as context, without asserting its runtime target.
        return bool(stem) and (
            target_path in {stem + ".py", stem + ".pyi"} or target_path.startswith(stem + "/")
        )
    stem = module.replace(".", "/")
    return (
        target_path.startswith(stem + "/")
        or ("/" + stem + "/") in target_path
        or any(
            target_path == suffix or target_path.endswith("/" + suffix)
            for suffix in (stem + ".py", stem + ".pyi", stem + "/__init__.py")
        )
    )


def related_bundles(local, reader, changed, missing):
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    targets = {
        (symbol.split("#", 1)[0], symbol.split("#", 1)[1].split(".")[0])
        for symbol in changed
        if "#" in symbol and not symbol.endswith("#<module>")
    }
    imports = defaultdict(list)
    for fact in local.facts.imports:
        owner = catalog[fact.evidence_ids[0]].path
        if any(
            owner != path and _import_matches(fact.module, fact.imported_name, owner, path, name)
            for path, name in targets
        ):
            imports[(fact.side, owner)].append(fact)
    needed, supporting_imports, ordered = set(), set(), []
    for module in local.facts.functions:
        if module.kind != "module":
            continue
        ref = catalog[module.evidence_ids[0]]
        relevant = imports.get((module.side, ref.path), ())
        if not relevant:
            continue
        excerpt = reader.read_excerpt(ref.evidence_id)
        validate_excerpts(local.snapshot.snapshot_id, (ref,), (excerpt,))
        if ref.range.start_line != 1 or ref.range.start_column not in {None, 0}:
            continue
        try:
            tree = ast.parse(excerpt.text)
            tables = _tables(symtable.symtable(excerpt.text, ref.path, "exec"))
        except (SyntaxError, ValueError, RecursionError):
            missing.append("Supporting source could not be inspected for lexical relationships.")
            continue
        functions = {}

        def visit(body, prefix=()):
            for node in body:
                if isinstance(node, ast.ClassDef):
                    visit(node.body, (*prefix, node.name))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions[".".join((*prefix, node.name))] = node

        visit(tree.body)
        aliases = {fact.alias or fact.imported_name for fact in relevant}
        roots = {
            name
            for name in functions
            if any(_scope_names(table) & aliases for table in tables.get(name, ()))
        }
        # A registry reference and the dispatch/collection methods often live in
        # one class. Walk lexical self/cls references in both directions, retaining
        # candidate source even when the target's runtime type remains unknown.
        adjacency = defaultdict(set)
        for name, node in functions.items():
            parent = name.rpartition(".")[0]
            for value in ast.walk(node):
                if not (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id in {"self", "cls"}
                    and parent
                ):
                    continue
                target = parent + "." + value.attr
                if target in functions:
                    adjacency[name].add(target)
                    adjacency[target].add(name)
        queue, visited = deque(sorted(roots)), set()
        while queue:
            name = queue.popleft()
            if name in visited:
                continue
            symbol = ref.path + "#" + name
            if symbol not in needed and len(needed) >= MAX_RELATED_FUNCTIONS:
                missing.append("Supporting source reached its 32-function traversal limit.")
                break
            visited.add(name)
            if symbol not in needed:
                needed.add(symbol)
                ordered.append(symbol)
            queue.extend(sorted(adjacency[name] - visited))
            parent = name.rpartition(".")[0]
            initializer = parent + ".__init__"
            if parent and initializer in functions and initializer not in visited:
                queue.append(initializer)
        if visited:
            supporting_imports.update(ident for fact in relevant for ident in fact.evidence_ids)
    bodies = defaultdict(list)
    for fact in local.facts.functions:
        if fact.kind == "function" and fact.symbol_id in needed:
            bodies[fact.symbol_id].extend(fact.evidence_ids)
    return [
        *(tuple(dict.fromkeys(bodies[symbol])) for symbol in ordered if bodies[symbol]),
        *((ident,) for ident in sorted(supporting_imports)),
    ], needed

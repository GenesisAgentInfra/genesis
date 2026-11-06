"""Retrieve bounded module-level callback wiring, never infer runtime edges."""

from __future__ import annotations

import ast
from collections import defaultdict

from genesis_contracts.validation import validate_excerpts

from .dependencies import _covers, _range

MAX_REGISTRATION_STATEMENTS = 32


def registration_bundles(local, reader, roots, missing):
    """Keep registration source and callbacks connected to changed functions.

    Only top-level statements sharing local assignment/callback names participate.
    Imported SDK names and string labels do not connect unrelated workflows. This
    is lexical retrieval, not evaluation of builders, calls, or callback execution.
    """
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    needed, callbacks = defaultdict(list), set()
    for module in local.facts.functions:
        if module.kind != "module":
            continue
        ref = catalog[module.evidence_ids[0]]
        seeds = {symbol.split("#", 1)[1] for symbol in roots if symbol.startswith(ref.path + "#")}
        if not seeds:
            continue
        excerpt = reader.read_excerpt(ref.evidence_id)
        validate_excerpts(local.snapshot.snapshot_id, (ref,), (excerpt,))
        if ref.range.start_line != 1 or ref.range.start_column not in {None, 0}:
            continue
        try:
            tree = ast.parse(excerpt.text)
        except (SyntaxError, ValueError, RecursionError):
            missing.append(
                "Frozen source could not be inspected for callback registration context."
            )
            continue
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        statements = [
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr))
            and any(isinstance(child, ast.Call) for child in ast.walk(node))
            and not any(
                isinstance(
                    child,
                    (
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                        ast.NamedExpr,
                    ),
                )
                for child in ast.walk(node)
            )
        ]
        bindings = {
            child.id
            for node in statements
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        }
        names = [
            {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            & (bindings | functions.keys())
            for node in statements
        ]
        connected, selected = seeds & functions.keys(), set()
        while connected:
            candidates = [
                i for i, refs in enumerate(names) if i not in selected and refs & connected
            ]
            if not candidates:
                break
            remaining = MAX_REGISTRATION_STATEMENTS - len(selected)
            if len(candidates) > remaining:
                missing.append("Callback registration context reached its 32-statement limit.")
            for i in candidates[:remaining]:
                selected.add(i)
                connected.update(names[i])
            if len(selected) >= MAX_REGISTRATION_STATEMENTS:
                break
        for name in connected & functions.keys():
            callbacks.add(ref.path + "#" + name)
        for i in sorted(selected):
            span = _range(statements[i], excerpt.text)
            candidates = [
                item
                for item in local.evidence
                if item.side == ref.side
                and item.path == ref.path
                and item.kind == "code"
                and _covers(item, span)
            ]
            if not candidates:
                missing.append("Callback registration has no complete existing source evidence.")
                continue
            selected_ref = min(
                candidates,
                key=lambda item: (
                    len(reader.read_excerpt(item.evidence_id).text),
                    item.evidence_id,
                ),
            )
            # Shifted source keeps its original side; no synthesized evidence.
            key = (ref.path, ast.dump(statements[i], include_attributes=False))
            needed[key].append(selected_ref.evidence_id)
    bodies = defaultdict(list)
    for fact in local.facts.functions:
        if fact.kind == "function" and fact.symbol_id in callbacks - roots:
            bodies[fact.symbol_id].extend(fact.evidence_ids)
    return (
        [tuple(dict.fromkeys(ids)) for ids in needed.values()]
        + [tuple(dict.fromkeys(bodies[symbol])) for symbol in sorted(bodies)],
        callbacks,
    )

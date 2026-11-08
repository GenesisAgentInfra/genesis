"""Bounded imported-value source retrieval; no value evaluation or call resolution."""

from __future__ import annotations

import ast
import hashlib
import symtable
from collections import defaultdict, deque

from genesis_contracts.validation import validate_excerpts

from .dependencies import _covers, _definitions, _range, _scope_names, _tables
from .modules import local_module_candidates


def _header_names(node, missing, parent=None):
    # Bases, decorators and defaults execute in the enclosing scope, so their
    # references are absent from the definition's child symbol table.
    headers = [*node.decorator_list]
    if isinstance(node, ast.ClassDef):
        headers.extend([*node.bases, *(keyword.value for keyword in node.keywords)])
    else:
        headers.extend([*node.args.defaults, *(v for v in node.args.kw_defaults if v)])
    names = set()
    for expression in headers:
        try:
            # A header can introduce lambda/comprehension locals of its own.
            names.update(
                _scope_names(symtable.symtable(ast.unparse(expression), "<header>", "eval"))
            )
        except (SyntaxError, ValueError, RecursionError):
            missing.append("Imported-value definition header dependencies were not inspected.")
    if parent is not None:
        names = {
            name
            for name in names
            if name in parent.get_identifiers() and parent.lookup(name).is_global()
        }
    return names


def _names(node, tables, missing):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {
            name for table in tables.get(node.name, ()) for name in _scope_names(table)
        } | _header_names(node, missing)
    return {
        value.id
        for value in ast.walk(node.value)
        if isinstance(value, ast.Name) and isinstance(value.ctx, ast.Load)
    }


def imported_value_bundles(local, reader, roots, missing):
    """Keep import bindings and original definitions together on both diff sides.

    Compiler scopes find referenced globals. The existing frozen-path import map
    identifies source candidates only: it never establishes runtime values or
    adds a resolution/edge. Unique module definitions supply their local source
    dependencies (e.g. a class and its instance); module aliases supply a complete
    module. Every bundle still passes the caller's privacy and packing rules.
    """
    catalog = {ref.evidence_id: ref for ref in local.evidence}
    modules = {
        (fact.side, catalog[fact.evidence_ids[0]].path): fact.evidence_ids
        for fact in local.facts.functions
        if fact.kind == "module"
    }
    # An unanalyzed captured module can still make an import ambiguous. Never
    # silently select the one parseable candidate instead of recording the gap.
    module_paths = set(modules) | {
        (file.side, file.path)
        for file in local.snapshot.files
        if file.path.endswith((".py", ".pyi"))
    }
    empty_modules = {
        (file.side, file.path)
        for file in local.snapshot.files
        if file.content_digest == "sha256:" + hashlib.sha256(b"").hexdigest()
    }
    loaded = {}
    root_headers = {}

    def load(side, path):
        key = (side, path)
        if key in loaded:
            return loaded[key]
        loaded[key] = None
        if key not in modules:
            if key in empty_modules:
                loaded[key] = ("", {}, {})
                return loaded[key]
            missing.append("Imported-value context has no complete frozen module source.")
            return None
        ref = catalog[modules[key][0]]
        excerpt = reader.read_excerpt(ref.evidence_id)
        validate_excerpts(local.snapshot.snapshot_id, (ref,), (excerpt,))
        if ref.range.start_line != 1 or ref.range.start_column not in {None, 0}:
            missing.append("Imported-value context requires a complete frozen module excerpt.")
            return None
        try:
            tree = ast.parse(excerpt.text)
            root_table = symtable.symtable(excerpt.text, path, "exec")
            tables = _tables(root_table)
        except (SyntaxError, ValueError, RecursionError):
            missing.append("Imported-value source could not be inspected.")
            return None
        # Match the extractor's conservative treatment of dynamic namespaces.
        # Supplying one initial assignment after such mutation would be misleading.
        if any(
            isinstance(node, ast.Delete)
            or isinstance(node, ast.ImportFrom)
            and any(a.name == "*" for a in node.names)
            or isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"exec", "eval", "setattr", "globals", "locals"}
            for node in ast.walk(tree)
        ):
            missing.append("Imported-value context omitted a dynamic module namespace.")
            return None
        loaded[key] = (excerpt.text, _definitions(tree), tables)
        parents = {}

        def record_parents(table):
            for child in table.get_children():
                parents[(child.get_name(), child.get_lineno())] = table
                record_parents(child)

        record_parents(root_table)
        root_headers[key] = {
            node.lineno: (node, parents[(node.name, node.lineno)])
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (node.name, node.lineno) in parents
        }
        return loaded[key]

    def unique_definition(definitions, name):
        nodes = definitions.get(name, ())
        if not nodes:
            return None
        if len(nodes) != 1 or nodes[0] is None:
            missing.append("Imported-value context omitted an ambiguous or unsupported binding.")
            return None
        return nodes[0]

    def evidence(side, path, node, text):
        span = _range(node, text)
        refs = [
            ref
            for ref in local.evidence
            if ref.side == side and ref.path == path and ref.kind == "code" and _covers(ref, span)
        ]
        if not refs:
            missing.append("Imported-value definition has no complete existing source evidence.")
            return ()
        return (
            min(
                refs, key=lambda r: (len(reader.read_excerpt(r.evidence_id).text), r.evidence_id)
            ).evidence_id,
        )

    def import_target(side, path, name, node):
        alias = next(
            (
                a
                for a in node.names
                if (a.asname or (a.name.split(".")[0] if isinstance(node, ast.Import) else a.name))
                == name
            ),
            None,
        )
        if alias is None:
            return None
        if isinstance(node, ast.Import):
            if "." in alias.name and alias.asname is None:
                missing.append("Imported-value context omitted an unaliased dotted module binding.")
                return None
            module, member = alias.name, None
        else:
            module, member = "." * node.level + (node.module or ""), alias.name
        paths = local_module_candidates(module, side, path, module_paths)
        if len(paths) == 1:
            target = next(iter(paths))
            data = load(side, target)
            if data is None:
                return None
            if member is None or member in data[1]:
                return target, member
        if len(paths) > 1:
            missing.append("Imported-value context omitted an ambiguous local module path.")
            return None
        if member is not None:
            child = module + ("" if module.endswith(".") else ".") + member
            paths = local_module_candidates(child, side, path, module_paths)
            if len(paths) == 1:
                return next(iter(paths)), None
            if len(paths) > 1:
                missing.append("Imported-value context omitted an ambiguous local module path.")
        # External/unavailable imports have no frozen source to retrieve. Their
        # existing import/call facts and unknown resolutions remain unchanged.
        return None

    def collect(side, path, name, refs, visited):
        key = (path, name)
        if key in visited:
            return
        if len(visited) >= 64:
            missing.append("Imported-value context reached its 64-binding traversal limit.")
            return
        visited.add(key)
        data = load(side, path)
        if data is None:
            return
        text, definitions, tables = data
        if name is None:
            refs.extend(modules.get((side, path), ()))
            return
        node = unique_definition(definitions, name)
        if node is None:
            return
        refs.extend(evidence(side, path, node, text))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            target = import_target(side, path, name, node)
            if target:
                collect(side, *target, refs, visited)
        else:
            for dependency in sorted(_names(node, tables, missing)):
                collect(side, path, dependency, refs, visited)

    bundles = defaultdict(list)
    module_roots = defaultdict(set)
    for fact in local.facts.functions:
        if fact.kind == "function" and fact.symbol_id in roots:
            module_roots[(fact.side, catalog[fact.evidence_ids[0]].path)].add(
                fact.symbol_id.split("#", 1)[1]
            )
    for (side, path), root_names in sorted(module_roots.items()):
        # Legacy/partial local analyses may contain function excerpts without a
        # module fact. Their existing capability gaps remain authoritative; this
        # optional retrieval pass has no source root to inspect in that case.
        if (side, path) not in modules:
            continue
        data = load(side, path)
        if data is None:
            continue
        text, definitions, tables = data
        names = set()
        for root in root_names:
            for table in tables.get(root, ()):
                names.update(_scope_names(table))
                header = root_headers[(side, path)].get(table.get_lineno())
                if header:
                    node, parent = header
                    names.update(_header_names(node, missing, parent))
        pending = deque(sorted(names))
        visited = set()
        while pending:
            name = pending.popleft()
            if name in visited:
                continue
            if len(visited) >= 64:
                missing.append("Imported-value context reached its 64-binding traversal limit.")
                break
            visited.add(name)
            node = unique_definition(definitions, name)
            if node is None:
                continue
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                pending.extend(sorted(_names(node, tables, missing) - visited))
                continue
            target = import_target(side, path, name, node)
            if target is None:
                continue
            target_data = load(side, target[0])
            if target_data is None:
                continue
            if target[1] is not None:
                target_node = unique_definition(target_data[1], target[1])
                # Callable-body selection already uses the resolved call graph.
                if target_node is None or isinstance(
                    target_node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    continue
            refs = []
            collect(side, *target, refs, set())
            if refs:
                bundles[(path, name)].extend((*evidence(side, path, node, text), *refs))
    return [tuple(dict.fromkeys(refs)) for _, refs in sorted(bundles.items())]

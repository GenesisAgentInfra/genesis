"""Python entry detection: where execution enters the code from outside.

Three sources, in decreasing confidence. Framework adapters recognise a decorator
only when the file also imports that framework. The `__main__` guard marks the
functions it calls. The root heuristic lists public functions nothing is seen to
call; it is deliberately broad and is never treated as a confirmed entry.

Recognition is by decorator shape and imports only. Routers registered by a call
such as `app.add_api_route(...)`, URL tables and plugin registries are not detected.
"""

from __future__ import annotations

import hashlib

from genesis_contracts.business_map import EntryDetection, EntryKind
from genesis_contracts.facts import CodeEntry, CodeFact, CodeSymbol, FactKind
from genesis_contracts.models import EvidenceSide

from genesis_ci.python.extract import Extraction

HTTP_FRAMEWORKS = ("fastapi", "starlette", "flask", "quart", "sanic", "aiohttp", "litestar")
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
HTTP_ROUTES = {"route", "api_route", "websocket"}
CLI_FRAMEWORKS = ("typer", "click")
CLI_COMMANDS = {"command", "group", "callback"}
TASK_DECORATORS = {
    "celery": {"task", "shared_task"},
    "dramatiq": {"actor"},
    "huey": {"task", "periodic_task"},
    "rq": {"job"},
}
TOOL_FRAMEWORKS = (
    "langchain",
    "langchain_core",
    "agents",
    "mcp",
    "fastmcp",
    "pydantic_ai",
    "crewai",
    "smolagents",
    "claude_agent_sdk",
)
TOOL_DECORATORS = {"tool", "function_tool", "tool_plain"}
MAIN_GUARDS = {'__name__ == "__main__"', "__name__ == '__main__'"}
_ADAPTER_ORDER = (
    EntryKind.http_route,
    EntryKind.cli_command,
    EntryKind.task,
    EntryKind.agent_tool,
    EntryKind.main,
)


def entry_id(symbol_id: str) -> str:
    return "entry_" + hashlib.sha256(symbol_id.encode("utf-8")).hexdigest()[:16]


def _first(frameworks, imported):
    return next((name for name in frameworks if name in imported), None)


def _literal(arguments, names):
    for argument in arguments:
        value = argument.value
        if argument.name in names and value.kind == "literal" and isinstance(value.value, str):
            return value.value
    return None


def _classify(decorator, imported):
    """Return (kind, framework, attributes) for a recognised framework decorator."""
    call = decorator.kind == "call" and bool(decorator.children)
    callee = decorator.children[0] if call else decorator
    arguments = decorator.arguments if call else ()
    if callee.kind == "attribute":
        name = callee.attribute
    elif callee.kind == "name":
        name = callee.text
    else:
        return None
    http = _first(HTTP_FRAMEWORKS, imported)
    if callee.kind == "attribute" and http and name in HTTP_METHODS | HTTP_ROUTES:
        if name in HTTP_METHODS:
            method = name.upper()
        elif name == "websocket":
            method = "WEBSOCKET"
        else:
            listed = next((a.value for a in arguments if a.name == "methods"), None)
            values = [
                child.value
                for child in (listed.children if listed is not None else ())
                if child.kind == "literal" and isinstance(child.value, str)
            ]
            method = ",".join(item.upper() for item in values) or "ANY"
        attributes = {"method": method}
        path = _literal(arguments, {None, "path", "rule"})
        if path is not None:
            attributes["path"] = path
        return EntryKind.http_route, http, attributes
    cli = _first(CLI_FRAMEWORKS, imported)
    if cli and name in CLI_COMMANDS:
        command = _literal(arguments, {None, "name"})
        return EntryKind.cli_command, cli, {"command": command} if command else {}
    for framework, names in TASK_DECORATORS.items():
        if framework in imported and name in names:
            task = _literal(arguments, {"name"})
            return EntryKind.task, framework, {"task": task} if task else {}
    tools = _first(TOOL_FRAMEWORKS, imported)
    if tools and name in TOOL_DECORATORS:
        return EntryKind.agent_tool, tools, {}
    return None


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        bool({"tests", "test"} & set(path.split("/")[:-1]))
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def detect_python_entries(
    extraction: Extraction, symbols: tuple[CodeSymbol, ...], facts: list[CodeFact]
) -> tuple[list[CodeEntry], dict]:
    """Detect entries on every side. Returns the entries and the evidence they cite."""
    catalog = {ref.evidence_id: ref for ref in extraction.analysis.evidence}
    by_symbol = {(symbol.side, symbol.symbol_id): symbol for symbol in symbols}
    found: dict[tuple[EvidenceSide, str], CodeEntry] = {}

    def add(symbol, kind, detection, framework, attributes, evidence):
        key = (symbol.side, symbol.symbol_id)
        current = found.get(key)
        if current is not None and (
            current.detection == EntryDetection.adapter
            and _ADAPTER_ORDER.index(current.kind) <= _ADAPTER_ORDER.index(kind)
        ):
            return
        evidence = tuple(ref for ref in evidence if ref in catalog) or symbol.evidence_ids
        if not evidence:
            return
        found[key] = CodeEntry(
            entry_id=entry_id(symbol.symbol_id),
            symbol_id=symbol.symbol_id,
            kind=kind,
            detection=detection,
            framework=framework,
            attributes=attributes,
            evidence_ids=evidence,
            side=symbol.side,
        )

    imports = {
        key: {item.module.split(".")[0] for item in file.imports if item.module}
        for key, file in extraction.files.items()
    }
    for parsed in extraction.analysis.symbols:
        symbol = by_symbol.get((parsed.side, parsed.symbol_id))
        if symbol is None or symbol.kind != "function":
            continue
        imported = imports.get((parsed.side, parsed.path), set())
        for decorator in parsed.decorators:
            match = _classify(decorator, imported)
            if match is not None:
                kind, framework, attributes = match
                add(
                    symbol,
                    kind,
                    EntryDetection.adapter,
                    framework,
                    attributes,
                    decorator.evidence_ids,
                )
                break

    guards = {
        (fact.side, fact.fingerprint)
        for fact in facts
        if fact.kind == FactKind.condition
        and fact.symbol_id.endswith("#<module>")
        and fact.text in MAIN_GUARDS
    }
    called: dict[tuple[EvidenceSide, str], set[str]] = {}
    for fact in facts:
        if fact.kind != FactKind.call or fact.target is None:
            continue
        for target in fact.target.targets:
            called.setdefault((fact.side, target), set()).add(fact.symbol_id)
            guarded = any(
                (fact.side, guard.fingerprint) in guards and guard.branch == "true"
                for guard in fact.guards
            )
            symbol = by_symbol.get((fact.side, target))
            if guarded and symbol is not None and symbol.kind == "function":
                add(
                    symbol,
                    EntryKind.main,
                    EntryDetection.adapter,
                    None,
                    {"guard": "__main__"},
                    fact.evidence_ids,
                )

    classes = {key for key, symbol in by_symbol.items() if symbol.kind == "class"}
    for key, symbol in sorted(by_symbol.items(), key=lambda item: (item[0][0].value, item[0][1])):
        if symbol.kind != "function" or key in found or _is_test_path(symbol.path):
            continue
        parts = symbol.qualified_name.split(".")
        if any(part.startswith("_") for part in parts) or len(parts) > 2:
            continue
        if len(parts) == 2 and (symbol.side, symbol.path + "#" + parts[0]) not in classes:
            continue
        callers = called.get(key, set()) - {symbol.symbol_id}
        if not callers:
            add(symbol, EntryKind.root, EntryDetection.root_heuristic, None, {}, ())
    entries = [found[key] for key in sorted(found, key=lambda item: (item[0].value, item[1]))]
    cited = {ref: catalog[ref] for entry in entries for ref in entry.evidence_ids}
    return entries, cited

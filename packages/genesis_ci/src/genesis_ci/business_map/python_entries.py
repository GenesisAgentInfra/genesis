"""Python entry detection: where execution enters the code from outside.

Four sources, in decreasing confidence. Framework adapters recognise a decorator
only when the file also imports that framework. Classes listed together under a
base that only declares a method are handlers a dispatcher runs. The `__main__`
guard marks the functions it calls. The root heuristic lists public functions no
code outside the tests is seen to call; it is deliberately broad and is never
treated as a confirmed entry.

Recognition is by the shape of the source only. Routers registered by a call such
as `app.add_api_route(...)`, tables of functions, and decorators a project defines
for its own registry are not detected.
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
ABSTRACT = "abstractmethod"
PROPERTIES = {"property", "abstractproperty", "cached_property", "setter", "getter", "deleter"}
NOT_IMPLEMENTED = "NotImplementedError"
# One class in a list is a value, not a registry.
REGISTRY_MINIMUM = 2
_ADAPTER_ORDER = (
    EntryKind.http_route,
    EntryKind.cli_command,
    EntryKind.task,
    EntryKind.agent_tool,
    EntryKind.handler,
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


def _decorator_names(parsed) -> set[str]:
    found = set()
    for decorator in parsed.decorators:
        call = decorator.kind == "call" and bool(decorator.children)
        callee = decorator.children[0] if call else decorator
        found.add(callee.attribute if callee.kind == "attribute" else callee.text)
    return found


class _Classes:
    """The classes of a snapshot: what each inherits and which methods it defines."""

    def __init__(self, extraction: Extraction, by_symbol: dict, facts: list[CodeFact]):
        self.extraction, self.by_symbol = extraction, by_symbol
        self.methods: dict[tuple, dict[str, object]] = {}
        for parsed in extraction.analysis.symbols:
            inside, _, name = parsed.qualified_name.rpartition(".")
            owner = parsed.path + "#" + inside
            if parsed.kind == "function" and inside and self.is_class(parsed.side, owner):
                self.methods.setdefault((parsed.side, owner), {})[name] = parsed
        self.facts: dict[tuple, list[CodeFact]] = {}
        for fact in facts:
            self.facts.setdefault((fact.side, fact.symbol_id), []).append(fact)
        self._chains: dict[tuple, tuple[str, ...]] = {}

    def named(self, expr, side, path) -> str | None:
        """The class an expression names, or creates an instance of."""
        if expr.kind == "call" and expr.children:
            expr = expr.children[0]
        if expr.kind not in {"name", "attribute"}:
            return None
        targets = self.extraction.resolver.resolve(expr, side, path).targets
        if len(targets) == 1 and self.is_class(side, targets[0]):
            return targets[0]
        return None

    def is_class(self, side, symbol_id: str) -> bool:
        symbol = self.by_symbol.get((side, symbol_id))
        return symbol is not None and symbol.kind == "class"

    def chain(self, side, cls: str) -> tuple[str, ...]:
        """The class, then the classes it inherits from that are written in the code."""
        if (side, cls) not in self._chains:
            found, pending = [cls], [cls]
            while pending:
                path, _, name = pending.pop(0).partition("#")
                file = self.extraction.files.get((side, path))
                for base in file.bases.get(name, ()) if file is not None else ():
                    for target in self.extraction.resolver.resolve(base, side, path).targets:
                        if target not in found and self.is_class(side, target):
                            found.append(target)
                            pending.append(target)
            self._chains[(side, cls)] = tuple(found)
        return self._chains[(side, cls)]

    def _declared_only(self, side, parsed) -> bool:
        """A method the class leaves to its subclasses."""
        if ABSTRACT in _decorator_names(parsed):
            return True
        body = self.facts.get((side, parsed.symbol_id), [])
        return (
            len(body) == 1 and body[0].kind == FactKind.raises and NOT_IMPLEMENTED in body[0].text
        )

    def declared(self, side, cls: str) -> list[str]:
        """Public methods a class declares without implementing; properties are not run."""
        return [
            name
            for name, parsed in self.methods.get((side, cls), {}).items()
            if not name.startswith("_")
            and not PROPERTIES & _decorator_names(parsed)
            and self._declared_only(side, parsed)
        ]

    def implementation(self, side, cls: str, name: str) -> str | None:
        """What runs when `name` is called on an instance of the class."""
        for owner in self.chain(side, cls):
            parsed = self.methods.get((side, owner), {}).get(name)
            if parsed is not None:
                return None if self._declared_only(side, parsed) else parsed.symbol_id
        return None


def _listed(value) -> list[tuple[str | None, object]]:
    """The elements of a list, tuple or dictionary literal, a dictionary's with their keys."""
    if value.kind in {"list", "tuple"}:
        return [(None, child) for child in value.children]
    if value.kind == "dict":
        return [
            (
                item.key.value
                if item.key is not None
                and item.key.kind == "literal"
                and isinstance(item.key.value, str)
                else None,
                item.value,
            )
            for item in value.entries
        ]
    return []


def _registered(extraction: Extraction, by_symbol: dict, facts: list[CodeFact]):
    """Handlers registered by listing their classes: (symbol, attributes, evidence).

    The shape is a list, tuple or dictionary written at module or class level whose
    elements are all classes with a shared base, where that base declares a method
    without implementing it and every listed class implements it. A dispatcher runs
    that method on whichever class it picks, so no call to the implementations is
    visible. Whether the dispatcher is driven from outside the system is not known.
    """
    classes = _Classes(extraction, by_symbol, facts)
    for (side, path), file in sorted(
        extraction.files.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        if _is_test_path(path):
            continue
        for binding in file.bindings:
            listed = _listed(binding.value)
            if len(listed) < REGISTRY_MINIMUM or binding.target.kind != "name":
                continue
            # A list built inside a function is a value of that call, not a registration.
            owner = binding.symbol_id
            if not owner.endswith("#<module>") and not classes.is_class(side, owner):
                continue
            named = [classes.named(expr, side, path) for _, expr in listed]
            if None in named or len(set(named)) < REGISTRY_MINIMUM:
                continue
            chains = [classes.chain(side, cls) for cls in named]
            for base in chains[0]:
                if not all(base in chain for chain in chains[1:]):
                    continue
                for method in classes.declared(side, base):
                    runs = [classes.implementation(side, cls, method) for cls in named]
                    if None in runs:
                        continue
                    for (label, expr), symbol_id in zip(listed, runs, strict=True):
                        attributes = {
                            "registry": binding.target.text,
                            "base": by_symbol[(side, base)].qualified_name,
                        }
                        if label:
                            attributes["name"] = label
                        yield (
                            by_symbol[(side, symbol_id)],
                            attributes,
                            expr.evidence_ids or binding.evidence_ids,
                        )


def detect_python_entries(
    extraction: Extraction, symbols: tuple[CodeSymbol, ...], facts: list[CodeFact]
) -> tuple[list[CodeEntry], dict]:
    """Detect entries on every side. Returns the entries and the evidence they cite."""
    catalog = {ref.evidence_id: ref for ref in extraction.analysis.evidence}
    by_symbol = {(symbol.side, symbol.symbol_id): symbol for symbol in symbols}
    found: dict[tuple[EvidenceSide, str], CodeEntry] = {}

    def add(symbol, kind, detection, framework, attributes, evidence):
        # A route or a main guard written in test code serves the tests, not a user.
        if _is_test_path(symbol.path):
            return
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

    for symbol, attributes, evidence in _registered(extraction, by_symbol, facts):
        add(symbol, EntryKind.handler, EntryDetection.adapter, None, attributes, evidence)

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
        # A call from a test is not a way production code gets there.
        in_test = _is_test_path(fact.symbol_id.partition("#")[0])
        for target in fact.target.targets:
            if not in_test:
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

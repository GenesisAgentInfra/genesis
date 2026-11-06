"""Bounded fixture visibility within captured modules/classes and ancestor conftests."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from genesis_contracts.intelligence import FixtureUse
from genesis_contracts.models import Resolution


def callee(expr):
    return expr.children[0] if expr.kind == "call" else expr


def keywords(expr):
    return {a.name: a.value for a in expr.arguments if a.name and not a.spread}


def positional(expr):
    return [a.value for a in expr.arguments if not a.name and not a.spread]


def literal_names(expr):
    if expr.kind == "literal" and isinstance(expr.value, str):
        return tuple(part.strip() for part in expr.value.split(",") if part.strip())
    if expr.kind in {"list", "tuple"} and all(
        c.kind == "literal" and isinstance(c.value, str) for c in expr.children
    ):
        return tuple(c.value for c in expr.children)
    return None


@dataclass(frozen=True)
class Fixture:
    symbol: object
    name: str
    autouse: bool
    uncertain: bool


class FixtureCatalog:
    def __init__(self, extraction):
        self.extraction = extraction
        self.fixtures = []
        self.dynamic_definitions = []
        self.symbols = {(s.side, s.symbol_id): s for s in extraction.analysis.symbols}
        for symbol in extraction.analysis.symbols:
            if symbol.kind != "function":
                continue
            for decorator in symbol.decorators:
                resolution = extraction.resolver.resolve(
                    callee(decorator), symbol.side, symbol.path
                )
                if "external:pytest.fixture" not in resolution.targets:
                    continue
                kw = keywords(decorator)
                name = kw.get("name")
                if name and (name.kind != "literal" or not isinstance(name.value, str)):
                    self.dynamic_definitions.append(symbol)
                    continue
                autouse = kw.get("autouse")
                uncertain = (
                    resolution.status != "resolved"
                    or bool(symbol.declaration_conditions)
                    or any(a.spread for a in decorator.arguments)
                )
                uncertain |= autouse is not None and (
                    autouse.kind != "literal" or not isinstance(autouse.value, bool)
                )
                self.fixtures.append(
                    Fixture(
                        symbol,
                        name.value if name else symbol.qualified_name.split(".")[-1],
                        bool(autouse and autouse.kind == "literal" and autouse.value is True),
                        uncertain,
                    )
                )

    def decorators(self, test):
        result = list(test.decorators)
        parents = test.qualified_name.split(".")[:-1]
        for index in range(1, len(parents) + 1):
            symbol = self.symbols.get((test.side, test.path + "#" + ".".join(parents[:index])))
            if symbol and symbol.kind == "class":
                result.extend(symbol.decorators)
        return result

    def rank(self, fixture, test):
        symbol = fixture.symbol
        if symbol.side != test.side:
            return None
        parent_name = symbol.qualified_name.rpartition(".")[0]
        test_parent = test.qualified_name.rpartition(".")[0]
        if symbol.path == test.path:
            if not parent_name:
                return (2, 0)
            owner = self.symbols.get((symbol.side, symbol.path + "#" + parent_name))
            if parent_name == test_parent and owner and owner.kind == "class":
                return (3, 0)
            return None
        if parent_name or PurePosixPath(symbol.path).name != "conftest.py":
            return None
        directory = PurePosixPath(symbol.path).parent
        if directory in PurePosixPath(test.path).parents:
            return (1, len(directory.parts))
        return None

    def missing_conftests(self, test):
        paths = {
            item.path
            for item in self.extraction.analysis.coverage
            if item.side == test.side and item.syntax.status != "analyzed"
        }
        for item in self.extraction.analysis.change_set.unresolved:
            if item.startswith(test.side.value + ":"):
                paths.add(item[len(test.side.value) + 1 :].rsplit(":", 1)[0])
        return tuple(
            sorted(
                path
                for path in paths
                if PurePosixPath(path).name == "conftest.py"
                and PurePosixPath(path).parent in PurePosixPath(test.path).parents
            )
        )

    def lookup(self, name, test):
        if self.missing_conftests(test):
            return ()

        candidates = [(self.rank(f, test), f) for f in self.fixtures if f.name == name]
        candidates = [(rank, fixture) for rank, fixture in candidates if rank is not None]
        if not candidates:
            return ()
        nearest = max(rank for rank, _ in candidates)
        # Imported fixture registrations may shadow ancestor conftests; do not guess.
        file = self.extraction.files.get((test.side, test.path))
        if nearest[0] < 2 and file and name in file.exports:
            return ()
        return tuple(f for rank, f in candidates if rank == nearest)

    def markers(self, test):
        direct, indirect, requested, limits = set(), set(), set(), []
        refs = set(test.evidence_ids)
        for decorator in self.decorators(test):
            target = self.extraction.resolver.resolve(callee(decorator), test.side, test.path)
            if any(a.spread for a in decorator.arguments):
                limits.append("Expanded decorator arguments are not resolved")
                continue
            if target.status != "resolved":
                limits.append("Decorator binding is not statically resolved")
                continue
            if target.targets == ("external:pytest.mark.usefixtures",):
                for arg in positional(decorator):
                    if arg.kind != "literal" or not isinstance(arg.value, str):
                        limits.append("Dynamic usefixtures names")
                    else:
                        requested.add(arg.value)
                refs.update(decorator.evidence_ids)
            elif target.targets == ("external:pytest.mark.parametrize",):
                args = positional(decorator)
                kw = keywords(decorator)
                names = (
                    literal_names(args[0] if args else kw["argnames"])
                    if args or "argnames" in kw
                    else None
                )
                if names is None:
                    limits.append("Dynamic parametrization names")
                    continue
                option = kw.get("indirect")
                if option is None or (option.kind == "literal" and option.value is False):
                    direct.update(names)
                elif option.kind == "literal" and option.value is True:
                    indirect.update(names)
                else:
                    selected = literal_names(option)
                    if selected is None or not set(selected) <= set(names):
                        limits.append("Dynamic or invalid indirect parametrization")
                        indirect.update(names)
                    else:
                        indirect.update(selected)
                        direct.update(set(names) - set(selected))
                refs.update(decorator.evidence_ids)
        # Runtime pytest configuration and module-level marks are deliberately not interpreted.
        if any(
            b.side == test.side
            and b.path == test.path
            and b.target.text in {"pytestmark", "pytest_plugins"}
            for b in self.extraction.analysis.bindings
        ):
            limits.append(
                "Module pytestmark/pytest_plugins requires unsupported collection semantics"
            )
        return direct - indirect, requested | indirect, refs, limits

    def uses(self, test, parameters):
        direct, marked, refs, limits = self.markers(test)
        missing = self.missing_conftests(test)
        if missing:
            limits.append("Visible conftest inputs are unavailable: " + ", ".join(missing))
        parameters = set(parameters) - direct
        pending = [(name, test.symbol_id, "parameter", refs, ()) for name in sorted(parameters)]
        pending += [
            (name, test.symbol_id, "usefixtures", refs, ()) for name in sorted(marked - parameters)
        ]
        autouse = {f.name for f in self.fixtures if f.autouse and self.rank(f, test) is not None}
        pending += [
            (name, test.symbol_id, "autouse", refs, ())
            for name in sorted(autouse - parameters - marked - direct)
        ]
        uses = []
        owners = set()
        budget = min(self.extraction.analysis.options.max_graph_visits, 128)
        while pending:
            if len(uses) >= budget:
                limits.append("Fixture dependency traversal budget exceeded")
                break
            name, requester, kind, request_refs, chain = pending.pop(0)
            candidates = self.lookup(name, test)
            targets = tuple(sorted({f.symbol.symbol_id for f in candidates}))
            evidence = set(request_refs)
            for fixture in candidates:
                evidence.update(fixture.symbol.evidence_ids)
            if requester in targets or any(target in chain for target in targets):
                limits.append(
                    "Fixture dependency cycle or same-name override dependency is unresolved"
                )
                resolution = Resolution(
                    status="unknown",
                    reason="Fixture cycle or parent-override lookup is unsupported",
                )
                targets = ()
            else:
                resolution = (
                    Resolution(
                        status="candidate",
                        targets=targets,
                        reason="Nearest captured class/module/ancestor-conftest definition; runtime collection and plugin overrides are not proven",
                    )
                    if targets
                    else Resolution(
                        status="unknown",
                        reason="No visible captured fixture; may be a builtin, plugin, imported fixture or missing definition",
                    )
                )
            uses.append(
                FixtureUse(
                    name=name,
                    requested_by=requester,
                    kind=kind,
                    resolution=resolution,
                    evidence_ids=tuple(sorted(evidence)),
                )
            )
            if not targets:
                limits.append(f"Fixture {name!r} remains unresolved")
                continue
            if len(candidates) != 1 or any(f.uncertain for f in candidates):
                limits.append(f"Fixture {name!r} has duplicate or uncertain definitions")
            for fixture in candidates:
                owner = fixture.symbol.symbol_id
                if owner in owners:
                    continue
                owners.add(owner)
                # Dependency lookup uses the requesting test's visibility, as pytest does.
                for dependency in fixture.symbol.parameters:
                    if (
                        dependency
                        not in {
                            "self",
                            "cls",
                            *fixture.symbol.default_parameters,
                            *fixture.symbol.variadic_parameters,
                        }
                        and dependency not in direct
                    ):
                        pending.append(
                            (
                                dependency,
                                owner,
                                "dependency",
                                set(fixture.symbol.evidence_ids),
                                (*chain, owner),
                            )
                        )
        if any(f.uncertain and self.rank(f, test) is not None for f in self.fixtures):
            limits.append(
                "Visible fixture registration is conditional or has dynamic configuration"
            )
        if any(
            self.rank(Fixture(s, "", False, True), test) is not None
            for s in self.dynamic_definitions
        ):
            limits.append("Visible fixture has a dynamic registered name")
        return tuple(uses), owners, tuple(sorted(direct)), tuple(sorted(parameters)), limits

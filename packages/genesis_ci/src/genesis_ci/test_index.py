"""Static test, fixture and mock context. Never execute pytest or customer code."""

from collections import defaultdict

from genesis_contracts.intelligence import TestIndexEntry
from genesis_contracts.models import Resolution, TestDefinition, validate_evidence_refs
from genesis_contracts.validation import _refs

from .pytest_context.fixtures import FixtureCatalog
from .pytest_context.mocks import MockIndex


def _expressions(expr):
    yield expr
    for child in expr.children:
        yield from _expressions(child)
    for entry in expr.entries:
        if entry.key:
            yield from _expressions(entry.key)
        yield from _expressions(entry.value)
    for arg in expr.arguments:
        yield from _expressions(arg.value)


def index_tests(extraction, impact):
    ir = extraction.analysis
    result = []
    affected = set(impact.affected_symbols)
    code_symbols = {(s.side, s.symbol_id) for s in ir.symbols}
    catalog = FixtureCatalog(extraction)
    mocks = MockIndex(extraction, catalog)
    calls_by_owner, assertions_by_owner = defaultdict(list), defaultdict(list)
    for call in ir.calls:
        calls_by_owner[(call.side, call.symbol_id)].append(call)
    for assertion in ir.assertions:
        assertions_by_owner[(assertion.side, assertion.symbol_id)].append(assertion)
    fixture_ids = {(f.symbol.side, f.symbol.symbol_id) for f in catalog.fixtures}
    seen_tests = set()
    for symbol in ir.symbols:
        if symbol.kind != "function" or not symbol.qualified_name.split(".")[-1].startswith(
            "test_"
        ):
            continue
        key = (symbol.side, symbol.symbol_id)
        if key in seen_tests or key in fixture_ids:
            continue
        # Nested function definitions are not standalone pytest tests.
        parent = symbol.qualified_name.rpartition(".")[0]
        if (
            parent
            and (symbol.side, symbol.path + "#" + parent) in catalog.symbols
            and catalog.symbols[(symbol.side, symbol.path + "#" + parent)].kind != "class"
        ):
            continue
        seen_tests.add(key)
        calls = calls_by_owner[key]
        assertions = assertions_by_owner[key]
        called = {
            target
            for call in calls
            for target in call.target.targets
            if (symbol.side, target) in code_symbols
        }
        asserted = set()
        for assertion in assertions:
            for expr in _expressions(assertion.expression):
                value = (
                    extraction.resolver.value(expr, symbol.side, symbol.path)
                    if expr.kind == "name"
                    else expr
                )
                if value.kind == "await" and value.children:
                    value = value.children[0]
                if value.kind == "call":
                    resolution = extraction.resolver.resolve(
                        value.children[0], symbol.side, symbol.path
                    )
                    asserted.update(
                        target
                        for target in resolution.targets
                        if (symbol.side, target) in code_symbols
                    )
        injected = mocks.injected(symbol)
        parameters = [
            p
            for p in symbol.parameters
            if p
            not in {
                "self",
                "cls",
                *injected,
                *symbol.default_parameters,
                *symbol.variadic_parameters,
            }
        ]
        uses, fixture_owners, parameterized, fixture_parameters, limits = catalog.uses(
            symbol, parameters
        )
        fixture_called = {
            target
            for owner in fixture_owners
            for call in calls_by_owner[(symbol.side, owner)]
            for target in call.target.targets
            if (symbol.side, target) in code_symbols
        }
        mock_uses, mock_assertions, exception_assertions, assertion_refs = mocks.scan(
            symbol, symbol, set(fixture_parameters)
        )
        mock_uses = list(mock_uses)
        for owner in sorted(fixture_owners):
            fixture_symbol = catalog.symbols[(symbol.side, owner)]
            fixture_params = (
                set(fixture_symbol.parameters)
                - set(fixture_symbol.default_parameters)
                - set(fixture_symbol.variadic_parameters)
                - set(parameterized)
            )
            fixture_mocks, _, _, _ = mocks.scan(fixture_symbol, symbol, fixture_params)
            mock_uses.extend(fixture_mocks)
        mocked = {
            target
            for use in mock_uses
            for target in use.target.targets
            if (symbol.side, target) in code_symbols
        }
        targets = tuple(
            sorted(
                (called | asserted | fixture_called | mocked | fixture_owners)
                & {sid for side, sid in affected if side == symbol.side}
            )
        )
        association = (
            Resolution(
                status="candidate",
                targets=targets,
                reason="Static call/assertion, visible fixture or mock-target association; activation, runtime coverage and acceptance semantics are not proven",
            )
            if targets
            else Resolution(status="unknown", reason="No supported association to affected symbols")
        )
        refs = {
            *symbol.evidence_ids,
            *assertion_refs,
            *(ref for a in assertions for ref in a.evidence_ids),
            *(ref for c in calls for ref in c.evidence_ids),
            *(ref for u in uses for ref in u.evidence_ids),
            *(ref for u in mock_uses for ref in u.evidence_ids),
            *(
                ref
                for owner in fixture_owners
                for c in calls_by_owner[(symbol.side, owner)]
                for ref in c.evidence_ids
            ),
        }
        if any(use.target.status == "unknown" for use in mock_uses):
            limits.append("Some mock target configurations are dynamic or unavailable")
        result.append(
            TestIndexEntry(
                side=symbol.side,
                definition=TestDefinition(
                    test_id=symbol.side.value + "::" + symbol.symbol_id,
                    symbol_id=symbol.symbol_id,
                    assertions=tuple(a.expression.text for a in assertions)
                    + mock_assertions
                    + exception_assertions,
                    mocks=tuple(
                        sorted(
                            {u.api + "(" + (u.target_text or "unknown") + ")" for u in mock_uses}
                        )
                    ),
                    association=association,
                    evidence_ids=tuple(sorted(refs)),
                ),
                called_symbol_ids=tuple(sorted(called)),
                asserted_symbol_ids=tuple(sorted(asserted)),
                fixture_parameters=fixture_parameters,
                fixture_candidates=tuple(sorted(fixture_owners)),
                mock_targets=tuple(
                    sorted({u.target_text for u in mock_uses if u.target_text is not None})
                ),
                fixture_uses=uses,
                fixture_called_symbol_ids=tuple(sorted(fixture_called)),
                mocked_symbol_ids=tuple(sorted(mocked)),
                mock_uses=tuple(mock_uses),
                mock_assertions=mock_assertions,
                parameterized_names=parameterized,
                injected_mock_parameters=injected,
                limitations=tuple(sorted(set(limits))),
            )
        )
    validate_test_index(ir, result)
    return tuple(result)


def validate_test_index(ir, entries):
    refs = {ref.evidence_id: ref for ref in ir.evidence}
    symbols = {(s.side, s.symbol_id) for s in ir.symbols}
    validate_evidence_refs(
        snapshot_id=ir.snapshot_id, evidence=ir.evidence, evidence_ids=tuple(_refs(entries))
    )
    ids = [entry.definition.test_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate test IDs")
    for entry in entries:
        if (entry.side, entry.definition.symbol_id) not in symbols:
            raise ValueError("Test owner is absent on its side")
        if any(refs[ref].side != entry.side for ref in _refs(entry)):
            raise ValueError("Test context evidence crosses snapshot sides")
        targets = (
            *entry.called_symbol_ids,
            *entry.asserted_symbol_ids,
            *entry.fixture_candidates,
            *entry.fixture_called_symbol_ids,
            *entry.mocked_symbol_ids,
            *entry.definition.association.targets,
        )
        if any((entry.side, target) not in symbols for target in targets):
            raise ValueError("Test context target is absent on its side")
        for use in entry.mock_uses:
            if (entry.side, use.owner_symbol_id) not in symbols:
                raise ValueError("Mock configuration owner is absent on its side")
        for use in entry.fixture_uses:
            if (entry.side, use.requested_by) not in symbols or any(
                (entry.side, target) not in symbols for target in use.resolution.targets
            ):
                raise ValueError("Fixture context owner or target is absent")

"""Static mock configurations and mock-receiver assertions, never runtime patching."""

from genesis_contracts.intelligence import MockUse
from genesis_contracts.models import Resolution
from genesis_contracts.python import NameOrigin, ValueExpr

from .fixtures import callee, keywords, positional

PATCH_APIS = {"external:unittest.mock.patch", "external:unittest.mock.patch.object"}
MOCK_ASSERTIONS = {
    "assert_called",
    "assert_called_once",
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
    "assert_not_called",
    "assert_awaited",
    "assert_awaited_once",
    "assert_awaited_with",
    "assert_awaited_once_with",
    "assert_any_await",
    "assert_has_awaits",
    "assert_not_awaited",
}


def candidate(target):
    return (
        Resolution(
            status="candidate",
            targets=target.targets,
            reason="Static patch target configuration; activation, replacement, lookup location and assertion coverage are not proven",
        )
        if target.targets
        else target
    )


class MockIndex:
    def __init__(self, extraction, catalog):
        self.extraction = extraction
        self.catalog = catalog
        self.calls = {}
        self.bindings = {}
        for call in extraction.analysis.calls:
            self.calls.setdefault((call.side, call.symbol_id), []).append(call)
        for binding in extraction.analysis.bindings:
            self.bindings.setdefault((binding.side, binding.symbol_id), []).append(binding)

    def api(self, expr, owner, test, fixture_names):
        resolution = self.extraction.resolver.resolve(expr, owner.side, owner.path)
        if (
            resolution.status == "resolved"
            and len(resolution.targets) == 1
            and resolution.targets[0] in PATCH_APIS
        ):
            return resolution.targets[0].removeprefix("external:")
        # These names are only plugin/builtin candidates and cannot override a local fixture.
        if expr.kind == "attribute" and expr.children:
            base = expr.children[0]
            if (
                base.kind == "name"
                and base.text in fixture_names
                and base.text in {"mocker", "monkeypatch"}
                and not self.catalog.lookup(base.text, test)
                and not self.catalog.missing_conftests(test)
            ):
                if (base.text, expr.attribute) in {("mocker", "patch"), ("monkeypatch", "setattr")}:
                    bindings = self.bindings.get((owner.side, owner.symbol_id), ())
                    if not any(b.target.text == base.text for b in bindings):
                        return base.text + "." + expr.attribute
        return None

    def parse(self, expr, arguments, owner, test, fixture_names, evidence):
        api = self.api(expr, owner, test, fixture_names)
        if not api:
            return None
        args = [a.value for a in arguments if not a.name and not a.spread]
        kw = {a.name: a.value for a in arguments if a.name and not a.spread}
        if any(a.spread for a in arguments):
            return MockUse(
                owner_symbol_id=owner.symbol_id,
                api=api,
                target_text=None,
                target=Resolution(status="unknown", reason="Expanded patch arguments"),
                evidence_ids=tuple(evidence),
            )

        def resolve_value(value):
            return self.extraction.resolver.value(value, owner.side, owner.path)

        object_api = api == "unittest.mock.patch.object" or (
            api == "monkeypatch.setattr" and (len(args) >= 3 or "name" in kw)
        )
        first = args[0] if args else kw.get("target")
        name = (
            args[1] if len(args) > 1 else kw.get("attribute" if api.endswith(".object") else "name")
        )
        text = None
        target = Resolution(status="unknown", reason="Dynamic or unavailable patch target")
        refs = set(evidence)
        if first is not None:
            first = resolve_value(first)
            refs.update(first.evidence_ids)
            if object_api and name is not None:
                name = resolve_value(name)
                refs.update(name.evidence_ids)
                if (
                    name.kind == "literal"
                    and isinstance(name.value, str)
                    and name.value.isidentifier()
                ):
                    text = first.text + "." + name.value
                    target = self.extraction.resolver.resolve(
                        ValueExpr(
                            kind="attribute", text=text, children=(first,), attribute=name.value
                        ),
                        owner.side,
                        owner.path,
                    )
            elif first.kind == "literal" and isinstance(first.value, str):
                text = first.value
                if all(part.isidentifier() for part in text.split(".")) and "." in text:
                    target = self.extraction.resolver.resolve(
                        ValueExpr(
                            kind="name",
                            text=text,
                            origins=(NameOrigin(name=text, source="import"),),
                        ),
                        owner.side,
                        owner.path,
                    )
        return MockUse(
            owner_symbol_id=owner.symbol_id,
            api=api,
            target_text=text,
            target=candidate(target),
            evidence_ids=tuple(sorted(refs)),
        )

    def default_mock(self, expr, api):
        threshold = 2 if api.endswith(".object") else 1
        return (
            not any(a.spread for a in expr.arguments)
            and "new" not in keywords(expr)
            and "new_callable" not in keywords(expr)
            and len(positional(expr)) <= threshold
        )

    def injections(self, test):
        parameters = [
            p for p in test.parameters if p not in {"self", "cls", *test.variadic_parameters}
        ]
        result = []
        for decorator in reversed(test.decorators):
            api = self.api(callee(decorator), test, test, set())
            if api not in {"unittest.mock.patch", "unittest.mock.patch.object"}:
                continue
            args = positional(decorator)
            kw = keywords(decorator)
            threshold = 2 if api.endswith(".object") else 1
            if any(a.spread for a in decorator.arguments):
                break  # Unknown injection count prevents matching subsequent parameters.
            if "new" not in kw and len(args) <= threshold:
                if len(result) < len(parameters):
                    result.append((parameters[len(result)], self.default_mock(decorator, api)))
        return tuple(result)

    def injected(self, test):
        return tuple(name for name, _ in self.injections(test))

    def scan(self, owner, test, fixture_names):
        uses = []
        receivers = (
            {name: None for name, is_mock in self.injections(owner) if is_mock}
            if owner.symbol_id == test.symbol_id
            else {}
        )
        refs = set()
        assertions = []
        exception_assertions = []
        for decorator in owner.decorators:
            use = self.parse(
                callee(decorator),
                decorator.arguments,
                owner,
                test,
                fixture_names,
                decorator.evidence_ids,
            )
            if use:
                uses.append(use)
        for call in self.calls.get((owner.side, owner.symbol_id), ()):
            use = self.parse(
                call.callee, call.arguments, owner, test, fixture_names, call.evidence_ids
            )
            if use:
                uses.append(use)
        for binding in self.bindings.get((owner.side, owner.symbol_id), ()):
            value = binding.value
            context = (
                value.kind == "unknown"
                and value.reason == "Context manager __enter__ result is unknown"
            )
            if context and value.children:
                value = value.children[0]
            if value.kind != "call" or binding.target.kind != "name":
                continue
            api = self.api(value.children[0], owner, test, fixture_names)
            # A patcher assigned without entering its context is not the injected mock.
            if (
                (context and api in {"unittest.mock.patch", "unittest.mock.patch.object"})
                or (not context and api == "mocker.patch")
            ) and self.default_mock(value, api):
                if (
                    sum(
                        b.target.text == binding.target.text
                        for b in self.bindings.get((owner.side, owner.symbol_id), ())
                    )
                    == 1
                ):
                    receivers[binding.target.text] = binding.target.position
        # Reassignment invalidates decorator-injected receiver identity.
        for binding in self.bindings.get((owner.side, owner.symbol_id), ()):
            if binding.target.text in self.injected(owner):
                receivers.pop(binding.target.text, None)
        for call in self.calls.get((owner.side, owner.symbol_id), ()):
            expr = call.callee
            if (
                expr.kind == "attribute"
                and expr.attribute in MOCK_ASSERTIONS
                and expr.children
                and expr.children[0].kind == "name"
                and expr.children[0].text in receivers
                and (
                    receivers[expr.children[0].text] is None
                    or (
                        expr.position is not None
                        and expr.position > receivers[expr.children[0].text]
                    )
                )
            ):
                assertions.append(call.expression or expr.text)
                refs.update(call.evidence_ids)
        # A raises() factory call alone does not assert an exception.
        for call in self.calls.get((owner.side, owner.symbol_id), ()):
            if (
                call.context_manager
                and call.target.status == "resolved"
                and call.target.targets == ("external:pytest.raises",)
            ):
                exception_assertions.append(call.expression or call.callee.text)
                refs.update(call.evidence_ids)
        return (
            tuple(uses),
            tuple(sorted(set(assertions))),
            tuple(sorted(set(exception_assertions))),
            refs,
        )

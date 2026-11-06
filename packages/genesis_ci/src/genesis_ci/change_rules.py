"""Small evidence-backed comparisons; syntax changes never prove business failures."""

from collections import defaultdict

from genesis_contracts.models import Finding
from genesis_contracts.validation import _refs

from .rules import identity

CONFIGURATION = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "max_output_tokens",
        "max_completion_tokens",
        "seed",
        "parallel_tool_calls",
        "tool_choice",
    }
)


def literal_value(expr):
    if expr.kind == "literal":
        return ("literal", expr.value)
    if expr.kind in {"list", "tuple"}:
        children = tuple(literal_value(c) for c in expr.children)
        return (expr.kind, children) if all(c is not None for c in children) else None
    if expr.kind == "dict":
        pairs = tuple(
            (literal_value(e.key) if e.key else None, literal_value(e.value)) for e in expr.entries
        )
        return ("dict", pairs) if all(k is not None and v is not None for k, v in pairs) else None
    return None


def change_findings(extraction, patterns, tests):
    ir = extraction.analysis
    results = []

    def add(rule, key, statement, items, category="cost_risk", gap=None):
        refs = tuple(sorted({r for item in items for r in _refs(item)}))
        if refs:
            results.append(
                Finding(
                    finding_id=identity(rule, key),
                    category=category,
                    severity="info",
                    statement=statement,
                    basis=("code_fact",),
                    evidence_ids=refs,
                    condition="Observed supported static syntax only; no execution, business correctness, failure probability or cost judgment.",
                    gap=gap,
                )
            )

    parsed = {c.call_id: c for c in ir.calls}
    groups = defaultdict(lambda: defaultdict(list))
    for call in patterns.model_calls:
        groups[(call.symbol_id, call.provider, call.api)][call.side.value].append(call)
    available = {(c.side.value, c.path) for c in ir.coverage if c.syntax.status == "analyzed"}
    deleted = {f.base_path for f in ir.change_set.files if f.base_path and not f.head_path}
    for key, sides in sorted(groups.items()):
        before, after = sides["base"], sides["head"]
        path = key[0].split("#")[0]
        # Failed parses must not turn recognized calls into deletion findings.
        if ("base", path) not in available or (
            ("head", path) not in available and path not in deleted
        ):
            continue
        if len(before) > len(after):
            add(
                "sdk_sites_removed",
                key,
                f"{key[0]}: recognized {key[1]} {key[2]} call sites decrease from {len(before)} to {len(after)}.",
                (*before, *after),
                gap="No invocation savings or business removal is inferred; unsupported changed call shapes may no longer be recognized.",
            )
        if len(before) == len(after) == 1:
            old, new = before[0], after[0]
            a, b = dict(old.parameters), dict(new.parameters)
            for name in sorted(CONFIGURATION & a.keys() & b.keys()):
                x, y = literal_value(a[name]), literal_value(b[name])
                if x is not None and y is not None and x != y:
                    add(
                        "model_parameter_changed",
                        (key, name),
                        f"{key[0]}: literal {name} changes from {a[name].text} to {b[name].text}.",
                        (old, new),
                        gap="Output caps are not output token use; defaults and omitted values are not guessed.",
                    )
            old_prompt = tuple(literal_value(p) for p in old.prompt)
            new_prompt = tuple(literal_value(p) for p in new.prompt)
            if (
                old_prompt
                and new_prompt
                and all(p is not None for p in (*old_prompt, *new_prompt))
                and old_prompt != new_prompt
            ):
                add(
                    "prompt_content_changed",
                    key,
                    f"{key[0]}: known literal prompt content changed.",
                    (old, new),
                    gap="Literal content comparison only; no intent alignment, quality or token cost judgment.",
                )
            old_guards = tuple(
                (g.kind, g.selector.text, g.names) for g in parsed[old.call_id].branch_guards
            )
            new_guards = tuple(
                (g.kind, g.selector.text, g.names) for g in parsed[new.call_id].branch_guards
            )
            if (
                old.conditions != new.conditions
                or old_guards != new_guards
                or parsed[old.call_id].lexical_conditions != parsed[new.call_id].lexical_conditions
            ):
                add(
                    "model_call_conditions_changed",
                    key,
                    f"{key[0]}: lexical conditions surrounding the model call changed.",
                    (old, new),
                    gap="Conditions may encode approval, success or failure policies; their business meaning and path feasibility require review.",
                )
    # Explicit constructor retry counts only; no provider default or retry execution inference.
    retry_groups = defaultdict(lambda: defaultdict(list))
    constructors = {
        "external:openai.OpenAI",
        "external:openai.AsyncOpenAI",
        "external:anthropic.Anthropic",
        "external:anthropic.AsyncAnthropic",
    }
    for call in ir.calls:
        if (
            call.target.status != "resolved"
            or len(call.target.targets) != 1
            or call.target.targets[0] not in constructors
        ):
            continue
        if any(arg.spread or arg.name is None for arg in call.arguments):
            continue
        retry = [arg for arg in call.arguments if arg.name == "max_retries"]
        if len(retry) == 1:
            value = extraction.resolver.value(retry[0].value, call.side, call.path)
            if value.kind == "literal" and type(value.value) is int and value.value >= 0:
                retry_groups[(call.symbol_id, call.target.targets[0])][call.side.value].append(
                    (call, value)
                )
    for key, sides in sorted(retry_groups.items()):
        if len(sides["base"]) == len(sides["head"]) == 1:
            (old, a), (new, b) = sides["base"][0], sides["head"][0]
            if a.value != b.value:
                add(
                    "explicit_retry_limit_changed",
                    key,
                    f"{key[0]}: explicit SDK max_retries changes from {a.value} to {b.value}.",
                    (old, new, a, b),
                    gap="Retries occur only for eligible failures and SDK behavior; no default, actual attempts, latency or total calls are inferred.",
                )
    symbols = defaultdict(lambda: defaultdict(list))
    for symbol in ir.symbols:
        if symbol.kind == "function":
            symbols[symbol.symbol_id][symbol.side.value].append(symbol)
    code_refs = {r.evidence_id for r in ir.evidence if r.kind == "code"}
    model_ids = {c.call_id for c in patterns.model_calls}
    awaits = defaultdict(lambda: defaultdict(list))
    for call in ir.calls:
        if (
            call.call_id in model_ids
            or not call.awaited
            or call.loop_ids
            or call.conditions
            or call.lexical_conditions
        ):
            continue
        if set(call.target.targets) & {
            "external:asyncio.gather",
            "external:asyncio.wait",
            "external:asyncio.create_task",
            "external:asyncio.ensure_future",
        }:
            continue
        if code_refs.intersection(call.evidence_ids):
            awaits[call.symbol_id][call.side.value].append(call)
    added_paths = {f.head_path for f in ir.change_set.files if f.change_type == "added"}
    for sid, sides in sorted(awaits.items()):
        path = sid.split("#")[0]
        # Only an added-file diff proves zero base sites; unavailable parses do not.
        base_known = ("base", path) in available or path in added_paths
        if not base_known or ("head", path) not in available:
            continue
        before, after = sides["base"], sides["head"]
        if len(after) > len(before):
            add(
                "direct_nonmodel_await_sites_added",
                sid,
                f"{sid}: direct non-model await sites outside branches/loops increase from {len(before)} to {len(after)}.",
                (*before, *after),
                gap="Await syntax only; gather/task scheduling calls are excluded. Early exits and dynamic targets remain unknown; no latency or invocation count.",
            )
    conditions = defaultdict(list)
    for c in ir.facts.conditions:
        conditions[(c.side.value, c.symbol_id)].append(c)
    handlers = defaultdict(list)
    for h in ir.exception_handlers:
        handlers[(h.side.value, h.symbol_id)].append(h)
    changes = set(ir.change_set.changed_symbol_ids)
    catalog = {r.evidence_id: r for r in ir.evidence}
    for sid, sides in sorted(symbols.items()):
        if sid not in changes or len(sides["base"]) != 1 or len(sides["head"]) != 1:
            continue
        old, new = sides["base"][0], sides["head"][0]
        if not any(catalog[r].kind == "code" for r in new.evidence_ids):
            continue
        a, b = conditions[("base", sid)], conditions[("head", sid)]
        if sorted(c.expression for c in a) != sorted(c.expression for c in b):
            add(
                "condition_checks_changed",
                sid,
                f"{sid}: conditional checks change from {[c.expression for c in a]} to {[c.expression for c in b]}.",
                (old, new, *a, *b),
                category="behavior_intent",
                gap="A syntactic check change is not an intent deviation; no user requirement or missing approval is inferred.",
            )
        a, b = handlers[("base", sid)], handlers[("head", sid)]

        def signature(items):
            return sorted((h.exception, h.is_group, h.simple_fallthrough) for h in items)

        if signature(a) != signature(b):
            add(
                "exception_handlers_changed",
                sid,
                f"{sid}: exception handler structure changes from {signature(a)} to {signature(b)}.",
                (old, new, *a, *b),
                gap="Exception names are source expressions, not resolved runtime types; no exception matching or success-rate claim.",
            )
    for h in ir.exception_handlers:
        if (
            h.side == "head"
            and h.symbol_id in changes
            and h.simple_fallthrough
            and any(catalog[r].kind == "code" for r in h.evidence_ids)
        ):
            add(
                "exception_pass_handler",
                h.handler_id,
                f"{h.symbol_id}: handler for {h.exception} contains only pass/ellipsis.",
                (h,),
                gap="If this handler is entered it has no explicit re-raise; enclosing finally, except* unmatched groups and cancellation may still propagate. This may be intentional.",
            )
    # Absence is confined to this snapshot's supported test index.
    associated = defaultdict(list)
    for test in tests:
        if test.side == "head":
            for target in test.definition.association.targets:
                associated[target].append(test)
    eligible = []
    for sid, sides in sorted(symbols.items()):
        if sid not in changes or len(sides["head"]) != 1:
            continue
        symbol = sides["head"][0]
        if not any(catalog[r].kind == "code" for r in symbol.evidence_ids):
            continue
        matches = associated[sid]
        if not matches or not any(m.definition.assertions for m in matches):
            eligible.append((symbol, matches))
    for symbol, matches in eligible[:50]:
        add(
            "changed_test_assertions_unknown",
            symbol.symbol_id,
            f"{symbol.symbol_id}: "
            + (
                "no associated test definition was found in the supported static index."
                if not matches
                else "associated tests have no supported assertions in their own bodies."
            ),
            (symbol, *(m.definition for m in matches)),
            category="acceptance_tests",
            gap="Not a coverage or failed-test verdict. Plugins, dynamic fixtures, helpers and semantic assertions can be missed. Report shows at most 50 such functions.",
        )
    return tuple(results)

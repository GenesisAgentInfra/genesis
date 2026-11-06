"""Official SDK and hand-written loop patterns, derived only from A2 IR."""

from __future__ import annotations

from genesis_contracts.intelligence import AgentLoop, ModelCall, PatternAnalysis
from genesis_contracts.models import AgentLoopFact, CapabilityStatus, LoopBound, Resolution
from genesis_contracts.python import ValueExpr
from genesis_contracts.validation import _refs

from .dispatch import collect_dispatch, dictionary
from .python.extract import incomplete, unknown

_APIS = {
    "external:openai.OpenAI.responses.create": ("openai", "responses.create"),
    "external:openai.AsyncOpenAI.responses.create": ("openai", "responses.create"),
    "external:openai.OpenAI.chat.completions.create": ("openai", "chat.completions.create"),
    "external:openai.AsyncOpenAI.chat.completions.create": ("openai", "chat.completions.create"),
    "external:anthropic.Anthropic.messages.create": ("anthropic", "messages.create"),
    "external:anthropic.AsyncAnthropic.messages.create": ("anthropic", "messages.create"),
}


def missing(reason):
    return ValueExpr(kind="unknown", text="", reason=reason)


def _schemas(expr):
    if expr is None:
        return (), False
    if expr.kind not in {"list", "tuple"}:
        return (), True
    names = []
    unresolved = False
    for item in expr.children:
        schema = dictionary(item)
        if schema is None:
            unresolved = True
            continue
        if schema.get("type") and schema["type"].value == "function" and "function" in schema:
            schema = dictionary(schema["function"])
        name = schema.get("name") if schema else None
        if name and name.kind == "literal" and isinstance(name.value, str):
            names.append(name.value)
        else:
            unresolved = True
    return tuple(sorted(set(names))), unresolved


def _bound(loop, resolver, controls):
    expr = resolver.value(loop.expression, loop.side, loop.path)
    bound_refs = tuple(sorted({*loop.evidence_ids, *_refs(expr)}))
    if loop.kind == "while" and expr.kind == "literal" and expr.value is False:
        return LoopBound(
            status="unknown",
            reason="Statically false while condition; body is not expected to execute, and the public bound type has no zero value",
            evidence_ids=bound_refs,
        )
    if (
        loop.counter_progression is not None
        and not resolver.files[(loop.side, loop.path)].dynamic_namespace
    ):
        counter = loop.counter_progression
        distance = (
            counter.stop - counter.start if counter.step > 0 else counter.start - counter.stop
        )
        if counter.comparison in {"<=", ">="}:
            distance += 1
        count = max(0, (distance + abs(counter.step) - 1) // abs(counter.step))
        refs = tuple(sorted({*bound_refs, *counter.evidence_ids}))
        if count:
            return LoopBound(
                status="bounded",
                max_iterations=count,
                reason="Local literal integer counter with adjacent initialization and straight-line monotonic update; exceptions may stop early, runtime duration is unknown",
                evidence_ids=refs,
            )
        return LoopBound(
            status="unknown",
            reason="Counter starts outside its loop condition; zero body iterations expected, public bound type has no zero value",
            evidence_ids=refs,
        )
    if loop.kind == "for" and not loop.is_async:
        count = None
        if expr.kind in {"list", "tuple"}:
            count = len(expr.children)
        elif expr.kind == "call":
            target = resolver.resolve(expr.children[0], loop.side, loop.path)
            args = [
                resolver.value(arg.value, loop.side, loop.path)
                for arg in expr.arguments
                if not arg.name and not arg.spread
            ]
            if (
                target.targets == ("builtin:range",)
                and target.status == "resolved"
                and 1 <= len(args) <= 3
                and len(args) == len(expr.arguments)
                and all(
                    a.kind == "literal"
                    and isinstance(a.value, int)
                    and not isinstance(a.value, bool)
                    for a in args
                )
            ):
                try:
                    count = len(range(*(arg.value for arg in args)))
                except (ValueError, OverflowError):
                    pass
        if count is not None and count > 0:
            return LoopBound(
                status="bounded",
                max_iterations=count,
                reason="Literal finite iteration range; early exits may reduce actual iterations",
                evidence_ids=bound_refs,
            )
        if count == 0:
            return LoopBound(
                status="unknown",
                reason="Statically empty loop; loop body is not expected to execute",
                evidence_ids=bound_refs,
            )
    if loop.single_pass_exit_id:
        exit_control = next(
            (control for control in controls if control.control_id == loop.single_pass_exit_id),
            None,
        )
        if exit_control and not exit_control.conditions:
            return LoopBound(
                status="bounded",
                max_iterations=1,
                reason="Straight-line loop body ends in break/return; at most one body iteration per loop entry, not a termination or latency guarantee",
                evidence_ids=tuple(sorted({*bound_refs, *exit_control.evidence_ids})),
            )
    if loop.kind == "while" and expr.kind == "literal" and expr.value is True:
        return LoopBound(
            status="unbounded",
            reason="No static iteration-count bound; breaks, returns, exceptions, or external cancellation may still stop execution",
            evidence_ids=bound_refs,
        )
    return LoopBound(
        status="unknown",
        reason="Iteration bound depends on runtime state or unsupported syntax",
        evidence_ids=bound_refs,
    )


def detect_patterns(extraction):
    ir = extraction.analysis
    resolver = extraction.resolver
    models = []
    for call in ir.calls:
        identities = {_APIS[target] for target in call.target.targets if target in _APIS}
        if not identities:
            continue
        # Do not pick one provider among ambiguous alternatives.
        if len(identities) != 1 or any(target not in _APIS for target in call.target.targets):
            continue
        provider, api = next(iter(identities))
        args = {}
        ambiguous = False
        for arg in call.arguments:
            if arg.spread or not arg.name or arg.name in args:
                ambiguous = True
            elif arg.name:
                args[arg.name] = resolver.value(arg.value, call.side, call.path)
        model = args.get("model", missing("Model parameter not supplied or not statically known"))
        if ambiguous:
            model = missing("Expanded or ambiguous arguments can override model configuration")
        prompts = tuple(
            args[name] for name in ("input", "messages", "system", "instructions") if name in args
        )
        models.append(
            ModelCall(
                call_id=call.call_id,
                side=call.side,
                path=call.path,
                symbol_id=call.symbol_id,
                provider=provider,
                api=api,
                resolution=call.target,
                model=model,
                prompt=prompts,
                tools=args.get("tools"),
                parameters=tuple(sorted(args.items())),
                conditions=call.conditions,
                loop_ids=call.loop_ids,
                evidence_ids=call.evidence_ids,
            )
        )
    loops = []
    for loop in ir.loops:
        loop_calls = [
            call for call in models if loop.loop_id in call.loop_ids and call.side == loop.side
        ]
        if not loop_calls:
            continue
        schemas = set()
        schema_unknown = False
        for call in loop_calls:
            names, unresolved = _schemas(call.tools)
            schemas.update(names)
            schema_unknown |= unresolved
        controls = tuple(
            control for control in ir.loop_controls if loop.loop_id in control.loop_ids
        )
        stop_conditions = tuple(
            control.kind
            + " under "
            + (" / ".join(control.conditions) or "no lexical branch guard")
            + (("; " + "; ".join(control.caveats)) if control.caveats else "")
            for control in controls
            if control.kind != "continue"
        )
        if loop.kind == "while":
            if not (loop.expression.kind == "literal" and loop.expression.value is True):
                stop_conditions = (
                    "while condition is false: " + loop.expression.text,
                    *stop_conditions,
                )
        else:
            stop_conditions = ("iterator is exhausted: " + loop.expression.text, *stop_conditions)
        sites, dispatch_complete = collect_dispatch(extraction, loop_calls, loop)
        dispatch = {}
        for site in sites:
            dispatch.setdefault(site.tool_name, set()).update(site.target.targets)
        dispatch_refs = [ref for site in sites for ref in site.evidence_ids]
        reachable = tuple(
            sorted(
                {
                    target
                    for name, targets in dispatch.items()
                    if name in schemas
                    for target in targets
                }
            )
        )
        dispatch_names = tuple(sorted(dispatch))
        dispatch_targets = tuple(
            sorted({target for targets in dispatch.values() for target in targets})
        )
        tool_resolution = (
            Resolution(
                status="candidate",
                targets=reachable,
                reason="Schema names match static dictionary or response-derived branch candidates; model choice, helper roles and runtime dispatch are not predicted",
            )
            if reachable
            else unknown("Tool schemas or dispatch could not be paired")
        )
        dispatch_resolution = (
            Resolution(
                status="candidate",
                targets=dispatch_targets,
                reason="Static dictionary/branch candidates; runtime key, guards and mutation unknown",
            )
            if dispatch_targets
            else unknown(
                "No supported dictionary or response-derived literal branch dispatch found"
            )
        )
        model_names = tuple(
            sorted(
                {
                    call.model.value
                    for call in loop_calls
                    if call.model.kind == "literal" and isinstance(call.model.value, str)
                }
            )
        )
        refs = tuple(
            sorted(
                set(
                    (
                        *loop.evidence_ids,
                        *dispatch_refs,
                        *(ref for control in controls for ref in control.evidence_ids),
                        *(
                            ref
                            for call in loop_calls
                            if call.tools is not None
                            for ref in call.tools.evidence_ids
                        ),
                        *(ref for call in loop_calls for ref in call.evidence_ids),
                    )
                )
            )
        )
        loops.append(
            AgentLoop(
                side=loop.side,
                loop=AgentLoopFact(
                    loop_id=loop.loop_id,
                    symbol_id=loop.symbol_id,
                    call_ids=tuple(c.call_id for c in loop_calls),
                    model=Resolution(status="resolved", targets=model_names)
                    if model_names and all(c.model.kind == "literal" for c in loop_calls)
                    else unknown("At least one model name is dynamic"),
                    prompt_evidence_ids=tuple(
                        sorted(
                            {
                                ref
                                for call in loop_calls
                                for prompt in call.prompt
                                for ref in prompt.evidence_ids
                            }
                        )
                    ),
                    reachable_tools=tool_resolution,
                    dispatch=dispatch_resolution,
                    iteration_bound=_bound(loop, resolver, controls),
                    stop_conditions=stop_conditions,
                    evidence_ids=refs,
                ),
                dispatch_sites=sites,
                controls=controls,
                schema_complete=not schema_unknown,
                dispatch_complete=dispatch_complete,
                schema_tool_names=tuple(sorted(schemas)),
                dispatch_tool_names=dispatch_names,
                unmatched_schema_tools=tuple(sorted(schemas - set(dispatch))),
                unmatched_dispatch_tools=tuple(sorted(set(dispatch) - schemas)),
            )
        )
    partial = (
        ir.facts.coverage.status != "analyzed"
        or any(c.resolution.status != "resolved" for c in models)
        or any(
            loop.loop.iteration_bound.status == "unknown"
            or loop.loop.dispatch.status == "unknown"
            or not loop.schema_complete
            or not loop.dispatch_complete
            for loop in loops
        )
    )
    result = PatternAnalysis(
        model_calls=tuple(models),
        loops=tuple(loops),
        coverage=incomplete(
            "Candidate SDK receivers, unknown loop bounds, or unsupported tool dispatch remain"
        )
        if partial
        else CapabilityStatus(
            status="analyzed",
            analyzed_scope="Named official OpenAI/Anthropic clients; literal range/while, dictionary and response-derived literal branch candidates",
        ),
    )

    from .pattern_validation import validate_patterns

    validate_patterns(ir, result)
    return result

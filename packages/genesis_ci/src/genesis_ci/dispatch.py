"""Static tool-dispatch candidates derived from typed branches and response provenance."""

from genesis_contracts.intelligence import ToolDispatch
from genesis_contracts.models import Resolution

from .python.resolve import qualified


def dictionary(expr):
    if expr.kind != "dict":
        return None
    result = {}
    for entry in expr.entries:
        if (
            entry.key is None
            or entry.key.kind != "literal"
            or not isinstance(entry.key.value, str)
            or entry.key.value in result
        ):
            return None
        result[entry.key.value] = entry.value
    return result


class ResponseOrigins:
    """Bounded alias/iteration tracing; a candidate source, never runtime data flow."""

    def __init__(self, extraction, models):
        self.extraction = extraction
        self.refs = {r.evidence_id: r for r in extraction.analysis.evidence}
        self.models = {}
        self.mutated_scopes = {
            (b.side, b.path, b.symbol_id)
            for b in extraction.analysis.bindings
            if b.target.kind in {"attribute", "subscript"}
        }
        for call in models:
            ref = self.refs[call.evidence_ids[0]]
            self.models[(call.side, call.path, (ref.range.start_line, ref.range.start_column))] = (
                call
            )
        self.iterations = {}
        for loop in extraction.analysis.loops:
            if loop.target and loop.target.kind == "name":
                for origin in loop.target.origins:
                    if origin.source == "local":
                        self.iterations.setdefault(
                            (loop.side, loop.path, qualified(origin.name)), []
                        ).append(loop)

    def selector(self, expr, side, path, call):
        ids, refs, fields = self.trace(expr, side, path, call, frozenset(), [128])
        if "name" not in fields or not fields.intersection({"tool_calls", "output", "content"}):
            return (), ()
        return tuple(sorted(ids)), tuple(sorted(refs))

    def trace(self, expr, side, path, call, seen, budget):
        empty = (set(), set(), set())
        budget[0] -= 1
        if budget[0] < 0 or len(seen) > 24:
            return empty
        file = self.extraction.files.get((side, path))
        if (
            not file
            or file.dynamic_namespace
            or file.mutable_values
            or (side, path, call.symbol_id) in self.mutated_scopes
            or self.extraction.resolver.forward_binding(expr, side, path)
        ):
            return empty
        if expr.kind == "call":
            model = self.models.get((side, path, expr.position))
            if model and model.symbol_id == call.symbol_id:
                return {model.call_id}, set(model.evidence_ids), set()
            return empty
        if expr.kind in {"attribute", "subscript", "await"} and expr.children:
            ids, refs, fields = self.trace(expr.children[0], side, path, call, seen, budget)
            if expr.kind == "attribute":
                fields.add(expr.attribute)
            elif expr.kind == "subscript":
                fields.update(
                    c.value
                    for c in expr.children[1:]
                    if c.kind == "literal" and isinstance(c.value, str)
                )
            return ids, refs | set(expr.evidence_ids), fields
        if expr.kind != "name" or len(expr.origins) != 1 or expr.origins[0].source != "local":
            return empty
        key = (side, path, qualified(expr.origins[0].name))
        if key in seen:
            return empty
        bindings = self.extraction.resolver.bindings.get(key, [])
        iterations = self.iterations.get(key, [])
        if len(bindings) == 1 and not iterations:
            binding = bindings[0]
            # Conditional unique definitions remain candidates; multiple writes are rejected.
            ids, refs, fields = self.trace(binding.value, side, path, call, seen | {key}, budget)
            return ids, refs | set(binding.evidence_ids), fields
        if len(iterations) == 1 and not bindings and iterations[0].loop_id in call.loop_ids:
            loop = iterations[0]
            ids, refs, fields = self.trace(loop.expression, side, path, call, seen | {key}, budget)
            return ids, refs | set(loop.evidence_ids), fields
        return empty


def collect_dispatch(extraction, models, loop):
    """Return sites and dictionary completeness. Branch cases are intentionally partial."""
    tracer = ResponseOrigins(extraction, models)
    resolver = extraction.resolver
    sites = []
    complete, seen = True, False
    model_ids = {m.call_id for m in models}
    for call in extraction.analysis.calls:
        if call.side != loop.side or loop.loop_id not in call.loop_ids:
            continue
        if call.callee.kind == "subscript":
            seen = True
            table_expr = resolver.value(call.callee.children[0], call.side, call.path)
            table = dictionary(table_expr)
            if table is None:
                complete = False
                continue
            for name, value in table.items():
                target = resolver.resolve(value, call.side, call.path)
                complete &= target.status == "resolved"
                refs = tuple(
                    sorted(
                        {
                            *call.evidence_ids,
                            *value.evidence_ids,
                            *table_expr.evidence_ids,
                        }
                    )
                )
                sites.append(
                    ToolDispatch(
                        call_id=call.call_id,
                        kind="dictionary",
                        tool_name=name,
                        target=target,
                        selector=call.callee.text,
                        evidence_ids=refs,
                    )
                )
        if call.call_id in model_ids:
            continue
        for guard in call.branch_guards:
            sources, refs = tracer.selector(guard.selector, call.side, call.path, call)
            sources = tuple(i for i in sources if i in model_ids)
            if not sources:
                continue
            seen = True
            complete = False  # No claim of exhaustive branches/defaults, guards or helper roles.
            target = (
                Resolution(
                    status="candidate",
                    targets=call.target.targets,
                    reason="Callable guarded by a literal name from a model response; may be a helper within that branch",
                )
                if call.target.targets
                else call.target
            )
            for name in sorted(set(guard.names)):
                sites.append(
                    ToolDispatch(
                        call_id=call.call_id,
                        kind=guard.kind,
                        tool_name=name,
                        target=target,
                        selector=guard.selector.text,
                        model_call_ids=sources,
                        evidence_ids=tuple(
                            sorted({*refs, *guard.evidence_ids, *call.evidence_ids})
                        ),
                    )
                )
    return tuple(sites), seen and complete

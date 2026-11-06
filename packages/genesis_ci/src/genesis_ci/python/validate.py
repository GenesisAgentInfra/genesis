from genesis_contracts.models import validate_evidence_refs
from genesis_contracts.validation import _refs


def validate_python(analysis):
    validate_evidence_refs(
        snapshot_id=analysis.snapshot_id,
        evidence=analysis.evidence,
        evidence_ids=tuple(_refs(analysis)),
    )
    refs = {item.evidence_id: item for item in analysis.evidence}
    symbols = {(item.side, item.symbol_id) for item in analysis.symbols}
    for collection, identifier in (
        (analysis.bindings, "binding_id"),
        (analysis.calls, "call_id"),
        (analysis.loops, "loop_id"),
        (analysis.assertions, "assertion_id"),
        (analysis.loop_controls, "control_id"),
        (analysis.exception_handlers, "handler_id"),
    ):
        ids = [getattr(item, identifier) for item in collection]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate Python fact IDs")
        for item in collection:
            if (item.side, item.symbol_id) not in symbols:
                raise ValueError("Python fact owner is absent on its side")
            if any(
                refs[ref].side != item.side or refs[ref].path != item.path for ref in _refs(item)
            ):
                raise ValueError("Python fact references a different side or file")
    loops = {loop.loop_id: loop for loop in analysis.loops}
    for call in (*analysis.calls, *analysis.loop_controls):
        if any(
            loop not in loops
            or loops[loop].side != call.side
            or loops[loop].symbol_id != call.symbol_id
            for loop in call.loop_ids
        ):
            raise ValueError("Call loop references must share side and owner")
    controls = {control.control_id: control for control in analysis.loop_controls}
    for control in analysis.loop_controls:
        if not control.loop_ids or len(control.loop_ids) != len(set(control.loop_ids)):
            raise ValueError("Loop controls require unique affected loops")
        if control.kind in {"break", "continue"} and len(control.loop_ids) != 1:
            raise ValueError("break/continue must target one nearest loop")
    for loop in analysis.loops:
        if loop.single_pass_exit_id:
            control = controls.get(loop.single_pass_exit_id)
            if (
                control is None
                or control.kind not in {"break", "return"}
                or loop.loop_id not in control.loop_ids
            ):
                raise ValueError("Single-pass exit must reference its loop break or return")
    for symbol in analysis.symbols:
        if any(
            refs[ref].side != symbol.side or refs[ref].path != symbol.path for ref in _refs(symbol)
        ):
            raise ValueError("Symbol references a different side or file")

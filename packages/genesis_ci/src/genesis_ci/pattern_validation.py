"""Check local pattern provenance against the source IR before projecting to B4."""

from genesis_contracts.models import validate_evidence_refs
from genesis_contracts.validation import _refs


def validate_patterns(ir, patterns):
    validate_evidence_refs(
        snapshot_id=ir.snapshot_id, evidence=ir.evidence, evidence_ids=tuple(_refs(patterns))
    )
    calls = {call.call_id: call for call in ir.calls}
    loops = {loop.loop_id: loop for loop in ir.loops}
    refs = {ref.evidence_id: ref for ref in ir.evidence}
    models = {call.call_id: call for call in patterns.model_calls}
    if len(models) != len(patterns.model_calls):
        raise ValueError("Duplicate model call IDs")
    for model in patterns.model_calls:
        call = calls.get(model.call_id)
        if call is None or (call.side, call.path, call.symbol_id) != (
            model.side,
            model.path,
            model.symbol_id,
        ):
            raise ValueError("Model call does not match its source call")
    for item in patterns.loops:
        loop = loops.get(item.loop.loop_id)
        if loop is None or (loop.side, loop.symbol_id) != (item.side, item.loop.symbol_id):
            raise ValueError("Agent loop does not match its source loop")
        for ref in _refs(item):
            if refs[ref].side != loop.side or refs[ref].path != loop.path:
                raise ValueError("Pattern evidence must stay on its side and file")
        expected_controls = tuple(
            control for control in ir.loop_controls if loop.loop_id in control.loop_ids
        )
        if item.controls != expected_controls:
            raise ValueError("Pattern loop controls differ from source IR")
        for site in item.dispatch_sites:
            call = calls.get(site.call_id)
            if call is None or call.side != loop.side or loop.loop_id not in call.loop_ids:
                raise ValueError("Dispatch call is outside its loop")
            if site.kind != "dictionary" and not site.model_call_ids:
                raise ValueError("Branch dispatch requires model response provenance")
            if any(
                mid not in item.loop.call_ids or mid not in models for mid in site.model_call_ids
            ):
                raise ValueError("Dispatch provenance refers to an unrelated model call")

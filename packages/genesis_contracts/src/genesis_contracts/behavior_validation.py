"""Check behavior identity, scope, source containment and exact transmitted text."""

import re

from .models import behavior_id_for


def _contains(outer, inner):
    return (
        outer.start_line <= inner.start_line <= inner.end_line <= outer.end_line
        and inner.start_column is not None
        and inner.end_column is not None
        and (
            inner.start_line != outer.start_line or inner.start_column >= (outer.start_column or 0)
        )
        and (
            inner.end_line != outer.end_line
            or outer.end_column is None
            or inner.end_column <= outer.end_column
        )
    )


def _selected_text(excerpt, outer, inner):
    lines = [m.group() for m in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", excerpt) if m.group()]
    first, last = inner.start_line - outer.start_line, inner.end_line - outer.start_line
    if first < 0 or last >= len(lines):
        raise ValueError("behavior range exceeds its source excerpt")
    start = inner.start_column - ((outer.start_column or 0) if first == 0 else 0)
    end = inner.end_column - ((outer.start_column or 0) if last == 0 else 0)
    first_text = re.sub(r"(?:\r\n|\r|\n)$", "", lines[first])
    last_text = re.sub(r"(?:\r\n|\r|\n)$", "", lines[last])
    if start < 0 or start > len(first_text) or end < 0 or end > len(last_text):
        raise ValueError("behavior columns exceed their source excerpt")
    if first == last:
        return first_text[start:end]
    return lines[first][start:] + "".join(lines[first + 1 : last]) + last_text[:end]


def validate_behavior_view(context):
    view = context.behavior_view
    if view is None:
        return
    snapshot_id = (
        context.snapshot_id if hasattr(context, "snapshot_id") else context.snapshot.snapshot_id
    )
    ids = [unit.unit_id for unit in view.units]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate behavior unit_id")
    refs = {ref.evidence_id: ref for ref in context.evidence}
    excerpts = {item.evidence_id: item.text for item in getattr(context, "excerpts", ())}
    owners = {}
    for symbol in context.facts.functions:
        if symbol.kind == "function":
            owners.setdefault((symbol.side, symbol.symbol_id), []).append(set(symbol.evidence_ids))
    for unit in view.units:
        if view.version == "1" and any(
            op.kind in {"context_region", "exception_region"} for op in unit.operations
        ):
            raise ValueError("source regions require behavior-view version 2")
        if unit.unit_id != behavior_id_for(snapshot_id, unit):
            raise ValueError("behavior identity does not match its snapshot and content")
        scope = set(unit.scope_evidence_ids)
        if scope not in owners.get((unit.side, unit.symbol_id), ()):
            raise ValueError("behavior must retain its exact owning-function evidence")
        for ident in scope:
            ref = refs.get(ident)
            if ref is None or ref.kind != "code" or ref.side != unit.side or ref.path != unit.path:
                raise ValueError("behavior evidence must match code side and path")
        atoms = (*unit.conditions, *unit.operations, *((unit.result,) if unit.result else ()))
        for atom in atoms:
            if not set(atom.evidence_ids) <= scope:
                raise ValueError("behavior role evidence must belong to its function scope")
            for ident in atom.evidence_ids:
                if not _contains(refs[ident].range, atom.range):
                    raise ValueError("behavior role range is outside its source evidence")
                if (
                    excerpts
                    and _selected_text(excerpts[ident], refs[ident].range, atom.range) != atom.text
                ):
                    raise ValueError("behavior role text differs from frozen source")


def validate_behavior_projection(local, request):
    if request.behavior_view is None:
        return
    if local.behavior_view is None:
        raise ValueError("request invented a behavior view")
    before, after = local.behavior_view, request.behavior_view
    if any(unit not in before.units for unit in after.units):
        raise ValueError("request changed local behavior units")
    if after.version != before.version or after.limitations != before.limitations:
        raise ValueError("request changed behavior-view scope")
    if after.omitted_units != before.omitted_units + len(before.units) - len(after.units):
        raise ValueError("request changed behavior omission count")

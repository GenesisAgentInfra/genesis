"""Draft only from frozen, statically located candidate entries."""

import hashlib
import os
import uuid
from dataclasses import replace
from pathlib import Path

import yaml
from genesis_contracts.models import FlowDefinition, FlowDraftRequest, FlowsDocument
from genesis_contracts.validation import validate_flow_draft

from .context import ContextOptions, build_context
from .flow_candidates import candidate_graph


def prepare_draft(result, *, options: ContextOptions | None = None):
    registered = {entry for flow in result.local.flows for entry in flow.entries}
    groups, _, roots = candidate_graph(result.extraction.analysis, result.impact, registered)
    entries = []
    refs = {ref.evidence_id: ref for ref in result.local.evidence}
    for entry in sorted(roots):
        matching = [
            key
            for key in groups[entry][0].evidence_ids
            if refs[key].side == "head" and refs[key].kind == "code"
        ]
        if matching:
            entries.append((entry, matching[0]))
    selected = build_context(
        result.local,
        result.reader,
        request_id=uuid.uuid4().hex,
        options=replace(
            options or ContextOptions(), preferred_evidence_ids=tuple(key for _, key in entries)
        ),
    )
    allowed = {ref.evidence_id for ref in selected.evidence}
    entries = [(entry, key) for entry, key in entries if key in allowed]
    if not entries:
        raise ValueError("No supported unregistered head entry fits the selected context")
    request = FlowDraftRequest(
        request_id=selected.request_id,
        snapshot_id=selected.snapshot_id,
        candidate_entries=tuple(entry for entry, _ in entries),
        entry_evidence_ids=tuple(key for _, key in entries),
        evidence=selected.evidence,
        excerpts=selected.excerpts,
    )
    validate_flow_draft(request)
    return request, selected


def static_drafts(request: FlowDraftRequest) -> FlowsDocument:
    return FlowsDocument(
        flows=tuple(
            FlowDefinition(
                id="candidate-" + hashlib.sha256(entry.encode()).hexdigest()[:12],
                name=entry.split("#", 1)[1],
                status="draft",
                entries=(entry,),
                notes="Static entry candidate only. Review the business boundary before confirming; no acceptance criteria inferred.",
            )
            for entry in request.candidate_entries
        )
    )


def save_draft(document: FlowsDocument, output: Path, request, *, mode: str, reason: str):
    output = output.absolute()
    metadata = output.with_suffix(".metadata.json")
    if any(p.is_symlink() for p in (output, *output.parents, metadata)):
        raise ValueError("Draft output cannot use symlinks")
    if output.exists() or metadata.exists():
        raise ValueError("Draft output already exists; choose a new --output path")
    if output.name == "flows.yaml":
        raise ValueError("Write a separate draft file; review before editing flows.yaml")
    output.parent.mkdir(parents=True, exist_ok=True)
    import json

    values = {
        output: yaml.safe_dump(
            document.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        ),
        metadata: json.dumps(
            {
                "snapshot_id": request.snapshot_id,
                "mode": mode,
                "reason": reason,
                "request": request.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    for path, content in values.items():
        with path.open("x", encoding="utf-8") as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(content)

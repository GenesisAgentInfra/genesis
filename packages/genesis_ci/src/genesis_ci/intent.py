"""Classify explicitly selected intent files from the same immutable source snapshot."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from genesis_contracts.models import (
    CapabilityStatus,
    EvidenceSide,
    IntentItem,
    Limitation,
    LocalAnalysis,
    ReferenceRange,
    SourceExcerpt,
    validate_repo_path,
)
from genesis_contracts.validation import validate_local_analysis

from .context.filters import contains_secret, excluded_path
from .snapshot import FrozenSnapshotReader, SnapshotReader
from .source_snapshot import FrozenSourceSnapshot

IntentSourceType = Literal["task", "requirements", "agent_plan", "pr_description"]


def is_canonical_ci_origin(origin: str, source_type: IntentSourceType) -> bool:
    """Check location syntax and classification, not authorship or claim truth."""
    kind = {"task": "issues", "pr_description": "pull"}.get(source_type)
    if kind is None:
        return False
    match = re.fullmatch(
        r"https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/"
        rf"[A-Za-z0-9_][A-Za-z0-9_.-]{{0,99}}/{kind}/([1-9][0-9]{{0,9}})",
        origin,
    )
    return bool(match and int(match[1]) < 2**31)


@dataclass(frozen=True)
class IntentSource:
    path: str
    source_type: IntentSourceType

    def __post_init__(self) -> None:
        validate_repo_path(self.path)
        if self.source_type not in {"task", "requirements", "agent_plan", "pr_description"}:
            raise ValueError("unsupported intent source type")


@dataclass(frozen=True)
class IntentCollection:
    local: LocalAnalysis
    reader: FrozenSnapshotReader


def _conflict_key(text: str) -> tuple[str, bool]:
    negative = r"\b(?:do\s+not|does\s+not|must\s+not|should\s+not|don't|doesn't|never|not)\b|不应|不得|禁止|不能|不要|不"
    text = text.casefold()
    is_negative = bool(re.search(negative, text))
    text = re.sub(negative, "", text)
    text = re.sub(r"\b(?:must|should|do|does)\b", "", text)
    return re.sub(r"[\W_]+", "", text), is_negative


def collect_intents(
    local: LocalAnalysis,
    reader: SnapshotReader,
    source: FrozenSourceSnapshot,
    sources: tuple[IntentSource, ...],
    *,
    exclude_paths: tuple[str, ...] = (),
    max_file_chars: int = 120_000,
    max_items: int = 200,
) -> IntentCollection:
    """Add located intent items without changing snapshot identity or reading the worktree.

    Callers must capture these paths as ``SnapshotInput(kind='intent')`` before
    analysis. PR descriptions and agent plans remain claims regardless of text.
    Conflicts are conservative lexical candidates; both statements survive.
    """
    if max_file_chars < 1 or max_items < 1:
        raise ValueError("intent budgets must be positive")
    validate_local_analysis(local)
    if source.manifest != local.snapshot:
        raise ValueError("intent source differs from the analysis snapshot")
    if len({item.path for item in sources}) != len(sources):
        raise ValueError("intent source paths must be unique")
    refs = {item.evidence_id: item for item in local.evidence}
    excerpts = {key: reader.read_excerpt(key) for key in refs}
    intents = list(local.intents)
    limitations = list(local.limitations)
    files = {(item.side, item.path): item for item in source.manifest.files}

    def limited(code: str, message: str) -> None:
        limitations.append(Limitation(code=code, message=message, affects_completeness=True))

    for selected in sources:
        file = files.get((EvidenceSide.head, selected.path))
        if excluded_path(selected.path, exclude_paths):
            limited("intent_excluded", "An intent source was excluded by the outbound policy.")
            continue
        if file is None or file.kind != "intent":
            limited("intent_not_captured", "An intent source was not captured as head intent text.")
            continue
        text = source.read_text(EvidenceSide.head, selected.path)
        if contains_secret(text):
            limited("intent_excluded", "An intent source contained suspected credentials.")
            continue
        if len(text) > max_file_chars:
            limited("intent_over_budget", "An intent source exceeded the text budget.")
            continue
        # Match physical newlines as SnapshotReader does; Unicode separators are source characters.
        lines = re.split(r"\r\n|\r|\n", text)
        # Only the materializer's first-line label is provenance. Body headings cannot
        # replace it, and the path convention alone does not establish authenticity.
        origin = lines[0].removeprefix("# Source: ")
        if (
            re.fullmatch(r"genesis-ci-intent-[A-Za-z0-9_-]+/source-[0-8]\.md", selected.path)
            and lines[0].startswith("# Source: ")
            and is_canonical_ci_origin(origin, selected.source_type)
        ):
            origin_ref = source.evidence(
                EvidenceSide.head, selected.path, ReferenceRange(start_line=1, end_line=1)
            )
            refs[origin_ref.evidence_id] = origin_ref
            excerpts[origin_ref.evidence_id] = SourceExcerpt(
                evidence_id=origin_ref.evidence_id, text=lines[0]
            )
            origin_ids = (origin_ref.evidence_id,)
            limitations.append(
                Limitation(
                    code="intent_source_location",
                    message=f"Recorded GitHub source location: {origin}. The source label does not establish a user requirement.",
                    evidence_ids=origin_ids,
                    affects_completeness=False,
                )
            )
        before = len(intents)
        for line_number, line in enumerate(lines, 1):
            if len(intents) >= max_items:
                limited("intent_over_budget", "Intent item count exceeded the selected budget.")
                break
            if re.match(r"^\s*#{1,6}\s", line):
                continue
            point = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()
            if not point or re.fullmatch(r"[-=_*]{3,}|`{3,}.*|~{3,}.*", point):
                continue
            ref = source.evidence(
                EvidenceSide.head,
                selected.path,
                ReferenceRange(start_line=line_number, end_line=line_number),
            )
            refs[ref.evidence_id] = ref
            excerpts[ref.evidence_id] = SourceExcerpt(evidence_id=ref.evidence_id, text=line)
            identifier = hashlib.sha256(
                f"{selected.source_type}\0{ref.evidence_id}".encode()
            ).hexdigest()[:24]
            item = IntentItem(
                intent_id=f"intent_{identifier}",
                source_type=selected.source_type,
                nature="agent_claim"
                if selected.source_type in {"agent_plan", "pr_description"}
                else "user_intent",
                text=point,
                evidence_ids=(ref.evidence_id,),
            )
            if item.intent_id not in {existing.intent_id for existing in intents}:
                intents.append(item)
        if before == len(intents):
            limited("intent_empty", "An intent source contains no intent text.")

    if len(intents) > 1:
        limitations.append(
            Limitation(
                code="intent_conflict_scope",
                message="Local conflict checks only detect near-identical statements with opposite negation; other semantic disagreements require semantic review. No lexical match does not prove consistency.",
                affects_completeness=False,
            )
        )
    conflicts: dict[str, list[int]] = {}
    for index, item in enumerate(intents):
        key, _ = _conflict_key(item.text)
        if key:
            conflicts.setdefault(key, []).append(index)
    for key, indexes in conflicts.items():
        if len({_conflict_key(intents[index].text)[1] for index in indexes}) > 1:
            group = "lexical_" + hashlib.sha256(key.encode()).hexdigest()[:16]
            for index in indexes:
                intents[index] = intents[index].model_copy(update={"conflict_group": group})
            limited(
                "intent_conflict_candidate",
                "Potential lexical conflict between supplied intent statements; no source was preferred.",
            )
    if sources and not intents:
        limited("intent_missing", "No declared user intent or agent claim was supplied.")

    capabilities = local.capabilities
    has_user_intent = any(item.nature == "user_intent" for item in intents)
    if has_user_intent and capabilities.acceptance_tests.status == "analyzed":
        capabilities = capabilities.model_copy(
            update={
                "acceptance_tests": CapabilityStatus(
                    status="analyzed",
                    analyzed_scope="Declared intent and associated static head tests supplied for semantic review; execution/coverage not proven",
                )
            }
        )
    updated = local.model_copy(
        update={
            "intents": tuple(intents),
            "evidence": tuple(refs.values()),
            "limitations": tuple(dict.fromkeys(limitations)),
            "capabilities": capabilities,
        }
    )
    validate_local_analysis(updated)
    return IntentCollection(
        updated, FrozenSnapshotReader(tuple(refs.values()), tuple(excerpts.values()))
    )

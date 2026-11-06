"""Measure known textual prompt leaves; never substitute them for billable request tokens."""

from genesis_contracts.estimates import PromptMeasurement
from genesis_contracts.models import EstimateParameter
from genesis_contracts.validation import _refs

from .tokenizer import ASSET_HASH, MODELS, VERSION, count_fragments

MAX_CHARACTERS = 65536
MAX_TOTAL_CHARACTERS = 1048576
MAX_FRAGMENTS = 1024


def text_parts(expr, texts, gaps, refs, state):
    refs.update(expr.evidence_ids)
    if state[0] <= 0:
        gaps.add("Prompt traversal budget exceeded")
        return
    state[0] -= 1
    if expr.kind == "literal" and isinstance(expr.value, str):
        texts.append(expr.value)
    elif expr.kind in {"list", "tuple"}:
        for child in expr.children:
            text_parts(child, texts, gaps, refs, state)
    elif expr.kind == "dict":
        for entry in expr.entries:
            if entry.key is None or entry.key.kind != "literal":
                gaps.add("Expanded/dynamic prompt mapping")
                continue
            # Count text payloads only; roles, names, URLs and metadata are not prose.
            if entry.key.value in {"content", "text"}:
                text_parts(entry.value, texts, gaps, refs, state)
            elif entry.key.value not in {"role", "type"}:
                gaps.add("Non-text or unsupported prompt field: " + str(entry.key.value))
    else:
        gaps.add("Dynamic or unsupported prompt value")


def measure_prompts(patterns):
    result = []
    remaining = MAX_TOTAL_CHARACTERS
    for call in patterns.model_calls:
        texts, gaps, refs = [], set(), set(call.evidence_ids)
        state = [8192]
        for prompt in call.prompt:
            text_parts(prompt, texts, gaps, refs, state)
        model = (
            call.model.value
            if call.model.kind == "literal" and isinstance(call.model.value, str)
            else None
        )
        chars = sum(len(t) for t in texts)
        tokens = None
        supported = (
            call.provider == "openai" and model in MODELS and call.resolution.status == "resolved"
        )
        if not call.prompt:
            gaps.add("Prompt not supplied or not statically identified")
        if (
            supported
            and texts
            and chars <= MAX_CHARACTERS
            and chars <= remaining
            and len(texts) <= MAX_FRAGMENTS
        ):
            tokens = count_fragments(texts)
            remaining -= chars
        elif supported:
            gaps.add(
                "No known text fragments"
                if not texts
                else "Tokenizer text/fragment budget exceeded"
            )
        else:
            gaps.add(
                "No verified encoding for this provider/model/call resolution; character counts only"
            )
        gaps.add(
            "Fragment tokens exclude framing, tools, dynamic values, history and multimodal payloads; not total request tokens or a token lower bound"
        )
        result.append(
            PromptMeasurement(
                call_id=call.call_id,
                side=call.side,
                symbol_id=call.symbol_id,
                model=model,
                known_characters=chars,
                text_fragments=len(texts),
                fragment_tokens=tokens,
                encoding="o200k_base" if tokens is not None else None,
                tokenizer_version=VERSION if tokens is not None else None,
                encoding_sha256=ASSET_HASH if tokens is not None else None,
                unknowns=tuple(sorted(gaps)),
                evidence_ids=tuple(sorted(refs | set(_refs(call.model)))),
            )
        )
    return tuple(result)


def measurement_parameters(measurement):
    return (
        EstimateParameter(
            name="known_prompt_characters",
            value=measurement.known_characters,
            unit="characters",
            source="Frozen prompt text leaves, excluding role/metadata keys",
        ),
        EstimateParameter(
            name="prompt_fragment_tokens",
            value=measurement.fragment_tokens,
            unit="tokens across independent text fragments",
            source=(
                "tiktoken "
                + measurement.tokenizer_version
                + "; "
                + measurement.encoding
                + "; sha256:"
                + measurement.encoding_sha256
            )
            if measurement.fragment_tokens is not None
            else None,
            unknown_reason="No supported encoding or tokenizer budget exceeded"
            if measurement.fragment_tokens is None
            else None,
        ),
    )

import json
import socket
from dataclasses import replace
from decimal import Decimal

import pytest
import requests
import tiktoken
from genesis_ci.cost import estimate_costs, validate_cost_estimates
from genesis_ci.patterns import detect_patterns
from genesis_ci.pipeline import analyze_snapshot, save_analysis
from genesis_ci.pricing import REVISION, load_prices
from genesis_ci.prompt_metrics import measure_prompts
from genesis_ci.tokenizer import ASSET_HASH, count_fragments, encoding
from genesis_contracts.cost import CostInputs
from test_flow_candidates import run_changes
from test_python_analysis import analyze

PREFIX = "from openai import OpenAI\nclient=OpenAI()\n"


def source(model="gpt-4.1", prompt='"hello world"'):
    return PREFIX + f'def main(): return client.responses.create(model="{model}", input={prompt})\n'


def patterns(root, text):
    return detect_patterns(analyze(root, {"app.py": text}))


def head(metrics):
    return next(m for m in metrics if m.side == "head")


def scenarios(result, **overrides):
    entries = []
    for c in result.patterns.model_calls:
        entry = dict(
            call_id=c.call_id,
            model=c.model.value,
            input_tokens=1000,
            output_tokens=200,
            invocations=3,
            quantity_source="same synthetic workload",
            catalog_revision=REVISION,
        )
        entry.update(overrides)
        entries.append(entry)
    before = next(c for c in result.patterns.model_calls if c.side == "base")
    after = next(c for c in result.patterns.model_calls if c.side == "head")
    return CostInputs(
        format_version=2,
        snapshot_id=result.local.snapshot.snapshot_id,
        scenarios=tuple(entries),
        comparisons=(
            dict(
                comparison_id="same-workload",
                base_call_id=before.call_id,
                head_call_id=after.call_id,
                assumption="Same manually supplied input/output counts and invocations on both sides",
            ),
        ),
    )


def test_cold_tokenizer_has_no_network_registry_or_plugin_access(monkeypatch):
    encoding.cache_clear()

    def forbidden(*args, **kwargs):
        pytest.fail("Tokenizer attempted network or registry access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken, "encoding_for_model", forbidden)
    assert count_fragments(["hello world"]) == 2
    assert count_fragments([""]) == 0
    assert count_fragments(["你好，世界"]) > 0
    assert count_fragments(["<|endoftext|>"]) > 1
    encoding.cache_clear()


def test_asset_corruption_is_rejected(monkeypatch):
    import genesis_tokenizer as tokenizer

    encoding.cache_clear()
    monkeypatch.setattr(tokenizer, "ASSET_HASH", "0" * 64)
    with pytest.raises(ValueError, match="integrity"):
        count_fragments(["hi"])
    encoding.cache_clear()


def test_version_mismatch_is_rejected(monkeypatch):
    import genesis_tokenizer as tokenizer

    encoding.cache_clear()
    monkeypatch.setattr(tokenizer, "version", lambda name: "99")
    with pytest.raises(ValueError, match="version"):
        count_fragments(["hi"])
    encoding.cache_clear()


def test_text_measurement_never_becomes_billable_input(source_repo):
    found = patterns(source_repo, source())
    metric = head(measure_prompts(found))
    assert metric.known_characters == 11 and metric.fragment_tokens == 2
    assert metric.encoding_sha256 == ASSET_HASH and not metric.input_complete
    estimates = estimate_costs("unused", found, measurements=(metric,))
    assert estimates[0].amount is None
    assert next(p for p in estimates[0].parameters if p.name == "input_tokens").value is None
    assert next(p for p in estimates[0].parameters if p.name == "prompt_fragment_tokens").value == 2


@pytest.mark.parametrize("model", ["unknown-model", "gpt-4.1-FAKE"])
def test_unknown_models_do_not_guess_encoding(source_repo, model):
    metric = head(measure_prompts(patterns(source_repo, source(model))))
    assert metric.known_characters == 11 and metric.fragment_tokens is None


def test_anthropic_has_characters_only_even_with_openai_model_name(source_repo):
    text = 'from anthropic import Anthropic\nclient=Anthropic()\ndef main(): return client.messages.create(model="gpt-4.1",messages=[{"role":"user","content":"hello"}])\n'
    metric = head(measure_prompts(patterns(source_repo, text)))
    assert metric.known_characters == 5 and metric.fragment_tokens is None


@pytest.mark.parametrize("prompt", ["dynamic()", "[]"])
def test_dynamic_or_absent_text_is_not_zero_tokens(source_repo, prompt):
    metric = head(measure_prompts(patterns(source_repo, source(prompt=prompt))))
    assert metric.fragment_tokens is None
    assert metric.unknowns


def test_empty_literal_is_a_known_empty_fragment(source_repo):
    metric = head(measure_prompts(patterns(source_repo, source(prompt='""'))))
    assert metric.fragment_tokens == 0 and metric.text_fragments == 1
    assert not metric.input_complete


def test_structured_payload_counts_text_not_role_url_or_metadata(source_repo):
    text = (
        PREFIX
        + 'def main(user):\n    return client.chat.completions.create(model="gpt-4.1", messages=[{"role":"system","content":"hello world"},{"role":"user","content":user},{"role":"user","content":[{"type":"image_url","image_url":{"url":"secret-url"}}]}])\n'
    )
    metric = head(measure_prompts(patterns(source_repo, text)))
    assert metric.known_characters == 11 and metric.fragment_tokens == 2
    assert any("Dynamic" in reason for reason in metric.unknowns)
    assert any("image_url" in reason for reason in metric.unknowns)


@pytest.mark.parametrize("constant", ["MAX_CHARACTERS", "MAX_TOTAL_CHARACTERS", "MAX_FRAGMENTS"])
def test_tokenizer_budgets_preserve_character_evidence(source_repo, monkeypatch, constant):
    monkeypatch.setattr("genesis_ci.prompt_metrics." + constant, 0)
    metric = head(measure_prompts(patterns(source_repo, source())))
    assert metric.fragment_tokens is None and metric.known_characters == 11
    assert any("budget" in s for s in metric.unknowns)


def test_price_catalog_and_comparison_use_decimal_and_explicit_pairing(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    inputs = scenarios(result)
    priced = analyze_snapshot(snapshot, cost_inputs=inputs)
    delta = next(e for e in priced.local.estimates if e.estimate_id.startswith("cost_delta"))
    assert delta.amount == float(Decimal("0.00216") - Decimal("0.0108"))
    assert delta.amount < 0 and delta.price_date == "2026-11-04"
    assert len({r.side for r in priced.local.evidence if r.evidence_id in delta.evidence_ids}) == 2
    assert all(entry.effective_from is None for entry in load_prices().entries)


def test_missing_quantities_remain_unknown_even_with_known_price(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    priced = analyze_snapshot(snapshot, cost_inputs=scenarios(result, output_tokens=None))
    assert all(e.amount is None and e.unknowns for e in priced.local.estimates)


def test_unknown_catalog_model_is_null_not_free(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source("unknown")}, {"app.py": source("unknown", prompt='"new"')}
    )
    priced = analyze_snapshot(snapshot, cost_inputs=scenarios(result))
    assert all(e.amount is None for e in priced.local.estimates)
    assert any("verified price" in u for e in priced.local.estimates for u in e.unknowns)


def test_unknown_revision_and_mixed_price_sources_rejected(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    with pytest.raises(ValueError, match="revision"):
        analyze_snapshot(snapshot, cost_inputs=scenarios(result, catalog_revision="future"))
    with pytest.raises(ValueError, match="override"):
        scenarios(result, input_price_per_million="1")


@pytest.mark.parametrize("bad", ["snapshot", "model", "side", "missing", "duplicate"])
def test_scenario_pairing_and_identity_are_validated(source_repo, bad):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    data = scenarios(result).model_dump(mode="json")
    if bad == "snapshot":
        data["snapshot_id"] = "wrong"
    if bad == "model":
        data["scenarios"][0]["model"] = "wrong"
    if bad == "side":
        data["comparisons"][0]["head_call_id"] = data["comparisons"][0]["base_call_id"]
    if bad == "missing":
        data["scenarios"] = data["scenarios"][:1]
    if bad == "duplicate":
        data["comparisons"] *= 2
    with pytest.raises(ValueError):
        analyze_snapshot(snapshot, cost_inputs=CostInputs.model_validate(data))


def test_forged_amount_cannot_be_saved(source_repo, tmp_path):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    priced = analyze_snapshot(snapshot, cost_inputs=scenarios(result))
    fake = priced.local.estimates[0].model_copy(update={"amount": 123})
    local = priced.local.model_copy(update={"estimates": (fake, *priced.local.estimates[1:])})
    with pytest.raises(ValueError, match="deterministic"):
        save_analysis(replace(priced, local=local), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    output = tmp_path / "good"
    save_analysis(priced, output)
    assert json.loads((output / "prompt-measurements.json").read_text())
    validate_cost_estimates(
        priced.local.snapshot.snapshot_id,
        priced.patterns,
        priced.cost_inputs,
        priced.prompt_measurements,
        priced.local.estimates,
    )


def test_explicit_group_totals_and_unknown_members(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    data = scenarios(result).model_dump(mode="json")
    call = next(c for c in result.patterns.model_calls if c.side == "head")
    data["groups"] = [
        dict(
            group_id="request",
            call_ids=[call.call_id],
            assumption="One explicitly supplied request scenario",
        )
    ]
    priced = analyze_snapshot(snapshot, cost_inputs=CostInputs.model_validate(data))
    assert (
        next(e for e in priced.local.estimates if e.estimate_id.startswith("cost_group")).amount
        == 0.00216
    )
    data["scenarios"][1]["output_tokens"] = None
    # Find the scenario by identity rather than assuming base/head iteration order.
    for s in data["scenarios"]:
        if s["call_id"] == call.call_id:
            s["output_tokens"] = None
    unknown = analyze_snapshot(snapshot, cost_inputs=CostInputs.model_validate(data))
    assert (
        next(e for e in unknown.local.estimates if e.estimate_id.startswith("cost_group")).amount
        is None
    )


def test_group_cannot_mix_sides_or_duplicate_calls(source_repo):
    result, snapshot = run_changes(
        source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")}
    )
    data = scenarios(result).model_dump(mode="json")
    data["groups"] = [
        dict(
            group_id="mixed",
            call_ids=[c.call_id for c in result.patterns.model_calls],
            assumption="invalid",
        )
    ]
    with pytest.raises(ValueError, match="one side"):
        analyze_snapshot(snapshot, cost_inputs=CostInputs.model_validate(data))
    data["groups"][0]["call_ids"] *= 2
    with pytest.raises(ValueError, match="unique"):
        CostInputs.model_validate(data)


def test_boolean_quantity_rejected(source_repo):
    result, _ = run_changes(source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")})
    with pytest.raises(ValueError):
        scenarios(result, input_tokens=True)


def test_forged_measurements_rejected_before_output_creation(source_repo, tmp_path):
    result, _ = run_changes(source_repo, {"app.py": source()}, {"app.py": source("gpt-4.1-mini")})
    fake = result.prompt_measurements[0].model_copy(update={"fragment_tokens": 999})
    with pytest.raises(ValueError, match="measurements"):
        save_analysis(
            replace(result, prompt_measurements=(fake, *result.prompt_measurements[1:])),
            tmp_path / "bad",
        )
    assert not (tmp_path / "bad").exists()

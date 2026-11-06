# Synthetic static acceptance corpus

This page is for contributors checking analyzer behavior. For reviewing your own
application in a coding agent, start with [coding-agent setup](../../docs/coding-agents.md).

These ten cases follow the system design's first evaluation list, separately from the four fixed HTTP fixtures. Expected rule prefixes are proposed engineering labels, not human-approved business judgments or a semantic accuracy benchmark. Cases 08 and 10 are negative controls: claims alone do not create implementation facts, and a justified extra call is a factual cost signal rather than a defect.

After the locked workspace setup:

    uv run --all-packages --frozen python scripts/evaluate_analysis.py
    uv run --all-packages --frozen python scripts/evaluate_analysis.py --output .genesis/evaluation

Each case creates a temporary Git repository, freezes base/head, parses frozen bytes, verifies references and five report sections, checks required/forbidden structural findings, then removes its temporary working copy. Synthetic source is never imported or executed. An output run retains reports plus a frozen snapshot under each case directory. Output must be new.

For a short model-change demo:

    uv run --all-packages --frozen python scripts/evaluate_analysis.py --case 06-model-replacement --output .genesis/model-demo
    uv run --all-packages --frozen genesis analyze --snapshot .genesis/model-demo/06-model-replacement/snapshot --offline --output .genesis/model-replay

The analyzer exits 2 after writing its usable partial report. This is expected; semantic review has not run. Compare prompt-measurements.json and report.md. Known fragment tokens do not populate billable input_tokens. No key, customer SDK environment, tokenizer cache, network or provider call is needed during analysis (initial dependency installation needs packages).

## Explicit cost demo

Use the base/head call IDs and model values in patterns.json. Create scenario.json with the following JSON, replacing placeholders:

    {
      "format_version": 2,
      "snapshot_id": "<snapshot_id from local-analysis.json>",
      "scenarios": [
        {
          "call_id": "<base call_id>",
          "model": "gpt-4.1",
          "input_tokens": 1000,
          "output_tokens": 200,
          "invocations": 3,
          "quantity_source": "Synthetic workload, not measured production usage",
          "catalog_revision": "openai-text-2026-11-04"
        },
        {
          "call_id": "<head call_id>",
          "model": "gpt-4.1-mini",
          "input_tokens": 1000,
          "output_tokens": 200,
          "invocations": 3,
          "quantity_source": "Same synthetic workload",
          "catalog_revision": "openai-text-2026-11-04"
        }
      ],
      "comparisons": [
        {
          "comparison_id": "model-change",
          "base_call_id": "<base call_id>",
          "head_call_id": "<head call_id>",
          "assumption": "Same explicitly supplied workload on both versions"
        }
      ],
      "groups": [
        {
          "group_id": "head-request",
          "call_ids": ["<head call_id>"],
          "assumption": "Only this scenario belongs to the example request"
        }
      ]
    }

    uv run --all-packages --frozen genesis analyze --snapshot .genesis/model-demo/06-model-replacement/snapshot --offline --cost-inputs /path/to/scenario.json --output .genesis/model-priced

Expected conditional amounts: base 0.0108 USD, head 0.00216 USD, difference -0.00864 USD. These are code-calculated standard uncached text scenarios at the named catalog revision, not actual bills, inferred invocation counts or current-price guarantees. Missing quantity/price leaves amount null. Existing v1 explicit-price scenarios remain supported.

## Human and semantic review

Read each case's semantic_review and compare the same frozen inputs when evaluating the hosted semantic analyzer or a coding agent. Record reviewer, proposed/accepted/rejected labels, false positives, missed items and review time, always with numerators/denominators. The runner does not call a model, classify plan text as user intent or claim that approval/notification changes violate requirements. When intent is supplied, its classification remains separate from the hosted semantic comparison.

Real customer samples need separate consent and storage; none are included. Passing 10/10 static cases does not establish the proposed 80% human semantic-quality threshold or production readiness.

# Synthetic business case: submit a report, then notify Slack

This is a developer-owned example of the business case in system design §12. It is not a customer repository, a live Slack integration, or evidence of semantic-model quality. The application files are `.txt` templates so test discovery cannot accidentally import them.

The user asks for a Slack notification after a successful submission, with no success notification after a failed submission. Approval denial must still stop submission. The candidate adds a model-generated summary and waits for Slack before returning, but does not inspect the submission result before notifying. Its PR description claims that failures do not notify. The one existing test only checks a successful return value.

The example gives reviewers three questions to investigate:

- Does the failure path actually satisfy the explicit requirement?
- Is the extra model summary wanted, and what additional waiting/cost does it introduce?
- Which failure and approval cases still need test assertions?

These are review questions and facts visible in the synthetic source. The offline analyzer does not claim it has resolved the semantic questions or run the tests.

## Run locally

This is a developer example. For reviewing your application from an agent, see
[coding-agent setup](../../docs/coding-agents.md). Install the checkout with
`uv sync --all-packages --group dev --frozen` as described in
[CONTRIBUTING.md](../../CONTRIBUTING.md). Choose a new output directory:

```sh
uv run --all-packages --frozen python examples/submit-report/run.py \
  --output /tmp/genesis-submit-report-example
```

The script copies owned text templates into a new private repository, creates base/head Git commits, and invokes the installed `genesis analyze --offline` with the task and PR description. It does not install application dependencies, import the application, execute its tests, or call a model/Slack/provider. The integration module raises `SYNTHETIC_CODE_MUST_NOT_EXECUTE` if someone accidentally imports it; successful analysis must only read it.

Exit code 0 from the example runner means local artifacts were delivered. The generated report is intentionally `partial`/`offline`; the underlying CLI returns 2 for this normal offline outcome.

## Read the result

- `report/summary.md`: readable Chinese explanation of the same findings and limits; start here.
- `report/report.md`: five sections within each explicit flow, plus an unassigned group. Evidence links lead to anchors in the same document. No raw source excerpt appendix is included.
- `report/report.json`: the unchanged public report schema and all findings/estimates/statuses.
- `report/local-analysis.json`: classified task/PR intent, confirmed flow map, static test definitions and other local facts.
- `report/snapshot/`: the exact frozen source bytes used by analysis. Treat this as private source-bearing data.
- `case.json`: identifies the synthetic case and the base/head revisions.

The report distinguishes `code_fact`, `conditional_estimate`, `user_intent`, `agent_claim` and semantic inference. Unknown model pricing, dynamic input length, latency or runtime behavior stay unknown. “No result in this group” never means the flow passed acceptance.

To also produce a private document with digest-verified frozen excerpts:

```sh
uv run --all-packages --frozen python examples/submit-report/run.py \
  --output /tmp/genesis-submit-report-with-source \
  --include-source-evidence
```

This adds `report/review-with-source.md`, which contains original code and intent text. The default Action artifact list does not upload it. Before/after tables align only the same path and evidence type; they do not infer renamed-function equivalence or invent a missing side.

Model-backed analysis is a separate, explicitly approved operation using the hosted Genesis service. The runner deliberately remains offline and does not synthesize model findings. The four pinned contract fixtures remain the separate deterministic mock examples.

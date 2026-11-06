# Genesis CLI

Review a Python code change before you merge it. Genesis freezes the local Git
inputs, extracts static evidence, and explains behavior changes, affected paths,
cost/wait/failure risks, available tests, and verification suggestions. It does
not execute your application or tests.

Start with `summary.md` for the readable Chinese report. `report.md` retains
detailed statuses and evidence; `report.json` is the structured result. All three
come from the same analysis.

## Install from source

Requires Git, Python 3.12+, and uv 0.13.7. The packages are not released on PyPI.
Clone the client outside the application you want to review:

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
```

Use `uv run --project /absolute/path/to/genesis-cli --package genesis-ci --no-dev
--frozen genesis ...` from any directory. The examples below assume you are in
the `genesis-cli` checkout. No private repository, server package, model key or
database is required to install the client.

## First review: no signup or auth required

Point `--repo` at your application's Git checkout:

```sh
uv run --package genesis-ci --no-dev --frozen genesis analyze \
  --repo /absolute/path/to/your-app --base main --head HEAD
```

With no personal connection settings, the CLI uses the official shared trial at
`https://semantic-api-production.up.railway.app`. You do not need a Genesis key,
model-provider key, or `genesis auth`. It shows the destination and selected
outbound material, including source excerpts, and asks before any network call.
Answer `y` to send, or `n` to keep a local partial report.

`base` is the earlier revision; `head` is the candidate revision. Omit `--head`
to include tracked working-tree changes; add `--include-untracked` for new files.
Choose revisions with a real diff. To inspect local working-tree changes from
inside your application, use:

```sh
uv run --project /absolute/path/to/genesis-cli --package genesis-ci --no-dev --frozen \
  genesis analyze --repo . --base HEAD
```

Add `--preview-only` to inspect the prepared payload without sending. Add
`--offline` for static analysis only, without credentials or network access.
Declining upload or using offline/preview mode produces a usable partial report
and exits with code **2**, which is expected.

Without an explicit output path, reports are saved in a new directory under
`.genesis/analyses/` in the target repository. The command prints its location.
Read `summary.md` first. Local artifacts can contain source code; do not commit
that directory or upload the entire directory as a CI artifact.

The shared trial starts with **10,000 admitted requests across all users**, not
10,000 per user. Analysis and optional flow drafting share this lifetime pool;
admitted failures also count. It does not reset daily, and availability is not
guaranteed. Exhaustion or revocation leaves a local partial report with an
explanation; the CLI does not automatically retry. The intentionally public
trial identity is bundled with the client and can be revoked by the operator.
Personal credentials are never written into the project or replaced by it.

## Optional: use your own Genesis key or service

For separate access, request a personal Genesis key and service origin from the
project operator. Personal key provisioning is currently manual; there is no
self-serve signup. Do not post personal keys in issues.
A Genesis key is separate from a model provider key; provider credentials remain
on the service. Your application does not need an embedded SDK.

```sh
uv run --package genesis-ci --no-dev --frozen genesis auth   --service-url https://YOUR-GENESIS-SERVICE
uv run --package genesis-ci --no-dev --frozen genesis analyze   --repo /absolute/path/to/your-app --base main --head HEAD
```

`auth` prompts without echoing and saves an origin-bound key outside the project.
It does not contact the server to validate the key; the first analysis does.
Explicit environment settings and saved credentials take priority over the
shared trial. Invalid or incomplete personal configuration does not silently
fall back to trial. A custom service URL requires its own key; the bundled trial
key is never selected for a custom origin. See [configuration](docs/usage.md) for
the complete precedence rules. The GitHub Action remains offline without an
explicit key and does not automatically consume shared trial quota.

Task/requirements/PR documents and `.genesis/flows.yaml` are optional. Without
them Genesis reviews code changes and conditional risks; it does not invent
requirements or claim requirement compliance. Optional `--task`, `--requirements`,
`--plan` and `--pr-description` accept repository-relative files.

## Reports and limits

- **Business changes:** what can behave differently, with before/after evidence.
- **Affected paths:** associated callers, code paths and supplied flow maps.
- **Cost/wait/failure:** conditional risks and supported static estimates.
- **Tests:** related tests and what their source appears to check; never a claim
  that tests have passed.
- **Verification:** suggested checks and missing evidence.

Exit 0 means the declared analysis completed, 2 means a usable partial report,
and 1 means the requested result could not be produced. Completion is not
approval of a change. Dynamic dispatch, unsupported Python constructs, omitted
context, and service failures can limit the result.

Structured business comparisons require a compatible service; capability
negotiation preserves legacy report v0.1.0 and enables v0.2.0 when supported.

## More

- [Configuration and data handling](docs/usage.md)
- [GitHub Action](docs/github-action.md)
- [Runnable synthetic business example](examples/submit-report/README.md)
- [Client development and compatibility](CONTRIBUTING.md)
- [Repository ownership](docs/repository-boundary.md)
- [Versioned report schemas](https://github.com/GenesisAgentInfra/code-intelligence-protocol)

## License

Original Genesis CLI code is licensed under [Apache-2.0](LICENSE). You may use,
modify and redistribute it, including commercially, subject to the license terms.
The license does not grant trademark rights or access to the separately operated
Genesis service. The private service implementation is not part of this repository.

Bundled third-party components retain their own licenses, including the MIT
notice for the tokenizer assets. See [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

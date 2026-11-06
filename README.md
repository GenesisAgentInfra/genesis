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

## First review: local only

Point `--repo` at your application's Git checkout:

```sh
uv run --package genesis-ci --no-dev --frozen genesis analyze   --repo /absolute/path/to/your-app --base main --head HEAD --offline
```

`base` is the earlier revision; `head` is the candidate revision. Omit `--head`
to include tracked working-tree changes; add `--include-untracked` for new files.
Choose revisions with a real diff. No upload or LLM call occurs in offline mode.
An offline report is partial and exits with code **2**, which is expected.

Without an explicit output path, reports are saved in a new directory under
`.genesis/analyses/` in the target repository. The command prints its location.
Read `summary.md` first. Local artifacts can contain source code; do not commit
that directory or upload the entire directory as a CI artifact.

## Semantic review with the Genesis service

Request a Genesis key and service origin from the project operator. Provisioning
is currently manual; there is no self-serve signup. Do not post keys in issues.
A Genesis key is separate from a model provider key; provider credentials remain
on the service. Your application does not need an embedded SDK.

```sh
uv run --package genesis-ci --no-dev --frozen genesis auth   --service-url https://YOUR-GENESIS-SERVICE
uv run --package genesis-ci --no-dev --frozen genesis analyze   --repo /absolute/path/to/your-app --base main --head HEAD
```

`auth` prompts without echoing and saves an origin-bound key outside the project.
It does not contact the server to validate the key; the first analysis does.
The analysis previews selected outbound material and asks for permission before
sending. This material includes actual source excerpts as well as static facts.
Use `--preview-only` to save and inspect the selected request without sending.

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

## License status

This is a local publication candidate. The proposed source-available terms in
[LICENSE-DRAFT.md](LICENSE-DRAFT.md) are under owner review and are not an
operative license. It is not published as MIT or OSI-approved open source.
Third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

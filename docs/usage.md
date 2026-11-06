# Client usage and data handling

## Credentials

`genesis auth --service-url https://YOUR-GENESIS-SERVICE` saves the key to
`$XDG_CONFIG_HOME/genesis/credentials.json`, or `~/.config/genesis/credentials.json`.
The directory/file use owner-only permissions. Do not put a key in source control.
For CI use a repository secret exposed as `GENESIS_API_KEY` and an explicit trusted
`GENESIS_SERVICE_URL`. A key saved for one origin is not sent to another origin.

The service origin is selected by `--service-url`, then `GENESIS_SERVICE_URL`,
then saved credentials. Repository-controlled configuration cannot choose the
recipient of credentials. Service URLs require HTTPS outside loopback.

## Optional local configuration

Create `.genesis/config.toml` only if you need custom context limits:

```toml
exclude = ["private_data/**", "secrets/**"]
input_token_budget = 40000
max_excerpt_chars = 12000
max_excerpts = 80
```

Exclusion patterns and secret filters reduce accidental transmission but are not
a guarantee that all secrets are detected. Inspect `--preview-only` output when
working with sensitive code. This output is itself sensitive local material.

## Online requests

The CLI freezes base/head/worktree source locally, parses it, then selects a
bounded context. Requests include selected actual source excerpts, their paths
and revision/evidence identifiers, static facts and behavior units, and any
selected intent/review documents. The whole Git repository is not uploaded.

An online analysis needs explicit interactive consent. `--accept-send` grants
that consent for automation; configure it only for a trusted repository and
service. Fork PRs and unverified PR contexts stay offline in the Action.

Offline mode makes no semantic request. No mode executes application code or
tests. Token counts and the dated bundled price catalog have explicit limits;
they do not predict arbitrary model billing.

Local analyses contain more than the three reports: frozen source, excerpts and
request/audit artifacts can be present. Keep `.genesis/` out of Git and share
reports only after reviewing their contents. Reports can themselves describe
private paths and behavior. Service retention is governed by the service
operator; the CLI source alone does not establish a hosted retention policy.

## Optional flow map

`genesis flows init --repo /path/to/app --offline` writes a separate draft and
exits 2. Review its entries before creating a confirmed `.genesis/flows.yaml`.
It does not invent acceptance criteria or overwrite a confirmed map. No flow
map is required for basic change review.

## Update

From the client checkout, fetch the desired reviewed revision and run
`uv sync --package genesis-ci --no-dev --frozen` again. For reproducible CI,
pin the repository/Action to a reviewed full commit SHA.

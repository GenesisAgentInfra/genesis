# Client usage and data handling

For everyday use inside Codex or Claude Code, start with
[coding-agent setup](coding-agents.md). This page is the CLI/configuration
reference an agent or terminal user can consult. Bare `genesis` examples assume
the CLI is on PATH; source installs can prefix them with
`uv run --project /absolute/path/to/genesis-cli --package genesis-ci --no-dev --frozen`.

## Agent integration commands

```sh
genesis agent install --agent codex
genesis agent install --agent claude
genesis agent install --agent both --scope project --repo /absolute/path/to/app
genesis agent status --agent both
genesis agent install --agent codex --update
```

Choose user scope (default) or project scope deliberately. `--dry-run` inspects
the installation plan; `status` checks files without writing. Setup does not
run analysis or authorize uploads. See the [agent guide](coding-agents.md) for
discovery, natural-language examples, updates and removal.

## Default shared trial

With no connection settings, `genesis analyze --repo /path/to/app --base HEAD`
uses the official shared trial at `https://semantic-api-production.up.railway.app`.
No `auth` is required. The CLI shows the destination and bounded payload and asks
for upload consent before capability discovery or analysis. `--preview-only`
saves the payload locally; `--offline` skips credential resolution and networking.

The dedicated trial credential is intentionally public and packaged in
`genesis_ci/assets/public-trial.json`. It is not a model-provider or personal key.
The initial 10,000 admitted requests are shared by every trial user, including
analysis and flow drafting, with no daily reset. Failed admitted requests count.
The operator can revoke or change the trial; there is no per-user guaranteed
allocation. On failure, the CLI keeps a partial report and does not retry.

## Optional personal credentials

Shared trial and personal keys both access the Genesis team's hosted private
service. The public CLI repository does not distribute a server for self-hosting.
Request a personal Genesis key from the Genesis team, then run:

```sh
genesis auth --service-url https://semantic-api-production.up.railway.app
```

The command prompts for your key without echoing it and saves it to
`$XDG_CONFIG_HOME/genesis/credentials.json`, or `~/.config/genesis/credentials.json`.
The directory/file use owner-only permissions. Do not put personal keys in source control.
For CI use a repository secret exposed as `GENESIS_API_KEY` and an explicit trusted
`GENESIS_SERVICE_URL`. A key saved for one origin is not sent to another origin.
Set `GENESIS_SERVICE_URL` to `https://semantic-api-production.up.railway.app`.

The URL override is retained for development/testing and endpoint changes. It
does not imply that a self-hosted Genesis server is included or offered. Normal
users use the official hosted endpoint above.

Connection precedence:

1. `--service-url` overrides `GENESIS_SERVICE_URL`, then the saved service URL.
2. `GENESIS_API_KEY` overrides the saved key. With only this variable and no
   saved URL, it targets the official service using your key, not the trial key.
3. A saved key is usable only for its saved origin. An explicit URL alone never
   enables trial, even if it is the official URL; supply a key for that URL.
4. Only when no URL/key settings and no credential file exist does the CLI
   select the bundled official trial. It does not save or overwrite credentials.

Empty environment values, incomplete or malformed saved credentials, and
authentication/quota failures do not fall back to trial. An explicit URL plus
environment key can override a broken saved credential file. To intentionally
return to trial, unset both environment variables and move your saved credential
file to a safe location outside the repository; keep personal keys private.

Repository-controlled configuration cannot choose the recipient of credentials.
Service URLs require HTTPS outside loopback, and redirects are not followed.

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
service. Fork PRs and unverified PR contexts stay offline in the Action. The
Action also remains offline without an explicit `GENESIS_API_KEY`; it does not
automatically opt in to shared trial.

Offline mode makes no semantic request. No mode executes application code or
tests. Token counts and the dated bundled price catalog have explicit limits;
they do not predict arbitrary model billing.

For a non-interactive coding agent, prepare `--preview-only`, discuss the
destination/material in chat, then use `--accept-send` only with upload approval.
Replay `<preview-output>/snapshot` with `--snapshot` to retain the frozen source;
keep the context options/configuration unchanged. Do not pass capture flags
(`--base`, `--head`, `--include-untracked`) with `--snapshot`.

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

Omit `--offline` to request semantic drafts using the same connection precedence
and upload confirmation as analysis. With no personal settings, this uses the
shared trial. Failure retains static draft entries and exits 2.

## Update

From the client checkout, fetch the desired reviewed revision and run
`uv sync --package genesis-ci --no-dev --frozen` again. For reproducible CI,
pin the repository/Action to a reviewed full commit SHA.

Refresh installed agent skills with `genesis agent install --agent codex --update`
(or the same agent/scope originally chosen). This does not replace local edits.

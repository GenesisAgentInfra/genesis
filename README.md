# Genesis CLI

Ask your coding agent to review a Python change with Genesis. The agent runs the
local CLI, Genesis extracts structured code evidence, and the hosted Genesis
service explains behavior changes, affected paths, cost/wait/failure risks, test
evidence, and verification gaps. The agent then explains the report in chat.

The CLI and static analysis are public. The semantic service is privately
maintained and operated by the Genesis team. You do not need to deploy a server
or supply a model-provider key. Task/PR documents and flow maps are optional.

## Start in your coding agent

Installing a command does not automatically tell an agent when or how to use it.
Genesis includes a `genesis-review` skill and an installer for Codex and Claude
Code. The skill teaches the workflow; the CLI performs the analysis.

Paste this into the coding agent working on your application:

> Help me set up Genesis from https://github.com/GenesisAgentInfra/genesis-cli.
> Read its README and docs/coding-agents.md, then install the CLI and the
> genesis-review skill for the agent I am using, with user scope. Keep the CLI
> checkout outside this application and reuse an existing installation if present.
> Verify the CLI version and skill installation. Do not run a review or upload
> source during setup.

The agent needs shell access, Git, Python 3.12+, and uv 0.13.7 in its execution
environment. Packages are not published on PyPI yet. A local installation does
not automatically appear in a remote/cloud agent; install in that environment
when that is where your project and agent run.

After setup, start a new agent session if the skill is not visible. Ask:

> Use Genesis to review my current uncommitted changes. Explain what changed
> for users, the main risks, and what still needs testing. Show the upload scope
> before sending source.

Or explicitly select the skill:

| Agent | Prompt |
| --- | --- |
| Codex | `$genesis-review` followed by your review request |
| Claude Code | `/genesis-review` followed by your review request |

Natural-language selection depends on the agent; explicit invocation makes your
choice clear. This setup does not install an automatic hook after every edit.
See [coding-agent setup and troubleshooting](docs/coding-agents.md).

## What happens during a review

1. The agent identifies your application and the intended change: worktree edits,
   branch changes, or a specified commit pair.
2. Genesis freezes that input and prepares a local preview. The agent explains
   which source excerpts and facts would be sent, and to which service.
3. With your upload approval, the agent runs the hosted review on that frozen
   input. Without approval, you still get a local partial report.
4. The agent reads `summary.md`, then checks statuses and evidence in `report.json`
   and `report.md`, and explains the result in your language.

With no personal connection settings, the CLI uses the official shared trial.
No `genesis auth` is needed. Installing the skill does not grant upload consent.
Genesis does not execute your application or its tests. The skill does not
create requirements or turn a review request into permission to fix/commit code.

## Manual setup, or instructions for your agent

Clone outside the application you want to review:

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Use `--agent claude` for Claude Code, or `--agent both`. The default is user
scope; project scope is also available. The installer prints its destinations
and leaves existing agent instructions, permission settings, and Genesis keys
alone. An existing different skill is preserved.

You can also invoke the CLI directly from your application directory:

```sh
uv run --project /absolute/path/to/genesis-cli --package genesis-ci --no-dev --frozen \
  genesis analyze --repo . --base HEAD
```

This compares the current tracked worktree to `HEAD`. Add `--include-untracked`
for new files that belong to the review. To compare committed branch changes,
choose the actual baseline and pass `--base BASE_COMMIT --head HEAD`.
`--preview-only` prepares material without sending; `--offline` runs only local
analysis. These partial modes normally exit **2**, not 0.

## Read the result

Reports are saved under your application's `.genesis/analyses/<run-id>/`. The
command prints the directory. Start with `summary.md`; `report.md` contains
detailed statuses/evidence and `report.json` contains the structured result.
All three reflect the same analysis. The five review areas are:

- **Business behavior:** what can change, with before/after evidence.
- **Affected paths:** callers, code paths, and any supplied flow maps.
- **Cost/wait/failure:** conditional risks and supported static estimates.
- **Tests:** what related test source appears to check, not a claim tests passed.
- **Verification:** suggested checks and missing evidence.

Exit **0** means analysis completed within its declared scope, **2** means a
usable partial report, and **1** means the requested result could not be produced.
Completion is not approval of a change. Missing requirements remain unknown.
Dynamic calls, unsupported constructs, omitted context, and service failures
can limit the result. Do not commit `.genesis/`: it can contain frozen source.

## Hosted service and access

The official endpoint is `https://semantic-api-production.up.railway.app`.
Shared trial and personal Genesis keys access this same service. The public
repository does not distribute the private server for self-hosting.

The trial starts with **10,000 admitted requests shared by all users**, including
analysis, flow drafting, and admitted failures. This lifetime pool has no daily
reset or guaranteed per-user allocation. The trial identity is deliberately
public and revocable. Exhaustion/revocation preserves a local partial report;
the CLI does not automatically retry.

For access under a personal key, request one from the Genesis team. Provisioning
is currently manual. Configure it securely outside agent chat:

```sh
uv run --package genesis-ci --no-dev --frozen genesis auth \
  --service-url https://semantic-api-production.up.railway.app
```

The prompt hides the key and saves it outside the project. Personal settings take
priority, and failures do not silently switch to trial. Do not paste personal
keys in chat or issues. The GitHub Action stays offline without an explicit key.
See [configuration, data handling, and access](docs/usage.md).

## Documentation

- [Use Genesis from a coding agent](docs/coding-agents.md) — setup, discovery,
  natural-language requests, team instructions, and troubleshooting.
- [CLI configuration and data handling](docs/usage.md) — command reference,
  credentials, optional context, upload behavior, and updates.
- [GitHub Action](docs/github-action.md) — repository automation, separate from
  local coding-agent use.
- [Synthetic business example](examples/submit-report/README.md) — a local
  deterministic example for understanding the output.
- [Client development](CONTRIBUTING.md) and [repository ownership](docs/repository-boundary.md).
- [Versioned report schemas](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

## License

Original Genesis CLI code is licensed under [Apache-2.0](LICENSE). You may use,
modify and redistribute it, including commercially, subject to the license terms.
The license does not grant trademark rights or access to the separately operated
Genesis service. The private service implementation is not part of this repository.

Bundled third-party components retain their own licenses, including the MIT
notice for tokenizer assets. See [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Code intelligence for your coding agent.</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">Website</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>Get started</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">Documentation</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">Star History</a>
</p>

<p align="center"><strong>English</strong> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <a href="README.ko.md">한국어</a> &nbsp;·&nbsp; <a href="README.de.md">Deutsch</a> &nbsp;·&nbsp; <a href="README.fr.md">Français</a> &nbsp;·&nbsp; <a href="README.es.md">Español</a></p>

<p align="center">
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/stargazers"><img src="https://img.shields.io/github/stars/GenesisAgentInfra/genesis-cli?style=flat-square&amp;logo=github&amp;label=Stars&amp;color=e3b341" alt="GitHub Stars" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GenesisAgentInfra/genesis-cli?style=flat-square&amp;color=34a853" alt="License: Apache-2.0" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md"><img src="https://img.shields.io/static/v1?label=works+with&amp;message=Codex+%7C+Claude+Code&amp;color=7c3aed&amp;style=flat-square" alt="Works with Codex and Claude Code" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli#what-your-review-covers"><img src="https://img.shields.io/static/v1?label=analyzes&amp;message=Python&amp;logo=python&amp;logoColor=white&amp;color=3776ab&amp;style=flat-square" alt="Supported analysis language: Python" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/packages/genesis_ci/pyproject.toml"><img src="https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2FGenesisAgentInfra%2Fgenesis-cli%2Fmain%2Fpackages%2Fgenesis_ci%2Fpyproject.toml&amp;query=%24.project.version&amp;label=version&amp;color=0891b2&amp;style=flat-square" alt="CLI package version" height="24"></a>
</p>

<p align="center">
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">
    <picture>
      <source media="(max-width: 600px) and (prefers-reduced-motion: reduce)" srcset="assets/readme/code-intelligence-animation-mobile-poster.png">
      <source media="(max-width: 600px)" srcset="assets/readme/code-intelligence-animation-mobile.gif">
      <source media="(prefers-reduced-motion: reduce)" srcset="assets/readme/code-intelligence-animation-poster.png">
      <img src="assets/readme/code-intelligence-animation.gif" alt="Illustrated review workflow: a Python code change moves through context, behavior, and risk analysis into a review report." width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">Illustrated review workflow</a></sub></p>

<a id="genesis-get-started"></a>

## Start in your coding agent

The CLI and static analysis are open source. Semantic review uses the Genesis
hosted service, with your approval before source is sent.

### 1. Install once

Paste this into Codex or Claude Code in the project you want to review:

```text
Set up Genesis from https://github.com/GenesisAgentInfra/genesis-cli.
Read its README and docs/coding-agents.md. Install the CLI outside this
project and the genesis-review skill for my current agent with user scope.
Reuse an existing installation if available. Verify the CLI version and
skill installation. Only set up; do not review or upload code yet.
```

Requires shell access, Git, Python 3.12+, and uv 0.13.7 where your agent runs.
Packages are installed from source and are not yet on PyPI.
[Remote/cloud setup and skill discovery](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md#maintenance-and-troubleshooting).

<details>
<summary>Manual installation</summary>

Run these commands outside the application you want to review:

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Use `--agent claude` for Claude Code or `--agent both`. The default scope is user.
The installer preserves existing agent instructions, permissions, credentials,
and any different existing skill.

[Setup options and troubleshooting](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md).

</details>

### 2. Ask for a review

Start a new agent session if the skill is not visible, then ask:

```text
Use Genesis to review my uncommitted changes.
Explain what changes for users, the main risks, and what still needs testing.
Show me which source excerpts will be sent before uploading.
```

You can also select the skill explicitly:

| Agent | Invocation |
| --- | --- |
| Codex | `$genesis-review` followed by your request |
| Claude Code | `/genesis-review` followed by your request |

Name a branch comparison or commit pair when you want a different scope.
Task descriptions and flow maps are optional context.

The official shared trial works without `genesis auth` when no personal
connection settings are configured. It uses a limited pool shared by all users.
A model-provider API key is not required.
[Access and trial limits](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial).

## What your review covers

| Area | What you get |
| --- | --- |
| Business behavior | Before-and-after evidence of how the application can behave differently. |
| Affected paths | Callers and code paths connected to the change, plus any supplied flow maps. |
| Cost, waiting, and failure | Conditional risks and static estimates where the available evidence supports them. |
| Tests | What related test source checks and which assertions may be missing. |
| Verification | Suggested checks and gaps that still need evidence. |

Genesis analyzes Python source without running your application or its tests.
Missing requirements and unresolved behavior remain explicit gaps in the review.

## From your change to a report

1. **Prepare locally.** Genesis captures the chosen changes and extracts code
   evidence. Your agent shows the source excerpts and facts selected for upload.
2. **Approve the upload.** With your authorization, Genesis sends that material
   to its hosted service. You can keep the analysis local and receive a partial
   report instead.
3. **Read the findings in chat.** Your agent explains the report, checks its
   evidence and status, and identifies what still needs verification.

Reports are saved in your project's `.genesis/analyses/<run-id>/`:

- `summary.md`: start with the readable summary.
- `report.md`: inspect detailed findings, evidence, and statuses.
- `report.json`: use the structured result in your own tools.

Exit codes: **0** means complete within the declared scope, **2** means a usable
partial report, and **1** means the requested result could not be produced.
Keep `.genesis/` out of Git; it can contain captured source.

## Source and service

The public repository contains the CLI and static analysis. The Genesis team
operates the private semantic service; its server implementation is not included
for self-hosting.

Preview and offline analysis stay local. Installing the skill does not enable
automatic reviews after every edit.

[Data handling, personal keys, and configuration](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md).

<a id="genesis-docs"></a>

## Documentation

- [Coding-agent guide](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md): setup, skill discovery, team instructions, and troubleshooting.
- [CLI guide](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md): commands, optional context, credentials, and data handling.
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md): configure repository automation; hosted analysis requires an explicit Genesis key.
- [Contributing](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md): develop and test the client.
- [Repository boundary](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md) and [report schemas](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

<a id="genesis-stars"></a>

## Star History

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="Star history for GenesisAgentInfra/genesis-cli" width="100%">
  </picture>
</a>

[View on Star History](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## License

Original Genesis CLI code is licensed under [Apache-2.0](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE).
Access to the separately operated Genesis service is not granted by this license.
Bundled components retain their own licenses; see [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)
and [third-party notices](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md).

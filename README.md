<p align="center">
  <img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle">&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<p align="center"><strong>English</strong> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a></p>

Genesis turns a repository into a map of business flows, each step backed by the code
it came from, and shows what a change does to those flows: which steps it touches and
whether an existing test covers the new behaviour.

- **The CLI is deterministic.** It freezes a snapshot of the code, extracts facts,
  finds entry points, checks every description it is given and renders the result.
  It calls no model and no service, and never imports or runs the code it reads.
- **Your coding agent does the reading.** Through the bundled skill, Codex or Claude
  Code describes each flow in business terms; the CLI accepts or rejects each
  description as a whole against the code evidence.

## What is supported today

- Python source.
- A full map of the current code, and the changes since a revision placed on that map.
- Test verdicts come from reading test source. Genesis does not run tests.

## Get started

Install the CLI outside the project you want to map:

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git
cd genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

`--agent` takes `codex`, `claude` or `both`. Then, in the project you want to map, ask
your agent for the business flows of the project or for what a change does to them,
or call the skill by name: `/genesis` in Claude Code, `$genesis` in Codex.

The result is written under `.genesis/` in that project: a page to open in a browser
(`view.html`) and a summary (`summary.md`).

## Commands

| Command | What it does |
| --- | --- |
| `genesis agent install` | Make Genesis discoverable in your coding agent; no analysis or upload. |
| `genesis agent status` | Inspect the installed skill files. |
| `genesis map prepare` | Freeze a snapshot, extract facts and write the static skeleton. |
| `genesis map plan` | Group entries into flows and create one task per flow. |
| `genesis map status` | List tasks, their state and what is still missing. |
| `genesis map context` | Everything needed to start one task. |
| `genesis map query` | Look at one symbol and its neighbours, or search the frozen source. |
| `genesis map read` | Read the frozen source behind one evidence reference. |
| `genesis map submit` | Check one submission for a task; accepted or rejected as a whole. |
| `genesis map diff` | List what changed since the base revision and where it lands on the map. |
| `genesis map render` | Write the page and the summary for a session. |

The agent runs the `map` commands for you; they are listed so you can see what it does.

## Repository layout

| Path | Holds |
| --- | --- |
| `packages/genesis_ci` | The CLI: snapshot, Python fact extraction, the map workflow, the agent skill. |
| `packages/genesis_contracts` | The schemas of the files the CLI reads and writes. |
| `viewer/` | The page `genesis map render` writes, as source. |
| `fixtures/business-map` | A worked example of every contract. |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Original Genesis code is licensed under [Apache-2.0](LICENSE). Bundled components keep
their own licenses; see [NOTICE](NOTICE) and
[third-party notices](THIRD_PARTY_NOTICES.md).

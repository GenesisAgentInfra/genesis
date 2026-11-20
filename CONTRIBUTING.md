# Contributing to Genesis

Genesis is a local CLI plus a skill that tells a coding agent how to drive it. This
page is for changing Genesis itself: how to report a problem, set up the repository,
run the checks and open a pull request. To install or use Genesis, see
[docs/install.md](docs/install.md) and [docs/usage.md](docs/usage.md).

## Questions and bug reports

Ask a question or report a bug in a
[GitHub issue](https://github.com/GenesisAgentInfra/genesis/issues). For a bug, say:

- the command you ran or what you asked your agent, and what it printed;
- what you expected instead;
- the Genesis version, from `genesis version` (`"$(uv tool dir --bin)/genesis" version`
  if `genesis` is not on your `PATH`);
- your coding agent and operating system.

Genesis is tested with Claude Code and Codex on macOS and Linux. Windows is not tested.

Do not attach files from `.genesis/` of a private project. Its `sessions/` and `out/`
folders hold copies of your source, and `view.html` and `graph.html` contain source
excerpts. "Share a result" in [docs/usage.md](docs/usage.md) explains how to get a copy
without them.

## Security problems

Do not report a vulnerability in a public issue. See [SECURITY.md](SECURITY.md).

## Where things are

| Path | Holds |
| --- | --- |
| `packages/genesis_ci` | The CLI. The bundled skill is in `src/genesis_ci/assets/skills/genesis/`, the built viewer page in `src/genesis_ci/assets/viewer/index.html`. |
| `packages/genesis_contracts` | The models of the files the CLI reads and writes. |
| `viewer/` | The source of the viewer page, a separate Node.js project. |
| `fixtures/business-map/` | A small synthetic project and example files, written by `scripts/build_map_fixtures.py`. |
| `scripts/` | The fixture generator and the package and public-file checks. |
| `tests/` | The Python tests. |
| `README.md`, `docs/`, `AGENTS.md` | The documents for users and their coding agents. |

## Set up

You need Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). uv
reads `.python-version` and downloads Python 3.12 when it is missing, so you do not
have to install Python yourself. CI uses uv 0.13.7; if a command behaves differently
from CI, try that version.

From the repository root:

```sh
uv sync --all-packages --group dev --frozen
```

This installs both packages into `.venv`, in editable mode, with the development tools.

## Run the checks

CI runs these commands on every push and pull request. Run them from the repository
root before you open one.

Lint, format check, tests and the public-file audit change nothing:

```sh
uv run --all-packages --frozen ruff check packages scripts tests
uv run --all-packages --frozen ruff format --check packages scripts tests
uv run --all-packages --frozen pytest -q
uv run --all-packages --frozen python scripts/check_public_boundary.py
```

The fixture generator rewrites `fixtures/business-map/`. CI then fails if anything
differs from what is committed, so commit what it changes together with your change:

```sh
uv run --all-packages --frozen python scripts/build_map_fixtures.py
git diff --exit-code -- fixtures/
```

The last three commands build both wheels into `dist/`, which Git ignores, and check
what they contain. Run `check_packages.py` after the two builds:

```sh
uv build --package genesis-ci --wheel
uv build --package genesis-contracts --wheel
uv run --all-packages --frozen python scripts/check_packages.py
```

While you work, run one file or one test by adding to the test command:
`uv run --all-packages --frozen pytest -q tests/test_docs.py`, or add
`-k part_of_a_test_name`.

Tests build small synthetic Git repositories. They need no key, no model, no network
and no private source. Genesis reads the analyzed source as text and never imports or
executes it; keep it that way.

## Contracts and fixtures

The models in `packages/genesis_contracts` are authoritative for the files the CLI
reads and writes. `fixtures/business-map/` holds a small synthetic project and worked
examples of four of those files: the business map (complete, partial and skeleton), the
change report, the evidence bundle and the snapshot manifest. It has no example of the
facts file, a plan or a task submission. `scripts/build_map_fixtures.py` regenerates the
directory.

## Pull requests

1. Create a branch from `main`, in a fork if you cannot push to this repository. Do not
   commit to `main` directly.
2. Run the checks above. If you changed the viewer, also run its commands (see
   "Changing the viewer").
3. Write commit messages and the pull request's title and description in English. Say
   what the change does and why, and how you checked it.
4. Open the pull request against `main`. The `Public client` workflow runs the checks
   above, then installs the package without the lockfile the way
   [docs/install.md](docs/install.md) does. Its `viewer` job tests and builds `viewer/`. For a first-time contributor, GitHub may
   wait for a maintainer to approve the run.
5. A maintainer reviews the pull request and merges it.

If the change alters a command, a flag, an output path or an error message, update the
documents in the same pull request (see "Documentation language").

## Changing the bundled skill

The skill's source is in `packages/genesis_ci/src/genesis_ci/assets/skills/genesis/`.
Edit that source, not an installed copy, and keep its commands in line with the CLI.

`agent install` copies the skill and records the Python it ran with. An edit to the
source therefore does not reach an installed copy until you install again. To try a
change with a real agent, install from your working tree into a test project, so the
copy you use every day stays as it is:

```sh
uv run --all-packages --frozen genesis agent install --agent claude --scope project --repo /path/to/test/project
```

Some tests read sentences of the skill, for example `tests/test_change_bookkeeping.py`,
`tests/test_agent_setup.py` and `tests/test_change_analysis.py`: run the whole suite
after a wording change. After each edit of the skill text, run the same command with
`--update`, then open the
test project in a new agent session. Without `--update`, `agent install` refuses to
replace a copy that differs, and `agent status` with the same `--scope` and `--repo`
prints `different or locally edited`. The installed copy runs this repository's
`.venv`, so changes to the Python code take effect without installing again.

For a test project, copy `fixtures/business-map/head` to a directory outside this
repository, then run `git init` there and commit (with an empty `HOME`, pass an
identity: `git -c user.name=test -c user.email=test@example.invalid commit`). To try a user-scope install instead,
set `HOME` to an empty test directory first, so that your own install is not replaced.

## Changing the viewer

The viewer is a separate Node.js project in `viewer/`. Its build tools need npm and
Node.js 20 (20.19 or later), Node.js 22 (22.13 or later), or Node.js 24 or later.
Node.js 21 and 23 do not work. The commands are in
[viewer/README.md](viewer/README.md); run them in `viewer/`, starting with
`npm install`.

Before you open a pull request, run `npm test`, `npm run lint` and `npm run build`.
The build type-checks, then writes the page into
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`. Run the Python tests
again, since `tests/test_view.py` reads the built page. Commit the built file together
with the source change that produced it.

CI's `viewer` job runs the same commands on Node.js 22, without the paid Graphical
package, and fails when the committed page differs from the one the source builds.

The page's interface text, in English and Chinese, is in `viewer/src/i18n.ts`.
[PRODUCT.md](PRODUCT.md) is the page's brief: who reads it and what it must and must
not do. Keep it current when a change alters what the page shows.

## Adding a language to the agent engine

Python is the only language the CLI parses (`packages/genesis_ci/src/genesis_ci/python/`).
The agent engine reads every other language through the coding agent, and the CLI
checks what the agent cites. Supporting one more language means adding its file suffix
in three places that must agree:

1. `SOURCE_SUFFIXES` in `packages/genesis_ci/src/genesis_ci/agent_map/session.py`.
   `is_test_path` in the same file decides which files count as tests; extend it if
   the language names its tests differently.
2. `LANGUAGE_OF_SUFFIX` in `tests/test_docs.py`: the suffix and the language's name.
3. The language list under "Languages" in `docs/usage.md` and the same list in
   `docs/usage.zh-CN.md`, with the name spelled as in the test.

`tests/test_docs.py` fails until the three agree.

## Licenses

Original contributions are provided under Apache-2.0; see LICENSE and NOTICE. Each
package directory carries a copy of both, checked by `scripts/check_packages.py`.

[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) lists the packages the viewer page
uses directly: every entry under `dependencies` in `viewer/package.json`, and any other
package `viewer/src` imports (such as `tw-animate-css`, imported by `src/index.css`).
When you add or remove one, change the table in the same commit. The viewer build
copies the whole file into the head of the page, so a page passed on alone keeps its
notices, and fails when a package whose code ends up in the page is not named in it.
After changing the file, rebuild the page and commit both.

## Documentation language

Write `README.md`, `AGENTS.md`, the guides in `docs/`, this file, `SECURITY.md` and the
bundled skill in English, in plain, short sentences. `README.zh-CN.md` and the
`docs/*.zh-CN.md` files say the same in natural Chinese. Keep every command, path, flag
and field name unchanged in them; `tests/test_docs.py` fails when their `sh` blocks
differ from the English ones.

People hand installation and use to their coding agent, so the documents are written
for an agent to follow as well as for a person to read: `docs/install.md` from a clean
machine to a working skill, `docs/usage.md` for what to ask and where the result is,
and `AGENTS.md` for an agent that opens this repository. When an install command, a
flag, an output path or an error message changes, change these with it;
`tests/test_docs.py` checks the parts that can be checked.

The figures in `docs/change-analysis-benchmark.md`, the benchmark table and chart in
`README.md`, their Chinese versions and the charts in `assets/readme/benchmark-*.svg`
come from benchmark runs whose data and scripts are not in this repository. They cannot
be regenerated here. Do not change a figure by hand; open an issue if one looks wrong.

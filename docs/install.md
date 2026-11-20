# Install Genesis

<p><strong>English</strong> &nbsp;·&nbsp; <a href="install.zh-CN.md">简体中文</a></p>

Genesis has two parts: a local CLI, and a skill that tells your coding agent how to
drive it. Installing means putting the CLI on your machine and copying the skill into
the directory your agent reads skills from.

A coding agent can follow this page from top to bottom on your behalf.

## Requirements

- macOS or Linux. Windows is not tested.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
- Python 3.12. You do not have to install it: uv downloads it when it is missing.
- A coding agent that can run shell commands and loads skills from one of the
  directories in the table below.

The project you analyze needs nothing. Genesis does not install its dependencies,
import or run its code, or use the network.

## Install

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

The first command installs the CLI into uv's tool directory, outside any project. The
second copies the skill into your home directory and records which Python environment
it runs with. Neither command touches the project you want to analyze, so run them from
any directory. uv may warn that its tool directory is not on your `PATH`; that does not
matter here, because the second command calls the CLI by its full path.

Choose `--agent` by the coding agent you use:

| Your agent | Flag | Where the skill goes |
| --- | --- | --- |
| Claude Code | `--agent claude` | `~/.claude/skills/genesis` |
| Codex | `--agent codex` | `~/.agents/skills/genesis` |
| Cursor, Gemini CLI, OpenCode, GitHub Copilot | `--agent codex` | `~/.agents/skills/genesis` |
| Claude Code together with Codex, Gemini CLI or GitHub Copilot | `--agent both` | both directories |

The flag chooses a directory, not a product: `codex` means `~/.agents/skills`. That is
the directory Codex reads, and the other agents in the third row read it too, according
to their documentation in November 2026. Genesis is tested with Claude Code and Codex.
With another agent, check after installing that it lists the skill.

Cursor and OpenCode also read `~/.claude/skills`. If you use one of them next to Claude
Code, `--agent claude` alone covers both; with `--agent both` they would find the skill
in two places.

An agent that reads none of these directories can still use Genesis: point it at the
installed `SKILL.md` and ask it to follow that file. The skill folder is
self-contained, so it can also be copied whole into another skills directory.

## Check the install

```sh
"$(uv tool dir --bin)/genesis" agent status
```

This prints `installed (current)` for each directory you installed into, and
`not installed` for the other.

Then run the CLI the way the skill does. It prints `genesis-ci` with its version. After
`--agent claude`:

```sh
python3 -I ~/.claude/skills/genesis/scripts/run_genesis.py version
```

After `--agent codex`:

```sh
python3 -I ~/.agents/skills/genesis/scripts/run_genesis.py version
```

## Start using it

Open the project you want to look at in your agent and ask. See [usage](usage.md).

Claude Code and Codex notice a new skill on their own. If your agent does not offer
`/genesis` (`$genesis` in Codex), start a new session.

Other agents list and call skills in their own way: in Cursor, type `/` in Agent chat
and look for `genesis`; in Gemini CLI, `/skills` shows what was found. In all of them
you can simply ask in plain language, and the agent picks the skill by its description.

An agent that installed Genesis during the session it is in may not have the skill
loaded yet. It does not need to wait: it can read the installed `SKILL.md` and follow
it. That is the same text the skill loads.

## Install for one project only

```sh
"$(uv tool dir --bin)/genesis" agent install --agent claude --scope project --repo /path/to/your/project
```

This writes the skill to `.claude/skills/genesis` (or `.agents/skills/genesis`) inside
that project instead of your home directory. The folder ignores itself in Git, because
it records a path on your machine. Each person who works on the project installs their
own copy.

## Update

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update
```

`--update` replaces an installed skill only when nobody edited it. Without the flag,
`agent install` refuses to touch a skill folder that differs from the version being
installed.

## Uninstall

```sh
rm -r ~/.claude/skills/genesis ~/.agents/skills/genesis
uv tool uninstall genesis-ci
```

Remove only the skill directories you installed into. Genesis writes nothing else
outside your projects. Inside a project it writes one directory, `.genesis/`; delete
it when you no longer want the results.

## Install from a checkout

Use this when you want the dependency versions the tests ran with, or when you work on
Genesis itself.

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git ~/genesis
cd ~/genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

- Clone to a place that stays, such as your home directory. The skill runs the Python
  environment inside this checkout (`.venv`). If you move or delete the checkout, the
  skill stops working until you run the last two commands again, with `--update` added
  to the last one.
- Do not clone Genesis into the project you want to analyze.
- To update: `git pull`, then the last two commands again, with `--update` added to
  the last one.
- To uninstall: remove the skill directories as above, then delete the checkout.

## When something goes wrong

| What you see | Why | What to do |
| --- | --- | --- |
| `uv: command not found` | uv is not installed. | [Install uv](https://docs.astral.sh/uv/getting-started/installation/), then start again. |
| `genesis: command not found` | uv's tool directory is not on your `PATH`. | Call it as `"$(uv tool dir --bin)/genesis"`, or run `uv tool update-shell` and open a new terminal. |
| `Executable already exists: genesis` | Another program named `genesis` is already in uv's tool directory. | Leave it in place and [install from a checkout](#install-from-a-checkout) instead. |
| `Cannot install Genesis skill: Skill already exists or was edited` | A Genesis skill folder is already there and differs from this version. | Add `--update`. If you edited the folder yourself, move it away first. |
| `Genesis skill environment is unavailable` | The Python environment recorded at install time is gone: the uv tool was removed, or the checkout was moved or deleted. | Install again, then run `agent install` with `--update`. |
| Your agent does not offer `/genesis` | The session started before the skill was installed, or the skill is in a directory your agent does not read. | Start a new session. Run `agent status` and compare with the table above. |
| `Operation not permitted` or `Read-only file system` from `map prepare` | The agent's sandbox does not let Genesis write `.genesis/` in your project. | Give the agent write access to the project directory. |
| `unsupported_repository` | The project has no source file Genesis can read. | Nothing to install or fix; Genesis cannot map this project. |

# Install Genesis

<p><strong>English</strong> &nbsp;·&nbsp; <a href="install.zh-CN.md">简体中文</a></p>

Genesis has two parts: a local CLI, and a skill that tells your coding agent how to
drive it. Installing means putting the CLI on your machine and copying the skill into
the directory your agent reads skills from.

A coding agent can do the install on your behalf: the sections from Requirements to
Start using it, in order. The sections after those cover updating, uninstalling and
other ways to install. The table at the end is for when a command fails.

## Requirements

- macOS or Linux. Windows is not tested.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
- Python. The CLI runs on Python 3.12, and uv downloads it when it is missing. The
  skill starts the CLI with `python3`, so some Python 3 must also be on your `PATH`.
  macOS with the command line tools and most Linux systems have one; a minimal
  container image may not.
- A coding agent that can run shell commands and loads skills from one of the
  directories in the table below.

The project you analyze has to be a Git repository with at least one commit. Beyond
that it needs nothing: Genesis does not install its dependencies, import or run its
code, or use the network.

## Install

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

The first command installs the CLI into uv's tool directory, outside any project. The
second copies the skill into your home directory and records which Python environment
it runs with. Neither command touches the project you want to analyze, so run them from
any directory. uv may warn that the directory it puts the `genesis` command in is not on
your `PATH`; that does not matter here, because the second command calls the CLI by its full path.

The first command needs the network. It fetches Genesis from GitHub, its dependencies
from PyPI and, when it is missing, Python 3.12. Both commands write outside your
project: the first to uv's tool, Python and cache directories, the second to
`~/.claude/skills` or `~/.agents/skills`. If your agent's sandbox blocks the network or
writing outside the project, the agent has to ask you to approve the two commands, or
you run them yourself in a terminal.

The package is named `genesis-ci` and the command it installs is `genesis`. uv's
upgrade and uninstall commands take the package name.

Choose `--agent` by the coding agent you use. Every `agent install` command on this
page is written with `--agent claude`. Put your own flag in its place each time,
including when you update.

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
installed `SKILL.md` and ask it to follow that file. You can also copy the whole skill
folder into another skills directory on the same machine. The folder records the path
of the Python environment the CLI is installed in, so a copy does not work on another
machine. `agent status` and `agent install --update` do not see a copy either: copy the
folder again after each update.

## Check the install

```sh
"$(uv tool dir --bin)/genesis" agent status
```

This prints `installed (current)` for each directory you installed into, and
`not installed` for the other.

`different or locally edited` means the skill folder is not what this CLI would install
now. Usually the CLI was upgraded, or installed again somewhere else, after the skill
was installed: run `agent install` again with `--update`. If you edited the folder
yourself, `--update` refuses; move the folder away first, then install.

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

## Update

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update
```

Pass the same `--agent` as when you installed. With a different flag, the command may
install a second copy in another directory, and the copy your agent reads may stay out
of date.

`--update` replaces an installed skill only when nobody edited it. Without the flag,
`agent install` refuses to touch a skill folder that differs from the version being
installed.

## Uninstall

Remove the skill from each directory you installed it into, then remove the CLI:

```sh
rm -r ~/.claude/skills/genesis    # installed with --agent claude or both
rm -r ~/.agents/skills/genesis    # installed with --agent codex or both
uv tool uninstall genesis-ci
```

Genesis writes nothing else outside your projects. Inside a project it writes one
directory, `.genesis/`; delete it when you no longer want the results.

## Install for one project only

This replaces the second command under [Install](#install). The CLI itself is still
installed with the first.

```sh
"$(uv tool dir --bin)/genesis" agent install --agent claude --scope project --repo /path/to/your/project
```

`--repo` must be the project's Git root, the directory that contains `.git`. The skill
goes to `.claude/skills/genesis` (or `.agents/skills/genesis`) inside that project
instead of your home directory. The folder ignores itself in Git, because it records a
path on your machine. Each person who works on the project installs their own copy.

`agent status` and `agent install --update` look in your home directory unless you add
the same `--scope project --repo`. To check the install:

```sh
"$(uv tool dir --bin)/genesis" agent status --scope project --repo /path/to/your/project
python3 -I /path/to/your/project/.claude/skills/genesis/scripts/run_genesis.py version
```

To update:

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update --scope project --repo /path/to/your/project
```

To uninstall, delete the skill folder inside the project. Remove the CLI too if nothing
else uses it:

```sh
rm -r /path/to/your/project/.claude/skills/genesis
uv tool uninstall genesis-ci
```

After `--agent codex`, write `.agents` in place of `.claude` in these paths.

## Install from a checkout

Use this when you want the dependency versions the tests ran with, when another
program named `genesis` is already in uv's tool directory, or when you work on Genesis
itself.

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git ~/genesis
cd ~/genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

- Clone to a place that stays, such as your home directory. The skill runs the Python
  environment inside this checkout (`.venv`). If you move the checkout, the skill stops
  working until you run the last two commands again in its new place, with `--update`
  added to the last one. If you delete it, clone it again first.
- Do not clone Genesis into the project you want to analyze.
- If you already set up the checkout for development as in
  [CONTRIBUTING.md](../CONTRIBUTING.md), skip the `uv sync` line. It removes the test
  and lint tools from `.venv`.
- Wherever this page calls `"$(uv tool dir --bin)/genesis"`, use
  `uv run --project ~/genesis --package genesis-ci --no-dev --frozen genesis` instead. It
  works from any directory. In place of `uv tool upgrade genesis-ci`, run
  `git -C ~/genesis pull`, and skip `uv tool uninstall genesis-ci`. To check the install:
  `uv run --project ~/genesis --package genesis-ci --no-dev --frozen genesis agent status`.
  The `python3 -I ... run_genesis.py version` check is the same as above.
- To update: `git pull`, then the last two commands again, with `--update` added to
  the last one.
- To uninstall: remove the skill directories as under [Uninstall](#uninstall), then
  delete the checkout. Skip `uv tool uninstall`.

## When something goes wrong

| What you see | Why | What to do |
| --- | --- | --- |
| `uv: command not found` | uv is not installed. | [Install uv](https://docs.astral.sh/uv/getting-started/installation/), then start again. |
| `genesis: command not found` | The directory uv puts the `genesis` command in (`uv tool dir --bin`) is not on your `PATH`. | Call it as `"$(uv tool dir --bin)/genesis"`, or run `uv tool update-shell` and open a new terminal. |
| `python3: command not found` | No Python 3 is on your `PATH`. The copy uv downloads for the CLI is not put there. | Install Python 3 with your system's package manager, then run the check again. |
| `Executable already exists: genesis` | Another program named `genesis` is already in uv's tool directory. | Leave it in place and [install from a checkout](#install-from-a-checkout) instead. |
| `Another version of the Genesis skill is installed` | An unedited Genesis skill folder from another version is already there. | Add `--update`. |
| `Skill folder was edited, or was not installed by Genesis` | The folder was changed by hand, or something else installed a skill named `genesis` there. | Move the folder away, then install again. |
| `Skill destination cannot contain symbolic links` | `~/.claude`, `~/.agents`, the `skills` folder in one of them, or the `genesis` folder is a symbolic link. Genesis does not read or write through links, so `agent install` and `agent status` stop. | If one `skills` folder links to the other, install into the real one with its flag, and pass the same `--agent` to `agent status`. An agent that reads the linked folder finds the skill through the link. Otherwise install with the other flag, into the directory that is not a link, and copy the whole `genesis` folder into the linked one, as described under [Install](#install). |
| `Genesis skill environment is unavailable` | The Python environment recorded at install time is gone: the uv tool was removed, or the checkout was moved or deleted. | Install again, then run `agent install` with `--update`. |
| Your agent does not offer `/genesis` | The session started before the skill was installed, or the skill is in a directory your agent does not read. | Start a new session. Run `agent status` and compare with the table above. |
| `Operation not permitted`, `Read-only file system` or a failed download from `uv tool install` or `agent install` | The agent's sandbox blocks the network or writing outside the project. | Approve running the command outside the sandbox, or run the two install commands yourself in a terminal. |
| `cannot_write`, `Operation not permitted` or `Read-only file system` from `map prepare` | Genesis cannot write `.genesis/` in your project: the agent's sandbox blocks it, or the directory is not writable. | Give the agent write access to the project directory. |
| `git_read_failed` | Git could not read the project. Most often the directory is not inside a Git repository: it was never put under Git, or it is a folder that only holds repositories. | Open the agent in the repository itself. If the project is not under Git yet, run `git init` there and commit the code. |
| `revision_unavailable` | The repository has no commit yet, or the revision you asked to compare with is not in the local clone. | Commit the code first, or fetch the revision and ask again. |
| `unsupported_repository` | The project has no source file Genesis can read. | Nothing to install or fix; Genesis cannot map this project. |

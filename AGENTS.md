# Notes for coding agents

Genesis is a local CLI plus a skill that tells a coding agent how to drive it. You are
most likely here for one of two reasons.

## The user asked you to install or use Genesis

1. **Install** by following [docs/install.md](docs/install.md). It is two commands,
   run from any directory. Do not clone this repository into the user's project, and
   do not install anything into the user's project environment.
2. **Use it in the session you are in.** A skill installed mid-session may not be
   loaded yet. Read the installed `SKILL.md` (`~/.claude/skills/genesis/SKILL.md` or
   `~/.agents/skills/genesis/SKILL.md`) and follow it as written, starting at "Locate
   the CLI". Do not work out the commands from `--help` or from this repository's
   source: the skill is the supported way to drive the CLI, and the CLI rejects
   submissions that do not follow it.
3. **Show the result.** Give the user the path of `.genesis/out/latest/view.html` in
   their project and say what is in it, as the skill's reporting sections describe.
   [docs/usage.md](docs/usage.md) is the page to point the user to.

Genesis reads the user's project and writes only `.genesis/` inside it. It does not run
the project's code or tests, and neither should you unless the user asks.

## The user asked you to change Genesis itself

Follow [CONTRIBUTING.md](CONTRIBUTING.md): the commands to run before a change is done,
where the bundled skill lives, and the rule that analyzed source is never imported or
executed. This is a public repository. Tests and fixtures use synthetic code only.

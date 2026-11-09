# Use Genesis from your coding agent

Set up Genesis and a project review instruction once. Then ask your coding agent
to prepare changes for code review (CR/PR); the instruction asks it to run Genesis
and explain the actual report before finalizing the review description. This
works without GitHub CI. You can also request a Genesis review directly.
The agent needs the CLI and review skill installed where it can read your application.

## How the agent learns about Genesis

| Piece | Responsibility |
| --- | --- |
| `genesis` CLI | Freeze Git input, extract code facts, call the hosted service when authorized, and write reports. |
| `genesis-review` skill | Tell the agent when to use Genesis, how to choose a diff and invoke the CLI, and how to explain statuses/evidence. |
| Project review instruction | Ask your team's agents to run Genesis when preparing Python changes for CR/PR. |

The installer puts `SKILL.md` and its runner into the agent's discovery directory.
The skill's name/description make it available for selection; explicit invocation
selects it directly. Installing a binary alone does not register a skill, MCP
tool, or hook. Natural-language routing is an agent decision: even with the
project instruction, invocation is not guaranteed. This is a default workflow,
not a mandatory check or merge gate.

This release provides a local skill integration for Codex and Claude Code. It
does not provide a Genesis MCP server or a mandatory post-edit hook. Other agents
can use the CLI through shell tools, but discovery requires their own supported
instruction/skill mechanism.

## One-time setup through chat

Give your agent this request (name Codex or Claude Code if it cannot infer which):

> 请从 https://github.com/GenesisAgentInfra/genesis-cli 接入 Genesis。
> 先读 README 和 docs/coding-agents.md，把 CLI 安装在当前应用仓库外，
> 并为我当前使用的 coding agent 安装用户级 genesis-review skill。
> 已有安装就复用；需要时更新未经用户修改的托管 skill。
> 按下方 “Configure CR preparation in this project” 配置当前项目的 CR 审查约定，
> 保留其他指令。检查版本、skill 和约定，并告诉我修改了哪个文件。
> 这一步只配置，不分析、不上传代码；以后上传仍需覆盖目标服务和所选源码的授权。

The agent follows the source installation steps in the [README](../README.md),
then runs these commands from the Genesis checkout:

```sh
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Use `--agent claude` for Claude Code, or `--agent both`. Installation requires
`--agent` so setup never guesses which agent settings you want. Default scope
is `user`. `--dry-run` prints destinations without writing.

| Agent | User scope (all local projects) | Project scope |
| --- | --- | --- |
| Codex | `~/.agents/skills/genesis-review/` | `<app>/.agents/skills/genesis-review/` |
| Claude Code | `~/.claude/skills/genesis-review/` | `<app>/.claude/skills/genesis-review/` |

For a single application, select its Git root, not the CLI checkout:

```sh
uv run --package genesis-ci --no-dev --frozen genesis agent install \
  --agent codex --scope project --repo /absolute/path/to/your-app
uv run --package genesis-ci --no-dev --frozen genesis agent status \
  --agent codex --scope project --repo /absolute/path/to/your-app
```

The installed `runtime.json` records the Python environment used for Genesis.
The runner calls that environment directly, so the agent need not guess the
checkout path or find `genesis` on PATH. Keep that environment available.
Generated installs contain machine-specific paths and a local `.gitignore`;
they are not meant to be force-added to Git. Each developer installs their own
copy. Share setup instructions and optional project policy instead.

The `genesis agent install` command writes only the skill directory. It does not
change `AGENTS.md`, `CLAUDE.md`, agent permissions, hooks, MCP configuration, or
Genesis credentials. An identical install is a no-op; a different existing skill
is preserved unless an unmodified managed installation is explicitly updated.
The README chat prompt additionally asks the agent to edit the current project's
instructions as described below. These are two separate setup steps.

## Verify discovery, then ask for a review

`genesis agent status` checks local files, not whether an agent has loaded them.
Look for `genesis-review` in the agent's skill selector. If missing, open a new
session or restart the agent. Claude Code versions with `/reload-skills` can
reload newly created skill directories. Then use an explicit request:

**Codex:**

```text
$genesis-review 检查当前未提交改动，解释业务变化、风险和需要补测的内容。先展示上传范围。
```

**Claude Code:**

```text
/genesis-review 检查当前未提交改动，解释业务变化、风险和需要补测的内容。先展示上传范围。
```

After confirming discovery, ordinary requests can name Genesis naturally:

> 用 Genesis 帮我看看这次改动有什么风险。

Be specific about scope when it matters:

| What you want | Example request |
| --- | --- |
| Uncommitted changes | “用 Genesis 检查当前未提交改动；新加的 billing.py 也包含进去。” |
| Branch changes | “用 Genesis 检查这个分支相对 main 的提交，不包括工作区改动。” |
| Local-only review | “用 Genesis 做离线检查，不要把代码上传。” |
| Explain an existing result | “解释这份 Genesis summary.md，必要时核对 report.md 的证据，不要重跑。” |

The skill tells the agent to choose the actual baseline and list relevant new
files. It should not blindly use `HEAD~1`, assume every repository has `main`,
or silently review an empty diff.

## Upload confirmation in an agent session

Agent shell calls often cannot interact with a terminal yes/no prompt. The
skill uses this workflow:

1. Run `analyze --preview-only` into a fresh private output directory.
2. Explain the destination and selected material in chat. It can contain real
   source excerpts and paths, not only abstract code facts.
3. Use existing explicit upload authorization if it covers this scope; otherwise
   ask for consent. Installation alone does not authorize upload.
4. After approval, use `--snapshot <preview-dir>/snapshot --accept-send` with a
   different output directory. Reuse the same context options and unchanged
   configuration so the reviewed source comes from the frozen preview.

No network call occurs during preview/offline analysis. If you decline, the
agent explains the local partial report. Worktree changes after the preview are
not silently added. Updated configuration or extra context needs a new preview.
A timeout or partial exit is not permission to retry.

Without personal settings, official shared trial works without `auth`. Existing
personal settings remain in effect. Configure a personal Genesis key privately
using the [credential instructions](usage.md#optional-personal-credentials),
outside agent chat. Neither setup nor the skill requires your provider key.

## Configure CR preparation in this project

The README setup prompt requests this step. For manual or existing installations,
ask your agent to apply it after installing/updating the skill. Scope it to the
application repository, not the Genesis checkout or the user's global instructions.

1. Read the current project instructions. Use root `AGENTS.md` for Codex or root
   `CLAUDE.md` for Claude Code; use both only when setting up both agents. Preserve
   the project's existing instruction-file conventions and shared pointers.
2. Add the section below, or update an existing Genesis section without duplicating
   it. Create the relevant file if absent; preserve unrelated text. If existing
   policy prohibits hosted analysis, keep the review offline. Resolve conflicting
   review requirements with the user instead of replacing them.
3. Read back the section and run `genesis agent status` for the chosen agent/scope.
   Report the instruction path and skill status. Setup ends here: no review,
   source upload, Git hook, or CI workflow is created by this setup request.

```markdown
## Genesis review before CR/PR
When the user asks to prepare, cut, or submit a code review (CR/PR) for Python
changes, use the installed genesis-review skill before finalizing the review
description or submitting it. This includes "准备发 CR" and "整理改动提 PR";
the user need not name Genesis. Honor an explicit request to skip Genesis.
Review the intended change set against its actual target base, including intended
uncommitted/new files. Reuse an existing Genesis result only if it covers the same
source snapshot, scope, and analysis inputs; disclose changes it does not cover.
Follow the skill's preview and upload-authorization steps. Preparing a CR alone
does not authorize source upload. Use applicable existing authorization or ask;
when offline is requested or upload is declined, explain the local partial report.
Summarize findings, report location, and unverified areas before the CR handoff.
If Genesis is unavailable, fails, or returns partial results, state that clearly;
do not label the change as passed or silently substitute the agent's own review.
This is agent guidance, not a Git hook or merge gate. Publishing the CR and
changing code still follow the user's request and existing project permissions.
```

Try it in a new agent session: “帮我整理这次改动，准备发 CR.” Check that the agent
actually invokes Genesis and reports its output; having the section on disk does
not prove that the current agent loaded or followed it. Direct terminal pushes
and CRs prepared without the agent are not intercepted. GitHub, GitLab, Gerrit,
and other review destinations use the same local convention; it does not install
an integration with those services. Unsupported changes should be identified
as outside Genesis's Python analysis scope.

The skill is user-scoped by default, but this instruction is per project. Repeat
this step for another project. To stop the default CR review, remove only this
Genesis instruction section; explicit Genesis reviews remain available.
For CI automation, see the optional [GitHub Action](github-action.md).

## Maintenance and troubleshooting

After updating the CLI, refresh an unmodified installed skill with the same scope:

```sh
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex --update
```

- **Skill missing:** check the agent, scope, application root, and execution host.
  Reopen/restart the agent. Administrator policy can restrict local skills.
- **Natural language does not select it:** explicitly use `$genesis-review` or
  `/genesis-review`. The agent still decides how to follow the instructions.
- **“Environment unavailable”:** the CLI checkout or environment moved/deleted.
  Run the installer with `--update` from the working installation.
- **Existing skill was edited:** the installer preserves it even with `--update`.
  Reconcile or move that directory after preserving your changes.
- **Exit 2:** inspect `summary.md` and `report.json`; it is a partial analysis,
  not necessarily a setup failure. Missing consent/service must be stated.
- **Remote/cloud agent:** a laptop installation does not automatically appear
  there. This installer targets local filesystem discovery; cloud products may
  require a different supported skill delivery mechanism.

To remove the integration, inspect `agent status` and remove only the corresponding
`genesis-review` directory you installed. CLI, credentials, and reports remain.

## References and validation scope

See the official [Codex skills documentation](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skills documentation](https://code.claude.com/docs/en/skills)
for agent-specific discovery and policy. The portable skill source is bundled
under `packages/genesis_ci/src/genesis_ci/assets/skills/genesis-review/`.

Tests verify installation, preservation of existing files, runner arguments/exit
codes, and real offline CLI analysis. They do not prove that every agent/version
will select the skill from every natural-language request. Explicit invocation
remains the user's discovery check.

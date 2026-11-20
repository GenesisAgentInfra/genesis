# 安装 Genesis

<p><a href="install.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong></p>

Genesis 有两部分：一个本地 CLI，和一个告诉 coding agent 怎么用它的 skill。安装就是把 CLI 装到你的机器上，再把 skill 复制到 agent 读取 skill 的目录里。

这一页可以直接交给 coding agent，让它从头到尾照着做。

## 需要什么

- macOS 或 Linux。Windows 没有测过。
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git。
- Python 3.12。不用自己装，机器上没有的话 uv 会下载。
- 一个能运行 shell 命令的 coding agent，并且会从下表中的某个目录加载 skill。

你要分析的项目什么都不用准备。Genesis 不安装它的依赖，不导入也不运行它的代码，也不联网。

## 安装

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

第一条命令把 CLI 装进 uv 的工具目录，不在任何项目里。第二条把 skill 复制到你的主目录，并记下它运行时用哪个 Python 环境。两条命令都不会碰你要分析的项目，在哪个目录下执行都可以。uv 可能会提示它的工具目录不在 `PATH` 里，这里不用管：第二条命令是用完整路径调用 CLI 的。

`--agent` 按你用的 coding agent 来选：

| 你用的 agent | 参数 | skill 装到哪里 |
| --- | --- | --- |
| Claude Code | `--agent claude` | `~/.claude/skills/genesis` |
| Codex | `--agent codex` | `~/.agents/skills/genesis` |
| Cursor、Gemini CLI、OpenCode、GitHub Copilot | `--agent codex` | `~/.agents/skills/genesis` |
| Claude Code 加上 Codex、Gemini CLI 或 GitHub Copilot | `--agent both` | 两个目录都装 |

这个参数选的是目录，不是产品：`codex` 指的是 `~/.agents/skills`。这是 Codex 读取的目录，按各家 2026 年 11 月的文档，第三行里的 agent 也读它。Genesis 只在 Claude Code 和 Codex 上测过。用其他 agent 的话，装完后确认一下它能列出这个 skill。

Cursor 和 OpenCode 也读 `~/.claude/skills`。如果你同时用 Claude Code 和它们中的一个，只用 `--agent claude` 就够了；用 `--agent both` 的话，它们会在两个地方都找到这个 skill。

如果你的 agent 这些目录都不读，也能用 Genesis：让它打开装好的 `SKILL.md`，照着文件做。skill 目录是自包含的，也可以整个复制到别的 skill 目录里。

## 检查是否装好

```sh
"$(uv tool dir --bin)/genesis" agent status
python3 -I ~/.claude/skills/genesis/scripts/run_genesis.py version
python3 -I ~/.agents/skills/genesis/scripts/run_genesis.py version
```

第一条会对每个装过的目录输出 `installed (current)`。后两条按 skill 的方式调用 CLI，一个目录一条：装在哪个目录就执行哪一条，它会输出 `genesis-ci` 和版本号。

## 开始使用

在 agent 里打开你想看的项目，直接提要求。见[使用说明](usage.zh-CN.md)。

Claude Code 和 Codex 会自己发现新装的 skill。如果 agent 里没有出现 `/genesis`（Codex 里是 `$genesis`），新开一个会话。

其他 agent 列出和调用 skill 的方式各不相同：Cursor 里在 Agent 对话框输入 `/`，找 `genesis`；Gemini CLI 里用 `/skills` 看找到了哪些。不管哪个 agent，直接用大白话提要求都可以，agent 会按 skill 的描述选中它。

如果 agent 是在当前会话里装的 Genesis，这个会话可能还没加载到 skill。它不用等：直接打开装好的 `SKILL.md` 照着做就行，skill 加载的就是这份文件。

## 只装到一个项目里

```sh
"$(uv tool dir --bin)/genesis" agent install --agent claude --scope project --repo /path/to/your/project
```

这样 skill 会写到那个项目里的 `.claude/skills/genesis`（或 `.agents/skills/genesis`），不写到主目录。这个目录会让 Git 忽略自己，因为里面记着你这台机器上的路径。项目里的每个人各装各的。

## 更新

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update
```

加了 `--update`，只有没被人改过的 skill 才会被替换。不加的话，已有的 skill 目录只要和要装的版本不一样，`agent install` 就不会动它。

## 卸载

```sh
rm -r ~/.claude/skills/genesis ~/.agents/skills/genesis
uv tool uninstall genesis-ci
```

只删你装过的那个 skill 目录。除此之外，Genesis 不会在项目之外写任何东西。在项目里它只写一个目录 `.genesis/`，结果不要了就删掉。

## 从源码目录安装

想用和测试时完全一致的依赖版本，或者要改 Genesis 本身，用这种方式。

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git ~/genesis
cd ~/genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

- 克隆到一个不会被清掉的地方，比如主目录。skill 用的就是这个目录里的 Python 环境（`.venv`）。目录被移动或删除后，skill 就不能用了，要把最后两条命令再执行一遍，并给最后一条加上 `--update`。
- 不要把 Genesis 克隆到你要分析的项目里。
- 更新：先 `git pull`，再执行最后两条命令，给最后一条加上 `--update`。
- 卸载：按上面删掉 skill 目录，再删掉这个源码目录。

## 出问题的时候

| 看到什么 | 原因 | 怎么办 |
| --- | --- | --- |
| `uv: command not found` | 没装 uv。 | [安装 uv](https://docs.astral.sh/uv/getting-started/installation/)，然后从头再来。 |
| `genesis: command not found` | uv 的工具目录不在 `PATH` 里。 | 用 `"$(uv tool dir --bin)/genesis"` 调用，或者执行 `uv tool update-shell` 后新开一个终端。 |
| `Executable already exists: genesis` | uv 的工具目录里已经有另一个叫 `genesis` 的程序。 | 不要覆盖它，改用[从源码目录安装](#从源码目录安装)。 |
| `Cannot install Genesis skill: Skill already exists or was edited` | 已经有一个 Genesis 的 skill 目录，和这个版本不一样。 | 加上 `--update`。如果那个目录是你自己改过的，先把它挪走。 |
| `Genesis skill environment is unavailable` | 安装时记下的 Python 环境不在了：uv 工具被卸载了，或者源码目录被移动、删除了。 | 重新安装，然后带 `--update` 再执行一次 `agent install`。 |
| agent 里没有 `/genesis` | 会话是在装 skill 之前开的，或者 skill 装到了你的 agent 不读的目录。 | 新开一个会话。执行 `agent status`，对照上面的表看装在哪里。 |
| `map prepare` 报 `Operation not permitted` 或 `Read-only file system` | agent 的沙箱不允许 Genesis 在你的项目里写 `.genesis/`。 | 给 agent 这个项目目录的写权限。 |
| `unsupported_repository` | 项目里没有 Genesis 能读的源码文件。 | 不是安装问题，Genesis 画不了这个项目。 |

# 安装 Genesis

<p><a href="install.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong></p>

Genesis 有两部分：一个本地 CLI，和一个告诉 coding agent 怎么用它的 skill。安装就是把 CLI 装到你的机器上，再把 skill 复制到 agent 读取 skill 的目录里。

安装可以直接交给 agent 来做：从“需要什么”到“开始使用”，按顺序照做即可。后面几节讲更新、卸载和其他装法，最后的表格是命令出错时查的。

## 需要什么

- macOS 或 Linux。Windows 没有测过。
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git。
- Python。CLI 跑在 Python 3.12 上，机器上没有的话 uv 会下载。skill 用 `python3` 启动 CLI，所以 `PATH` 里还要有一个 Python 3。装了命令行工具的 macOS 和大多数 Linux 系统都有，精简的容器镜像可能没有。
- 一个能运行 shell 命令的 agent，并且会从下表中的某个目录加载 skill。

你要分析的项目必须是 Git 仓库，并且至少有一次提交。除此之外什么都不用准备：Genesis 不安装它的依赖，不导入也不运行它的代码，也不联网。

## 安装

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

第一条命令把 CLI 装进 uv 的工具目录，不在任何项目里。第二条把 skill 复制到你的主目录，并记下它运行时用哪个 Python 环境。两条命令都不会碰你要分析的项目，在哪个目录下执行都可以。uv 可能会提示它放 `genesis` 命令的目录不在 `PATH` 里，这里不用管：第二条命令是用完整路径调用 CLI 的。

第一条命令需要联网：从 GitHub 下载 Genesis，从 PyPI 下载依赖，机器上没有 Python 3.12 时还要下载 Python。两条命令都会写项目之外的位置：第一条写 uv 的工具目录、Python 目录和缓存目录，第二条写 `~/.claude/skills` 或 `~/.agents/skills`。如果 agent 的沙箱不允许联网或不允许写项目之外的位置，它需要先请你批准这两条命令，或者由你自己在终端里执行。

包名是 `genesis-ci`，它装上的命令叫 `genesis`。uv 的升级和卸载命令用的是包名。

`--agent` 按你用的 agent 来选。本页所有 `agent install` 命令写的都是 `--agent claude`，每次都换成你自己的参数，更新时也一样。

| 你用的 agent | 参数 | skill 装到哪里 |
| --- | --- | --- |
| Claude Code | `--agent claude` | `~/.claude/skills/genesis` |
| Codex | `--agent codex` | `~/.agents/skills/genesis` |
| Cursor、Gemini CLI、OpenCode、GitHub Copilot | `--agent codex` | `~/.agents/skills/genesis` |
| Claude Code 加上 Codex、Gemini CLI 或 GitHub Copilot | `--agent both` | 两个目录都装 |

这个参数选的是目录，不是产品：`codex` 指的是 `~/.agents/skills`。这是 Codex 读取的目录，按各家 2026 年 11 月的文档，第三行里的 agent 也读它。Genesis 只在 Claude Code 和 Codex 上测过。用其他 agent 的话，装完后确认一下它能列出这个 skill。

Cursor 和 OpenCode 也读 `~/.claude/skills`。如果你同时用 Claude Code 和它们中的一个，只用 `--agent claude` 就够了；用 `--agent both` 的话，它们会在两个地方都找到这个 skill。

如果你的 agent 这些目录都不读，也能用 Genesis：让它打开装好的 `SKILL.md`，照着文件做。也可以把整个 skill 目录复制到本机的其他 skill 目录里。目录里记着 CLI 所在 Python 环境的路径，所以复制到另一台机器上不能用。`agent status` 和 `agent install --update` 也看不到复制出去的那份，每次更新后要重新复制。

## 检查是否装好

```sh
"$(uv tool dir --bin)/genesis" agent status
```

它会对每个装过的目录输出 `installed (current)`，对另一个目录输出 `not installed`。

如果输出 `different or locally edited`，说明这个 skill 目录和当前 CLI 现在会装出来的不一样。多半是装完 skill 之后 CLI 升级过，或者在别处重新装过：带 `--update` 再执行一次 `agent install`。如果目录是你自己改过的，`--update` 不会动它，先把目录挪走再安装。

然后按 skill 的方式调用一次 CLI，它会输出 `genesis-ci` 和版本号。用 `--agent claude` 装的：

```sh
python3 -I ~/.claude/skills/genesis/scripts/run_genesis.py version
```

用 `--agent codex` 装的：

```sh
python3 -I ~/.agents/skills/genesis/scripts/run_genesis.py version
```

## 开始使用

在 agent 里打开你想看的项目，直接提要求。见[使用说明](usage.zh-CN.md)。

Claude Code 和 Codex 会自己发现新装的 skill。如果 agent 里没有出现 `/genesis`（Codex 里是 `$genesis`），新开一个会话。

其他 agent 列出和调用 skill 的方式各不相同：Cursor 里在 Agent 对话框输入 `/`，找 `genesis`；Gemini CLI 里用 `/skills` 看找到了哪些。不管哪个 agent，直接用大白话提要求都可以，agent 会按 skill 的描述选中它。

如果 agent 是在当前会话里装的 Genesis，这个会话可能还没加载到 skill。它不用等：直接打开装好的 `SKILL.md` 照着做就行，skill 加载的就是这份文件。

## 更新

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update
```

`--agent` 要和安装时一样。换了参数，命令可能会在另一个目录里再装一份，而你的 agent 实际读取的那一份可能没有更新。

加了 `--update`，只有没被人改过的 skill 才会被替换。不加的话，已有的 skill 目录只要和要装的版本不一样，`agent install` 就不会动它。

## 卸载

装到了哪个目录，就删哪个目录里的 skill，然后卸载 CLI：

```sh
rm -r ~/.claude/skills/genesis    # installed with --agent claude or both
rm -r ~/.agents/skills/genesis    # installed with --agent codex or both
uv tool uninstall genesis-ci
```

第一行对应用 `--agent claude` 或 `both` 装的，第二行对应用 `--agent codex` 或 `both` 装的。除此之外，Genesis 不会在项目之外写任何东西。在项目里它只写一个目录 `.genesis/`，结果不要了就删掉。

## 只装到一个项目里

这种装法代替[安装](#安装)里的第二条命令。CLI 本身还是用第一条装。

```sh
"$(uv tool dir --bin)/genesis" agent install --agent claude --scope project --repo /path/to/your/project
```

`--repo` 必须是项目的 Git 根目录，也就是包含 `.git` 的那个目录。skill 会写到那个项目里的 `.claude/skills/genesis`（或 `.agents/skills/genesis`），不写到主目录。这个目录会让 Git 忽略自己，因为里面记着你这台机器上的路径。项目里的每个人各装各的。

`agent status` 和 `agent install --update` 默认只看主目录，要加上同样的 `--scope project --repo`。检查是否装好：

```sh
"$(uv tool dir --bin)/genesis" agent status --scope project --repo /path/to/your/project
python3 -I /path/to/your/project/.claude/skills/genesis/scripts/run_genesis.py version
```

更新：

```sh
uv tool upgrade genesis-ci
"$(uv tool dir --bin)/genesis" agent install --agent claude --update --scope project --repo /path/to/your/project
```

卸载时删掉项目里的 skill 目录。CLI 没有别处在用的话，也一起卸载：

```sh
rm -r /path/to/your/project/.claude/skills/genesis
uv tool uninstall genesis-ci
```

用 `--agent codex` 装的，把这些路径里的 `.claude` 换成 `.agents`。

## 从源码目录安装

想用和测试时完全一致的依赖版本，uv 的工具目录里已经有另一个叫 `genesis` 的程序，或者要改 Genesis 本身，用这种方式。

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git ~/genesis
cd ~/genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

- 克隆到一个不会被清掉的地方，比如主目录。skill 用的就是这个目录里的 Python 环境（`.venv`）。目录被移动后，skill 就不能用了，要在新位置把最后两条命令再执行一遍，并给最后一条加上 `--update`；目录被删掉的话，先重新克隆。
- 不要把 Genesis 克隆到你要分析的项目里。
- 如果已经按 [CONTRIBUTING.md](../CONTRIBUTING.md) 配好了开发环境，跳过 `uv sync` 那一行，它会把测试和 lint 工具从 `.venv` 里删掉。
- 本页其他地方写 `"$(uv tool dir --bin)/genesis"` 的命令，都换成 `uv run --project ~/genesis --package genesis-ci --no-dev --frozen genesis`，在哪个目录下执行都可以。`uv tool upgrade genesis-ci` 换成 `git -C ~/genesis pull`，`uv tool uninstall genesis-ci` 不用执行。比如检查是否装好：`uv run --project ~/genesis --package genesis-ci --no-dev --frozen genesis agent status`。`python3 -I ... run_genesis.py version` 这一步和上面一样。
- 更新：先 `git pull`，再执行最后两条命令，给最后一条加上 `--update`。
- 卸载：按[卸载](#卸载)里说的删掉 skill 目录，再删掉这个源码目录。不用执行 `uv tool uninstall`。

## 出问题的时候

| 看到什么 | 原因 | 怎么办 |
| --- | --- | --- |
| `uv: command not found` | 没装 uv。 | [安装 uv](https://docs.astral.sh/uv/getting-started/installation/)，然后从头再来。 |
| `genesis: command not found` | uv 放 `genesis` 命令的目录（`uv tool dir --bin`）不在 `PATH` 里。 | 用 `"$(uv tool dir --bin)/genesis"` 调用，或者执行 `uv tool update-shell` 后新开一个终端。 |
| `python3: command not found` | `PATH` 里没有 Python 3。uv 为 CLI 下载的那份不会放进 `PATH`。 | 用系统的包管理器装一个 Python 3，然后重新检查。 |
| `Executable already exists: genesis` | uv 的工具目录里已经有另一个叫 `genesis` 的程序。 | 不要覆盖它，改用[从源码目录安装](#从源码目录安装)。 |
| `Another version of the Genesis skill is installed` | 已经装着另一个版本的 Genesis skill，而且没被改过。 | 加上 `--update`。 |
| `Skill folder was edited, or was not installed by Genesis` | 这个目录被手工改过，或者是别的工具装的同名 `genesis` skill。 | 把这个目录挪走，再重新安装。 |
| `Skill destination cannot contain symbolic links` | `~/.claude`、`~/.agents`、它们下面的 `skills` 目录，或者 `genesis` 目录本身是符号链接。Genesis 不通过链接读写文件，所以 `agent install` 和 `agent status` 都会停下。 | 如果一个 `skills` 目录链接到另一个，就用对应的参数装到真实的那个目录，`agent status` 也带上同一个 `--agent`。读取链接目录的 agent 会通过链接找到 skill。其他情况下，用另一个参数装到不是链接的那个目录，再按[安装](#安装)里说的把整个 `genesis` 目录复制到链接的那个目录。 |
| `Genesis skill environment is unavailable` | 安装时记下的 Python 环境不在了：uv 工具被卸载了，或者源码目录被移动、删除了。 | 重新安装，然后带 `--update` 再执行一次 `agent install`。 |
| agent 里没有 `/genesis` | 会话是在装 skill 之前开的，或者 skill 装到了你的 agent 不读的目录。 | 新开一个会话。执行 `agent status`，对照上面的表看装在哪里。 |
| `uv tool install` 或 `agent install` 报 `Operation not permitted`、`Read-only file system`，或者下载失败 | agent 的沙箱不允许联网，或不允许写项目之外的位置。 | 批准这条命令在沙箱外执行，或者自己在终端里执行这两条安装命令。 |
| `map prepare` 报 `cannot_write`、`Operation not permitted` 或 `Read-only file system` | Genesis 没法在你的项目里写 `.genesis/`：agent 的沙箱拦住了，或者这个目录不可写。 | 给 agent 这个项目目录的写权限。 |
| `git_read_failed` | Git 读不了这个项目。最常见的原因是这个目录不在任何 Git 仓库里：项目还没用 Git 管理，或者这只是一个放了几个仓库的文件夹。 | 在仓库目录里打开 agent。项目还没用 Git 管理的话，先在里面执行 `git init` 并提交代码。 |
| `revision_unavailable` | 仓库里还没有任何提交，或者你要对比的版本不在本地克隆里。 | 先提交代码，或者先把那个版本 fetch 下来，再问一次。 |
| `unsupported_repository` | 项目里没有 Genesis 能读的源码文件。 | 不是安装问题，Genesis 画不了这个项目。 |

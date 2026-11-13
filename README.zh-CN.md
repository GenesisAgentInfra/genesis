<p align="center">
  <img src="assets/readme/favicon.svg" alt="Genesis 图标" width="52" height="52" align="middle">&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong></p>

Genesis 把一个代码仓库变成一张业务流程图，每一步都有对应的代码作为依据；并且展示一次改动对这些流程做了什么：碰到了哪些步骤，现有的测试有没有覆盖到新的行为。

- **CLI 是确定性的。** 它冻结一份代码快照、提取事实、找出入口、校验收到的每一条描述，并渲染结果。它不调用任何模型和服务，也从不导入或运行它读到的代码。
- **阅读代码的是你的编码助手。** 通过自带的技能，Codex 或 Claude Code 用业务语言描述每条流程；CLI 对照代码依据，整条接受或整条拒绝。

## 目前支持

- Python 源码。
- 当前代码的完整流程图，以及相对某个版本的改动在图上的位置。
- 测试结论来自阅读测试源码。Genesis 不运行测试。

## 开始使用

在你要分析的项目之外安装 CLI：

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git
cd genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

`--agent` 可以是 `codex`、`claude` 或 `both`。然后在要分析的项目里，让你的编码助手梳理项目的业务流程，或者说明一次改动对流程的影响；也可以直接点名技能：Claude Code 里用 `/genesis`，Codex 里用 `$genesis`。

结果写在该项目的 `.genesis/` 目录下：一个用浏览器打开的页面（`view.html`）和一份摘要（`summary.md`）。

## 命令

| 命令 | 作用 |
| --- | --- |
| `genesis agent install` | 让你的编码助手能发现 Genesis；不做分析，不上传任何内容。 |
| `genesis agent status` | 检查已安装的技能文件。 |
| `genesis map prepare` | 冻结快照、提取事实，写出静态骨架。 |
| `genesis map plan` | 把入口归并成流程，每条流程建一个任务。 |
| `genesis map status` | 列出任务、它们的状态和还缺什么。 |
| `genesis map context` | 开始一个任务所需的全部内容。 |
| `genesis map query` | 查看一个符号及其相邻关系，或搜索冻结的源码。 |
| `genesis map read` | 读取某条依据引用背后的冻结源码。 |
| `genesis map submit` | 校验一个任务的一次提交；整条接受或整条拒绝。 |
| `genesis map diff` | 列出相对基准版本改了什么，以及它们落在图上的位置。 |
| `genesis map render` | 为一次会话写出页面和摘要。 |

`map` 这组命令由编码助手替你执行；列在这里是为了让你知道它做了什么。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `packages/genesis_ci` | CLI：快照、Python 事实提取、流程图工作流、助手技能。 |
| `packages/genesis_contracts` | CLI 读写的各种文件的结构定义。 |
| `viewer/` | `genesis map render` 写出的页面的源码。 |
| `fixtures/business-map` | 每种结构的一份完整示例。 |

## 开发

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Genesis 自身的代码采用 [Apache-2.0](LICENSE) 许可。打包进来的组件保留各自的许可证，见 [NOTICE](NOTICE) 和[第三方声明](THIRD_PARTY_NOTICES.md)。

<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">让你的编程 Agent 看懂代码变更。</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">官网</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>开始使用</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">文档</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">Star History</a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <a href="README.ko.md">한국어</a> &nbsp;·&nbsp; <a href="README.de.md">Deutsch</a> &nbsp;·&nbsp; <a href="README.fr.md">Français</a> &nbsp;·&nbsp; <a href="README.es.md">Español</a></p>

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
      <img src="assets/readme/code-intelligence-animation.gif" alt="代码审查流程示意：从 Python 代码变更，经上下文、行为和风险分析，生成审查报告。" width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">代码审查流程示意</a></sub></p>

<a id="genesis-get-started"></a>

## 在你的编程 Agent 中开始使用

CLI 和静态分析部分开源。语义审查由 Genesis 托管服务完成，发送源码前需要获得你的授权。

### 1. 完成一次安装

在要审查的项目中，把下面的提示词粘贴给 Codex 或 Claude Code：

```text
请从 https://github.com/GenesisAgentInfra/genesis-cli 安装 Genesis。
先阅读 README 和 docs/coding-agents.md，把 CLI 安装在当前项目之外，
并为我正在使用的 Agent 安装用户级 genesis-review skill。
已有安装就复用。检查 CLI 版本和 skill 安装状态。
这一步只安装，不审查、不上传代码。
```

Agent 的运行环境需要 Shell 访问权限、Git、Python 3.12+ 和 uv 0.13.7。
目前通过源码安装，尚未发布到 PyPI。
[远程或云端环境与 skill 发现说明](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md#maintenance-and-troubleshooting)。

<details>
<summary>手动安装</summary>

在待审查应用的仓库之外执行：

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Claude Code 使用 `--agent claude`，同时安装到两种 Agent 则使用 `--agent both`。
默认安装范围为用户级。安装器会保留已有的 Agent 指令、权限、凭据，以及与当前版本不同的既有 skill。

[安装选项与故障排查](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md)。

</details>

### 2. 发起审查

如果看不到新安装的 skill，先开启一个新的 Agent 会话，然后输入：

```text
用 Genesis 审查我当前未提交的改动。
解释这些改动会怎样影响用户、有哪些主要风险，以及还需要测试什么。
上传前先展示将要发送的源码片段。
```

也可以明确选择 skill：

| Agent | 调用方式 |
| --- | --- |
| Codex | `$genesis-review` 后接你的请求 |
| Claude Code | `/genesis-review` 后接你的请求 |

需要其他审查范围时，请指定分支比较或两个提交。任务描述和流程图都是可选上下文。

未配置个人连接设置时，可以直接使用官方共享试用，无需执行 `genesis auth`。
试用额度有限，由所有用户共享。无需提供模型供应商的 API key。
[访问方式与试用限制](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial)。

## 审查涵盖哪些内容

| 维度 | 你会获得什么 |
| --- | --- |
| 业务行为 | 通过改动前后的代码证据，说明应用行为可能发生的变化。 |
| 受影响路径 | 与改动关联的调用方、代码路径，以及你提供的流程图。 |
| 成本、等待与失败 | 基于现有证据的条件性风险分析和静态估算。 |
| 测试 | 相关测试源码检查了什么，以及可能缺少哪些断言。 |
| 验证 | 建议执行的检查，以及仍然缺少的证据。 |

Genesis 分析 Python 源码，不执行应用或测试。缺失的需求和无法确定的行为会明确保留为审查缺口。

## 从代码改动到审查报告

1. **本地准备。** Genesis 捕获所选改动并提取代码证据。Agent 会展示选中待上传的源码片段与事实。
2. **授权上传。** 获得你的授权后，Genesis 才会把这些材料发送到托管服务。你也可以仅在本地分析，获得一份部分报告。
3. **在对话中阅读结果。** Agent 解释报告、核对证据与状态，并指出仍需验证的内容。

报告保存在项目的 `.genesis/analyses/<run-id>/` 目录：

- `summary.md`：从易读的摘要开始。
- `report.md`：查看详细发现、证据和状态。
- `report.json`：在你自己的工具中使用结构化结果。

退出码：**0** 表示在声明的范围内完成分析，**2** 表示产出了可用的部分报告，**1** 表示无法产出所请求的结果。
不要将 `.genesis/` 提交到 Git，其中可能包含捕获的源码。

## 源码与服务

公开仓库包含 CLI 和静态分析部分。私有语义服务由 Genesis 团队运营，仓库不提供可自托管的服务端实现。

预览和离线分析均在本地完成。安装 skill 不会开启每次编辑后的自动审查。

[数据处理、个人密钥与配置](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md)。

<a id="genesis-docs"></a>

## 文档

- [编程 Agent 指南](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md)：安装、skill 发现、团队指令和故障排查。
- [CLI 指南](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md)：命令、可选上下文、凭据和数据处理。
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md)：配置仓库自动化；使用托管分析时需要明确提供 Genesis key。
- [参与开发](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md)：开发与测试客户端。
- [仓库边界](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md)和[报告 Schema](https://github.com/GenesisAgentInfra/code-intelligence-protocol)。

<a id="genesis-stars"></a>

## Star History

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="GenesisAgentInfra/genesis-cli 的 Star 历史" width="100%">
  </picture>
</a>

[在 Star History 查看](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## 许可证

Genesis CLI 的原创代码采用 [Apache-2.0](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE) 许可证。
该许可证不授予对单独运营的 Genesis 服务的访问权限。
捆绑组件保留各自的许可证，详见 [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)
和[第三方声明](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md)。

<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">为你的 Agent 的每一次变更提供护栏。</h1>

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

<a id="genesis-benchmarks"></a>

## 基准对比

<picture>
  <source media="(max-width: 600px)" srcset="assets/readme/agent-change-benchmarks-mobile.svg">
  <img src="assets/readme/agent-change-benchmarks.svg" alt="以下为排版预览用的模拟数据，并非实测结果。" width="100%">
</picture>

## 为什么需要 Genesis

看清一次代码改动，会怎样改变 Agent 交付给用户的结果。

| 业务影响 | Genesis 帮你审查什么 |
| --- | --- |
| **Agent 一直在忙，用户却拿不到结果。** [来源](https://github.com/openai/openai-agents-python/issues/191) | 任务完成和停止条件的变化。 |
| **用户点了拒绝，操作却照常执行。** [来源](https://github.com/langchain-ai/langchain/issues/40492) | 审批检查与操作执行路径的变化。 |
| **用户只请求一次，同一个操作却执行两次。** [来源](https://github.com/langchain-ai/langgraph/issues/9185) | 重试路径与防止重复操作的检查。 |
| **同样的任务，消耗更多 token。** [来源](https://github.com/microsoft/agent-framework/issues/5049) | 提示词膨胀与额外模型调用。 |
| **任务还能完成，用户却要等更久。** [来源](https://github.com/openai/openai-agents-python/issues/2386) | 阻塞调用与串行执行步骤。 |

<a id="genesis-get-started"></a>

## 在你的编程 Agent 中开始使用

CLI 和静态分析部分开源。语义审查由 Genesis 托管服务完成，发送源码前需要获得你的授权。

### 1. 为当前项目配置一次

在要审查的项目中，把下面的提示词粘贴给 Codex 或 Claude Code：

```text
请从 https://github.com/GenesisAgentInfra/genesis-cli 接入 Genesis。
先读 README 和 docs/coding-agents.md，把 CLI 安装在当前项目之外，
并为我当前使用的 Agent 安装用户级 genesis-review skill。
已有安装就复用；需要时更新未经用户修改的托管 skill。
按照 docs/coding-agents.md 的 “Configure CR preparation in this project”，
在当前项目的 Agent 指令文件中加入准备 CR/PR 前先运行 Genesis 的约定，
保留其他现有内容。检查 CLI、skill 和项目约定，并告诉我修改了哪个文件。
这一步只配置，不审查、不上传代码；以后的上传仍需获得覆盖目标服务和所选源码的授权。
```

**配置后的体验：**你照常说“帮我整理这次改动，准备发 CR”，项目指令会要求 Agent
先运行 Genesis、解释结果，再整理 CR/PR 描述。没有固定口令，也不限中文：
“发 CR”“提 PR”“提审”“帮我写这次改动的 PR 描述”，以及英文的 “open a PR”
“raise an MR”，都属于把改动交给别人审查的意图；单独 commit 或 push 不自动触发。
这个流程在本地发起，不依赖 GitHub CI。
它是 Agent 的默认工作约定，不保证每次触发，也不是 Git hook 或合并门禁。
skill 安装在用户级，但这项审查约定只配置到当前项目；只安装 CLI 不会添加约定。
手动安装、已有用户升级和移除方式见[项目配置指南](docs/coding-agents.md#configure-cr-preparation-in-this-project)。

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

</details>

### 2. 照常准备 CR/PR

```text
帮我整理这次改动，准备发 CR/PR。
先解释审查发现和未验证的部分，再整理提交 review 的描述。
上传前先展示发送范围。
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

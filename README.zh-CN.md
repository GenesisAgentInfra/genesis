<p align="center">
  <img src="assets/readme/favicon.svg" alt="Genesis 图标" width="52" height="52" align="middle">&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">把 agent 的改动画出来。<br>看清哪里会出问题。</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="许可证：Apache-2.0"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis/stargazers"><img src="https://img.shields.io/github/stars/GenesisAgentInfra/genesis?style=flat-square" alt="GitHub stars"></a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong></p>

<p align="center">
  <a href="assets/readme/genesis-demo.mp4"><img src="assets/readme/flow-demo.webp" alt="下单流程一步步画出来，然后四处改动带着测试结论落上去；扣款一步被标为风险" width="900"></a>
  <br>
  <a href="assets/readme/genesis-demo.mp4"><b>▶ 观看 37 秒演示视频</b></a>
</p>

Genesis 把你的代码库画成一张业务流程图，告诉你 agent 的哪些改动没测到、哪些有风险。它作为一个 skill 跑在 Claude Code 和 Codex 里，Python、TypeScript、JavaScript、Go、Java、Rust 等大多数常见语言的项目都能用，其中 Python 的结果最准。

## 快速开始

最省事的办法是让你的 coding agent 来装。在 agent 里打开你自己的项目，把下面这句话发给它：

```text
按 https://raw.githubusercontent.com/GenesisAgentInfra/genesis/main/docs/install.zh-CN.md 安装 Genesis，然后用它看看我最近一次提交改了什么，最后告诉我怎么打开结果。
```

也可以自己装。需要先有 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git，系统是 macOS 或 Linux：

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

用 Codex 就把参数换成 `--agent codex`，两个都用就换成 `--agent both`。其他 agent 怎么装，以及更新、卸载和常见问题，见[安装说明](docs/install.zh-CN.md)。

然后在 Claude Code 里打开你自己的项目。一共两个命令：

```text
/genesis map
/genesis review main
```

`map` 画出系统现在的样子，帮你看懂它。`review` 告诉你相对某个版本（这里是 `main`）改了什么，有没有测试管着。你也可以直接用大白话问。

Codex 里对应的是 `$genesis`。跑完之后用浏览器打开 `.genesis/out/latest/view.html`。旁边的 `summary.md` 可以直接贴进 PR。页面怎么看、还有哪些文件，见[使用说明](docs/usage.zh-CN.md)。

## 你会看到什么

假设你让 agent 加一个游客下单。它做了，顺手还改了另外三处。Genesis 画出下单流程，把这四处改动都标在上面：

<p align="center">
  <img src="assets/readme/flow-map.png" alt="下单流程的前半段：按游客还是已登录、有没有库存、是否满包邮门槛分支" width="820">
</p>

| 对顾客改变了什么 | 有测试吗 |
| --- | --- |
| 扣款超时会重试，最多 3 次，但没带幂等键。顾客可能被扣两次钱。 | 🔴 没有测试走到。没有哪个测试模拟过支付超时。 |
| 扣款期间不再锁库存。两个人可能同时买走最后一件。 | 🟡 只是走到。测试跑过这段代码，但没测两个人抢最后一件。 |
| 顾客留个邮箱就能以游客身份下单。 | ⚪ 不确定。游客下单的测试把邮箱校验替换掉了。 |
| 包邮门槛从 $50 降到 $35。 | ✅ 有测试覆盖。测试下了 $34.99、$35.00、$35.01 三种订单。 |

点开任意一步，能看到它背后的代码和碰到它的测试：

<p align="center">
  <img src="assets/readme/change-detail.png" alt="打开扣款这一步：风险说明、对顾客改变了什么，以及测试结论背后的依据" width="640">
</p>

## 能信吗

代码是 agent 读的，但它说了不算。它写下的每一步都必须引用对应的那几行代码，Genesis CLI 会拿冻结的仓库快照逐条核对。有一条对不上，整份描述就被退回，agent 重写。对 Python，Genesis 还会自己解析代码，agent 漏画了分支，图上会标 `partial`。

CLI 不调用任何模型，不往外发任何东西，也不会运行你的代码。

## 评测

Claude Code 和 Codex 分别在装和不装 Genesis 的情况下，分析了 5 个开源 Python 仓库的 10 个提交。提问用的是用户平时会说的话：这个提交改了什么，会不会弄坏别的功能，测试能不能兜住。每个答案都由自动化的读者对照标准答案计分，标准答案根据代码和测试建立。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/benchmark-zh-dark.svg">
    <img src="assets/readme/benchmark-zh-light.svg" width="860" alt="Claude Code 和 Codex 在不用与使用 Genesis 时的四项指标。覆盖判断正确：79% 到 88%，76% 到 80%。测试跑到但兜不住的改动被答案指出：8% 到 38%，4% 到 23%。受影响的入口被点名：32% 到 47%，15% 到 24%。提出的风险中真实的比例：44% 到 64%，54% 到 72%。">
  </picture>
</p>

|  | Claude Code | Claude Code + Genesis | Codex | Codex + Genesis |
| --- | ---: | ---: | ---: | ---: |
| 覆盖判断正确的改动 | 79% | 88% | 76% | 80% |
| 测试跑到但兜不住的改动，被答案指出 | 8% | 38% | 4% | 23% |
| 受影响的入口被点名 | 32% | 47% | 15% | 24% |
| 点名的入口里正确的比例 | 67% | 68% | 71% | 54% |
| 每次运行提出的风险 | 6.1 | 4.2 | 4.5 | 3.3 |
| &nbsp;&nbsp;真实 | 2.9 | 2.8 | 2.4 | 2.4 |
| &nbsp;&nbsp;不成立 | 2.1 | 0.7 | 1.4 | 0.5 |
| &nbsp;&nbsp;仅凭代码无法判断 | 1.2 | 0.7 | 0.7 | 0.4 |
| 提出的风险中真实的比例 | 44% | 64% | 54% | 72% |

使用 Genesis 后，两个 agent 都能指出更多“测试跑到但兜不住”的改动，点名更多受改动影响的入口，提出的风险里经不起对照代码核对的也更少。它们找到的真实风险和原来差不多，Codex 点名的入口里正确的比例下降了。样本不大：10 个提交，每个运行 3 次。

每个指标的含义和完整结果，见[变更分析评测](docs/change-analysis-benchmark.zh-CN.md)。

## 局限

- Python 的结果最准确，因为 Genesis 会解析它。其他语言也能用：由你的 agent 读代码，Genesis 逐步对照源码核对，但 agent 漏掉的路径不会被标出来。
- 测试结论是读测试代码得出的，Genesis 不会去跑测试。
- 风险是 agent 读代码时注意到的，没有规则引擎。

## 文档

- [安装说明](docs/install.zh-CN.md)：需要什么，哪个 agent 用哪个参数，怎么更新、卸载，出问题怎么办。
- [使用说明](docs/usage.zh-CN.md)：怎么问，结果在哪里，页面怎么看。
- [评测](docs/change-analysis-benchmark.zh-CN.md)：测了什么，以及完整结果。
- [AGENTS.md](AGENTS.md)：写给被指到这个仓库来的 coding agent。

## 许可证

[Apache-2.0](LICENSE)。随附组件保留各自的许可证，见 [NOTICE](NOTICE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。想参与开发，看 [CONTRIBUTING.md](CONTRIBUTING.md)。

## Star 增长

<p align="center">
  <a href="https://star-history.com/#GenesisAgentInfra/genesis&Date"><img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis&type=Date" alt="Star 增长曲线： GenesisAgentInfra/genesis" width="640"></a>
</p>

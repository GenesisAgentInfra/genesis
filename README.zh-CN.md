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

https://github.com/user-attachments/assets/ceeb6ae9-0ee7-4d26-aae6-93599befc805

Genesis 把你的代码库画成一张业务流程图，告诉你 agent 的哪些改动没测到、哪些有风险。它作为一个 skill 跑在 Claude Code 和 Codex 里，Python、TypeScript、JavaScript、Go、Java、Rust 等大多数常见语言的项目都能用，其中 Python 的结果最准。

## 评测

**一个 PR 把 `>` 改成了 `>=`，你的测试会发现吗？** 测试可以每次都跑到这一行，却从没测过两个值刚好相等的情况。

我们评测了 5 个开源 Python 项目的 10 个提交，其中有 33 处改动，即使撤回，跑到那段代码的测试依然会通过。装上 Genesis 后，Claude Code 和 Codex 在评审中指出这类盲点的次数都是原来的 **5 倍左右**。

| 正确指出盲点的次数 | 只用 agent | 装上 Genesis |
| --- | ---: | ---: |
| Claude Code | 8 / 99 | **38 / 99** |
| Codex | 4 / 99 | **23 / 99** |

每个 agent 在每种配置下都对每个提交评审三遍，33 处盲点各出现三次，共 99 次机会。测试能否发现改动，由模型阅读源码和测试后判断。[完整结果与评测方法](docs/change-analysis-benchmark.zh-CN.md)

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

然后在 Claude Code 里打开你自己的项目。这个项目必须是 Git 仓库，并且至少有一次提交。接着提下面两种要求之一：

```text
/genesis map
/genesis review main
```

`map` 画出系统现在的样子，帮你看懂它。`review` 告诉你相对某个版本（这里是 `main`）改了什么，有没有测试管着。你也可以直接用大白话问。

Codex 里对应的是 `$genesis`。跑完之后用浏览器打开 `.genesis/out/latest/view.html`。旁边的 `summary.md` 可以直接贴进 PR。页面怎么看、还有哪些文件，见[使用说明](docs/usage.zh-CN.md)。

## 你会看到什么

假设你让 agent 加一个游客下单。它做了，顺手还改了另外三处。Genesis 画出下单流程，把这四处改动都标在上面：

<p align="center">
  <img src="assets/readme/flow-map.png" alt="结账流程的前半段：已登录还是留邮箱的游客、逐件查库存、包邮门槛和扣款，步骤上标着编号的改动、测试结论和风险" width="820">
</p>

| 对顾客改变了什么 | 有测试吗 |
| --- | --- |
| 扣款超时会重试，最多 3 次，但没带幂等键。顾客可能被扣两次钱。 | 🔴 未找到覆盖。没有哪个测试模拟过支付超时。 |
| 扣款期间不再锁库存。两个人可能同时买走最后一件。 | 🟡 缺少行为验证。测试跑过这段代码，但没测两个人抢最后一件。 |
| 顾客留个邮箱就能以游客身份下单。 | ⚪ 覆盖待确认。游客下单的测试用例来自仓库外的一个包，光读代码看不出它们测了什么。 |
| 包邮门槛从 $50 降到 $35。 | ✅ 有行为验证。测试下了 $34.99、$35.00、$35.01 三种订单。 |

这些是页面上的叫法。`summary.md` 里同样的四种结论写作 not reached、reached only、unknown 和 covered，对照见[使用说明](docs/usage.zh-CN.md#测试结论)。

点开任意一步，能看到这一步改了什么、测试结论和理由，以及背后的代码：

<p align="center">
  <img src="assets/readme/change-detail.png" alt="打开扣款这一步：扣款超时重试不带幂等键的风险，以及改了什么" width="640">
</p>

## 能信吗

代码是 agent 读的，但它说了不算。它写下的每一步都必须引用对应的那几行代码，Genesis CLI 会拿冻结的仓库快照逐条核对。有一条对不上，整份描述就被退回，agent 重写。对 Python，Genesis 还会自己解析代码：agent 漏画了分支，`summary.md` 里的结果就会标成 `partial`。画地图时，页面顶部也会显示“部分完成”；看改动时页面上没有这个标记，要看 `summary.md`。

看改动时，改动清单是 Genesis 对比两个版本的代码自己算出来的，不靠 agent 去找。每处改动的含义、测试结论和风险是 agent 的判断。只有明显站不住的结论会被 CLI 退回：标成“有行为验证”（covered），却没有引用任何带断言的测试；或者在 Python 项目里，有测试直接调用了改动的函数，却标成“未找到覆盖”（not reached）。其他语言里，引用的测试有没有断言，是 agent 自己说的。

CLI 不调用任何模型，不往外发任何东西，也不会运行你的代码。

## 局限

- Python 的结果最准确，因为 Genesis 会解析它。其他语言也能用：由你的 agent 读代码，Genesis 拿源码核对它写下的每一步，但 agent 漏掉的路径不会被标出来。
- 测试结论是读测试代码得出的，Genesis 不会去跑测试。
- 风险是 agent 读代码时注意到的，没有规则引擎。

## 文档

- [安装说明](docs/install.zh-CN.md)：需要什么，哪个 agent 用哪个参数，怎么更新、卸载，出问题怎么办。
- [使用说明](docs/usage.zh-CN.md)：怎么问，结果在哪里，页面怎么看。
- [评测](docs/change-analysis-benchmark.zh-CN.md)：测了什么，以及完整结果。
- [AGENTS.md](AGENTS.md)：写给 coding agent，用户让它安装、使用或修改 Genesis 时先读这里。

有问题或发现 bug，请到 [GitHub issues](https://github.com/GenesisAgentInfra/genesis/issues) 提。安全问题请按 [SECURITY.md](SECURITY.md) 的说明私下报告。

## 许可证

[Apache-2.0](LICENSE)。随附组件保留各自的许可证，见 [NOTICE](NOTICE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。想参与开发，看 [CONTRIBUTING.md](CONTRIBUTING.md)。

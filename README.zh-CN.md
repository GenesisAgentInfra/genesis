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
  <img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square" alt="Python 3.12">
  <a href="https://github.com/GenesisAgentInfra/genesis/stargazers"><img src="https://img.shields.io/github/stars/GenesisAgentInfra/genesis?style=flat-square" alt="GitHub stars"></a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <strong>简体中文</strong></p>

<p align="center">
  <a href="assets/readme/genesis-demo.mp4"><img src="assets/readme/flow-demo.webp" alt="下单流程一步步画出来，然后四处改动带着测试结论落上去；扣款一步被标为风险" width="900"></a>
  <br>
  <a href="assets/readme/genesis-demo.mp4"><b>▶ 观看 37 秒演示视频</b></a>
</p>

Genesis 把你的代码库画成一张业务流程图，告诉你 agent 的哪些改动没测到、哪些有风险。它作为一个 skill 跑在 Claude Code 和 Codex 里。

## 快速开始

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git
cd genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

用 Codex 的话，把最后的参数换成 `--agent codex` 或 `--agent both`。

然后在 Claude Code 里打开你自己的项目。一共两个命令：

```text
/genesis map
/genesis review main
```

`map` 画出系统现在的样子，帮你看懂它。`review` 告诉你相对某个版本（这里是 `main`）改了什么，有没有测试管着。你也可以直接用大白话问。

Codex 里对应的是 `$genesis`。跑完之后用浏览器打开 `.genesis/view.html`。旁边的 `summary.md` 可以直接贴进 PR。

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

## 局限

- Python 的结果最准确，因为 Genesis 会解析它。其他语言也能用：由你的 agent 读代码，Genesis 逐步对照源码核对，但 agent 漏掉的路径不会被标出来。
- 测试结论是读测试代码得出的，Genesis 不会去跑测试。
- 风险是 agent 读代码时注意到的，没有规则引擎。

## 许可证

[Apache-2.0](LICENSE)。随附组件保留各自的许可证，见 [NOTICE](NOTICE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。想参与开发，看 [CONTRIBUTING.md](CONTRIBUTING.md)。

## Star 增长

<p align="center">
  <a href="https://star-history.com/#GenesisAgentInfra/genesis&Date"><img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis&type=Date" alt="Star 增长曲线： GenesisAgentInfra/genesis" width="640"></a>
</p>

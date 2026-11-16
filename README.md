<p align="center">
  <img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle">&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h3 align="center">See what your agent built.<br>Catch what it left untested.</h3>

<p align="center"><strong>English</strong> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a></p>

<p align="center">
  <a href="assets/readme/genesis-demo.mp4"><img src="assets/readme/flow-demo.webp" alt="A checkout flow drawing itself step by step, then its four changes landing with test verdicts; the card charge is marked as a risk" width="900"></a>
  <br>
  <a href="assets/readme/genesis-demo.mp4"><b>▶ Watch the 37-second demo</b></a>
</p>

Coding agents write code faster than you can read it. Genesis turns your repo into a
flow map in plain language, then shows where each change lands on that map and whether
a test checks it.

## Quick start

```sh
git clone https://github.com/GenesisAgentInfra/genesis.git
cd genesis
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent claude
```

Use `--agent codex` or `--agent both` if you work in Codex.

Now open your own project in Claude Code and ask:

```text
/genesis map this project
/genesis what does my uncommitted work change, and is it tested?
/genesis review this branch against main
```

In Codex the skill is `$genesis`. When it finishes, open `.genesis/view.html` in a
browser. The `summary.md` next to it is ready to paste into a pull request.

## What you get

Say you asked your agent for guest checkout. It built that, and changed three other
things on the way. Genesis draws the checkout flow and puts all four changes on it:

<p align="center">
  <img src="assets/readme/flow-map.png" alt="The first half of the Place an order flow, branching on guest or signed in, stock, and the free-shipping threshold" width="820">
</p>

| What changed for shoppers | Is it tested? |
| --- | --- |
| A card charge that times out is retried up to 3 times, with no idempotency key. A shopper can be charged twice. | 🔴 Not reached. No test makes the payment time out. |
| Stock is no longer held while the card is charged. Two shoppers can pay for the last unit. | 🟡 Reached only. Tests run this code but none buys the last unit twice. |
| Shoppers can check out as a guest by leaving an email. | ⚪ Unknown. The guest test stubs out the email check. |
| Free shipping starts above $35 instead of $50. | ✅ Covered. Tests place orders at $34.99, $35.00 and $35.01. |

Click a step to see the code behind it and the tests that touch it:

<p align="center">
  <img src="assets/readme/change-detail.png" alt="The Charge the card step opened: the risk, what changed for shoppers, and the test evidence behind the verdict" width="640">
</p>

## Can I trust it?

Your agent does the reading, but it doesn't get the last word. Every step it writes has
to quote the lines of code it stands for, and the Genesis CLI checks each quote against
a frozen snapshot of your repo. If one doesn't match, the whole description is rejected
and the agent tries again. If the agent skips a branch, the map is marked `partial`.

The CLI calls no model, sends nothing anywhere, and never runs your code.

## Limits

- Python repositories only, for now.
- Test verdicts come from reading your tests. Genesis doesn't run them.
- Risks are what your agent noticed while reading. There is no rule engine.

## License

[Apache-2.0](LICENSE). Bundled components keep their own licenses, listed in
[NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Want to help?
See [CONTRIBUTING.md](CONTRIBUTING.md).

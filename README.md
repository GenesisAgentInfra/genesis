<p align="center">
  <img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle">&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Visualize your agent's changes.<br>See where they can break.</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="License: Apache-2.0"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis/stargazers"><img src="https://img.shields.io/github/stars/GenesisAgentInfra/genesis?style=flat-square" alt="GitHub stars"></a>
</p>

<p align="center"><strong>English</strong> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a></p>

https://github.com/user-attachments/assets/ceeb6ae9-0ee7-4d26-aae6-93599befc805

Genesis turns your codebase into a business flow map and shows which of your agent's
changes are untested or risky. It runs as a skill inside Claude Code and Codex, and
works on projects in Python, TypeScript, JavaScript, Go, Java, Rust and most other
common languages. Python gets the most accurate results.

## Benchmark

**A PR changes `>` to `>=`. Would your tests notice?** A test can run that line every
time and still miss the case where the two values are equal.

Across 10 commits from 5 open-source Python projects, we found 33 changes where tests
reached the code but would still pass if the change were undone. With Genesis, Claude
Code and Codex flagged these gaps **about 5× as often** in code review.

| Gaps correctly flagged | Agent alone | With Genesis |
| --- | ---: | ---: |
| Claude Code | 8 / 99 | **38 / 99** |
| Codex | 4 / 99 | **23 / 99** |

Each agent reviewed every commit three times per setup (33 gaps × 3 = 99). Models
judged coverage by reading the code and tests. [Full results and methodology](docs/change-analysis-benchmark.md)

## Quick start

The quickest way is to let your coding agent do it. Open your own project in the agent
and paste:

```text
Install Genesis by following https://raw.githubusercontent.com/GenesisAgentInfra/genesis/main/docs/install.md, then review my latest commit with it and tell me how to open the result.
```

Or install it yourself. You need [uv](https://docs.astral.sh/uv/getting-started/installation/)
and Git, on macOS or Linux:

```sh
uv tool install --python 3.12 "git+https://github.com/GenesisAgentInfra/genesis#subdirectory=packages/genesis_ci"
"$(uv tool dir --bin)/genesis" agent install --agent claude
```

Use `--agent codex` for Codex and `--agent both` for both. Other agents, updating,
uninstalling and troubleshooting are in the [install guide](docs/install.md).

Now open your own project in Claude Code. It has to be a Git repository with at least
one commit. Then ask for one of two things:

```text
/genesis map
/genesis review main
```

`map` draws the system as it is now, so you can understand it. `review` shows what
changed since a revision (here `main`) and whether a test checks it. You can also just
ask in plain language.

In Codex the skill is `$genesis`. When it finishes, open `.genesis/out/latest/view.html`
in a browser. The `summary.md` next to it is ready to paste into a pull request. The
[usage guide](docs/usage.md) explains the page and the other files.

## What you get

Say you asked your agent for guest checkout. It built that, and changed three other
things on the way. Genesis draws the checkout flow and puts all four changes on it:

<p align="center">
  <img src="assets/readme/flow-map.png" alt="The first half of the Check out a cart flow: signed in or guest with an email, a stock check per item, the free-shipping threshold and the card charge, with numbered changes, their test verdicts and risk marks on the steps" width="820">
</p>

| What changed for shoppers | Is it tested? |
| --- | --- |
| A card charge that times out is retried up to 3 times, with no idempotency key. A shopper can be charged twice. | 🔴 No coverage found. No test makes the payment time out. |
| Stock is no longer held while the card is charged. Two shoppers can pay for the last unit. | 🟡 Behavior not checked. Tests run this code but none buys the last unit twice. |
| Shoppers can check out as a guest by leaving an email. | ⚪ Coverage unclear. The guest tests take their cases from a package outside the repository, so reading them does not show what they check. |
| Free shipping starts above $35 instead of $50. | ✅ Behavior checked. Tests place orders at $34.99, $35.00 and $35.01. |

These are the labels on the page. `summary.md` calls the same verdicts not reached,
reached only, unknown and covered; the [usage guide](docs/usage.md#test-verdicts) lists
both.

Click a step to see what changed there, the test verdict with the note that explains
it, and the code behind it:

<p align="center">
  <img src="assets/readme/change-detail.png" alt="The card charge step opened: the risk that a timed-out charge is retried with no idempotency key, and what changed" width="640">
</p>

## Can I trust it?

Your agent does the reading, but it doesn't get the last word. Every step it writes has
to quote the lines of code it stands for, and the Genesis CLI checks each quote against
a frozen snapshot of your repo. If one doesn't match, the whole description is rejected
and the agent tries again. For Python, Genesis also parses the code itself, so a branch
the agent skips leaves the result marked `partial` in `summary.md`. When you map a
project, the page also shows "Partial" at the top. A review's page does not, so check
`summary.md`.

In a review, Genesis finds the changes itself by comparing the two versions of the code,
so the list does not depend on the agent. What each change means, its test verdict and
its risks are the agent's reading. The CLI refuses a verdict only in plain cases: Behavior checked (covered) with no cited
test that asserts anything, or, for Python, No coverage found (not reached) when a test
calls the changed function directly. In other languages, whether a cited test asserts
anything is the agent's word.

The CLI calls no model, sends nothing anywhere, and never runs your code.

## Limits

- Python gets the most accurate results, because Genesis parses it. Other languages
  work too: your agent reads the code and Genesis checks each step against the source,
  but a path the agent misses is not flagged.
- Test verdicts come from reading your tests. Genesis doesn't run them.
- Risks are what your agent noticed while reading. There is no rule engine.

## Documentation

- [Install](docs/install.md): requirements, which flag for which agent, updating,
  uninstalling, and what to do when something goes wrong.
- [Use](docs/usage.md): what to ask, where the result is, how to read the page.
- [Benchmark](docs/change-analysis-benchmark.md): what was measured and the full results.
- [AGENTS.md](AGENTS.md): for a coding agent asked to install, use or change Genesis.

Questions and bug reports go to [GitHub issues](https://github.com/GenesisAgentInfra/genesis/issues).
Report a security problem privately, as [SECURITY.md](SECURITY.md) describes.

## License

[Apache-2.0](LICENSE). Bundled components keep their own licenses, listed in
[NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Want to help?
See [CONTRIBUTING.md](CONTRIBUTING.md).

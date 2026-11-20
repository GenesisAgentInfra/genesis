# Change-analysis benchmark

<p><strong>English</strong> &nbsp;·&nbsp; <a href="change-analysis-benchmark.zh-CN.md">简体中文</a></p>

This page gives the full results behind the comparison in the [README](../README.md),
and explains what each measure means.

The question: when a user asks a coding agent what a commit changes, what it could
break and whether the tests cover it, how do the answers differ with Genesis installed?

- [What was compared](#what-was-compared)
- [Reference answers](#reference-answers)
- [How an answer is scored](#how-an-answer-is-scored)
- [The measures](#the-measures)
- [Results](#results)
- [Reading the numbers](#reading-the-numbers)

## What was compared

Two coding agents, each with and without Genesis:

| Setup | Agent and model | Installed in the project |
| --- | --- | --- |
| Claude Code | Claude Code 2.1.322, `claude-opus-5-5`, effort high | nothing |
| Claude Code + Genesis | the same | the Genesis skill and CLI |
| Codex | Codex CLI 0.142.2, `gpt-6-astra`, reasoning effort high | nothing |
| Codex + Genesis | the same | the Genesis skill and CLI |

Genesis was built from commit `91b832e` and installed with
`genesis agent install --agent <claude|codex> --scope project --repo <repository copy>`.
The two setups of an agent differ in nothing else: each run starts from a fresh copy of
the repository at the commit under review, with the same request.

Each setup answered 10 commits three times: 30 runs per setup, 120 runs in
all.

### The request

There are six requests, three in English and three in Chinese, written the way a user
would type them. Two of them:

> Can you review the latest commit for me? What does it change, which parts of the
> product does it touch, could it break anything, and do the existing tests cover it?

> 帮我看下最新这个提交改了些什么，会不会影响到别的功能？现有的测试能不能兜住，有没有什么风险？

Each commit and repeat got one of the six, the same one in all four setups. The requests
ask for no format, and none of them names Genesis: the agent decides by itself whether
to use it. It did in all 60 runs that had it.

### Repositories and commits

The five repositories were chosen by a fixed rule, not by hand: a GitHub search for
Python agent, LLM, MCP and RAG projects with a permissive licence and at least 200
stars, taken from the most stars down, keeping the first five of medium size (8,000 to
25,000 non-blank lines of source) that have a test suite, a lockfile and two commits
that fit the rule below. Repositories used while developing Genesis were skipped, so
Genesis had never been run on any of the five. Here *source* means the Python files of
the project's own package, outside the tests.

From each repository two recent commits were taken, also by rule: each changes at
least two source files and 40 to 250 lines in them, is not a merge commit, a version
bump or a documentation-only change, and has at least three scorable units. Lines are
counted as added plus removed, leaving out blank lines, comment-only lines and
docstrings. Other files in the commit, such as tests, front-end code, scripts and
documentation, are not counted.

| Repository | Commit | Scorable units | Covered | Executed only | Left out |
| --- | --- | ---: | ---: | ---: | ---: |
| [Azure-Samples/chat-with-your-data-solution-accelerator](https://github.com/Azure-Samples/chat-with-your-data-solution-accelerator) | [`6489e85`](https://github.com/Azure-Samples/chat-with-your-data-solution-accelerator/commit/6489e85ad2f62ec37bd256c0ed852410289a918e) | 7 | 5 | 2 | 1 |
| [Azure-Samples/chat-with-your-data-solution-accelerator](https://github.com/Azure-Samples/chat-with-your-data-solution-accelerator) | [`d211e98`](https://github.com/Azure-Samples/chat-with-your-data-solution-accelerator/commit/d211e9896db9c6ff0223bdd9834b2f8ca7718151) | 12 | 12 | 0 | 0 |
| [OpenOSINT/OpenOSINT](https://github.com/OpenOSINT/OpenOSINT) | [`6f6c9a8`](https://github.com/OpenOSINT/OpenOSINT/commit/6f6c9a83ca7fc85a423987aa03ea7e5f8ab9fb97) | 13 | 11 | 2 | 1 |
| [OpenOSINT/OpenOSINT](https://github.com/OpenOSINT/OpenOSINT) | [`ec1bc82`](https://github.com/OpenOSINT/OpenOSINT/commit/ec1bc826dc0d288bb596fa378cdff350c562634d) | 15 | 14 | 1 | 7 |
| [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) | [`496741d`](https://github.com/Taxuspt/garmin_mcp/commit/496741ddd9d6bf6810e8fb3a092ebd512762e496) | 16 | 10 | 6 | 0 |
| [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) | [`808407a`](https://github.com/Taxuspt/garmin_mcp/commit/808407a34cacf59906e66a2d129d8e6dfe9c4f8d) | 22 | 18 | 4 | 3 |
| [dbt-labs/dbt-mcp](https://github.com/dbt-labs/dbt-mcp) | [`201148d`](https://github.com/dbt-labs/dbt-mcp/commit/201148d7ef294abfd4ba6bfd52141e6fba91b1bf) | 42 | 28 | 14 | 1 |
| [dbt-labs/dbt-mcp](https://github.com/dbt-labs/dbt-mcp) | [`db9e8f2`](https://github.com/dbt-labs/dbt-mcp/commit/db9e8f2ac2d33abd85843ae3d3012c3476b8e48a) | 8 | 7 | 1 | 7 |
| [microsoft/typeagent-py](https://github.com/microsoft/typeagent-py) | [`6ac73a8`](https://github.com/microsoft/typeagent-py/commit/6ac73a8c4b324bc0c6e7b46368d144f125343e83) | 10 | 8 | 2 | 4 |
| [microsoft/typeagent-py](https://github.com/microsoft/typeagent-py) | [`be4a162`](https://github.com/microsoft/typeagent-py/commit/be4a16281a269bded6249666bad559bed7173ea4) | 8 | 7 | 1 | 2 |
| **Total** |  | 153 | 120 | 33 | 26 |

The columns are explained in the next section.

## Reference answers

Each commit has a reference answer, built by reading the code before the runs. No
answer of an agent and no output of Genesis was used to build it. The readers named on
this page are language-model sessions that follow written instructions, not people.

### Change units

A **unit** is one separate change to the code: a new or changed branch, a changed
default or constant, a new function, a changed decorator, a removed definition. Only
the project's Python source gives units; test files, other languages, comments and
formatting give none.

### Coverage level of each unit

Units that leave nothing for a test to catch get no level: refactors that change no
behaviour, pure removals, and definitions that only moved. Every other unit is
**scorable**. Two readers, working independently, give each scorable unit one level by
reading the code and the tests:

| Level | Meaning |
| --- | --- |
| **Covered** | A test that the project's default test command runs reaches the changed code, and would fail if this unit alone were undone. |
| **Executed only** | Such a test runs the code, but would still pass if the unit were undone: it does not take the changed path, or checks nothing the change affects. |
| **Not covered** | No such test runs the code. |
| **Cannot tell** | Reading alone does not decide it. |

In `summary.md` Genesis calls these levels covered, reached only, not reached and
unknown. Its page shows them as Behavior checked, Behavior not checked, No coverage
found and Coverage unclear (see [Test verdicts](usage.md#test-verdicts)).

This is stricter than line coverage, which counts a line as covered once any test runs
it. Here "covered" asks whether a test would notice if the change were taken back. For
every scorable unit there is a patch that undoes that unit and nothing else, and the
readers judge against it. A test that is skipped by default, or that replaces the changed
function with a stub, does not count.

A unit gets a level only when both readers give the same one; on these commits they
agreed on every scorable unit.

The reference answers have 179 units. 153 of them are scorable:
120 covered and 33 executed only (none is "not covered"). The
other 26 are left out of the coverage measures: 20 refactors,
4 removals and 2 moves.

### Entry points

Entry points are the ways into the code from outside, such as HTTP routes, MCP tools,
CLI commands and background jobs. For each unit, the reference answer lists the entry points
whose behaviour the unit changes: those through which some input reaches the changed
code.

## How an answer is scored

An answer is free text. Three steps turn it into numbers:

1. **Unit reading.** A reader gets the whole answer and the commit's units, without
   their reference levels, and records the level the answer gives each unit, or "none"
   when the answer says nothing about that unit's tests.
2. **Extraction.** An extractor lists the changes the answer describes, the entry
   points it names for each, and the risks it raises.
3. **Checking.** A checker reads the code before and after the commit and judges every
   risk the answer raises.

The readers, extractors and checkers are language-model sessions that follow written
instructions; no person graded an answer. They are not told which setup an answer came
from. A fifth of the answers were read a second time, independently: depending on the
setup, the two readings gave the same level for 95% to 97% of the
units. A fifth of the risks were checked a second time: the two checks gave the same
verdict on 89% of those from the Claude Code setups and
92% of those from the Codex setups.

## The measures

Each measure is computed for a run. A commit's value is the mean of its three runs,
and the figure in the tables is the mean over the 10 commits. Rows written as "x of n"
are counts over all runs. A run or commit in which a measure has no value, such as
precision when the answer names no entry point, is left out of that mean.

### Test coverage

- **Coverage accuracy.** The share of a commit's scorable units for which the answer
  gives the reference level. A unit the answer does not mention, or says nothing about
  the tests of, counts as wrong.
- **Accuracy of the verdicts given.** The same, over only the units the answer gives a
  level for. It separates "said something wrong" from "said nothing".
- **Verdict rate.** The share of scorable units the answer gives a level for.

  Example: a commit has 10 scorable units. The answer gives the right level for 8, a
  wrong one for 1, and does not mention 1. Coverage accuracy is 80%, accuracy of the
  verdicts given is 8 of 9 (89%), and the verdict rate is 90%.
- **By reference level.** The same readings, counted separately for the covered and
  the executed-only units over all three runs: 120 × 3 = 360
  readings of covered units and 33 × 3 = 99 readings of
  executed-only units per setup.
- **False assurance.** How many of the 99 executed-only readings the answer
  calls covered. This is the costly mistake: the user is told a test protects a change
  when no test would catch it.

Most units in these commits are covered, so an answer that called every unit covered
would already reach a coverage accuracy of 82%. The executed-only
units are where the answers differ, which is why they are counted separately.

### Entry points

For each unit, the entry points the answer names for it are compared with the
reference entry points.

- **Entry-point recall.** Of the reference entry points, the share the answer names.
  A unit the answer does not mention has recall 0.
- **Entry-point precision.** Of the entry points the answer names, the share that are
  in the reference.

Both are averaged over the units of a commit, removals left out. A unit whose
reference lists no entry point is left out of recall, and a unit for which the answer
names none is left out of precision. Only entry points named one by one count: a
phrase such as "all admin routes" is not scored.

Example: the reference has entry points A, B and C for a unit. The answer names A, B
and two that are not in the reference. Recall is 2 of 3, precision 2 of 4.

- **Entry points named per run.** A count, shown for context: a longer list is not a
  better one.

### Changes found

- **Change recall.** The share of the reference units the answer mentions at all,
  whatever it says about them. It is reported in two parts: units the commit message
  describes, which an agent can repeat from the message, and units it does not, which
  can only be found by reading the diff. Moves are left out. Of the other units, 117
  are described by their commit message and 60 are not. In two commits the message
  describes none, so the first part is a mean over 8 commits.
- **Changes listed per run.** A count, shown for context.

Genesis builds its list of changes from the diff, so change recall favours it by
construction.

### Risks

Every risk an answer raises is checked against the code. A remark that only gives a
rating ("low", "none"), or says nothing can go wrong, is not a raised risk.

| Verdict | Meaning |
| --- | --- |
| **Real** | The problem can happen with the code as it is after the commit, and it follows from this change: a concrete failure, wrong result, broken caller, data loss, security or compatibility problem. |
| **Not real** | The code rules it out, the claim misreads the code, or it is not tied to this change, such as general advice to add tests. |
| **Unclear** | The code alone does not decide it: it depends on runtime data, an outside service or the authors' intent. |

- **Risks raised per run**, and how many of them are real, not real and unclear. Each
  figure is rounded on its own, so the three parts can differ from the total by 0.1.
- **Share of raised risks that are real.** Real risks divided by raised risks, computed
  for each run and then averaged, so it is not exactly the "of them real" row divided
  by the "risks raised per run" row.

Risks are counted one by one; severity is not weighed.

## Results

The README shows four of these rows under plainer names:

| In the README | On this page |
| --- | --- |
| Changes given a correct test-coverage verdict | Coverage accuracy |
| Changes that tests run but would not catch, flagged as such | Executed-only units called executed only, as a share of the 99 readings |
| Affected entry points named | Entry-point recall |
| Share of named entry points that are right | Entry-point precision |

The risk rows show the same figures in both.

### Claude Code

| Measure | Without Genesis | With Genesis |
| --- | ---: | ---: |
| **Test coverage** |  |  |
| Coverage accuracy | 79% | 88% |
| Accuracy of the verdicts given | 88% | 89% |
| Verdict rate | 90% | 99% |
| Covered units called covered | 339 of 360 | 349 of 360 |
| Executed-only units called executed only | 8 of 99 | 38 of 99 |
| False assurance: executed-only units called covered | 47 of 99 | 34 of 99 |
| **Entry points** |  |  |
| Entry-point recall | 32% | 47% |
| Entry-point precision | 67% | 68% |
| Entry points named per run | 3.8 | 6.3 |
| **Changes found** |  |  |
| Change recall, units the commit message mentions | 96% | 98% |
| Change recall, units it does not mention | 69% | 75% |
| Changes listed per run | 6.9 | 7.0 |
| **Risks** |  |  |
| Risks raised per run | 6.1 | 4.2 |
| of them real | 2.9 | 2.8 |
| of them not real | 2.1 | 0.7 |
| of them unclear | 1.2 | 0.7 |
| Share of raised risks that are real | 44% | 64% |

### Codex

| Measure | Without Genesis | With Genesis |
| --- | ---: | ---: |
| **Test coverage** |  |  |
| Coverage accuracy | 76% | 80% |
| Accuracy of the verdicts given | 87% | 92% |
| Verdict rate | 87% | 87% |
| Covered units called covered | 330 of 360 | 333 of 360 |
| Executed-only units called executed only | 4 of 99 | 23 of 99 |
| False assurance: executed-only units called covered | 43 of 99 | 30 of 99 |
| **Entry points** |  |  |
| Entry-point recall | 15% | 24% |
| Entry-point precision | 71% | 54% |
| Entry points named per run | 1.8 | 4.4 |
| **Changes found** |  |  |
| Change recall, units the commit message mentions | 90% | 92% |
| Change recall, units it does not mention | 55% | 55% |
| Changes listed per run | 5.4 | 5.0 |
| **Risks** |  |  |
| Risks raised per run | 4.5 | 3.3 |
| of them real | 2.4 | 2.4 |
| of them not real | 1.4 | 0.5 |
| of them unclear | 0.7 | 0.4 |
| Share of raised risks that are real | 54% | 72% |

### Verdicts by reference level

Counts over all three runs of every commit. In each column the two blocks sum to
360 and 99.

| Reference level, and what the answer said | Claude Code | Claude Code + Genesis | Codex | Codex + Genesis |
| --- | ---: | ---: | ---: | ---: |
| **Covered** (360 readings) |  |  |  |  |
| covered (correct) | 339 | 349 | 330 | 333 |
| executed only | 5 | 4 | 7 | 1 |
| not covered or cannot tell | 3 | 2 | 4 | 6 |
| no verdict or not mentioned | 13 | 5 | 19 | 20 |
| **Executed only** (99 readings) |  |  |  |  |
| executed only (correct) | 8 | 38 | 4 | 23 |
| covered | 47 | 34 | 43 | 30 |
| not covered or cannot tell | 9 | 21 | 6 | 9 |
| no verdict or not mentioned | 35 | 6 | 46 | 37 |

### Coverage accuracy by commit

| Commit | Claude Code | Claude Code + Genesis | Codex | Codex + Genesis |
| --- | ---: | ---: | ---: | ---: |
| chat-with-your-data-solution-accelerator `6489e85` | 76% | 86% | 67% | 62% |
| chat-with-your-data-solution-accelerator `d211e98` | 100% | 100% | 83% | 100% |
| OpenOSINT `6f6c9a8` | 85% | 100% | 79% | 97% |
| OpenOSINT `ec1bc82` | 89% | 93% | 93% | 89% |
| garmin_mcp `496741d` | 60% | 75% | 56% | 75% |
| garmin_mcp `808407a` | 83% | 97% | 79% | 88% |
| dbt-mcp `201148d` | 61% | 67% | 60% | 60% |
| dbt-mcp `db9e8f2` | 67% | 83% | 67% | 63% |
| typeagent-py `6ac73a8` | 80% | 80% | 80% | 80% |
| typeagent-py `be4a162` | 88% | 96% | 92% | 88% |
| **Mean** | 79% | 88% | 76% | 80% |

With Genesis, coverage accuracy is higher on 8 of the 10 commits for Claude
Code and equal on 2. For Codex it is higher on 4, equal on
1 and lower on 5 (compared before rounding: on dbt-mcp `201148d` the
two Codex values are 60.3% and 59.5%).

### What changes with Genesis, and what does not

- **Executed-only units.** Without Genesis the agents rarely identify one: 8
  and 4 of 99 readings. With Genesis it is 38 and
  23. False assurance falls from 47 to 34 for Claude
  Code and from 43 to 30 for Codex. Readings that call such a
  unit not covered or cannot tell go up, from 9 to 21 for
  Claude Code and from 6 to 9 for Codex.
- **Covered units.** Little changes: the four setups get 330 to
  349 of 360 right.
- **Verdict rate.** Claude Code gives a verdict for 99% of the scorable units with
  Genesis, up from 90%. Codex stays at 87%.
- **Entry points.** Recall rises for both agents. Precision stays about the same for
  Claude Code (67% and 68%) and falls for Codex, from 71% to
  54%.
- **Changes found.** Change recall moves little. For units the commit message does not
  mention, it goes from 69% to 75% for Claude Code and stays at
  55% for Codex.
- **Risks.** Both agents raise fewer risks with Genesis, and fewer of them fail the
  check: 2.1 to 0.7 per run for Claude Code, 1.4 to
  0.5 for Codex. The number of real risks per run stays about the same.

## Reading the numbers

- **Small sample.** Ten commits from five Python repositories, three runs each, with
  one model per agent. On single commits the difference goes both ways, as the table
  by commit shows.
- **Coverage is read, not run.** A reference level is what two readers concluded from
  the code and the tests. No test was executed to set it.
- **Scored by models.** The reference answers and the scoring come from language-model
  sessions, checked against each other, not against human reviewers.
- **Entry points must be named.** An answer that says "every admin route" gets no
  credit for the routes it means.
- **Same yardstick as Genesis.** The reference levels, and the question behind them
  (would a test fail if the change were undone?), are the ones the Genesis skill gives
  the agent for its own verdicts. The requests ask in a user's words whether the tests
  cover the change, and name no levels. The runs do not show how an agent without
  Genesis would do if the request asked for this distinction directly. They also do
  not separate the skill's instructions from the facts the CLI supplies.

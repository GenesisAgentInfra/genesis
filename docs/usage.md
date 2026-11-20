# Use Genesis

<p><strong>English</strong> &nbsp;·&nbsp; <a href="usage.zh-CN.md">简体中文</a></p>

You talk to your coding agent, and the agent drives Genesis. There is nothing to
configure and no command for you to learn: open your project in the agent and ask for
one of two things. If Genesis is not installed yet, see [install](install.md).

## Review a change

```text
/genesis review main
```

In Codex the skill is `$genesis`. Plain language works as well, in any language:

```text
What does my last commit change, could it break anything, and do the tests cover it?
Review this branch against main before I open the pull request.
Look at what I have not committed yet. Is it safe?
```

The word after `review` is the revision to compare with: a branch, a tag or a commit.
Without one, the agent compares with the point where your branch started, and for
uncommitted work with your last commit.

You get every change in behaviour, said in product terms, each with:

- the entry points and flows that reach it;
- a test verdict (see [the four verdicts](#test-verdicts));
- the risks the agent found while reading the change and the code that calls it.

## Map the project

```text
/genesis map
```

Or: "Draw the business flows of this project", "How does checkout work here?".

The agent finds the ways into the system (routes, commands, jobs, handlers), groups
them into business flows and describes each flow as steps and branches. On a large
project it describes the main flows first and offers to do the rest.

## Where the result is

Genesis writes into `.genesis/out/latest/` inside your project:

| File | What it is |
| --- | --- |
| `view.html` | The page to open. Each flow as a diagram, with the changes on it. |
| `summary.md` | The same result as text, ready to paste into a pull request. |
| `graph.html` | A plain outline of the same map that needs no scripts. |
| `business-map.json` | The map as data. |
| `change-report.json` | The changes and their verdicts as data. Written for a review only. |

Your agent gives you the path of `view.html` when it is done. Open the file in a
browser, not in an editor preview: the page needs scripts. It is self-contained and
loads nothing from the network when it opens.

When the agent draws a map, it also opens the page in your browser at the start, where
it can. The page does not refresh itself: reload it once the agent has finished.

When the agent runs on another machine (over SSH, in a container or in the cloud),
there is no browser for it to open. Copy `view.html` to your own machine, or read
`summary.md` where it is.

## Reading the page

- Each flow is drawn as steps and arrows. A decision shows its branches.
- Click a step to see the code behind it and the tests that touch it.
- In a review, each change sits on the step it belongs to, with what it means, its test
  verdict and any risk. `summary.md` lists the changes that belong to no step under
  "Changes not on the map".
- A map marked `partial` is usable but not finished: some flows are not described yet,
  or a described flow leaves part of the code unaccounted for. `summary.md` says which.

### Test verdicts

Genesis reads your tests. It never runs them, so a verdict is never a statement that a
test passed.

| On the page | In `summary.md` | Meaning |
| --- | --- | --- |
| Behavior checked | covered | A test runs the changed code and would fail if the change were undone. |
| Behavior not checked | reached only | Tests run the code but would not fail if the change were undone: they miss its path or check nothing it affects. |
| No coverage found | not reached | No test gets to it. |
| Coverage unclear | unknown | It could not be told. |
| Coverage unclear | called by tests, not assessed | Static analysis found tests that call the code, and nobody has read them yet. |

Risks and flow names are your agent's reading of the code. No rule engine produced
them, and the names are not confirmed requirements.

## Share a result

`view.html` and `graph.html` contain excerpts of your source. To pass a result on, ask
your agent for a copy to share. It writes `view.share.html` and `graph.share.html`
beside the normal pages, without source excerpts. They can still name steps by a line
of code where a flow is not described, and a review still shows the changed lines.

## Ask again

- A question about a map you already have ("which flows touch refunds?") is answered
  from the existing result. Nothing is analyzed again.
- Asking for the map again on unchanged code continues where the last run stopped.
  After the code changed, the agent starts a new run.

## What it leaves in your project

One directory, `.genesis/`. Its `sessions/` and `out/` folders hold copies of your
source and are ignored by Git through `.genesis/.gitignore`. Do not commit or publish
them. Genesis changes no other file, and your agent changes code or tests only when
you ask for that separately.

## Languages

Python gets the most accurate result: Genesis parses it, finds the entry points itself
and marks a map `partial` when a flow leaves out a branch.

Other languages work through your agent. It finds the entry points and reads the code,
and Genesis checks every step it writes against the source. A path the agent misses is
not flagged, and the agent says so in its report.

## What Genesis does not do

- It does not run your code or your tests, and it reads no coverage data.
- It calls no model and no service. The reading is done by your own agent, with
  whatever model and account that agent already uses.
- It has no rules that detect risks.
- It does not record how one flow hands over to another. Your agent may describe that
  in its report, as its own reading.

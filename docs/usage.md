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

The word after `review` is the branch, tag or commit to compare with. With a branch
name, the review covers what you have committed since your branch left that branch.
Work you have not committed, new files included, is not part of it. Without a word,
the agent compares with the point where your branch started.

Uncommitted work is a review of its own, compared with your last commit: ask for it,
as in the third example above. New files Git does not track yet are included when the
agent judges they belong to the change. In a Python project the report names any it
left out. In other languages it does not: the agent checks for new files itself before
it starts.

When there is nothing to compare (no change since that revision, or a revision your
local repository does not have), the agent says so. It suggests another revision, a
review of your uncommitted work, or a map.

You get every change in behaviour, said in product terms, each with:

- the entry points and flows that reach it;
- a test verdict (see [test verdicts](#test-verdicts));
- the risks the agent found while reading the change and the code that calls it.

The agent also describes the flows your changes land on, so that the page shows the
changes on named business steps. In a Python project it describes up to three, those
with the most changes. When more are affected, it names the others, which stay drawn
from the code alone, and offers to describe them. If you ask for a quick answer, it
skips the flows. In other languages it describes the flows the changed code belongs to
before it explains the changes, because that is how a change gets its place on the map.
In a Python project mapped before, the review starts from the latest map in which the
agent found entry points of its own: from the entry points that map used and the way
it grouped them into flows. So a change lands on the flow the map showed, as long as
the code that starts that flow is all still there. Ask it to start from a committed
copy of a map instead, such as the one Genesis EDD keeps with a spec, and every clone
of the project gets the same flows.

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
| `business-map.json` | The map as data. Its `mode` is `change` for a review. A review's map covers what the review analyzed, only the planned flows once it has a plan: it is not a map of the whole project. A map written by an earlier version has no `mode` and may be either kind. |
| `change-report.json` | The changes and their verdicts as data. Written for a review only. |

`business-map.json` also records, under `source`, the code it was read from: the
commit (`revision`), whether uncommitted changes were read with it (`worktree_dirty`),
whether files it would have read were left out, such as one over the size limit
(`integrity_status`), and every file read (`files`), each with the SHA-256 digest of
its content but not its text. The digest is that of the file as the commit stores it,
which is what `git show <revision>:<path>` prints, even when your checkout converts
its line endings; a file with uncommitted changes has the digest of what was read. To
tell whether the map still matches a later commit, compare the digests with that
commit's files the same way: a file whose digest differs, or that is gone, has
changed since. A file added later is not listed. A file that a Git filter such as
git-crypt converts counts as uncommitted when Git's index cannot vouch for it; run
`git status` once, which updates the index, and prepare again.

`latest` holds the most recent run only: a review replaces an earlier map there, and a
map replaces an earlier review. Every run also keeps its result, with the same files,
in its own folder `.genesis/out/<session id>/`.

Your agent gives you the path of `view.html` when it is done. Open the file in a
browser, not in an editor preview: the page needs scripts. It is self-contained and
loads nothing from the network when it opens. When your project's `origin` is on
GitHub and the commits are pushed, two things on the page reach GitHub, and only when
you click them. The code behind a step and the commit ids link to github.com. In a
review, the commit range in the header asks GitHub's public API for the commits
between the two revisions; it sends the repository name and the two commit ids.

For a Python project, the agent also opens the page in your browser at the start of a
map, where there is a browser to open. At that point the page lists the entry points
Genesis found, one line each. The page does not refresh itself: reload it once the
agent has finished. For a project in another language there is nothing to show at the
start, so open the page when the agent gives you its path. The page is never opened
when the environment variable `GENESIS_NO_BROWSER` is set.

When the agent runs on another machine (over SSH, in a container or in the cloud),
there is no browser for it to open. Copy `view.html` to your own machine, or read
`summary.md` where it is.

## Reading the page

- Each flow is drawn as steps and arrows. A decision shows its branches.
- Click a step to see what it does and the code behind it. When your project's
  `origin` is on GitHub, the commit has been pushed and the code there is the same,
  the step links to the file on GitHub instead of showing the code.
- In a review, each change sits on the step it belongs to, with what it means, its test
  verdict, the reason for the verdict and any risk. The tests behind a verdict are
  named in `summary.md` and `graph.html`, not on the page.
- Changes that belong to no step, and flows a change removed, are in the block
  `Outside the flows`. `summary.md` lists those changes under "Changes not on the map".
- A risk that names only changed files Genesis did not analyze, such as a Dockerfile,
  is not on the page: `summary.md` and `graph.html` list it with those files.
- When you select a change, `May affect` marks the results further along its flow that
  the change can lead to. It follows the arrows of the flow and is not a finding.
- A domain folds its lookup and upkeep flows into one row, such as
  `3 more lookup and upkeep flows`. Click it to list them. Flows in no domain sit under
  `Other flows`. A card with a number in its corner stands for several steps. Click it
  to show them.
- A step can carry a badge: `Risk` when the agent recorded a risk on the step or on the
  change shown on it. Otherwise a changed step shows `Needs validation` whenever its
  test verdict is anything other than `Behavior checked`.
- `Unconfirmed` or `Unknown` on a step means the evidence does not fully support it.
  `summary.md` lists these steps with the reason under "Uncertain". This is not the
  test verdict `Coverage unclear`.
- `Code structure` marks a flow that is not described yet: the flow is named by its
  route or function, and its steps by lines of code. `Not described yet` marks a flow
  that has a name but no described steps.
- A step shows an `Input / output` tab only when the agent described its data shape.
  It is the shape the agent read from the code, not a contract that was checked.

### Test verdicts

Genesis reads your tests. It never runs them, so a verdict is never a statement that a
test passed.

| On the page | In `summary.md` | Meaning |
| --- | --- | --- |
| Behavior checked | covered | A test runs the changed code and would fail if the change were undone. |
| Behavior not checked | reached only | Tests run the code but would not fail if the change were undone: they miss its path or check nothing it affects. |
| No coverage found | not reached | No test gets to it. |
| Coverage unclear | unknown | It could not be told. Either your agent read the tests and could not decide, or nobody assessed the change and static analysis had nothing to go on: it found no test that calls the code, or the code was removed. A test may still reach it in a way static analysis does not follow. On the page, the note under the verdict says which. |
| Coverage unclear | called by tests, not assessed | Static analysis found tests that call the code, and nobody has read them yet. |

The page's own labels exist in English and Chinese only. The page picks Chinese when
your agent wrote the result in Chinese, and English otherwise, whatever language you
read this guide in. In Chinese the four verdicts read 有行为验证, 缺少行为验证,
未找到覆盖 and 覆盖待确认. `summary.md` and `graph.html` always use English labels.

Risks and flow names are your agent's reading of the code. No rule engine produced
them, and the names are not confirmed requirements.

### Finished or partial

A map marked `partial` is usable but not finished: some flows are not described yet, a
described flow leaves part of the code unaccounted for, or files were left out. The
page shows `Partial` next to the size of the map, and `summary.md` says which.

A map that is not partial is finished for the flows the agent planned, not
necessarily for the whole project. The page does not show what was left outside.
`summary.md` and `graph.html` do: the scope (how many planned flows cover how many
entries), the entries skipped with their reasons and those not handled, and, under
"Not expanded", the larger functions that a single step stands for. Steps the agent
could not confirm stay in a finished map, tagged as above.

In a review, the page shows no status, and `summary.md` has two. `Status` under
"Changes on the map" says whether the review is finished. It is `partial` when
something the review owes is missing, such as an explanation, or a flow the changes
land on that is still drawn as code structure. `Map status` at the top is about the
map underneath. It can read `partial` while the review is complete, for example after
a quick answer that described no flows.

## Share a result

`view.html` and `graph.html` contain excerpts of your source. To pass a result on, ask
your agent for a copy to share. It writes `view.share.html` and `graph.share.html`
beside the normal pages, without source excerpts. They can still name steps by a line
of code where a flow is not described, and a review still shows the changed lines.
They also keep file paths with line numbers, the names of functions and tests, and
the explanations and risks your agent wrote. When the project's `origin` is on GitHub
and the commit has been pushed, `view.share.html` also links to the cited files there,
and the links name the repository and the commit.

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

`git status` still lists `.genesis/` as untracked. The only file Git sees there is that
`.gitignore`. Commit it, or add `.genesis/` to your project's own `.gitignore`.

Each new review, and each run after the code changed, adds a folder to both
`sessions/` and `out/`, and Genesis never removes them. Delete `.genesis/` when you no
longer need the results; the next run creates it again.

[Genesis EDD](https://github.com/GenesisAgentInfra/genesis-edd) makes one copy on
purpose: it copies the `business-map.json` a spec was written against into the spec's
folder, to be committed with the spec. That file has no source excerpts, but where a
flow is not described yet its steps are named by lines of code, and it lists the paths
of the files the map was read from, each with a digest of its content.

## Languages

Python gets the most accurate result: Genesis parses it, finds the entry points itself
and marks a map `partial` when a flow leaves out a branch.

Other languages work through your agent. It finds the entry points and reads the code,
and Genesis checks every step it writes against the source. A path the agent misses is
not flagged, and the agent says so in its report.

One run reads a project in one of these two ways. In a project with Python files and
files in other languages, such as a Python backend with a TypeScript frontend, Genesis
takes the Python way and counts the other source files: in the whole project for a
map, in the changed files for a review. When those are the majority, the agent runs
Genesis again the other way, which covers every language, Python
included, without the Python analysis. Otherwise the result covers the Python files,
and changed files in other languages are listed as not analyzed. You can always ask
for one way or the other. Neither way reads Genesis's own `.genesis/` folder or a
folder you asked to leave out: their files are not counted, and a review gives the
number of changed files in them, folder by folder.

Genesis reads source files in these languages: C, C++, C#, Clojure, Dart, Elixir,
Erlang, Go, Java, JavaScript, Julia, Kotlin, Lua, Objective-C, Perl, PHP, Python, R,
Ruby, Rust, Scala, shell scripts, SQL, Svelte, Swift, TypeScript and Vue. A project
with no file in any of them cannot be mapped. Files are recognised by extension: .c .h
.cc .cpp .hpp .cs .clj .dart .ex .exs .erl .go .java .js .jsx .mjs .cjs .jl .kt .kts
.lua .m .mm .pl .php .py .r .rb .rs .scala .sh .sql .svelte .swift .ts .tsx .vue.
Files in these languages with another extension, such as .pm, .mts or .cxx, are not
read.

## Large projects

Before the first step, your agent counts the source files Genesis would read. That
takes seconds. When the first step will take a while, the agent tells you how many
files there are and roughly how long to wait. On an 8-core machine:

| Source files | First step of a map | First step of a review |
| --- | --- | --- |
| about 100 | seconds | under a minute |
| about 650 | about 1.5 minutes | about 4.5 minutes |
| about 5,000 | about 12 minutes | about 35 minutes |

Describing the flows comes after that and takes your agent's own time.

Genesis reads up to 50,000 source files. On a project above that, the agent asks you
first: raise the limit and wait longer, or leave folders out, for example to look at
the backend only. A source file larger than 1 MB is not read: it is nearly always
generated or vendored code. When a limit leaves files out, the result says how many
and is marked partial. Folders you chose to leave out are not counted that way: the
result covers the rest of the project, and a review gives the number of changed files
in them, folder by folder.

## What Genesis does not do

- It does not run your code or your tests, and it reads no coverage data.
- The CLI calls no model and no service. The reading is done by your own agent, with
  whatever model and account that agent already uses.
- It has no rules that detect risks.
- It does not record how one flow hands over to another. Your agent may describe that
  in its report, as its own reading.

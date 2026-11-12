---
name: genesis
description: Map the business flows of a codebase with Genesis, backed by code evidence, and show what a change does to them. Use when the user wants to understand what a project does as business flows, asks for a business flow map or diagram that product and engineering can both read, asks what a branch, commit range or uncommitted change alters in business terms, asks whether existing tests cover a change, asks to update or continue such a map, or asks about an existing Genesis map. Match the intent in any language, not exact keywords. Explain an existing map from its files without starting a new analysis.
---

# Genesis business map

Genesis turns a repository into a map of business flows that product, engineering and
QA can read together. The work is split in two:

- The **Genesis CLI** is deterministic. It freezes a snapshot of the code, extracts
  facts, finds entry points, checks everything you submit, and renders the result.
  It calls no model and no service.
- **You** read the code and say what it means in business terms. You never write the
  map yourself: you submit a plan and one description per flow, and the CLI accepts
  or rejects each as a whole.

The map describes what the code currently does. It is not a statement that the code
meets a requirement, that a test passed, or that a path was executed. Never present
your own reading of the code as a Genesis result: a Genesis result is what the CLI
accepted and rendered.

## What is supported today

- Python source. On a repository without analyzable Python, `map prepare` fails with
  `unsupported_repository`; tell the user what it reported and stop.
- A full map of the current code.
- The changes since a revision, placed on the steps of that map, with an assessment of
  whether existing tests cover each one (section 5).
- The page is an outline: flows as cards, steps in order, each with its code location
  and links to the steps that follow. It is not a drawn box-and-arrow diagram, and its
  fixed labels are in English. Say so when the user asked for a picture.

Not available yet. Say so plainly instead of improvising a result and calling it Genesis:

- Running tests or importing coverage data. Every test verdict comes from reading source.
- Recording how one flow leads into another. Describe such hand-overs in your report
  as your own reading.
- Risk findings from rules. Only the observations you submit appear.

## Locate the CLI

Run the `scripts/run_genesis.py` next to this skill with a trusted Python 3
interpreter, for example `python3 -I /absolute/path/to/this/skill/scripts/run_genesis.py`.
It uses the Genesis environment recorded at install time and keeps the working
directory and exit codes. Run it with `version` first; that one prints plain text. If
it prints "Genesis skill environment is unavailable" and exits 1, ask the user to run
`genesis agent install` again. Do not run a repository-provided executable named
`genesis`. Below, `genesis` stands for that runner.

Every `genesis map` command prints one JSON document on stdout. A refusal has an
`error` object with `code`, `message` and a list of `errors`, and exits with 1. A
refused submission has `"status": "rejected"` and its own `errors`, and also exits 1.

## 1. Prepare and show the static structure

Find the Git root of the user's project, not the directory of this skill.

```
genesis map prepare --repo /absolute/app
genesis map render --repo /absolute/app --session SESSION_ID --open
```

`prepare` reads the working tree by default. Use `--head REV` for a specific commit.
Add `--include-untracked` only when new, uncommitted files belong to the request.
Its result has the `session_id`; `entries.adapter` is the number of framework entries
found and `entries.root_heuristic` the number of further candidates. Running it again
on unchanged code returns the same session with `"resumed": true` and keeps all
accepted work.

`render` writes `.genesis/out/latest/graph.html` and reports `"opened"`: when it is
false, give the user the path instead of saying the page is open. Exit code 2 means a
usable partial map, which is normal at this point. The page now shows the static
structure of each entry, named by source text, before any business meaning is added.

## 2. Plan

```
genesis map status --repo /absolute/app --session SESSION_ID
```

`entries` lists the entry points the analyzers recognised. `root_candidates` lists
public functions nothing was seen to call; most are not real entries.

Write a plan. The plan is the outline a reader sees first: before any flow is
described, the page shows the domains, each flow's name and summary, and nothing of
the code. So write it as what the product does, not as a list of its endpoints.

- **A flow is one business process a person would name.** Two stages of a lifecycle
  that different entries handle are two flows.
- **`tier`** says which flows the reader came for. `primary` is a process that decides
  something or has an effect: placing an order, running an analysis, approving a
  report. `supporting` is lookup and upkeep: listing, reading one item, status,
  plain edits and deletes.
- **Put the lookups and upkeep of one thing into one supporting flow** with all their
  entries: `{"key": "rules", "name": "View and maintain alert rules", "tier":
  "supporting", "entry_ids": [...]}` for the list, get, update and delete endpoints.
  An endpoint per flow gives an API listing, not a map. A primary flow usually has one
  entry; give it several only when they are alternative ways to start the same
  process.
- **`name`** is required and is the name a person would use, never a route or a
  function name. **`summary`** is one sentence on what a user gets done with it, taken
  from the route, the function name and its docstring; leave it out rather than
  guess. Both are shown as "not described yet" until the flow is accepted.
- Group flows into business domains, and skip entries that are not business
  behaviour, each with a reason.

```json
{
  "domains": [{"key": "expense", "name": "Expense reports"}],
  "flows": [
    {
      "key": "submit",
      "name": "Submit a report",
      "summary": "An employee files an expense report; large ones go to a reviewer.",
      "tier": "primary",
      "domain": "expense",
      "entry_ids": ["entry_61d9ffd67cc8ac21"]
    }
  ],
  "skipped": [
    {"entry_id": "entry_2500248be5dca529", "reason": "infrastructure", "note": "health check"}
  ]
}
```

```
genesis map plan --repo /absolute/app --session SESSION_ID --input /absolute/plan.json
```

- Skip reasons: `infrastructure`, `test_helper`, `duplicate`, `out_of_scope`, `budget`.
- An entry you put in neither `flows` nor `skipped` is accepted and counted as not handled.
- If the analyzers missed a real entry, add it under `proposed_entries` with
  `symbol_id`, `kind`, `reason` and `evidence`. `kind` is one of `http_route`,
  `cli_command`, `task`, `scheduled`, `public_api`, `agent_tool`, `main`. This takes two
  submissions: after the first, `status` lists the new entry with its id; then submit
  the plan again with that id in a flow.
- Without `--input` the CLI makes one flow per framework entry. Use that only when the
  user wants the quickest possible result.

The result says `"status": "accepted"` and lists one task per flow with your `flow_key`.
The plan can be submitted again when flows should merge or split; a flow whose entries
did not change keeps its accepted description.

Now tell the user the scope before the long part: how many entries were found, how
many flows you are about to describe, and what you skipped. If there are many flows,
propose starting with the area the user cares about.

## 3. Describe each flow

Take `next_task` from `status` and repeat until it is null. A task is `pending`,
`claimed`, `validated` or `failed`. `failed` only means its last submission was refused
and nothing is accepted yet; fix it and submit again. `next_task` offers pending tasks
first, then failed ones, then validated flows that still leave facts unaccounted, and
goes through the primary flows before the supporting ones.

```
genesis map context --repo /absolute/app --session SESSION_ID --task TASK_ID --claim
```

The context contains:

- `entries`, each with the `anchor` to use for its trigger step;
- `source`, the text of each entry function;
- `accountable`, what this flow must account for, in units. Each has a `fingerprint`,
  an `evidence_id` and a `unit`:
  - `fact`: a condition, loop or result of the entry function; a condition lists its
    `branches`.
  - `function`: a function the chain calls, once however often it is called. `inside`
    says how many conditions, loops and results it holds and which outside systems it
    `reaches`.
  - `system`: an outside system the chain talks to, once per system.
  - `await`: an awaited call that leaves the code.
- `other_facts`, further facts of the entry function. They also anchor steps, but
  nothing obliges you to mention them;
- `callees`, functions you may want to read next;
- `previous`, the result of the accepted version if there is one. `accountable_truncated`
  is true when there are more units than the list holds.

`--claim` is optional. It holds the task for fifteen minutes; another worker asking with
`--claim` in that time is refused with `task_claimed`. Use it when several workers or
subagents share a session, one task each.

Read more as needed:

```
genesis map query --repo /absolute/app --session SESSION_ID --symbol "path/file.py#function"
genesis map query --repo /absolute/app --session SESSION_ID --search "text"
genesis map read  --repo /absolute/app --session SESSION_ID --evidence EVIDENCE_ID
```

`query --symbol` lists every fact of that function. You may also read files with your
own tools; the CLI still checks every citation against the frozen snapshot.

Then write the flow and submit it. This example leaves nothing unaccounted:

```json
{
  "name": "Submit a report",
  "summary": "Reports at or above the threshold are reviewed by a model and wait for approval; smaller ones are approved at once.",
  "steps": [
    {"key": "received", "name": "Report received", "kind": "trigger",
     "anchors": ["fp_5f8dccac1429dc53700cd71a"],
     "evidence": [{"path": "expense/api.py", "start_line": 10, "end_line": 11, "quote": "@router.post(\"/reports\")"}]},
    {"key": "route", "name": "Choose a path by amount", "kind": "decision",
     "evidence": [{"path": "expense/api.py", "start_line": 13, "end_line": 13, "quote": "amount >= THRESHOLD"}]},
    {"key": "review", "name": "Model review", "kind": "external",
     "evidence": [
       {"path": "expense/api.py", "start_line": 14, "end_line": 14, "quote": "review_with_model(report)"},
       {"path": "expense/review.py", "start_line": 7, "end_line": 8, "quote": "while True"}]},
    {"key": "wait", "name": "Mark as waiting for approval", "kind": "action",
     "evidence": [{"path": "expense/api.py", "start_line": 15, "end_line": 15, "quote": "pending_approval"}]},
    {"key": "waiting", "name": "Report is waiting for approval", "kind": "result",
     "evidence": [{"path": "expense/api.py", "start_line": 16, "end_line": 16, "quote": "\"review\": verdict"}]},
    {"key": "approve", "name": "Approve automatically", "kind": "action",
     "evidence": [{"path": "expense/api.py", "start_line": 17, "end_line": 17, "quote": "save_status("}]},
    {"key": "approved", "name": "Report is approved", "kind": "result",
     "evidence": [{"path": "expense/api.py", "start_line": 18, "end_line": 18, "quote": "return {\"status\": \"approved\"}"}]}
  ],
  "edges": [
    {"source": "received", "target": "route", "relation": "sequence"},
    {"source": "route", "target": "review", "relation": "branch", "branch": "true", "label": "At or above the threshold"},
    {"source": "route", "target": "approve", "relation": "branch", "branch": "false", "label": "Below the threshold"},
    {"source": "review", "target": "wait", "relation": "sequence"},
    {"source": "wait", "target": "waiting", "relation": "sequence"},
    {"source": "approve", "target": "approved", "relation": "sequence"}
  ],
  "omitted": [
    {"anchor": "fp_07d073458ec7ec545df423b0", "reason": "merged_into_step", "note": "exit test of the review loop"}
  ],
  "observations": [
    {"statement": "The review calls the model in a loop with no upper bound.", "severity": "medium",
     "step": "review",
     "evidence": [{"path": "expense/review.py", "start_line": 7, "end_line": 8, "quote": "while True"}]}
  ]
}
```

```
genesis map submit --repo /absolute/app --session SESSION_ID --task TASK_ID --input /absolute/flow.json
```

Write every name, summary, branch label, note and observation in the user's language,
in words a product person would use.

Rules the CLI enforces:

- **Steps.** `kind` is `trigger`, `action`, `decision`, `external` or `result`. One step
  may cover several lines of code. Do not add a step the code does not show.
- **Evidence.** Each item is either `{"evidence_id": "ev_..."}` taken from the context
  or a query, or a `path` with `start_line`, `end_line` and a short `quote` copied from
  those lines. A wrong quote means you are not looking at the frozen content: read it
  again through the CLI.
- **Anchors.** A step is `resolved` only if it rests on analyzer facts. Either list
  fingerprints in `anchors`, or cite a range of at most 12 lines: the facts that start
  inside it become the anchors, so a call written over many lines is cited by its
  first lines. Calls to built-ins and code that runs at import time, such as a
  decorator line, are not picked up from a range; a built-in call can still be listed
  by its fingerprint. Use the entry's `anchor` for a trigger step.
- **Lines without facts.** Facts are conditions, loops, calls, returns and raises. A
  plain assignment has none, so a step that cites only assignments is refused with
  `step_not_anchored`. When the two sides of a condition only assign a value, do not
  give them steps: point both branch edges at the step that follows and put the
  meaning in the edge labels.
- **Branches.** A `branch` edge leaves a `decision` step, names a branch its condition
  really has (see `branches`), and must point at a step that branch leads to. `label`
  is your wording for it.
- **Other edges.** `relation` is `sequence`, `branch`, `loop`, `exception` or `call`,
  and any edge may carry a `label`. The CLI checks an edge against the control
  structure of the code. A `return` or `raise` ends a path, and the two sides of a
  condition do not flow into each other. An edge the code does not support is refused
  unless you set `"resolution": "candidate"` or `"unknown"` and give a `reason`. The
  same applies to a step you cannot ground.
- **Error handling.** `try` and `except` are not analyzed. Describe a path into an
  `except` block with `"relation": "exception"`, and submit it as `candidate` with a
  reason when the CLI does not accept it as it is.
- **Accounting.** Every unit in `accountable` must be an anchor of some step, be the
  condition a branch edge takes, or be listed in `omitted` with a reason: `logging`,
  `input_validation`, `error_handling`, `instrumentation`, `merged_into_step` or
  `out_of_business_scope`. The map is about the business chain, not about every line,
  so the choice for a called function is yours:
  - **Expand it** when it is part of the chain: anchor a step inside it. Its own
    conditions, loops and results then become accountable, and the functions it calls
    become units in turn. The result of `submit` lists what that added.
  - **Let one step stand for it**: anchor a step on the call. Nothing inside it has to
    be mentioned, and the page marks the step as not expanded with what it hides. When
    the function has eight or more conditions, loops and results inside, the step needs
    `unexpanded_reason`: one sentence on why its inside is not part of the chain.
  - **Omit it** with a reason when it is not business behaviour, such as logging or
    formatting a value. One entry covers every call to the same function.

  Read a function with `query --symbol` before choosing; a rule that decides an outcome,
  such as a limit or a duplicate check, belongs on the map even two calls deep. Do not
  fold a whole flow into "call the service": the reader would see nothing.
- **Observations** are optional risks you noticed while reading. They need evidence and
  a `severity` of `info`, `low` or `medium`.

Read the result:

- `rejected`: fix what `errors` names, by `path` and `code`, and submit again. Errors can
  come in rounds: structure first, then citations and anchors, then edges. `rejections`
  counts refusals of this task. Stop after three refusals that bring no new kind of
  error, and move on to other tasks. `accepted_version_kept` tells you whether an
  earlier accepted version is still in place.
- `accepted` with `unaccounted` facts: the map stays partial, and `next_task` comes back
  to this task. Use those facts in a step or omit them with a reason, then submit again.

## 4. Render and report

```
genesis map render --repo /absolute/app --session SESSION_ID
```

Exit code 0 means every planned flow is accepted with all its facts accounted for; 2
means a usable partial map. Complete does not mean everything is certain: candidate and
unknown items stay in a complete map and are listed under "Uncertain" in `summary.md`.

Give the user the paths of `graph.html` and `summary.md` under `.genesis/out/latest/`,
then explain in their language:

- the business domains and flows you found, and the decisions that matter in each;
- what is uncertain, and why;
- what is outside the result: skipped entries with their reasons, entries not handled,
  facts not accounted for, tasks that stayed failed;
- the observations you recorded, marked as yours;
- how flows hand over to each other, as your own reading, since the map does not record it.

Say plainly that the names are your synthesis of the code, not confirmed requirements.
If something in the result calls for action, name it and say what you could do next.
Changing code or tests needs its own request from the user.

## 5. Changes since a revision

Use this when the user asks what a branch, a commit range or their uncommitted work
changes, where a change lands in the business flows, or whether tests cover it.

```
genesis map prepare --repo /absolute/app --base main
genesis map diff    --repo /absolute/app --session SESSION_ID
```

`--base REV` compares that revision with the working tree, or with `--head REV`. The
result of `prepare` adds `changes`, `changes_placed`, `change_status` and
`changed_files_not_analyzed`. The list of changes comes from the code alone, so `diff`
shows it before you do anything; rendering at this point is optional and gives the
same list on the static structure.

- `changes` has one entry per changed condition, call, loop, result or definition, and
  `source_*` entries for everything else that changed, such as a constant or a default
  value. A branch or loop that was added or removed as a whole is one entry that shows
  the whole block. `before` and `after` give the text of each side with an
  `evidence_id`.
- `placement` is the step of the current map a change belongs to. Without a `reason`,
  a step rests on the changed code itself. A `reason` says how the place was chosen
  otherwise. An `unassigned` change has no place on the map; report it as such.
- `tests` is what the test sources alone show. A test is linked when it calls the
  changed function, directly or through other calls, or requests a route that leads to
  it with an HTTP test client. `reached_only` at this point means only that; `unknown`
  means no such test was found.
- `possibly_affected` lists flows that can reach changed code without a step on it;
  `removed_flows` the entries that no longer exist; `unanalyzed_changes` the changed
  files Genesis did not analyze, such as other languages. Mention all three.

Reformatting, comments and code that only moved are not changes.

Then plan as in section 2 and describe flows as in section 3. Only the flows the changes
land on are needed: `status` lists them under `change.affected_flows`, and `next_task`
offers their tasks first. When they are done, `next_task` is `task_change`:

```
genesis map context --repo /absolute/app --session SESSION_ID --task task_change
```

It returns up to 30 changes that still need an explanation. For each one, read both
sides with `genesis map read --evidence`, read the tests listed for it, and search for
tests that reach it another way. A linked test may still not reach the change, for
example when it replaces the changed function with a stub. Then submit:

```json
{
  "changes": [
    {"change_id": "chg_9603691aeade3d47",
     "summary": "The review threshold now includes the boundary amount.",
     "effect": "A report of exactly the threshold amount goes to model review instead of being approved at once.",
     "verdict": "reached_only",
     "note": "The test submits 50 and 500 and accepts either status, so the boundary amount is never exercised.",
     "test_ids": ["head::tests/test_submit.py#test_submit_report_status"]},
    {"change_id": "chg_f1c02c12d9463145",
     "summary": "Approval no longer records the intermediate reviewed status.",
     "verdict": "not_reached",
     "note": "No test calls the approval route or approve_report."}
  ]
}
```

```
genesis map submit --repo /absolute/app --session SESSION_ID --task task_change --input /absolute/changes.json
```

- `summary` says in business terms what is different, and `effect` what it means for the
  flow. Do not describe the line edit. Write both in the user's language.
- `verdict` is your reading of the tests. `covered`: a test's input takes the changed
  path and the test asserts on the result. `reached_only`: tests call the code but miss
  the changed path or assert nothing about it; `note` says what is missing.
  `not_reached`: no test reaches it. `unknown`: you could not tell; `note` says why.
  Every verdict needs a `note`. Leave `verdict` out to keep the static result.
- `test_ids` names the tests your verdict is about, as `head::<path>#<function>`, for
  example `head::tests/test_api.py#test_refund`; a method is `#TestClass.test_name`.
  A test static analysis did not link may be named; the report marks it as identified
  by you. `not_reached` names no tests: describe near misses in `note`.
- The CLI refuses a verdict the test sources contradict: `covered` when none of the named
  tests contains an assertion, `not_reached` when a test calls the changed function
  itself or requests its route, an unknown `change_id` or test. A refusal changes
  nothing already accepted.
- An observation you recorded on a flow is shown as `introduced` when its evidence cites
  code this change added, or when its whole flow is new, and as `persisting` when it
  cites code the change modified. Cite the changed lines when the risk comes from them.
- Submissions add up. Ask for the context again until `changes_waiting` is 0. An
  unassigned change may be explained too, but nothing requires it.

Render as in section 4. In a change session the page is the map with the changes on it:
each change is shown inside the step it belongs to, with both sides, your explanation
and the test verdict; the flows that changed are open and indexed at the top; and what
has no step is listed after the map. `summary.md` lists the same changes by flow and
step, and `change-report.json` holds them as data. Exit code 0 means every change on the
map is explained and assessed and the flows they sit on are described. The rest of the
map may still be a static skeleton.

Tell the user, in their language: what changed in business terms, flow by flow; for each
change whether tests cover it and what is missing; the changes with no place on the map;
flows that are possibly affected or removed; and the files that were not analyzed. Say
that no test was run: a verdict is a reading of the test source, by static analysis or by
you, and never a statement that a test passed. Do not run tests yourself unless the user
asks for it.

## Later requests

- **What a branch or a pending change does:** section 5, with `--base` set to the
  revision it started from.

- **A question about an existing map:** read `.genesis/out/latest/summary.md` and
  `business-map.json`, and answer from them. Do not start a new analysis.
- **The code changed and the user wants the map again:** run `map prepare` again. New
  content gives a new session; plan and describe the flows as before.
- **Sharing:** `genesis map render ... --share` writes `graph.share.html` beside the
  normal page, without source excerpts. That file is the one to pass on.

`.genesis/sessions/` and `.genesis/out/` contain source text and are ignored by Git; do
not commit or publish them. `.genesis/.gitignore` itself may be committed. Do not edit
files under `.genesis/` by hand.

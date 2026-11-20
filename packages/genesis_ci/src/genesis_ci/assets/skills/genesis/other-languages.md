# Genesis for a project that is not Python

Follow this file when `map prepare` reports `"engine": "agent"`. It replaces sections
2, 3 and 5 of `SKILL.md`; locating the CLI, rendering and the later requests stay as
described there. The pages the user gets are the same.

What differs is who finds things. Genesis has no analyzer for this language, so there
are no facts, no detected entries and no check that a flow leaves nothing out:

- **You** find the ways into the system, read the code and describe each flow.
- **The CLI** freezes the source, confirms that every quote you cite is in the frozen
  file at the lines you give, checks that the steps form one connected flow, and
  places each changed line on the step that cites it.

A path you do not draw is not reported as missing. Read each entry to its ends,
including the failure paths, before you submit.

## 1. Prepare

```
genesis map prepare --repo /absolute/app
genesis map prepare --repo /absolute/app --base main
```

Without `--base` the session maps the code as it is. With `--base REV` it also lists
what changed since that revision. For one commit, a commit range, a branch, a pull
request or uncommitted work, choose `--base` and `--head` as step 1 of section 5 in
`SKILL.md` says; the flags mean the same here. The result has `session_id`, `files`
(how many source files were frozen) and `file_types`. Tests are told apart by their path:
`tests/`, `__tests__/`, `*.test.*`, `*.spec.*`, `*_test.*`.

If the project's main language is not Python but it has some Python files, `prepare`
answers with `"engine": "python"` and maps only those. Run it again with
`--engine agent`.

## 2. Plan

Find the entries yourself: routes, commands, jobs, queue and event handlers, exported
functions other systems call. Read the router, the command table and the job
registration, not only the file names. Then write the plan. It is what a reader sees
first, so write what the product does, not a list of endpoints.

```json
{
  "domains": [{"key": "checkout", "name": "Checkout"}],
  "flows": [
    {
      "key": "place",
      "name": "Place an order",
      "summary": "A shopper pays for a cart and gets a confirmation.",
      "tier": "primary",
      "domain": "checkout",
      "entries": [
        {
          "name": "POST /orders",
          "kind": "http_route",
          "evidence": [
            {"path": "src/routes.ts", "start_line": 6, "end_line": 9,
             "quote": "router.post(\"/orders\""}
          ]
        }
      ]
    }
  ]
}
```

```
genesis map plan --repo /absolute/app --session SESSION_ID --input /absolute/plan.json
```

- A flow is one business process a person would name. `tier` is `primary` for a process
  that decides something or has an effect, `supporting` for lookups and upkeep. Put the
  list, get, update and delete of one thing into one supporting flow.
- `kind` is one of `http_route`, `cli_command`, `task`, `scheduled`, `public_api`,
  `agent_tool`, `handler`, `main`.
- `quote` is a short piece of text copied from inside the cited lines. Line numbers
  refer to the file as `prepare` froze it.
- Each entry starts one flow. The plan can be submitted again; a flow whose entries did
  not change keeps its accepted description.
- In a change session you may plan only the flows the changed files belong to. Say so
  in your report.

Tell the user the scope before the long part: which flows you are about to describe and
what you left out.

## 3. Describe each flow

Take `next_task` from `status` and repeat until it is null or `task_change`.

```
genesis map status  --repo /absolute/app --session SESSION_ID
genesis map context --repo /absolute/app --session SESSION_ID --task TASK_ID
genesis map submit  --repo /absolute/app --session SESSION_ID --task TASK_ID --input /absolute/flow.json
```

`context` gives the entries with their source and, in a change session, the changes
this flow carries or could carry. Read on from there in the repository with your own
tools; `genesis map query --search TEXT` finds lines in the frozen source and gives
each an `evidence_id` you can cite instead of a range.

```json
{
  "name": "Place an order",
  "summary": "A shopper pays for a cart and gets a confirmation.",
  "steps": [
    {"key": "start", "name": "Shopper submits the order", "kind": "trigger",
     "evidence": [{"path": "src/routes.ts", "start_line": 6, "end_line": 7,
                   "quote": "router.post(\"/orders\""}]},
    {"key": "stock", "name": "Every item in stock?", "kind": "decision",
     "evidence": [{"path": "src/checkout.ts", "start_line": 15, "end_line": 15,
                   "quote": "inventory.inStock"}]},
    {"key": "out", "name": "Tell the shopper it is out of stock", "kind": "result",
     "evidence": [{"path": "src/checkout.ts", "start_line": 16, "end_line": 16,
                   "quote": "out_of_stock"}]},
    {"key": "charge", "name": "Charge the card", "kind": "external",
     "evidence": [{"path": "src/checkout.ts", "start_line": 20, "end_line": 20,
                   "quote": "stripe.charge"}]}
  ],
  "edges": [
    {"source": "start", "target": "stock", "relation": "sequence"},
    {"source": "stock", "target": "out", "relation": "branch", "branch": "no"},
    {"source": "stock", "target": "charge", "relation": "branch", "branch": "yes"}
  ],
  "observations": [
    {"statement": "Retries send no idempotency key, so a shopper can be charged twice.",
     "severity": "medium", "category": "data_integrity", "step": "charge",
     "evidence": [{"path": "src/checkout.ts", "start_line": 21, "end_line": 23,
                   "quote": "stripe.charge"}],
     "gap": "No test makes the payment provider time out."}
  ]
}
```

- Step `kind`: `trigger` (what sets the flow off; one per entry), `action`, `decision`,
  `external` (a call to an outside system: payment provider, database, model, queue),
  `result` (an end the user or caller sees).
- Name steps in business language. Cite the few lines that do what the step says, not
  the whole function: a change belongs to the step that cites its lines, and a wide
  citation pulls unrelated changes onto the step.
- Every step must be reachable from a trigger through edges.
- Edge `relation`: `sequence`, `branch`, `loop`, `exception`, `call`. A `branch` edge
  leaves a `decision` and names in `branch` the outcome it takes, in words a reader
  understands. A decision has an edge for each way it can go.
- Draw the failure paths and retry loops the code has.
- If the code does not show a relation, set `"resolution": "candidate"` or `"unknown"`
  with a `reason`. The page marks such a step as unconfirmed.
- `observations` are risks you noticed, each on a step with the lines that show it.
  `severity` is `info`, `low` or `medium`; `category` is `reliability`, `correctness`,
  `data_integrity`, `security`, `performance` or `other`.
- Do not send `anchors`, `omitted` or `unexpanded_reason`.
- **Stages.** A reader takes in about seven blocks across. A flow that is wider gets
  `stages`: each folds a run of steps into one block, and the reader opens the block to
  see its steps. This is where you abstract, so name a stage for what its steps get done
  together ("Check the payment", not "Steps 3 to 6"):

  ```
  "stages": [
    {"key": "pay", "name": "Charge the card and handle a decline", "steps": ["charge", "declined", "retry"]}
  ]
  ```

  A stage holds two or more steps that run one after another; no step outside it may
  run between them. The trigger stays outside. Keep outside the stages the decisions
  and outcomes a reader needs to follow the flow, and fold the work in between. A step
  belongs to one stage at most.

A result with `too_wide` is accepted, but the flow is more than seven blocks across with
its stages folded: the map stays partial and `next_task` comes back to it until you add
or widen stages.

A submission is accepted or rejected as a whole. `errors` names each problem by the
step or edge it is about; fix them and submit again. `quote_not_found` means the text
is not in those lines of the frozen file: read the file again and correct the range.

## 4. Changes since a revision

In a change session, `genesis map diff` lists the changes at any time: each is a run of
changed lines with `before` and `after`, and a `placement`.

- A change is `projected` when a step cites its lines. Describing the flows is what
  brings changes onto the map.
- For an `unassigned` change in code a flow runs through, add or widen a step so that it
  cites those lines, and submit the flow again. Leave a change unassigned only when no
  flow passes through it; report it as off the map.
- A change that only removes lines has no line in the current code for a step to cite.
  It stays off the map: explain it like any other change and report it as off the map.
- `unanalyzed_changes` are changed files that are not source, such as configuration.
  Mention them.

The CLI takes explanations before any flow is described, but a change then has no
place on the map and is only listed as off it. So plan and describe the flows the
changed code belongs to first; only those flows are needed.

When the flows are done, `next_task` is `task_change`:

```
genesis map context --repo /absolute/app --session SESSION_ID --task task_change
genesis map submit  --repo /absolute/app --session SESSION_ID --task task_change --input /absolute/changes.json
```

```json
{
  "changes": [
    {
      "change_id": "chg_18745c68532a2379",
      "summary": "Free shipping now starts above $35 instead of $50.",
      "short_summary": "Free shipping from $35",
      "verdict": "covered",
      "note": "The test places orders at 35 and 35.01 and asserts which total includes shipping.",
      "tests": [
        {"name": "free shipping starts above 35", "asserts": true,
         "evidence": [{"path": "tests/checkout.test.ts", "start_line": 8, "end_line": 13,
                       "quote": "toBe(40.99)"}]}
      ]
    },
    {
      "change_id": "chg_8fd88ccb25378bae",
      "summary": "A card charge that times out is retried, up to 3 times.",
      "verdict": "not_reached",
      "note": "No test makes the payment provider time out."
    }
  ]
}
```

- `summary` says what is different for a user or another system, not which lines moved.
- Every change outside test files needs a `verdict` and a `note`. Find the tests
  yourself and read them:
  - `covered`: a cited test takes the changed path and asserts on the result. At least
    one cited test has `"asserts": true`.
  - `reached_only`: tests run the code but miss the changed path, or assert nothing
    about it. Cite them; the note says what is missing.
  - `not_reached`: no test gets there. Cite none.
  - `unknown`: it could not be told; the note says why.
- A change to a test file gets a `summary` and no verdict.
- Verdicts come from reading tests. Never say a test ran or passed.

This submission takes less than the one section 5 of `SKILL.md` describes for Python.
Anything else is refused:

- One entry per change, with `change_id`. There is no `change_ids`: when several
  changes are parts of one change in behaviour, give each its own entry.
- Tests are cited under `tests`, with evidence. There is no `test_ids`.
- `short_summary` and `effect` are optional, as in `SKILL.md`.
- There is no `risks` list. Read for risks as step 4 of section 5 in `SKILL.md`
  describes, then record each risk as an `observation` on the step it concerns and
  submit that flow again.

Assessments can be sent in several submissions; each replaces what was said before
about the changes it names.

## 5. Render and report

Render as in section 4 of `SKILL.md`. Exit code 0 means every planned flow is accepted
and, in a change session, every change is explained.

Report as described there, with one addition. Say in one sentence that Genesis has no
analyzer for this language: each step was checked against the source, and a path you
did not draw would not have been flagged.

---
name: genesis-review
description: Review Python changes with Genesis when explicitly requested or asked to check change risks. Under a project Genesis review convention, use for the intent to prepare changes for reviewers or draft their review description, in any language (prepare for review, cut a CR, open a PR, raise an MR). Match intent, not exact keywords. Explain existing reports without starting a new analysis.
---

# Genesis change review

Run the installed Genesis CLI and explain its actual report. Genesis performs
local static analysis; the optional hosted semantic stage uses the Genesis
team's private service. This skill supplies invocation guidance, not analysis
results or inferred user requirements.
If the request is to explain an existing report, read that report and its
evidence directly; do not start a new analysis.

## When preparing a CR/PR

When the project has opted into Genesis before CR/PR preparation, run this review
before finalizing the review description or submitting the change. Recognize
review-handoff intent from the conversation, including requests to draft the
review description or get changes ready for colleagues. CR, pull request/PR,
and merge request/MR are equivalent here; examples are not an exhaustive list
or a required command language. A standalone commit/push or a question about
review terminology does not imply a new review. Clarify ambiguous handoffs.
Honor an explicit request to skip Genesis. A CR request alone does not authorize hosted
source upload; follow the consent steps below. This skill does not install a
Git hook, intercept terminal pushes, or enforce a merge gate.

Review the whole intended change set, not just the latest commit. Reuse a prior
Genesis report only after verifying its frozen source, scope, and analysis inputs
still match. If code changed, explain that the previous result is stale and apply
the preview/consent steps to the new scope. Keep automatic failure retries disabled.
For changes outside the supported Python scope, state the limitation.

Before the CR handoff, explain the actual Genesis findings, report location, and
remaining gaps. If it cannot run or finishes only partially, report that status
and follow the user's instructions for continuing; never present it as a pass.
Code fixes and publishing the CR require their own authorization under the user's
request and project policy.

## Locate the CLI and choose the change

Use the `scripts/run_genesis.py` next to this skill through a trusted Python 3
interpreter, for example `python3 -I /absolute/path/to/this/skill/scripts/run_genesis.py`.
The installer records its Genesis Python environment in `runtime.json`; the
runner preserves the application's working directory and all CLI exit codes.
Run the runner with `version` first. If that environment has moved or is missing,
reinstall the skill from the current Genesis installation. Do not silently run
a repository-provided executable named `genesis`.

Determine the target Git root from the user's workspace, not from the CLI/skill
installation directory. Inspect Git status and local revisions. State the scope:

- Uncommitted edits: `analyze --repo /absolute/app --base HEAD`, without `--head`.
- Branch changes: resolve the user's target branch and its merge-base with HEAD;
  pass that commit as `--base` and `--head HEAD` for committed changes only. Omit
  `--head` if the user also wants tracked worktree edits included.
- A specified commit pair: pass the actual earlier/later revisions as
  `--base`/`--head`. Do not assume `HEAD~1` or `main` matches the user's request.

List new files and add `--include-untracked` only when they belong to the requested
review. Genesis ignores untracked files by default. If the intended comparison
is empty or no base commit exists, explain that; do not invent commits or
manufacture a diff. Ask only when choosing a different scope changes the review.

## Prepare locally, then send only when authorized

First run the chosen `analyze` command with `--preview-only` and a new absolute
`--output` directory under the target repository's `.genesis/analyses/`. Read
`send-preview.txt` and the terminal's destination. No network call is made in
this mode. If a preview cannot be built, retain/explain the local report.

The payload can include actual source excerpts, paths, static facts and selected
documents. Explain the destination and payload scope in chat. Upload approval
may already be explicit in the user's request or established project policy;
otherwise ask before sending. Installing this skill or asking for a local review
does not itself authorize a hosted upload.

Once approved, replay the exact frozen input rather than recapturing worktree
edits: `analyze --repo /absolute/app --snapshot /absolute/preview/snapshot
--accept-send --output /absolute/new-result`. Pass the same context/exclusion,
source-root and optional-document options used for the preview. Snapshot mode
cannot be combined with `--base`, `--head` or `--include-untracked`. Use a fresh
output directory for each invocation. If files changed after the preview,
explain that the result covers the frozen input; a newer review needs a new
preview. Keep `.genesis/config.toml` and any external review/cost inputs unchanged
as well; if they changed, prepare a new preview. Never add unapproved context
between preview and send.

If the user requests offline analysis, use `--offline` directly. If consent is
declined, explain the already-written local report and stop; do not retry online.
Without connection settings, the CLI uses official shared trial access; no
`auth` or model-provider key is needed. Keep existing personal credentials and
endpoint settings. Do not inspect, echo, copy, or manufacture keys.

Task/PR/requirements documents and `.genesis/flows.yaml` are optional. Do not
create them from the conversation or run `flows init` as an onboarding prerequisite.
Pass optional intent files only when the user actually supplies them for review.
Do not run application code/tests or change code merely to generate a report.

## Read and explain the result

- Exit `0`: analysis completed within its declared scope; not approval or proof
  that the change is safe.
- Exit `2`: a usable partial report. Read it; do not mistake it for a crashed
  CLI or automatically retry a paid/limited request.
- Exit `1`: input/setup failure; inspect the error before attempting a correction.

Read `summary.md` first, then `report.json` for statuses and `report.md` for
supporting evidence. Explain the changed business behavior, affected paths,
cost/wait/failure risks, existing test evidence, and recommended verification in
the user's language. Separate findings from uncertainties and the agent's own
observations. Cite concrete before/after evidence and report locations. If the
service is unavailable or quota is exhausted, explicitly say semantic analysis
did not complete; do not substitute an agent-written review as a Genesis result.

Keep `.genesis/` artifacts private: they may contain frozen source. Do not commit
or publish them automatically. Finishing a review does not authorize fixing,
committing, or merging changes.

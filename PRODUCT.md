# Product

<!-- impeccable:product-schema 1 -->

The design brief for the viewer page (`view.html`, source in `viewer/`), read by people who change the page and by the design-review tool they use on it; for what Genesis is and how to use it, see [README.md](README.md).

## Platform

web

## Stack

React with a build step. The build is compiled into one self-contained HTML file that the
Python CLI fills with data and writes to disk. The page loads nothing from the network
when it is opened.

## Users

- Primary: product managers, founders and business people who ship software with coding
  agents and do not read the code. They need to see what the product does as business
  flows, and what a change (a PR, or an agent's uncommitted work) alters in product logic.
- Secondary: engineers reviewing the same change, who need the code evidence behind each
  statement.

## Product Purpose

Genesis turns a repository into a map of business flows backed by code evidence, and
shows what a change does to those flows: where existing tests do not cover the new
behaviour, and the risks the agent found while reading the change. Success: a person who
cannot read code opens the page and can say what changed for users, which flows it
touched, what no test checks and what could break.

## Positioning

Code-diagram tools explain engineering structure. Genesis shows product-level flows, with
branches and failure paths, described by the user's own coding agent and checked against
the source by a deterministic CLI, every step backed by code evidence; and for a change,
the before and after of the product logic placed on the flow, with a test-coverage verdict
for each change and the risks the agent raised.

## Operating Context

- Written by `genesis map render` in the local Python CLI, which a coding agent (Claude
  Code, Codex) drives through the genesis skill. Opened from `file://` in a browser.
- In a review the agent also describes the flows the changes land on, so that changes sit
  on named business steps. A flow it did not describe stays drawn from the code alone.
- Before the first step the agent checks the project's size with `genesis map size`, so
  the user knows how long it takes. Files kept out by a limit make the result partial;
  for a map, the page then shows `Partial` next to the size of the map.
- `genesis map render --share` writes `view.share.html` and `graph.share.html` beside the
  normal pages, without source excerpts; those are the files people pass on. A review
  still shows the changed lines.
- Data comes from two draft contracts in `packages/genesis_contracts`: the business map
  (`business_map.py`, schema 0.1.0) and the change report (`change_report.py`, schema
  0.1.0). This page only reads them. The CLI adds source excerpts from the evidence bundle
  (`evidence_bundle.py`); `--share` leaves them out.

## Capabilities and Constraints

- Python is analyzed statically by the CLI and gets the most accurate results. Other
  languages work through the coding agent: it reads the code and the CLI checks every
  citation against the source, but a path the agent misses is not flagged. A project with
  Python and other languages is read one way per run. The pages are the same either way.
- Changes are projected onto the current (head) map. There is no map of the base side,
  apart from removed flows and the names of removed steps.
- Test verdicts come from reading source. The page must never imply that a test ran.
- Risks are the agent's own reading; the CLI has no rules that detect them, and an
  agent's risk is never rated high. A change is marked as a risk when it brings one: an
  observation the agent recorded about lines the change wrote, or a risk in the report
  that names the change. The
  change's panel lists them. A risk that names only changes to test code is not shown.
- Self-contained: fonts, scripts and images are built into the file, and nothing is loaded
  from the network when the page opens. The one request the page can make is to GitHub's
  compare API, and only when the reader opens the commit tree. Every name, label and
  source excerpt comes from the analysed repository or an agent and must be rendered as
  text, never as markup.
- The page is written as `view.html` beside `graph.html`, a plain outline of the same map
  that needs no script. `graph.html` keeps its own renderer and tests.
- Fixed interface text follows the language of the content automatically. It exists in
  Chinese and English.
- Subtraction is a requirement: one diagram of the product's flows and the change it
  carries. The page has no export, sharing or presentation features. The canvas has zoom,
  fit to view and a switch between light and dark. Modules and stages open and fold. A
  step opens a panel with its code and its tests, and an Input / output tab only when the
  agent described the data the step takes and returns. A flow can be walked through in
  the order it usually runs. A review adds the list of changes, with previous and next,
  and the commit tree.

## Brand Commitments

- Name: Genesis. Icon and wordmark: `assets/readme/favicon.svg`,
  `assets/readme/wordmark-light.svg`, `assets/readme/wordmark-dark.svg`.
- The icon and wordmark are black and off-white. The viewer page is not limited to that:
  it has its own theme, in `viewer/graphical/`, with a light and a dark rendition.

## Evidence on Hand

- `fixtures/business-map/`: a small synthetic expense app with hand-written contract
  samples (complete, partial and skeleton maps; a change with a report and evidence).
- `docs/change-analysis-benchmark.md`: a comparison of Claude Code and Codex, with and
  without Genesis, on 10 commits from 5 open-source Python repositories.
- There are no customer maps, usage numbers or testimonials to show.

## Product Principles

1. Show the product, not the code. Business language leads; code is evidence on request.
2. Keep every statement honest about its basis: agent synthesis or static fact, resolved
   or candidate, test verdicts read from source.
3. Change first. When a change exists, what changed for users comes before the rest of
   the map; among the changes, a new risk comes first, then what is untested.
4. Subtract. One diagram and the change it carries; nothing a reader did not come for.

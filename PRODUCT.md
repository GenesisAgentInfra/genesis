# Product

<!-- impeccable:product-schema 1 -->

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
shows what a change does to those flows, including where existing tests do not cover the
new behaviour. Success: a person who cannot read code opens the page and can say what
changed for users, which flows it touched, and what no test checks.

## Positioning

Code-diagram tools explain engineering structure. Genesis shows product-level flows, with
branches and failure paths, described by the user's own coding agent and checked against
the source by a deterministic CLI, every step backed by code evidence; and for a change,
the before and after of the product logic placed on the flow, with a test-coverage verdict
for each change.

## Operating Context

- Written by `genesis map render` in the local Python CLI, which a coding agent (Claude
  Code, Codex) drives through the genesis skill. Opened from `file://` in a browser.
- `genesis map render --share` writes a variant without source excerpts; that file is the
  one people pass on.
- Data comes from two draft contracts in `packages/genesis_contracts`: the business map
  (`business_map.py`, schema 0.1.0) and the change report (`change_report.py`, schema
  0.1.0). This page only reads them.

## Capabilities and Constraints

- Python is analyzed statically by the CLI and gets the most accurate results. Other
  languages work through the coding agent: it reads the code and the CLI checks every
  citation against the source, but a path the agent misses is not flagged. The pages are
  the same either way.
- Changes are projected onto the current (head) map. There is no map of the base side,
  apart from removed flows and the names of removed steps.
- Test verdicts come from reading source. The page must never imply that a test ran.
- Self-contained: fonts, scripts and images are built into the file, and nothing is loaded
  from the network when the page opens. The one request the page can make is to GitHub's
  compare API, and only when the reader opens the commit tree. Every
  name, label and source excerpt comes from the analysed repository or an agent and must
  be rendered as text, never as markup.
- The page is written as `view.html` beside `graph.html`, a plain outline of the same map
  that needs no script. `graph.html` keeps its own renderer and tests.
- Fixed interface text follows the language of the content automatically. It exists in
  Chinese and English.
- Subtraction is a requirement: one flow diagram and the change it carries. No export
  menu, share cards, presentation mode, lens tracing or AI follow-ups. The page's own
  controls are zoom, fit to view, a switch between light and dark, and a walk through one
  flow in the order it usually runs.

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
- No real customer maps, usage numbers or testimonials exist. Do not fabricate any.

## Product Principles

1. Show the product, not the code. Business language leads; code is evidence on request.
2. Keep every statement honest about its basis: agent synthesis or static fact, resolved
   or candidate, test verdicts read from source.
3. Change first. When a change exists, what changed for users and what is untested comes
   before the rest of the map.
4. Subtract. One diagram and the change it carries; nothing a reader did not come for.

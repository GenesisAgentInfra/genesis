# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React with a build step (user's choice, 2026-11-11). The build is compiled into one
self-contained HTML file that the Python CLI fills with data and writes to disk. The page
loads nothing from the network when it is opened.

## Users

- Primary: product managers, founders and business people who ship software with coding
  agents and do not read the code. They need to see what the product does as business
  flows, and what a change (a PR, or an agent's uncommitted work) alters in product logic.
  Confirmed by the user on 2026-11-11 and in the team huddle of 2026-11-10.
- Secondary: engineers reviewing the same change, who need the code evidence behind each
  statement. (Inferred from the evidence-backed design of the CLI; not separately confirmed.)

## Product Purpose

Genesis turns a repository into a map of business flows backed by code evidence, and
shows what a change does to those flows, including where existing tests do not cover the
new behaviour. Success: a person who cannot read code opens the page and can say what
changed for users, which flows it touched, and what no test checks.

## Positioning

Code-diagram tools such as archify and Understand-Anything explain engineering structure.
Genesis shows product-level flows, with branches and failure paths, built by a
deterministic CLI and worded by the user's own coding agent, every step backed by code
evidence; and for a change, the before and after of the product logic placed on the flow,
with a test-coverage verdict for each change.

## Operating Context

- Written by `genesis map render` in the local Python CLI, which a coding agent (Claude
  Code, Codex) drives through the genesis skill. Opened from `file://` in a browser.
- `genesis map render --share` writes a variant without source excerpts; that file is the
  one people pass on.
- Data comes from two draft contracts in `packages/genesis_contracts`: the business map
  (`business_map.py`, schema 0.1.0) and the change report (`change_report.py`, schema
  0.1.0). Dean (欧阳) owns the contracts and the CLI; this page only reads them.

## Capabilities and Constraints

- Python repositories only, for now.
- Changes are projected onto the current (head) map. There is no map of the base side,
  apart from removed flows and the names of removed steps.
- Test verdicts come from reading source. The page must never imply that a test ran.
- Offline and self-contained: no external fonts, scripts or images at view time. Every
  name, label and source excerpt comes from the analysed repository or an agent and must
  be rendered as text, never as markup.
- The new page is generated beside the existing `graph.html`; `graph.html`, its renderer
  and its tests stay untouched until the team decides to replace them (user decision,
  2026-11-11).
- Fixed interface text follows the language of the content automatically (user decision,
  2026-11-11).
- Subtraction is a requirement: one flow diagram and the change it carries. No theme
  switcher, export menu, share cards, presentation mode, path or lens tracing, or AI
  follow-ups (user's explicit instruction, 2026-11-11).

## Brand Commitments

- Name: Genesis. Icon and wordmark: `assets/readme/favicon.svg`,
  `assets/readme/wordmark-light.svg`, `assets/readme/wordmark-dark.svg`.
- The marketing site (`genesis-website`) is black and white; this has not been made
  binding for the CLI's pages.

## Evidence on Hand

- `fixtures/business-map/`: a small synthetic expense app with hand-written contract
  samples (complete, partial and skeleton maps; a change with a report and evidence).
- No real customer maps, usage numbers or testimonials exist. Do not fabricate any.

## Product Principles

1. Show the product, not the code. Business language leads; code is evidence on request.
2. Keep every statement honest about its basis: agent synthesis or static fact, resolved
   or candidate, test verdicts read from source.
3. Change first. When a change exists, what changed for users and what is untested comes
   before the rest of the map.
4. Subtract. One diagram and the change it carries; nothing a reader did not come for.

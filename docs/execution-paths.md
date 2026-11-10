# Execution paths with code evidence

The CLI extracts static facts from frozen Git snapshots. The service interprets
that code as part of its semantic analysis, communicating with the CLI through
the API. Application flows described in the report are separate from where
Genesis itself is deployed.

The CLI requests `behavior_review` v2. The service advertises support through
`/capabilities` with `behavior_review_versions: ["1", "2"]`, while retaining the
legacy scalar version `1`. The CLI negotiates downward only: v2, then v1, then
no behavior comparison. Negotiation cannot add material to the approved upload
or retry the analysis POST.

Version 2 retains the scenario, condition, before/after behavior, explanation,
impact, and preserved behavior, and adds up to six execution paths. Each path
describes either the base or head revision. Every step and link cites code
evidence from that same revision. The model uses the existing call count,
output budget, and single repair allowance.

For example, "wait for notification after a successful submission, then return
the result" can be represented as submission → wait for notification → return.
If the service cannot confirm the notification implementation, the outcome or
link remains unknown, with an explanation of the missing evidence. Semantic
inference does not establish a resolved static call or observed execution.
Validation rejects missing code references, references to the wrong revision,
and links to nonexistent steps.

`summary.md` shows scenarios, steps, outcomes, and missing links. `report.md`
adds statuses, IDs, reasoning, and evidence. Both render the same analysis
without another model rewrite. JSON reports use schema `0.3.0`; readers remain
compatible with existing `0.1.0` and `0.2.0` reports.

Entry discovery also considers public methods with an explicit enclosing class
as candidates. Private methods, nested functions, and duplicate definitions are
excluded from these new entry candidates. This does not prove instance
construction, decorator registration, or reflective dispatch. Existing candidate
relationship retrieval still supplies source to the service without turning
guesses into resolved call edges.

Offline tests verify contracts, references, and the client/service handoff.
They do not establish better model quality. Model evaluations must pin the CLI,
service, prompt, and presentation versions, and retain earlier answers and scores.

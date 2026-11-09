# Evidence for agent-change review scenarios

Researched 2026-11-09. Primary issue pages and their current GitHub API status were checked. These sources establish reported failure modes, not their prevalence, customer demand for Genesis, or Genesis detection accuracy. No source reproduction was executed during this research. Framework-version-specific examples must not be generalized into current universal defects.

## 1. A tool-selection setting keeps the agent calling tools

- **Source:** [OpenAI Agents Python issue #191](https://github.com/openai/openai-agents-python/issues/191), opened March 17, 2025; closed as not planned.
- **Observed report:** A retrieval agent repeatedly called a successful search tool instead of producing its answer. Raising `max_turns` to 100 did not resolve it. Its configuration included `tool_choice="required"`. [The author reported](https://github.com/openai/openai-agents-python/issues/191#issuecomment-2728909350) that removing that setting resolved the behavior. [Repository collaborator `rm-openai` acknowledged](https://github.com/openai/openai-agents-python/issues/191#issuecomment-2730585723) the configuration pitfall and linked [PR #203](https://github.com/openai/openai-agents-python/pull/203), introducing tool-use behavior controls.
- **Suitable scenario:** “One configuration change, and your agent keeps calling tools instead of finishing.”
- **Genesis mapping to verify:** Review the changed Python call sites, conditions and visible loop/stop controls; explain conditional cost/wait risk. Do not claim Genesis understands every framework's runner internals, predicts exact spend, or has detected this specific issue.
- **Evidence strength:** Reproduction code and author-confirmed workaround; collaborator acknowledgement. Historical configuration interaction, not evidence that all current Agents SDK versions retain the same behavior.

## 2. An added routing middleware lets a rejected action execute

- **Source:** [LangChain issue #40492](https://github.com/langchain-ai/langchain/issues/40492), opened September 16, 2026; still open when checked.
- **Observed report:** An offline example on `langchain==1.4.0` / `langgraph==1.2.11` compares a normal human-review path against the same graph with an additional `after_model` middleware returning `jump_to="tools"`. The rejected marker-writing tool runs in the latter case. [A contributor independently reproduced it](https://github.com/langchain-ai/langchain/issues/40492#issuecomment-5693992598). [The original author explicitly separates](https://github.com/langchain-ai/langchain/issues/40492#issuecomment-5789210288) that demonstrated case from unverified claims involving regenerated tool-call IDs.
- **Suitable scenario:** “You add a route, but an action can now run after the user rejects it.”
- **Genesis mapping to verify:** Explain changes to visible application branches and affected call paths; identify which approval invariants need tests. No demonstrated framework-internal or security-vulnerability detection coverage; a source-only application review may lack the dependency code needed to identify this defect.
- **Evidence strength:** Deterministic published reproduction and independent contributor confirmations. No independently executed reproduction in this research and no released fix verified. Do not say every added middleware bypasses approval.

## 3. Resuming after a timeout repeats an action that already succeeded

- **Source:** [LangGraph issue #9185](https://github.com/langchain-ai/langgraph/issues/9185), opened October 4, 2026; closed as not planned on October 16, 2026.
- **Observed report:** A local fake payment provider commits a payment but responds after the tool timeout. Resuming the failed tool node produces a second payment. The issue supplies a no-network/no-key reproduction and output. [Repository contributor `eliornl` explains](https://github.com/langchain-ai/langgraph/issues/9185#issuecomment-6221463411) that a node without a saved result runs again and side effects require idempotency; it was closed in favor of [documentation issue #9240](https://github.com/langchain-ai/langgraph/issues/9240).
- **Suitable scenario:** “The request timed out—but the action happened. Retrying it can do it twice.”
- **Genesis mapping to verify:** Review visible retry/failure paths, affected side-effecting calls, and test-source assertions; identify missing timeout/replay checks. Do not claim runtime deduplication, exactly-once execution, or inspection of external provider state.
- **Evidence strength:** Published local reproduction plus repository explanation of intended resume semantics. This is a recovery/application design hazard, not a claimed unfixed LangGraph bug or proof of real financial loss.

## README use

Keep the scenarios short and link their issue sources directly. Describe Genesis as helping review changed behavior, affected paths, cost/wait risks and verification gaps from the supplied Python evidence. Keep the capability mapping conditional where framework/runtime semantics are unavailable. These examples are not Genesis benchmark results.

Avoid a “tests pass but production fails” claim unless a source actually establishes passing tests. A missing failure-path test can be a review question, not an asserted historical fact about these projects.

## Local capability evidence

Inspected in the CLI checkout based on commit `ebdf401`; these are source/contracts, not measured detection results on the external examples:

- [`rules.py`](../../packages/genesis_ci/src/genesis_ci/rules.py): structural comparisons for recognized SDK call sites, direct awaits and visible loop bounds; explicitly disclaims inferred runtime counts and prices.
- [`impact.py`](../../packages/genesis_ci/src/genesis_ci/impact.py): source-backed call and reachable-tool graph, reverse callers and bounded reachability.
- [`pytest_context/report.py`](../../packages/genesis_ci/src/genesis_ci/pytest_context/report.py): associated test sources and recognized assertions; explicitly says no tests ran and business acceptance coverage is unproven.
- [`models.py`](../../packages/genesis_contracts/src/genesis_contracts/models.py): `VerificationSuggestion` (line 298) carries scenarios, suggested assertions and evidence; `BehaviorChange` (line 333) requires source references for each described before/after side and limitations for a missing side. Contracts establish report structure, not semantic model accuracy.

No full LangGraph/Pydantic runner interpretation, hidden dependency source inspection, external state verification, runtime enforcement, or guarantee of catching these cases is established by those modules.

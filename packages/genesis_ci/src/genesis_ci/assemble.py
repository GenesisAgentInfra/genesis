"""Project typed local stages into the established B4 input contract."""

from genesis_contracts.models import CapabilityStatus, Limitation, LocalAnalysis, SectionStatuses
from genesis_contracts.validation import validate_local_analysis

from .behavior import build_behavior_view


def build_local_analysis(
    snapshot, extraction, patterns, impact, flows, tests, findings=(), estimates=()
):
    analysis = extraction.analysis
    limitations = (
        *flows.limitations,
        Limitation(
            code="static_scope",
            message="Static Python subset only; dynamic calls, fixture execution and runtime behavior are not proven.",
            affects_completeness=False,
        ),
    )
    if analysis.change_set.unresolved:
        limitations += (
            Limitation(
                code="python_inputs_incomplete",
                message="; ".join(analysis.change_set.unresolved),
                affects_completeness=True,
            ),
        )
    test_gaps = any(t.side.value == "head" and t.limitations for t in tests)
    if test_gaps:
        limitations += (
            Limitation(
                code="test_context_partial",
                message="Static test context has unresolved fixture, parametrization or mock configuration; see tests.json per-test limitations.",
                affects_completeness=True,
            ),
        )
    local = LocalAnalysis(
        behavior_view=build_behavior_view(extraction),
        snapshot=snapshot.capture.manifest,
        evidence=extraction.registry.freeze().evidence_catalog(),
        change_set=analysis.change_set,
        facts=analysis.facts,
        agent_loops=tuple(item.loop for item in patterns.loops),
        impact_graph=impact.graph,
        flows=flows.head.flows,
        flow_impacts=tuple(item.impact for item in flows.impacts if item.side.value == "head"),
        test_definitions=tuple(item.definition for item in tests),
        intents=flows.intents,
        rule_findings=findings,
        estimates=estimates,
        capabilities=SectionStatuses(
            # Code behavior can be reviewed without a declared business requirement.
            # Intent alignment is added only when confirmed sources are supplied.
            behavior_intent=analysis.facts.coverage,
            flow_impact=flows.coverage,
            cost_risk=CapabilityStatus(
                status="insufficient_context", reason="Model call quantities or prices are unknown"
            )
            if any(e.unknowns for e in estimates)
            else patterns.coverage,
            acceptance_tests=CapabilityStatus(
                status="analyzed",
                analyzed_scope="Static test definitions and assertions supplied for semantic review; execution/coverage not proven",
            )
            if not test_gaps
            and any(t.side.value == "head" and t.definition.association.targets for t in tests)
            else CapabilityStatus(
                status="insufficient_context",
                reason="Associated head tests are missing, or static fixture/mock context is incomplete",
            ),
            verification=analysis.facts.coverage,
        ),
        limitations=limitations,
    )
    validate_local_analysis(local)
    return local

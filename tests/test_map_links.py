"""Cross-flow relations require an actual call target and evidence on both ends."""

from types import SimpleNamespace

from genesis_ci.business_map.links import flow_links
from genesis_contracts.business_map import MapLink
from genesis_contracts.map_tasks import MapPlan
from test_map_loop import API, REVIEW, src
from test_map_loop import workspace as workspace


def test_assembly_extracts_entry_calls_with_real_evidence(workspace):
    from genesis_ci.business_map.python_entries import entry_id

    submit = next(e for e in workspace.entries().values() if e.symbol_id == API + "#submit_report")
    plan = MapPlan.model_validate(
        {
            "flows": [
                {"key": "submit", "name": "提交报销", "entry_ids": [submit.entry_id]},
                {
                    "key": "review",
                    "name": "模型审核",
                    "entry_ids": [entry_id(REVIEW + "#review_with_model")],
                },
            ],
            "proposed_entries": [
                {
                    "symbol_id": REVIEW + "#review_with_model",
                    "kind": "public_api",
                    "reason": "审核业务入口",
                    "evidence": [src(REVIEW, 6, "async def review_with_model(report):")],
                }
            ],
        }
    )
    workspace.save_plan(plan)
    result = workspace.stored_map()
    assert len(result.links) == 1
    link = result.links[0]
    assert link.name == "模型审核" and link.relation == "call"
    assert link.resolution == "resolved"
    assert link.anchors and link.source_evidence_ids and link.target_evidence_ids
    assert link.source.step_id and link.target.step_id
    assert link.reason and "amount >= THRESHOLD" in link.reason
    evidence = {e.evidence_id for e in result.evidence}
    assert set(link.source_evidence_ids + link.target_evidence_ids) <= evidence


def test_candidates_and_shared_helpers_never_become_confirmed_flow_calls():
    fp = "fp_" + "a" * 24
    a = {
        "flow_id": "a",
        "name": "提交",
        "entries": [{"symbol_id": "app.py#a", "evidence_ids": ["entry_a"]}],
        "steps": [{"step_id": "call", "kind": "action", "anchors": [fp]}],
    }
    b = {
        "flow_id": "b",
        "name": "审核",
        "entries": [{"symbol_id": "app.py#b", "evidence_ids": ["entry_b"]}],
        "steps": [],
    }
    fact = SimpleNamespace(
        side="head",
        kind="call",
        symbol_id="app.py#a",
        fingerprint=fp,
        target=SimpleNamespace(
            status="candidate", targets=["app.py#b"], reason="Unknown receiver type"
        ),
        evidence_ids=["call_evidence"],
        guards=[],
    )
    facts = SimpleNamespace(facts=[fact])
    link = MapLink.model_validate(flow_links([a, b], facts)[0])
    assert link.resolution == "candidate" and link.reason == "Unknown receiver type"
    fact.target = SimpleNamespace(
        status="resolved", targets=["app.py#b", "app.py#other"], reason=None
    )
    assert flow_links([a, b], facts)[0]["resolution"] == "candidate"
    fact.symbol_id = "app.py#shared_helper"
    assert flow_links([a, b], facts) == []
    fact.symbol_id = "app.py#a"
    fact.target = SimpleNamespace(status="unresolved", targets=[], reason=None)
    assert flow_links([a, b], facts) == []

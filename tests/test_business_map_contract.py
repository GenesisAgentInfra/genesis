"""Business map contract: the samples hold, and each consistency rule rejects its violation."""

import copy
import json
from pathlib import Path

import pytest
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.schemas import map_schemas
from jsonschema import Draft202012Validator
from pydantic import ValidationError

SAMPLES = Path(__file__).parents[1] / "fixtures" / "business-map"
OTHER_ANCHOR = "fp_" + "0" * 24


def load(name):
    return json.loads((SAMPLES / f"expense-{name}.json").read_text(encoding="utf-8"))


def flow(data, flow_id):
    return next(item for item in data["flows"] if item["flow_id"] == flow_id)


def step(data, step_id):
    return next(
        item for entry in data["flows"] for item in entry["steps"] if item["step_id"] == step_id
    )


def edge(data, source, target):
    return next(
        item
        for entry in data["flows"]
        for item in entry["edges"]
        if (item["source"], item["target"]) == (source, target)
    )


def rejects(name, mutate, message):
    data = copy.deepcopy(load(name))
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        BusinessMap.model_validate(data)


@pytest.mark.parametrize("name", ["complete", "skeleton", "partial"])
def test_samples_match_the_model_and_the_exported_schema(name):
    data = load(name)
    parsed = BusinessMap.model_validate(data)
    assert parsed.model_dump(mode="json", exclude_none=True) == data
    Draft202012Validator(map_schemas()["business-map.schema.json"]).validate(data)


def test_samples_cover_the_three_states():
    complete, skeleton, partial = load("complete"), load("skeleton"), load("partial")
    assert complete["analysis_status"] == "complete"
    assert {item["stage"] for item in complete["flows"]} == {"synthesized"}
    assert complete["links"][0]["relation"] == "state_handoff"
    assert {item["source"] for item in complete["findings"]} == {"rule", "agent_observation"}
    assert {item["stage"] for item in skeleton["flows"]} == {"skeleton"}
    assert skeleton["domains"][0]["support"] == "path_grouping"
    assert partial["analysis_status"] == "partial"
    assert flow(partial, "flow_submit_report")["accounting"]["unaccounted"] == 1
    assert step(partial, "step_notify_unknown")["resolution"] == "unknown"


def test_map_schema_is_valid_and_versioned():
    for schema in map_schemas().values():
        Draft202012Validator.check_schema(schema)
    with pytest.raises(ValueError):
        map_schemas("9.9.9")


def test_step_claims_need_matching_evidence():
    rejects(
        "complete",
        lambda data: step(data, "step_choose_path").update(anchors=[]),
        "resolved step must be anchored",
    )
    rejects(
        "complete",
        lambda data: step(data, "step_choose_path").update(evidence_ids=[]),
        "needs code evidence",
    )
    rejects(
        "complete",
        lambda data: step(data, "step_choose_path").update(resolution="candidate"),
        "requires a reason",
    )
    rejects(
        "partial",
        lambda data: step(data, "step_notify_unknown").pop("reason"),
        "requires a reason",
    )


def test_static_fact_support_needs_analyzer_anchors():
    def unanchored_static_step(data):
        step(data, "step_choose_path").update(
            support="static_fact", resolution="candidate", reason="no facts", anchors=[]
        )

    rejects("complete", unanchored_static_step, "static_fact support requires")


def test_branch_edges_are_tied_to_their_decision():
    rejects(
        "complete",
        lambda data: edge(data, "step_choose_path", "step_model_review").pop("condition"),
        "branch edge requires its condition",
    )
    rejects(
        "complete",
        lambda data: edge(data, "step_model_review", "step_mark_pending").update(
            relation="branch",
            condition={"label": "x", "anchor": step(data, "step_model_review")["anchors"][0]},
        ),
        "must leave a decision step",
    )
    rejects(
        "complete",
        lambda data: edge(data, "step_choose_path", "step_model_review")["condition"].update(
            anchor=OTHER_ANCHOR
        ),
        "anchored in its decision step",
    )


def test_edges_stay_inside_their_flow():
    rejects(
        "complete",
        lambda data: edge(data, "step_mark_pending", "step_return_pending").update(
            target="step_check_pending"
        ),
        "two steps of its own flow",
    )
    rejects(
        "complete",
        lambda data: edge(data, "step_mark_pending", "step_return_pending").update(
            target="step_mark_pending"
        ),
        "only a loop edge",
    )


def test_links_need_evidence_on_both_ends_and_two_flows():
    rejects(
        "complete",
        lambda data: data["links"][0].update(target_evidence_ids=[]),
        "target_evidence_ids",
    )
    rejects(
        "complete",
        lambda data: data["links"][0]["target"].update(
            flow_id="flow_submit_report", step_id="step_choose_path"
        ),
        "two different flows",
    )
    rejects(
        "complete",
        lambda data: data["links"][0]["target"].update(step_id="step_choose_path"),
        "step outside its flow",
    )
    rejects(
        "complete",
        lambda data: data["links"][0].update(support="static_fact", anchors=[OTHER_ANCHOR]),
        "only call and async_task links",
    )
    rejects(
        "complete",
        lambda data: data["links"][0].pop("reason"),
        "candidate link requires a reason",
    )


def test_evidence_must_exist_and_belong_to_the_map_side():
    rejects(
        "complete",
        lambda data: step(data, "step_choose_path").update(evidence_ids=["ev_missing"]),
        "unknown evidence_id",
    )
    rejects("complete", lambda data: data.update(side="base"), "its own side")
    rejects(
        "complete",
        lambda data: data.update(snapshot_id="sha256:" + "1" * 64),
        "snapshot_id does not match",
    )


def test_accounting_keeps_omissions_visible():
    rejects(
        "complete",
        lambda data: flow(data, "flow_submit_report")["accounting"].update(covered=6),
        "must add up to accountable",
    )
    rejects(
        "complete",
        lambda data: flow(data, "flow_submit_report").update(omitted=[]),
        "do not match the accounting count",
    )

    def omit_a_used_anchor(data):
        target = flow(data, "flow_submit_report")
        target["omitted"][0]["anchor"] = step(data, "step_choose_path")["anchors"][0]

    rejects("complete", omit_a_used_anchor, "both used by the map and left out")


def test_complete_requires_everything_accounted_for():
    def leave_a_fact_unaccounted(data):
        target = flow(data, "flow_submit_report")
        target["unaccounted"] = [target["omitted"].pop()["anchor"]]
        target["accounting"].update(omitted=0, unaccounted=1)

    rejects("complete", leave_a_fact_unaccounted, "no unaccounted or truncated facts")
    rejects(
        "complete",
        lambda data: flow(data, "flow_submit_report")["accounting"].update(truncated=True),
        "no unaccounted or truncated facts",
    )
    rejects(
        "complete",
        lambda data: data["coverage"].update(tasks_validated=2, tasks_pending=1),
        "no pending or failed tasks",
    )
    rejects("partial", lambda data: data.update(analysis_status="complete"), "complete map")
    rejects(
        "complete",
        lambda data: data.update(
            limitations=[{"code": "budget", "message": "cut", "affects_completeness": True}]
        ),
        "limitation that affects completeness",
    )


def test_skeleton_flows_are_purely_static():
    rejects(
        "skeleton",
        lambda data: step(data, "step_choose_path").update(support="agent_synthesis"),
        "only static steps",
    )
    rejects(
        "skeleton",
        lambda data: flow(data, "flow_submit_report").update(support="agent_synthesis"),
        "skeleton flow is static",
    )
    rejects(
        "complete",
        lambda data: flow(data, "flow_submit_report").update(support="static_fact"),
        "synthesized flow is agent synthesis",
    )


def test_findings_are_sourced_and_placed():
    def finding(data, source):
        return next(item for item in data["findings"] if item["source"] == source)

    rejects(
        "complete",
        lambda data: finding(data, "agent_observation").update(severity="high"),
        "cannot be rated high",
    )
    rejects(
        "complete",
        lambda data: finding(data, "agent_observation").update(rule="made_up_rule"),
        "does not claim a rule",
    )
    rejects(
        "complete",
        lambda data: finding(data, "rule").update(anchors=[]),
        "names its rule and its fact anchors",
    )
    rejects(
        "complete",
        lambda data: step(data, "step_model_review").update(finding_ids=[]),
        "placed on a step or flow",
    )
    rejects(
        "complete",
        lambda data: step(data, "step_choose_path").update(finding_ids=["find_missing"]),
        "unknown finding",
    )
    rejects(
        "complete",
        lambda data: data.update(unassigned_finding_ids=["find_loop_no_count_bound"]),
        "both placed on the map and unassigned",
    )


def test_identities_and_grouping_are_unambiguous():
    def duplicate_entry_symbol(data):
        approve = flow(data, "flow_approve_report")
        approve["entries"][0]["symbol_id"] = flow(data, "flow_submit_report")["entries"][0][
            "symbol_id"
        ]

    rejects("complete", duplicate_entry_symbol, "entry symbols across flows")
    rejects(
        "complete",
        lambda data: data["domains"].append(
            {
                "domain_id": "domain_other",
                "name": "其他",
                "support": "agent_synthesis",
                "flow_ids": ["flow_submit_report"],
            }
        ),
        "domain of a flow",
    )
    rejects(
        "complete",
        lambda data: data["domains"][0].update(flow_ids=["flow_missing"]),
        "unknown flow",
    )
    rejects(
        "complete",
        lambda data: flow(data, "flow_approve_report")["steps"].append(
            copy.deepcopy(step(data, "step_choose_path"))
        ),
        "step_id values must be unique",
    )
    rejects(
        "complete",
        lambda data: data["coverage"].update(entries_skipped=1),
        "must add up to the total",
    )


def test_fingerprint_ignores_position_and_separates_distinct_facts():
    base = dict(symbol="src/app.py#submit", kind="condition", text="amount >= THRESHOLD")
    first = fact_fingerprint(**base)
    assert first == fact_fingerprint(**{**base, "text": "  amount >= THRESHOLD\n"})
    assert first.startswith("fp_") and len(first) == 27
    assert len({first, fact_fingerprint(**base, ordinal=1)}) == 2
    assert first != fact_fingerprint(**{**base, "text": "amount > THRESHOLD"})
    assert first != fact_fingerprint(**{**base, "kind": "call"})
    assert first != fact_fingerprint(**{**base, "symbol": "src/app.py#approve"})
    with pytest.raises(ValueError):
        fact_fingerprint(**base, ordinal=-1)
    with pytest.raises(ValueError):
        fact_fingerprint(**{**base, "symbol": ""})

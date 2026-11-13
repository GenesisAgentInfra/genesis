"""A problem between two items of a submission is reported at the item, with its value."""

import pytest
from genesis_ci.business_map.workspace import pydantic_problems
from genesis_contracts.map_tasks import ChangeSubmission, FlowSubmission, MapPlan
from pydantic import ValidationError

CITE = [{"evidence_id": "ev_1"}]


def step(key):
    return {"key": key, "name": key, "kind": "action", "evidence": CITE}


def problems(model, raw):
    with pytest.raises(ValidationError) as refused:
        model.model_validate(raw)
    return [
        (item["path"], item["code"], item["message"]) for item in pydantic_problems(refused.value)
    ]


def test_an_edge_to_a_step_that_does_not_exist_names_the_edge_and_the_key():
    flow = {
        "name": "下单",
        "steps": [step("recv"), step("save")],
        "edges": [
            {"source": "recv", "target": "save", "relation": "sequence"},
            {"source": "save", "target": "notify", "relation": "sequence"},
            {"source": "retry", "target": "recv", "relation": "sequence"},
        ],
    }
    assert problems(FlowSubmission, flow) == [
        (
            "edges[1].target",
            "invalid_reference",
            "No step in this submission has the key 'notify'.",
        ),
        ("edges[2].source", "invalid_reference", "No step in this submission has the key 'retry'."),
    ]


def test_an_observation_on_a_step_that_does_not_exist_is_located_too():
    flow = {
        "name": "下单",
        "steps": [step("recv")],
        "observations": [{"statement": "没有重试上限。", "step": "save", "evidence": CITE}],
    }
    assert problems(FlowSubmission, flow) == [
        (
            "observations[0].step",
            "invalid_reference",
            "No step in this submission has the key 'save'.",
        )
    ]


def test_a_repeated_key_is_reported_where_it_repeats_and_says_what_it_repeats():
    flow = {
        "name": "下单",
        "steps": [step("recv"), step("save"), step("recv")],
        "omitted": [
            {"anchor": "fp_" + "1" * 24, "reason": "logging"},
            {"anchor": "fp_" + "1" * 24, "reason": "logging"},
        ],
    }
    assert problems(FlowSubmission, flow) == [
        ("steps[2].key", "invalid_duplicate", "'recv' is already used at steps[0].key."),
        (
            "omitted[1].anchor",
            "invalid_duplicate",
            f"'fp_{'1' * 24}' is already used at omitted[0].anchor.",
        ),
    ]


def test_a_plan_says_which_flow_and_which_entry_do_not_fit():
    plan = {
        "domains": [{"key": "orders", "name": "订单"}],
        "flows": [
            {"key": "create", "name": "下单", "domain": "orders", "entry_ids": ["entry_a"]},
            {
                "key": "refund",
                "name": "退款",
                "domain": "billing",
                "entry_ids": ["entry_b", "entry_a"],
            },
        ],
        "skipped": [{"entry_id": "entry_b", "reason": "duplicate"}],
    }
    assert problems(MapPlan, plan) == [
        ("flows[1].domain", "invalid_reference", "No domain in this plan has the key 'billing'."),
        (
            "flows[1].entry_ids[1]",
            "invalid_duplicate",
            "'entry_a' is already used at flows[0].entry_ids[0].",
        ),
        (
            "skipped[0].entry_id",
            "invalid_duplicate",
            "'entry_b' is already used at flows[1].entry_ids[0].",
        ),
    ]


def test_a_change_assessed_twice_is_reported_at_the_second_assessment():
    answer = {
        "changes": [
            {"change_id": "chg_1", "summary": "阈值改了。"},
            {"change_id": "chg_2", "summary": "多了一次重试。"},
            {"change_id": "chg_1", "summary": "阈值改为包含 100。"},
        ]
    }
    assert problems(ChangeSubmission, answer) == [
        (
            "changes[2].change_id",
            "invalid_duplicate",
            "'chg_1' is already used at changes[0].change_id.",
        )
    ]


def test_a_test_named_twice_is_reported_inside_its_assessment():
    answer = {
        "changes": [
            {"change_id": "chg_1", "summary": "阈值改了。"},
            {
                "change_id": "chg_2",
                "summary": "多了一次重试。",
                "verdict": "covered",
                "note": "两个测试都断言了重试次数。",
                "test_ids": [
                    "head::tests/test_retry.py#test_twice",
                    "head::tests/test_retry.py#test_twice",
                ],
            },
        ]
    }
    assert [item[:2] for item in problems(ChangeSubmission, answer)] == [
        ("changes[1].test_ids[1]", "invalid_duplicate")
    ]


def test_a_problem_inside_one_item_keeps_the_place_pydantic_gives_it():
    flow = {
        "name": "下单",
        "steps": [step("recv"), step("save")],
        "edges": [{"source": "recv", "target": "save", "relation": "branch"}],
    }
    assert [item[:2] for item in problems(FlowSubmission, flow)] == [
        ("edges[0]", "invalid_value_error")
    ]

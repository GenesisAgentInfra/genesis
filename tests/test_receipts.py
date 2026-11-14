"""A refusal names the item it is about, not only its position in the submission."""

from genesis_ci.business_map.changes import CHANGE_TASK
from test_called_functions import API, quote_flow, quoting  # noqa: F401
from test_change_analysis import change  # noqa: F401
from test_drawing_cases import batch_flow, batching, fact  # noqa: F401
from test_map_loop import src


def named(result):
    assert result["status"] == "rejected"
    return [(item["path"], item["code"], item.get("item")) for item in result["errors"]]


def test_a_refused_step_edge_or_omission_is_named_by_its_own_key(quoting):  # noqa: F811
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    # The `def` line: nothing on it is a fact.
    flow["steps"].append(
        {
            "key": "total",
            "name": "合计",
            "kind": "action",
            "evidence": [src(API, 13, "def create_quote")],
        }
    )
    flow["edges"].append({"source": "save", "target": "recv", "relation": "sequence"})
    flow["omitted"] = [{"anchor": "fp_" + "0" * 24, "reason": "logging"}]
    flow["observations"] = [{"statement": "没有上限。", "step": "save", "evidence": []}]
    assert named(workspace.submit(task, flow)) == [
        ("observations[0].evidence", "invalid_too_short", "observation on save")
    ]
    flow["observations"] = []
    assert named(workspace.submit(task, flow)) == [
        ("steps[6]", "step_not_anchored", "step total"),
        ("edges[6]", "edge_not_supported", "edge save -> recv"),
        ("omitted[0].anchor", "unknown_anchor", "omitted fp_" + "0" * 24),
    ]


def test_a_refused_assessment_names_the_change(change):  # noqa: F811
    result = change.submit(
        CHANGE_TASK,
        {"changes": [{"change_id": "chg_missing", "summary": "x"}]},
    )
    assert named(result) == [("changes[0].change_id", "unknown_change", "change chg_missing")]


def unit(workspace, task, starts):
    listed = workspace.context(task)["accountable"]
    return next(item for item in listed if item["text"].startswith(starts))


def refused_omission(workspace, task, flow):
    result = workspace.submit(task, flow)
    assert [(item["path"], item["code"]) for item in result["errors"]] == [
        ("omitted[0].anchor", "omitted_but_used")
    ], result["errors"]
    return result["errors"][0]


def test_leaving_out_the_call_of_an_expanded_function_names_the_function_and_its_steps(quoting):  # noqa: F811
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    call = unit(workspace, task, "price_order")["fingerprint"]
    # Written out as an anchor and left out as well, with steps inside the function.
    flow["steps"][1]["anchors"] = [call]
    flow["omitted"] = [{"anchor": call, "reason": "merged_into_step"}]
    error = refused_omission(workspace, task, flow)
    # A fingerprint says nothing by itself: the receipt says which code it is.
    assert error["item"] == f"omitted {call} (`price_order(order)` on line 15 of quote/api.py)"
    message = error["message"]
    assert "quote/pricing.py#price_order is expanded" in message
    assert "steps 'coupon', 'discount' are anchored inside it" in message
    assert "drop this entry" in message
    # The other reason a unit cannot be left out is not mentioned.
    assert "`anchors`" not in message


def test_leaving_out_what_a_step_is_anchored_on_names_that_step(quoting):  # noqa: F811
    workspace, task = quoting
    flow = quote_flow(workspace, task)
    workspace.submit(task, flow)
    condition = unit(workspace, task, "order.get")["fingerprint"]
    flow["steps"][2]["anchors"] = [condition]
    flow["omitted"] = [{"anchor": condition, "reason": "input_validation"}]
    error = refused_omission(workspace, task, flow)
    assert error["item"].endswith('(`order.get("coupon")` on line 6 of quote/pricing.py)')
    assert error["message"].startswith("It is in the `anchors` of step 'coupon'.")
    assert "expanded" not in error["message"]


def test_leaving_out_a_function_one_step_stands_for_names_the_step_and_the_function(batching):  # noqa: F811
    workspace, task = batching
    flow = batch_flow(workspace, task)
    # Nothing inside the function any more: a step on its second call stands for it.
    gone = {"drop", "names"}
    flow["steps"] = [step for step in flow["steps"] if step["key"] not in gone]
    flow["edges"] = [
        edge for edge in flow["edges"] if not gone & {edge["source"], edge["target"]}
    ] + [
        {"source": "recv", "target": "tags", "relation": "sequence"},
        {"source": "tags", "target": "load", "relation": "sequence"},
    ]
    second = fact(workspace, "batch/api.py#start_batch", "call", 'clean(batch["tags"])')
    first = fact(workspace, "batch/api.py#start_batch", "call", 'clean(batch["names"])')
    next(step for step in flow["steps"] if step["key"] == "tags")["anchors"] = [second]
    flow["omitted"] = [{"anchor": second, "reason": "out_of_business_scope"}]
    message = refused_omission(workspace, task, flow)["message"]
    assert message.startswith(
        "This call is in the `anchors` of step 'tags', and a step anchored on a call stands "
        "for batch/work.py#clean."
    )
    # Leaving out another call of the same function contradicts that step just as much.
    flow["omitted"] = [{"anchor": first, "reason": "out_of_business_scope"}]
    message = refused_omission(workspace, task, flow)["message"]
    assert message.startswith(
        "Step 'tags' is anchored on another call to batch/work.py#clean, on line 14, and one "
        "choice covers every call to the same function."
    )


def test_a_step_left_with_nothing_but_what_the_submission_omits_is_told_so(batching):  # noqa: F811
    workspace, task = batching
    flow = batch_flow(workspace, task)
    # Both calls of the function are cited by their lines, nothing is anchored inside
    # it, and the function is left out: the two steps have nothing left to stand on.
    flow["steps"] = [step for step in flow["steps"] if step["key"] != "drop"]
    flow["edges"] = [edge for edge in flow["edges"] if "drop" not in edge.values()]
    first = fact(workspace, "batch/api.py#start_batch", "call", 'clean(batch["names"])')
    flow["omitted"] = [{"anchor": first, "reason": "out_of_business_scope"}]
    result = workspace.submit(task, flow)
    assert named(result) == [
        ("steps[1]", "step_not_anchored", "step names"),
        ("steps[2]", "step_not_anchored", "step tags"),
    ]
    message = result["errors"][0]["message"]
    # Not "no fact starts in the cited lines": one does, and the submission set it aside.
    assert message.startswith(
        'The cited lines hold nothing but `clean(batch["names"])`, which this submission '
        "lists in `omitted`."
    )

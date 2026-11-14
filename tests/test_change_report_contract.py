"""Change report and evidence bundle contracts: the sample holds, each rule rejects its violation."""

import copy
import json
from pathlib import Path

import pytest
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import (
    ChangeReport,
    CoverageAssessment,
    validate_change_report_against_map,
)
from genesis_contracts.evidence_bundle import EvidenceBundle, validate_evidence_bundle
from genesis_contracts.schemas import map_schemas
from jsonschema import Draft202012Validator
from pydantic import ValidationError

SAMPLE = Path(__file__).parents[1] / "fixtures" / "business-map" / "change"


def load(name):
    return json.loads((SAMPLE / f"{name}.json").read_text(encoding="utf-8"))


def change(data, change_id):
    return next(item for item in data["changes"] if item["change_id"] == change_id)


def rejects(mutate, message):
    data = copy.deepcopy(load("change-report"))
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        ChangeReport.model_validate(data)


def assessment(**fields):
    case = {"test_id": "head::tests/test_a.py#test_a", "evidence_ids": ["ev_case"]}
    base = {"execution_data": "not_collected", "items": [{**case, "tags": ["related"]}]}
    return CoverageAssessment.model_validate({**base, **fields})


def test_sample_matches_the_models_and_the_exported_schemas():
    schemas = map_schemas()
    for name, model in (
        ("business-map", BusinessMap),
        ("change-report", ChangeReport),
        ("evidence-bundle", EvidenceBundle),
    ):
        data = load(name)
        parsed = model.model_validate(data)
        assert parsed.model_dump(mode="json", exclude_none=True) == data
        Draft202012Validator.check_schema(schemas[f"{name}.schema.json"])
        Draft202012Validator(schemas[f"{name}.schema.json"]).validate(data)


def test_sample_is_consistent_across_its_documents():
    head = BusinessMap.model_validate(load("business-map"))
    report = ChangeReport.model_validate(load("change-report"))
    bundle = EvidenceBundle.model_validate(load("evidence-bundle"))
    validate_change_report_against_map(report, head)
    cited = {ref.evidence_id: ref for ref in (*head.evidence, *report.evidence)}
    validate_evidence_bundle(bundle, tuple(cited.values()))
    assert {ref.side.value for ref in report.evidence} == {"base", "head"}


def test_sample_shows_a_boundary_change_that_tests_only_reach():
    data = load("change-report")
    threshold = change(data, "chg_threshold_condition")
    assert (threshold["before"]["text"], threshold["after"]["text"]) == (
        "amount >= THRESHOLD",
        "amount > THRESHOLD",
    )
    assert threshold["before"]["anchor"] != threshold["after"]["anchor"]
    assert threshold["tests"]["verdict"] == "reached_only"
    assert threshold["tests"]["execution_data"] == "not_collected"
    statuses = {item["finding"]["finding_id"]: item["status"] for item in data["finding_changes"]}
    assert statuses["find_loop_no_count_bound"] == "introduced"
    assert "persisting" in statuses.values()


def test_change_sides_follow_the_change_kind():
    rejects(
        lambda data: change(data, "chg_threshold_condition").pop("before"),
        "modified fact has both sides",
    )
    rejects(
        lambda data: change(data, "chg_review_loop").update(
            before=copy.deepcopy(change(data, "chg_threshold_condition")["before"])
        ),
        "exists only on the head side",
    )
    rejects(
        lambda data: change(data, "chg_review_loop").update(kind="loop_removed"),
        "exists only on the base side",
    )
    rejects(
        lambda data: change(data, "chg_threshold_condition")["before"].update(side="head"),
        "before side of a change is the base",
    )


def test_evidence_is_cited_on_the_side_it_belongs_to():
    def cite_head_evidence_as_before(data):
        item = change(data, "chg_threshold_condition")
        item["before"]["evidence_ids"] = item["after"]["evidence_ids"]

    rejects(cite_head_evidence_as_before, "wrong side of the change")
    rejects(
        lambda data: change(data, "chg_review_loop")["after"].update(evidence_ids=["ev_missing"]),
        "unknown evidence_id",
    )
    rejects(
        lambda data: data["finding_changes"][0].update(status="resolved"),
        "wrong side of the change",
    )


def test_projection_names_exactly_the_target_its_status_needs():
    rejects(
        lambda data: change(data, "chg_review_loop")["projection"].pop("step_id"),
        "names a flow and one of its steps",
    )
    rejects(
        lambda data: change(data, "chg_review_loop")["projection"].update(status="unassigned"),
        "has no map target",
    )
    rejects(
        lambda data: change(data, "chg_review_loop").update(projection={"status": "unassigned"}),
        "states why it has no map target",
    )
    rejects(
        lambda data: change(data, "chg_review_loop")["projection"].update(status="removed_step"),
        "names a flow and the removed step",
    )


def test_complete_report_explains_and_assesses_every_placed_change():
    rejects(
        lambda data: change(data, "chg_review_loop").pop("explanation"),
        "explains every change on the map or within reach of a flow",
    )

    def reached_without_a_step(data):
        # Off the map, yet a flow gets to it: it is owed an explanation all the same.
        item = change(data, "chg_review_loop")
        item.update(projection={"status": "unassigned", "reason": "No step covers this code."})
        item.pop("explanation")
        data["possibly_affected"] = [
            {"flow_id": "flow_approve_report", "change_ids": ["chg_review_loop"], "reason": "x"}
        ]

    rejects(reached_without_a_step, "explains every change on the map or within reach of a flow")
    rejects(
        lambda data: change(data, "chg_review_loop").pop("tests"),
        "assesses coverage of every placed change",
    )
    rejects(
        lambda data: data.update(
            limitations=[{"code": "budget", "message": "cut", "affects_completeness": True}]
        ),
        "limitation that affects completeness",
    )
    data = copy.deepcopy(load("change-report"))
    change(data, "chg_review_loop").pop("tests")
    data["analysis_status"] = "partial"
    ChangeReport.model_validate(data)


def test_report_references_stay_inside_the_report():
    rejects(
        lambda data: change(data, "chg_review_loop").update(finding_ids=["find_missing"]),
        "finding the report does not list",
    )
    rejects(
        lambda data: data.update(
            possibly_affected=[
                {"flow_id": "flow_approve_report", "change_ids": ["chg_missing"], "reason": "x"}
            ]
        ),
        "unknown change",
    )
    rejects(
        lambda data: data["changes"].append(copy.deepcopy(data["changes"][0])),
        "change_id values must be unique",
    )
    rejects(
        lambda data: data["unanalyzed_changes"][0].update(path="../outside.md"),
        "invalid segment",
    )
    rejects(
        lambda data: change(data, "chg_review_loop").update(kind="test_added"),
        "no coverage assessment of itself",
    )


def test_coverage_verdict_needs_matching_evidence():
    both = {"tags": ["related", "assertion_found"]}
    case = {"test_id": "head::tests/test_a.py#test_a", "evidence_ids": ["ev_case"]}
    covered = assessment(
        verdict="covered",
        basis=["static_fact", "agent_assessment"],
        items=[{**case, **both}],
    )
    assert covered.verdict == "covered"
    executed = assessment(
        verdict="covered",
        basis=["imported_coverage"],
        execution_data="imported",
        items=[{**case, "tags": ["assertion_found"], "executed": True}],
    )
    assert executed.items[0].executed is True
    assert assessment(verdict="not_reached", basis=["static_fact"], items=[]).items == ()
    with pytest.raises(ValidationError, match="reaches the change and asserts"):
        assessment(verdict="covered", basis=["agent_assessment"])
    with pytest.raises(ValidationError, match="input takes the changed path"):
        assessment(verdict="covered", basis=["static_fact"], items=[{**case, **both}])
    with pytest.raises(ValidationError, match="states what is missing"):
        assessment(verdict="reached_only", basis=["static_fact"])
    with pytest.raises(ValidationError, match="needs a test that reaches"):
        assessment(verdict="reached_only", basis=["static_fact"], note="x", items=[])
    with pytest.raises(ValidationError, match="cannot list a test that reaches"):
        assessment(verdict="not_reached", basis=["static_fact"])
    with pytest.raises(ValidationError, match="static test index or an assessment"):
        assessment(verdict="not_reached", items=[])
    # An agent may conclude it from reading the tests; the basis then says so.
    assert assessment(verdict="not_reached", basis=["agent_assessment"], items=[]).items == ()
    with pytest.raises(ValidationError, match="what could not be analyzed"):
        assessment(verdict="unknown", items=[])


def test_execution_status_needs_imported_execution_data():
    case = {"test_id": "head::tests/test_a.py#test_a", "evidence_ids": ["ev_case"]}
    with pytest.raises(ValidationError, match="needs imported execution data"):
        assessment(
            verdict="reached_only",
            basis=["static_fact"],
            note="x",
            items=[{**case, "tags": ["related"], "executed": True}],
        )
    with pytest.raises(ValidationError, match="imported_coverage basis needs imported"):
        assessment(verdict="reached_only", basis=["imported_coverage"], note="x")
    with pytest.raises(ValidationError, match="a test that executed the change"):
        assessment(
            verdict="reached_only",
            basis=["imported_coverage"],
            execution_data="imported",
            note="x",
        )
    with pytest.raises(ValidationError, match="statically related or was executed"):
        assessment(verdict="unknown", note="x", items=[case])


def test_report_targets_must_exist_on_the_head_map():
    head = BusinessMap.model_validate(load("business-map"))

    def invalid(mutate, message, target=head):
        data = copy.deepcopy(load("change-report"))
        mutate(data)
        with pytest.raises(ValueError, match=message):
            validate_change_report_against_map(ChangeReport.model_validate(data), target)

    invalid(
        lambda data: change(data, "chg_review_loop")["projection"].update(step_id="step_gone"),
        "step outside its flow",
    )
    invalid(
        lambda data: change(data, "chg_review_loop")["projection"].update(flow_id="flow_gone"),
        "unknown flow",
    )
    invalid(
        lambda data: change(data, "chg_review_loop").update(
            projection={
                "status": "removed_step",
                "flow_id": "flow_submit_report",
                "removed_step": {"step_id": "step_model_review", "name": "模型审核"},
            }
        ),
        "still exists on the head map",
    )
    invalid(
        lambda data: data["finding_changes"][1]["finding"].update(finding_id="find_other"),
        "missing from the head map",
    )
    other = load("business-map")
    other["findings"] = [f for f in other["findings"] if f["source"] == "rule"]
    for flow in other["flows"]:
        for step in flow["steps"]:
            step["finding_ids"] = [f for f in step["finding_ids"] if f.startswith("find_loop")]
    invalid(lambda data: None, "missing from the head map", BusinessMap.model_validate(other))
    base_side = Path(__file__).parents[1] / "fixtures" / "business-map" / "expense-complete.json"
    unrelated = BusinessMap.model_validate(json.loads(base_side.read_text(encoding="utf-8")))
    invalid(lambda data: None, "different snapshots", unrelated)


def test_evidence_bundle_matches_its_catalog_and_hides_source_when_shared():
    report = ChangeReport.model_validate(load("change-report"))
    head = BusinessMap.model_validate(load("business-map"))
    cited = tuple({ref.evidence_id: ref for ref in (*head.evidence, *report.evidence)}.values())
    data = load("evidence-bundle")
    shared = EvidenceBundle(snapshot_id=data["snapshot_id"], share_mode=True)
    validate_evidence_bundle(shared, cited)
    with pytest.raises(ValidationError, match="carries no source excerpts"):
        EvidenceBundle.model_validate({**data, "share_mode": True})
    with pytest.raises(ValidationError, match="at most one excerpt"):
        EvidenceBundle.model_validate(
            {**data, "excerpts": [*data["excerpts"], data["excerpts"][0]]}
        )
    tampered = copy.deepcopy(data)
    tampered["excerpts"][0]["text"] += " "
    with pytest.raises(ValueError, match="does not match its evidence digest"):
        validate_evidence_bundle(EvidenceBundle.model_validate(tampered), cited)
    missing = {**data, "excerpts": data["excerpts"][1:]}
    with pytest.raises(ValueError, match="an excerpt for every cited"):
        validate_evidence_bundle(EvidenceBundle.model_validate(missing), cited)
    with pytest.raises(ValueError, match="belongs to no cited evidence"):
        validate_evidence_bundle(EvidenceBundle.model_validate(data), cited[1:])
    with pytest.raises(ValueError, match="different snapshots"):
        validate_evidence_bundle(
            EvidenceBundle(snapshot_id="sha256:" + "1" * 64, share_mode=True), cited
        )


def test_further_projections_name_places_and_are_checked_against_the_map():
    head = BusinessMap.model_validate(load("business-map"))
    other = {"status": "projected", "flow_id": "flow_submit_report", "step_id": "step_choose_path"}
    data = copy.deepcopy(load("change-report"))
    change(data, "chg_review_loop")["other_projections"] = [other]
    validate_change_report_against_map(ChangeReport.model_validate(data), head)
    rejects(
        lambda data: change(data, "chg_review_loop").update(
            other_projections=[{"status": "unassigned", "reason": "nowhere"}]
        ),
        "further projection names a place",
    )
    data = copy.deepcopy(load("change-report"))
    change(data, "chg_review_loop")["other_projections"] = [{**other, "step_id": "step_gone"}]
    with pytest.raises(ValueError, match="step outside its flow"):
        validate_change_report_against_map(ChangeReport.model_validate(data), head)


def test_source_changes_follow_the_same_side_rules_as_fact_changes():
    rejects(
        lambda data: change(data, "chg_review_loop").update(kind="source_removed"),
        "removed fact exists only on the base side",
    )
    data = copy.deepcopy(load("change-report"))
    change(data, "chg_review_loop").update(kind="source_added", detail="A retry loop.")
    assert ChangeReport.model_validate(data).changes[1].detail == "A retry loop."


def test_a_test_named_by_an_agent_counts_only_as_the_agents_assessment():
    named = [
        {
            "test_id": "head::tests/test_a.py#test_a",
            "evidence_ids": ["ev_case"],
            "tags": ["agent_identified", "assertion_found"],
        }
    ]
    covered = assessment(verdict="covered", basis=["agent_assessment"], items=named)
    assert covered.items[0].tags == ("agent_identified", "assertion_found")
    with pytest.raises(ValidationError, match="named by an agent needs the agent_assessment"):
        assessment(verdict="reached_only", basis=["static_fact"], note="x", items=named)
    with pytest.raises(ValidationError, match="cannot list a test that reaches"):
        assessment(verdict="not_reached", basis=["static_fact", "agent_assessment"], items=named)


def test_change_submissions_explain_every_verdict():
    from genesis_contracts.map_tasks import ChangeSubmission

    entry = {"change_id": "chg_a", "summary": "阈值改为包含边界。"}
    accepted = ChangeSubmission.model_validate({"changes": [entry]})
    assert accepted.changes[0].verdict is None
    for bad, message in (
        ({**entry, "verdict": "covered"}, "needs a note"),
        ({**entry, "test_ids": ["head::t#a"]}, "belong to a coverage verdict"),
        ({**entry, "verdict": "passed", "note": "x"}, "Input should be"),
    ):
        with pytest.raises(ValidationError, match=message):
            ChangeSubmission.model_validate({"changes": [bad]})
    with pytest.raises(ValidationError, match="'chg_a' is already used at changes") as twice:
        ChangeSubmission.model_validate({"changes": [entry, entry]})
    assert twice.value.errors()[0]["loc"] == ("changes", 1, "change_id")
    with pytest.raises(ValidationError):
        ChangeSubmission.model_validate({"changes": []})
    assert "change-submission.schema.json" in map_schemas()

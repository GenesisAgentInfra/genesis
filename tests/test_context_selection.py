"""Context selection must make progress past an oversized earlier candidate."""

import hashlib
import json

import pytest
from genesis_ci.context import ContextBudgetExceeded, ContextOptions, build_context
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.models import ReviewDirectives, ReviewDocument, project_analysis_request
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_request_against_local
from genesis_tokenizer import count_fragments
from test_git_snapshot import git


def changed_repository(source_repo):
    def source(value):
        return (
            "def oversized():\n"
            + "    text = 'ordinary explanatory text'\n" * 220
            + f"    return {value}\n\ndef small():\n    return {value}\n"
        )

    (source_repo / "app.py").write_text(source(1))
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_text(source(2))
    return analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))


def test_oversized_earlier_body_does_not_discard_fitting_changed_functions(source_repo):
    result = changed_repository(source_repo)
    options = ContextOptions(input_token_budget=12000, max_excerpt_chars=2000)
    request = build_context(result.local, result.reader, request_id="skip-large", options=options)
    validate_request_against_local(result.local, request)
    assert (
        count_fragments(
            [
                json.dumps(
                    project_analysis_request(request), ensure_ascii=False, separators=(",", ":")
                )
            ]
        )
        <= options.payload_token_budget
    )
    assert request.truncated
    assert {f.side.value for f in request.facts.functions if f.symbol_id == "app.py#small"} == {
        "base",
        "head",
    }
    assert request.change_set.files


def test_excerpt_cap_counts_accepted_items_and_keeps_head_then_base(source_repo):
    result = changed_repository(source_repo)
    options = ContextOptions(input_token_budget=12000, max_excerpts=2, max_excerpt_chars=2000)
    request = build_context(result.local, result.reader, request_id="pair", options=options)
    validate_request_against_local(result.local, request)
    assert len(request.excerpts) == 2
    assert {ref.side.value for ref in request.evidence} == {"base", "head"}
    assert {f.symbol_id for f in request.facts.functions} == {"app.py#small"}


def test_skipping_does_not_reintroduce_excluded_source(source_repo):
    result = changed_repository(source_repo)
    request = build_context(
        result.local,
        result.reader,
        request_id="excluded",
        options=ContextOptions(input_token_budget=12000, exclude_paths=("app.py",)),
    )
    validate_request_against_local(result.local, request)
    assert not request.excerpts
    assert request.truncated
    assert any("excluded" in reason for reason in request.missing_context)


def test_diff_seeds_and_directives_share_the_same_byte_budget(source_repo):
    result = changed_repository(source_repo)
    text = "Review instructions. " * 800
    schema_text = json.dumps({"description": "x" * 12000})
    directives = ReviewDirectives(
        documents=(
            ReviewDocument(
                role="instructions",
                path="review.md",
                text=text,
                sha256=hashlib.sha256(text.encode()).hexdigest(),
            ),
            ReviewDocument(
                role="schema",
                path="schemas/report.json",
                text=schema_text,
                sha256=hashlib.sha256(schema_text.encode()).hexdigest(),
            ),
        )
    )
    request = build_context(
        result.local, result.reader, request_id="directives", review_directives=directives
    )
    validate_request_against_local(result.local, request)
    assert request.review_directives == directives
    assert len(request.model_dump_json().encode()) > 20000
    projected = json.dumps(
        project_analysis_request(request), ensure_ascii=False, separators=(",", ":")
    )
    assert count_fragments([projected]) <= 20000
    assert schema_text not in projected
    assert {ref.side.value for ref in request.evidence if ref.kind == "code"} == {"base", "head"}
    assert request.intents == ()
    with pytest.raises(ContextBudgetExceeded):
        build_context(
            result.local,
            result.reader,
            request_id="too-small",
            review_directives=directives,
            options=ContextOptions(input_token_budget=1000),
        )


def test_changed_function_and_current_associated_test_remain_prioritized(source_repo):
    (source_repo / "app.py").write_text("def submit():\n    return True\n")
    (source_repo / "tests").mkdir()
    (source_repo / "tests/test_app.py").write_text(
        "from app import submit\ndef test_submit():\n    assert submit() is not None\n"
    )
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_text(
        "def submit():\n" + "    print('detail')\n" * 15 + "    return True\n"
    )
    (source_repo / "tests/test_app.py").write_text(
        "from app import submit\ndef test_submit():\n    assert submit() is True\n"
    )
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    request = build_context(
        result.local,
        result.reader,
        request_id="current-test",
        options=ContextOptions(input_token_budget=16000),
    )
    validate_request_against_local(result.local, request)
    assert (
        count_fragments(
            [
                json.dumps(
                    project_analysis_request(request), ensure_ascii=False, separators=(",", ":")
                )
            ]
        )
        <= 8000
    )
    assert {f.side.value for f in request.facts.functions if f.symbol_id == "app.py#submit"} == {
        "base",
        "head",
    }
    catalog = {ref.evidence_id: ref for ref in request.evidence}
    assert any(
        all(catalog[ref].side == "head" for ref in test.evidence_ids)
        and "submit() is True" in " ".join(test.assertions)
        for test in request.test_definitions
    )


@pytest.mark.parametrize("input_budget", [9000, 40000])
def test_review_context_retains_changed_body_pair_and_direct_caller(source_repo, input_budget):
    """Review prose must not reduce a small edited function to isolated calls."""

    def source(operator):
        return (
            "def dispatch(amount, threshold):\n"
            "    decision = classify(amount, threshold)\n"
            "    return deliver(decision)\n\n"
            "def classify(amount, threshold):\n"
            f"    if amount {operator} threshold:\n"
            "        return 'review'\n"
            "    return 'approve'\n\n"
            "def deliver(decision):\n"
            "    return {'decision': decision}\n"
        )

    (source_repo / "workflow.py").write_text(source(">="))
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "workflow.py").write_text(source(">"))
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    review_text = "Read source carefully; report supported conclusions and uncertainty. " * 200
    reference_text = "Application review scope includes the supplied source files. " * 15
    directives = ReviewDirectives(
        documents=tuple(
            ReviewDocument(
                role=role, path=path, text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
            )
            for role, path, text in (
                ("instructions", "review.md", review_text),
                ("reference", "scope.md", reference_text),
            )
        )
    )
    request = build_context(
        result.local, result.reader, request_id="body-context", review_directives=directives
    )
    validate_request_against_local(result.local, request)
    functions = {(f.side.value, f.symbol_id) for f in request.facts.functions}
    assert {(side, "workflow.py#classify") for side in ("base", "head")} <= functions
    assert {(side, "workflow.py#dispatch") for side in ("base", "head")} <= functions
    selected_text = "\n".join(item.text for item in request.excerpts)
    assert "if amount >= threshold:" in selected_text
    assert "if amount > threshold:" in selected_text
    assert "decision = classify(amount, threshold)" in selected_text
    assert request.review_directives == directives


def test_changed_class_keeps_existing_methods_and_added_method(source_repo):
    before = (
        "class Client:\n"
        "    def execute(self, value):\n"
        "        return self.prepare(value)\n\n"
        "    def prepare(self, value):\n"
        "        return str(value)\n"
    )
    (source_repo / "client.py").write_text(before)
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "client.py").write_text(
        before + "\n    async def execute_async(self, value):\n        return self.prepare(value)\n"
    )
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    request = build_context(result.local, result.reader, request_id="class-context")
    validate_request_against_local(result.local, request)
    selected = {(f.side.value, f.symbol_id) for f in request.facts.functions}
    assert {
        (side, f"client.py#Client.{method}")
        for side in ("base", "head")
        for method in ("execute", "prepare")
    } <= selected
    assert ("head", "client.py#Client.execute_async") in selected
    assert all(
        reader == excerpt
        for excerpt in request.excerpts
        for reader in [result.reader.read_excerpt(excerpt.evidence_id)]
    )


def test_full_review_wire_cap_applies_even_when_schema_text_is_not_model_context(source_repo):
    result = changed_repository(source_repo)
    schema_text = "x" * 262144
    directives = ReviewDirectives(
        documents=tuple(
            ReviewDocument(
                role="schema",
                path=f"schemas/{index}.json",
                text=schema_text,
                sha256=hashlib.sha256(schema_text.encode()).hexdigest(),
            )
            for index in range(2)
        )
    )
    with pytest.raises(ContextBudgetExceeded):
        build_context(
            result.local, result.reader, request_id="wire-overflow", review_directives=directives
        )


def test_actual_method_change_precedes_unchanged_class_members(source_repo):
    def source(value):
        return (
            "class Workflow:\n"
            "    def __init__(self):\n        self.name = 'workflow'\n\n"
            f"    def execute(self):\n        return {value}\n"
        )

    (source_repo / "workflow.py").write_text(source(1))
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "workflow.py").write_text(source(2))
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    request = build_context(
        result.local,
        result.reader,
        request_id="changed-method",
        options=ContextOptions(max_excerpts=2),
    )
    selected = {(f.side.value, f.symbol_id) for f in request.facts.functions}
    assert {(side, "workflow.py#Workflow.execute") for side in ("base", "head")} <= selected


def test_preferred_base_body_still_admits_its_head_partner(source_repo):
    def source(operator):
        return f"def route(value):\n    if value {operator} 5:\n        return True\n    return False\n"

    (source_repo / "app.py").write_text(source(">="))
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_text(source(">"))
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    preferred = next(
        f.evidence_ids[0]
        for f in result.local.facts.functions
        if f.side == "base" and f.kind == "function"
    )
    request = build_context(
        result.local,
        result.reader,
        request_id="preferred-pair",
        options=ContextOptions(preferred_evidence_ids=(preferred,)),
    )
    assert {
        (f.side.value, f.symbol_id) for f in request.facts.functions if f.kind == "function"
    } == {("base", "app.py#route"), ("head", "app.py#route")}

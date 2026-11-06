import json
from pathlib import Path

import pytest
from genesis_ci.context import ContextBudgetExceeded, ContextOptions, build_context, preview_request
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_ci.snapshot import FrozenSnapshotReader
from genesis_contracts import LocalAnalysis
from genesis_contracts.models import SourceExcerpt, project_analysis_request
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_request_against_local
from genesis_tokenizer import count_fragments
from test_git_snapshot import git


def load_fixture(name="normal-five-sections"):
    root = Path(__file__).resolve().parents[1] / "fixtures" / name
    payload = json.loads((root / "semantic.json").read_text())
    local = LocalAnalysis.model_validate(payload["local_analysis"])
    reader = FrozenSnapshotReader.from_directory(root, local.snapshot, local.evidence)
    return local, reader


def test_context_projects_fixed_inputs_to_org_contract_and_previews_selected_ranges():
    local, reader = load_fixture()
    request = build_context(local, reader, request_id="b-context-fixture")
    validate_request_against_local(local, request)
    assert request.protocol_version == "0.1.0"
    assert request.snapshot_id == local.snapshot.snapshot_id
    assert request.rule_findings == local.rule_findings
    assert request.estimates == local.estimates
    assert request.intents == local.intents
    assert request.excerpts
    assert all(reader.read_excerpt(item.evidence_id) == item for item in request.excerpts)
    preview = preview_request(request)
    assert "UTF-8" in preview
    assert all(ref.path in preview for ref in request.evidence)


def test_context_budget_omits_whole_evidence_and_retains_valid_reference_closure():
    local, reader = load_fixture()
    request = build_context(
        local,
        reader,
        request_id="small-budget",
        options=ContextOptions(input_token_budget=5000, max_excerpts=2),
    )
    validate_request_against_local(local, request)
    assert (
        count_fragments(
            [
                json.dumps(
                    project_analysis_request(request), ensure_ascii=False, separators=(",", ":")
                )
            ]
        )
        <= 2500
    )
    assert len(request.excerpts) <= 2
    assert request.truncated
    assert request.missing_context
    assert all(reader.read_excerpt(item.evidence_id) == item for item in request.excerpts)


def test_context_excludes_paths_and_sensitive_derived_fields_before_preview():
    local, reader = load_fixture()
    credential = "sk-proj-" + "SyntheticPrivateValue" * 2
    poisoned = local.intents[0].model_copy(update={"text": credential})
    local = local.model_copy(update={"intents": (poisoned, *local.intents[1:])})
    request = build_context(
        local,
        reader,
        request_id="privacy",
        options=ContextOptions(exclude_paths=("tests",)),
    )
    validate_request_against_local(local, request)
    assert credential not in request.model_dump_json()
    assert "tests/" not in request.model_dump_json()
    assert credential not in preview_request(request)
    assert request.truncated
    assert any("excluded" in reason for reason in request.missing_context)


def test_context_follows_changed_helper_to_unchanged_caller_without_sending_unrelated_code(
    source_repo,
):
    (source_repo / "entry.py").write_text(
        "from helper import render\ndef run():\n    return render()\n"
    )
    (source_repo / "helper.py").write_text("def render():\n    return 'old'\n")
    (source_repo / "unrelated.py").write_text(
        "def unrelated():\n    return 'UNRELATED_PRIVATE_TEXT'\n"
    )
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "helper.py").write_text("def render():\n    return 'new'\n")
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    request = build_context(result.local, result.reader, request_id="cross-file")
    validate_request_against_local(result.local, request)
    assert {ref.path for ref in request.evidence} == {"entry.py", "helper.py"}
    assert "UNRELATED_PRIVATE_TEXT" not in request.model_dump_json()
    assert "unrelated.py" not in request.model_dump_json()


def test_budget_keeps_changed_function_bodies_and_associated_tests_before_call_details(source_repo):
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
        request_id="budget-with-tests",
        options=ContextOptions(input_token_budget=16000),
    )
    validate_request_against_local(result.local, request)
    assert request.truncated
    assert len(request.model_dump_json().encode()) <= 524_288
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
    assert request.test_definitions
    assert all(test.assertions for test in request.test_definitions)
    catalog = {ref.evidence_id: ref for ref in request.evidence}
    assert any(
        all(catalog[ref].side == "head" for ref in test.evidence_ids)
        and "submit() is True" in " ".join(test.assertions)
        for test in request.test_definitions
    )
    assert {f.side for f in request.facts.functions if f.symbol_id == "app.py#submit"} == {
        "base",
        "head",
    }


@pytest.mark.parametrize(
    "name", ["dynamic-call-unresolved", "missing-intent-and-tests", "flow-entry-invalid"]
)
def test_context_preserves_original_missing_capabilities(name):
    local, reader = load_fixture(name)
    request = build_context(local, reader, request_id="gaps")
    validate_request_against_local(local, request)
    assert request.missing_context
    assert not request.truncated


def test_flow_entry_evidence_can_be_prioritized_with_a_single_excerpt_budget():
    local, reader = load_fixture()
    preferred = next(ref for ref in local.evidence if ref.kind == "code" and ref.side == "head")
    request = build_context(
        local,
        reader,
        request_id="preferred",
        options=ContextOptions(max_excerpts=1, preferred_evidence_ids=(preferred.evidence_id,)),
    )
    assert [ref.evidence_id for ref in request.evidence] == [preferred.evidence_id]


def test_mutated_reader_bytes_are_rejected_and_tiny_budget_fails_explicitly():
    local, reader = load_fixture()

    class TamperedReader:
        def evidence_catalog(self):
            return reader.evidence_catalog()

        def read_excerpt(self, evidence_id):
            return SourceExcerpt(evidence_id=evidence_id, text="changed after capture")

    with pytest.raises(ValueError, match="digest"):
        build_context(local, TamperedReader(), request_id="tampered")
    with pytest.raises(ContextBudgetExceeded):
        build_context(
            local, reader, request_id="tiny", options=ContextOptions(input_token_budget=1)
        )


def test_suspected_credential_in_real_frozen_code_never_enters_request_or_preview(source_repo):
    (source_repo / "app.py").write_text("def submit():\n    return False\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    credential = "ghp_" + "SyntheticCredential" * 2
    (source_repo / "app.py").write_text(
        f"def submit():\n    api_key = '{credential}'\n    return True\n"
    )
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    request = build_context(result.local, result.reader, request_id="secret-source")
    validate_request_against_local(result.local, request)
    assert credential not in request.model_dump_json()
    assert credential not in preview_request(request)
    assert request.truncated

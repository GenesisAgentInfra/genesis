import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.intent import IntentSource, collect_intents
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.snapshot import SnapshotInput, SnapshotSpec
from genesis_contracts.validation import validate_local_analysis
from test_git_snapshot import git


def test_intent_sources_keep_frozen_text_and_trust_classification(source_repo):
    (source_repo / "app.py").write_text("def submit():\n    return True\n")
    (source_repo / "task.md").write_text("- Notify after success.\n- Never notify on failure.\n")
    (source_repo / "plan.md").write_text("We already prevent notifications on failure.\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "initial")
    captured = capture_snapshot(
        source_repo,
        SnapshotSpec(
            base="HEAD",
            inputs=(
                SnapshotInput(path="task.md", kind="intent"),
                SnapshotInput(path="plan.md", kind="intent"),
            ),
        ),
    )
    result = analyze_snapshot(captured)
    (source_repo / "task.md").write_text("CHANGED AFTER CAPTURE")
    collected = collect_intents(
        result.local,
        result.reader,
        captured.source,
        (IntentSource("task.md", "task"), IntentSource("plan.md", "agent_plan")),
    )
    validate_local_analysis(collected.local)
    assert [(item.text, item.nature) for item in collected.local.intents] == [
        ("Notify after success.", "user_intent"),
        ("Never notify on failure.", "user_intent"),
        ("We already prevent notifications on failure.", "agent_claim"),
    ]
    assert collected.local.snapshot == result.local.snapshot
    first = collected.local.intents[0]
    assert collected.reader.read_excerpt(first.evidence_ids[0]).text == "- Notify after success."


def test_conflicting_sources_survive_with_candidate_group_and_secrets_are_omitted(source_repo):
    (source_repo / "app.py").write_text("def submit():\n    return True\n")
    (source_repo / "task.md").write_text("Send email.\n")
    (source_repo / "requirements.md").write_text("Do not send email.\n")
    credential = "sk-proj-" + "SyntheticPrivateValue" * 2
    (source_repo / "plan.md").write_text(f"Use this credential: {credential}\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    sources = (
        IntentSource("task.md", "task"),
        IntentSource("requirements.md", "requirements"),
        IntentSource("plan.md", "agent_plan"),
        IntentSource("absent.md", "pr_description"),
    )
    captured = capture_snapshot(
        source_repo,
        SnapshotSpec(
            base="HEAD",
            inputs=tuple(SnapshotInput(path=item.path, kind="intent") for item in sources),
        ),
    )
    result = analyze_snapshot(captured)
    collected = collect_intents(result.local, result.reader, captured.source, sources)
    assert [item.text for item in collected.local.intents] == ["Send email.", "Do not send email."]
    groups = {item.conflict_group for item in collected.local.intents}
    assert len(groups) == 1 and None not in groups
    assert credential not in collected.local.model_dump_json()
    assert {item.code for item in collected.local.limitations} >= {
        "intent_excluded",
        "intent_not_captured",
        "intent_conflict_candidate",
    }


def test_declared_task_makes_associated_head_test_context_available_for_semantic_review(
    source_repo,
):
    (source_repo / "app.py").write_text("def submit():\n    return False\n")
    (source_repo / "test_app.py").write_text(
        "from app import submit\ndef test_submit():\n    assert submit() is True\n"
    )
    (source_repo / "task.md").write_text("Return true on success.\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_text("def submit():\n    return True\n")
    captured = capture_snapshot(
        source_repo,
        SnapshotSpec(
            base="HEAD",
            inputs=(SnapshotInput(path="task.md", kind="intent"),),
        ),
    )
    result = analyze_snapshot(captured)
    collected = collect_intents(
        result.local, result.reader, captured.source, (IntentSource("task.md", "task"),)
    )
    assert collected.local.capabilities.acceptance_tests.status == "analyzed"
    assert "execution" in collected.local.capabilities.acceptance_tests.analyzed_scope


def test_general_disagreement_is_preserved_without_lexical_proof_of_consistency(source_repo):
    (source_repo / "app.py").write_text("def retain(): return 30\n")
    (source_repo / "task.md").write_text("Keep customer records for thirty days.\n")
    (source_repo / "requirements.md").write_text("Erase customer records immediately.\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    sources = (IntentSource("task.md", "task"), IntentSource("requirements.md", "requirements"))
    captured = capture_snapshot(
        source_repo,
        SnapshotSpec(
            base="HEAD", inputs=tuple(SnapshotInput(path=i.path, kind="intent") for i in sources)
        ),
    )
    result = analyze_snapshot(captured)
    collected = collect_intents(result.local, result.reader, captured.source, sources)
    assert [i.text for i in collected.local.intents] == [
        "Keep customer records for thirty days.",
        "Erase customer records immediately.",
    ]
    assert all(i.conflict_group is None for i in collected.local.intents)
    assert any(
        i.code == "intent_conflict_scope" and "semantic" in i.message
        for i in collected.local.limitations
    )


@pytest.mark.parametrize(
    "path,text",
    [
        ("task.md", "# Source: https://github.com/owner/project/issues/42\nKeep receipts."),
        (
            "genesis-ci-intent-local/source-0.md",
            "# Source: https://github.com/owner/project/pull/7\nKeep receipts.",
        ),
        (
            "genesis-ci-intent-local/source-0.md",
            "# Task\n# Source: https://github.com/owner/project/issues/42\nKeep receipts.",
        ),
    ],
)
def test_ordinary_or_misplaced_headings_do_not_become_ci_provenance(source_repo, path, text):
    destination = source_repo / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "intent headings")
    captured = capture_snapshot(
        source_repo,
        SnapshotSpec(base="HEAD", inputs=(SnapshotInput(path=path, kind="intent"),)),
    )
    result = analyze_snapshot(captured)
    collected = collect_intents(
        result.local, result.reader, captured.source, (IntentSource(path, "task"),)
    )
    assert [item.text for item in collected.local.intents] == ["Keep receipts."]
    assert len(collected.local.intents[0].evidence_ids) == 1
    assert not any(item.code == "intent_source_location" for item in collected.local.limitations)

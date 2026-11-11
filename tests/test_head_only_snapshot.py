"""A snapshot without a base captures the head side only and reports no change."""

import pytest
from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.git_snapshot import SnapshotError, capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

APP = """def helper():
    return 1


def run():
    return helper()
"""


def test_commit_capture_without_base_has_one_side_and_no_changes(source_repo):
    write(source_repo, "app.py", APP)
    head = commit(source_repo)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(head="HEAD"))
    manifest = snapshot.capture.manifest
    assert (manifest.base_revision, manifest.head_revision) == (None, head)
    assert {file.side for file in manifest.files} == {EvidenceSide.head}
    assert snapshot.capture.file_diff.changes == ()
    extraction = extract_python(snapshot)
    assert extraction.analysis.change_set.changed_symbol_ids == ()
    facts = python_facts(extraction)
    assert facts.facts and {fact.side for fact in facts.facts} == {EvidenceSide.head}
    call = next(fact for fact in facts.facts if fact.kind == "call")
    assert call.target.targets == ("app.py#helper",)


def test_worktree_capture_without_base_reads_uncommitted_content(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    write(source_repo, "app.py", APP.replace("return 1", "return 2"))
    snapshot = capture_snapshot(source_repo, SnapshotSpec())
    manifest = snapshot.capture.manifest
    assert manifest.base_revision is None
    assert manifest.head_revision.startswith("worktree:")
    assert {file.side for file in manifest.files} == {EvidenceSide.head}
    assert "return 2" in snapshot.source.read_text(EvidenceSide.head, "app.py")
    assert snapshot.capture.worktree_consistency == "two_matching_reads"


def test_same_content_gives_the_same_snapshot_identity(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    first = capture_snapshot(source_repo, SnapshotSpec(head="HEAD")).capture.manifest
    second = capture_snapshot(source_repo, SnapshotSpec(head="HEAD")).capture.manifest
    compared = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    assert first.snapshot_id == second.snapshot_id
    assert compared.capture.manifest.snapshot_id != first.snapshot_id
    assert {file.side for file in compared.capture.manifest.files} == set(EvidenceSide)


def test_a_named_but_missing_base_is_still_an_error(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    with pytest.raises(SnapshotError):
        capture_snapshot(source_repo, SnapshotSpec(base="no-such-revision", head="HEAD"))

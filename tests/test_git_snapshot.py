import os
import shutil
import subprocess

import pytest
from genesis_ci.cli import app
from genesis_ci.git_snapshot import SnapshotError, capture_snapshot
from genesis_ci.snapshot_store import load_snapshot, save_snapshot
from genesis_ci.source_snapshot import EvidenceRegistry, FrozenSourceSnapshot
from genesis_contracts.models import EvidenceSide, ReferenceRange
from genesis_contracts.snapshot import SnapshotInput, SnapshotLimits, SnapshotSpec
from typer.testing import CliRunner

BASE, HEAD = EvidenceSide.base, EvidenceSide.head


def git(repo, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(
        ["git", "-c", "core.hooksPath=" + os.devnull, *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    ).stdout


def write(repo, path, content):
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content.encode() if isinstance(content, str) else content)


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "snapshot test")
    return git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def repo(tmp_path):
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Snapshot Test")
    git(repo, "config", "user.email", "snapshot@example.invalid")
    write(repo, "src/app.py", "from .helper import run\n\ndef main():\n    return run()\n")
    write(repo, "src/helper.py", "def run():\n    return 1\n")
    write(repo, "tests/test_app.py", "def test_main():\n    assert main() == 1\n")
    write(repo, ".gitignore", ".genesis/snapshots/\nignored.py\n")
    commit(repo)
    return repo


def changes(result):
    return [
        (item.change.change_type, item.change.base_path, item.change.head_path)
        for item in result.capture.file_diff.changes
    ]


def test_commit_capture_has_both_sides_all_context_and_file_changes(repo):
    base = git(repo, "rev-parse", "HEAD").decode().strip()
    write(repo, "src/helper.py", "def run():\n    return 2\n")
    (repo / "src/app.py").rename(repo / "src/entry.py")
    (repo / "tests/test_app.py").unlink()
    write(repo, "src/new.py", "value = 3\n")
    head = commit(repo)
    write(repo, "src/helper.py", "dirty; this must not be captured\n")
    result = capture_snapshot(repo, SnapshotSpec(base=base, head=head))
    assert set(changes(result)) == {
        ("renamed", "src/app.py", "src/entry.py"),
        ("modified", "src/helper.py", "src/helper.py"),
        ("deleted", "tests/test_app.py", None),
        ("added", None, "src/new.py"),
    }
    assert result.source.read_bytes(HEAD, "src/helper.py") == b"def run():\n    return 2\n"
    assert result.source.read_bytes(BASE, "src/helper.py") == b"def run():\n    return 1\n"
    assert result.capture.manifest.base_revision == base
    assert result.capture.manifest.head_revision == head
    assert result.capture.file_diff.symbol_status == "not_analyzed"
    assert "changed_symbol_ids" not in result.capture.file_diff.model_dump()
    assert result.capture.manifest.integrity_status == "complete"


def test_stable_capture_and_read_after_repository_removed(repo):
    spec = SnapshotSpec(base="HEAD", head="HEAD")
    first = capture_snapshot(repo, spec)
    second = capture_snapshot(repo, spec)
    assert first.capture == second.capture
    assert "src/app.py" in first.source.list_files(HEAD)
    shutil.rmtree(repo)
    assert b"return run()" in first.source.read_bytes(HEAD, "src/app.py")
    with pytest.raises(KeyError, match="not captured"):
        first.source.read_bytes(HEAD, "not_there.py")


def test_worktree_uses_final_bytes_and_keeps_index_unchanged(repo):
    write(repo, "src/helper.py", "staged = 1\n")
    git(repo, "add", "src/helper.py")
    write(repo, "src/helper.py", "final = 2\n")
    write(repo, "src/new.py", "new = 1\n")
    git(repo, "add", "src/new.py")
    (repo / "tests/test_app.py").unlink()
    index = (repo / ".git/index").read_bytes()
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    assert result.source.read_bytes(HEAD, "src/helper.py") == b"final = 2\n"
    assert result.source.read_bytes(HEAD, "src/new.py") == b"new = 1\n"
    assert ("deleted", "tests/test_app.py", None) in changes(result)
    assert result.capture.worktree_consistency == "two_matching_reads"
    assert result.capture.manifest.head_revision.startswith("worktree:")
    assert (repo / ".git/index").read_bytes() == index
    snapshot_id = result.capture.manifest.snapshot_id
    write(repo, "src/helper.py", "changed after capture\n")
    assert result.source.read_bytes(HEAD, "src/helper.py") == b"final = 2\n"
    assert (
        capture_snapshot(repo, SnapshotSpec(base="HEAD")).capture.manifest.snapshot_id
        != snapshot_id
    )


def test_untracked_files_require_opt_in_but_explicit_intent_is_selected(repo):
    write(repo, "scratch.py", "scratch = 1\n")
    write(repo, "ignored.py", "ignored = 1\n")
    write(repo, "task.md", "Please preserve notifications.\n")
    spec = SnapshotSpec(base="HEAD", inputs=(SnapshotInput(path="task.md", kind="intent"),))
    result = capture_snapshot(repo, spec)
    assert "scratch.py" not in result.source.list_files(HEAD)
    assert "ignored.py" not in result.source.list_files(HEAD)
    assert result.source.read_text(HEAD, "task.md").startswith("Please")
    assert any(
        item.path == "scratch.py" and item.reason == "untracked_not_selected"
        for item in result.capture.omissions
    )
    assert result.capture.manifest.integrity_status == "partial"
    included = capture_snapshot(repo, spec.model_copy(update={"include_untracked": True}))
    assert "scratch.py" in included.source.list_files(HEAD)
    assert "ignored.py" not in included.source.list_files(HEAD)
    assert included.capture.manifest.integrity_status == "complete"


def test_secret_and_generated_inputs_never_override_exclusion(repo):
    for path in (
        ".env",
        ".env.local",
        "secret.pem",
        ".aws/credentials",
        ".venv/app.py",
        "node_modules/app.py",
        ".genesis/snapshots/app.py",
    ):
        write(repo, path, "SECRET DO NOT CAPTURE\n")
        git(repo, "add", "-f", path)
    git(repo, "commit", "-qm", "excluded files")
    spec = SnapshotSpec(
        base="HEAD", head="HEAD", inputs=(SnapshotInput(path=".env", kind="config"),)
    )
    result = capture_snapshot(repo, spec)
    for file in result.capture.manifest.files:
        assert b"SECRET" not in result.source.read_bytes(file.side, file.path)
    assert result.capture.manifest.integrity_status == "partial"
    assert any(
        item.path == ".env" and item.affects_completeness for item in result.capture.omissions
    )


def test_flow_and_explicit_input_bytes_change_snapshot_identity(repo):
    write(repo, ".genesis/flows.yaml", "schema_version: 1\nflows: []\n")
    git(repo, "add", "-f", ".genesis/flows.yaml")
    commit(repo)
    write(repo, "task.md", "original intent\n")
    spec = SnapshotSpec(base="HEAD", inputs=(SnapshotInput(path="task.md", kind="intent"),))
    first = capture_snapshot(repo, spec)
    write(repo, "task.md", "new intent\n")
    second = capture_snapshot(repo, spec)
    assert first.capture.manifest.snapshot_id != second.capture.manifest.snapshot_id
    assert (
        next(
            item.kind
            for item in second.capture.manifest.files
            if item.side == HEAD and item.path == ".genesis/flows.yaml"
        )
        == "flow"
    )


def test_invalid_baseline_never_becomes_empty_base(repo):
    for ref in ("not-a-local-ref", "--help", "HEAD:path-does-not-exist"):
        with pytest.raises(SnapshotError) as caught:
            capture_snapshot(repo, SnapshotSpec(base=ref, head="HEAD"))
        assert caught.value.code == "revision_unavailable"


def test_nested_directory_is_rejected(repo):
    with pytest.raises(SnapshotError, match="repository root"):
        capture_snapshot(repo / "src", SnapshotSpec(base="HEAD", head="HEAD"))


def test_linked_git_worktree_is_supported(repo, tmp_path):
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    result = capture_snapshot(linked, SnapshotSpec(base="HEAD"))
    assert result.source.read_bytes(HEAD, "src/helper.py").endswith(b"return 1\n")


@pytest.mark.parametrize("head", ["HEAD", None])
def test_symlinks_are_not_read(repo, tmp_path, head):
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET OUTSIDE\n")
    (repo / "src/linked.py").symlink_to(outside)
    commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head=head))
    assert "src/linked.py" not in result.source.list_files(HEAD)
    assert any(
        item.path == "src/linked.py" and item.reason == "symlink"
        for item in result.capture.omissions
    )
    assert result.capture.manifest.integrity_status == "partial"


def test_directory_symlink_cannot_turn_excluded_code_into_deletions(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD").decode().strip()
    shutil.rmtree(repo / "src")
    outside = tmp_path / "external"
    outside.mkdir()
    write(outside, "app.py", "DO NOT READ\n")
    (repo / "src").symlink_to(outside, target_is_directory=True)
    head = commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base=base, head=head))
    assert not any(item[0] == "deleted" and item[1].startswith("src/") for item in changes(result))
    assert result.capture.file_diff.coverage.status == "insufficient_context"


def test_gitlinks_are_omitted_not_traversed(repo):
    sha = git(repo, "rev-parse", "HEAD").decode().strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor")
    git(repo, "commit", "-qm", "gitlink")
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    assert any(
        item.path == "vendor" and item.reason == "submodule" for item in result.capture.omissions
    )


def test_binary_encoding_lfs_and_missing_explicit_input_are_partial(repo):
    write(repo, "binary.py", b"\x00\x01")
    write(repo, "latin.py", b"# coding: latin-1\nname = '\xe9'\n")
    write(
        repo,
        "lfs.py",
        "version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\nsize 100\n",
    )
    commit(repo)
    result = capture_snapshot(
        repo,
        SnapshotSpec(
            base="HEAD", head="HEAD", inputs=(SnapshotInput(path="missing.md", kind="intent"),)
        ),
    )
    reasons = {(item.path, item.reason) for item in result.capture.omissions}
    assert ("binary.py", "binary") in reasons
    assert ("latin.py", "unsupported_encoding") in reasons
    assert ("lfs.py", "binary") in reasons
    assert ("missing.md", "missing_input") in reasons
    assert result.capture.manifest.integrity_status == "partial"


@pytest.mark.parametrize(
    "limits,reason",
    [
        (SnapshotLimits(max_file_bytes=10), "file_budget"),
        (SnapshotLimits(max_total_bytes=80), "total_budget"),
        (SnapshotLimits(max_files=2), "count_budget"),
    ],
)
def test_budgets_are_explicit_and_never_invent_file_additions(repo, limits, reason):
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD", limits=limits))
    assert result.capture.manifest.integrity_status == "partial"
    assert any(item.reason == reason for item in result.capture.omissions)
    assert changes(result) == []
    assert (
        sum(
            len(result.source.read_bytes(item.side, item.path))
            for item in result.capture.manifest.files
        )
        <= limits.max_total_bytes
    )


def test_git_metadata_budget_is_bounded(repo):
    with pytest.raises(SnapshotError) as caught:
        capture_snapshot(
            repo,
            SnapshotSpec(base="HEAD", head="HEAD", limits=SnapshotLimits(max_metadata_bytes=1)),
        )
    assert caught.value.code == "metadata_budget"


def test_executable_mode_changes_are_captured_and_affect_worktree_id(repo):
    first = capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    (repo / "src/helper.py").chmod(0o755)
    second = capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    assert first.capture.manifest.snapshot_id != second.capture.manifest.snapshot_id
    delta = next(
        item
        for item in second.capture.file_diff.changes
        if item.change.head_path == "src/helper.py"
    )
    assert delta.base_mode == "100644" and delta.head_mode == "100755"


def test_duplicate_content_does_not_make_arbitrary_rename(repo):
    write(repo, "old1.py", "same\n")
    write(repo, "old2.py", "same\n")
    base = commit(repo)
    (repo / "old1.py").unlink()
    (repo / "old2.py").unlink()
    write(repo, "new.py", "same\n")
    head = commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base=base, head=head))
    assert not any(item[0] == "renamed" for item in changes(result))
    assert len(changes(result)) == 3


def test_no_customer_code_git_filters_or_fsmonitor_execute(repo, tmp_path, monkeypatch):
    marker = tmp_path / "executed"
    command = f"touch {marker}"
    git(repo, "config", "core.fsmonitor", command)
    git(repo, "config", "diff.external", command)
    git(repo, "config", "diff.evil.textconv", command)
    git(repo, "config", "filter.evil.smudge", command)
    write(repo, ".gitattributes", "*.py diff=evil filter=evil\n")
    write(repo, "conftest.py", f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    write(repo, "setup.py", f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    # Disable configured fsmonitor while committing our test fixture.
    git(repo, "-c", "core.fsmonitor=false", "add", "-A")
    git(repo, "-c", "core.fsmonitor=false", "commit", "-qm", "unsafe hooks")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", command)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", command)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-repository"))
    for head in ("HEAD", None):
        result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head=head))
        assert "setup.py" in result.source.list_files(HEAD)
    assert not marker.exists()


def test_live_changes_fail_after_bounded_retries(repo, monkeypatch):
    import genesis_ci.git_snapshot as module

    original = module._read_worktree
    counter = 0

    def unstable(root, path, limit):
        nonlocal counter
        if path == "src/helper.py":
            counter += 1
            write(repo, path, f"counter = {counter}\n")
        return original(root, path, limit)

    monkeypatch.setattr(module, "_read_worktree", unstable)
    with pytest.raises(SnapshotError) as caught:
        capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    assert caught.value.code == "worktree_changed"
    assert counter == 4


def test_single_worktree_change_is_retried_successfully(repo, monkeypatch):
    import genesis_ci.git_snapshot as module

    original = module._read_worktree
    reads = 0

    def once(root, path, limit):
        nonlocal reads
        if path == "src/helper.py":
            reads += 1
            if reads == 2:
                write(repo, path, "stable after edit\n")
        return original(root, path, limit)

    monkeypatch.setattr(module, "_read_worktree", once)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    assert reads == 4
    assert result.source.read_bytes(HEAD, "src/helper.py") == b"stable after edit\n"


def test_skip_worktree_requires_commit_mode(repo):
    git(repo, "update-index", "--skip-worktree", "src/helper.py")
    with pytest.raises(SnapshotError) as caught:
        capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    assert caught.value.code == "sparse_worktree"
    assert (
        capture_snapshot(
            repo, SnapshotSpec(base="HEAD", head="HEAD")
        ).capture.manifest.integrity_status
        == "complete"
    )


def test_evidence_is_registered_only_after_freezing_and_reader_stays_stable(repo):
    write(repo, "src/unicode.py", "# 中文\r\nvalue = '好'\r\n")
    commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    registry = EvidenceRegistry(result.source)
    span = ReferenceRange(start_line=1, end_line=2, start_column=2, end_column=5)
    ref = registry.register(HEAD, "src/unicode.py", span)
    assert registry.register(HEAD, "src/unicode.py", span) == ref
    reader = registry.freeze()
    assert reader.read_excerpt(ref.evidence_id).text == "中文\r\nvalue"
    (repo / "src/unicode.py").write_text("mutated")
    assert reader.read_excerpt(ref.evidence_id).text == "中文\r\nvalue"
    registry.register(BASE, "src/unicode.py", ReferenceRange(start_line=1, end_line=1))
    assert len(reader.evidence_catalog()) == 1
    with pytest.raises(ValueError, match="lines"):
        registry.register(HEAD, "src/unicode.py", ReferenceRange(start_line=3, end_line=3))


def test_source_rejects_missing_or_tampered_bytes(repo):
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    files = {
        (item.side, item.path): result.source.read_bytes(item.side, item.path)
        for item in result.capture.manifest.files
    }
    key = next(iter(files))
    files[key] = b"changed"
    with pytest.raises(ValueError, match="digest"):
        FrozenSourceSnapshot(result.capture.manifest, files)
    files.pop(key)
    with pytest.raises(ValueError, match="match manifest"):
        FrozenSourceSnapshot(result.capture.manifest, files)


def test_artifact_round_trip_outlives_repo_and_detects_tampering(repo, tmp_path):
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    directory = (tmp_path / "snapshot").resolve()
    save_snapshot(result, directory)
    shutil.rmtree(repo)
    restored = load_snapshot(directory)
    assert restored.capture == result.capture
    assert restored.source.read_bytes(HEAD, "src/helper.py") == b"def run():\n    return 1\n"
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "snapshot.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        save_snapshot(result, directory)
    blob = next((directory / "blobs").iterdir())
    blob.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest"):
        load_snapshot(directory)


def test_artifact_symlink_blob_and_loader_budget_rejected(repo, tmp_path):
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    directory = (tmp_path / "snapshot").resolve()
    save_snapshot(result, directory)
    with pytest.raises(SnapshotError):
        load_snapshot(directory, limits=SnapshotLimits(max_total_bytes=1))
    blob = next((directory / "blobs").iterdir())
    outside = tmp_path / "blob"
    outside.write_bytes(blob.read_bytes())
    blob.unlink()
    blob.symlink_to(outside)
    with pytest.raises(SnapshotError, match="unsafe"):
        load_snapshot(directory)


def test_cli_captures_real_repo_and_partial_exit_codes(repo, tmp_path):
    output = (tmp_path / "artifact").resolve()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "snapshot",
            "--repo",
            str(repo),
            "--base",
            "HEAD",
            "--head",
            "HEAD",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "symbols=not_analyzed" in result.output
    assert load_snapshot(output).capture.manifest.integrity_status == "complete"
    write(repo, "not_selected.py", "new = True\n")
    partial = runner.invoke(
        app,
        [
            "snapshot",
            "--repo",
            str(repo),
            "--base",
            "HEAD",
            "--worktree",
            "--output",
            str(tmp_path / "partial"),
        ],
    )
    assert partial.exit_code == 2, partial.output
    assert (tmp_path / "partial/snapshot.json").exists()
    failed = runner.invoke(
        app,
        [
            "snapshot",
            "--repo",
            str(repo),
            "--base",
            "missing",
            "--worktree",
            "--output",
            str(tmp_path / "failed"),
        ],
    )
    assert failed.exit_code == 1
    assert not (tmp_path / "failed").exists()


def test_snapshot_spec_rejects_ambiguous_or_unsafe_selection():
    from pydantic import ValidationError

    for values in (
        {"head": "HEAD", "include_untracked": True},
        {"exclude_paths": ("../outside",)},
        {"inputs": ({"path": "/outside", "kind": "intent"},)},
    ):
        with pytest.raises(ValidationError):
            SnapshotSpec(base="HEAD", **values)


def test_git_conflict_stages_are_not_silently_merged(repo):
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    git(repo, "checkout", "-qb", "other")
    write(repo, "src/helper.py", "other = True\n")
    other = commit(repo)
    git(repo, "checkout", "-q", "--detach", head)
    write(repo, "src/helper.py", "mine = True\n")
    commit(repo)
    result = subprocess.run(["git", "merge", other], cwd=repo, capture_output=True)
    assert result.returncode != 0
    with pytest.raises(SnapshotError) as caught:
        capture_snapshot(repo, SnapshotSpec(base=head))
    assert caught.value.code == "unmerged_index"


def test_failed_worktree_capture_does_not_write_partial_artifact(repo, tmp_path, monkeypatch):
    import genesis_ci.git_snapshot as module

    def changing(*args, **kwargs):
        raise module._ChangedDuringCapture()

    monkeypatch.setattr(module, "_read_worktree", changing)
    output = tmp_path / "never-written"
    result = CliRunner().invoke(
        app,
        ["snapshot", "--repo", str(repo), "--base", "HEAD", "--worktree", "--output", str(output)],
    )
    assert result.exit_code == 1
    assert "worktree_changed" in result.output
    assert not output.exists()


def test_utf8_bom_and_non_line_separators_remain_exact(repo):
    content = "\ufeff# 文本\u2028still first line\f\nvalue = 1\r\n"
    write(repo, "source.py", content)
    commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    ref = result.source.evidence(HEAD, "source.py", ReferenceRange(start_line=1, end_line=1))
    registry = EvidenceRegistry(result.source)
    registry.register(HEAD, "source.py", ref.range)
    assert registry.freeze().read_excerpt(ref.evidence_id).text == content.split("\n")[0]
    assert result.source.read_bytes(HEAD, "source.py") == content.encode("utf-8")


def test_named_revision_is_pinned_once_before_tree_reads(repo, monkeypatch):
    import genesis_ci.git_snapshot as module

    base = git(repo, "rev-parse", "HEAD").decode().strip()
    write(repo, "src/helper.py", "updated = True\n")
    head = commit(repo)
    git(repo, "branch", "moving", head)
    original = module._Git.tree

    def move_ref_after_resolving(self, revision):
        result = original(self, revision)
        if revision == head:
            git(repo, "update-ref", "refs/heads/moving", base)
        return result

    monkeypatch.setattr(module._Git, "tree", move_ref_after_resolving)
    result = capture_snapshot(repo, SnapshotSpec(base=base, head="moving"))
    assert result.capture.manifest.head_revision == head
    assert result.source.read_bytes(HEAD, "src/helper.py") == b"updated = True\n"


def test_loaded_metadata_rejects_changed_mode_or_delta(repo, tmp_path):
    import json

    result = capture_snapshot(repo, SnapshotSpec(base="HEAD"))
    directory = (tmp_path / "snapshot").resolve()
    save_snapshot(result, directory)
    metadata = directory / "snapshot.json"
    original = json.loads(metadata.read_text())
    head_mode = next(item for item in original["modes"] if item["side"] == "head")
    head_mode["mode"] = "100755"
    metadata.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="worktree identity"):
        load_snapshot(directory)
    payload = result.capture.model_dump(mode="json")
    payload["file_diff"]["changes"] = [
        {
            "change": {"change_type": "deleted", "base_path": "not-captured.py"},
            "base_mode": "100644",
        }
    ]
    metadata.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="file delta"):
        load_snapshot(directory)


def test_a_link_to_a_document_does_not_make_the_snapshot_partial(repo):
    (repo / "GUIDE.md").symlink_to("README.md")
    commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    listed = [item for item in result.capture.omissions if item.path == "GUIDE.md"]
    # The link is still recorded on both sides and never read, but it cannot hide source.
    assert {(item.reason, item.affects_completeness) for item in listed} == {("symlink", False)}
    assert result.capture.manifest.integrity_status == "complete"


def test_a_link_that_may_be_a_directory_still_makes_the_snapshot_partial(repo, tmp_path):
    outside = tmp_path / "vendored"
    outside.mkdir()
    (repo / "vendored").symlink_to(outside, target_is_directory=True)
    commit(repo)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", head="HEAD"))
    assert result.capture.manifest.integrity_status == "partial"

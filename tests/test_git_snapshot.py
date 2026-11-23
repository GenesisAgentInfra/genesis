import os
import shutil
import subprocess
import time

import pytest
from genesis_ci.git_snapshot import SnapshotError, capture_snapshot, changed_paths
from genesis_ci.snapshot_store import load_snapshot, save_snapshot
from genesis_ci.source_snapshot import EvidenceRegistry, FrozenSourceSnapshot
from genesis_contracts.models import EvidenceSide, ReferenceRange
from genesis_contracts.snapshot import SnapshotInput, SnapshotLimits, SnapshotSpec

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
    assert distinct_bytes(result) <= limits.max_total_bytes


def distinct_bytes(result):
    """Bytes the capture holds, content that is the same on both sides counted once."""
    sizes = {
        item.content_digest: len(result.source.read_bytes(item.side, item.path))
        for item in result.capture.manifest.files
    }
    return sum(sizes.values())


def captured(result, side):
    return sorted(item.path for item in result.capture.manifest.files if item.side == side)


ALL = ["src/app.py", "src/helper.py", "tests/test_app.py"]
# What one side of the fixture weighs, and the file a change replaces.
ONE_SIDE, HELPER = 118, "def run():\n    return 2\n"


def test_a_side_that_repeats_the_other_costs_the_budget_nothing(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD").decode().strip()
    write(repo, "src/helper.py", HELPER)
    head = commit(repo)
    # Room for one side and the changed file, far from room for two sides.
    limits = SnapshotLimits(max_total_bytes=ONE_SIDE + len(HELPER), max_files=4)
    result = capture_snapshot(repo, SnapshotSpec(base=base, head=head, limits=limits))
    assert result.capture.manifest.integrity_status == "complete"
    assert captured(result, BASE) == ALL == captured(result, HEAD)
    assert changes(result) == [("modified", "src/helper.py", "src/helper.py")]
    assert distinct_bytes(result) == ONE_SIDE + len(HELPER)
    # What was captured within the limits can be stored and read back within them.
    save_snapshot(result, tmp_path / "stored")
    restored = load_snapshot(tmp_path / "stored", limits=limits)
    assert restored.capture == result.capture
    assert all(
        restored.source.read_bytes(item.side, item.path)
        == result.source.read_bytes(item.side, item.path)
        for item in result.capture.manifest.files
    )


def test_the_working_tree_is_charged_only_for_what_differs_from_the_base(repo):
    write(repo, "src/helper.py", HELPER)
    limits = SnapshotLimits(max_total_bytes=ONE_SIDE + len(HELPER), max_files=4)
    result = capture_snapshot(repo, SnapshotSpec(base="HEAD", limits=limits))
    assert result.capture.manifest.integrity_status == "complete"
    assert captured(result, BASE) == ALL == captured(result, HEAD)
    assert changes(result) == [("modified", "src/helper.py", "src/helper.py")]


@pytest.mark.parametrize("head", ["commit", "worktree"])
def test_changed_content_that_does_not_fit_is_still_left_out_and_said(repo, head):
    base = git(repo, "rev-parse", "HEAD").decode().strip()
    write(repo, "src/helper.py", HELPER)
    write(repo, "src/new.py", "value = 3\n")
    revision = commit(repo) if head == "commit" else None
    if head == "worktree":
        git(repo, "add", "-A")
    # One byte short of the changed file, and no file left for the new one.
    for limits, reason, path in (
        (
            SnapshotLimits(max_total_bytes=ONE_SIDE + len(HELPER) - 1),
            "total_budget",
            "src/helper.py",
        ),
        (SnapshotLimits(max_files=4), "count_budget", "src/new.py"),
    ):
        result = capture_snapshot(repo, SnapshotSpec(base=base, head=revision, limits=limits))
        assert result.capture.manifest.integrity_status == "partial"
        assert (HEAD, path, reason) in {
            (item.side, item.path, item.reason) for item in result.capture.omissions
        }
        # The unchanged files are there all the same.
        assert {"src/app.py", "tests/test_app.py"} <= set(captured(result, HEAD))


def test_git_metadata_budget_is_bounded(repo):
    with pytest.raises(SnapshotError) as caught:
        capture_snapshot(
            repo,
            SnapshotSpec(base="HEAD", head="HEAD", limits=SnapshotLimits(max_metadata_bytes=1)),
        )
    assert caught.value.code == "metadata_budget"


def test_a_worktree_capture_says_whether_it_differs_from_its_commit(repo):
    def dirty(**spec):
        return capture_snapshot(repo, SnapshotSpec(**spec)).worktree_dirty

    assert dirty() is False
    # A changed mode, a file outside the scope and untracked source left out do not count.
    (repo / "src/helper.py").chmod(0o755)
    write(repo, "notes.md", "draft\n")
    write(repo, "src/scratch.py", "scratch = 1\n")
    assert dirty() is False
    # Untracked source that is read is not in the commit.
    assert dirty(include_untracked=True) is True
    (repo / "src/scratch.py").unlink()
    write(repo, "src/helper.py", "def run():\n    return 2\n")
    assert dirty() is True
    # A commit is never dirty, whatever the working tree holds.
    assert dirty(head="HEAD") is False
    git(repo, "checkout", "--", "src/helper.py")
    (repo / "tests/test_app.py").unlink()
    assert dirty() is True
    # A folder left out on purpose is not compared.
    assert dirty(exclude_paths=("tests",)) is False


def converted_checkout(repo, tmp_path):
    """Files the checkout converts as their attributes ask, and a filter that must not run."""
    marker = tmp_path / "filtered"
    write(repo, ".gitattributes", "*.py text eol=crlf filter=evil\nsrc/app.py ident\n")
    write(repo, "src/app.py", "# $Id$\nfrom .helper import run\n")
    commit(repo)
    for path in ("src/helper.py", "src/app.py"):
        (repo / path).unlink()
        git(repo, "checkout", "--", path)
    git(repo, "config", "filter.evil.clean", f"touch {marker}")
    git(repo, "config", "filter.evil.process", f"touch {marker}")
    git(repo, "config", "core.safecrlf", "true")
    assert (repo / "src/helper.py").read_bytes() == b"def run():\r\n    return 1\r\n"
    assert (repo / "src/app.py").read_bytes().startswith(b"# $Id: ")
    return marker


def test_a_clean_checkout_with_converted_line_endings_is_not_dirty(repo, tmp_path):
    marker = converted_checkout(repo, tmp_path)
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    write(repo, "src/helper.py", "def run():\r\n    return 2\r\n")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True
    # Git converted the bytes; no filter driver of the repository ran.
    assert not marker.exists()


def test_a_file_with_stale_metadata_is_compared_as_git_would_store_it(repo, tmp_path):
    marker = converted_checkout(repo, tmp_path)
    index = repo / ".git" / "index"

    def changed():
        # The index cannot vouch for the files any more, so their bytes are compared.
        later = time.time() + 60
        for path in ("src/helper.py", "src/app.py"):
            os.utime(repo / path, (later, later))
        before = index.read_bytes()
        found = changed_paths(repo, "HEAD", None)
        assert index.read_bytes() == before
        return found

    assert changed() == []
    write(repo, "src/helper.py", "def run():\r\n    return 2\r\n")
    assert changed() == [("M", "src/helper.py")]
    assert not marker.exists()


def test_a_sha256_repository_is_compared_in_its_own_hash(tmp_path):
    repo = tmp_path / "sha256"
    repo.mkdir()
    git(repo, "init", "-q", "--object-format=sha256")
    git(repo, "config", "user.name", "Snapshot Test")
    git(repo, "config", "user.email", "snapshot@example.invalid")
    write(repo, "app.py", "value = 1\n")
    commit(repo)
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    write(repo, "app.py", "value = 2\n")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True


def settle(repo, *paths):
    """Make the index vouch for `paths`, as it does for a checkout made a while ago."""
    earlier = time.time() - 600
    for path in paths:
        os.utime(repo / path, (earlier, earlier))
    git(repo, "update-index", "-q", "--refresh")


def stale(repo, *paths):
    """Leave the index unable to vouch for `paths`, as a tool that touched them does."""
    later = time.time() + 60
    for path in paths:
        os.utime(repo / path, (later, later))


def user_configuration(tmp_path, monkeypatch, autocrlf):
    """The user's own Git configuration, which a capture reads `core.autocrlf` from."""
    if autocrlf is not None:
        path = tmp_path / "user.gitconfig"
        path.write_text(f"[core]\n\tautocrlf = {autocrlf}\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(path))


def test_a_checkout_the_user_configuration_converts_is_not_dirty(repo, tmp_path, monkeypatch):
    # Git for Windows turns CRLF conversion on in its own configuration, outside the
    # repository, and checks files out with CRLF line endings.
    user_configuration(tmp_path, monkeypatch, "true")
    for path in ("src/app.py", "src/helper.py"):
        (repo / path).unlink()
        git(repo, "-c", "core.autocrlf=true", "checkout", "--", path)
    assert (repo / "src/helper.py").read_bytes() == b"def run():\r\n    return 1\r\n"
    assert git(repo, "-c", "core.autocrlf=true", "status", "--porcelain") == b""
    snapshot = capture_snapshot(repo, SnapshotSpec())
    assert snapshot.worktree_dirty is False
    stale(repo, "src/app.py", "src/helper.py")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    assert changed_paths(repo, "HEAD", None) == []
    write(repo, "src/helper.py", "def run():\r\n    return 2\r\n")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True
    assert changed_paths(repo, "HEAD", None) == [("M", "src/helper.py")]


def test_a_file_a_filter_driver_converts_is_clean_while_the_index_vouches_for_it(repo, tmp_path):
    marker = tmp_path / "filtered"
    git(repo, "config", "filter.up.clean", f"touch {marker}; tr a-z A-Z")
    git(repo, "config", "filter.up.smudge", "tr A-Z a-z")
    write(repo, ".gitattributes", "settings/*.py filter=up\n")
    write(repo, "settings/conf.py", "x = 1\n")
    commit(repo)
    (repo / "settings/conf.py").unlink()
    git(repo, "checkout", "--", "settings/conf.py")
    assert git(repo, "show", "HEAD:settings/conf.py") == b"X = 1\n"
    assert (repo / "settings/conf.py").read_bytes() == b"x = 1\n"
    settle(repo, "settings/conf.py")
    assert git(repo, "status", "--porcelain") == b""
    marker.unlink()
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    write(repo, "settings/conf.py", "x = 2\n")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True
    # The index told; the driver, a command of the repository, never ran.
    assert not marker.exists()


def test_converted_files_are_compared_without_a_process_each(repo, monkeypatch):
    from genesis_ci.git_snapshot import _Git

    write(repo, ".gitattributes", "*.py text eol=crlf\n")
    paths = [f"pkg/module_{index}.py" for index in range(12)]
    for index, path in enumerate(paths):
        write(repo, path, f"value = {index}\n")
    commit(repo)
    for path in paths:
        (repo / path).unlink()
    git(repo, "checkout", "--", "pkg")
    assert (repo / paths[0]).read_bytes() == b"value = 0\r\n"
    calls = []
    run = _Git.run

    def counted(self, *args, **options):
        calls.append(args)
        return run(self, *args, **options)

    monkeypatch.setattr(_Git, "run", counted)
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    # With timestamps the index cannot vouch for, the bytes are compared in process.
    stale(repo, *paths)
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    assert changed_paths(repo, "HEAD", None) == []
    assert not [args for args in calls if "hash-object" in args]


def test_without_a_listing_from_git_every_file_is_compared_byte_by_byte(
    repo, tmp_path, monkeypatch
):
    from genesis_ci.git_snapshot import _StoredBlobs

    def refused(self, base):
        raise SnapshotError("metadata_budget", "Git output exceeded its byte budget.")

    converted_checkout(repo, tmp_path)
    monkeypatch.setattr(_StoredBlobs, "listed", refused)
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    (repo / "tests/test_app.py").unlink()
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True


def test_a_capture_builds_what_it_knows_of_its_inputs_once(repo):
    class Counted(tuple):
        reads = 0

        def __iter__(self):
            Counted.reads += 1
            return super().__iter__()

    paths = [f"web/module_{index}.ts" for index in range(40)]
    for path in paths:
        write(repo, path, "export const value = 1;\n")
    commit(repo)
    spec = SnapshotSpec(inputs=[{"path": path, "kind": "code"} for path in paths])
    spec = spec.model_copy(update={"inputs": Counted(spec.inputs)})
    snapshot = capture_snapshot(repo, spec, reads=lambda path: path.endswith(".ts"))
    assert len(snapshot.source.list_files(HEAD)) > len(paths)
    # Not once for every path it considers: an input list can name every file.
    assert Counted.reads < 10


def test_a_converted_file_is_recorded_with_the_digest_of_its_commit(repo, tmp_path):
    from genesis_ci.source_snapshot import content_digest

    converted_checkout(repo, tmp_path)
    snapshot = capture_snapshot(repo, SnapshotSpec())
    assert snapshot.worktree_dirty is False
    # Converted by its line endings, and by `ident`, which only Git can undo.
    assert snapshot.commit_digests == {
        path: content_digest(git(repo, "show", f"HEAD:{path}"))
        for path in ("src/app.py", "src/helper.py")
    }
    # The snapshot itself holds the bytes as read.
    read = {item.path: item.content_digest for item in snapshot.capture.manifest.files}
    assert read["src/helper.py"] == content_digest(b"def run():\r\n    return 1\r\n")
    stale(repo, "src/app.py", "src/helper.py")
    assert capture_snapshot(repo, SnapshotSpec()).commit_digests == snapshot.commit_digests
    assert capture_snapshot(repo, SnapshotSpec(head="HEAD")).commit_digests == {}


@pytest.mark.parametrize(
    ("attributes", "autocrlf", "dirty"),
    [
        ("", None, True),
        ("", "input", False),
        ("*.py text\n*.sh text\n", None, False),
        ("*.py -text\n*.sh -text\n", "true", True),
        ("*.py binary\n*.sh binary\n", "true", True),
    ],
)
def test_line_endings_alone_differ_only_where_git_converts_them(
    repo, tmp_path, monkeypatch, attributes, autocrlf, dirty
):
    from genesis_ci.source_snapshot import content_digest

    user_configuration(tmp_path, monkeypatch, autocrlf)
    write(repo, ".gitattributes", attributes)
    write(repo, "run.sh", "make dist\n")
    commit(repo)
    # Rewritten with CRLF line endings, as an editor set to them does.
    write(repo, "src/helper.py", "def run():\r\n    return 1\r\n")
    write(repo, "run.sh", "make dist\r\n")
    snapshot = capture_snapshot(repo, SnapshotSpec())
    assert snapshot.worktree_dirty is dirty
    committed = content_digest(b"def run():\n    return 1\n")
    assert snapshot.commit_digests == ({} if dirty else {"src/helper.py": committed})
    listed = changed_paths(repo, "HEAD", None)
    assert listed == ([("M", "run.sh"), ("M", "src/helper.py")] if dirty else [])
    # As Git itself compares the content (`git status` may go by the size alone), and
    # the same once the change is staged.
    options = ["-c", f"core.autocrlf={autocrlf}"] if autocrlf else []
    assert bool(git(repo, *options, "diff", "--name-only")) is dirty
    git(repo, *options, "add", "src/helper.py", "run.sh")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is dirty


def test_a_file_git_is_told_not_to_check_is_compared_by_its_bytes(repo):
    git(repo, "update-index", "--assume-unchanged", "src/helper.py", "tests/test_app.py")
    write(repo, "src/helper.py", "def run():\n    return 2\n")
    # Git itself no longer looks at it.
    assert git(repo, "status", "--porcelain") == b""
    snapshot = capture_snapshot(repo, SnapshotSpec())
    assert (snapshot.worktree_dirty, snapshot.commit_digests) == (True, {})
    write(repo, "src/helper.py", "def run():\n    return 1\n")
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is False
    (repo / "tests/test_app.py").unlink()
    assert capture_snapshot(repo, SnapshotSpec()).worktree_dirty is True


def test_a_file_added_while_git_ignores_timestamps_is_compared_by_its_bytes(repo):
    git(repo, "config", "core.ignoreStat", "true")
    write(repo, "src/rates.py", "rate = 1\n")
    commit(repo)
    assert b"h src/rates.py" in git(repo, "ls-files", "-v")
    write(repo, "src/rates.py", "rate = 2\n")
    snapshot = capture_snapshot(repo, SnapshotSpec())
    assert (snapshot.worktree_dirty, snapshot.commit_digests) == (True, {})


def test_a_file_restored_while_it_is_read_is_read_again(repo, monkeypatch):
    from genesis_ci.git_snapshot import _StoredBlobs

    write(repo, "src/helper.py", "def run():\n    return 2\n")
    listed = _StoredBlobs.listed
    restored = []

    def restoring(self, base):
        if not restored:
            # Restored after the file was read, before Git lists what differs.
            git(repo, "checkout", "--", "src/helper.py")
            restored.append(base)
        return listed(self, base)

    monkeypatch.setattr(_StoredBlobs, "listed", restoring)
    snapshot = capture_snapshot(repo, SnapshotSpec())
    # What was read and what is said of it agree.
    assert snapshot.source.read_bytes(HEAD, "src/helper.py") == b"def run():\n    return 1\n"
    assert (snapshot.worktree_dirty, snapshot.commit_digests) == (False, {})


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


@pytest.mark.parametrize(
    ("path", "exclude", "excluded", "on_purpose"),
    [
        (".genesis/edd/refund/evals/s1/tests/test.sh", (), ".genesis", ".genesis"),
        ("services/api/.genesis/edd/x.sh", (), "services/api/.genesis", "services/api/.genesis"),
        (".genesis/flows.yaml", (), None, None),
        (".genesis/flows.yaml", (".genesis",), ".genesis", ".genesis"),
        ("web/node_modules/pkg/index.js", (), "web/node_modules", None),
        ("build/release.sh", (), "build", None),
        ("deploy/env/production.yaml", (), "deploy/env", None),
        ("build/release.sh", ("build",), "build", "build"),
        ("vendor/lib/util.py", ("vendor",), "vendor", "vendor"),
        ("vendored.py", ("vendor",), None, None),
        ("app/core.py", (), None, None),
    ],
)
def test_excluded_by_names_what_every_capture_leaves_out(path, exclude, excluded, on_purpose):
    from genesis_ci.git_snapshot import excluded_by, left_out_by

    spec = SnapshotSpec(exclude_paths=exclude)
    # Only Genesis's own folder and what `--exclude` names are left out by choice: no
    # capture reads a build or dependency folder either, but that is no one's choice.
    assert (excluded_by(path, spec), left_out_by(path, spec)) == (excluded, on_purpose)

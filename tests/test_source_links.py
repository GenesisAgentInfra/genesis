"""Viewer source links must identify published source, never pretend local edits are online."""

import pytest
from genesis_ci.business_map.source_links import github_repository, github_source_links
from genesis_ci.git_snapshot import capture_snapshot
from genesis_contracts.models import EvidenceSide, ReferenceRange
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write


@pytest.mark.parametrize(
    "remote, expected",
    [
        ("git@github.com:org/repo.git", "https://github.com/org/repo"),
        ("ssh://git@github.com/org/repo.git", "https://github.com/org/repo"),
        ("https://token:secret@github.com/org/repo.git", "https://github.com/org/repo"),
        ("https://github.com.attacker.test/org/repo", None),
        ("https://gitlab.com/org/repo", None),
        ("file:///tmp/repo", None),
    ],
)
def test_repository_url_normalization(remote, expected):
    assert github_repository(remote) == expected


def published_repo(repo):
    write(repo, "src/a file.py", "value = 1\n")
    sha = commit(repo)
    git(repo, "remote", "add", "origin", "git@github.com:org/repo.git")
    git(repo, "update-ref", "refs/remotes/origin/main", sha)
    return sha


def evidence(snapshot, side=EvidenceSide.head, path="src/a file.py", line=1):
    return snapshot.source.evidence(side, path, ReferenceRange(start_line=line, end_line=line))


def test_links_pin_both_sides_and_survive_a_later_checkout(source_repo):
    base = published_repo(source_repo)
    write(source_repo, "src/a file.py", "value = 2\n")
    head = commit(source_repo)
    git(source_repo, "update-ref", "refs/remotes/origin/main", head)
    snap = capture_snapshot(source_repo, SnapshotSpec(base=base, head=head))
    refs = (evidence(snap, EvidenceSide.base), evidence(snap))
    write(source_repo, "src/a file.py", "value = 3\n")
    commit(source_repo)
    links = github_source_links(source_repo, snap.capture, refs)
    for ref, sha in zip(refs, (base, head), strict=True):
        assert links[ref.evidence_id] == {
            "url": f"https://github.com/org/repo/blob/{sha}/src/a%20file.py#L1",
            "exact": True,
        }


def test_worktree_changes_link_only_the_committed_file_and_omit_new_files(source_repo):
    sha = published_repo(source_repo)
    write(source_repo, "src/a file.py", "value = 2\nextra = 3\n")
    write(source_repo, "new.py", "new = True\n")
    snap = capture_snapshot(source_repo, SnapshotSpec(base=sha, include_untracked=True))
    refs = (evidence(snap), evidence(snap, line=2), evidence(snap, path="new.py"))
    links = github_source_links(source_repo, snap.capture, refs)
    for ref in refs[:2]:
        assert links[ref.evidence_id] == {
            "url": f"https://github.com/org/repo/blob/{sha}/src/a%20file.py",
            "exact": False,
        }
    assert refs[2].evidence_id not in links


def test_unpublished_commit_and_missing_origin_do_not_produce_links(source_repo):
    base = published_repo(source_repo)
    write(source_repo, "src/a file.py", "value = 2\n")
    head = commit(source_repo)
    snap = capture_snapshot(source_repo, SnapshotSpec(base=base, head=head))
    refs = (evidence(snap),)
    assert github_source_links(source_repo, snap.capture, refs) == {}
    git(source_repo, "remote", "remove", "origin")
    assert github_source_links(source_repo, snap.capture, refs) == {}

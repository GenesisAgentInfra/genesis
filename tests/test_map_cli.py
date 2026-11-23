"""`genesis map prepare` and `genesis map render`: static skeleton end to end, no model."""

import hashlib
import json

import pytest
from genesis_ci.business_map.render import render_html, render_summary
from genesis_ci.cli import app
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle
from test_business_map_contract import SAMPLES
from test_git_snapshot import commit, git, write
from typer.testing import CliRunner

APP = """import typer

cli = typer.Typer()


@cli.command("greet")
def greet(name):
    if not name:
        raise typer.BadParameter("<b>name</b> is required")
    return name
"""


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    monkeypatch.setenv("GENESIS_NO_BROWSER", "1")


def run(*arguments):
    return CliRunner().invoke(app, ["map", *arguments])


def prepared(repo, *extra):
    result = run("prepare", "--repo", str(repo), *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_prepare_writes_a_private_session_with_a_valid_skeleton(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    summary = prepared(source_repo, "--head", "HEAD")
    assert summary["mode"] == "map" and summary["base_revision"] is None
    assert (summary["flows"], summary["entries"]) == (1, {"adapter": 1, "root_heuristic": 0})
    root = source_repo / ".genesis" / "sessions" / summary["session_id"]
    skeleton = BusinessMap.model_validate_json((root / "business-map.json").read_text())
    assert skeleton.snapshot_id == summary["snapshot_id"]
    assert skeleton.flows[0].stage == "skeleton"
    bundle = EvidenceBundle.model_validate_json((root / "evidence-bundle.json").read_text())
    assert {item.evidence_id for item in bundle.excerpts} == {
        ref.evidence_id for ref in skeleton.evidence
    }
    assert (source_repo / ".genesis" / ".gitignore").read_text().split() == ["sessions/", "out/"]
    # The same content gives the same session, so preparing again changes nothing.
    assert prepared(source_repo, "--head", "HEAD") == summary


def test_prepare_reads_the_working_tree_by_default_and_compares_with_a_base(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    write(source_repo, "app.py", APP.replace("return name", "return name.title()"))
    worktree = prepared(source_repo)
    assert worktree["head_revision"].startswith("worktree:")
    compared = prepared(source_repo, "--base", "HEAD")
    assert compared["mode"] == "change" and compared["base_revision"]
    assert compared["session_id"] != worktree["session_id"]


def test_render_publishes_escaped_html_at_a_stable_path(source_repo):
    write(source_repo, "app.py", APP)
    sha = commit(source_repo)
    git(source_repo, "remote", "add", "origin", "git@github.com:org/repo.git")
    git(source_repo, "update-ref", "refs/remotes/origin/main", sha)
    session = prepared(source_repo, "--head", "HEAD")["session_id"]
    result = run("render", "--repo", str(source_repo), "--session", session)
    # A skeleton is a usable partial map.
    assert result.exit_code == 2, result.output
    output = json.loads(result.stdout)
    latest = source_repo / ".genesis" / "out" / "latest"
    assert output["graph"] == str(latest / "graph.html") and output["opened"] is False
    page = (latest / "graph.html").read_text()
    assert "command greet · greet" in page
    assert "&lt;b&gt;name&lt;/b&gt; is required" in page and "<b>name</b>" not in page
    assert "<script" not in page and "http://" not in page and "https://" not in page
    assert "- Flows: 1" in (latest / "summary.md").read_text()
    assert (source_repo / ".genesis" / "out" / session / "graph.html").read_text() == page
    view = (latest / "view.html").read_text()
    payload = json.loads(
        view.split('<script id="genesis-data" type="application/json">', 1)[1].split(
            "</script>", 1
        )[0]
    )
    assert payload["source_links"]
    assert all(
        link["exact"] and link["url"].startswith(f"https://github.com/org/repo/blob/{sha}/app.py#L")
        for link in payload["source_links"].values()
    )


@pytest.mark.parametrize("engine", ["python", "agent"])
def test_a_review_map_says_it_comes_from_a_review(source_repo, engine):
    out = source_repo / ".genesis" / "out"

    def render(session):
        # No flow is described yet: each result is partial, and usable.
        result = run("render", "--repo", str(source_repo), "--session", session)
        assert result.exit_code == 2, result.output

    def published(folder):
        return json.loads((out / folder / "business-map.json").read_text())

    write(source_repo, "app.py", APP)
    commit(source_repo)
    mapped = prepared(source_repo, "--engine", engine, "--head", "HEAD")["session_id"]
    render(mapped)
    assert published("latest")["mode"] == "map"
    write(source_repo, "app.py", APP.replace("return name", "return name.title()"))
    commit(source_repo)
    flags = ("--engine", engine, "--base", "HEAD~1", "--head", "HEAD")
    review = prepared(source_repo, *flags)["session_id"]
    render(review)
    # `latest` is the newest result, a review included; its map says it is one.
    assert published("latest")["mode"] == "change"
    assert (out / "latest" / "change-report.json").is_file()
    assert published(mapped)["mode"] == "map"
    stored = source_repo / ".genesis" / "sessions" / review / "business-map.json"
    assert json.loads(stored.read_text())["mode"] == "change"
    # A session prepared before maps carried `mode` is published by what it is.
    stored.write_text(
        json.dumps({k: v for k, v in json.loads(stored.read_text()).items() if k != "mode"})
    )
    render(review)
    assert published("latest")["mode"] == "change"


def rendered_source(repo, session):
    run("render", "--repo", str(repo), "--session", session)
    text = (repo / ".genesis" / "out" / session / "business-map.json").read_text()
    assert str(repo) not in text
    return json.loads(text)["source"]


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_render_records_the_code_a_map_was_read_from(source_repo):
    write(source_repo, "app.py", APP)
    sha = commit(source_repo)
    session = prepared(source_repo)["session_id"]
    clean = rendered_source(source_repo, session)
    assert clean == {
        "revision": sha,
        "worktree_dirty": False,
        "integrity_status": "complete",
        "files": {"app.py": digest(APP.encode())},
    }
    # The same session renders the same bytes.
    published = source_repo / ".genesis" / "out" / session / "business-map.json"
    first = published.read_bytes()
    assert rendered_source(source_repo, session) == clean and published.read_bytes() == first
    # Neither page carries it: with no GitHub link to make, the commit is not named.
    run("render", "--repo", str(source_repo), "--session", session, "--share")
    for name in ("view.html", "view.share.html"):
        view = (source_repo / ".genesis" / "out" / session / name).read_text()
        assert sha not in view and clean["files"]["app.py"] not in view
    # Uncommitted work that is read is said to be, with the commit it was read on.
    edited = APP.replace("return name", "return name.title()")
    write(source_repo, "app.py", edited)
    summary = prepared(source_repo)
    assert summary["worktree_dirty"] is True
    dirty = rendered_source(source_repo, summary["session_id"])
    assert (dirty["revision"], dirty["worktree_dirty"]) == (sha, True)
    assert dirty["files"] == {"app.py": digest(edited.encode())}
    # A map of a commit reads the commit, whatever the working tree holds.
    committed = rendered_source(source_repo, prepared(source_repo, "--head", "HEAD")["session_id"])
    assert committed == clean


@pytest.mark.parametrize("engine", ["python", "agent"])
def test_a_review_records_the_code_its_map_was_read_from(source_repo, engine):
    write(source_repo, "app.py", APP)
    # Not text at the base, so left out there: the snapshot is partial.
    write(source_repo, "data.py", b"blob = 1\0\n")
    base = commit(source_repo)
    edited = APP.replace("return name", "return name.title()")
    write(source_repo, "app.py", edited)
    write(source_repo, "data.py", "blob = 2\n")
    head = commit(source_repo)
    summary = prepared(source_repo, "--engine", engine, "--base", base, "--head", head)
    assert summary["integrity_status"] == "partial"
    # The map of a review is the head side's: its commit and the files read there.
    assert rendered_source(source_repo, summary["session_id"]) == {
        "revision": head,
        "worktree_dirty": False,
        "integrity_status": "complete",
        "files": {"app.py": digest(edited.encode()), "data.py": digest(b"blob = 2\n")},
    }


def test_the_agent_engine_says_a_committed_file_it_did_not_read_was_removed(source_repo):
    write(source_repo, "a.ts", "export const a = 1;\n")
    write(source_repo, "b.ts", "export const b = 2;\n")
    sha = commit(source_repo)

    def read():
        summary = prepared(source_repo, "--engine", "agent")
        source = rendered_source(source_repo, summary["session_id"])
        assert source["revision"] == sha
        return summary["worktree_dirty"], summary["integrity_status"], list(source["files"])

    # Removed from the index too: Git no longer lists it, yet the commit has it.
    git(source_repo, "rm", "-q", "b.ts")
    assert read() == (True, "complete", ["a.ts"])
    # Removed from the working tree only. Either way the file is gone, not left out, so
    # the snapshot is complete.
    git(source_repo, "reset", "-q", "--", "b.ts")
    assert read() == (True, "complete", ["a.ts"])
    git(source_repo, "checkout", "--", "b.ts")
    assert read() == (False, "complete", ["a.ts", "b.ts"])


def test_a_reader_can_tell_that_a_map_no_longer_matches_the_code(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "README.md", "# App\n")
    first = commit(source_repo)
    source = rendered_source(source_repo, prepared(source_repo)["session_id"])
    write(source_repo, "README.md", "# App, documented\n")
    docs = commit(source_repo)
    write(source_repo, "app.py", APP.replace("return name", "return name.title()"))
    code = commit(source_repo)

    def changed(revision):
        return [
            path
            for path, expected in source["files"].items()
            if digest(git(source_repo, "show", f"{revision}:{path}")) != expected
        ]

    assert source["revision"] == first
    assert changed(first) == [] and changed(docs) == []
    assert changed(code) == ["app.py"]


@pytest.mark.parametrize("engine", ["python", "agent"])
def test_a_map_records_files_as_their_commit_holds_them(source_repo, engine):
    write(source_repo, ".gitattributes", "*.py text eol=crlf\n")
    write(source_repo, "app.py", APP)
    sha = commit(source_repo)
    # A checkout with CRLF line endings, as on Windows: Git converts them back on commit.
    (source_repo / "app.py").unlink()
    git(source_repo, "checkout", "--", "app.py")
    assert b"\r\n" in (source_repo / "app.py").read_bytes()
    worktree = rendered_source(source_repo, prepared(source_repo, "--engine", engine)["session_id"])
    assert (worktree["revision"], worktree["worktree_dirty"]) == (sha, False)
    # The digests are those of the commit, which every clone has, as for a map of it.
    assert worktree["files"]["app.py"] == digest(git(source_repo, "show", f"{sha}:app.py"))
    flags = ("--engine", engine, "--head", "HEAD")
    assert rendered_source(source_repo, prepared(source_repo, *flags)["session_id"]) == worktree


def test_a_session_from_an_earlier_version_renders_without_a_source(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    summary = prepared(source_repo)
    stored = source_repo / ".genesis" / "sessions" / summary["session_id"] / "session.json"
    old = json.loads(stored.read_text())
    del old["worktree_dirty"]
    stored.write_text(json.dumps(old))
    run("render", "--repo", str(source_repo), "--session", summary["session_id"])
    latest = source_repo / ".genesis" / "out" / "latest" / "business-map.json"
    assert "source" not in json.loads(latest.read_text())
    # Preparing again on the same content tells, and the next render records it.
    assert prepared(source_repo)["session_id"] == summary["session_id"]
    assert rendered_source(source_repo, summary["session_id"])["worktree_dirty"] is False


def test_share_mode_leaves_source_excerpts_out(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    session = prepared(source_repo, "--head", "HEAD")["session_id"]
    run("render", "--repo", str(source_repo), "--session", session, "--share")
    latest = source_repo / ".genesis" / "out" / "latest"
    page = (latest / "graph.share.html").read_text()
    # The private page was never written by this render, and is never replaced by it.
    assert not (latest / "graph.html").exists()
    run("render", "--repo", str(source_repo), "--session", session)
    assert "<pre>" in (latest / "graph.html").read_text()
    assert (latest / "graph.share.html").read_text() == page
    assert "app.py:" in page and "<pre>" not in page


def test_unsupported_repository_and_unknown_session_fail_with_a_reason(source_repo):
    write(source_repo, "index.ts", "export const x = 1;\n")
    commit(source_repo)
    result = run("prepare", "--repo", str(source_repo), "--head", "HEAD", "--engine", "python")
    assert result.exit_code == 1
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "unsupported_repository" and ".ts: 1" in error["message"]
    assert not (source_repo / ".genesis").exists()
    missing = run("render", "--repo", str(source_repo), "--session", "ses_0000000000000000")
    assert missing.exit_code == 1
    assert json.loads(missing.stdout)["error"]["code"] == "not_found"
    assert run("render", "--repo", str(source_repo), "--session", "../x").exit_code == 1


@pytest.mark.parametrize("name", ["complete", "skeleton", "partial"])
def test_renderer_handles_every_map_sample(name):
    data = BusinessMap.model_validate_json((SAMPLES / f"expense-{name}.json").read_text())
    page = render_html(data)
    assert page.startswith("<!doctype html>") and "<script" not in page
    assert all(flow.name in page for flow in data.flows)
    assert render_summary(data).startswith("# Genesis map")


def test_renderer_shows_changes_coverage_and_links():
    change = SAMPLES / "change"
    head = BusinessMap.model_validate_json((change / "business-map.json").read_text())
    report = ChangeReport.model_validate_json((change / "change-report.json").read_text())
    bundle = EvidenceBundle.model_validate_json((change / "evidence-bundle.json").read_text())
    page = render_html(head, bundle, report)
    assert "amount &gt;= THRESHOLD" in page and "amount &gt; THRESHOLD" in page
    assert "reached only" in page and "no execution data collected" in page
    assert "How flows connect" in page and "state handoff" in page
    assert "Risk findings" in page and "<pre>" in page
    assert "tests: reached only" in render_summary(head, report)


PLACES = {
    "step": {"status": "projected", "flow_id": "flow_submit_report", "step_id": "step_choose_path"},
    "removed step": {
        "status": "removed_step",
        "flow_id": "flow_submit_report",
        "removed_step": {"step_id": "step_gone", "name": "旧的分流"},
    },
    "off the map": {"status": "unassigned", "reason": "No entry on the map reaches this code."},
}


def told_alike(place, **tests):
    """The change sample with both changes at one place, told in the threshold's words."""
    change = SAMPLES / "change"
    head = BusinessMap.model_validate_json((change / "business-map.json").read_text())
    data = json.loads((change / "change-report.json").read_text())
    first, other = data["changes"]
    first["projection"] = other["projection"] = place
    other.update({"explanation": first["explanation"], "tests": first["tests"], **tests})
    return head, ChangeReport.model_validate(data), first["explanation"]["summary"]


@pytest.mark.parametrize("place", PLACES.values(), ids=PLACES.keys())
def test_an_explanation_shared_by_changes_at_one_place_is_printed_once(place):
    head, report, words = told_alike(place)
    summary = render_summary(head, report)
    assert summary.count(words) == 1 and summary.count("tests: head::") == 1
    assert "covers 2 changes: src/expense/api.py:14, src/expense/review.py:7-10" in summary
    # Each change keeps its own code and anchor; the words and tests are shown once.
    page = render_html(head, None, report)
    assert page.count('class="delta"') == 2 and page.count(words) == 1
    assert 'id="chg_review_loop"' in page and "while True" in page
    assert page.count("Explained together with the change above.") == 1


def test_changes_told_alike_but_judged_differently_stay_apart():
    unknown = {"verdict": "unknown", "basis": [], "execution_data": "not_collected", "note": "x"}
    head, report, words = told_alike(PLACES["step"], tests=unknown)
    summary = render_summary(head, report)
    assert summary.count(words) == 2 and "covers" not in summary
    page = render_html(head, None, report)
    assert page.count(words) == 2 and "Explained together" not in page


def test_a_source_file_of_several_thousand_lines_is_analyzed(source_repo):
    from genesis_ci.business_map.session import load_facts
    from genesis_ci.git_snapshot import capture_snapshot
    from genesis_ci.python import extract_python
    from genesis_contracts.snapshot import SnapshotSpec

    # Larger than the report pipeline's node limit, like the core modules of real projects.
    handlers = "".join(
        f"def handler_{index}(value):\n    if value > {index}:\n        return compute(value, {index})\n"
        f"    return value\n\n\n"
        for index in range(2500)
    )
    write(source_repo, "big.py", "def compute(a, b):\n    return a + b\n\n\n" + handlers)
    write(source_repo, "app.py", APP)
    commit(source_repo)
    summary = prepared(source_repo, "--head", "HEAD")
    assert summary["files_unsupported"] == [] and summary["files_analyzed"] == 2
    facts = load_facts(source_repo, summary["session_id"])
    assert sum(1 for item in facts.symbols if item.path == "big.py") > 2500
    # The report pipeline keeps its own limit and now says which one was hit.
    plain = extract_python(capture_snapshot(source_repo, SnapshotSpec(head="HEAD")))
    skipped = [item for item in plain.analysis.coverage if item.syntax.status != "analyzed"]
    assert [(item.path, item.syntax.reason) for item in skipped] == [
        ("big.py", "File not analyzed: Python node budget exceeded")
    ]


def test_a_larger_repository_is_prepared_in_worker_processes(source_repo, monkeypatch):
    from genesis_ci.business_map import session

    for index in range(6):
        write(
            source_repo,
            f"pkg/mod_{index}.py",
            f"def step_{index}(value):\n    if value:\n        return value + {index}\n    return 0\n",
        )
    write(source_repo, "pkg/__init__.py", "")
    write(source_repo, "app.py", APP)
    commit(source_repo)
    single = prepared(source_repo, "--head", "HEAD")
    root = source_repo / ".genesis" / "sessions" / single["session_id"]
    before = {name: (root / name).read_text() for name in ("facts.json", "business-map.json")}
    # Lower the threshold instead of creating dozens of files.
    monkeypatch.setattr(session, "PARALLEL_FILES", 2)
    assert session._workers(type("F", (), {"path": "a.py"})() for _ in range(3)) > 1
    again = prepared(source_repo, "--head", "HEAD")
    assert again["session_id"] == single["session_id"]
    assert {name: (root / name).read_text() for name in before} == before
    # The setting wins over the size of the repository.
    monkeypatch.setenv("GENESIS_WORKERS", "1")
    assert session._workers(type("F", (), {"path": "a.py"})() for _ in range(500)) == 1


def test_prepare_says_when_most_source_is_in_another_language(source_repo):
    write(source_repo, "app.py", APP)
    for index in range(3):
        write(source_repo, f"web/src/page{index}.ts", f"export const page{index} = {index}\n")
    write(source_repo, "web/src/App.tsx", "export function App() { return null }\n")
    commit(source_repo)
    summary = prepared(source_repo)
    assert summary["engine"] == "python"
    other = summary["other_languages"]
    assert other["python_files"] == 1 and other["other_files"] == 4
    assert other["by_type"] == {".ts": 3, ".tsx": 1}
    assert "--engine agent" in other["note"]


def test_prepare_leaves_the_note_out_while_python_is_the_main_language(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "tools/helper.py", "def helper():\n    return 1\n")
    write(source_repo, "scripts/build.sh", "echo build\n")
    commit(source_repo)
    other = prepared(source_repo)["other_languages"]
    assert other == {
        "scope": "project",
        "python_files": 2,
        "other_files": 1,
        "by_type": {".sh": 1},
    }


def test_prepare_on_a_python_only_project_reports_no_other_language(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    assert "other_languages" not in prepared(source_repo)


def test_a_review_judges_by_the_files_it_changes(source_repo):
    write(source_repo, "app.py", APP)
    for index in range(4):
        write(source_repo, f"web/src/page{index}.ts", f"export const page{index} = {index}\n")
    commit(source_repo)
    # A backend change in a project that is mostly frontend: Python is the right way.
    write(source_repo, "app.py", APP + "\n\ndef extra():\n    return 2\n")
    commit(source_repo)
    assert "other_languages" not in prepared(source_repo, "--base", "HEAD~1", "--head", "HEAD")
    # A frontend change: most of what the review is about is not Python.
    write(source_repo, "web/src/page0.ts", "export const page0 = 10\n")
    write(source_repo, "web/src/page1.ts", "export const page1 = 11\n")
    commit(source_repo)
    other = prepared(source_repo, "--base", "HEAD~1", "--head", "HEAD")["other_languages"]
    assert other["scope"] == "changed"
    assert (other["python_files"], other["other_files"]) == (0, 2)
    assert "--engine agent" in other["note"]


EVAL = "#!/bin/sh\nexit 0\n"


def test_other_languages_counts_only_what_a_snapshot_can_read(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "lib/helper.py", "def helper():\n    return 1\n")
    # Genesis EDD keeps its evals in Genesis's own folder, which no snapshot reads.
    for name in ("test.sh", "genesis.sh", "fixtures/refund.sh"):
        write(source_repo, f".genesis/edd/refund/evals/s1/tests/{name}", EVAL)
    write(source_repo, ".genesis/edd/refund/evals/s1/tests/shared/observe.py", "OK = 1\n")
    for index in range(3):
        write(source_repo, f"vendor/tools/run{index}.sh", EVAL)
    commit(source_repo)
    other = prepared(source_repo)["other_languages"]
    assert (other["python_files"], other["other_files"]) == (2, 3)
    assert "--engine agent" in other["note"]
    # A folder left out on purpose is not counted either.
    assert "other_languages" not in prepared(source_repo, "--exclude", "vendor")
    # Nor in a review whose change adds evals beside a change to the Python code.
    write(source_repo, "app.py", APP + "\n\ndef extra():\n    return 2\n")
    for index in range(3):
        write(source_repo, f".genesis/edd/refund/evals/s2/tests/check{index}.sh", EVAL)
    write(source_repo, "vendor/tools/run0.sh", "#!/bin/sh\nexit 1\n")
    commit(source_repo)
    review = prepared(source_repo, "--base", "HEAD~1", "--head", "HEAD", "--exclude", "vendor")
    assert "other_languages" not in review


def change_report(repo, summary):
    root = repo / ".genesis" / "sessions" / summary["session_id"]
    return ChangeReport.model_validate_json((root / "change-report.json").read_text())


def left_out_note(report):
    [note] = [item for item in report.limitations if item.code == "changed_files_left_out"]
    return note.message


def test_the_agent_engine_freezes_nothing_a_snapshot_leaves_out(source_repo):
    write(source_repo, "web/app.ts", "export const app = 1\n")
    write(source_repo, ".genesis/edd/refund/evals/s1/tests/test.sh", EVAL)
    write(source_repo, "vendor/lib.ts", "export const lib = 1\n")
    commit(source_repo)
    summary = prepared(source_repo, "--engine", "agent", "--exclude", "vendor")
    # Asking for a file the snapshot refuses would mark it partial for no missing input.
    assert summary["integrity_status"] == "complete"
    assert (summary["files"], summary["file_types"]) == (1, {".ts": 1})
    # A review counts the changed files in those folders instead of listing them.
    write(source_repo, "web/app.ts", "export const app = 2\n")
    write(source_repo, "README.md", "Web app\n")
    write(source_repo, ".genesis/edd/refund/evals/s2/tests/test.sh", EVAL)
    write(source_repo, "vendor/lib.ts", "export const lib = 2\n")
    commit(source_repo)
    review = prepared(
        source_repo,
        "--engine",
        "agent",
        "--base",
        "HEAD~1",
        "--head",
        "HEAD",
        "--exclude",
        "vendor",
    )
    assert review["integrity_status"] == "complete" and review["changed_files_not_analyzed"] == 1
    report = change_report(source_repo, review)
    assert [item.path for item in report.unanalyzed_changes] == ["README.md"]
    # `.genesis/` also holds the `.gitignore` the first `prepare` wrote, committed since.
    assert left_out_note(report) == (
        "3 changed files in `.genesis/` or in folders passed to `--exclude`: not analyzed "
        "(.genesis: 2, vendor: 1)."
    )


@pytest.mark.parametrize("engine", ["python", "agent"])
def test_a_review_lists_the_changed_files_no_one_chose_to_leave_out(source_repo, engine):
    # No run reads a build, dependency or cache folder, yet no one chose to leave it
    # out, and a change there can matter: a release script, a deployment setting.
    listed = {"build/release.sh": "make dist\n", "deploy/env/production.yaml": "replicas: 2\n"}
    # Genesis's own folder and a folder passed to `--exclude` are counted instead.
    counted = {".genesis/edd/refund/evals/s1/tests/test.sh": EVAL, "vendor/tools/run.sh": EVAL}
    write(source_repo, "app.py", APP)
    for path, text in {**listed, **counted}.items():
        write(source_repo, path, text)
    commit(source_repo)
    write(source_repo, "app.py", APP.replace("return name", "return name.title()"))
    for path, text in {**listed, **counted}.items():
        write(source_repo, path, text + "# changed\n")
    commit(source_repo)
    flags = ("--engine", engine, "--base", "HEAD~1", "--head", "HEAD", "--exclude", "vendor")
    review = prepared(source_repo, *flags)
    assert review["changed_files_not_analyzed"] == 2
    report = change_report(source_repo, review)
    assert [item.path for item in report.unanalyzed_changes] == list(listed)
    assert left_out_note(report) == (
        "2 changed files in `.genesis/` or in folders passed to `--exclude`: not analyzed "
        "(.genesis: 1, vendor: 1)."
    )


def test_a_changed_file_in_a_folder_no_run_reads_says_why_it_was_not_analyzed(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "build/tool.py", "def run():\n    return 1\n")
    write(source_repo, "Dockerfile", "FROM python:3.12\n")
    commit(source_repo)
    write(source_repo, "build/tool.py", "def run():\n    return 2\n")
    write(source_repo, "Dockerfile", "FROM python:3.13\n")
    report = change_report(source_repo, prepared(source_repo, "--base", "HEAD"))
    reasons = {item.path: item.reason for item in report.unanalyzed_changes}
    # Python, yet in a build folder, which no run reads: not a language Genesis lacks.
    assert reasons == {
        "Dockerfile": "Not a supported source language; not analyzed.",
        "build/tool.py": "In `build/`: Genesis reads no dependency, build or cache folder; "
        "not analyzed.",
    }
    codes = {item.code: item.message for item in report.limitations}
    assert codes["changed_files_outside_languages"].startswith("1 changed file outside")
    assert codes["changed_files_not_read"].startswith("1 changed file that no snapshot")


def test_a_new_file_in_a_folder_no_run_reads_is_named_like_a_changed_one(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "build/tool.py", "def run():\n    return 1\n")
    commit(source_repo)
    write(source_repo, "build/tool.py", "def run():\n    return 2\n")
    write(source_repo, "build/added.sh", "make dist\n")
    # Left out unless asked for, as any untracked file, and named.
    report = change_report(source_repo, prepared(source_repo, "--base", "HEAD"))
    assert [item.path for item in report.unanalyzed_changes] == ["build/tool.py"]
    [note] = [item for item in report.limitations if item.code == "untracked_files_left_out"]
    assert "build/added.sh" in note.message
    # Listed as added with the changes when untracked files are included.
    summary = prepared(source_repo, "--base", "HEAD", "--include-untracked")
    listed = {
        item.path: item.change for item in change_report(source_repo, summary).unanalyzed_changes
    }
    assert listed == {"build/added.sh": "added", "build/tool.py": "modified"}


def test_untracked_caches_git_does_not_ignore_do_not_crowd_out_the_changes(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "build/tool.py", "def run():\n    return 1\n")
    write(source_repo, "docs/feed.md", "feed\n")
    commit(source_repo)
    write(source_repo, "build/tool.py", "def run():\n    return 2\n")
    write(source_repo, "docs/feed.md", "feed, edited\n")
    write(source_repo, "build/added.sh", "make dist\n")
    # Made by running the code, in folders no file of the project is in.
    for index in range(130):
        write(source_repo, f".venv/lib/site-packages/pkg/m{index:03}.py", "x = 1\n")
    write(source_repo, "app/__pycache__/app.cpython-312.pyc", b"\x00compiled")
    write(source_repo, "build/__pycache__/tool.cpython-312.pyc", b"\x00compiled")
    summary = prepared(source_repo, "--base", "HEAD")
    assert (summary["untracked_left_out"], summary["untracked_by_folder"]) == (1, 132)
    notes = {item.code: item for item in change_report(source_repo, summary).limitations}
    note = notes["untracked_files_left_out"]
    assert note.message.startswith("1 untracked file left out") and "build/added.sh" in note.message
    # Counted by the folder each lies in, not listed.
    counted = notes["untracked_files_by_folder"]
    assert "(.venv: 130, app/__pycache__: 1, build/__pycache__: 1)" in counted.message
    assert not counted.affects_completeness
    summary = prepared(source_repo, "--base", "HEAD", "--include-untracked")
    listed = [item.path for item in change_report(source_repo, summary).unanalyzed_changes]
    assert listed == ["build/tool.py", "docs/feed.md", "build/added.sh"]
    assert summary["untracked_by_folder"] == 132


@pytest.mark.parametrize("flags", [(), ("--include-untracked",)])
def test_new_project_folders_named_like_a_build_folder_are_counted_by_folder(source_repo, flags):
    write(source_repo, "app/main.py", APP)
    commit(source_repo)
    # New folders of the project, not made by running it, with a build or env name.
    write(source_repo, "app/build/__init__.py", "")
    write(source_repo, "app/build/runner.py", "def run(job):\n    if job:\n        return 1\n")
    write(source_repo, "config/env/production.cfg", "debug = false\n")
    summary = prepared(source_repo, "--base", "HEAD", *flags)
    assert summary["untracked_by_folder"] == 3
    report = change_report(source_repo, summary)
    [note] = [item for item in report.limitations if item.code == "untracked_files_by_folder"]
    assert note.message.startswith("3 untracked files in dependency, build or cache folders")
    assert "(app/build: 2, config/env: 1)" in note.message


def test_the_changes_are_listed_before_new_files_when_the_list_is_cut(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "docs/feed.md", "feed\n")
    commit(source_repo)
    write(source_repo, "docs/feed.md", "feed, edited\n")
    for index in range(120):
        write(source_repo, f"assets/icon{index:03}.svg", "<svg/>\n")
    summary = prepared(source_repo, "--base", "HEAD", "--include-untracked")
    report = change_report(source_repo, summary)
    listed = [item.path for item in report.unanalyzed_changes]
    assert len(listed) == 100 and listed[0] == "docs/feed.md"
    codes = {item.code: item.message for item in report.limitations}
    assert codes["changed_files_outside_languages"].startswith("121 changed files")


@pytest.mark.parametrize("engine", ["python", "agent"])
def test_a_review_of_uncommitted_work_counts_new_files_left_out_on_purpose(source_repo, engine):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    write(source_repo, "app.py", APP.replace("return name", "return name.title()"))
    # New evals in Genesis's own folder and a new file in a folder left out on purpose.
    for name in ("test.sh", "fixtures/refund.sh"):
        write(source_repo, f".genesis/edd/refund/evals/s1/tests/{name}", EVAL)
    write(source_repo, "scratch/try.py", "def attempt():\n    return 1\n")
    flags = ("--engine", engine, "--base", "HEAD", "--exclude", "scratch")
    expected = (
        "3 changed files in `.genesis/` or in folders passed to `--exclude`: not analyzed "
        "(.genesis: 2, scratch: 1)."
    )
    first = prepared(source_repo, *flags)
    # The `.gitignore` the first run writes there is Genesis's own, not part of the change.
    assert left_out_note(change_report(source_repo, first)) == expected
    # Nor is what Genesis keeps there later, which Git ignores: sessions, rendered pages.
    write(source_repo, ".genesis/out/latest/summary.md", "# Summary\n")
    assert (source_repo / ".genesis" / "sessions" / first["session_id"]).is_dir()
    for extra in ((), ("--include-untracked",)):
        report = change_report(source_repo, prepared(source_repo, *flags, *extra))
        assert left_out_note(report) == expected and not report.unanalyzed_changes


def test_size_counts_no_file_in_genesis_own_folder(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, ".genesis/edd/refund/evals/s1/tests/shared/observe.py", "OK = 1\n")
    commit(source_repo)
    write(source_repo, "app.py", APP + "\n")
    write(source_repo, ".genesis/edd/refund/evals/s1/tests/shared/observe.py", "OK = 2\n")
    commit(source_repo)
    result = run("size", "--repo", str(source_repo), "--base", "HEAD~1", "--head", "HEAD")
    size = json.loads(result.stdout)
    assert (size["source_files"], size["changed_source_files"]) == (1, 1)
    assert size["largest_folders"] == {".": 1}


def test_size_counts_the_files_prepare_would_read_without_reading_them(source_repo):
    write(source_repo, "app.py", APP)
    write(source_repo, "lib/helper.py", "def helper():\n    return 1\n")
    commit(source_repo)
    write(source_repo, "lib/helper.py", "def helper():\n    return 2\n")
    commit(source_repo)
    result = run("size", "--repo", str(source_repo))
    assert result.exit_code == 0, result.output
    size = json.loads(result.stdout)
    assert (size["engine"], size["mode"], size["source_files"]) == ("python", "map", 2)
    assert size["over_limit"] is False and size["tell_user"] is False
    review = json.loads(
        run("size", "--repo", str(source_repo), "--base", "HEAD~1", "--head", "HEAD").stdout
    )
    assert (review["mode"], review["changed_source_files"]) == ("change", 1)
    over = json.loads(run("size", "--repo", str(source_repo), "--max-files", "1").stdout)
    assert over["over_limit"] is True and over["tell_user"] is True
    assert "--max-files" in over["note"]
    assert not (source_repo / ".genesis").exists()


def test_size_leaves_out_the_files_prepare_leaves_out(source_repo):
    write(source_repo, "app.py", APP)
    for index in range(3):
        write(source_repo, f"vendor/lib{index}.py", f"def lib_{index}():\n    return {index}\n")
    # No snapshot reads these: Genesis's own folder, build output and a secret folder.
    write(source_repo, ".genesis/edd/evals/case-1/observe.py", "def observe():\n    return 1\n")
    write(source_repo, "build/lib/app.py", APP)
    write(source_repo, ".ssh/helper.py", "def helper():\n    return 1\n")
    commit(source_repo)

    def size(*extra):
        result = run("size", "--repo", str(source_repo), *extra)
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    whole = size()
    assert whole["largest_folders"] == {"vendor": 3, ".": 1}
    assert whole["source_files"] == prepared(source_repo, "--head", "HEAD")["files_analyzed"] == 4
    narrowed = size("--exclude", "vendor/lib0.py", "--exclude", "vendor")
    excluded = prepared(source_repo, "--head", "HEAD", "--exclude", "vendor")
    assert narrowed["source_files"] == excluded["files_analyzed"] == 1
    assert narrowed["largest_folders"] == {".": 1}
    # Leaving a folder out is one of the two ways under the limit that the note offers.
    over = size("--max-files", "2")
    assert over["over_limit"] is True and "--exclude" in over["note"]
    assert size("--max-files", "2", "--exclude", "vendor")["over_limit"] is False
    write(source_repo, "app.py", APP + "\n\ndef extra():\n    return 2\n")
    write(source_repo, "vendor/lib0.py", "def lib_0():\n    return 10\n")
    write(source_repo, ".genesis/edd/evals/case-1/observe.py", "def observe():\n    return 2\n")
    commit(source_repo)
    review = size("--base", "HEAD~1", "--head", "HEAD")
    assert (review["source_files"], review["changed_source_files"]) == (4, 2)
    review = size("--base", "HEAD~1", "--head", "HEAD", "--exclude", "vendor")
    assert (review["source_files"], review["changed_source_files"]) == (1, 1)
    # A path `prepare` refuses is refused the same way.
    for command in ("size", "prepare"):
        refused = run(command, "--repo", str(source_repo), "--exclude", "vendor/")
        assert refused.exit_code == 1, refused.output
        assert json.loads(refused.stdout)["error"]["code"] == "invalid_input"


def test_size_chooses_the_engine_prepare_chooses(source_repo):
    for index in range(2):
        write(source_repo, f"web/page{index}.ts", f"export const page{index} = {index}\n")
    # Python that only Genesis's own folder holds does not make a Python project.
    write(source_repo, ".genesis/edd/evals/case-1/observe.py", "def observe():\n    return 1\n")
    commit(source_repo)
    size = json.loads(run("size", "--repo", str(source_repo)).stdout)
    summary = prepared(source_repo, "--head", "HEAD")
    assert (size["engine"], size["source_files"]) == (summary["engine"], summary["files"])
    assert (size["engine"], size["source_files"]) == ("agent", 2)


def test_size_counts_the_new_files_a_review_of_uncommitted_work_reads(source_repo):
    from genesis_ci.snapshot_store import load_snapshot

    write(source_repo, "app.py", APP)
    commit(source_repo)
    write(source_repo, "app.py", APP + "\n\ndef extra():\n    return 2\n")
    for index in range(2):
        write(source_repo, f"lib/new{index}.py", f"def new_{index}():\n    return {index}\n")
    # New files no run reads: one in Genesis's own folder, one in a folder left out.
    write(source_repo, ".genesis/edd/evals/case-1/observe.py", "def observe():\n    return 1\n")
    write(source_repo, "scratch/try.py", "def attempt():\n    return 1\n")
    flags = ("--base", "HEAD", "--exclude", "scratch")
    for extra, counts in (((), (1, 1)), (("--include-untracked",), (3, 3))):
        result = run("size", "--repo", str(source_repo), *flags, *extra)
        assert result.exit_code == 0, result.output
        size = json.loads(result.stdout)
        assert (size["source_files"], size["changed_source_files"]) == counts
        review = prepared(source_repo, *flags, *extra)
        root = source_repo / ".genesis" / "sessions" / review["session_id"]
        changed = load_snapshot(root / "snapshot").capture.file_diff.changes
        # Counted as `prepare` reads them: the new files only when it is told to.
        assert (review["files_analyzed"], len(changed)) == counts


def test_size_takes_every_option_prepare_takes_to_choose_files():
    from typer.main import get_command

    commands = get_command(app).commands["map"].commands

    def options(name):
        # Read from the command itself: its help is cut to the width of the terminal.
        return {option for param in commands[name].params for option in param.opts}

    # The skill runs `size`, then `prepare`, with the same flags. Only the engine, which
    # reads the files `prepare` freezes, and the map whose entries a session starts
    # from are not about which files those are.
    chosen = options("prepare") - {"--engine", "--entries-from"}
    assert "--exclude" in chosen and chosen <= options("size")


def test_files_a_limit_keeps_out_are_named_and_make_the_result_partial(source_repo):
    write(source_repo, "app.py", APP)
    for index in range(3):
        write(source_repo, f"lib/mod{index}.py", f"def value_{index}():\n    return {index}\n")
    commit(source_repo)
    summary = prepared(source_repo, "--max-files", "2")
    missing = summary["files_over_size_limit"]
    assert missing["total"] == 2 and missing["by_reason"] == {"count_budget": 2}
    assert missing["file_limit"] == 2 and len(missing["files"]) == 2
    rendered = run("render", "--repo", str(source_repo), "--session", summary["session_id"])
    assert rendered.exit_code == 2, rendered.output
    assert json.loads(rendered.stdout)["analysis_status"] == "partial"
    text = (source_repo / ".genesis/out/latest/summary.md").read_text(encoding="utf-8")
    assert "2 source files were not read" in text and "--max-files" in text


def test_a_run_given_a_higher_file_limit_reads_its_own_snapshot_back(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    summary = prepared(source_repo, "--max-files", "60000")
    assert "files_over_size_limit" not in summary
    rendered = run("render", "--repo", str(source_repo), "--session", summary["session_id"])
    assert rendered.exit_code in (0, 2), rendered.output
    assert (
        run("status", "--repo", str(source_repo), "--session", summary["session_id"]).exit_code == 0
    )


def test_size_refuses_a_folder_outside_git_and_a_repository_with_no_commit(tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    write(folder, "app.py", APP)
    outside = run("size", "--repo", str(folder))
    assert outside.exit_code == 1
    assert json.loads(outside.stdout)["error"]["code"] == "git_read_failed"
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q")
    write(empty, "app.py", APP)
    fresh = run("size", "--repo", str(empty))
    assert fresh.exit_code == 1
    error = json.loads(fresh.stdout)["error"]
    assert error["code"] == "revision_unavailable" and "no commit yet" in error["message"]


def test_the_viewer_sample_script_imports_what_it_uses():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "viewer/scripts/sample_from_session.py"
    spec = importlib.util.spec_from_file_location("sample_from_session", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)

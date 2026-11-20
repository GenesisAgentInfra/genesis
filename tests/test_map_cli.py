"""`genesis map prepare` and `genesis map render`: static skeleton end to end, no model."""

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

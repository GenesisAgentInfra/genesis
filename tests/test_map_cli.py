"""`genesis map prepare` and `genesis map render`: static skeleton end to end, no model."""

import json

import pytest
from genesis_ci.business_map.render import render_html, render_summary
from genesis_ci.cli import app
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle
from test_business_map_contract import SAMPLES
from test_git_snapshot import commit, write
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
    commit(source_repo)
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
    result = run("prepare", "--repo", str(source_repo), "--head", "HEAD")
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

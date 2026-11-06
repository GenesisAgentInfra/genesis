"""User-facing review layout over the frozen public report/local-analysis seam."""

import json
import shutil
from pathlib import Path

import pytest
from genesis_ci.cli import app
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_ci.report import assemble_report, render_markdown, render_review_markdown
from genesis_ci.snapshot import FrozenSnapshotReader
from genesis_contracts.models import (
    AnalysisRequest,
    LocalAnalysis,
    SemanticAnalysisResponse,
    SourceExcerpt,
)
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write
from typer.testing import CliRunner


def review_fixture(name="normal-five-sections"):
    root = Path(__file__).resolve().parents[1] / "fixtures" / name
    data = json.loads((root / "semantic.json").read_text())
    local = LocalAnalysis.model_validate(data["local_analysis"])
    report = assemble_report(
        local,
        AnalysisRequest.model_validate(data["request"]),
        SemanticAnalysisResponse.model_validate(data["semantic_response"]),
    )
    reader = FrozenSnapshotReader.from_directory(root, local.snapshot, local.evidence)
    return local, report, reader


def test_review_groups_explicit_flow_links_and_keeps_unassigned_findings_and_all_five_sections():
    local, report, _ = review_fixture()
    before = report.model_dump_json()
    markdown = render_review_markdown(report, local)
    flow, unassigned = markdown.split("## 未归属具体流程", 1)
    assert "## 流程：提交报告" in flow
    assert "F-SEM-TEST" in flow
    assert "F-SEM-BEHAVIOR" not in flow
    assert "F-SEM-BEHAVIOR" in unassigned
    assert "F-SEM-CLAIM" in unassigned
    for text in (flow, unassigned):
        for title in (
            "业务变化与意图",
            "受影响流程与路径",
            "成本、等待与失败风险",
            "验收要点与已有测试",
            "验证建议",
        ):
            assert f"### {title}" in text
    assert "user_intent" in markdown
    assert "agent_claim" in markdown
    assert "semantic_inference" in markdown
    assert "代码与测试未执行" in markdown
    assert report.model_dump_json() == before


def test_review_links_to_frozen_evidence_and_compares_versions_without_embedding_source():
    local, report, reader = review_fixture()
    markdown = render_review_markdown(report, local)
    assert "## 冻结版本前后对照" in markdown
    assert "不推断函数对应" in markdown
    assert "| 路径 / 类型 | base 证据 | head 证据 |" in markdown
    assert report.scope.base_revision in markdown
    assert report.scope.head_revision in markdown
    for ref in report.evidence:
        assert f"](#evidence-{ref.evidence_id})" in markdown
        assert f'<a id="evidence-{ref.evidence_id}"></a>' in markdown
        assert ref.snippet_digest in markdown
    code = next(ref for ref in report.evidence if ref.kind == "code" and ref.side == "head")
    assert reader.read_excerpt(code.evidence_id).text not in markdown


def test_source_appendix_uses_verified_frozen_text_after_the_repository_is_removed(source_repo):
    write(source_repo, "app.py", 'def submit():\n    return "old-frozen-result"\n')
    base = commit(source_repo)
    write(source_repo, "app.py", 'def submit():\n    return "new-frozen-result"\n')
    captured = capture_snapshot(source_repo, SnapshotSpec(base=base))
    result = analyze_snapshot(captured)
    reader = result.reader
    shutil.rmtree(source_repo)
    plain = render_review_markdown(result.report, result.local)
    with_source = render_review_markdown(result.report, result.local, reader=reader)
    assert "包含冻结源码与意图原文" in with_source
    assert 'return "old-frozen-result"' in with_source
    assert 'return "new-frozen-result"' in with_source
    assert 'return "old-frozen-result"' not in plain
    assert 'return "new-frozen-result"' not in plain


def test_review_rejects_mislabelled_versions_and_tampered_source_before_publishing():
    local, report, reader = review_fixture()
    wrong = report.model_copy(
        update={"scope": report.scope.model_copy(update={"head_revision": "another-revision"})}
    )
    with pytest.raises(ValueError, match="frozen"):
        render_review_markdown(wrong, local)

    class TamperedReader:
        def evidence_catalog(self):
            return reader.evidence_catalog()

        def read_excerpt(self, evidence_id):
            return SourceExcerpt(evidence_id=evidence_id, text="not the frozen source")

    with pytest.raises(ValueError, match="digest"):
        render_review_markdown(report, local, reader=TamperedReader())


@pytest.mark.parametrize(
    "name",
    (
        "normal-five-sections",
        "dynamic-call-unresolved",
        "missing-intent-and-tests",
        "flow-entry-invalid",
    ),
)
def test_review_retains_partial_scope_and_legacy_exports_remain_byte_identical(name):
    local, report, _ = review_fixture(name)
    expected = Path(__file__).resolve().parents[1] / "fixtures" / name / "report.md"
    assert render_markdown(report) == expected.read_text()
    markdown = render_review_markdown(report, local)
    for finding in report.findings:
        assert finding.finding_id in markdown
    for limitation in report.limitations:
        assert limitation.code in markdown
    if name == "normal-five-sections":
        assert "未知，不按零处理" in markdown
        assert "No runtime measurements or external implementation supplied" in markdown
        assert "Actual latency and failure rate" in markdown
    if name == "missing-intent-and-tests":
        assert "insufficient_context" in markdown
        assert "partial" in markdown
    if name == "flow-entry-invalid":
        assert "unsupported" in markdown


def test_untrusted_finding_text_cannot_create_external_image_or_html_links():
    local, report, _ = review_fixture()
    injected = report.findings[0].model_copy(
        update={
            "statement": '![load](https://example.invalid/pixel) <img src="https://example.invalid/other">'
        }
    )
    report = report.model_copy(update={"findings": (injected, *report.findings[1:])})
    markdown = render_review_markdown(report, local)
    assert "![load](" not in markdown
    assert "<img " not in markdown
    assert "&lt;img " in markdown


def test_missing_flow_map_cli_groups_discovered_entries_without_inventing_named_flow(
    source_repo, tmp_path
):
    write(source_repo, "app.py", "def submit():\n    return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def submit():\n    return 2\n")
    output = tmp_path / "candidate-report"
    run = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--offline",
            "--output",
            str(output),
        ],
    )
    assert run.exit_code == 2, run.stdout
    markdown = (output / "report.md").read_text()
    assert "## 候选入口：app.py#submit" in markdown
    assert "genesis flows init" in markdown
    assert "candidate（未确认）" in markdown
    candidate = markdown.split("## 候选入口：", 1)[1].split("## 未归属具体流程", 1)[0]
    assert "Candidate flow entry app.py#submit" in candidate
    assert "flow_entry_" in candidate
    for title in (
        "代码变化与风险",
        "调用路径与影响",
        "成本、等待与失败风险",
        "已有测试与验证缺口",
        "验证建议",
    ):
        assert f"### {title}" in candidate
    report = json.loads((output / "report.json").read_text())
    assert all(not finding["flow_ids"] for finding in report["findings"])
    assert "## 流程：" not in markdown


def test_candidate_group_keeps_other_findings_unassigned_and_rejects_foreign_evidence(source_repo):
    write(source_repo, "app.py", "def submit():\n    return None\n")
    base = commit(source_repo)
    write(
        source_repo,
        "app.py",
        'from openai import OpenAI\nclient = OpenAI()\ndef submit():\n    return client.responses.create(model="synthetic", input="hello")\n',
    )
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base)))
    discovery = result.flows.entry_discovery
    markdown = render_review_markdown(result.report, result.local, entry_discovery=discovery)
    candidate, unassigned = markdown.split("## 未归属具体流程", 1)
    assert "Candidate flow entry app.py#submit" in candidate
    assert "call sites increase from 0 to 1" not in candidate
    assert "call sites increase from 0 to 1" in unassigned
    bad = discovery.candidates[0].model_copy(update={"evidence_ids": ("ev_foreign_snapshot",)})
    with pytest.raises(ValueError, match="same frozen head"):
        render_review_markdown(
            result.report,
            result.local,
            entry_discovery=discovery.model_copy(update={"candidates": (bad,)}),
        )
    wrong_symbol = discovery.candidates[0].model_copy(update={"symbol_id": "app.py#not_discovered"})
    with pytest.raises(ValueError, match="same frozen head"):
        render_review_markdown(
            result.report,
            result.local,
            entry_discovery=discovery.model_copy(update={"candidates": (wrong_symbol,)}),
        )


def test_missing_flow_map_without_discovered_entry_preserves_unknown_and_init_hint(source_repo):
    write(source_repo, "settings.py", "LIMIT = 1\n")
    base = commit(source_repo)
    write(source_repo, "settings.py", "LIMIT = 2\n")
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base)))
    markdown = render_review_markdown(
        result.report, result.local, entry_discovery=result.flows.entry_discovery
    )
    assert "genesis flows init" in markdown
    assert "在已分析范围内没有可展示的候选入口" in markdown
    assert "## 候选入口：" not in markdown

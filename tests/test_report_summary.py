"""The concise report must not turn partial analysis into an approval."""

import re

import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_ci.report import render_review_markdown
from genesis_ci.report_summary import render_summary
from genesis_contracts.models import AnalysisStatus, CapabilityStatus, Limitation, Severity
from genesis_contracts.snapshot import SnapshotSpec
from test_b_report_review import review_fixture
from test_git_snapshot import commit, write


def test_summary_explains_timeout_in_chinese_without_changing_detailed_results():
    local, report, _ = review_fixture()
    report = report.model_copy(
        update={
            "analysis_status": AnalysisStatus.partial,
            "section_status": report.section_status.model_copy(
                update={
                    "acceptance_tests": CapabilityStatus(
                        status="insufficient_context", reason="Semantic stage has not completed."
                    )
                }
            ),
            "limitations": (
                *report.limitations,
                Limitation(
                    code="analysis_timeout",
                    message="Semantic analysis exceeded its deadline.",
                    affects_completeness=True,
                ),
            ),
        }
    )
    original = report.model_dump_json()
    detailed = render_review_markdown(report, local)
    summary = render_summary(report, local)
    assert "模型分析超过时间上限" in summary
    assert "尚未完成：已有测试的检查" in summary
    assert "Semantic stage has not completed" not in summary
    assert "insufficient_context" not in summary
    assert "partial" not in summary
    assert "未知金额不能按零处理" in summary
    assert "代码与测试未执行" in summary
    assert report.model_dump_json() == original
    assert render_review_markdown(report, local) == detailed
    assert "Semantic stage has not completed" in detailed


def test_summary_names_actual_unresolved_calls_without_claiming_invalid_flow_or_missing_intent(
    source_repo,
):
    write(source_repo, "app.py", 'def submit(report):\n    return report.get("title")\n')
    base = commit(source_repo)
    write(source_repo, "app.py", 'def submit(report):\n    return report.get("name")\n')
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base)))
    summary = render_summary(result.report, result.local)
    assert "report.get" in summary
    assert "无法确认实际实现" in summary
    assert "本次只做了本地静态检查" in summary
    assert "Some input files" not in summary
    assert "Candidate SDK" not in summary
    assert "流程地图中有入口无法对应" not in summary
    assert "只检查代码变化和风险，不判断是否符合用户需求" in summary
    assert "请提供需求" not in summary
    assert "不能当成没有问题" in summary


def test_summary_links_only_to_frozen_detailed_evidence_and_escapes_untrusted_prose():
    local, report, _ = review_fixture()
    malicious = report.findings[0].model_copy(
        update={
            "severity": Severity.high,
            "statement": '![load](https://example.invalid/pixel) <img src="bad">',
            "condition": "![condition](https://example.invalid/condition)",
            "recommendation": "<script>alert(1)</script>",
        }
    )
    report = report.model_copy(update={"findings": (malicious, *report.findings[1:])})
    summary = render_summary(report, local)
    detailed = render_review_markdown(report, local)
    links = re.findall(r"\(report.md#evidence-([^)]+)\)", summary)
    assert links
    assert all(f'id="evidence-{ref}"' in detailed for ref in links)
    assert "![load](" not in summary
    assert "![condition](" not in summary
    assert "<img " not in summary and "<script>" not in summary
    assert "&lt;img " in summary and "&lt;script&gt;" in summary


def test_summary_bounds_risk_list_but_reports_remaining_count_and_keeps_conditions():
    local, report, _ = review_fixture()
    findings = tuple(
        report.findings[0].model_copy(
            update={
                "finding_id": f"review-risk-{number}",
                "severity": Severity.high,
                "statement": f"风险 {number}",
                "condition": "仅当审批通过且提交失败时。",
            }
        )
        for number in range(10)
    )
    report = report.model_copy(update={"findings": findings})
    summary = render_summary(report, local)
    assert "优先处理 10 项" in summary
    assert "还有 2 项需核对的发现" in summary
    assert summary.count("何时出现：仅当审批通过且提交失败时。") == 8
    assert "风险 9" not in summary


def test_summary_empty_partial_report_does_not_mean_no_risk_or_complete_review():
    local, report, _ = review_fixture()
    report = report.model_copy(
        update={"findings": (), "suggestions": (), "analysis_status": AnalysisStatus.partial}
    )
    summary = render_summary(report, local)
    assert "本次分析尚未全部完成" in summary
    assert "不能当成没有问题" in summary
    assert "没有单独生成测试清单" in summary


def test_summary_retains_unknown_limit_and_rejects_mixed_snapshot():
    local, report, _ = review_fixture()
    report = report.model_copy(
        update={
            "analysis_status": AnalysisStatus.partial,
            "limitations": (
                *report.limitations,
                Limitation(
                    code="future_limit", message="New scope gap.", affects_completeness=True
                ),
            ),
        }
    )
    assert "还有其他分析限制" in render_summary(report, local)
    wrong = report.model_copy(
        update={"scope": report.scope.model_copy(update={"head_revision": "another-revision"})}
    )
    with pytest.raises(ValueError, match="same frozen analysis"):
        render_summary(wrong, local)

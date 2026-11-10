from genesis_contracts import AnalysisResponse, LocalAnalysis
from genesis_contracts.intelligence import FlowEntryDiscovery
from genesis_contracts.models import (
    AnalysisRequest,
    BehaviorAnalysisResponse,
    CapabilityStatus,
    Limitation,
    PathAnalysisResponse,
    SectionStatuses,
    SemanticAnalysisResponse,
)
from genesis_contracts.validation import (
    validate_local_analysis,
    validate_model_response,
    validate_public_response,
    validate_request_against_local,
    validate_semantic_response,
)

from .report_behavior import render_behavior_review
from .snapshot import SnapshotReader


def _merge_capability_status(local: CapabilityStatus, remote: CapabilityStatus) -> CapabilityStatus:
    """Retain both analyses without upgrading either side's coverage boundary."""
    severity = {"analyzed": 0, "insufficient_context": 1, "unsupported": 2}
    status = max((local.status, remote.status), key=severity.__getitem__)

    def retain_text(name: str) -> str | None:
        local_text, remote_text = getattr(local, name), getattr(remote, name)
        if local_text == remote_text or not remote_text:
            return local_text
        if not local_text:
            return remote_text
        return f"本地静态分析：{local_text}\n语义分析：{remote_text}"

    return CapabilityStatus(
        status=status,
        reason=retain_text("reason"),
        analyzed_scope=retain_text("analyzed_scope"),
    )


def assemble_report(
    local: LocalAnalysis,
    request: AnalysisRequest | None,
    semantic: SemanticAnalysisResponse | None,
    *,
    execution_mode: str = "mock",
    failure: Limitation | None = None,
    analyzer_version: str = "0.1.0-mock",
    rule_version: str = "0.1.0-mock",
    parser_limitations: tuple[str, ...] = (
        "Deterministic fixture facts; no customer code was analyzed.",
    ),
) -> AnalysisResponse:
    validate_local_analysis(local)
    if request is not None:
        validate_request_against_local(local, request)
    elif semantic is not None:
        raise ValueError("Semantic output requires its validated request")
    limitations = list(local.limitations)
    statuses = {}
    if semantic is not None:
        if execution_mode == "semantic":
            validate_model_response(request, semantic)
        else:
            validate_semantic_response(request, semantic)
        limitations.extend(semantic.limitations)
    else:
        execution_mode = "offline"
        limitations.append(
            failure
            or Limitation(
                code="offline",
                message="Semantic analysis was not requested.",
                affects_completeness=True,
            )
        )
    if request is not None and (request.truncated or request.missing_context):
        limitations.append(
            Limitation(
                code="context_incomplete",
                message="Selected context is truncated or missing: "
                + ", ".join(request.missing_context),
                affects_completeness=True,
            )
        )
    for name in SectionStatuses.model_fields:
        local_status = getattr(local.capabilities, name)
        remote_status = (
            getattr(semantic.section_status, name)
            if semantic
            else CapabilityStatus(
                status="insufficient_context",
                reason="Semantic service unavailable; local facts and rules retained.",
            )
        )
        # Coverage stays conservative; neither side's supported explanation is discarded.
        statuses[name] = _merge_capability_status(local_status, remote_status)
    review = semantic.behavior_review if semantic else None
    complete = (
        semantic is not None
        and execution_mode != "offline"
        and all(status.status == "analyzed" for status in statuses.values())
        and local.snapshot.integrity_status == "complete"
        and not local.snapshot.omitted_inputs
        and not any(item.affects_completeness for item in limitations)
        and (review is None or review.coverage.status == "analyzed")
    )
    model = (
        PathAnalysisResponse
        if review is not None and review.version == "2"
        else BehaviorAnalysisResponse
        if review is not None
        else AnalysisResponse
    )
    report = model(
        **({"behavior_review": review} if review is not None else {}),
        snapshot_id=local.snapshot.snapshot_id,
        analysis_status="complete" if complete else "partial",
        section_status=SectionStatuses(**statuses),
        scope={
            "base_revision": local.snapshot.base_revision,
            "head_revision": local.snapshot.head_revision,
            "analyzed_files": tuple(sorted({file.path for file in local.snapshot.files})),
            "omitted_inputs": local.snapshot.omitted_inputs,
            "parser_limitations": parser_limitations,
            "execution_mode": execution_mode,
        },
        findings=(*local.rule_findings, *(semantic.findings if semantic else ())),
        estimates=local.estimates,
        suggestions=semantic.suggestions if semantic else (),
        limitations=tuple(dict.fromkeys(limitations)),
        analyzer_version=analyzer_version,
        rule_version=rule_version,
        semantic_version=semantic.semantic_version if semantic else None,
        evidence=local.evidence,
    )
    validate_public_response(report)
    return report


def render_markdown(report: AnalysisResponse) -> str:
    labels = {
        "behavior_intent": "业务变化与意图",
        "flow_impact": "受影响流程与路径",
        "cost_risk": "成本、等待与失败风险",
        "acceptance_tests": "验收要点与已有测试",
        "verification": "验证建议",
    }
    lines = [
        "# Code Intelligence 分析报告",
        "",
        f"- 状态：{report.analysis_status.value}",
        f"- Snapshot：{report.snapshot_id}",
        f"- 模式：{report.scope.execution_mode}",
        f"- 版本：analyzer={report.analyzer_version}; rule={report.rule_version}; semantic={report.semantic_version or 'none'}",
        "- complete 只表示声明范围的五栏分析完成，不表示测试通过。",
        "",
        "## 分析范围",
        "",
        f"- base：{report.scope.base_revision}; head：{report.scope.head_revision}",
        "- 文件：" + ", ".join(report.scope.analyzed_files),
    ]
    for label, items in (
        ("未纳入", report.scope.omitted_inputs),
        ("解析限制", report.scope.parser_limitations),
    ):
        lines.extend(f"- {label}：{item}" for item in items)
    lines.extend(render_behavior_review(report, detailed=True))
    for section, title in labels.items():
        status = getattr(report.section_status, section)
        lines.extend(("", f"## {title}", "", f"状态：{status.status.value}"))
        if status.reason:
            lines.extend(("", status.reason))
        if status.analyzed_scope:
            lines.append(f"分析范围：{status.analyzed_scope}")
        for finding in (item for item in report.findings if item.category.value == section):
            lines.extend(
                (
                    "",
                    f"- [{finding.finding_id}] {finding.severity.value}: {finding.statement}",
                    "  - 依据类型：" + ", ".join(finding.basis),
                    "  - 证据：" + ", ".join(finding.evidence_ids),
                )
            )
            for label, value in (
                ("偏差", finding.deviation),
                ("条件", finding.condition),
                ("缺口", finding.gap),
                ("建议", finding.recommendation),
                ("流程", ", ".join(finding.flow_ids)),
                ("估算引用", ", ".join(finding.estimate_ids)),
            ):
                if value:
                    lines.append(f"  - {label}：{value}")
        if section == "cost_risk":
            for estimate in report.estimates:
                lines.extend(
                    (
                        "",
                        f"- 估算 {estimate.estimate_id}：" + "; ".join(estimate.structural_signals),
                    )
                )
                for param in estimate.parameters:
                    value = (
                        str(param.value)
                        if param.value is not None
                        else "未知：" + param.unknown_reason
                    )
                    lines.append(
                        f"  - {param.name}: {value} ({param.unit}); 来源：{param.source or '未提供'}"
                    )
                for label, value in (
                    ("公式", estimate.formula),
                    ("金额", estimate.amount),
                    ("币种", estimate.currency),
                    ("价格来源", estimate.price_source),
                    ("价格日期", estimate.price_date),
                ):
                    if value is not None:
                        lines.append(f"  - {label}：{value}")
                lines.extend(f"  - 假设：{item}" for item in estimate.assumptions)
                lines.extend(f"  - 未知：{item}" for item in estimate.unknowns)
                lines.append("  - 证据：" + ", ".join(estimate.evidence_ids))
                if estimate.flow_ids:
                    lines.append("  - 流程：" + ", ".join(estimate.flow_ids))
        if section == "verification":
            for suggestion in report.suggestions:
                lines.extend(
                    (
                        "",
                        f"- [{suggestion.suggestion_id}] {suggestion.scenario}",
                        f"  - 理由：{suggestion.rationale}",
                    )
                )
                for label, items in (
                    ("条件", suggestion.conditions),
                    ("建议断言", suggestion.suggested_assertions),
                    ("待确认", suggestion.questions_for_user),
                    ("已有测试证据", suggestion.existing_test_evidence_ids),
                    ("证据", suggestion.evidence_ids),
                ):
                    lines.extend(f"  - {label}：{item}" for item in items)
    lines.extend(("", "## 分析限制", ""))
    lines.extend(
        f"- {item.code}：{item.message}（影响完整性：{item.affects_completeness}；证据：{', '.join(item.evidence_ids)}）"
        for item in report.limitations
    )
    lines.extend(("", "## 证据目录", ""))
    for ref in report.evidence:
        span = ref.range
        location = f"{ref.side.value}:{ref.path}:{span.start_line}-{span.end_line}"
        lines.append(
            f"- {ref.evidence_id}: {location}; columns={span.start_column}:{span.end_column}; kind={ref.kind.value}; {ref.snippet_digest}"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_review_markdown(
    report: AnalysisResponse,
    local: LocalAnalysis,
    *,
    reader: SnapshotReader | None = None,
    entry_discovery: FlowEntryDiscovery | None = None,
) -> str:
    """Render grouped review; an explicitly supplied frozen reader includes source text.

    The legacy renderer stays unchanged for the pinned public examples. Callers
    should publish source-bearing output separately from shareable report.md.
    """
    from .report_review import render_review

    return render_review(report, local, reader=reader, entry_discovery=entry_discovery)

"""Flow-oriented presentation, without changing the public report schema."""

from __future__ import annotations

import html
import re
from collections import defaultdict

from genesis_contracts.intelligence import FlowEntryDiscovery
from genesis_contracts.models import AnalysisResponse, LocalAnalysis
from genesis_contracts.validation import (
    validate_excerpts,
    validate_local_analysis,
    validate_public_response,
)

from .report_behavior import render_behavior_review
from .snapshot import SnapshotReader

SECTIONS = {
    "behavior_intent": "业务变化与意图",
    "flow_impact": "受影响流程与路径",
    "cost_risk": "成本、等待与失败风险",
    "acceptance_tests": "验收要点与已有测试",
    "verification": "验证建议",
}


def _section_labels(local):
    labels = dict(SECTIONS)
    if not any(item.nature == "user_intent" for item in local.intents):
        labels.update(
            behavior_intent="代码变化与风险",
            acceptance_tests="已有测试与验证缺口",
        )
    if not local.flows:
        labels["flow_impact"] = "调用路径与影响"
    return labels


def _text(value) -> str:
    # Repository/model text remains visible text, never an external image or HTML.
    escaped = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*{}\[\]|])", r"\\\1", escaped).replace("\n", " ")


def _details(lines, fields) -> None:
    for label, value in fields:
        if value is not None and value != "":
            lines.append(f"  - {label}：{_text(value)}")


def _evidence_link(ref) -> str:
    return f"[{ref.evidence_id}](#evidence-{ref.evidence_id})"


def _comparison(report):
    grouped = defaultdict(lambda: {"base": [], "head": []})
    for ref in report.evidence:
        grouped[(ref.path, ref.kind.value)][ref.side.value].append(ref)
    lines = [
        "",
        "## 冻结版本前后对照",
        "",
        "仅把同一路径、同一证据类型的引用并列；不推断函数对应、改名对应或业务等价。",
        "一侧没有引用只表示该侧未提供这类证据，不证明文件、代码或行为不存在。",
        "",
        "| 路径 / 类型 | base 证据 | head 证据 |",
        "| --- | --- | --- |",
    ]
    for (path, kind), sides in sorted(grouped.items()):
        cells = []
        for side in ("base", "head"):
            refs = sorted(
                sides[side],
                key=lambda ref: (ref.range.start_line, ref.range.end_line, ref.evidence_id),
            )
            cells.append(
                "<br>".join(
                    f"{_evidence_link(ref)} L{ref.range.start_line}–{ref.range.end_line}"
                    for ref in refs
                )
                or "未提供此侧证据"
            )
        lines.append(f"| {_text(path)} / {kind} | {cells[0]} | {cells[1]} |")
    return lines


def _section(report, section, flow_id, labels):
    status = getattr(report.section_status, section)
    lines = ["", f"### {labels[section]}", "", f"本次分析栏目状态：{status.status.value}"]
    _details(lines, (("原因", status.reason), ("分析范围", status.analyzed_scope)))
    items = [
        item
        for item in report.findings
        if item.category.value == section
        and (flow_id in item.flow_ids if flow_id else not item.flow_ids)
    ]
    for item in items:
        lines.extend(
            ("", f"- **{_text(item.finding_id)}** · {item.severity.value}：{_text(item.statement)}")
        )
        _details(
            lines,
            (
                ("依据类型", ", ".join(item.basis)),
                ("证据", ", ".join(item.evidence_ids)),
                ("偏差", item.deviation),
                ("条件", item.condition),
                ("缺口", item.gap),
                ("建议", item.recommendation),
                ("流程", ", ".join(item.flow_ids)),
                ("估算引用", ", ".join(item.estimate_ids)),
            ),
        )
    estimates = (
        (
            [item for item in report.estimates if flow_id in item.flow_ids]
            if flow_id
            else [item for item in report.estimates if not item.flow_ids]
        )
        if section == "cost_risk"
        else []
    )
    for estimate in estimates:
        lines.extend(("", f"- **条件估算 {_text(estimate.estimate_id)}**"))
        _details(lines, (("结构信号", "; ".join(estimate.structural_signals)),))
        for param in estimate.parameters:
            value = param.value if param.value is not None else f"未知：{param.unknown_reason}"
            _details(
                lines, ((param.name, f"{value} ({param.unit}); 来源：{param.source or '未提供'}"),)
            )
        _details(
            lines,
            (
                ("公式", estimate.formula),
                ("金额", estimate.amount if estimate.amount is not None else "未知，不按零处理"),
                ("币种", estimate.currency),
                ("价格来源", estimate.price_source),
                ("价格日期", estimate.price_date),
                ("流程", ", ".join(estimate.flow_ids)),
                ("证据", ", ".join(estimate.evidence_ids)),
            ),
        )
        _details(lines, (("假设", value) for value in estimate.assumptions))
        _details(lines, (("未知", value) for value in estimate.unknowns))
    suggestions = report.suggestions if section == "verification" and flow_id is None else ()
    for suggestion in suggestions:
        lines.extend(("", f"- **{_text(suggestion.suggestion_id)}**：{_text(suggestion.scenario)}"))
        _details(lines, (("理由", suggestion.rationale),))
        for label, values in (
            ("条件", suggestion.conditions),
            ("建议断言", suggestion.suggested_assertions),
            ("待确认", suggestion.questions_for_user),
            ("已有测试证据", suggestion.existing_test_evidence_ids),
            ("证据", suggestion.evidence_ids),
        ):
            _details(lines, ((label, value) for value in values))
    if not items and not estimates and not suggestions:
        lines.extend(("", "未提供归属于本分组的结果；不代表没有问题或已完成验收。"))
    if section == "verification" and flow_id:
        lines.extend(("", "验证建议没有显式流程归属，统一列于「未归属具体流程」。"))
    return lines


def _candidate_groups(report, local, discovery):
    lines = [
        "",
        "## 代码入口与路径",
        "",
        "未提供可选的流程地图，本次按代码路径分析。若需要业务流程分组，可运行 `genesis flows init` 起草并人工确认；不影响当前代码风险分析。",
    ]
    if discovery is None:
        return [*lines, "", "未提供自动入口发现结果；不推断入口。"], set()
    catalog = {ref.evidence_id: ref for ref in report.evidence}
    used = set()
    local_findings = {item.finding_id: item for item in local.rule_findings}
    if not discovery.candidates:
        lines.extend(("", "在已分析范围内没有可展示的候选入口；不代表项目没有入口。"))
    _details(
        lines,
        (("入口发现状态", discovery.coverage.status.value), ("限制", discovery.coverage.reason)),
    )
    for limit in discovery.limitations:
        _details(lines, (("入口发现限制", limit),))
    for candidate in discovery.candidates:
        symbols = [
            item
            for item in local.facts.functions
            if item.side == "head"
            and item.kind == "function"
            and item.symbol_id == candidate.symbol_id
        ]
        refs = set(candidate.evidence_ids)
        if (
            candidate.side != "head"
            or len(symbols) != 1
            or not refs
            or not set(symbols[0].evidence_ids) <= refs
            or any(
                ref not in catalog or catalog[ref].side != "head" or catalog[ref].kind != "code"
                for ref in refs
            )
        ):
            raise ValueError("Candidate entry must cite the same frozen head symbol and evidence")
        findings = tuple(
            item
            for item in report.findings
            if item.finding_id == candidate.candidate_id
            and item == local_findings.get(item.finding_id)
            and item.category == "flow_impact"
            and not item.flow_ids
            and set(item.evidence_ids) == refs
        )
        used.update(item.finding_id for item in findings)
        lines.extend(
            (
                "",
                f"## 候选入口：{_text(candidate.symbol_id)}",
                "",
                "- 状态：candidate（未确认）；这是静态入口候选，不是已确认业务流程或运行事实。",
            )
        )
        _details(
            lines,
            (
                ("候选 ID", candidate.candidate_id),
                ("发现理由", candidate.reason),
                ("冻结 head 证据", ", ".join(candidate.evidence_ids)),
            ),
        )
        projection = report.model_copy(
            update={"findings": findings, "estimates": (), "suggestions": ()}
        )
        for section in SECTIONS:
            lines.extend(_section(projection, section, None, _section_labels(local)))
    return lines, used


def render_review(
    report: AnalysisResponse,
    local: LocalAnalysis,
    *,
    reader: SnapshotReader | None = None,
    entry_discovery: FlowEntryDiscovery | None = None,
) -> str:
    validate_public_response(report)
    validate_local_analysis(local)
    if (
        report.snapshot_id != local.snapshot.snapshot_id
        or report.evidence != local.evidence
        or report.scope.base_revision != local.snapshot.base_revision
        or report.scope.head_revision != local.snapshot.head_revision
    ):
        raise ValueError("Review inputs must refer to the same frozen analysis")
    source = {}
    if reader is not None:
        catalog = {ref.evidence_id: ref for ref in reader.evidence_catalog()}
        for ref in report.evidence:
            if catalog.get(ref.evidence_id) != ref:
                raise ValueError("Source appendix reader differs from report evidence")
            excerpt = reader.read_excerpt(ref.evidence_id)
            validate_excerpts(report.snapshot_id, (ref,), (excerpt,))
            source[ref.evidence_id] = excerpt.text
    lines = [
        "# Code Intelligence 流程审阅报告" if local.flows else "# Code Intelligence 代码变更报告",
        "",
        f"- 展示版本：flow-review-v1；公开 JSON schema：{report.schema_version}。",
        f"- 状态：{report.analysis_status.value}；模式：{report.scope.execution_mode}",
        f"- Snapshot：{_text(report.snapshot_id)}",
        f"- 版本：analyzer={_text(report.analyzer_version)}; rule={_text(report.rule_version)}; semantic={_text(report.semantic_version or 'none')}",
        "- 代码与测试未执行；complete 只表示声明范围分析完成，不表示业务验收通过。",
        "- 按显式 flow_ids 分组；跨流程结果会重复展示。未声明归属的结果与验证建议保留在独立分组。",
        "- 栏目状态适用于本次分析，不是逐流程通过结论。",
        "- 包含冻结源码与意图原文；仅供获授权的本地审阅，不默认上传 CI artifact。"
        if reader is not None
        else "- 本文不包含原始源码摘录；证据链接仅跳转到本报告的冻结位置目录。",
        "",
        "## 分析范围",
        "",
        f"- base：{_text(report.scope.base_revision)}",
        f"- head：{_text(report.scope.head_revision)}",
        "- 文件：" + ", ".join(_text(path) for path in report.scope.analyzed_files),
    ]
    for label, values in (
        ("未纳入", report.scope.omitted_inputs),
        ("解析限制", report.scope.parser_limitations),
    ):
        _details(lines, ((label, value) for value in values))
    if not any(item.nature == "user_intent" for item in local.intents):
        lines.extend(
            (
                "",
                "未提供用户需求或已确认的验收规则；本次分析代码变化、风险和验证建议，不判断需求符合性。需求与 PR 说明均为可选输入。",
            )
        )
    lines.extend(render_behavior_review(report, detailed=True))
    labels = _section_labels(local)
    flows = {flow.id: flow for flow in local.flows}
    referenced = {flow for item in (*report.findings, *report.estimates) for flow in item.flow_ids}
    for flow_id in sorted(set(flows) | referenced):
        flow = flows.get(flow_id)
        title = _text(flow.name) if flow else _text(flow_id)
        lines.extend(("", f"## 流程：{title}", "", f"- ID：{_text(flow_id)}"))
        if flow:
            lines.append(
                f"- 流程地图状态：{flow.status.value}；入口：{', '.join(_text(entry) for entry in flow.entries)}"
            )
        else:
            lines.append("- 当前本地流程地图没有此 ID 的定义；不推断名称或验收要求。")
        for section in SECTIONS:
            lines.extend(_section(report, section, flow_id, labels))
    unassigned_report = report
    if not local.flows:
        candidates, grouped_ids = _candidate_groups(report, local, entry_discovery)
        lines.extend(candidates)
        unassigned_report = report.model_copy(
            update={
                "findings": tuple(
                    item for item in report.findings if item.finding_id not in grouped_ids
                )
            }
        )
    lines.extend(
        ("", "## 未归属具体流程", "", "未提供显式流程 ID 的结果；此处不代表项目中不存在相关流程。")
    )
    for section in SECTIONS:
        lines.extend(_section(unassigned_report, section, None, labels))
    lines.extend(("", "## 分析限制", ""))
    for item in report.limitations:
        lines.append(
            f"- {_text(item.code)}：{_text(item.message)}（影响完整性：{item.affects_completeness}）"
        )
        _details(lines, (("证据", ", ".join(item.evidence_ids)),))
    # Link only known IDs in rendered findings; all targets live in this document.
    joined = "\n".join(lines)
    for ref in report.evidence:
        joined = joined.replace(ref.evidence_id, _evidence_link(ref))
    lines = [joined, *_comparison(report), "", "## 证据目录", ""]
    for ref in report.evidence:
        revision = report.scope.base_revision if ref.side == "base" else report.scope.head_revision
        lines.extend(
            (
                f'<a id="evidence-{ref.evidence_id}"></a>',
                "",
                f"### {ref.evidence_id}",
                "",
                f"- 冻结位置：{ref.side.value}:{_text(ref.path)}:{ref.range.start_line}-{ref.range.end_line}；列 {ref.range.start_column}:{ref.range.end_column}",
                f"- 版本：{_text(revision)}；类型：{ref.kind.value}",
                f"- 摘要：{ref.snippet_digest}",
                "",
            )
        )
        if ref.evidence_id in source:
            content = source[ref.evidence_id]
            fence = "`" * max(
                3, 1 + max((len(run) for run in re.findall(r"`+", content)), default=0)
            )
            lines.extend((fence + "text", content, fence, ""))
    return "\n".join(lines).rstrip() + "\n"

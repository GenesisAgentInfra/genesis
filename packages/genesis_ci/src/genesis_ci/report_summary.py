"""A concise reading view of existing results; no model call or new analysis."""

from __future__ import annotations

import re
from collections import Counter

from genesis_contracts.models import AnalysisResponse, LocalAnalysis
from genesis_contracts.validation import validate_local_analysis, validate_public_response

from .report_behavior import render_behavior_review
from .report_review import _text

SECTIONS = {
    "behavior_intent": "代码行为与需求对照",
    "flow_impact": "受影响的调用路径",
    "cost_risk": "成本与等待风险",
    "acceptance_tests": "已有测试的检查",
    "verification": "后续验证建议",
}
LEVELS = {"high": "优先处理", "medium": "需要核对", "low": "一般提醒", "info": "变化说明"}
LIMITS = {
    "analysis_timeout": "模型分析超过时间上限，部分检查未完成；已经返回的结果保留在报告中。",
    "provider_error": "模型服务调用失败，部分语义分析没有返回结果。",
    "provider_output_invalid": "模型返回的部分内容未通过格式或证据检查，已被丢弃。",
    "service_unavailable": "分析服务不可用，本次保留了已获得的结果。",
    "invalid_api_key": "Genesis Key 验证或连接配置不可用，未完成线上分析；请核对本机授权配置。",
    "quota_exceeded": "Genesis Key 的请求额度已用完，未完成线上分析。",
    "request_too_large": "部分分析材料超过了请求或模型输入上限。",
    "offline": "本次只做了本地静态检查，没有请求模型分析。",
    "preview_only": "本次只预览了待发送材料，没有请求模型分析。",
    "send_not_confirmed": "本次没有确认发送材料，因此未请求模型分析。",
    "fork_pr_offline": "当前 PR 上下文不允许发送代码，本次仅做本地检查，没有使用服务密钥。",
    "incomplete_reachability": "静态调用关系不足以确认所有业务分支实际会如何执行。",
    "test_context_partial": "部分测试依赖或模拟配置未能完整识别，测试关联仍需人工核对。",
    "flow_entry_discovery_partial": "代码入口发现尚不完整，可能遗漏部分调用路径。",
}


def _locations(report, evidence_ids, limit=3):
    catalog = {ref.evidence_id: ref for ref in report.evidence}
    refs = [catalog[ref] for ref in evidence_ids if ref in catalog]
    refs.sort(
        key=lambda ref: (ref.side != "head", ref.kind != "code", ref.path, ref.range.start_line)
    )
    seen, links = set(), []
    for ref in refs:
        key = (ref.side, ref.path, ref.range.start_line, ref.range.end_line)
        if key in seen:
            continue
        seen.add(key)
        side = "改动后" if ref.side == "head" else "改动前"
        span = str(ref.range.start_line)
        if ref.range.end_line != ref.range.start_line:
            span += f"–{ref.range.end_line}"
        label = _text(f"{side} {ref.path} 第 {span} 行")
        links.append(f"[{label}](report.md#evidence-{ref.evidence_id})")
        if len(links) == limit:
            break
    return "；".join(links)


def _condition(value):
    if value == (
        "Static recognized call sites only. Branches, repeated invocations, retries, "
        "dynamic mutation and runtime outcomes can differ."
    ):
        return "仅根据静态识别出的调用位置判断；实际分支、重复调用、重试和运行结果仍需验证。"
    # Translate only the exact scope wrapper added by the semantic validator.
    prefix = re.match(r"^Inspected head excerpts: .*?\. No conclusion about omitted paths\.", value)
    if prefix:
        return value[prefix.end() :].strip() + "（仅针对已引用的改动后代码，其他路径仍未知。）"
    return value


def _statement(item, local):
    # These are known local rule templates, not translations guessed from model prose.
    if item not in local.rule_findings:
        return item.statement
    if item.finding_id.startswith("loop_no_count_bound_"):
        return "模型调用位于一个没有静态次数上限的循环中；需要核对退出条件和调用次数。"
    if item.finding_id.startswith("tool_schema_dispatch_mismatch_"):
        return "工具声明与代码中的工具分发候选不一致，需要核对实际可调用的工具。"
    if item.finding_id.startswith("loop_bound_changed_"):
        return "模型调用所在循环的静态次数上限发生变化，需要核对停止条件。"
    return item.statement


def _finding(lines, item, report, local, number):
    lines.extend(
        ("", f"### {number}. {LEVELS[item.severity]}：{_text(_statement(item, local))}", "")
    )
    if item.condition:
        lines.append(f"- 何时出现：{_text(_condition(item.condition))}")
    if item.recommendation:
        lines.append(f"- 建议处理：{_text(item.recommendation)}")
    elif item.gap:
        lines.append(f"- 还需核对：{_text(item.gap)}")
    if "semantic_inference" in item.basis:
        lines.append("- 判断依据：模型结合所列证据作出的推断，需要核对触发条件。")
    else:
        lines.append("- 判断依据：本地静态检查；代码中的结构变化不等于运行时已发生故障。")
    if item.flow_ids:
        names = {flow.id: flow.name for flow in local.flows}
        lines.append(
            "- 涉及流程：" + "、".join(_text(names.get(fid, fid)) for fid in item.flow_ids)
        )
    locations = _locations(report, item.evidence_ids)
    if locations:
        lines.append("- 核对位置：" + locations)


def _limits(report, local):
    messages = []
    codes = {item.code for item in report.limitations if item.affects_completeness}
    calls = [call for call in local.facts.calls if call.target.status != "resolved"]
    for item in sorted(report.limitations, key=lambda item: item.code != "analysis_timeout"):
        if not item.affects_completeness:
            continue
        if item.code in {"no_runtime_execution", "truncated_snapshot", "context_incomplete"}:
            continue
        if item.code == "incomplete_reachability" and calls:
            continue
        if item.code in LIMITS:
            messages.append(LIMITS[item.code])
        elif re.search(r"[\u4e00-\u9fff]", item.message):
            messages.append(item.message)
        else:
            messages.append("还有其他分析限制，原始原因和证据保留在详细报告的“分析限制”中。")
    if codes & {"truncated_snapshot", "context_incomplete"}:
        messages.append("模型收到的材料不完整，部分代码或关联信息没有纳入；结论只覆盖已提供内容。")
    unfinished = [
        SECTIONS[name]
        for name in SECTIONS
        if getattr(report.section_status, name).reason == "Semantic stage has not completed."
    ]
    if unfinished:
        messages.append("尚未完成：" + "、".join(unfinished) + "。")
    unsupported = [
        SECTIONS[name]
        for name in SECTIONS
        if getattr(report.section_status, name).status == "unsupported"
    ]
    if unsupported:
        messages.append("当前分析能力不支持完整检查：" + "、".join(unsupported) + "。")
    # Cite actual unresolved calls instead of repeating the broad section fallback.
    if not calls and (local.facts.unresolved or local.facts.coverage.status != "analyzed"):
        messages.append("部分代码结构尚未被完整识别；对应范围内仍可能有未发现的问题。")
    if any(flow.entry_status == "invalid" for flow in local.flow_impacts):
        messages.append("提供的流程地图中有入口无法对应到已分析代码，请核对入口路径。")
    elif not calls and any(flow.status != "resolved" for flow in local.flow_impacts):
        messages.append("部分流程与改动之间的调用路径尚未确认，影响范围可能不完整。")
    if not messages and not calls and report.analysis_status != "complete":
        messages.append("部分检查尚未完成或材料不足；各栏原始状态和原因保留在详细报告中。")
    lines = ["", "## 哪些还没查清", ""]
    if not messages and not calls:
        lines.append("声明范围内的分析已完成；代码与测试未执行，仍需实际验证。")
    lines.extend(f"- {_text(message)}" for message in dict.fromkeys(messages))
    if calls:
        lines.append(
            f"- 静态分析有 {len(calls)} 处调用无法确认实际实现，调用路径检查因此不完整。"
            "这是分析器的能力限制，不能直接当成代码错误："
        )
    for call in calls[:3]:
        lines.append(
            f"  - 例如 {_text(call.expression)}：{_locations(report, call.evidence_ids, 1)}"
        )
    if len(calls) > 3:
        lines.append(f"  - 另有 {len(calls) - 3} 处调用，详见完整分析材料。")
    return lines


def render_summary(report: AnalysisResponse, local: LocalAnalysis) -> str:
    """Keep findings and uncertainty intact while hiding internal diagnostic wording."""
    validate_public_response(report)
    validate_local_analysis(local)
    if (
        report.snapshot_id != local.snapshot.snapshot_id
        or report.evidence != local.evidence
        or report.scope.base_revision != local.snapshot.base_revision
        or report.scope.head_revision != local.snapshot.head_revision
    ):
        raise ValueError("Summary inputs must refer to the same frozen analysis")
    state = {
        "complete": "声明范围内的分析已完成。",
        "partial": "本次分析尚未全部完成，下面是已经得到的结果。",
        "failed": "本次分析未成功完成，请先查看下方未完成原因。",
    }[report.analysis_status]
    lines = [
        "# 代码变更简报",
        "",
        state + " 代码与测试未执行，不能据此认定测试通过或代码没有问题。",
        "",
        "先看需要处理的风险，再看分析边界。完整状态、原始说明和所有证据见 [详细报告](report.md)。",
        "",
        "## 这次检查了什么",
        "",
        f"- 对比版本：{_text((report.scope.base_revision or '未提供')[:12])} → {_text((report.scope.head_revision or '未提供')[:12])}。",
    ]
    changed = list(dict.fromkeys(f.head_path or f.base_path for f in local.change_set.files))
    lines.append(
        f"- 变更文件共 {len(changed)} 个：" + "、".join(_text(p) for p in changed[:10]) + "。"
    )
    if len(changed) > 10:
        lines.append("- 其余变更文件见详细报告及本地分析材料。")
    if not any(item.nature == "user_intent" for item in local.intents):
        lines.append(
            "- 本次未提供需求或已确认的验收规则，只检查代码变化和风险，不判断是否符合用户需求。"
        )
    else:
        lines.append("- 本次还结合了已提供的需求或已确认的流程验收规则进行对照。")
    lines.extend(render_behavior_review(report))
    priorities = sorted(
        (item for item in report.findings if item.severity != "info"),
        key=lambda item: {"high": 0, "medium": 1, "low": 2}[item.severity],
    )
    lines.extend(("", "## 需要你关注什么", ""))
    if priorities:
        counts = Counter(item.severity for item in priorities)
        lines.append(
            "、".join(f"{LEVELS[level]} {counts[level]} 项" for level in LEVELS if counts[level])
            + "。多项发现可能涉及同一问题；等级不代表结论已经过运行验证。"
        )
        for number, item in enumerate(priorities[:8], 1):
            _finding(lines, item, report, local, number)
        if len(priorities) > 8:
            lines.extend(
                (
                    "",
                    f"还有 {len(priorities) - 8} 项需核对的发现，请继续阅读 [详细报告](report.md)。",
                )
            )
    else:
        lines.append("本次结果没有列出需优先处理的风险；请结合下方分析边界判断，不能当成没有问题。")
    observations = [
        item
        for item in report.findings
        if item.severity == "info" and "semantic_inference" in item.basis
    ]
    if observations:
        lines.extend(("", "## 其他变化与权衡", ""))
        for item in observations[:3]:
            lines.append(f"- {_text(item.statement)}")
            if item.condition:
                lines.append(f"  - 适用条件：{_text(_condition(item.condition))}")
            if item.gap:
                lines.append(f"  - 尚不确定：{_text(item.gap)}")
            locations = _locations(report, item.evidence_ids, 1)
            if locations:
                lines.append("  - 核对位置：" + locations)
    info_count = sum(item.severity == "info" for item in report.findings)
    if info_count:
        lines.extend(
            (
                "",
                f"另有 {info_count} 项说明性发现（含上方已展示内容），完整列表见详细报告；这些观察不自动表示需要修改代码。",
            )
        )
    if report.estimates:
        lines.extend(
            (
                "",
                f"本次还有 {len(report.estimates)} 项条件成本估算，金额、公式和假设见详细报告；未知金额不能按零处理。",
            )
        )
    lines.extend(("", "## 下一步如何验证", ""))
    if report.suggestions:
        for item in report.suggestions[:5]:
            lines.append(f"- {_text(item.scenario)}")
            for condition in item.conditions:
                lines.append(f"  - 条件：{_text(condition)}")
            for assertion in item.suggested_assertions:
                lines.append(f"  - 应检查：{_text(assertion)}")
            for question in item.questions_for_user:
                lines.append(f"  - 待确认：{_text(question)}")
            lines.append("  - 依据：" + _locations(report, item.evidence_ids, 1))
        if len(report.suggestions) > 5:
            lines.append(f"- 另有 {len(report.suggestions) - 5} 项验证建议，见详细报告。")
    else:
        lines.append(
            "本次没有单独生成测试清单。先按上方风险中的处理建议核对；其他测试场景和覆盖情况仍需确认。"
        )
    lines.extend(_limits(report, local))
    lines.extend(("", "[查看详细报告与完整证据](report.md) · [查看结构化结果](report.json)", ""))
    return "\n".join(lines)

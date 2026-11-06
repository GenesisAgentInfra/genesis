"""Two presentations of the same validated semantic behavior comparison."""


def render_behavior_review(report, *, detailed=False):
    from .report_review import _text

    review = getattr(report, "behavior_review", None)
    if review is None:
        return []
    lines = ["", "## 业务行为前后变化", "", "以下是根据代码推导的行为变化，尚未经运行验证。"]
    if detailed:
        lines.append(f"- 覆盖状态：{review.coverage.status.value}；格式版本：{review.version}")
        if review.coverage.reason:
            lines.append(f"- 范围说明：{_text(review.coverage.reason)}")
        if review.coverage.analyzed_scope:
            lines.append(f"- 已分析范围：{_text(review.coverage.analyzed_scope)}")
    elif review.coverage.status != "analyzed":
        lines.append("本次只能解释已取得代码中的部分场景；完整范围与缺失原因见详细报告。")
    if not review.changes:
        lines.append("本次没有生成有足够依据的前后行为对照；请继续查看风险与分析边界。")
    for index, change in enumerate(review.changes, 1):
        lines.extend(("", f"### {index}. {_text(change.scenario)}", ""))
        if detailed:
            lines.append(f"- 变化 ID：{_text(change.change_id)}；依据：semantic_inference")
        for label, value in (
            ("触发条件", change.condition),
            ("改动前", change.before or "该版本材料不足，无法判断。"),
            ("改动后", change.after or "该版本材料不足，无法判断。"),
            ("为什么会这样", change.explanation),
            ("实际影响", change.impact),
            ("仍然保留的行为", change.preserved_behavior),
        ):
            if value:
                lines.append(f"- {label}：{_text(value)}")
        for limitation in change.limitations:
            lines.append(f"- 尚不确定：{_text(limitation)}")
        if detailed:
            for label, ids in (
                ("base 证据", change.before_evidence_ids),
                ("head 证据", change.after_evidence_ids),
                ("解释证据", change.evidence_ids),
                ("关联发现", change.finding_ids),
            ):
                if ids:
                    lines.append(f"- {label}：" + ", ".join(_text(ident) for ident in ids))
        else:
            catalog = {ref.evidence_id: ref for ref in report.evidence}
            ids = tuple(
                dict.fromkeys(
                    (*change.before_evidence_ids, *change.after_evidence_ids, *change.evidence_ids)
                )
            )
            links = []
            for ident in ids:
                ref = catalog[ident]
                label = _text(f"{ref.side.value} {ref.path}:{ref.range.start_line}")
                links.append(f"[{label}](report.md#evidence-{ident})")
            lines.append("- 核对位置：" + "；".join(links))
    return lines

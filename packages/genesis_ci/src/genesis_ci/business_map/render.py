"""Minimal renderer: one static HTML file and a Markdown summary.

No script and no external resource: the page works from `file://` and can be read
offline. Every name, label and source excerpt is escaped as text, because it comes
from the analyzed repository or from an agent and must never be read as markup.

This is a plain outline, not a graph layout. Steps are listed in order and each
shows where control goes next.

In a change session the page is still the map. Each change is shown on the step it
belongs to, flows with changes are open and listed first in an index, and only what
has no place on the map is listed apart.
"""

from __future__ import annotations

from html import escape

from genesis_contracts.business_map import BusinessMap, MapFlow
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle

STYLE = """
:root { color-scheme: light dark; --bg: #fafafa; --fg: #1c1c1e; --muted: #6b6b70;
  --line: #dcdce0; --card: #ffffff; --accent: #2f5fd0; --warn: #9a5b00; --bad: #b3261e; }
@media (prefers-color-scheme: dark) { :root { --bg: #151517; --fg: #e9e9ec; --muted: #9a9aa2;
  --line: #303036; --card: #1d1d21; --accent: #8fb0ff; --warn: #e0a84a; --bad: #ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main, header { max-width: 980px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 28px 0 8px; }
p { margin: 4px 0; } a { color: var(--accent); text-decoration: none; }
code, pre { font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: var(--muted); } .status { font-weight: 600; }
.status.partial, .tag.warn { color: var(--warn); } .tag.bad { color: var(--bad); }
.tag { font-size: 12px; border: 1px solid var(--line); border-radius: 999px; padding: 0 8px;
  margin-left: 6px; color: var(--muted); white-space: nowrap; }
details.flow { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  margin: 8px 0; padding: 0 14px; }
details.flow > summary { cursor: pointer; padding: 10px 0; font-weight: 600; }
ol.steps { list-style: none; margin: 0; padding: 0 0 10px; }
li.step { border-top: 1px solid var(--line); padding: 8px 0; }
.kind { display: inline-block; min-width: 68px; font-size: 12px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .03em; }
.name { overflow-wrap: anywhere; } ul.next { margin: 2px 0 0 72px; padding: 0; list-style: none;
  font-size: 13px; color: var(--muted); }
ul.next .branch { color: var(--fg); border: 1px solid var(--line); border-radius: 4px;
  padding: 0 5px; margin-right: 4px; }
details.evidence { margin: 4px 0 0 72px; font-size: 13px; }
details.evidence > summary { cursor: pointer; color: var(--muted); }
pre { margin: 4px 0; padding: 8px 10px; background: var(--bg); border: 1px solid var(--line);
  border-radius: 6px; overflow-x: auto; white-space: pre; }
ul.plain { margin: 4px 0; padding-left: 20px; }
li.change { margin: 10px 0; padding: 8px 0; border-top: 1px solid var(--line); list-style: none; }
code.side { white-space: pre-wrap; overflow-wrap: anywhere; }
.delta { margin: 6px 0 6px 72px; padding: 6px 10px; border-left: 3px solid var(--warn);
  background: var(--bg); border-radius: 0 6px 6px 0; }
.delta p, .delta details.evidence { margin-left: 0 !important; }
.delta .what { font-size: 12px; color: var(--warn); text-transform: uppercase;
  letter-spacing: .03em; }
li.step.removed .name { text-decoration: line-through; color: var(--muted); }
ul.plain .delta { margin-left: 0; }
"""

STAGE_TEXT = {
    "skeleton": "Static structure. Not yet synthesized into business steps.",
    "synthesized": "Synthesized by a coding agent from the code evidence shown.",
}
PLANNED_TEXT = (
    "Named by the plan and not described yet. The steps below are the static code "
    "structure, not business steps."
)
VERDICT_TEXT = {
    "covered": "covered",
    "reached_only": "reached only",
    "not_reached": "not reached",
    "unknown": "unknown",
}


VERDICT_LEGEND = (
    "Test verdicts come from reading source, never from running tests. covered: a test takes "
    "the changed path and asserts on the result. reached only: tests call the code but miss "
    "the changed path or assert nothing about it. not reached: no test gets to it. "
    "unknown: could not be told."
)


def compared(report: ChangeReport) -> str:
    """What the report compares, in the user's own names where they gave any."""

    def name(ref, revision, fallback):
        short = (revision or "")[:12] if not (revision or "").startswith("worktree:") else ""
        if ref and short and not short.startswith(ref[:12]):
            return f"{ref} ({short})"
        return ref or short or fallback

    base = name(report.base_ref, report.base_revision, "base")
    head = name(report.head_ref, report.head_revision, "the working tree")
    return f"Compared {base} with {head}."


def _tag(text: str, tone: str = "") -> str:
    return f'<span class="tag {tone}">{escape(text)}</span>'


def _evidence(evidence_ids, refs, excerpts, *, sided: bool = False) -> str:
    parts = []
    for evidence_id in evidence_ids:
        ref = refs.get(evidence_id)
        if ref is None:
            continue
        lines = (
            str(ref.range.start_line)
            if ref.range.start_line == ref.range.end_line
            else f"{ref.range.start_line}-{ref.range.end_line}"
        )
        side = ("before · " if ref.side == "base" else "after · ") if sided else ""
        where = escape(f"{side}{ref.path}:{lines}")
        text = excerpts.get(evidence_id)
        if text is None:
            parts.append(f'<p class="muted" style="margin-left:72px">{where}</p>')
        else:
            parts.append(
                f'<details class="evidence"><summary>{where}</summary>'
                f"<pre>{escape(text)}</pre></details>"
            )
    return "".join(parts)


def _inside_text(item) -> str:
    """What a step leaves out when it stands for a whole function, in a few words."""
    counts = [
        f"{count} {name}{'s' * (count != 1)}"
        for count, name in (
            (item.conditions, "condition"),
            (item.loops, "loop"),
            (item.results, "result"),
        )
        if count
    ]
    name = item.symbol_id.partition("#")[2]
    text = f"{name}: " + (", ".join(counts) + " inside" if counts else "nothing to decide inside")
    if item.reaches:
        text += "; reaches " + ", ".join(item.reaches)
    return text


def _side_text(part) -> str:
    if part is None:
        return "<em>absent</em>"
    return f'<code class="side">{escape(part.text)}</code>'


def _change_card(item, refs, excerpts, reason: str | None, *, anchor: bool = True) -> str:
    """One change, as it is shown on the step it belongs to."""
    body = (
        f'<p><span class="what">{escape(item.kind.value.replace("_", " "))}</span></p>'
        f"<p>{_side_text(item.before)} → {_side_text(item.after)}</p>"
    )
    if item.detail:
        body += f"<p>{escape(item.detail)}</p>"
    if reason:
        body += f'<p class="muted">{escape(reason)}</p>'
    if item.explanation:
        body += f"<p>{escape(item.explanation.summary)}"
        if item.explanation.effect:
            body += " " + escape(item.explanation.effect)
        body += _tag("agent explanation") + "</p>"
    if item.tests:
        tests = item.tests
        basis = ", ".join(value.value.replace("_", " ") for value in tests.basis)
        execution = (
            "execution data imported"
            if tests.execution_data == "imported"
            else "no execution data collected"
        )
        body += (
            f"<p>Tests: <strong>{escape(VERDICT_TEXT[tests.verdict.value])}</strong>"
            f"{_tag(basis) if basis else ''}{_tag(execution)}</p>"
        )
        if tests.note:
            body += f'<p class="muted">{escape(tests.note)}</p>'
        for case in tests.items:
            body += f'<p class="muted" style="margin:2px 0 0 0">{escape(case.test_id)}</p>'
            body += _evidence(case.evidence_ids, refs, excerpts)
    sides = [
        *(item.before.evidence_ids if item.before else ()),
        *(item.after.evidence_ids if item.after else ()),
    ]
    identity = f' id="{escape(item.change_id)}"' if anchor else ""
    return (
        f'<div class="delta"{identity}>{body}{_evidence(sides, refs, excerpts, sided=True)}</div>'
    )


class _Overlay:
    """The changes of a report, sorted by where they sit on the map."""

    def __init__(self, report: ChangeReport, refs, excerpts):
        self.report = report
        # Change cards by step, and by flow for steps that no longer exist.
        self.on_step: dict[str, list[str]] = {}
        self.removed: dict[str, list[tuple[str, str]]] = {}
        self.count: dict[str, int] = {}
        self.off_map: list[str] = []
        self.reaching = {item.flow_id: item for item in report.possibly_affected}
        self.finding_status = {
            item.finding.finding_id: item.status for item in report.finding_changes
        }
        for item in report.changes:
            if item.projection.status == "unassigned":
                self.off_map.append(
                    f"<li>{_change_card(item, refs, excerpts, item.projection.reason)}</li>"
                )
                continue
            for index, target in enumerate((item.projection, *item.other_projections)):
                card = _change_card(item, refs, excerpts, target.reason, anchor=index == 0)
                self.count[target.flow_id] = self.count.get(target.flow_id, 0) + 1
                if target.status == "projected":
                    self.on_step.setdefault(target.step_id, []).append(card)
                else:
                    self.removed.setdefault(target.flow_id, []).append(
                        (target.removed_step.name, card)
                    )


def _flow(flow: MapFlow, refs, excerpts, findings, opened: bool, overlay=None) -> str:
    names = {step.step_id: step.name for step in flow.steps}
    outgoing: dict[str, list] = {}
    for edge in flow.edges:
        outgoing.setdefault(edge.source, []).append(edge)
    code = flow.stage == "skeleton"
    on_step = overlay.on_step if overlay else {}
    items = []
    for step in flow.steps:
        name = escape(step.name)
        tags = "".join(
            [
                _tag(step.resolution.value, "warn") if step.resolution != "resolved" else "",
                _tag("changed", "warn") if step.step_id in on_step else "",
                _tag("not expanded") if step.unexpanded else "",
                *(
                    _tag(f"{findings[fid].severity.value} risk", "bad")
                    for fid in step.finding_ids
                    if fid in findings
                ),
            ]
        )
        nexts = "".join(
            "<li>"
            + (
                f'<span class="branch">{escape(edge.condition.label)}</span>'
                if edge.condition
                else (f'<span class="branch">{escape(edge.label)}</span>' if edge.label else "")
            )
            + ("↺ " if edge.relation == "loop" else "→ ")
            + f'<a href="#{escape(edge.target)}">{escape(names[edge.target])}</a>'
            + (_tag(edge.resolution.value, "warn") if edge.resolution != "resolved" else "")
            + "</li>"
            for edge in outgoing.get(step.step_id, ())
        )
        reason = (
            f'<p class="muted" style="margin-left:72px">{escape(step.reason)}</p>'
            if step.reason
            else ""
        )
        items.append(
            f'<li class="step {escape(step.kind.value)}" id="{escape(step.step_id)}">'
            f'<span class="kind">{escape(step.kind.value)}</span>'
            + (f'<code class="name">{name}</code>' if code else f'<span class="name">{name}</span>')
            + tags
            # What this change did here, before where control goes next.
            + "".join(on_step.get(step.step_id, ()))
            + (f'<ul class="next">{nexts}</ul>' if nexts else "")
            + reason
            # One step for a whole function: say how much is inside and why that is enough.
            + "".join(
                f'<p class="muted" style="margin-left:72px">Not expanded · '
                f"{escape(_inside_text(item))}"
                + (f" · {escape(item.reason)}" if item.reason else "")
                + "</p>"
                for item in step.unexpanded
            )
            + _evidence(step.evidence_ids, refs, excerpts)
            + "</li>"
        )
    # Steps the change removed have no place among the head steps; they close the flow.
    for name, card in overlay.removed.get(flow.flow_id, ()) if overlay else ():
        items.append(
            '<li class="step removed"><span class="kind">removed</span>'
            f'<span class="name">{escape(name)}</span>{_tag("removed", "warn")}{card}</li>'
        )
    entry = flow.entries[0]
    meta = f"{len(flow.steps)} steps · {entry.kind.value.replace('_', ' ')}"
    if entry.detection != "adapter":
        meta += " · candidate entry"
    left_out = "".join(
        f"<li>{escape(item.reason.value.replace('_', ' '))}: "
        + (escape(item.note) if item.note else f"<code>{escape(item.anchor)}</code>")
        + "</li>"
        for item in flow.omitted
    )
    notes = "".join(f"<li>{escape(item.message)}</li>" for item in flow.limitations)
    if flow.accounting.unaccounted:
        notes += f"<li>{flow.accounting.unaccounted} code facts are not accounted for.</li>"
    count = overlay.count.get(flow.flow_id, 0) if overlay else 0
    reaching = overlay.reaching.get(flow.flow_id) if overlay else None
    marks = _tag(f"{count} change{'s' * (count != 1)}", "warn") if count else ""
    if flow.name_from_plan:
        marks += _tag("not described yet")
    if flow.tier != "primary":
        marks += _tag("supporting")
    reach = ""
    if reaching is not None:
        marks += _tag("possibly affected", "warn")
        links = ", ".join(
            f'<a href="#{escape(change_id)}">change {index}</a>'
            for index, change_id in enumerate(reaching.change_ids, 1)
        )
        reach = f'<p class="muted">{escape(reaching.reason)} See {links}.</p>'
    return (
        f'<details class="flow" id="{escape(flow.flow_id)}"{" open" if opened else ""}>'
        f"<summary>{escape(flow.name)}"
        f'<span class="tag">{escape(meta)}</span>'
        + marks
        + "</summary>"
        + (f"<p>{escape(flow.summary)}</p>" if flow.summary else "")
        + '<p class="muted">'
        + escape(PLANNED_TEXT if flow.name_from_plan else STAGE_TEXT[flow.stage.value])
        + "</p>"
        + reach
        + f'<ol class="steps">{"".join(items)}</ol>'
        + (
            f'<p class="muted">Left out of the map:</p><ul class="plain">{left_out}</ul>'
            if left_out
            else ""
        )
        + (f'<ul class="plain muted">{notes}</ul>' if notes else "")
        + "</details>"
    )


def _change_header(report: ChangeReport, overlay: _Overlay, flows) -> str:
    """What was compared and which flows the changes sit on, as an index into the map."""
    placed = sum(1 for item in report.changes if item.projection.status != "unassigned")
    status = "complete" if report.analysis_status == "complete" else "partial"
    index = "".join(
        f'<li><a href="#{escape(flow_id)}">{escape(flows[flow_id].name)}</a>: '
        f"{count} change{'s' * (count != 1)}</li>"
        for flow_id, count in overlay.count.items()
    )
    notes = "".join(f"<li>{escape(item.message)}</li>" for item in report.limitations)
    apart = len(overlay.off_map)
    return (
        f"<h2>Changes on the map{_tag(status, '' if status == 'complete' else 'warn')}</h2>"
        f'<p class="muted">{escape(compared(report))}</p>'
        f'<p class="muted">{len(report.changes)} changes · {placed} on the map in '
        f"{len(overlay.count)} flow{'s' * (len(overlay.count) != 1)} · "
        + (f'<a href="#off-map">{apart} not on the map</a>' if apart else "0 not on the map")
        + "</p>"
        + (f'<ul class="plain">{index}</ul>' if index else "<p>No change sits on the map.</p>")
        + f'<p class="muted">{escape(VERDICT_LEGEND)}</p>'
        + (f'<ul class="plain muted">{notes}</ul>' if notes else "")
    )


def _off_map(report: ChangeReport, overlay: _Overlay, refs, excerpts) -> str:
    """What the change set contains that no step of the map can show."""
    removed = "".join(_flow(flow, refs, excerpts, {}, False) for flow in report.removed_flows)
    extra = "".join(
        f"<li>{escape(item.path)} ({escape(item.change)}): {escape(item.reason)}</li>"
        for item in report.unanalyzed_changes
    )
    return (
        (f"<h2>Removed flows</h2>{removed}" if removed else "")
        + (
            f'<h2 id="off-map">Changes not on the map</h2><ul class="plain">'
            f"{''.join(overlay.off_map)}</ul>"
            if overlay.off_map
            else ""
        )
        + (
            f'<h2>Changed files that were not analyzed</h2><ul class="plain">{extra}</ul>'
            if extra
            else ""
        )
    )


def by_tier(flows, flow_ids) -> list[str]:
    """The business processes of a domain before the lookups and upkeep around them."""
    return sorted(flow_ids, key=lambda flow_id: flows[flow_id].tier != "primary")


def render_html(
    business_map: BusinessMap,
    bundle: EvidenceBundle | None = None,
    report: ChangeReport | None = None,
) -> str:
    refs = {ref.evidence_id: ref for ref in business_map.evidence}
    if report is not None:
        refs.update((ref.evidence_id, ref) for ref in report.evidence)
    excerpts = {item.evidence_id: item.text for item in (bundle.excerpts if bundle else ())}
    findings = {item.finding_id: item for item in business_map.findings}
    overlay = _Overlay(report, refs, excerpts) if report is not None else None
    flows = {flow.flow_id: flow for flow in business_map.flows}
    names = {step.step_id: step.name for flow in business_map.flows for step in flow.steps}

    def shown(flow: MapFlow) -> str:
        # With changes on the map, open the flows they sit on and keep the rest folded.
        opened = flow.flow_id in overlay.count if overlay else len(flows) <= 3
        return _flow(flow, refs, excerpts, findings, opened, overlay)

    grouped = {flow_id for domain in business_map.domains for flow_id in domain.flow_ids}
    sections = []
    for domain in business_map.domains:
        label = "grouped by path" if domain.support == "path_grouping" else "business domain"
        body = "".join(shown(flows[flow_id]) for flow_id in by_tier(flows, domain.flow_ids))
        sections.append(f"<section><h2>{escape(domain.name)}{_tag(label)}</h2>{body}</section>")
    loose = [flow for flow in business_map.flows if flow.flow_id not in grouped]
    if loose:
        body = "".join(shown(flow) for flow in loose)
        sections.append(f"<section><h2>Ungrouped</h2>{body}</section>")
    links = "".join(
        f'<li><a href="#{escape(link.source.flow_id)}">{escape(flows[link.source.flow_id].name)}</a>'
        f" → {escape(link.name)} → "
        f'<a href="#{escape(link.target.flow_id)}">{escape(flows[link.target.flow_id].name)}</a>'
        f"{_tag(link.relation.value.replace('_', ' '))}"
        f"{_tag(link.resolution, 'warn') if link.resolution != 'resolved' else ''}</li>"
        for link in business_map.links
    )
    status_of = overlay.finding_status if overlay else {}
    risks = "".join(
        f"<li>{_tag(item.severity.value, 'bad')}{_tag(item.source.value.replace('_', ' '))}"
        f"{_tag(status_of[item.finding_id], 'warn') if item.finding_id in status_of else ''} "
        f"{escape(item.statement)}</li>"
        for item in business_map.findings
    )
    notes = "".join(f"<li>{escape(item.message)}</li>" for item in business_map.limitations)
    coverage = business_map.coverage
    status = (
        "Complete within the planned scope"
        if business_map.analysis_status == "complete"
        else "Partial"
    )
    title = "Genesis map" if report is None else "Genesis map with changes"
    about = (
        (
            '<h2>Skipped entries</h2><ul class="plain">'
            + "".join(
                f"<li><code>{escape(item.symbol_id)}</code>: {escape(item.reason)}"
                + (f" - {escape(item.note)}" if item.note else "")
                + "</li>"
                for item in coverage.skipped_entries
            )
            + "</ul>"
            if coverage.skipped_entries
            else ""
        )
        + (f'<h2>How flows connect</h2><ul class="plain">{links}</ul>' if links else "")
        + (f'<h2>Risk findings</h2><ul class="plain">{risks}</ul>' if risks else "")
    )
    body = "".join(sections) + ("" if sections else '<p class="muted">No flow to show.</p>')
    if overlay is None:
        main = about + body
    else:
        # The map comes right after the index of changes; everything else follows it.
        main = (
            _change_header(report, overlay, flows)
            + body
            + _off_map(report, overlay, refs, excerpts)
            + about
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{STYLE}</style></head><body><header>"
        f"<h1>{title}</h1>"
        f'<p class="status {escape(business_map.analysis_status)}">{status}</p>'
        f"<p>{escape(coverage.scope)}</p>"
        f'<p class="muted">{len(business_map.flows)} flows · {len(names)} steps · '
        f"{coverage.entries_total} entries found, {coverage.entries_unhandled} not handled, "
        f"{coverage.entries_skipped} skipped</p>"
        + (f'<ul class="plain">{notes}</ul>' if notes else "")
        + f"</header><main>{main}</main></body></html>\n"
    )


def uncertain_items(business_map: BusinessMap) -> list[str]:
    """Steps and connections the map does not claim as resolved, with their reasons."""
    found = []
    for flow in business_map.flows:
        names = {step.step_id: step.name for step in flow.steps}
        for step in flow.steps:
            if step.resolution != "resolved":
                found.append(
                    f"{flow.name}: {step.name} ({step.resolution.value}) - {step.reason or ''}"
                )
        for edge in flow.edges:
            if edge.resolution != "resolved":
                found.append(
                    f"{flow.name}: {names[edge.source]} -> {names[edge.target]} "
                    f"({edge.resolution.value}) - {edge.reason or ''}"
                )
    for link in business_map.links:
        if link.resolution != "resolved":
            found.append(f"{link.name} ({link.resolution}) - {link.reason or ''}")
    return found


def _change_lines(business_map: BusinessMap, report: ChangeReport) -> list[str]:
    """The changes as they sit on the map: by flow, then by step."""
    flows = {flow.flow_id: flow for flow in business_map.flows}
    placed = sum(1 for item in report.changes if item.projection.status != "unassigned")

    def told(item, indent: str, reason: str | None) -> list[str]:
        if item.explanation:
            text = item.explanation.summary
            if item.explanation.effect:
                text += " " + item.explanation.effect
        else:
            text = f"{item.kind.value.replace('_', ' ')} in {item.symbol_id}"
        verdict = f" (tests: {VERDICT_TEXT[item.tests.verdict.value]})" if item.tests else ""
        lines = [f"{indent}- {text}{verdict}"]
        if reason:
            # On the map this says how the step was chosen; off it, why there is none.
            placed = item.projection.status != "unassigned"
            lines.append(f"{indent}  - {'placement: ' if placed else ''}{reason}")
        if item.tests and item.tests.note and item.explanation:
            lines.append(f"{indent}  - {item.tests.note}")
        if item.tests and item.tests.items:
            tests = ", ".join(case.test_id for case in item.tests.items)
            lines.append(f"{indent}  - tests: {tests}")
        return lines

    on_step: dict[tuple[str, str], list] = {}
    removed: dict[str, list] = {}
    apart = []
    for item in report.changes:
        if item.projection.status == "unassigned":
            apart.append(item)
        for target in (item.projection, *item.other_projections):
            if target.status == "projected":
                on_step.setdefault((target.flow_id, target.step_id), []).append((item, target))
            elif target.status == "removed_step":
                removed.setdefault(target.flow_id, []).append((item, target))
    touched = list(dict.fromkeys([*(flow_id for flow_id, _ in on_step), *removed]))
    lines = [
        "",
        "## Changes on the map",
        "",
        f"- {compared(report)}",
        f"- Status: {report.analysis_status}",
        f"- {len(report.changes)} changes, {placed} on the map in {len(touched)} flows, "
        f"{len(apart)} not on the map",
    ]
    lines += [f"- Limitation: {item.message}" for item in report.limitations]
    lines += ["", VERDICT_LEGEND]
    for flow in business_map.flows:
        if flow.flow_id not in touched:
            continue
        lines += ["", f"### {flow.name}", ""]
        for step in flow.steps:
            found = on_step.get((flow.flow_id, step.step_id))
            if found:
                lines.append(f"- {step.name}")
                for item, target in found:
                    lines += told(item, "  ", target.reason)
        for item, target in removed.get(flow.flow_id, ()):
            lines.append(f"- removed: {target.removed_step.name}")
            lines += told(item, "  ", None)
    if apart:
        lines += ["", "## Changes not on the map", ""]
        for item in apart:
            lines += told(item, "", item.projection.reason)
    if report.finding_changes:
        lines += ["", "## Risk findings touched by the changes", ""]
        lines += [f"- {item.status}: {item.finding.statement}" for item in report.finding_changes]
    if report.possibly_affected:
        lines += ["", "## Flows that can reach changed code", ""]
        lines += [
            f"- {flows[item.flow_id].name}: {len(item.change_ids)} changes"
            for item in report.possibly_affected
        ]
    if report.removed_flows:
        lines += ["", "## Removed flows", ""]
        lines += [f"- {flow.name}" for flow in report.removed_flows]
    if report.unanalyzed_changes:
        lines += ["", "## Changed files not analyzed", ""]
        lines += [
            f"- {item.path} ({item.change}): {item.reason}" for item in report.unanalyzed_changes
        ]
    return lines


def render_summary(business_map: BusinessMap, report: ChangeReport | None = None) -> str:
    coverage = business_map.coverage
    flows = {flow.flow_id: flow for flow in business_map.flows}
    lines = [
        "# Genesis map" if report is None else "# Genesis map with changes",
        "",
        f"- Status: {business_map.analysis_status}",
        f"- Scope: {coverage.scope}",
        f"- Flows: {len(business_map.flows)}",
        f"- Entries: {coverage.entries_total} found, {coverage.entries_skipped} skipped, "
        f"{coverage.entries_unhandled} not handled",
        f"- Tasks: {coverage.tasks_validated} accepted, {coverage.tasks_pending} pending, "
        f"{coverage.tasks_failed} failed",
    ]
    lines += [f"- Limitation: {item.message}" for item in business_map.limitations]
    touched: set[str] = set()
    if report is not None:
        # In a change session the changes are the result; the map is what they sit on.
        lines[2] = f"- Map status: {business_map.analysis_status}"
        lines += [*_change_lines(business_map, report), "", "# Map"]
        touched = {
            target.flow_id
            for item in report.changes
            for target in (item.projection, *item.other_projections)
            if target.flow_id
        }
    grouped = {flow_id for domain in business_map.domains for flow_id in domain.flow_ids}
    sections = [(domain.name, domain.flow_ids) for domain in business_map.domains]
    loose = tuple(flow_id for flow_id in flows if flow_id not in grouped)
    if loose:
        sections.append(("Ungrouped", loose))
    for name, flow_ids in sections:
        lines += ["", f"## {name}", ""]
        for flow_id in by_tier(flows, flow_ids):
            flow = flows[flow_id]
            left = flow.accounting.unaccounted
            note = f", {left} facts not accounted for" if left else ""
            mark = ", changed" if flow_id in touched else ""
            role = ", supporting" if flow.tier != "primary" else ""
            # A flow the plan named has no business steps yet; its step count is code.
            state = (
                "not described yet"
                if flow.name_from_plan
                else f"{len(flow.steps)} steps, {flow.stage.value}"
            )
            told = f": {flow.summary}" if flow.summary and flow.name_from_plan else ""
            lines.append(f"- {flow.name}{told} ({state}{role}{note}{mark})")
    uncertain = uncertain_items(business_map)
    if uncertain:
        lines += ["", "## Uncertain", ""] + [f"- {item}" for item in uncertain]
    folded = [
        f"- {flow.name} / {step.name}: {_inside_text(item)}"
        + (f" - {item.reason}" if item.reason else "")
        for flow in business_map.flows
        for step in flow.steps
        for item in step.unexpanded
        if item.conditions + item.loops + item.results >= 3
    ]
    if folded:
        # A reader should see where one step stands for a function with decisions inside.
        lines += ["", "## Not expanded", ""] + folded
    if business_map.findings:
        lines += ["", "## Risk findings", ""]
        lines += [
            f"- {item.severity.value} ({item.source.value.replace('_', ' ')}): {item.statement}"
            for item in business_map.findings
        ]
    if coverage.skipped_entries:
        lines += ["", "## Skipped entries", ""]
        lines += [
            f"- {item.symbol_id}: {item.reason}" + (f" - {item.note}" if item.note else "")
            for item in coverage.skipped_entries
        ]
    return "\n".join(lines) + "\n"

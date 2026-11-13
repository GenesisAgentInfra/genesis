"""Connect planned flow entries using call facts, never shared changes or names.

Only calls owned by the source entry are considered. A helper expanded into two
flows does not establish a call between those flows. Awaiting a function is still
a call; it does not establish a queued task or an event delivery.
"""

from __future__ import annotations

import hashlib

from genesis_contracts.facts import FactKind, FactSet


def flow_links(flows: list[dict], facts: FactSet) -> list[dict]:
    entries: dict[str, list[tuple[dict, dict]]] = {}
    for flow in flows:
        for entry in flow.get("entries", []):
            entries.setdefault(entry["symbol_id"], []).append((flow, entry))
    by_anchor = {fact.fingerprint: fact for fact in facts.facts if fact.side == "head"}
    links = []
    for fact in facts.facts:
        if fact.side != "head" or fact.kind != FactKind.call or not fact.target:
            continue
        if fact.target.status not in {"resolved", "candidate"}:
            continue
        for source, _ in entries.get(fact.symbol_id, []):
            source_step = next(
                (
                    step
                    for step in source.get("steps", [])
                    if fact.fingerprint in step.get("anchors", [])
                ),
                None,
            )
            for symbol in fact.target.targets:
                for target, entry in entries.get(symbol, []):
                    if source["flow_id"] == target["flow_id"]:
                        continue
                    if not fact.evidence_ids or not entry.get("evidence_ids"):
                        continue
                    target_step = next(
                        (
                            step
                            for step in target.get("steps", [])
                            if step["kind"] == "trigger"
                            and set(step.get("evidence_ids", [])) & set(entry["evidence_ids"])
                        ),
                        None,
                    )
                    # Multiple possible callees remain candidates even if an adapter
                    # reports the call expression itself as resolved.
                    candidate = fact.target.status != "resolved" or len(fact.target.targets) != 1
                    key = f"{source['flow_id']}:{fact.fingerprint}:{target['flow_id']}"
                    guards = [
                        by_anchor[g.fingerprint].text
                        for g in fact.guards
                        if g.fingerprint in by_anchor
                    ]
                    reason = fact.target.reason if candidate else None
                    if candidate and not reason:
                        reason = "The call has multiple possible targets."
                    if guards:
                        conditions = "; ".join(
                            f"{by_anchor[g.fingerprint].text} [{g.branch}]"
                            for g in fact.guards
                            if g.fingerprint in by_anchor
                        )
                        reason = f"{reason + ' ' if reason else ''}{conditions}"
                    links.append(
                        {
                            "link_id": "link_" + hashlib.sha256(key.encode()).hexdigest()[:20],
                            "source": {
                                "flow_id": source["flow_id"],
                                **({"step_id": source_step["step_id"]} if source_step else {}),
                            },
                            "target": {
                                "flow_id": target["flow_id"],
                                **({"step_id": target_step["step_id"]} if target_step else {}),
                            },
                            "relation": "call",
                            "name": target["name"],
                            "support": "static_fact",
                            "resolution": "candidate" if candidate else "resolved",
                            **({"reason": reason[:2000]} if reason else {}),
                            "anchors": [fact.fingerprint],
                            "source_evidence_ids": list(fact.evidence_ids),
                            "target_evidence_ids": entry["evidence_ids"],
                        }
                    )
    return sorted(links, key=lambda link: link["link_id"])

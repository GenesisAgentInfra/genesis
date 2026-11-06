"""Evidence and linkage checks shared by the service, CLI and public reports."""


def validate_behavior_review(review, evidence, findings):
    if review is None:
        return
    catalogue = {item.evidence_id: item for item in evidence}
    finding_ids = {item.finding_id for item in findings}
    seen = set()
    for change in review.changes:
        if change.change_id in seen:
            raise ValueError("duplicate behavior change_id")
        seen.add(change.change_id)
        if not set(change.finding_ids) <= finding_ids:
            raise ValueError("behavior change refers to unknown finding_id")
        for side in ("base", "head"):
            ids = change.before_evidence_ids if side == "base" else change.after_evidence_ids
            if any(
                ident not in catalogue
                or catalogue[ident].kind != "code"
                or catalogue[ident].side != side
                for ident in ids
            ):
                raise ValueError("behavior comparison must cite code from its described side")
        if any(ident not in catalogue for ident in change.evidence_ids):
            raise ValueError("behavior explanation refers to unselected evidence")
        if not any(catalogue[ident].kind == "code" for ident in change.evidence_ids):
            raise ValueError("behavior explanation requires code evidence")

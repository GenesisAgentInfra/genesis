"""Evidence bundle: the source excerpts behind the evidence a map or report cites.

Draft contract. The bundle is private by default because it contains source text.
A share-mode bundle carries no excerpts; readers then see paths and line ranges only.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .models import ContractModel, EvidenceRef, SourceExcerpt


class EvidenceBundle(ContractModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    snapshot_id: str = Field(min_length=1)
    share_mode: bool = False
    excerpts: tuple[SourceExcerpt, ...] = ()

    @model_validator(mode="after")
    def share_mode_has_no_source(self) -> EvidenceBundle:
        ids = [item.evidence_id for item in self.excerpts]
        if len(ids) != len(set(ids)):
            raise ValueError("an evidence reference has at most one excerpt")
        if self.share_mode and self.excerpts:
            raise ValueError("a share-mode bundle carries no source excerpts")
        return self


def validate_evidence_bundle(bundle: EvidenceBundle, evidence: tuple[EvidenceRef, ...]) -> None:
    """Check a bundle against the evidence catalog of the document it accompanies."""
    by_id = {ref.evidence_id: ref for ref in evidence}
    if any(ref.snapshot_id != bundle.snapshot_id for ref in evidence):
        raise ValueError("the bundle and the evidence come from different snapshots")
    excerpts = {item.evidence_id: item for item in bundle.excerpts}
    if excerpts.keys() - by_id.keys():
        raise ValueError("an excerpt belongs to no cited evidence reference")
    if not bundle.share_mode and by_id.keys() - excerpts.keys():
        raise ValueError("a private bundle has an excerpt for every cited evidence reference")
    for evidence_id, excerpt in excerpts.items():
        digest = "sha256:" + hashlib.sha256(excerpt.text.encode("utf-8")).hexdigest()
        if digest != by_id[evidence_id].snippet_digest:
            raise ValueError("an excerpt does not match its evidence digest")

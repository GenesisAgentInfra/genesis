"""The interactive map page: a prebuilt single-file viewer filled with session data.

The viewer is a React app under `viewer/` in the repository, built into one HTML file
at `assets/viewer/index.html`. Rendering only puts the session's data into that file;
nothing is fetched when the page opens, so it works from `file://` and offline.

The data travels as JSON inside a `<script type="application/json">` element. Every
`<`, `>` and `&` is escaped, so text from the analysed repository or an agent can never
close the element or be read as markup; the viewer renders all of it as text.
"""

from __future__ import annotations

import json
from importlib.resources import files

from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle

DATA_SLOT = '<script id="genesis-data" type="application/json">null</script>'
_ESCAPES = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    " ": "\\u2028",
    " ": "\\u2029",
}


def view_payload(
    business_map: BusinessMap,
    bundle: EvidenceBundle | None = None,
    report: ChangeReport | None = None,
) -> dict:
    """What the viewer reads: the map, the change report and any source excerpts."""
    return {
        "format_version": 1,
        "share": bundle is None or bundle.share_mode,
        "map": business_map.model_dump(mode="json", exclude_none=True),
        "report": None if report is None else report.model_dump(mode="json", exclude_none=True),
        "excerpts": {item.evidence_id: item.text for item in (bundle.excerpts if bundle else ())},
    }


def _embed(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "".join(_ESCAPES.get(char, char) for char in text)


def viewer_template() -> str:
    return (files("genesis_ci") / "assets" / "viewer" / "index.html").read_text(encoding="utf-8")


def render_view(
    business_map: BusinessMap,
    bundle: EvidenceBundle | None = None,
    report: ChangeReport | None = None,
) -> str:
    template = viewer_template()
    if template.count(DATA_SLOT) != 1:
        raise ValueError("the viewer template has no single data slot; rebuild viewer/")
    filled = DATA_SLOT.replace("null", _embed(view_payload(business_map, bundle, report)))
    return template.replace(DATA_SLOT, filled)

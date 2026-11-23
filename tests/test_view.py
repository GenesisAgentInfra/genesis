"""The interactive viewer page: data travels as inert JSON inside the prebuilt template."""

import json
import re
from hashlib import sha256
from pathlib import Path

import pytest
from genesis_ci.business_map.view import DATA_SLOT, render_view, viewer_template
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.change_report import ChangeReport
from genesis_contracts.evidence_bundle import EvidenceBundle
from test_business_map_contract import SAMPLES
from test_git_snapshot import commit, write
from test_map_cli import APP, prepared, run

CHANGE = SAMPLES / "change"
SLOT = re.compile(r'<script id="genesis-data" type="application/json">(.*?)</script>', re.S)


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    monkeypatch.setenv("GENESIS_NO_BROWSER", "1")


def change_sample():
    head = BusinessMap.model_validate_json((CHANGE / "business-map.json").read_text())
    report = ChangeReport.model_validate_json((CHANGE / "change-report.json").read_text())
    bundle = EvidenceBundle.model_validate_json((CHANGE / "evidence-bundle.json").read_text())
    return head, bundle, report


def embedded(page: str) -> dict:
    found = SLOT.findall(page)
    assert len(found) == 1
    return json.loads(found[0])


def test_template_ships_in_the_package_with_one_empty_data_slot():
    template = viewer_template()
    assert template.count(DATA_SLOT) == 1
    # Offline: nothing is loaded from the network when the page opens.
    assert not re.search(r'(?:src|href)="(?:https?:)?//', template)


def test_every_page_carries_the_current_third_party_notices():
    # A view.html or view.share.html passed on alone must still carry the notices of the
    # code compiled into it, and they must be the ones in the repository now.
    notices = (Path(__file__).resolve().parents[1] / "THIRD_PARTY_NOTICES.md").read_text()
    head = viewer_template().split("</head>", 1)[0]
    comment = notices.replace("-->", "- ->").replace("<!--", "<! --")
    assert head.startswith(f'<!doctype html>\n<html lang="en">\n  <head>\n    <!--\n{comment}')
    assert "Copyright (c) Meta Platforms" in head


def test_view_carries_the_map_the_report_and_the_excerpts():
    head, bundle, report = change_sample()
    payload = embedded(render_view(head, bundle, report))
    assert payload["share"] is False
    assert payload["map"] == head.model_dump(mode="json", exclude_none=True)
    assert payload["report"] == report.model_dump(mode="json", exclude_none=True)
    assert payload["excerpts"] == {item.evidence_id: item.text for item in bundle.excerpts}


def test_neither_page_carries_the_code_the_map_was_read_from():
    head, bundle, report = change_sample()
    data = head.model_dump(mode="json", exclude_none=True)
    revision = "f00d" * 10
    files = {ref.path: "sha256:" + sha256(ref.path.encode()).hexdigest() for ref in head.evidence}
    source = {
        "revision": revision,
        "worktree_dirty": True,
        "integrity_status": "partial",
        "files": files,
    }
    sourced = BusinessMap.model_validate({**data, "source": source})
    # The page has no use for it; a reader finds it in business-map.json. The commit is
    # named only in the links to GitHub.
    for page in (render_view(sourced, bundle, report), render_view(sourced, None, report)):
        assert embedded(page)["map"] == data
        assert revision not in page and "worktree_dirty" not in page
        assert not any(digest in page for digest in files.values())


def test_share_view_carries_no_source_excerpts():
    head, _, report = change_sample()
    payload = embedded(render_view(head, None, report))
    assert payload["share"] is True and payload["excerpts"] == {}


def test_text_from_the_repository_cannot_close_the_data_element():
    head, bundle, report = change_sample()
    hostile = "</script><img src=x onerror=alert(1)>&amp; "
    data = head.model_dump(mode="json", exclude_none=True)
    data["flows"][0]["name"] = hostile
    page = render_view(BusinessMap.model_validate(data), bundle, report)
    assert "<img src=x" not in page and " " not in page
    assert embedded(page)["map"]["flows"][0]["name"] == hostile


def test_render_writes_the_viewer_beside_the_outline(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    session = prepared(source_repo, "--head", "HEAD")["session_id"]
    output = json.loads(run("render", "--repo", str(source_repo), "--session", session).stdout)
    latest = source_repo / ".genesis" / "out" / "latest"
    assert output["view"] == str(latest / "view.html") and output["opened"] is False
    assert embedded((latest / "view.html").read_text())["map"]["flows"][0]["name"]
    shared = json.loads(
        run("render", "--repo", str(source_repo), "--session", session, "--share").stdout
    )
    assert shared["view"] == str(latest / "view.share.html")
    assert embedded((latest / "view.share.html").read_text())["excerpts"] == {}


SKILL = (
    Path(__file__).resolve().parents[1]
    / "packages/genesis_ci/src/genesis_ci/assets/skills/genesis/SKILL.md"
)


def test_the_skill_names_every_page_render_writes(source_repo):
    write(source_repo, "app.py", APP)
    commit(source_repo)
    session = prepared(source_repo, "--head", "HEAD")["session_id"]
    for extra in ((), ("--share",)):
        assert run(
            "render", "--repo", str(source_repo), "--session", session, *extra
        ).exit_code in (
            0,
            2,
        )
    latest = source_repo / ".genesis" / "out" / "latest"
    written = {path.name for path in latest.glob("*.html")}
    named = set(re.findall(r"\b(?:view|graph)(?:\.share)?\.html\b", SKILL.read_text()))
    assert named == written == {"view.html", "graph.html", "view.share.html", "graph.share.html"}


def test_open_shows_the_viewer_and_not_the_outline(source_repo, monkeypatch):
    import webbrowser

    write(source_repo, "app.py", APP)
    commit(source_repo)
    session = prepared(source_repo, "--head", "HEAD")["session_id"]
    monkeypatch.delenv("GENESIS_NO_BROWSER")
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda uri: opened.append(uri) or True)
    latest = source_repo / ".genesis" / "out" / "latest"
    for extra, page in (((), "view.html"), (("--share",), "view.share.html")):
        result = run("render", "--repo", str(source_repo), "--session", session, "--open", *extra)
        assert json.loads(result.stdout)["opened"] is True
        assert opened[-1] == (latest / page).as_uri()

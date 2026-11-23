"""What the risk pass is given to read, how a risk names where it comes from, and withdrawal."""

import hashlib

from genesis_ci.business_map.changes import CHANGE_TASK
from genesis_ci.business_map.render import render_html, render_summary
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.workspace import Workspace
from test_change_analysis import by_kind, two_commits
from test_map_loop import codes

EXTRACT = """import os


def extract(url):
    key = os.environ.get("SCRAPE_KEY")
{check}    return fetch(url, key)


def fetch(url, key):
    return url
"""
FEED = """from app.extract import extract


def fetch_all(entries):
    results = []
    for entry in entries:
        results.append(extract(entry))
    return results


def first(entry):
    return extract(entry)
{extra}"""
TEST = """from app.extract import extract


def test_extract():
    assert extract("u") == "u"
"""
BASE = {
    "app/__init__.py": "",
    "app/extract.py": EXTRACT.format(check=""),
    "app/feed.py": FEED.format(extra=""),
    "tests/test_extract.py": TEST,
    "docs/feed.md": "Set SCRAPE_KEY.\n",
}
HEAD = {
    **BASE,
    "app/extract.py": EXTRACT.format(
        check='    if not key:\n        print("no key")\n        return None\n'
    ),
    # A call written by this change is part of the change, not a caller outside it.
    "app/feed.py": FEED.format(extra="\n\ndef again(entry):\n    return extract(entry)\n"),
    "docs/feed.md": "Set SCRAPE_KEY, or nothing is fetched.\n",
}


def test_the_unchanged_callers_of_a_changed_function_are_listed_loops_first(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    check = by_kind(workspace.stored_report(), "condition_added", "#extract").change_id
    [listed] = workspace.context(CHANGE_TASK)["unchanged_callers"]
    assert listed == {
        "symbol_id": "app/extract.py#extract",
        "change_ids": [check],
        "callers": [
            {
                "path": "app/feed.py",
                "line": 7,
                "text": "extract(entry)",
                "loop": "for entry in entries",
            },
            {"path": "app/feed.py", "line": 12, "text": "extract(entry)"},
        ],
        "callers_total": 2,
    }
    # Once nothing waits for an explanation, the result says what to read for risks.
    owed = [
        {"change_id": item.change_id, "summary": "没有密钥时不再抓取。"}
        for item in workspace.stored_report().changes
        if not item.kind.value.startswith("test_")
    ]
    result = workspace.submit(CHANGE_TASK, {"changes": owed})
    assert result["status"] == "accepted" and result["changes_waiting"] == 0
    assert result["read_for_risks"]["unchanged_callers"] == [listed]
    assert result["read_for_risks"]["unanalyzed_changes"] == ["docs/feed.md"]
    # A submission of risks alone carries no reading list.
    risk = {"statement": "x", "change_ids": [check]}
    assert "read_for_risks" not in workspace.submit(CHANGE_TASK, {"risks": [risk]})


# A risk read in docs/feed.md, a changed file Genesis does not analyze.
DOCS_RISK = {
    "statement": "docs/feed.md 现在说没有 SCRAPE_KEY 就什么也抓不到，读者会以为缺密钥时程序报错。",
    "paths": ["docs/feed.md"],
}


def test_a_risk_from_a_changed_file_genesis_did_not_analyze_names_that_file(source_repo):
    # A change in Genesis's own folder is counted by folder, not listed.
    head = {**HEAD, ".genesis/evals/feed.md": "Nothing is fetched without a key.\n"}
    workspace, _ = two_commits(source_repo, BASE, head)
    check = by_kind(workspace.stored_report(), "condition_added", "#extract").change_id
    docs = DOCS_RISK
    both = {**docs, "statement": "缺密钥时只打印一行，文档却说什么也不抓。", "change_ids": [check]}
    result = workspace.submit(CHANGE_TASK, {"risks": [docs, both]})
    assert result["status"] == "accepted" and result["risks"] == 2, result
    report = workspace.stored_report()
    assert "changed_files_left_out" in {item.code for item in report.limitations}
    by_statement = {item.statement: item for item in report.risks}
    alone = by_statement[docs["statement"]]
    assert alone.paths == ("docs/feed.md",) and alone.change_ids == ()
    summary = render_summary(workspace.stored_map(), report)
    # Shown at the file it comes from, not at some unrelated code.
    assert f"- low: {docs['statement']} (at docs/feed.md)" in summary
    assert f"- low: {both['statement']} (at app/extract.py#extract, docs/feed.md)" in summary
    assert "docs/feed.md</span>" in render_html(workspace.stored_map(), None, report)

    def refused(risk):
        result = workspace.submit(CHANGE_TASK, {"risks": [risk]})
        assert result["status"] == "rejected"
        return codes(result)

    # Only a file `unanalyzed_changes` lists: analyzed code is named by its change, and a
    # file left out on purpose is not listed.
    for path in ("app/extract.py", "docs/other.md", ".genesis/evals/feed.md"):
        assert refused({**docs, "paths": [path]}) == [
            ("risks[0].paths[0]", "not_in_unanalyzed_changes")
        ]
    assert refused({"statement": "x"})[0][0] == "risks[0]"
    assert refused({**docs, "paths": ["../feed.md"]})[0][0] == "risks[0]"
    # A risk on changes alone keeps the id it had before files could be named.
    workspace.submit(CHANGE_TASK, {"risks": [{"statement": "x", "change_ids": [check]}]})
    key = "risk_" + hashlib.sha256(f"x\n{check}".encode()).hexdigest()[:16]
    assert key in {item.risk_id for item in workspace.stored_report().risks}


def test_an_accepted_risk_is_withdrawn_by_its_id_and_the_result_names_it(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    check = by_kind(workspace.stored_report(), "condition_added", "#extract").change_id
    code = {"statement": "缺密钥时 extract 返回 None，调用方照样收下。", "change_ids": [check]}
    other = {"statement": "x", "change_ids": [check]}
    result = workspace.submit(CHANGE_TASK, {"risks": [DOCS_RISK, code, other]})
    assert result["risks"] == 3 and "withdrawn" not in result, result
    ids = {item.statement: item.risk_id for item in workspace.stored_report().risks}
    kept = ids[code["statement"]]
    # Reworded in the submission that takes the old wording back.
    reworded = {**DOCS_RISK, "statement": "docs/feed.md 让人以为缺密钥时会报错，其实只打印一行。"}
    taken = [ids[DOCS_RISK["statement"]], ids["x"]]
    result = workspace.submit(CHANGE_TASK, {"withdrawn_risks": taken, "risks": [reworded]})
    assert result["status"] == "accepted" and result["risks"] == 2, result
    # The report keeps no trace of a risk taken back, so the result names each one.
    assert result["withdrawn"] == 2 and result["withdrawn_risks"] == taken
    statements = {item.statement for item in workspace.stored_report().risks}
    assert statements == {code["statement"], reworded["statement"]}
    # Taken back and sent again in the same words, a risk stays: nothing is withdrawn.
    result = workspace.submit(CHANGE_TASK, {"withdrawn_risks": [kept], "risks": [code]})
    assert result["risks"] == 2 and "withdrawn" not in result, result
    # An id that is not accepted is refused, and nothing changes.
    result = workspace.submit(CHANGE_TASK, {"withdrawn_risks": [taken[0]]})
    assert codes(result) == [("withdrawn_risks[0]", "unknown_risk")]
    assert len(workspace.stored_report().risks) == 2
    # A submission may do nothing but take risks back.
    result = workspace.submit(CHANGE_TASK, {"withdrawn_risks": [kept]})
    assert result["status"] == "accepted" and result["risks"] == 1, result
    assert result["withdrawn"] == 1 and result["withdrawn_risks"] == [kept]
    assert [item.statement for item in workspace.stored_report().risks] == [reworded["statement"]]


def test_a_risk_on_a_file_a_later_prepare_leaves_out_is_named_not_dropped(source_repo):
    workspace, first = two_commits(source_repo, BASE, HEAD)
    assert workspace.submit(CHANGE_TASK, {"risks": [DOCS_RISK]})["status"] == "accepted"
    (risk,) = workspace.stored_report().risks
    # The same revisions with docs/ left out: the same session, its accepted work kept,
    # and docs/feed.md now counted by its folder instead of listed.
    again = prepare(source_repo, base="base", head="HEAD", exclude=("docs",))
    assert (again["session_id"], again["resumed"]) == (first["session_id"], True)
    workspace = Workspace(source_repo, again["session_id"])
    report = workspace.stored_report()
    assert report.risks == ()
    note = next(item for item in report.limitations if item.code == "risks_not_shown")
    assert risk.risk_id in note.message and not note.affects_completeness
    assert note.message.startswith(
        "1 accepted risk names changes or changed files the report no longer lists, and is "
        "not shown"
    )
    # `diff` lists it by the id that withdraws it.
    hidden = workspace.change_summary()["risks_not_shown"]
    assert hidden == [
        {"risk_id": risk.risk_id, "statement": risk.statement, "paths": ["docs/feed.md"]}
    ]
    result = workspace.submit(CHANGE_TASK, {"withdrawn_risks": [risk.risk_id]})
    assert result["withdrawn_risks"] == [risk.risk_id]
    codes_left = {item.code for item in workspace.stored_report().limitations}
    assert "risks_not_shown" not in codes_left
    assert "risks_not_shown" not in workspace.change_summary()

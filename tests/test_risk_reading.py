"""What the risk pass is given to read: the code outside the changes that they reach."""

from genesis_ci.business_map.changes import CHANGE_TASK
from test_change_analysis import by_kind, two_commits

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

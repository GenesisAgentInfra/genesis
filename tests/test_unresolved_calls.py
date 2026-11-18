"""Calls into the code base that could not be resolved are said, not read as unreachable."""

from genesis_ci.business_map.changes import CHANGE_TASK
from test_change_analysis import two_commits

# A stub beside the module makes `app.services` ambiguous: the import cannot be resolved,
# so nothing links `main` to `analyze` although it calls it.
FILES = {
    "app/__init__.py": "",
    "app/services.pyi": "def analyze(x: int) -> int: ...\n",
    "app/cli.py": "from app.services import analyze\n\n\ndef main():\n    return analyze(1)\n\n\n"
    'if __name__ == "__main__":\n    main()\n',
    "app/extra.py": "def unused():\n    return 1\n",
}
BASE = {**FILES, "app/services.py": "def analyze(x):\n    return x\n"}
HEAD = {
    **FILES,
    "app/services.py": "def analyze(x):\n    if x < 0:\n        raise ValueError(x)\n    return x\n",
    "app/extra.py": "def unused():\n    return 2\n",
}


def test_a_change_behind_an_unresolved_call_is_owed_an_explanation(source_repo):
    workspace, _ = two_commits(source_repo, BASE, HEAD)
    report = workspace.stored_report()
    behind = next(item for item in report.changes if item.symbol_id == "app/services.py#analyze")
    assert behind.projection.status == "unassigned" and behind.unresolved_calls == 1
    assert behind.projection.reason.startswith(
        "No resolved call leads here from an entry on the map; 1 call that could not be "
        "resolved may lead here, such as `analyze(1)` in app/cli.py:5."
    )
    # Code no call of any kind leads to is told apart from it, and owes nothing.
    alone = next(item for item in report.changes if item.symbol_id == "app/extra.py#unused")
    assert alone.unresolved_calls is None
    assert alone.projection.reason == (
        "No entry on the map reaches this code through calls static analysis resolved."
    )
    assert [item.change_id for item in report.owed()] == [behind.change_id]
    found = next(item for item in report.limitations if item.code == "unresolved_local_calls")
    assert not found.affects_completeness
    assert found.message.startswith(
        "1 call into this code base's own modules could not be resolved, such as "
        "`analyze(1)` in app/cli.py:5"
    )
    # Unreachable only because a call failed to resolve: not complete until explained.
    assert report.analysis_status == "partial"
    context = workspace.context(CHANGE_TASK)
    assert context["changes_waiting"] == 1
    assert context["changes"][0]["unresolved_calls"] == 1
    entry = {"change_id": behind.change_id, "summary": "负数输入现在会报错。"}
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "accepted" and result["analysis_status"] == "complete"

"""Reject source contradictions without running analyzed functions or tests."""

import pytest
from genesis_ci.business_map.changes import CHANGE_TASK, ChangeAnalysis
from genesis_contracts.models import Resolution
from test_change_analysis import by_kind, two_commits
from test_git_snapshot import write
from test_map_loop import codes

TEST_ID = "head::tests/test_stock.py#test_price"
BASE = {
    "app/__init__.py": "",
    "app/stock.py": (
        "def reserve(stock, qty):\n"
        "    if qty <= 0:\n"
        '        raise ValueError("qty")\n'
        "    return stock - qty\n\n"
        "def price(qty, unit):\n"
        "    return qty * unit\n"
    ),
    "tests/test_stock.py": (
        "from app.stock import reserve, price\n\n"
        "def test_reserve_runs():\n"
        "    reserve(10, 3)\n\n"
        "def test_price():\n"
        "    assert price(2, 5) == 10\n"
    ),
}


def submission(workspace, assertion="price(2, 5) == 10", test_id=TEST_ID):
    item = by_kind(workspace.stored_report(), "result_modified", "price")
    return {
        "change_id": item.change_id,
        "summary": "Change the price calculation.",
        "verdict": "covered",
        "note": "The test checks this change.",
        "test_ids": [test_id],
        "checks": [
            {
                "test_id": test_id,
                "assertion": assertion,
                "scenario": "Use the test's inputs.",
                "detects": "The assertion fails if this change is undone.",
            }
        ],
    }


def case(repo, before, after, assertion):
    base = {
        "app/__init__.py": "",
        "app/stock.py": f"def price(qty, unit):\n    return {before}\n",
        "tests/test_stock.py": (
            f"from app.stock import price\n\ndef test_price():\n    assert {assertion}\n"
        ),
    }
    head = {**base, "app/stock.py": f"def price(qty, unit):\n    return {after}\n"}
    workspace, _ = two_commits(repo, base, head)
    return workspace, submission(workspace, assertion)


def test_rounding_reproduction_rejects_real_assertion_with_false_reason(source_repo):
    head = {
        **BASE,
        "app/stock.py": BASE["app/stock.py"]
        .replace("return stock - qty", "return max(stock - qty, 0)")
        .replace("return qty * unit", "return round(qty * unit, 2)"),
    }
    workspace, _ = two_commits(source_repo, BASE, head)
    before = workspace.stored_report()
    entry = submission(workspace)
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "rejected"
    assert codes(result) == [("changes[0].checks[0].assertion", "assertion_does_not_distinguish")]
    assert workspace.stored_report() == before
    assert by_kind(before, "result_modified", "price").tests.verdict == "reached_only"
    # The agent revises the assessment; the guard never writes a verdict for it.
    entry.update(verdict="reached_only", checks=[], note="Integer inputs miss rounding.")
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"


@pytest.mark.parametrize(
    ("before", "after", "assertion"),
    [
        ("qty * unit", "qty * unit + qty % 2", "price(2, 5) == 10"),
        ("qty * unit", "qty * unit + qty % 2", "price(1, 5) > 0"),
        ("qty * unit", "qty * unit + 1", "0 < price(1, 5) < 20"),
        ("qty * unit", "max(qty * unit, 0)", "price(2, 5) == 10"),
        ("qty * unit", "min(qty * unit, 10)", "price(1, 5) == 5"),
        ("qty * unit", "abs(qty * unit)", "price(+2, 5) == 10"),
        ("qty * unit", "round(qty * unit)", "price(2, 5) == 10"),
        ("qty * unit", "round(qty * unit, 2)", "price(1 + 1, 5) == 10"),
    ],
)
def test_fixed_integer_comparisons_cannot_be_upgraded_by_prose(
    source_repo, before, after, assertion
):
    workspace, entry = case(source_repo, before, after, assertion)
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert ("changes[0].checks[0].assertion", "assertion_does_not_distinguish") in codes(result)


@pytest.mark.parametrize(
    ("before", "after", "assertion"),
    [
        ("qty * unit", "qty * unit + qty % 2", "price(1, 5) == 6"),
        ("qty * unit", "max(qty * unit, 0)", "price(-2, 5) == 0"),
        ("qty * unit", "round(qty * unit, 2)", "price(3, 0.335) == 1.01"),
        ("qty * unit", "round(qty * unit, -1)", "price(1, 16) == 20"),
        ("qty * unit", "qty * unit + 1", "price(qty=1, unit=5) == 6"),
        ("qty / unit", "round(qty / unit, 2)", "price(1, 3) == 0.33"),
        ("qty * unit", "qty * unit + 1", "price(True, 5) == 6"),
        ("qty * unit", "qty * unit + 1", "price(2 ** 100, 5) > 0"),
        ("qty * unit", "qty * unit + 1", "price(9223372036854775808, 5) > 0"),
        ("qty * unit", "qty * unit + 1", "price(1, 5) is not None"),
        ("qty // unit", "qty // unit + 1", "price(1, 0) == 1"),
    ],
)
def test_distinguishing_or_unsupported_comparisons_remain_agent_assessments(
    source_repo, before, after, assertion
):
    workspace, entry = case(source_repo, before, after, assertion)
    assert workspace.submit(CHANGE_TASK, {"changes": [entry]})["status"] == "accepted"
    tests = by_kind(workspace.stored_report(), "result_modified", "price").tests
    assert tests.verdict == "covered"
    assert tests.execution_data == "not_collected"
    assert "agent_assessment" in tests.basis


@pytest.mark.parametrize(
    "extra",
    [
        {"conftest.py": "# May define autouse fixtures.\n"},
        {"app/__init__.py": "from .stock import price\n"},
        {"tests/__init__.py": "import pytest\n"},
        {"app/stock.py": "def round(n, digits):\n    return n + 1\n\n" + BASE["app/stock.py"]},
        {"app/stock.py": "from somewhere import round\n" + BASE["app/stock.py"]},
        {"app/stock.py": BASE["app/stock.py"] + "\nround = lambda n, d: n + 1\n"},
        {
            "tests/test_stock.py": BASE["tests/test_stock.py"].replace(
                "test_price():", "test_price(fixture):"
            )
        },
        {"tests/test_stock.py": "import pytest\n" + BASE["tests/test_stock.py"]},
        {"tests/test_stock.py": BASE["tests/test_stock.py"] + "\ndef setup_module():\n    pass\n"},
        {
            "tests/test_stock.py": BASE["tests/test_stock.py"].replace(
                "def test_price", "@decorate\ndef test_price"
            )
        },
        {
            "tests/test_stock.py": BASE["tests/test_stock.py"].replace(
                "    assert price", "    prepare()\n    assert price"
            )
        },
        {"app/stock.py": BASE["app/stock.py"].replace("def price", "@decorate\ndef price")},
        {
            "app/stock.py": BASE["app/stock.py"].replace(
                "    return qty * unit", "    record(qty)\n    return qty * unit"
            )
        },
    ],
)
def test_unknown_setup_or_binding_abstains(source_repo, extra):
    base = {**BASE, **extra}
    head = {
        **base,
        "app/stock.py": base["app/stock.py"].replace(
            "return qty * unit", "return round(qty * unit, 2)"
        ),
    }
    workspace, _ = two_commits(source_repo, base, head)
    entry = submission(workspace)
    result = workspace.submit(CHANGE_TASK, {"changes": [entry]})
    assert result["status"] == "accepted", result


def test_changed_signature_cannot_be_used_as_the_counterfactual(source_repo):
    head = {
        **BASE,
        "app/stock.py": BASE["app/stock.py"]
        .replace("price(qty, unit)", "price(unit, qty)")
        .replace("return qty * unit", "return round(qty * unit, 2)"),
    }
    workspace, _ = two_commits(source_repo, BASE, head)
    assert (
        workspace.submit(CHANGE_TASK, {"changes": [submission(workspace)]})["status"] == "accepted"
    )


def test_head_test_is_held_fixed_and_live_edits_do_not_change_evidence(source_repo):
    base = {
        **BASE,
        "tests/test_stock.py": BASE["tests/test_stock.py"].replace(
            "price(2, 5) == 10", "price(1, 5) == 5"
        ),
    }
    head = {
        **BASE,
        "app/stock.py": BASE["app/stock.py"].replace(
            "return qty * unit", "return qty * unit + qty % 2"
        ),
    }
    workspace, _ = two_commits(source_repo, base, head)
    write(
        source_repo,
        "tests/test_stock.py",
        BASE["tests/test_stock.py"].replace("price(2, 5) == 10", "price(1, 5) == 6"),
    )
    result = workspace.submit(CHANGE_TASK, {"changes": [submission(workspace)]})
    assert result["status"] == "rejected"
    assert codes(result) == [("changes[0].checks[0].assertion", "assertion_does_not_distinguish")]


def test_rejecting_one_test_does_not_prevent_citing_a_distinguishing_test(source_repo):
    base = {
        **BASE,
        "tests/test_stock.py": BASE["tests/test_stock.py"]
        + "\ndef test_odd():\n    assert price(1, 5) == 6\n",
    }
    head = {
        **base,
        "app/stock.py": BASE["app/stock.py"].replace(
            "return qty * unit", "return qty * unit + qty % 2"
        ),
    }
    workspace, _ = two_commits(source_repo, base, head)
    good = submission(workspace, "price(1, 5) == 6", "head::tests/test_stock.py#test_odd")
    assert workspace.submit(CHANGE_TASK, {"changes": [good]})["status"] == "accepted"
    before = workspace.stored_report()
    assert (
        workspace.submit(CHANGE_TASK, {"changes": [submission(workspace)]})["status"] == "rejected"
    )
    assert workspace.stored_report() == before


def test_source_with_import_side_effect_is_never_executed(source_repo, tmp_path):
    sentinel = tmp_path / "executed"
    base = {
        **BASE,
        "app/stock.py": f"open({str(sentinel)!r}, 'w').write('ran')\n" + BASE["app/stock.py"],
    }
    head = {
        **base,
        "app/stock.py": base["app/stock.py"].replace(
            "return qty * unit", "return round(qty * unit, 2)"
        ),
    }
    workspace, _ = two_commits(source_repo, base, head)
    assert (
        workspace.submit(CHANGE_TASK, {"changes": [submission(workspace)]})["status"] == "accepted"
    )
    assert not sentinel.exists()


def test_candidate_call_target_cannot_refute_an_agent_assessment(source_repo, monkeypatch):
    workspace, entry = case(source_repo, "qty * unit", "round(qty * unit, 2)", "price(2, 5) == 10")
    analysis = ChangeAnalysis(workspace)
    call = next(
        f for f in analysis.ordered("head", "tests/test_stock.py#test_price") if f.kind == "call"
    )
    candidate = call.model_copy(
        update={
            "target": Resolution(
                status="candidate", targets=call.target.targets, reason="Ambiguous binding"
            )
        }
    )
    ordered = analysis.ordered
    monkeypatch.setattr(
        analysis,
        "ordered",
        lambda side, symbol: [
            candidate if fact is call else fact for fact in ordered(side, symbol)
        ],
    )
    change = next(c for c in analysis.diff.changes if c.change_id == entry["change_id"])
    assert not analysis.coverage_guard.refutes(
        change, analysis.tests[TEST_ID], entry["checks"][0]["assertion"]
    )

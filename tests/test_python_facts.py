"""Python adapter: language-neutral facts with position-independent fingerprints."""

import pytest
from genesis_ci.business_map.python_facts import canonical_python, python_facts
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.facts import CodeFact, FactSet
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from pydantic import ValidationError
from test_git_snapshot import commit, git, write

BASE, HEAD = EvidenceSide.base, EvidenceSide.head

APP = """from helpers import review, save

THRESHOLD = 100


async def submit(report):
    amount = report["amount"]
    if amount >= THRESHOLD:
        verdict = await review(report)
        save(report, "pending")
        return {"status": "pending", "review": verdict}
    elif amount < 0:
        raise ValueError("negative amount")
    else:
        save(report, "approved")
    return {"status": "approved"}
"""
HELPERS = """def review(report):
    return "ok"


def save(report, status):
    return (report, status)
"""


def analyze(root, files, base=None):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    extraction = extract_python(capture_snapshot(root, SnapshotSpec(base=base or head, head=head)))
    return python_facts(extraction)


def select(result, kind=None, side=HEAD, symbol=None):
    return [
        fact
        for fact in result.facts
        if fact.side == side
        and (kind is None or fact.kind == kind)
        and (symbol is None or fact.symbol_id == symbol)
    ]


def one(result, kind, text, side=HEAD):
    found = [fact for fact in select(result, kind, side) if fact.text == text]
    assert len(found) == 1, [fact.text for fact in select(result, kind, side)]
    return found[0]


def test_facts_carry_the_branch_they_sit_on(source_repo):
    result = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS})
    threshold = one(result, "condition", "amount >= THRESHOLD")
    negative = one(result, "condition", "amount < 0")
    assert threshold.guards == ()
    assert [(g.fingerprint, g.branch) for g in negative.guards] == [
        (threshold.fingerprint, "false")
    ]
    pending = one(result, "call", 'save(report, "pending")')
    assert [(g.fingerprint, g.branch) for g in pending.guards] == [(threshold.fingerprint, "true")]
    approved = one(result, "call", 'save(report, "approved")')
    assert [(g.fingerprint, g.branch) for g in approved.guards] == [
        (threshold.fingerprint, "false"),
        (negative.fingerprint, "false"),
    ]
    rejected = one(result, "raise", 'raise ValueError("negative amount")')
    assert [g.branch for g in rejected.guards] == ["false", "true"]
    final = one(result, "return", 'return {"status": "approved"}')
    assert final.guards == ()


def test_calls_reuse_the_extractor_resolution(source_repo):
    result = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS})
    reviewed = one(result, "call", "review(report)")
    assert reviewed.awaited is True
    assert reviewed.boundary == "internal"
    assert reviewed.target.status == "resolved"
    assert reviewed.target.targets == ("helpers.py#review",)
    assert reviewed.symbol_id == "app.py#submit"
    raised = one(result, "call", 'ValueError("negative amount")')
    assert raised.boundary == "builtin"
    assert all(fact.target is None and fact.boundary is None for fact in select(result, "return"))


def test_fingerprints_survive_line_shifts_and_reformatting(source_repo):
    first = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    shifted = '"""Module docstring added above everything."""\n\n' + APP.replace(
        "amount >= THRESHOLD", "amount>=THRESHOLD"
    ).replace(
        'save(report, "pending")', 'save(\n            report,\n            "pending",\n        )'
    )
    result = analyze(source_repo, {"app.py": shifted}, base=base)
    before = {fact.fingerprint: fact for fact in select(result, side=BASE)}
    after = {fact.fingerprint: fact for fact in select(result, side=HEAD)}
    moved = one(result, "condition", "amount>=THRESHOLD")
    original = one(result, "condition", "amount >= THRESHOLD", side=BASE)
    assert moved.fingerprint == original.fingerprint
    assert moved.range.start_line == original.range.start_line + 2
    # Wrapping a call and adding the formatter's trailing comma changes no fact.
    assert before.keys() == after.keys()
    assert {fact.fingerprint for fact in select(first)} == set(before)


def test_a_changed_operator_is_a_different_fact(source_repo):
    analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    result = analyze(
        source_repo, {"app.py": APP.replace("amount >= THRESHOLD", "amount > THRESHOLD")}, base
    )
    old = one(result, "condition", "amount >= THRESHOLD", side=BASE)
    new = one(result, "condition", "amount > THRESHOLD")
    assert old.fingerprint != new.fingerprint
    unchanged = one(result, "condition", "amount < 0")
    assert unchanged.fingerprint == one(result, "condition", "amount < 0", side=BASE).fingerprint
    # The guard now points at the new condition, but the guarded call is the same fact.
    kept = one(result, "call", 'save(report, "pending")')
    assert kept.fingerprint == one(result, "call", 'save(report, "pending")', side=BASE).fingerprint
    assert kept.guards[0].fingerprint == new.fingerprint


def test_repeated_facts_are_told_apart_by_ordinal(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def run(log):
    log("step")
    log("step")
    if log:
        return 1
    if log:
        return 1
"""
        },
    )
    calls = [fact for fact in select(result, "call") if fact.text == 'log("step")']
    assert [fact.ordinal for fact in calls] == [0, 1]
    assert len({fact.fingerprint for fact in calls}) == 2
    conditions = select(result, "condition")
    assert [fact.ordinal for fact in conditions] == [0, 1]
    returns = select(result, "return")
    assert [fact.guards[0].fingerprint for fact in returns] == [
        fact.fingerprint for fact in conditions
    ]


def test_loops_and_match_cases_are_recorded(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def drain(queue, handle):
    while queue:
        item = queue.pop()
        for part in item.parts:
            handle(part)
    match queue.state:
        case "closed":
            return None
        case other if other:
            return other
"""
        },
    )
    outer = one(result, "loop", "while queue")
    inner = one(result, "loop", "for part in item.parts")
    assert inner.loops == (outer.fingerprint,)
    assert one(result, "call", "handle(part)").loops == (outer.fingerprint, inner.fingerprint)
    assert one(result, "call", "queue.pop()").loops == (outer.fingerprint,)
    subject = one(result, "condition", "match queue.state")
    branches = [fact.guards[0].branch for fact in select(result, "return")]
    assert branches == ['case "closed"', "case other if other"]
    assert {fact.guards[0].fingerprint for fact in select(result, "return")} == {
        subject.fingerprint
    }


def test_nested_scopes_keep_their_own_context(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def cached(fn):
    return fn


class Service:
    def run(self, ready):
        if ready:
            @cached
            def inner(value):
                return value + 1
            return inner(1)
        return (lambda x: missing(x))(2)
"""
        },
    )
    inner = one(result, "return", "return value + 1")
    assert inner.symbol_id == "app.py#Service.run.inner"
    assert inner.guards == ()
    outer = one(result, "return", "return inner(1)")
    assert outer.symbol_id == "app.py#Service.run"
    assert [guard.branch for guard in outer.guards] == ["true"]
    assert not [fact for fact in select(result, "call") if fact.text == "missing(x)"]
    symbols = {symbol.symbol_id: symbol for symbol in result.symbols if symbol.side == HEAD}
    assert symbols["app.py#Service.run.inner"].decorators == ("cached",)
    assert symbols["app.py#Service"].kind == "class"


def test_unparsed_files_are_reported_and_facts_validate(source_repo):
    result = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS, "broken.py": "def (:\n"})
    status = {item.path: item for item in result.files if item.side == HEAD}
    assert status["broken.py"].status == "unsupported" and status["broken.py"].reason
    assert status["app.py"].status == "analyzed"
    assert FactSet.model_validate(result.model_dump(mode="json")) == result
    cited = {ref for fact in result.facts for ref in fact.evidence_ids}
    assert cited <= {ref.evidence_id for ref in result.evidence}


def test_canonical_text_ignores_layout_but_not_string_contents():
    assert canonical_python("f( a,b )") == canonical_python("f(a, b)")
    assert canonical_python("a and \\\n    b") == canonical_python("a and b")
    assert canonical_python("(a  # why\n and b)") == canonical_python("(a and b)")
    assert canonical_python('x == "a  b"') != canonical_python('x == "a b"')
    assert canonical_python("amount >= 100") != canonical_python("amount > 100")
    assert canonical_python('"unterminated') == '"unterminated'


def test_fact_set_rejects_inconsistent_facts(source_repo):
    data = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS}).model_dump(mode="json")

    def rejects(mutate, message):
        import copy

        changed = copy.deepcopy(data)
        mutate(changed)
        with pytest.raises(ValidationError, match=message):
            FactSet.model_validate(changed)

    guarded = next(i for i, fact in enumerate(data["facts"]) if fact["guards"])
    call = next(i for i, fact in enumerate(data["facts"]) if fact["kind"] == "call")
    rejects(lambda d: d["facts"].append(d["facts"][0]), "fingerprints on one side")
    rejects(lambda d: d["facts"][0].update(symbol_id="app.py#gone"), "symbol on its own side")
    rejects(
        lambda d: d["facts"][guarded]["guards"][0].update(fingerprint="fp_" + "0" * 24),
        "condition or loop in the same symbol",
    )
    rejects(lambda d: d["facts"][call].update(target=None), "carry a target and a boundary")
    rejects(lambda d: d["facts"][0].update(evidence_ids=["ev_missing"]), "unknown evidence_id")
    with pytest.raises(ValidationError, match="only a call can be awaited"):
        returned = next(fact for fact in data["facts"] if fact["kind"] == "return")
        CodeFact.model_validate({**returned, "awaited": True})


def test_canonical_text_ignores_the_commas_a_formatter_adds():
    assert canonical_python("f(\n    a,\n    b,\n)") == canonical_python("f(a, b)")
    assert canonical_python("f(\n    only,\n)") == canonical_python("f(only)")
    assert canonical_python("[a, b,]") == canonical_python("[a, b]")
    assert canonical_python("{'k': v,}") == canonical_python("{'k': v}")
    assert canonical_python("(a, b,)") == canonical_python("(a, b)")
    # The comma of a one-element tuple changes the value, so it stays.
    assert canonical_python("(a,)") != canonical_python("(a)")
    assert canonical_python("return (a,)") != canonical_python("return (a)")
    assert canonical_python("f((a,))") != canonical_python("f((a))")


def test_a_definition_starts_at_its_first_decorator(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": "import functools\n\n\n@functools.cache\n@staticmethod\ndef load():\n    return 1\n"
        },
    )
    symbol = next(item for item in result.symbols if item.symbol_id == "app.py#load")
    assert (symbol.range.start_line, symbol.range.end_line) == (4, 7)


def test_tests_are_recorded_as_source_with_calls_and_assertions(source_repo):
    files = {
        "shop/__init__.py": "",
        "shop/cart.py": "def total(items):\n    return sum(items)\n\n\ndef clear():\n    return []\n",
        "tests/test_cart.py": "import pytest\n\nfrom shop.cart import clear, total\n\n\n"
        "def helper():\n    return total([1])\n\n\n"
        "def test_total():\n    assert total([1, 2]) == 3\n\n\n"
        "def test_rejects_text():\n    with pytest.raises(TypeError):\n        total(['a', 1])\n\n\n"
        "def test_clear_runs():\n    clear()\n",
        "shop/test_data.py": "def test_like_name_outside_tests():\n    return 1\n",
    }
    found = {item.symbol_id.partition("#")[2]: item for item in analyze(source_repo, files).tests}
    # A helper is not a test; a `test_*.py` file counts wherever it sits.
    assert sorted(found) == [
        "test_clear_runs",
        "test_like_name_outside_tests",
        "test_rejects_text",
        "test_total",
    ]
    assert found["test_total"].test_id == "head::tests/test_cart.py#test_total"
    assert found["test_total"].called_symbol_ids == ("shop/cart.py#total",)
    assert found["test_total"].assertions == ("total([1, 2]) == 3",)
    # `pytest.raises` checks something without an assert statement.
    assert found["test_rejects_text"].assertions == ("pytest.raises(TypeError)",)
    assert found["test_clear_runs"].called_symbol_ids == ("shop/cart.py#clear",)
    assert found["test_clear_runs"].assertions == ()


def test_source_roots_follow_the_package_layout():
    from genesis_ci.business_map.python_facts import python_source_roots

    paths = [
        "setup.py",
        "packages/core/src/core/__init__.py",
        "packages/core/src/core/sub/__init__.py",
        "packages/core/src/core/sub/mod.py",
        "packages/api/app/__init__.py",
        "top/__init__.py",
        "tests/test_core.py",
        "docs/conf.py",
    ]
    assert python_source_roots(paths) == (".", "src", "packages/api", "packages/core/src")


def test_files_analyzed_in_worker_processes_give_the_same_facts(source_repo, monkeypatch):
    import genesis_ci.python.extract as extract
    from genesis_ci.business_map.python_facts import collect_file

    files = {"app.py": APP, "helpers.py": HELPERS, "broken.py": "def (:\n"}
    # Workers start in the analyzed repository. Its files must never be imported in
    # place of a real module, or analyzing a repository would run its code.
    files.update(
        {"pickle.py": 'raise SystemExit("shadowed")\n', "genesis_ci.py": "import nothing\n"}
    )
    monkeypatch.chdir(source_repo)
    files.update(
        {
            f"pkg/mod_{index}.py": HELPERS + f"\n\nVALUE_{index} = review({index})\n"
            for index in range(6)
        }
    )
    for path, text in files.items():
        write(source_repo, path, text)
    head = commit(source_repo)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base=head, head=head))

    def dumped(extraction):
        return python_facts(extraction).model_dump(mode="json")

    plain = dumped(extract_python(snapshot))
    hooked = extract_python(snapshot, collect=collect_file)
    # With the hook the syntax trees are released, and nothing downstream needs them.
    assert all(file.module is None for file in hooked.files.values())
    assert dumped(hooked) == plain

    pooled = []
    real = extract._extract_in_processes

    def recorded(jobs, workers):
        pooled.append(real(jobs, workers))
        return pooled[-1]

    monkeypatch.setattr(extract, "_extract_in_processes", recorded)
    parallel = extract_python(snapshot, workers=2, collect=collect_file)
    assert len(pooled) == 1
    assert dumped(parallel) == plain
    assert parallel.analysis.evidence == hooked.analysis.evidence
    assert [(item.path, item.syntax.status) for item in parallel.analysis.coverage] == [
        (item.path, item.syntax.status) for item in hooked.analysis.coverage
    ]
    if pooled[0] is None:
        pytest.skip("no worker process could start here; the in-process fallback was used")


def test_extraction_falls_back_when_no_process_pool_can_start(source_repo, monkeypatch):
    import genesis_ci.python.extract as extract
    from genesis_ci.business_map.python_facts import collect_file

    monkeypatch.setattr(extract, "_extract_in_processes", lambda jobs, workers: None)
    result = analyze(source_repo, {"app.py": APP, "helpers.py": HELPERS})
    for path, text in {"app.py": APP, "helpers.py": HELPERS}.items():
        write(source_repo, path, text)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(head="HEAD"))
    fallback = python_facts(extract_python(snapshot, workers=4, collect=collect_file))
    assert {fact.fingerprint for fact in select(fallback)} == {
        fact.fingerprint for fact in select(result)
    }

"""Retrieve dispatch source without upgrading uncertain runtime targets."""

from genesis_ci.context import ContextOptions, build_context
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_request_against_local
from test_git_snapshot import git


def dispatch_repository(source_repo):
    (source_repo / "pkg/providers").mkdir(parents=True)
    (source_repo / "pkg/providers/remote.py").write_text(
        "class Remote:\n    def fetch(self):\n        return 'content', []\n"
    )
    # The package re-export is deliberately outside the captured scope. It is
    # enough to retrieve source, never enough to assert a resolved import/call.
    (source_repo / "pkg/runner.py").write_text(
        "from . import Remote\nimport asyncio\n"
        + "# unrelated explanation\n" * 700
        + """class Runner:
    def select(self, kind):
        choices = {"remote": Remote}
        return choices[kind]

    async def fetch_one(self, kind):
        Provider = self.select(kind)
        provider = Provider()
        if hasattr(provider, "fetch_async"):
            content, images = await provider.fetch_async()
        else:
            content, images = provider.fetch()
        return content

    async def run(self, kinds):
        rows = await asyncio.gather(*(self.fetch_one(k) for k in kinds))
        return [row for row in rows if row]
"""
    )
    (source_repo / "unrelated.py").write_text(
        "from elsewhere import Remote\ndef unrelated():\n    return Remote().fetch_async()\n"
    )
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "pkg/providers/remote.py").write_text(
        "import asyncio\nlimit = asyncio.Semaphore(2)\n"
        "class Remote:\n    def fetch(self):\n        return 'content', []\n"
        "    async def fetch_async(self):\n        async with limit:\n"
        "            return await asyncio.to_thread(self.fetch)\n"
    )
    return analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))


def test_large_unchanged_dispatch_and_collection_are_sent_as_candidate_source(source_repo):
    result = dispatch_repository(source_repo)
    request = build_context(result.local, result.reader, request_id="dynamic")
    validate_request_against_local(result.local, request)
    owners = {(f.side, f.symbol_id) for f in request.facts.functions}
    assert {
        (side, "pkg/runner.py#Runner." + name)
        for side in ("base", "head")
        for name in ("select", "fetch_one", "run")
    } <= owners
    assert not any(f.symbol_id.startswith("unrelated.py#") for f in request.facts.functions)
    dynamic = [
        c for c in result.extraction.analysis.calls if c.callee.text == "provider.fetch_async"
    ]
    assert dynamic and all(c.target.status == "unknown" for c in dynamic)
    assert not any(
        e.resolution == "resolved" and "fetch_async" in e.target_id
        for e in request.impact_graph.edges
    )


def test_candidate_context_obeys_exclusions_and_tiny_budgets(source_repo):
    result = dispatch_repository(source_repo)
    for options in (
        ContextOptions(exclude_paths=("pkg/runner.py",)),
        ContextOptions(max_excerpts=2, input_token_budget=12000),
    ):
        request = build_context(result.local, result.reader, request_id="bounded", options=options)
        validate_request_against_local(result.local, request)
        assert request.truncated
        assert len(request.excerpts) <= options.max_excerpts
        if options.exclude_paths:
            assert not any(ref.path == "pkg/runner.py" for ref in request.evidence)


def test_unpacking_keeps_other_import_calls_but_never_types_unpacked_names(source_repo):
    (source_repo / "app.py").write_text("# base\n")
    git(source_repo, "add", ".")
    git(source_repo, "commit", "-qm", "base")
    (source_repo / "app.py").write_text(
        "import asyncio\n"
        "def run(source):\n"
        "    first, [second, *rest] = source()\n"
        "    first()\n    second()\n    rest()\n"
        "    return asyncio.gather()\n"
    )
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD")))
    found = {c.callee.text: c for c in result.extraction.analysis.calls if c.side == "head"}
    assert found["asyncio.gather"].target.status == "resolved"
    assert all(found[name].target.status == "unknown" for name in ("first", "second", "rest"))

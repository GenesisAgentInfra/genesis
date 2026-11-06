import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.patterns import detect_patterns
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write
from test_python_analysis import analyze, calls

PREFIX = """from openai import OpenAI
client = OpenAI()
def search(): return "found"
def store(): return "stored"
def fallback(): return None
TOOLS = [{"type": "function", "function": {"name": "search"}}, {"type": "function", "function": {"name": "store"}}]
def agent():
    for step in range(3):
        response = client.chat.completions.create(model="x", messages=[], tools=TOOLS)
        for tool in response.choices[0].message.tool_calls:
"""


def head_loop(result):
    patterns = detect_patterns(result)
    return next(item for item in patterns.loops if item.side == "head")


def test_if_elif_positive_bodies_and_response_lineage(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + """            if tool.function.name == "search":
                search()
            elif "store" == tool.function.name:
                store()
            else:
                fallback()
"""
        },
    )
    assert result.analysis.format_version == 5
    loop = head_loop(result)
    sites = loop.dispatch_sites
    assert {(s.tool_name, s.target.targets) for s in sites} == {
        ("search", ("app.py#search",)),
        ("store", ("app.py#store",)),
    }
    assert all(s.kind == "if" and s.model_call_ids for s in sites)
    assert loop.loop.reachable_tools.targets == ("app.py#search", "app.py#store")
    assert loop.loop.reachable_tools.status == "candidate"
    assert not loop.dispatch_complete
    fallback = next(c for c in calls(result) if c.callee.text == "fallback")
    assert fallback.branch_guards == ()
    assert all(s.target.status == "candidate" for s in sites)


def test_match_alias_guard_and_or_pattern_keep_candidates(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": PREFIX
            + """            name = tool.function.name
            match name:
                case "search" | "store" if enabled:
                    search()
                case _:
                    fallback()
"""
        },
    )
    loop = head_loop(result)
    assert {s.tool_name for s in loop.dispatch_sites} == {"search", "store"}
    assert all(s.kind == "match" for s in loop.dispatch_sites)
    refs = {r.evidence_id: r for r in result.analysis.evidence}
    reader = result.registry.freeze()
    texts = [reader.read_excerpt(ref).text for s in loop.dispatch_sites for ref in s.evidence_ids]
    assert "enabled" in texts
    assert any("response =" in t for t in texts)
    assert all(refs[ref].side == "head" for s in loop.dispatch_sites for ref in s.evidence_ids)


@pytest.mark.parametrize(
    "body",
    [
        'if mode == "search":\n                search()',
        'if tool.function.name != "search":\n                search()',
        "if tool.function.name == dynamic_name:\n                search()",
        'if tool.function.name == "search" or enabled:\n                search()',
        "match tool.function.name:\n                case dynamic_name:\n                    search()",
        'if tool.function.name == "search":\n                def deferred():\n                    search()',
    ],
)
def test_unrelated_negative_dynamic_or_deferred_branch_is_not_dispatch(source_repo, body):
    result = analyze(source_repo, {"app.py": PREFIX + "            " + body + "\n"})
    assert head_loop(result).dispatch_sites == ()


def test_ambiguous_response_assignment_is_not_provenance(source_repo):
    source = PREFIX.replace(
        "        for tool in response",
        "        response = unrelated()\n        for tool in response",
    )
    result = analyze(
        source_repo,
        {"app.py": source + '            if tool.function.name == "search": search()\n'},
    )
    assert head_loop(result).dispatch_sites == ()


def test_anthropic_async_content_and_mapping_name(source_repo):
    source = """from anthropic import AsyncAnthropic
client = AsyncAnthropic()
def search(): pass
async def agent():
    while True:
        response = await client.messages.create(model="x", messages=[], tools=[{"name": "search", "input_schema": {}}])
        for block in response.content:
            match block["name"]:
                case "search":
                    search()
        break
"""
    result = analyze(source_repo, {"app.py": source})
    loop = head_loop(result)
    assert loop.loop.reachable_tools.targets == ("app.py#search",)
    assert loop.dispatch_sites[0].model_call_ids


def test_response_provenance_cannot_cross_function_or_loop_scope(source_repo):
    source = (
        PREFIX
        + """            def nested():
                if tool.function.name == "search": search()
"""
    )
    result = analyze(source_repo, {"app.py": source})
    assert head_loop(result).dispatch_sites == ()


def test_branch_dispatch_reaches_graph_flow_and_changed_tool(source_repo):
    source = PREFIX + '            if tool.function.name == "search": search()\n'
    analyze(
        source_repo,
        {
            "app.py": source,
            ".genesis/flows.yaml": "schema_version: 1\nflows:\n- id: agent\n  name: Agent\n  status: confirmed\n  entries: [app.py#agent]\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", source.replace('return "found"', 'return "new"'))
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    edges = [e for e in result.impact.graph.edges if e.relation == "dispatches"]
    assert any(e.target_id == "head::app.py#search" and e.resolution == "candidate" for e in edges)
    assert ("head", "app.py#agent") in result.impact.affected_symbols
    assert "app.py#search" in result.local.flow_impacts[0].changed_symbol_ids
    assert result.local.flow_impacts[0].status != "resolved"


def test_tool_and_bound_changes_include_two_sided_evidence(source_repo):
    source = PREFIX + '            if tool.function.name == "search": search()\n'
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    source = source.replace('== "search": search()', '== "store": store()').replace(
        "range(3)", "range(8)"
    )
    write(source_repo, "app.py", source)
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    ids = [f.finding_id for f in result.report.findings]
    assert any(i.startswith("tool_dispatch_changed") for i in ids)
    assert any(i.startswith("loop_bound_changed") for i in ids)
    refs = {r.evidence_id: r for r in result.local.evidence}
    for finding in result.report.findings:
        if finding.finding_id.startswith(("tool_dispatch_changed", "loop_bound_changed")):
            assert {refs[r].side.value for r in finding.evidence_ids} == {"base", "head"}


def test_schema_only_config_change_outside_function_still_reported(source_repo):
    source = PREFIX + '            if tool.function.name == "search": search()\n'
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", source.replace('{"name": "store"}', '{"name": "write"}'))
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert "app.py#agent" not in result.local.change_set.changed_symbol_ids
    assert any(f.finding_id.startswith("tool_schema_changed") for f in result.report.findings)


def test_partial_branch_never_claims_missing_dispatch(source_repo):
    source = PREFIX + '            if tool.function.name == "search": search()\n'
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", source.replace("range(3)", "range(4)"))
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert not any(
        f.finding_id.startswith("tool_schema_dispatch_mismatch") for f in result.report.findings
    )


def test_pattern_validator_rejects_unrelated_response_provenance(source_repo):
    from genesis_ci.pattern_validation import validate_patterns

    result = analyze(
        source_repo,
        {"app.py": PREFIX + '            if tool.function.name == "search": search()\n'},
    )
    patterns = detect_patterns(result)
    loop = patterns.loops[0]
    site = loop.dispatch_sites[0].model_copy(update={"model_call_ids": ("missing-call",)})
    invalid_loop = loop.model_copy(update={"dispatch_sites": (site,)})
    invalid = patterns.model_copy(update={"loops": (invalid_loop, *patterns.loops[1:])})
    with pytest.raises(ValueError, match="unrelated model"):
        validate_patterns(result.analysis, invalid)


def test_unassigned_changes_exclude_modules_tests_and_mapped_functions(source_repo):
    analyze(
        source_repo,
        {
            "app.py": "def entry(): return 1\ndef orphan(): return 1\n",
            "tests/test_app.py": "def test_x(): pass\n",
            ".genesis/flows.yaml": "schema_version: 1\nflows:\n- id: main\n  name: Main\n  status: confirmed\n  entries: [app.py#entry]\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def entry(): return 2\ndef orphan(): return 2\n")
    write(source_repo, "tests/test_app.py", "def test_x(): assert True\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert {(u.side.value, u.symbol_id) for u in result.flows.unassigned_changes} == {
        ("base", "app.py#orphan"),
        ("head", "app.py#orphan"),
    }
    finding = next(f for f in result.report.findings if f.finding_id == "flow_unassigned_head")
    assert "app.py#orphan" in finding.statement
    assert "unused" in finding.condition


def test_unassigned_change_with_missing_map_does_not_assert_unused(source_repo):
    analyze(source_repo, {"app.py": "def entry(): return 1\n"})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def entry(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert result.flows.unassigned_changes
    assert any(item.code == "flows_missing" for item in result.local.limitations)
    assert not any(f.finding_id == "flow_unassigned_head" for f in result.report.findings)


def test_global_model_prompt_change_has_definition_evidence(source_repo):
    source = PREFIX.replace('model="x", messages=[]', "model=MODEL, messages=[PROMPT]")
    source = 'MODEL = "x"\nPROMPT = "hello"\n' + source + "            pass\n"
    analyze(source_repo, {"app.py": source})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(
        source_repo,
        "app.py",
        source.replace('MODEL = "x"', 'MODEL = "y"').replace(
            'PROMPT = "hello"', 'PROMPT = "hello world"'
        ),
    )
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert "app.py#agent" not in result.local.change_set.changed_symbol_ids
    findings = [
        f
        for f in result.report.findings
        if f.finding_id.startswith(("model_literal_changed", "prompt_literal_changed"))
    ]
    assert len(findings) == 2
    texts = [result.reader.read_excerpt(ref).text for f in findings for ref in f.evidence_ids]
    assert 'MODEL = "x"' in texts and 'MODEL = "y"' in texts
    assert 'PROMPT = "hello world"' in texts


@pytest.mark.parametrize(
    "mutation",
    [
        "response.choices = unrelated()",
        "response.choices.append(unrelated())",
    ],
)
def test_response_mutation_blocks_branch_provenance(source_repo, mutation):
    source = PREFIX.replace(
        "        for tool in response", "        " + mutation + "\n        for tool in response"
    )
    result = analyze(
        source_repo,
        {"app.py": source + '            if tool.function.name == "search": search()\n'},
    )
    assert head_loop(result).dispatch_sites == ()


def test_multiple_dispatch_tables_preserve_all_candidate_targets(source_repo):
    source = """from openai import OpenAI
client = OpenAI()
def first(): pass
def second(): pass
a = {"search": first}
b = {"search": second}
def agent(name):
    for _ in range(3):
        client.responses.create(model="x", input="hi", tools=[{"name": "search"}])
        a[name]()
        b[name]()
"""
    result = analyze(source_repo, {"app.py": source})
    loop = head_loop(result)
    assert loop.loop.reachable_tools.targets == ("app.py#first", "app.py#second")
    assert len(loop.dispatch_sites) == 2

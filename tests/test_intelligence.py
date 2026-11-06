from genesis_ci.flows import map_flows
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.impact import build_impact
from genesis_ci.patterns import detect_patterns
from genesis_ci.python import extract_python
from genesis_ci.test_index import index_tests
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write
from test_python_analysis import analyze, calls

HEAD = EvidenceSide.head


def test_sdk_loop_schema_dispatch_and_literal_bound(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
client = OpenAI()
def search(query): return query
TOOLS = [{"type": "function", "function": {"name": "search", "description": "Search"}}]
DISPATCH = {"search": search}
def agent(messages, tool_name):
    for step in range(3):
        response = client.chat.completions.create(model="gpt-4.1", messages=messages, tools=TOOLS)
        DISPATCH[tool_name]("query")
        if response.done:
            break
"""
        },
    )
    patterns = detect_patterns(result)
    models = [c for c in patterns.model_calls if c.side == HEAD]
    assert len(models) == 1
    assert models[0].provider == "openai" and models[0].model.value == "gpt-4.1"
    loop = next(item for item in patterns.loops if item.side == HEAD)
    assert loop.loop.iteration_bound.max_iterations == 3
    assert loop.loop.reachable_tools.targets == ("app.py#search",)
    assert loop.loop.reachable_tools.status == "candidate"
    assert loop.unmatched_schema_tools == ()
    assert loop.loop.stop_conditions
    graph = build_impact(result, patterns).graph
    assert any(edge.relation == "dispatches" for edge in graph.edges)


def test_anthropic_alias_async_dynamic_model_and_unbounded_loop(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from anthropic import AsyncAnthropic as Client
client = Client()
async def agent(model_name, messages):
    while True:
        response = await client.messages.create(model=model_name, messages=messages)
        if response.done: break
"""
        },
    )
    patterns = detect_patterns(result)
    model = next(item for item in patterns.model_calls if item.side == HEAD)
    assert model.provider == "anthropic"
    assert model.model.kind == "name"
    loop = next(item for item in patterns.loops if item.side == HEAD)
    assert loop.loop.iteration_bound.status == "unbounded"
    assert "breaks" in loop.loop.iteration_bound.reason
    assert loop.loop.dispatch.status == "unknown"


def test_same_method_name_dynamic_receiver_and_shadowed_sdk_are_not_models(source_repo):
    result = analyze(
        source_repo,
        {
            "openai.py": "class OpenAI:\n    pass\n",
            "app.py": """from openai import OpenAI
def run(client):
    client.responses.create(model="fake")
    unknown.create()
client = OpenAI()
client.responses.create(model="also fake")
""",
        },
    )
    assert detect_patterns(result).model_calls == ()


def test_graph_propagates_cross_file_helper_to_unchanged_flow(source_repo):
    analyze(
        source_repo,
        {
            "helper.py": "def work():\n    return 1\n",
            "app.py": "from helper import work\ndef main():\n    return work()\n",
            ".genesis/flows.yaml": "schema_version: 1\nflows:\n- id: main\n  name: Main\n  status: confirmed\n  entries: [app.py#main]\n  acceptance: [Return a value]\n",
            "tests/test_app.py": "from app import main\ndef test_main():\n    assert main() == 1\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "helper.py", "def work():\n    return 2\n")
    commit(source_repo)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD"))
    result = extract_python(snapshot)
    patterns = detect_patterns(result)
    impact = build_impact(result, patterns)
    assert (HEAD, "app.py#main") in impact.affected_symbols
    assert (HEAD, "tests/test_app.py#test_main") in impact.affected_symbols
    flows = map_flows(snapshot, result, impact)
    flow = next(item for item in flows.impacts if item.side == HEAD)
    assert "helper.py#work" in flow.impact.changed_symbol_ids
    assert flow.impact.entry_status == "valid"
    assert flows.intents[0].nature == "user_intent"
    tests = index_tests(result, impact)
    test = next(item for item in tests if item.side == HEAD)
    assert "app.py#main" in test.called_symbol_ids
    assert "app.py#main" in test.asserted_symbol_ids
    assert test.definition.association.status == "candidate"


def test_graph_cycles_budget_and_both_sides_have_distinct_nodes(source_repo):
    from genesis_contracts.python import PythonOptions

    first = analyze(source_repo, {"app.py": "def a(): return b()\ndef b(): return a()\n"})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    result = analyze(
        source_repo,
        {"app.py": "def a(): return b(1)\ndef b(): return a()\n"},
        before=base,
        options=PythonOptions(max_graph_visits=1),
    )
    impact = build_impact(result, detect_patterns(result))
    assert impact.coverage.status == "insufficient_context"
    ids = {node.node_id for node in impact.graph.nodes}
    assert "base::app.py#a" in ids and "head::app.py#a" in ids
    assert len(impact.affected_symbols) == 1
    assert first.analysis.change_set.changed_symbol_ids == ()


def test_bad_flow_map_and_deleted_entry_do_not_block_other_facts(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": "def main(): pass\n",
            ".genesis/flows.yaml": "schema_version: 1\nflows:\n- id: gone\n  name: Gone\n  status: confirmed\n  entries: [app.py#deleted]\n  acceptance: [Must still work]\n",
        },
    )
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    flows = map_flows(snapshot, result, build_impact(result, detect_patterns(result)))
    assert flows.impacts[-1].impact.entry_status == "invalid"
    assert flows.intents
    write(source_repo, ".genesis/flows.yaml", "flows: [invalid")
    commit(source_repo)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    result = extract_python(snapshot)
    flows = map_flows(snapshot, result, build_impact(result, detect_patterns(result)))
    assert any(item.code == "flows_invalid" for item in flows.limitations)
    assert result.analysis.symbols


def test_decorator_defaults_calls_belong_to_enclosing_scope(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": "def factory(): pass\n@factory()\ndef run(x=factory()):\n    return factory()\n"
        },
    )
    found = [c for c in calls(result) if c.callee.text == "factory"]
    assert [c.symbol_id for c in found].count("app.py#<module>") == 2
    assert [c.symbol_id for c in found].count("app.py#run") == 1


def test_monkeypatch_and_conditional_import_never_resolve_as_certain(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """if condition:
    from openai import OpenAI
client = OpenAI()
client.responses.create(model="test")
"""
        },
    )
    assert all(
        call.resolution.status == "candidate" for call in detect_patterns(result).model_calls
    )
    result = analyze(
        source_repo,
        {
            "app.py": """import openai
openai.OpenAI = custom
client = openai.OpenAI()
client.responses.create(model="test")
"""
        },
    )
    assert not any(
        call.resolution.status == "resolved" for call in detect_patterns(result).model_calls
    )


def test_multiple_sdk_instances_and_tool_mismatch(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
client = OpenAI()
def search(): pass
def other(): pass
dispatch = {"other": other}
tools = [{"type":"function", "name":"search"}]
def run(messages, name):
    for i in range(2):
        client.responses.create(model="m", input=messages, tools=tools)
        dispatch[name]()
"""
        },
    )
    loop = next(item for item in detect_patterns(result).loops if item.side == HEAD)
    assert loop.unmatched_schema_tools == ("search",)
    assert loop.unmatched_dispatch_tools == ("other",)
    assert loop.loop.reachable_tools.status == "unknown"


def test_literal_arguments_with_expansion_are_not_known_model(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
client = OpenAI()
def run(extra):
    return client.responses.create(model="m", **extra)
"""
        },
    )
    assert (
        next(item for item in detect_patterns(result).model_calls if item.side == HEAD).model.kind
        == "unknown"
    )

import hashlib

import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.models import EvidenceSide
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write

BASE, HEAD = EvidenceSide.base, EvidenceSide.head


def analyze(root, files, before=None, options=None):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    return extract_python(
        capture_snapshot(root, SnapshotSpec(base=before or head, head=head)), options
    )


def calls(result, path="app.py", side=HEAD):
    return [call for call in result.analysis.calls if call.path == path and call.side == side]


def test_expression_receiver_metadata_never_resolves_to_builtin_constant(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def normalize(value, flag):
    (value or '').lower()
    (value if flag else '').strip()
    ''.upper()
    return len(str(value))
"""
        },
    )
    found = calls(result)
    methods = [call for call in found if call.callee.kind == "attribute"]
    assert methods and all(call.target.status == "unknown" for call in methods)
    assert all("builtin:None" not in call.target.targets for call in found)
    assert next(call for call in found if call.callee.text == "len").target.targets == (
        "builtin:len",
    )


def test_direct_alias_relative_import_reexport_and_unchanged_caller(source_repo):
    files = {
        "src/pkg/__init__.py": "from .helper import work as exported\n",
        "src/pkg/helper.py": "def work():\n    return 1\n",
        "src/pkg/app.py": "from . import exported\nfrom .helper import work as alias\n\ndef main():\n    alias()\n    return exported()\n",
    }
    first = analyze(source_repo, files)
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "src/pkg/helper.py", "def work():\n    return 2\n")
    commit(source_repo)
    result = extract_python(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    found = calls(result, "src/pkg/app.py")
    assert len(found) == 2
    assert all(
        c.target.targets == ("src/pkg/helper.py#work",) and c.target.status == "resolved"
        for c in found
    )
    assert "src/pkg/helper.py#work" in result.analysis.change_set.changed_symbol_ids
    assert "src/pkg/app.py#main" not in result.analysis.change_set.changed_symbol_ids
    assert first.analysis.change_set.changed_symbol_ids == ()


def test_parameters_bindings_shadowing_and_dynamic_targets(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI as Client
def create(): pass
def wrapper(Client, fn):
    client = Client()
    fn()
    return client.responses.create(model="not-proven")
client = Client()
async def run():
    alias = client
    return await alias.responses.create(model="gpt-4.1", input="hi")
def dynamic(registry, name):
    return registry[name]()
"""
        },
    )
    found = calls(result)
    sdk = [c for c in found if c.callee.text == "alias.responses.create"][0]
    assert sdk.target.targets == ("external:openai.OpenAI.responses.create",)
    shadow = [c for c in found if c.callee.text == "client.responses.create"][0]
    assert shadow.target.status == "unknown"
    assert next(c for c in found if c.callee.text == "registry[name]").target.status == "unknown"
    assert sdk.awaited
    assert sdk.arguments[0].name == "model"
    assert sdk.arguments[0].value.value == "gpt-4.1"
    assert result.analysis.bindings
    for ref in result.analysis.evidence:
        excerpt = result.registry.freeze().read_excerpt(ref.evidence_id)
        assert ref.snippet_digest == "sha256:" + hashlib.sha256(excerpt.text.encode()).hexdigest()


def test_initializer_attribute_and_multiple_assignments_remain_candidates(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """import openai
class Agent:
    def __init__(self):
        self.client = openai.AsyncOpenAI()
    async def run(self):
        return await self.client.responses.create(input="hello")
"""
        },
    )
    call = next(c for c in calls(result) if c.callee.text == "self.client.responses.create")
    assert call.target.targets == ("external:openai.AsyncOpenAI.responses.create",)
    assert call.target.status == "candidate"


def test_conditional_reassignment_and_decorated_symbols_not_resolved(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
def plain(): pass
@decorate
def decorated(): pass
fn = plain
if condition:
    fn = decorated
fn()
decorated()
"""
        },
    )
    for call in calls(result):
        if call.callee.text in {"fn", "decorated"}:
            assert call.target.status != "resolved"


def test_local_module_shadows_installed_sdk(source_repo):
    result = analyze(
        source_repo,
        {
            "openai.py": "def OpenAI():\n    return object()\n",
            "app.py": "import openai\nclient = openai.OpenAI()\nclient.responses.create(input='hello')\n",
        },
    )
    constructor = next(c for c in calls(result) if c.callee.text == "openai.OpenAI")
    assert constructor.target.targets == ("openai.py#OpenAI",)
    assert (
        next(c for c in calls(result) if c.callee.text == "client.responses.create").target.status
        == "unknown"
    )


def test_ambiguous_module_and_cyclic_reexport_stay_unknown(source_repo):
    result = analyze(
        source_repo,
        {
            "pkg/a.py": "from .b import f\n",
            "pkg/b.py": "from .a import f\n",
            "app.py": "from pkg.a import f\nf()\n",
        },
    )
    assert calls(result)[0].target.status == "unknown"
    write(source_repo, "duplicate/app.py", "def f(): pass\n")
    result = analyze(
        source_repo,
        {"app.py": "def f(): pass\nf()\n", "consumer.py": "import app\napp.f()\n"},
        options=PythonOptions(source_roots=(".", "duplicate")),
    )
    assert calls(result, "consumer.py")[0].target.status == "unknown"


def test_syntax_failure_does_not_report_all_symbols_deleted(source_repo):
    analyze(source_repo, {"app.py": "def main():\n    return 1\n", "ok.py": "def helper(): pass\n"})
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    result = analyze(source_repo, {"app.py": "def invalid(\n"}, before=base)
    assert result.analysis.change_set.changed_symbol_ids == ()
    assert result.analysis.change_set.unresolved
    assert any(
        c.path == "app.py" and c.side == HEAD and c.syntax.status == "unsupported"
        for c in result.analysis.coverage
    )
    assert any(s.path == "ok.py" and s.side == HEAD for s in result.analysis.symbols)


def test_asserts_loops_conditions_and_nested_function_ownership(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def run():
    for i in range(3):
        def inner():
            return external()
        if i > 1:
            break
        assert helper(i)
    while True:
        awaitable()
        break
"""
        },
    )
    loops = [loop for loop in result.analysis.loops if loop.side == HEAD]
    assert len(loops) == 2
    assert all(loop.break_conditions for loop in loops)
    nested = next(c for c in calls(result) if c.callee.text == "external")
    assert nested.symbol_id == "app.py#run.inner"
    assert nested.loop_ids == ()
    helper = next(c for c in calls(result) if c.callee.text == "helper")
    assert helper.loop_ids == (loops[0].loop_id,)
    assert any(a.symbol_id == "app.py#run" for a in result.analysis.assertions)


def test_empty_comment_only_bom_crlf_and_no_final_newline(source_repo):
    result = analyze(
        source_repo,
        {
            "empty.py": "",
            "comments.py": "# only comment\n",
            "app.py": "\ufeffdef hello():\r\n    return '中'",
            "unicode.py": "x = '\\u2028'\n",
        },
    )
    assert all(c.syntax.status == "analyzed" for c in result.analysis.coverage)
    assert any(s.symbol_id == "app.py#hello" for s in result.analysis.symbols)
    assert result.analysis.change_set.changed_symbol_ids == ()


def test_budgets_and_star_import_limitations(source_repo):
    result = analyze(
        source_repo,
        {"app.py": "from other import *\nf()\n", "huge.py": "x = 1\n" * 100},
        options=PythonOptions(max_file_bytes=100),
    )
    assert (
        next(c for c in result.analysis.coverage if c.path == "huge.py").syntax.status
        == "unsupported"
    )
    assert any(u.feature == "import" for u in result.analysis.facts.unresolved)
    assert calls(result)[0].target.status == "unknown"


def test_snapshot_deleted_after_capture_customer_top_level_never_executes(source_repo, tmp_path):
    marker = tmp_path / "executed"
    write(
        source_repo,
        "app.py",
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef run(): pass\n",
    )
    commit(source_repo)
    captured = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    import shutil

    shutil.rmtree(source_repo)
    first = extract_python(captured)
    second = extract_python(captured)
    assert first.analysis == second.analysis
    assert not marker.exists()
    assert len(first.analysis.symbols) > 0


def test_private_ir_validates_side_and_owner(source_repo):
    from genesis_ci.python.validate import validate_python

    result = analyze(source_repo, {"app.py": "def run():\n    return external()\n"})
    call = calls(result)[0]
    tampered = call.model_copy(update={"side": BASE})
    with pytest.raises(ValueError, match="side"):
        validate_python(result.analysis.model_copy(update={"calls": (tampered,)}))


def test_bom_evidence_columns_match_first_line_tokens(source_repo):
    result = analyze(source_repo, {"app.py": "\ufeffprint('中')\r\n"})
    reader = result.registry.freeze()
    call = calls(result)[0]
    assert reader.read_excerpt(call.evidence_ids[0]).text == "print('中')"
    ref = next(ref for ref in result.analysis.evidence if ref.evidence_id == call.evidence_ids[0])
    assert ref.range.start_column == 1


def test_call_before_local_definition_is_not_resolved(source_repo):
    result = analyze(source_repo, {"app.py": "work()\ndef work(): pass\n"})
    assert calls(result)[0].target.status == "unknown"


def test_imported_module_mutation_invalidates_exported_symbol(source_repo):
    result = analyze(
        source_repo,
        {
            "helper.py": "def work(): pass\nexec(runtime_code)\n",
            "app.py": "from helper import work\nwork()\n",
        },
    )
    assert calls(result)[0].target.status == "unknown"


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

import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, git, write
from test_python_analysis import analyze


def run(root, files, options=None):
    analyze(root, files)
    return analyze_snapshot(capture_snapshot(root, SnapshotSpec(base="HEAD", head="HEAD")), options)


def test_entry(result, sid=None):
    return next(
        entry
        for entry in result.tests
        if entry.side == "head" and (sid is None or entry.definition.symbol_id == sid)
    )


test_entry.__test__ = False


def test_fixture_visibility_alias_name_and_nearest_override(source_repo):
    result = run(
        source_repo,
        {
            "conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 1\n",
            "tests/conftest.py": 'from pytest import fixture as fx\n@fx(name="value")\ndef inner(): return 2\n',
            "tests/sibling/conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 3\n",
            "tests/test_main.py": "def test_value(value): assert value\n",
            "tests/local/test_local.py": "import pytest\n@pytest.fixture\ndef value(): return 4\ndef test_value(value): assert value\n",
        },
    )
    entry = test_entry(result, "tests/test_main.py#test_value")
    assert entry.fixture_candidates == ("tests/conftest.py#inner",)
    assert entry.fixture_uses[0].resolution.status == "candidate"
    local = test_entry(result, "tests/local/test_local.py#test_value")
    assert local.fixture_candidates == ("tests/local/test_local.py#value",)


def test_class_fixture_is_visible_only_to_its_class(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_classes.py": """import pytest
@pytest.fixture
def value(): return 1
class TestOne:
    @pytest.fixture
    def value(self): return 2
    def test_one(self, value): assert value
class TestTwo:
    def test_two(self, value): assert value
def helper():
    def test_nested(value): assert value
"""
        },
    )
    assert test_entry(result, "tests/test_classes.py#TestOne.test_one").fixture_candidates == (
        "tests/test_classes.py#TestOne.value",
    )
    assert test_entry(result, "tests/test_classes.py#TestTwo.test_two").fixture_candidates == (
        "tests/test_classes.py#value",
    )
    assert not any("test_nested" in entry.definition.symbol_id for entry in result.tests)


def test_fixture_dependencies_use_requesting_test_scope_and_autouse(source_repo):
    result = run(
        source_repo,
        {
            "app.py": "def work(): return 1\n",
            "tests/conftest.py": """import pytest
from app import work
@pytest.fixture
def service(value): return work()
@pytest.fixture(autouse=True)
def boot(): return work()
@pytest.fixture
def value(): return "ancestor"
""",
            "tests/test_main.py": """import pytest
@pytest.fixture
def value(): return "local"
@pytest.mark.usefixtures("service")
def test_main(): assert True
""",
        },
    )
    entry = test_entry(result)
    assert set(entry.fixture_candidates) == {
        "tests/conftest.py#service",
        "tests/conftest.py#boot",
        "tests/test_main.py#value",
    }
    assert entry.fixture_called_symbol_ids == ("app.py#work",)
    assert entry.called_symbol_ids == ()
    assert entry.asserted_symbol_ids == ()
    assert any(
        use.kind == "dependency" and use.requested_by == "tests/conftest.py#service"
        for use in entry.fixture_uses
    )
    assert any(use.kind == "autouse" for use in entry.fixture_uses)


def test_direct_indirect_params_defaults_and_variadics(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_params.py": """import pytest
@pytest.fixture
def value(): return 1
@pytest.fixture
def indirect_value(): return 2
@pytest.mark.parametrize("value, indirect_value", [(3, 4)], indirect=["indirect_value"])
def test_values(value, indirect_value, optional=5, *args, **kwargs):
    assert value
""",
        },
    )
    entry = test_entry(result)
    assert entry.parameterized_names == ("value",)
    assert entry.fixture_parameters == ("indirect_value",)
    assert entry.fixture_candidates == ("tests/test_params.py#indirect_value",)


def test_cycles_and_budget_are_explicit(source_repo):
    files = {
        "tests/test_cycle.py": """import pytest
@pytest.fixture
def a(b): return b
@pytest.fixture
def b(a): return a
def test_cycle(a): assert a
"""
    }
    result = run(source_repo, files)
    assert any("cycle" in limit for limit in test_entry(result).limitations)
    limited = analyze_snapshot(
        capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD")),
        PythonOptions(max_graph_visits=1),
    )
    assert any("budget" in limit for limit in test_entry(limited).limitations)


def test_fixture_only_association_to_changed_code_is_not_asserted_coverage(source_repo):
    run(
        source_repo,
        {
            "app.py": "def build(): return 1\n",
            "tests/conftest.py": "import pytest\nfrom app import build\n@pytest.fixture\ndef service(): return build()\n",
            "tests/test_main.py": "def test_main(service): assert service\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def build(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    entry = test_entry(result)
    assert "app.py#build" in entry.definition.association.targets
    assert entry.fixture_called_symbol_ids == ("app.py#build",)
    assert entry.asserted_symbol_ids == ()
    assert entry.definition.association.status == "candidate"


def test_patch_decorators_order_new_value_and_mock_assertions(source_repo):
    result = run(
        source_repo,
        {
            "app.py": "def send(): pass\ndef save(): pass\n",
            "tests/test_main.py": """from unittest.mock import patch as p
@p("app.send")
@p("app.save")
def test_main(save_mock, send_mock, service):
    send_mock.assert_not_called()
    save_mock.assert_called_once_with(1)
@p("app.send", new=None)
def test_replacement(service):
    service.assert_called()
""",
        },
    )
    entry = test_entry(result, "tests/test_main.py#test_main")
    assert entry.injected_mock_parameters == ("save_mock", "send_mock")
    assert entry.fixture_parameters == ("service",)
    assert entry.mocked_symbol_ids == ("app.py#save", "app.py#send")
    assert set(entry.mock_assertions) == {
        "send_mock.assert_not_called()",
        "save_mock.assert_called_once_with(1)",
    }
    replaced = test_entry(result, "tests/test_main.py#test_replacement")
    assert replaced.injected_mock_parameters == ()
    assert replaced.mock_assertions == ()


def test_context_patch_object_and_raises_vs_factories(source_repo):
    result = run(
        source_repo,
        {
            "app.py": "def send(): pass\n",
            "tests/test_main.py": """import app
import pytest
from unittest.mock import patch
def test_context():
    with patch.object(app, "send") as mocked:
        mocked.assert_not_called()
    with pytest.raises(ValueError):
        app.send()
    patcher = patch("app.send")
    patcher.assert_not_called()
    pytest.raises(TypeError)
""",
        },
    )
    entry = test_entry(result)
    assert entry.mocked_symbol_ids == ("app.py#send",)
    assert entry.mock_assertions == ("mocked.assert_not_called()",)
    assert "pytest.raises(ValueError)" in entry.definition.assertions
    assert "pytest.raises(TypeError)" not in entry.definition.assertions


def test_monkeypatch_string_object_and_mocker_return(source_repo):
    result = run(
        source_repo,
        {
            "app.py": "def send(): pass\ndef save(): pass\n",
            "tests/test_main.py": """import app
def test_main(monkeypatch, mocker):
    monkeypatch.setattr("app.send", lambda: None)
    monkeypatch.setattr(app, "save", lambda: None)
    mocked = mocker.patch("app.send")
    mocked.assert_called_once()
""",
        },
    )
    entry = test_entry(result)
    assert entry.mocked_symbol_ids == ("app.py#save", "app.py#send")
    assert entry.mock_assertions == ("mocked.assert_called_once()",)


@pytest.mark.parametrize(
    "code",
    [
        "import pytest\n@pytest.fixture\ndef monkeypatch(): return object()\ndef test_main(monkeypatch):\n    monkeypatch.setattr('app.send', None)\n",
        "def test_main(mocker):\n    mocker = other()\n    mocker.patch('app.send')\n",
        "def test_main(client):\n    client.assert_called_once()\n",
    ],
)
def test_shadowed_plugin_fixture_or_arbitrary_assert_method_not_mock(source_repo, code):
    result = run(source_repo, {"app.py": "def send(): pass\n", "tests/test_main.py": code})
    entry = test_entry(result)
    assert entry.mock_uses == ()
    assert entry.mock_assertions == ()


def test_dynamic_targets_remain_unknown_and_mock_only_change_associates(source_repo):
    run(
        source_repo,
        {
            "app.py": "def send(): return 1\n",
            "tests/test_main.py": """from unittest.mock import patch
@patch("app.send")
def test_send(mock_send):
    mock_send.assert_not_called()
def test_dynamic(target):
    patch(target)
""",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def send(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    entry = test_entry(result, "tests/test_main.py#test_send")
    assert entry.definition.association.targets == ("app.py#send",)
    assert entry.called_symbol_ids == ()
    assert entry.asserted_symbol_ids == ()
    dynamic = test_entry(result, "tests/test_main.py#test_dynamic")
    assert dynamic.mock_uses[0].target.status == "unknown"
    assert dynamic.limitations


def test_fixture_sources_never_execute_and_context_evidence_is_side_correct(source_repo, tmp_path):
    marker = tmp_path / "ran"
    result = run(
        source_repo,
        {
            "tests/conftest.py": f"import pytest\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n@pytest.fixture\ndef value(): raise RuntimeError('never run')\n",
            "tests/test_main.py": "def test_main(value): assert value\n",
        },
    )
    assert not marker.exists()
    entry = test_entry(result)
    refs = {ref.evidence_id: ref for ref in result.local.evidence}
    assert all(refs[ref].side == "head" for ref in entry.definition.evidence_ids)
    assert any(refs[ref].path == "tests/conftest.py" for ref in entry.definition.evidence_ids)
    assert result.reader.read_selected(entry.definition.evidence_ids)


def test_test_context_validator_rejects_cross_side_fixture(source_repo):
    from genesis_ci.test_index import validate_test_index

    result = run(source_repo, {"tests/test_main.py": "def test_main(value): assert value\n"})
    entry = test_entry(result)
    base_ref = next(ref.evidence_id for ref in result.local.evidence if ref.side == "base")
    invalid = entry.model_copy(
        update={"definition": entry.definition.model_copy(update={"evidence_ids": (base_ref,)})}
    )
    with pytest.raises(ValueError, match="crosses snapshot"):
        validate_test_index(result.extraction.analysis, [invalid])


def test_mock_receiver_before_binding_and_after_reassignment_not_assertion(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_main.py": """from unittest.mock import patch
def test_before():
    mocked.assert_called_once()
    with patch("app.send") as mocked:
        pass
@patch("app.send")
def test_reassigned(mocked):
    mocked = arbitrary()
    mocked.assert_called_once()
"""
        },
    )
    assert all(not entry.mock_assertions for entry in result.tests)


def test_association_report_missing_assert_is_limited_to_test_body(source_repo):
    run(
        source_repo,
        {
            "app.py": "def work(): return 1\n",
            "tests/test_main.py": "from app import work\ndef test_smoke(): work()\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def work(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    finding = next(f for f in result.report.findings if f.category == "acceptance_tests")
    assert "this test body" in finding.gap
    assert "no tests were run" in finding.condition
    assert finding.evidence_ids


def test_fixture_candidate_limitations_downgrade_acceptance_context(source_repo):
    run(
        source_repo,
        {
            "app.py": "def work(): return 1\n",
            "tests/test_main.py": "from app import work\ndef test_smoke(plugin_value): assert work() == 1\n",
            ".genesis/flows.yaml": "schema_version: 1\nflows:\n- id: main\n  name: Main\n  status: confirmed\n  entries: [app.py#work]\n  acceptance: [Return one]\n",
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def work(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert result.local.capabilities.acceptance_tests.status == "insufficient_context"
    assert any(item.code == "test_context_partial" for item in result.local.limitations)


def test_unparsed_nearer_conftest_does_not_fall_through_to_ancestor(source_repo):
    result = run(
        source_repo,
        {
            "conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 1\n",
            "tests/conftest.py": "def invalid(:\n",
            "tests/test_main.py": "def test_main(value, monkeypatch):\n    monkeypatch.setattr('app.send', None)\n",
        },
    )
    entry = test_entry(result)
    assert not entry.fixture_candidates
    assert any("conftest inputs" in message for message in entry.limitations)
    assert not entry.mock_uses


def test_conditional_autouse_registration_is_not_silently_complete(source_repo):
    result = run(
        source_repo,
        {
            "tests/conftest.py": "import pytest\n@pytest.fixture(autouse=enabled)\ndef boot(): pass\n",
            "tests/test_main.py": "def test_main(): assert True\n",
        },
    )
    assert any("dynamic configuration" in message for message in test_entry(result).limitations)


def test_usefixtures_names_are_not_split_like_parametrize(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_main.py": """import pytest
@pytest.fixture
def a(): pass
@pytest.fixture
def b(): pass
@pytest.mark.usefixtures("a,b")
def test_main(): pass
"""
        },
    )
    entry = test_entry(result)
    assert entry.fixture_candidates == ()
    assert entry.fixture_uses[0].name == "a,b"


def test_dynamic_parametrization_and_duplicate_fixture_stay_explicit(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_main.py": """import pytest
@pytest.fixture
def value(): return 1
@pytest.fixture
def value(): return 2
@pytest.mark.parametrize(dynamic_names, [(1,)])
def test_main(value): assert value
"""
        },
    )
    entry = test_entry(result)
    assert any("Dynamic parametrization" in message for message in entry.limitations)
    assert any("duplicate" in message for message in entry.limitations)
    assert entry.fixture_uses[0].resolution.status == "candidate"


@pytest.mark.parametrize(
    "patch_expression",
    [
        'patch("app.send", replacement)',
        'patch("app.send", new=replacement)',
        'patch.object(app, "send", replacement)',
        'patch("app.send", new_callable=custom_factory)',
    ],
)
def test_context_explicit_replacement_not_assumed_mock(source_repo, patch_expression):
    result = run(
        source_repo,
        {
            "app.py": "def send(): pass\n",
            "tests/test_main.py": "import app\nfrom unittest.mock import patch\ndef test_main():\n    with "
            + patch_expression
            + " as replaced:\n        replaced.assert_called_once()\n",
        },
    )
    entry = test_entry(result)
    assert entry.mock_uses
    assert entry.mock_assertions == ()


def test_custom_factory_injects_parameter_without_proving_mock_type(source_repo):
    result = run(
        source_repo,
        {
            "tests/test_main.py": """from unittest.mock import patch
@patch("app.send", new_callable=custom_factory)
def test_main(replaced, mocker):
    replaced.assert_called_once()
    value = mocker.patch("app.send", new=custom_object)
    value.assert_called_once()
"""
        },
    )
    entry = test_entry(result)
    assert entry.injected_mock_parameters == ("replaced",)
    assert entry.fixture_parameters == ("mocker",)
    assert entry.mock_assertions == ()


def test_imported_fixture_does_not_falsely_choose_ancestor(source_repo):
    result = run(
        source_repo,
        {
            "conftest.py": "import pytest\n@pytest.fixture\ndef value(): return 1\n",
            "helpers.py": "import pytest\n@pytest.fixture\ndef value(): return 2\n",
            "tests/test_main.py": "from helpers import value\ndef test_main(value): assert value\n",
        },
    )
    assert test_entry(result).fixture_candidates == ()
    assert test_entry(result).fixture_uses[0].resolution.status == "unknown"


def test_fixture_mock_context_projects_through_existing_b4_contract(source_repo):
    from genesis_ci.report import assemble_report
    from genesis_contracts.models import AnalysisRequest, SemanticAnalysisResponse
    from genesis_contracts.validation import validate_request_against_local

    run(
        source_repo,
        {
            "app.py": "def work(): return 1\n",
            "tests/conftest.py": "import pytest\nfrom app import work\n@pytest.fixture\ndef service(): return work()\n",
            "tests/test_main.py": 'from unittest.mock import patch\n@patch("app.work")\ndef test_main(mock_work, service):\n    mock_work.assert_called_once_with(service)\n',
        },
    )
    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def work(): return 2\n")
    commit(source_repo)
    result = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    local = result.local
    fields = (
        "change_set",
        "facts",
        "agent_loops",
        "impact_graph",
        "flows",
        "flow_impacts",
        "test_definitions",
        "intents",
        "evidence",
        "rule_findings",
        "estimates",
    )
    request = AnalysisRequest(
        request_id="pytest-handoff",
        snapshot_id=local.snapshot.snapshot_id,
        cli_version="0.4.0-static",
        **{name: getattr(local, name) for name in fields},
        excerpts=result.reader.read_selected(tuple(ref.evidence_id for ref in local.evidence)),
    )
    validate_request_against_local(local, request)
    response = SemanticAnalysisResponse(
        request_id=request.request_id,
        snapshot_id=request.snapshot_id,
        section_status=local.capabilities,
        semantic_version="test-only",
    )
    report = assemble_report(
        local,
        request,
        response,
        analyzer_version="0.4.0-static",
        rule_version="0.4.0-structural",
        parser_limitations=("Static pytest subset",),
    )
    assert any(f.category == "acceptance_tests" for f in report.findings)
    assert report.analysis_status == "partial"
    entry = test_entry(result)
    assert "mock_work.assert_called_once_with(service)" in entry.definition.assertions
    assert entry.fixture_called_symbol_ids == entry.mocked_symbol_ids == ("app.py#work",)


def test_report_test_limit_is_explicit(source_repo):
    from genesis_ci.pytest_context.report import test_findings
    from genesis_contracts.models import Resolution

    result = run(source_repo, {"tests/test_main.py": "def test_main(): pass\n"})
    entry = test_entry(result)
    entries = tuple(
        entry.model_copy(
            update={
                "definition": entry.definition.model_copy(
                    update={
                        "test_id": str(index),
                        "association": Resolution(
                            status="candidate", targets=("app.py#work",), reason="synthetic test"
                        ),
                    }
                )
            }
        )
        for index in range(51)
    )
    findings = test_findings(entries)
    assert len(findings) == 50
    assert "50 of 51" in findings[-1].gap

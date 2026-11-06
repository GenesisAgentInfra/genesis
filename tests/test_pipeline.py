import json
import shutil

import httpx
import pytest
from genesis_ci.cli import app
from genesis_ci.cost import estimate_costs
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.patterns import detect_patterns
from genesis_ci.pipeline import analyze_snapshot, save_analysis
from genesis_ci.snapshot_store import load_snapshot, save_snapshot
from genesis_contracts.cost import CostInputs
from genesis_contracts.models import AnalysisResponse, LocalAnalysis
from genesis_contracts.validation import validate_local_analysis, validate_public_response
from test_git_snapshot import commit, git, write
from test_python_analysis import analyze
from typer.testing import CliRunner


def scenario(snapshot_id, call, **changes):
    entry = dict(
        call_id=call.call_id,
        model=call.model.value,
        input_tokens=1000,
        output_tokens=200,
        invocations=3,
        quantity_source="test workload",
        input_price_per_million="2.50",
        output_price_per_million="10",
        price_source="explicit synthetic test price",
        price_date="2026-11-03",
    )
    entry.update(changes)
    return CostInputs(snapshot_id=snapshot_id, scenarios=(entry,))


def changed_snapshot(root):
    write(
        root,
        "app.py",
        'from openai import AsyncOpenAI\nclient = AsyncOpenAI()\nasync def main():\n    return await client.responses.create(model="old-model", input="hi")\n',
    )
    write(
        root,
        ".genesis/flows.yaml",
        "schema_version: 1\nflows:\n- id: main\n  name: Main\n  status: confirmed\n  entries: [app.py#main]\n  acceptance: [Return an answer]\n",
    )
    base = commit(root)
    write(
        root,
        "app.py",
        'from openai import AsyncOpenAI\nclient = AsyncOpenAI()\nasync def main():\n    return await client.responses.create(model="new-model", input="hello world")\n',
    )
    head = commit(root)
    return capture_snapshot(
        root,
        __import__("genesis_contracts.snapshot", fromlist=["SnapshotSpec"]).SnapshotSpec(
            base=base, head=head
        ),
    )


def test_real_snapshot_pipeline_and_cli_without_live_repo_or_network(
    source_repo, tmp_path, monkeypatch
):
    snapshot = changed_snapshot(source_repo)
    frozen = tmp_path / "capture"
    save_snapshot(snapshot, frozen)
    shutil.rmtree(source_repo)
    monkeypatch.setattr(
        httpx.Client, "send", lambda *a, **kw: pytest.fail("offline contacted HTTP")
    )
    result = analyze_snapshot(load_snapshot(frozen))
    validate_local_analysis(result.local)
    validate_public_response(result.report)
    assert result.local.intents and result.local.flow_impacts
    assert any(f.finding_id.startswith("model_literal_changed") for f in result.report.findings)
    assert any(f.finding_id.startswith("prompt_literal_changed") for f in result.report.findings)
    assert any(f.category == "flow_impact" for f in result.report.findings)
    assert result.report.analysis_status == "partial"
    assert result.report.analyzer_version == "0.8.0-static"
    assert all(e.amount is None for e in result.report.estimates)
    assert all(result.reader.read_excerpt(ref.evidence_id) for ref in result.local.evidence)
    destination = tmp_path / "analysis"
    cli = CliRunner().invoke(
        app, ["analyze", "--snapshot", str(frozen), "--offline", "--output", str(destination)]
    )
    assert cli.exit_code == 2, cli.output
    assert (
        LocalAnalysis.model_validate_json((destination / "local-analysis.json").read_bytes())
        == result.local
    )
    assert (
        AnalysisResponse.model_validate_json((destination / "report.json").read_bytes())
        == result.report
    )
    assert json.loads((destination / "complete.json").read_text())["analysis_status"] == "partial"
    assert "先看中文简报：" in cli.output
    summary = destination / "summary.md"
    assert "本次只做了本地静态检查" in summary.read_text()
    assert summary.stat().st_mode & 0o777 == 0o600
    assert "insufficient_context" not in summary.read_text()
    rerun = CliRunner().invoke(
        app, ["analyze", "--snapshot", str(frozen), "--output", str(destination)]
    )
    assert rerun.exit_code == 1
    assert analyze_snapshot(load_snapshot(frozen)).report == result.report


def test_scenario_cost_is_explicit_decimal_formula_and_unknowns_survive(source_repo):
    snapshot = changed_snapshot(source_repo)
    result = analyze_snapshot(snapshot)
    call = next(c for c in result.patterns.model_calls if c.side == "head")
    inputs = scenario(snapshot.capture.manifest.snapshot_id, call)
    priced = analyze_snapshot(snapshot, cost_inputs=inputs)
    assert priced.report.estimates[0].amount == 0.0135
    assert priced.report.estimates[0].price_date == "2026-11-03"
    partial = analyze_snapshot(
        snapshot, cost_inputs=scenario(inputs.snapshot_id, call, input_tokens=None)
    )
    assert partial.report.estimates[0].amount is None
    assert partial.report.estimates[0].unknowns
    with pytest.raises(ValueError, match="different snapshot"):
        estimate_costs("wrong", result.patterns, inputs)
    with pytest.raises(ValueError, match="model"):
        analyze_snapshot(snapshot, cost_inputs=scenario(inputs.snapshot_id, call, model="other"))
    with pytest.raises(ValueError):
        scenario(inputs.snapshot_id, call, input_price_per_million="-1")


def test_unparsed_local_sdk_never_becomes_external_sdk(source_repo):
    result = analyze(
        source_repo,
        {
            "openai.py": "def invalid(:\n",
            "app.py": 'from openai import OpenAI\nclient=OpenAI()\nclient.responses.create(model="x")\n',
        },
    )
    assert not detect_patterns(result).model_calls
    assert any(c.target.status == "unknown" for c in result.analysis.calls)


def test_mutated_containers_do_not_claim_literal_prompt_size(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
client = OpenAI()
messages = [{"role": "user", "content": "hello"}]
messages.append({"role": "user", "content": dynamic()})
client.chat.completions.create(model="x", messages=messages)
"""
        },
    )
    call = next(c for c in detect_patterns(result).model_calls if c.side == "head")
    assert call.prompt[0].kind == "unknown"


def test_duplicate_definitions_change_not_lost_and_graph_valid(source_repo):
    result = analyze(
        source_repo, {"app.py": "def work(): return 1\ndef work(): return 2\nwork()\n"}
    )
    from genesis_contracts.snapshot import SnapshotSpec

    base = git(source_repo, "rev-parse", "HEAD").decode().strip()
    write(source_repo, "app.py", "def work(): return 3\ndef work(): return 2\nwork()\n")
    commit(source_repo)
    output = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert "app.py#work" in output.local.change_set.changed_symbol_ids
    assert result.analysis.calls[-1].target.status == "candidate"


def test_gather_does_not_become_serial_model_await(source_repo):
    from genesis_contracts.snapshot import SnapshotSpec

    write(source_repo, "app.py", "async def run(): pass\n")
    base = commit(source_repo)
    write(
        source_repo,
        "app.py",
        """import asyncio
from openai import AsyncOpenAI
client=AsyncOpenAI()
async def run():
    await asyncio.gather(client.responses.create(model="x"), client.responses.create(model="x"))
""",
    )
    commit(source_repo)
    output = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base=base, head="HEAD")))
    assert any(f.finding_id.startswith("sdk_sites_added") for f in output.report.findings)
    assert not any(
        f.finding_id.startswith("direct_await_sites_added") for f in output.report.findings
    )


def test_analysis_output_rejects_symlink_parent(source_repo, tmp_path):
    result = analyze_snapshot(changed_snapshot(source_repo))
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        save_analysis(result, link / "output")
    assert not list(target.iterdir())


def test_later_assignments_never_supply_earlier_receiver_or_model(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """from openai import OpenAI
def invalid():
    client.responses.create(model="x")
    client = OpenAI()
def run(model):
    client = OpenAI()
    client.responses.create(model=model)
    model = "wrong"
"""
        },
    )
    patterns = detect_patterns(result)
    assert not any(c.symbol_id == "app.py#invalid" for c in patterns.model_calls)
    assert all(
        c.model.kind == "unknown" for c in patterns.model_calls if c.symbol_id == "app.py#run"
    )


def test_namespace_package_does_not_imply_external_sdk(source_repo):
    result = analyze(
        source_repo,
        {
            "openai/custom.py": "value=1\n",
            "app.py": 'from openai import OpenAI\nclient=OpenAI()\nclient.responses.create(model="x")\n',
        },
    )
    assert not detect_patterns(result).model_calls


def test_dependency_versions_and_test_fixtures_are_static_provenance(source_repo):
    from genesis_contracts.snapshot import SnapshotSpec

    analyze(
        source_repo,
        {
            "pyproject.toml": '[project]\ndependencies = ["openai>=1.0", "anthropic==0.60; python_version > \'3.10\'"]\n',
            "uv.lock": '[[package]]\nname="openai"\nversion="1.99.0"\n',
            "tests/test_app.py": """import pytest
from unittest.mock import patch
@pytest.fixture
def service():
    raise RuntimeError("never execute fixture")
@patch("app.call")
def test_app(mock_call, service, monkeypatch):
    monkeypatch.setattr("app.other", 1)
    assert service
""",
        },
    )
    output = analyze_snapshot(capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD")))
    declarations = output.dependencies.declarations
    assert any(d.declaration == "1.99.0" and d.kind == "lock_version" for d in declarations)
    assert any(d.declaration == "openai>=1.0" for d in declarations)
    entry = next(t for t in output.tests if t.side == "head")
    assert entry.fixture_candidates == ("tests/test_app.py#service",)
    assert entry.mock_targets == ("app.call", "app.other")
    assert "service" in entry.fixture_parameters
    assert all(
        r in {e.evidence_id for e in output.local.evidence}
        for d in declarations
        for r in d.evidence_ids
    )


def test_real_local_analysis_projects_to_existing_semantic_contract(source_repo):
    from genesis_ci.report import assemble_report
    from genesis_contracts.models import AnalysisRequest, SemanticAnalysisResponse
    from genesis_contracts.validation import (
        validate_request_against_local,
        validate_semantic_response,
    )

    result = analyze_snapshot(changed_snapshot(source_repo))
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
        request_id="real-static-contract-check",
        snapshot_id=local.snapshot.snapshot_id,
        cli_version="0.2.0-static",
        **{name: getattr(local, name) for name in fields},
        excerpts=result.reader.read_selected(tuple(ref.evidence_id for ref in local.evidence)),
    )
    validate_request_against_local(local, request)
    response = SemanticAnalysisResponse(
        request_id=request.request_id,
        snapshot_id=request.snapshot_id,
        section_status=local.capabilities,
        semantic_version="test-only-no-provider",
    )
    validate_semantic_response(request, response)
    report = assemble_report(
        local,
        request,
        response,
        execution_mode="mock",
        analyzer_version="0.2.0-static",
        rule_version="0.2.0-structural",
        parser_limitations=("Real static facts; test-only semantic response",),
    )
    assert report.estimates == local.estimates
    assert report.findings == local.rule_findings
    assert report.analysis_status == "partial"

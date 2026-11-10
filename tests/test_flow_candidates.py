import json
import shutil

import httpx
import pytest
from genesis_ci.flow_candidates import discover_entries, validate_entries
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot, save_analysis
from genesis_ci.snapshot_store import load_snapshot, save_snapshot
from genesis_contracts.intelligence import FlowEntryDiscovery
from genesis_contracts.models import EvidenceSide
from genesis_contracts.python import PythonOptions
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_local_analysis, validate_public_response
from test_git_snapshot import commit, write

HEAD = EvidenceSide.head


def run_changes(root, before, after, options=None):
    for path, content in before.items():
        write(root, path, content)
    base = commit(root)
    for path, content in after.items():
        if content is None:
            (root / path).unlink()
        else:
            write(root, path, content)
    commit(root)
    snapshot = capture_snapshot(root, SnapshotSpec(base=base, head="HEAD"))
    return analyze_snapshot(snapshot, options), snapshot


def chain(root, **kwargs):
    return run_changes(
        root,
        {
            "helper.py": "def work(): return 1\n",
            "app.py": "from helper import work\ndef main(): return work()\n",
            "tests/test_app.py": "from app import main\ndef test_main(): assert main() == 1\n",
        },
        {"helper.py": "def work(): return 2\n"},
        **kwargs,
    )


def entries(result):
    return result.flows.entry_discovery.candidates


def validate(result, discovery, registered=()):
    validate_entries(
        result.extraction.analysis,
        result.impact,
        result.flows.unassigned_changes,
        set(registered),
        discovery,
    )


def test_unchanged_cross_file_entry_has_witness_path_and_head_evidence(source_repo):
    result, _ = chain(source_repo)
    assert len(entries(result)) == 1
    entry = entries(result)[0]
    assert entry.symbol_id == "app.py#main" and entry.status == "candidate"
    assert entry.paths[0].symbol_ids == ("app.py#main", "helper.py#work")
    assert entry.paths[0].changed_symbol_id == "helper.py#work"
    assert len(entry.paths[0].edge_ids) == 1
    catalog = {ref.evidence_id: ref for ref in result.local.evidence}
    assert all(catalog[ref].side == HEAD for ref in entry.evidence_ids)
    assert not any(catalog[ref].kind == "test" for ref in entry.evidence_ids)
    assert result.flows.entry_discovery.coverage.status == "analyzed"
    assert not result.flows.intents and not result.flows.head.flows
    finding = next(f for f in result.report.findings if f.finding_id == entry.candidate_id)
    assert "candidate" in finding.condition.lower()
    assert "user" in finding.recommendation
    validate_local_analysis(result.local)
    validate_public_response(result.report)


def test_two_entries_and_two_changes_are_deduplicated_with_distinct_paths(source_repo):
    result, _ = run_changes(
        source_repo,
        {
            "helpers.py": "def first(): return 1\ndef second(): return 1\n",
            "app.py": "from helpers import first, second\ndef one(): first(); second()\ndef two(): first()\n",
        },
        {"helpers.py": "def first(): return 2\ndef second(): return 2\n"},
    )
    found = {item.symbol_id: item for item in entries(result)}
    assert set(found) == {"app.py#one", "app.py#two"}
    assert len(found["app.py#one"].paths) == 2
    assert len(found["app.py#two"].paths) == 1
    assert not result.flows.entry_discovery.unresolved_change_ids


@pytest.mark.parametrize("status", ["confirmed", "draft"])
def test_registered_entries_are_not_reproposed_or_turned_into_intent(source_repo, status):
    mapping = f"schema_version: 1\nflows:\n- id: main\n  name: Main\n  status: {status}\n  entries: [app.py#main]\n"
    if status == "confirmed":
        mapping += "  acceptance: [Return an answer]\n"
    result, _ = run_changes(
        source_repo,
        {"app.py": "def main(): return 1\n", ".genesis/flows.yaml": mapping},
        {"app.py": "def main(): return 2\n"},
    )
    assert not entries(result)
    assert len(result.flows.intents) == (1 if status == "confirmed" else 0)


@pytest.mark.parametrize("mapping", ["flows: [invalid", "schema_version: 1\nflows: []\n"])
def test_invalid_or_empty_map_preserves_code_candidates(source_repo, mapping):
    result, _ = run_changes(
        source_repo,
        {"app.py": "def main(): return 1\n", ".genesis/flows.yaml": mapping},
        {"app.py": "def main(): return 2\n"},
    )
    assert [e.symbol_id for e in entries(result)] == ["app.py#main"]
    assert not result.local.intents


def test_module_call_supports_function_entry_but_is_not_itself_an_entry(source_repo):
    result, _ = run_changes(
        source_repo,
        {"app.py": "def main(): return 1\nif __name__ == '__main__': main()\n"},
        {"app.py": "def main(): return 2\nif __name__ == '__main__': main()\n"},
    )
    assert [e.symbol_id for e in entries(result)] == ["app.py#main"]
    edge = next(e for e in result.impact.graph.edges if e.source_id == "head::app.py#<module>")
    assert set(edge.evidence_ids) <= set(entries(result)[0].evidence_ids)


def test_nested_functions_and_tests_are_excluded_but_public_methods_are_candidates(source_repo):
    text = "def outer():\n    def inner(): return 1\n    return inner()\nclass C:\n    def method(self): return 1\n"
    result, _ = run_changes(
        source_repo,
        {"app.py": text, "tests/test_app.py": "def test_it(): assert 1\n"},
        {
            "app.py": text.replace("return 1", "return 2"),
            "tests/test_app.py": "def test_it(): assert 2\n",
        },
    )
    assert {e.symbol_id for e in entries(result)} == {"app.py#outer", "app.py#C.method"}
    assert not result.flows.entry_discovery.unresolved_change_ids
    assert any(
        p.changed_symbol_id == "app.py#outer.inner" for e in entries(result) for p in e.paths
    )


def test_duplicate_definitions_are_not_unique_entries(source_repo):
    result, _ = run_changes(
        source_repo,
        {"app.py": "def main(): return 1\ndef main(): return 2\n"},
        {"app.py": "def main(): return 3\ndef main(): return 2\n"},
    )
    assert not entries(result)
    assert result.flows.entry_discovery.unresolved_change_ids == ("app.py#main",)


@pytest.mark.parametrize("external_root", [False, True])
def test_mutual_recursion_terminates_and_only_real_external_root_is_suggested(
    source_repo, external_root
):
    text = "def a(): return b()\ndef b():\n    a()\n    return 1\n"
    if external_root:
        text += "def run(): return a()\n"
    result, _ = run_changes(
        source_repo, {"app.py": text}, {"app.py": text.replace("return 1", "return 2")}
    )
    assert [e.symbol_id for e in entries(result)] == (["app.py#run"] if external_root else [])
    assert bool(result.flows.entry_discovery.unresolved_change_ids) != external_root


def test_self_recursion_is_still_only_a_candidate(source_repo):
    text = "def run(n):\n    if n: return run(n-1)\n    return 1\n"
    result, _ = run_changes(
        source_repo, {"app.py": text}, {"app.py": text.replace("return 1", "return 2")}
    )
    assert [e.symbol_id for e in entries(result)] == ["app.py#run"]
    assert entries(result)[0].paths[0].edge_ids == ()


def test_dynamic_paths_and_parse_failures_keep_explicit_coverage_gaps(source_repo):
    result, _ = run_changes(
        source_repo,
        {
            "app.py": "def run(callback):\n    callback()\n    return 1\n",
            "broken.py": "def broken(:\n",
        },
        {"app.py": "def run(callback):\n    callback()\n    return 2\n"},
    )
    assert entries(result)[0].status == "candidate"
    assert result.flows.entry_discovery.coverage.status == "insufficient_context"
    assert "Input graph" in result.flows.entry_discovery.coverage.reason


def test_deleted_only_changes_have_no_head_candidate(source_repo):
    result, _ = run_changes(
        source_repo,
        {"gone.py": "def gone(): return 1\n", "keep.py": "VALUE=1\n"},
        {"gone.py": None},
    )
    assert any(item.side == "base" for item in result.flows.unassigned_changes)
    assert not entries(result)
    assert not result.flows.entry_discovery.unresolved_change_ids


def test_shared_traversal_budget_does_not_promote_frontier_to_root(source_repo):
    result, _ = chain(source_repo, options=PythonOptions(max_graph_visits=1))
    assert not entries(result)
    assert result.flows.entry_discovery.unresolved_change_ids == ("helper.py#work",)
    assert "budget exhausted" in result.flows.entry_discovery.coverage.reason
    assert any(item.code == "flow_entry_discovery_partial" for item in result.report.limitations)


@pytest.mark.parametrize("budget", ["MAX_PATHS", "MAX_CANDIDATES", "MAX_PATH_LENGTH"])
def test_output_and_path_budgets_are_explicit(source_repo, monkeypatch, budget):
    monkeypatch.setattr("genesis_ci.flow_candidates." + budget, 0)
    result, _ = chain(source_repo)
    assert not entries(result)
    assert "budget" in result.flows.entry_discovery.coverage.reason


def test_candidate_edges_and_branch_conditions_are_kept_in_witness(source_repo):
    result, _ = chain(source_repo)
    edge = next(e for e in result.impact.graph.edges if e.source_id == "head::app.py#main")
    updated = edge.model_copy(update={"resolution": "candidate", "condition": "if enabled"})
    graph = result.impact.graph.model_copy(
        update={"edges": tuple(updated if e == edge else e for e in result.impact.graph.edges)}
    )
    impact = result.impact.model_copy(update={"graph": graph})
    found = discover_entries(
        result.extraction.analysis, impact, result.flows.unassigned_changes, set()
    )
    assert found.candidates[0].paths[0].edge_ids == (edge.edge_id,)
    assert found.candidates[0].status == "candidate"
    assert found.coverage.status == "insufficient_context"


@pytest.mark.parametrize(
    "bad", ["edge", "path", "evidence", "side", "duplicate", "unresolved", "registered"]
)
def test_validator_rejects_forged_or_incomplete_candidate_provenance(source_repo, bad):
    result, _ = chain(source_repo)
    discovery = result.flows.entry_discovery
    entry = discovery.candidates[0]
    path = entry.paths[0]
    if bad == "edge":
        entry = entry.model_copy(
            update={"paths": (path.model_copy(update={"edge_ids": ("missing",)}),)}
        )
    elif bad == "path":
        entry = entry.model_copy(
            update={
                "paths": (path.model_copy(update={"symbol_ids": tuple(reversed(path.symbol_ids))}),)
            }
        )
    elif bad == "evidence":
        entry = entry.model_copy(update={"paths": (path.model_copy(update={"evidence_ids": ()}),)})
    elif bad == "side":
        entry = entry.model_copy(
            update={
                "evidence_ids": (
                    *entry.evidence_ids,
                    next(r.evidence_id for r in result.local.evidence if r.side == "base"),
                )
            }
        )
    elif bad == "unresolved":
        discovery = discovery.model_copy(update={"unresolved_change_ids": ("helper.py#work",)})
    discovery = discovery.model_copy(
        update={"candidates": (entry, entry) if bad == "duplicate" else (entry,)}
    )
    with pytest.raises(ValueError):
        validate(result, discovery, (entry.symbol_id,) if bad == "registered" else ())


def test_frozen_replay_and_serialized_artifacts_need_no_repo_or_http(
    source_repo, tmp_path, monkeypatch
):
    result, snapshot = chain(source_repo)
    frozen = tmp_path / "snapshot"
    save_snapshot(snapshot, frozen)
    shutil.rmtree(source_repo)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **k: pytest.fail("offline contacted HTTP"))
    replay = analyze_snapshot(load_snapshot(frozen))
    assert replay.flows.entry_discovery == result.flows.entry_discovery
    output = tmp_path / "analysis"
    save_analysis(replay, output)
    data = json.loads((output / "flows.json").read_text())
    assert (
        FlowEntryDiscovery.model_validate(data["entry_discovery"]) == replay.flows.entry_discovery
    )
    assert "Candidate flow entry app.py#main" in (output / "report.md").read_text()
    assert not replay.local.intents


def test_diamond_uses_shortest_path_and_ids_ignore_line_shifts(source_repo):
    app = "from helper import work\ndef middle(): return work()\ndef main():\n    middle()\n    return work()\n"
    result, _ = run_changes(
        source_repo,
        {"helper.py": "def work(): return 1\n", "app.py": app},
        {"helper.py": "def work(): return 2\n"},
    )
    entry = entries(result)[0]
    assert entry.paths[0].symbol_ids == ("app.py#main", "helper.py#work")
    replay, _ = run_changes(
        source_repo,
        {"helper.py": "def work(): return 1\n", "app.py": "\n\n" + app},
        {"helper.py": "def work(): return 2\n"},
    )
    assert entries(replay)[0].candidate_id == entry.candidate_id


def test_real_output_cap_retains_full_counts_and_limits_report(source_repo):
    before = "".join(f"def entry_{i:03}(): return 1\n" for i in range(102))
    result, _ = run_changes(
        source_repo, {"app.py": before}, {"app.py": before.replace("return 1", "return 2")}
    )
    assert len(entries(result)) == 100
    assert len(result.flows.entry_discovery.unresolved_change_ids) == 2
    assert "output budget" in result.flows.entry_discovery.coverage.reason
    findings = [f for f in result.report.findings if f.finding_id.startswith("flow_entry_")]
    assert len(findings) == 50
    assert "50 candidates" in findings[-1].gap


def test_no_change_produces_no_entry_inventions_and_never_executes_source(source_repo):
    text = "raise RuntimeError('customer source must never execute')\ndef main(): return 1\n"
    write(source_repo, "app.py", text)
    commit(source_repo)
    snapshot = capture_snapshot(source_repo, SnapshotSpec(base="HEAD", head="HEAD"))
    result = analyze_snapshot(snapshot)
    assert not entries(result)
    assert not result.flows.entry_discovery.unresolved_change_ids
    assert result.flows.entry_discovery.coverage.status == "analyzed"


def test_candidates_survive_b4_request_and_report_without_new_http_fields(source_repo):
    from genesis_ci.pipeline import ANALYZER_VERSION, RULE_VERSION
    from genesis_ci.report import assemble_report
    from genesis_contracts.models import AnalysisRequest, SemanticAnalysisResponse
    from genesis_contracts.validation import validate_request_against_local

    result, _ = chain(source_repo)
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
        request_id="flow-entry-handoff",
        snapshot_id=local.snapshot.snapshot_id,
        cli_version=ANALYZER_VERSION,
        **{field: getattr(local, field) for field in fields},
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
        local, request, response, analyzer_version=ANALYZER_VERSION, rule_version=RULE_VERSION
    )
    assert any(f.finding_id == entries(result)[0].candidate_id for f in report.findings)
    assert not request.flows and not request.intents
    validate_public_response(report)


def test_framework_method_candidate_keeps_registration_and_dispatch_uncertain(source_repo):
    source = "from framework import route\nclass Handler:\n    @route('/submit')\n    async def submit(self):\n        return await self.provider.send()\n    def _private(self): return 1\n"
    result, _ = run_changes(
        source_repo,
        {"app.py": source},
        {
            "app.py": source.replace(
                "self.provider.send()", "self.provider.send(urgent=True)"
            ).replace("return 1", "return 2")
        },
    )
    assert {item.symbol_id for item in entries(result)} == {"app.py#Handler.submit"}
    candidate = entries(result)[0]
    assert "not established" in candidate.reason
    assert "app.py#Handler._private" in result.flows.entry_discovery.unresolved_change_ids
    # A public method is a proposed review entry; neither its decorator nor the
    # dynamic receiver becomes a proven route/call merely because it was found.
    calls = [
        item
        for item in result.local.facts.calls
        if item.side == "head" and item.caller_symbol_id == "app.py#Handler.submit"
    ]
    assert calls and all(item.target.status != "resolved" for item in calls)
    validate(result, result.flows.entry_discovery)

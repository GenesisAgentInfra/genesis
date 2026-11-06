"""Generate synthetic contract examples; never execute fixture source code."""

import hashlib
import json
from pathlib import Path

import yaml
from genesis_ci.snapshot import FrozenSnapshotReader
from genesis_contracts.models import (
    AnalysisRequest,
    EvidenceRef,
    EvidenceSide,
    FileIdentity,
    LocalAnalysis,
    ReferenceRange,
    SemanticAnalysisResponse,
    SnapshotManifest,
    evidence_id_for,
    snapshot_id_for,
)
from genesis_contracts.validation import validate_local_analysis, validate_semantic_response

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "normal-five-sections",
    "dynamic-call-unresolved",
    "missing-intent-and-tests",
    "flow-entry-invalid",
)


def digest(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(name):
    dynamic = name == NAMES[1]
    missing = name == NAMES[2]
    invalid = name == NAMES[3]
    entry = "src/app.py#submit_report"
    flow = {
        "id": "submit-report",
        "name": "提交报告",
        "status": "draft" if missing else "confirmed",
        "entries": ["src/app.py#deleted_entry" if invalid else entry],
        "acceptance": [] if missing else ["失败时不发送成功通知"],
    }
    base_flow = {**flow, "entries": [entry]}
    base = "def submit_report(report):\n    return third_party.submit(report)\n"
    head = (
        "async def submit_report(report):\n    result = third_party.submit(report)\n"
        + (
            "    callback = registry[name]\n    await callback(result)\n"
            if dynamic
            else "    await notify(result)\n"
        )
        + "    return result\n"
    )
    sources = {
        ("base", "src/app.py"): ("code", base),
        ("head", "src/app.py"): ("code", head),
        ("base", ".genesis/flows.yaml"): (
            "flow",
            yaml.safe_dump(
                {"schema_version": 1, "flows": [base_flow]}, allow_unicode=True, sort_keys=False
            ),
        ),
        ("head", ".genesis/flows.yaml"): (
            "flow",
            yaml.safe_dump(
                {"schema_version": 1, "flows": [flow]}, allow_unicode=True, sort_keys=False
            ),
        ),
        ("head", "intent/pr.md"): (
            "intent",
            "PR: 提交后调用动态注册的处理器。\n"
            if dynamic
            else "PR: 已加入通知，失败时不会发送。\n",
        ),
    }
    if not missing:
        sources[("head", "intent/task.md")] = (
            "intent",
            "提交成功后通知 Slack；提交失败时不发成功通知。\n",
        )
        sources[("head", "tests/test_submit.py")] = (
            "test",
            "async def test_submit_report():\n    result = await submit_report({})\n    assert result is not None\n",
        )
    files = tuple(
        FileIdentity(path=path, side=side, kind=kind, content_digest=digest(text))
        for (side, path), (kind, text) in sources.items()
    )
    revisions = {"base_revision": f"fixture-{name}-base", "head_revision": f"fixture-{name}-head"}
    snapshot = SnapshotManifest(
        snapshot_id=snapshot_id_for(files=files, **revisions),
        files=files,
        integrity_status="complete",
        **revisions,
    )
    refs = []
    by_path = {}
    out = ROOT / "fixtures" / name
    # Remove obsolete generated fixture inputs only; keep report outputs until regeneration.
    for side in ("base", "head"):
        for old in (out / side).rglob("*"):
            if old.is_file() and (side, old.relative_to(out / side).as_posix()) not in sources:
                old.unlink()
    for (side, path), (kind, text) in sources.items():
        write(out / side / path, text)
        span = ReferenceRange(start_line=1, end_line=len(text.splitlines()))
        snippet_digest = digest(text.rstrip("\n"))
        ref = EvidenceRef(
            evidence_id=evidence_id_for(
                snapshot_id=snapshot.snapshot_id,
                side=EvidenceSide(side),
                path=path,
                range=span,
                digest=snippet_digest,
            ),
            snapshot_id=snapshot.snapshot_id,
            side=side,
            path=path,
            kind=kind,
            range=span,
            snippet_digest=snippet_digest,
        )
        refs.append(ref)
        by_path[(side, path)] = ref.evidence_id
    base_id = by_path[("base", "src/app.py")]
    code_id = by_path[("head", "src/app.py")]
    flow_id = by_path[("head", ".genesis/flows.yaml")]
    claim_id = by_path[("head", "intent/pr.md")]
    intents = [
        {
            "intent_id": "claim-1",
            "source_type": "pr_description",
            "nature": "agent_claim",
            "text": sources[("head", "intent/pr.md")][1].strip(),
            "evidence_ids": [claim_id],
        }
    ]
    if not missing:
        intent_id = by_path[("head", "intent/task.md")]
        intents.extend(
            [
                {
                    "intent_id": "task-1",
                    "source_type": "task",
                    "nature": "user_intent",
                    "text": sources[("head", "intent/task.md")][1].strip(),
                    "evidence_ids": [intent_id],
                },
                {
                    "intent_id": "flow-1",
                    "source_type": "flow_acceptance",
                    "nature": "user_intent",
                    "text": flow["acceptance"][0],
                    "flow_id": flow["id"],
                    "evidence_ids": [flow_id],
                },
            ]
        )
    analyzed = {"status": "analyzed", "analyzed_scope": "Synthetic submit_report example only"}

    def insufficient(reason):
        return {"status": "insufficient_context", "reason": reason}

    statuses = {
        name: analyzed
        for name in (
            "behavior_intent",
            "flow_impact",
            "cost_risk",
            "acceptance_tests",
            "verification",
        )
    }
    if missing:
        statuses.update(
            behavior_intent=insufficient("No user intent supplied; the PR is only an agent claim."),
            acceptance_tests=insufficient(
                "No confirmed acceptance criteria or test definitions supplied."
            ),
        )
    if dynamic:
        statuses.update(
            flow_impact=insufficient("Dynamic callback target is unknown."),
            behavior_intent=insufficient(
                "Unknown callback prevents verification of notification behavior."
            ),
        )
    if invalid:
        statuses["flow_impact"] = {
            "status": "unsupported",
            "reason": "Configured entry no longer resolves.",
        }
    unresolved = (
        [
            {
                "unresolved_id": "dynamic-1",
                "feature": "call",
                "reason": "registry[name] is selected dynamically",
                "evidence_ids": [code_id],
            }
        ]
        if dynamic
        else []
    )
    local = LocalAnalysis(
        snapshot=snapshot,
        evidence=refs,
        intents=intents,
        flows=[flow],
        change_set={
            "files": [
                {
                    "change_type": "modified",
                    "base_path": "src/app.py",
                    "head_path": "src/app.py",
                    "evidence_ids": [base_id, code_id],
                }
            ],
            "changed_symbol_ids": [entry],
        },
        facts={
            "coverage": insufficient("Dynamic target remains unknown") if dynamic else analyzed,
            "functions": [
                {
                    "symbol_id": entry,
                    "side": side,
                    "kind": "function",
                    "is_async": side == "head",
                    "evidence_ids": [ref],
                }
                for side, ref in (("base", base_id), ("head", code_id))
            ],
            "calls": [
                {
                    "call_id": "call-head-1",
                    "side": "head",
                    "caller_symbol_id": entry,
                    "expression": "callback(result)" if dynamic else "notify(result)",
                    "target": {"status": "unknown", "reason": "Dynamic registry target"}
                    if dynamic
                    else {
                        "status": "candidate",
                        "targets": ["notify"],
                        "reason": "Syntactic name; external implementation not provided",
                    },
                    "awaited": True,
                    "evidence_ids": [code_id],
                }
            ],
            "awaits": [
                {
                    "fact_id": "await-1",
                    "side": "head",
                    "symbol_id": entry,
                    "expression": "await callback(result)" if dynamic else "await notify(result)",
                    "evidence_ids": [code_id],
                }
            ],
            "unresolved": unresolved,
        },
        agent_loops=[],
        impact_graph={
            "nodes": [
                {
                    "node_id": "entry",
                    "symbol_id": entry,
                    "kind": "symbol",
                    "evidence_ids": [code_id],
                },
                {
                    "node_id": "callee",
                    "kind": "unknown" if dynamic else "external",
                    "evidence_ids": [code_id],
                },
            ],
            "edges": [
                {
                    "edge_id": "wait-1",
                    "source_id": "entry",
                    "target_id": "callee",
                    "relation": "awaits",
                    "resolution": "unknown" if dynamic else "candidate",
                    "reason": "Dynamic dispatch"
                    if dynamic
                    else "External notify implementation not supplied",
                    "evidence_ids": [code_id],
                }
            ],
        },
        flow_impacts=[
            {
                "flow_id": "submit-report",
                "status": "unknown" if invalid or dynamic else "resolved",
                "entry_status": "invalid" if invalid else "valid",
                "changed_symbol_ids": [] if invalid else [entry],
                "reason": "Entry missing" if invalid else "Direct entry changed",
                "evidence_ids": [code_id, flow_id],
            }
        ],
        test_definitions=[]
        if missing
        else [
            {
                "test_id": "test-submit",
                "symbol_id": "tests/test_submit.py#test_submit_report",
                "assertions": ["result is not None"],
                "mocks": [],
                "association": {
                    "status": "candidate",
                    "targets": [entry],
                    "reason": "Matching call spelling in static test source",
                },
                "evidence_ids": [by_path[("head", "tests/test_submit.py")]],
            }
        ],
        rule_findings=[
            {
                "finding_id": "F-RULE-WAIT",
                "category": "cost_risk",
                "statement": "An awaited operation was added before returning; actual added wait is unknown.",
                "severity": "low",
                "basis": ["code_fact"],
                "evidence_ids": [base_id, code_id],
                "estimate_ids": ["wait-1"],
            }
        ],
        estimates=[
            {
                "estimate_id": "wait-1",
                "structural_signals": ["One additional serial await"],
                "parameters": [
                    {
                        "name": "added_wait",
                        "value": None,
                        "unit": "ms",
                        "unknown_reason": "No runtime measurements or external implementation supplied",
                    }
                ],
                "unknowns": ["Actual latency and failure rate"],
                "evidence_ids": [base_id, code_id],
            }
        ],
        capabilities=statuses,
        limitations=[
            {
                "code": "mock_fixture",
                "message": "Synthetic contract example, not a customer analysis.",
            }
        ]
        + (
            [
                {
                    "code": "dynamic_target_unresolved",
                    "message": "Downstream callback behavior cannot be resolved.",
                    "affects_completeness": True,
                    "evidence_ids": [code_id],
                }
            ]
            if dynamic
            else []
        ),
    )
    reader = FrozenSnapshotReader.from_directory(out, snapshot, tuple(refs))
    request = AnalysisRequest(
        request_id=f"demo-{name}",
        snapshot_id=snapshot.snapshot_id,
        cli_version="0.1.0-mock",
        **{
            key: getattr(local, key)
            for key in (
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
        },
        excerpts=reader.read_selected(tuple(ref.evidence_id for ref in refs)),
        missing_context=("user intent", "test definitions") if missing else (),
    )
    findings = []
    if not dynamic:
        findings.append(
            {
                "finding_id": "F-SEM-BEHAVIOR",
                "category": "behavior_intent",
                "statement": "The head function awaits notify(result) before returning; the base function returns submission directly.",
                "severity": "info",
                "basis": ["code_fact"],
                "evidence_ids": [base_id, code_id],
            }
        )
        if not missing:
            findings.append(
                {
                    "finding_id": "F-SEM-CLAIM",
                    "category": "behavior_intent",
                    "statement": "No success-value check appears before notify in the visible function. If submit returns a failure value instead of raising, the PR's claim is unverified.",
                    "severity": "medium",
                    "basis": ["code_fact", "user_intent", "agent_claim", "semantic_inference"],
                    "evidence_ids": [code_id, intent_id, claim_id],
                    "deviation": "unverified_claim",
                    "condition": "Only when submit returns a failure value; exceptions prevent the following notify call.",
                }
            )
    if not missing:
        findings.append(
            {
                "finding_id": "F-SEM-TEST",
                "category": "acceptance_tests",
                "statement": "The supplied test checks a non-null result; it contains no assertion about notification on failure.",
                "severity": "low",
                "basis": ["code_fact", "user_intent"],
                "evidence_ids": [by_path[("head", "tests/test_submit.py")], intent_id],
                "flow_ids": [] if invalid else ["submit-report"],
            }
        )
    suggestions = [
        {
            "suggestion_id": "V-001",
            "scenario": "Review the new awaited operation's failure behavior.",
            "conditions": ["Submission returns a failure value", "Submission raises an exception"],
            "suggested_assertions": []
            if missing or dynamic
            else ["No success notification is sent on a failure-valued submission"],
            "existing_test_evidence_ids": []
            if missing
            else [by_path[("head", "tests/test_submit.py")]],
            "rationale": "Missing intent prevents deriving business acceptance."
            if missing
            else "Distinguish return-value failures from exceptions; test definitions are not executed.",
            "questions_for_user": [
                "Which values mean submission failed?",
                "Should an awaited operation's failure change the return behavior?",
            ],
            "evidence_ids": [code_id],
        }
    ]
    response = SemanticAnalysisResponse(
        request_id=request.request_id,
        snapshot_id=snapshot.snapshot_id,
        findings=findings,
        suggestions=suggestions,
        section_status=statuses,
        semantic_version="mock-v1",
    )
    validate_local_analysis(local)
    validate_semantic_response(request, response)
    payload = {
        "snapshot": snapshot.model_dump(mode="json"),
        "evidence": [ref.model_dump(mode="json") for ref in refs],
        "local_analysis": local.model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "semantic_response": response.model_dump(mode="json"),
    }
    write(out / "semantic.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    for name in NAMES:
        build(name)

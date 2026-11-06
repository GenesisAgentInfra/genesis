"""Offline A-side orchestration; no service, provider, Git, or customer execution."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from genesis_contracts.cost import CostInputs
from genesis_contracts.estimates import PromptMeasurement
from genesis_contracts.intelligence import (
    DependencyAnalysis,
    ImpactAnalysis,
    PatternAnalysis,
    TestIndexEntry,
)
from genesis_contracts.models import AnalysisResponse, LocalAnalysis
from genesis_contracts.python import PythonOptions

from .assemble import build_local_analysis
from .change_rules import change_findings
from .cost import estimate_costs, validate_cost_estimates
from .dependencies import read_dependencies
from .flows import FlowAnalysis, map_flows
from .git_snapshot import CapturedSnapshot
from .impact import build_impact
from .patterns import detect_patterns
from .prompt_metrics import measure_prompts
from .pytest_context.report import test_findings
from .python import extract_python
from .python.extract import Extraction
from .report import assemble_report, render_markdown
from .test_index import index_tests

ANALYZER_VERSION = "0.8.0-static"
RULE_VERSION = "0.7.0-structural"
PARSER_LIMITATIONS = (
    "LibCST 1.9.0, configured Python source roots; static subset only. Customer modules/tests are never imported or executed.",
    "No runtime types, dynamic imports, descriptor/MRO resolution, interprocedural values, pytest fixture execution or semantic intent judgment.",
    "Official named OpenAI/Anthropic clients, literal dictionaries and response-derived if/match dispatch candidates; dependency constraints are provenance, not installed version verification.",
    "Loop control paths are lexical candidates; caught exceptions, finally and context managers may override transfers. Counter bounds cover only a straight-line local integer subset.",
    "Known prompt fragments use only pinned offline encodings; fragment tokens are not complete input tokens. Cost needs explicit snapshot-bound quantities and dated prices.",
)


@dataclass(frozen=True)
class PipelineResult:
    local: LocalAnalysis
    report: AnalysisResponse
    extraction: Extraction
    patterns: PatternAnalysis
    impact: ImpactAnalysis
    flows: FlowAnalysis
    tests: tuple[TestIndexEntry, ...]
    dependencies: DependencyAnalysis
    prompt_measurements: tuple[PromptMeasurement, ...] = ()
    cost_inputs: CostInputs | None = None

    @property
    def reader(self):
        return self.extraction.registry.freeze()


def analyze_snapshot(
    snapshot: CapturedSnapshot,
    options: PythonOptions | None = None,
    cost_inputs: CostInputs | None = None,
) -> PipelineResult:
    from .rules import structural_findings

    extraction = extract_python(snapshot, options)
    patterns = detect_patterns(extraction)
    impact = build_impact(extraction, patterns)
    flows = map_flows(snapshot, extraction, impact)
    tests = index_tests(extraction, impact)
    dependencies = read_dependencies(snapshot, extraction.registry)
    findings = (
        *structural_findings(extraction, patterns, flows),
        *test_findings(tests),
        *change_findings(extraction, patterns, tests),
    )
    measurements = measure_prompts(patterns)
    estimates = estimate_costs(
        snapshot.capture.manifest.snapshot_id, patterns, cost_inputs, measurements
    )
    local = build_local_analysis(
        snapshot, extraction, patterns, impact, flows, tests, findings, estimates
    )
    report = assemble_report(
        local,
        None,
        None,
        analyzer_version=ANALYZER_VERSION,
        rule_version=RULE_VERSION,
        parser_limitations=PARSER_LIMITATIONS,
    )
    return PipelineResult(
        local,
        report,
        extraction,
        patterns,
        impact,
        flows,
        tests,
        dependencies,
        measurements,
        cost_inputs,
    )


def save_analysis(result: PipelineResult, destination: Path) -> None:
    """Create private local output; completion marker is written last, never overwrite."""
    if result.prompt_measurements != measure_prompts(result.patterns):
        raise ValueError("Prompt measurements differ from frozen pattern facts")
    validate_cost_estimates(
        result.local.snapshot.snapshot_id,
        result.patterns,
        result.cost_inputs,
        result.prompt_measurements,
        result.local.estimates,
    )
    if result.report.estimates != result.local.estimates:
        raise ValueError("Report estimates differ from local calculations")
    root = destination.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Analysis output cannot use symlinks")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700, exist_ok=False)
    artifacts = {
        "local-analysis.json": result.local.model_dump(mode="json"),
        "python-analysis.json": result.extraction.analysis.model_dump(mode="json"),
        "dependencies.json": result.dependencies.model_dump(mode="json"),
        "patterns.json": result.patterns.model_dump(mode="json"),
        "prompt-measurements.json": [m.model_dump(mode="json") for m in result.prompt_measurements],
        "impact.json": result.impact.model_dump(mode="json"),
        "flows.json": {
            "head": result.flows.head.model_dump(mode="json"),
            "impacts": [i.model_dump(mode="json") for i in result.flows.impacts],
            "entry_discovery": result.flows.entry_discovery.model_dump(mode="json"),
            "unassigned_changes": [
                i.model_dump(mode="json") for i in result.flows.unassigned_changes
            ],
        },
        "tests.json": [item.model_dump(mode="json") for item in result.tests],
        "report.json": result.report.model_dump(mode="json"),
    }
    if result.local.behavior_view is not None:
        artifacts["behavior-view.json"] = result.local.behavior_view.model_dump(mode="json")
    if result.cost_inputs is not None:
        artifacts["cost-inputs.json"] = result.cost_inputs.model_dump(mode="json")
    for name, payload in artifacts.items():
        with (root / name).open("x", encoding="utf-8") as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    with (root / "report.md").open("x", encoding="utf-8") as stream:
        os.chmod(stream.fileno(), 0o600)
        stream.write(render_markdown(result.report))
    with (root / "complete.json").open("x", encoding="utf-8") as stream:
        os.chmod(stream.fileno(), 0o600)
        stream.write(
            json.dumps(
                {
                    "snapshot_id": result.local.snapshot.snapshot_id,
                    "analyzer_version": ANALYZER_VERSION,
                    "analysis_status": result.report.analysis_status.value,
                }
            )
            + "\n"
        )

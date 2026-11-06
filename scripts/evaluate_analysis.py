"""Offline synthetic acceptance corpus. Never execute any source file in a case."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.pipeline import analyze_snapshot, save_analysis
from genesis_ci.report import render_markdown
from genesis_ci.snapshot_store import load_snapshot, save_snapshot
from genesis_contracts.snapshot import SnapshotSpec
from genesis_contracts.validation import validate_local_analysis, validate_public_response

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
    )
    return subprocess.run(
        ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_files(root, files):
    for name, text in files.items():
        path = root / name
        if path.is_absolute() and not path.is_relative_to(root):
            raise ValueError("Case path escapes evaluation repository")
        if ".." in Path(name).parts:
            raise ValueError("Unsafe case path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def run_case(case, output=None):
    with tempfile.TemporaryDirectory(prefix="genesis-evaluation-") as tmp:
        root = Path(tmp).resolve() / "repository"
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.name", "Synthetic Evaluation")
        git(root, "config", "user.email", "evaluation@example.invalid")
        write_files(root, case["before"])
        git(root, "add", ".")
        git(root, "commit", "-qm", "base")
        base = git(root, "rev-parse", "HEAD")
        write_files(root, case["after"])
        git(root, "add", ".")
        git(root, "commit", "-qm", "head")
        snapshot = capture_snapshot(root, SnapshotSpec(base=base, head="HEAD"))
        frozen = Path(tmp).resolve() / "frozen"
        save_snapshot(snapshot, frozen)
        result = analyze_snapshot(load_snapshot(frozen))
        validate_local_analysis(result.local)
        validate_public_response(result.report)
        for ref in result.local.evidence:
            result.reader.read_excerpt(ref.evidence_id)
        ids = [f.finding_id for f in result.report.findings]
        missing = [p for p in case["required_rules"] if not any(i.startswith(p) for i in ids)]
        forbidden = [p for p in case["forbidden_rules"] if any(i.startswith(p) for i in ids)]
        assert not missing and not forbidden, (case["id"], missing, forbidden)
        assert result.report.analysis_status == "partial"
        assert all(f.deviation is None for f in result.report.findings)
        assert all(e.amount is None for e in result.report.estimates)
        markdown = render_markdown(result.report)
        assert all(
            title in markdown
            for title in (
                "业务变化与意图",
                "受影响流程与路径",
                "成本、等待与失败风险",
                "验收要点与已有测试",
                "验证建议",
            )
        )
        if output:
            save_analysis(result, output / case["id"])
            save_snapshot(snapshot, output / case["id"] / "snapshot")
        return {
            "id": case["id"],
            "passed": True,
            "negative_control": case["negative_control"],
            "findings": len(ids),
            "semantic_review": case["semantic_review"],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="New directory for reviewable reports")
    parser.add_argument("--case", help="Run one case ID; omit for all ten")
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
    cases = json.loads((ROOT / "examples/analysis-evaluation/cases.json").read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            parser.error("Unknown case ID")
    results = [run_case(case, args.output) for case in cases]
    summary = {
        "passed": len(results),
        "total": len(cases),
        "negative_controls": sum(c["negative_control"] for c in cases),
        "semantic_quality": "not measured; human labels and B-side model review pending",
        "cases": results,
    }
    if args.output:
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

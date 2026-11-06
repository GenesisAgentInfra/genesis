"""Build a synthetic Git case and analyze its text; never import the case modules."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_case(output: Path, *, include_source_evidence: bool = False) -> Path:
    output = output.absolute()
    if output.exists() or any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("Choose a new output directory without symlink ancestors")
    output.mkdir(mode=0o700, parents=True)
    repo = output / "repo"
    repo.mkdir(mode=0o700)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
        and key not in {"GENESIS_API_KEY", "GENESIS_SERVICE_URL", "PYTHONPATH", "PYTHONHOME"}
    }
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, *args],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()

    templates = Path(__file__).with_name("templates")

    def copy_templates(side: str) -> None:
        for source in sorted((templates / side).rglob("*.txt")):
            relative = source.relative_to(templates / side).with_suffix("")
            destination = repo / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            destination.chmod(0o600)

    git("init", "-q")
    git("config", "user.name", "Genesis Synthetic Example")
    git("config", "user.email", "synthetic@example.invalid")
    git("config", "commit.gpgsign", "false")
    copy_templates("common")
    copy_templates("base")
    git("add", "-A")
    git("commit", "-qm", "Synthetic base: approval then submission")
    base = git("rev-parse", "HEAD")
    copy_templates("head")
    git("add", "-A")
    git("commit", "-qm", "Synthetic candidate: model summary and Slack notification")
    head = git("rev-parse", "HEAD")
    report = output / "report"
    command = [
        str(Path(sys.executable).with_name("genesis")),
        "analyze",
        "--repo",
        str(repo),
        "--base",
        base,
        "--head",
        head,
        "--task",
        "task.md",
        "--pr-description",
        "pr.md",
        "--offline",
        "--output",
        str(report),
    ]
    if include_source_evidence:
        command.append("--include-source-evidence")
    result = subprocess.run(command, cwd=output, env=env, check=False, timeout=45)
    if result.returncode not in {0, 2} or not (report / "complete.json").exists():
        raise RuntimeError("Synthetic analysis did not produce a completed local artifact")
    metadata = {
        "synthetic": True,
        "customer_code_executed": False,
        "network_requested": False,
        "base": base,
        "head": head,
        "expected_analysis_status": "partial",
        "note": "Developer-owned demonstration; not customer validation or a semantic accuracy result.",
    }
    metadata_path = output / "case.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    metadata_path.chmod(0o600)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, type=Path, help="New private demonstration directory"
    )
    parser.add_argument(
        "--include-source-evidence",
        action="store_true",
        help="Also write a private frozen-source review",
    )
    args = parser.parse_args()
    report = run_case(args.output, include_source_evidence=args.include_source_evidence)
    print(f"Synthetic offline example ready: {report / 'report.md'}")
    print(
        "Partial is expected: no semantic provider, Slack, application code or tests were executed."
    )


if __name__ == "__main__":
    main()

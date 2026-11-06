"""Invoke the installed CLI with argv; PR text is frozen data, never shell code."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from genesis_ci.ci_intent import collect_ci_intents, materialize_ci_intents
from genesis_ci.workflow import ci_offline_reason


def main() -> int:
    repo = Path(
        os.environ.get("GENESIS_ACTION_REPO") or os.environ.get("GITHUB_WORKSPACE", ".")
    ).resolve()
    output = Path(os.environ["RUNNER_TEMP"]).resolve() / ("genesis-report-" + uuid4().hex)
    command = [
        str(Path(sys.executable).parent / "genesis"),
        "analyze",
        "--repo",
        str(repo),
        "--output",
        str(output),
    ]
    env = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    event = {}
    event_path = env.get("GITHUB_EVENT_PATH")
    if event_path:
        path = Path(event_path)
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError("Invalid GitHub event file")
        event = json.loads(path.read_bytes())
    pr = event.get("pull_request", {})
    base = env.get("GENESIS_ACTION_BASE") or pr.get("base", {}).get("sha")
    if base:
        command += ["--base", base]
    task = env.get("GENESIS_ACTION_TASK")
    if task:
        command += ["--task", task]
    if ci_offline_reason() or not env.get("GENESIS_API_KEY"):
        command += ["--offline"]
        env.pop("GENESIS_API_KEY", None)
    else:
        command += ["--accept-send"]
    bundle = collect_ci_intents(
        event,
        repository=env.get("GITHUB_REPOSITORY", ""),
        event_name=env.get("GITHUB_EVENT_NAME", ""),
        token=env.get("GENESIS_GITHUB_TOKEN"),
        api_url=env.get("GITHUB_API_URL", "https://api.github.com"),
    )
    # The read token belongs only to the collector, never the analysis subprocess.
    env.pop("GENESIS_GITHUB_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    with materialize_ci_intents(repo, bundle) as files:
        for source in files.sources:
            command += [
                "--task" if source.source_type == "task" else "--pr-description",
                source.path,
            ]
        command += ["--intent-metadata", files.metadata_path]
        result = subprocess.run(command, env=env, cwd=env["RUNNER_TEMP"], check=False)
    report = output / "report.json"
    valid = result.returncode in {0, 2} and report.exists() and (output / "complete.json").exists()
    status = json.loads(report.read_text())["analysis_status"] if valid else "failed"
    summary_digest = None
    if valid:
        content = (output / "summary.md").read_bytes()
        with Path(env["GITHUB_STEP_SUMMARY"]).open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            start = stream.tell()
            stream.write(content)
            stream.flush()
            stream.seek(start)
            written = stream.read()
        if written != content:
            raise ValueError("Job Summary append could not be verified")
        summary_digest = hashlib.sha256(written).hexdigest()
    with Path(env["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"analysis-status={status}\n")
        if valid:
            stream.write(f"report-directory={output}\n")
            stream.write(f"summary-sha256={summary_digest}\n")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Local orchestration of the existing frozen analysis pipeline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

from genesis_contracts.models import Limitation


def default_base(repo: Path) -> str:
    """Resolve a local merge-base without fetching or running repository hooks."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    remote = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    for ref in (remote, "refs/heads/main", "refs/heads/master"):
        if ref and (base := git("merge-base", "HEAD", ref)):
            return base
    raise ValueError("Cannot resolve the default branch merge-base; provide --base REV.")


def new_output(repo: Path) -> Path:
    return repo / ".genesis" / "analyses" / uuid.uuid4().hex


def ci_offline_reason() -> str | None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name == "pull_request_target":
        return "Privileged pull_request_target events cannot send repository content."
    if event_name not in {"pull_request", "pull_request_review", "pull_request_review_comment"}:
        return None
    try:
        path = Path(os.environ["GITHUB_EVENT_PATH"])
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError("Invalid PR event")
        pr = json.loads(path.read_bytes())["pull_request"]
        base_repo = pr["base"]["repo"]["full_name"]
        head_repo = pr["head"]["repo"]["full_name"]
        if not head_repo or not base_repo or head_repo != base_repo:
            return "Fork PR: semantic service disabled; no key or code is sent."
    except (KeyError, TypeError, ValueError, OSError):
        return "Cannot verify PR repository identity; semantic service disabled."
    return None


def with_semantic(result, request, semantic, failure=None):
    from .pipeline import ANALYZER_VERSION, PARSER_LIMITATIONS, RULE_VERSION
    from .report import assemble_report

    return replace(
        result,
        report=assemble_report(
            result.local,
            request,
            semantic,
            execution_mode="semantic",
            failure=failure,
            analyzer_version=ANALYZER_VERSION,
            rule_version=RULE_VERSION,
            parser_limitations=PARSER_LIMITATIONS,
        ),
    )


def failure(code: str, message: str) -> Limitation:
    return Limitation(code=code, message=message, affects_completeness=True)


def publish_analysis(
    result,
    output: Path,
    *,
    captured=None,
    request=None,
    preview=None,
    semantic=None,
    reader=None,
    include_source_evidence=False,
    selection_log=None,
) -> None:
    """Publish a completed private directory, never a half-written final report."""
    from .pipeline import save_analysis
    from .report import render_review_markdown
    from .report_summary import render_summary
    from .snapshot_store import save_snapshot

    output = output.absolute()
    if any(path.is_symlink() for path in (output, *output.parents)) or output.exists():
        raise ValueError("Output must be a new directory without symlink ancestors")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name("." + output.name + "-" + uuid.uuid4().hex)
    try:
        save_analysis(result, staging)
        marker = (staging / "complete.json").read_bytes()
        (staging / "complete.json").unlink()
        (staging / "report.md").write_text(
            render_review_markdown(
                result.report, result.local, entry_discovery=result.flows.entry_discovery
            ),
            encoding="utf-8",
        )
        if captured is not None:
            save_snapshot(captured, staging / "snapshot")
        artifacts = {"summary.md": render_summary(result.report, result.local)}
        if include_source_evidence:
            artifacts["review-with-source.md"] = render_review_markdown(
                result.report,
                result.local,
                reader=reader or result.reader,
                entry_discovery=result.flows.entry_discovery,
            )
        if request is not None:
            artifacts["request.json"] = request.model_dump_json(indent=2) + "\n"
            if selection_log is not None:
                artifacts["context-selection.json"] = (
                    json.dumps(
                        {
                            "snapshot_id": request.snapshot_id,
                            "decisions": selection_log,
                            "selected_evidence_ids": [ref.evidence_id for ref in request.evidence],
                            "missing_context": request.missing_context,
                            "behavior_review_version": request.behavior_review_version,
                            "behavior_view_version": request.behavior_view.version
                            if request.behavior_view
                            else None,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                )
        if semantic is not None:
            artifacts["semantic.json"] = semantic.model_dump_json(indent=2) + "\n"
        if preview is not None:
            artifacts["send-preview.txt"] = preview + "\n"
        for name, content in artifacts.items():
            with (staging / name).open("x", encoding="utf-8") as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(content)
        with (staging / "complete.json").open("xb") as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(marker)
        if output.exists():
            raise ValueError("Output already exists")
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

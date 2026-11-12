import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import typer
from genesis_contracts import AnalysisRequest, LocalAnalysis, SemanticAnalysisResponse
from genesis_contracts.models import Limitation, ServiceError
from genesis_contracts.validation import validate_request_against_local

from .agent_setup import Agent, Scope
from .report import assemble_report, render_markdown
from .snapshot import FrozenSnapshotReader

app = typer.Typer(no_args_is_help=True)
flows_app = typer.Typer(no_args_is_help=True)
app.add_typer(flows_app, name="flows")
agent_app = typer.Typer(no_args_is_help=True)
app.add_typer(agent_app, name="agent")
map_app = typer.Typer(no_args_is_help=True, help="Local business map; no service, no model.")
app.add_typer(map_app, name="map")
FIXTURE_NAMES = (
    "normal-five-sections",
    "dynamic-call-unresolved",
    "missing-intent-and-tests",
    "flow-entry-invalid",
)


def _map_failure(error: Exception) -> typer.Exit:
    """Report a refusal as JSON on stdout, like every other result of `genesis map`."""
    from pydantic import ValidationError

    from .business_map.workspace import LoopError, pydantic_problems

    if isinstance(error, LoopError):
        body = {"code": error.code, "message": str(error), "errors": error.errors}
    elif isinstance(error, ValidationError):
        body = {
            "code": "invalid_input",
            "message": "The input does not match the expected structure.",
            "errors": pydantic_problems(error),
        }
    else:
        code = getattr(error, "code", None) or (
            "not_found" if isinstance(error, FileNotFoundError) else "invalid_map_input"
        )
        body = {"code": code, "message": str(error), "errors": []}
    typer.echo(json.dumps({"error": body}, ensure_ascii=False, indent=2))
    return typer.Exit(1)


@map_app.command("prepare")
def map_prepare(
    repo: Path = typer.Option(Path("."), "--repo"),
    base: str | None = typer.Option(None, "--base", help="Compare against this revision"),
    head: str | None = typer.Option(None, "--head", help="Default: the working tree"),
    include_untracked: bool = typer.Option(False, "--include-untracked"),
    exclude: list[str] | None = typer.Option(None, "--exclude"),
) -> None:
    """Freeze a snapshot, extract facts and write the static skeleton. Calls no model.

    A repository with many source files is analyzed in several worker processes. Set
    GENESIS_WORKERS to choose how many; 1 keeps everything in one process.
    """
    from .business_map.session import prepare
    from .git_snapshot import SnapshotError

    try:
        result = prepare(
            repo,
            base=base,
            head=head,
            include_untracked=include_untracked,
            exclude=tuple(exclude or ()),
        )
    except (SnapshotError, ValueError, OSError) as error:
        raise _map_failure(error) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


def _map_call(action) -> None:
    """Run one loop action and print its JSON result; exit 1 with the errors if refused."""
    try:
        result = action()
    except (ValueError, OSError) as error:
        raise _map_failure(error) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("status") == "rejected":
        raise typer.Exit(1)


def _map_input(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@map_app.command("plan")
def map_plan(
    session: str = typer.Option(..., "--session"),
    repo: Path = typer.Option(Path("."), "--repo"),
    plan_file: Path | None = typer.Option(None, "--input", help="Omit for the default plan"),
) -> None:
    """Group entries into flows and create one task per flow."""
    from genesis_contracts.map_tasks import MapPlan

    from .business_map.workspace import Workspace

    def action():
        plan = None if plan_file is None else MapPlan.model_validate(_map_input(plan_file))
        return Workspace(repo, session).save_plan(plan)

    _map_call(action)


@map_app.command("status")
def map_status(
    session: str = typer.Option(..., "--session"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """List tasks, their state and what is still missing."""
    from .business_map.workspace import Workspace

    _map_call(lambda: Workspace(repo, session).status())


@map_app.command("context")
def map_context(
    session: str = typer.Option(..., "--session"),
    task: str = typer.Option(..., "--task"),
    repo: Path = typer.Option(Path("."), "--repo"),
    claim: bool = typer.Option(False, "--claim", help="Hold the task for this worker"),
) -> None:
    """Everything needed to start one task: entries, source and the facts to account for."""
    from .business_map.workspace import Workspace

    _map_call(lambda: Workspace(repo, session).context(task, claim))


@map_app.command("query")
def map_query(
    session: str = typer.Option(..., "--session"),
    repo: Path = typer.Option(Path("."), "--repo"),
    symbol: str | None = typer.Option(None, "--symbol"),
    search: str | None = typer.Option(None, "--search"),
) -> None:
    """Look at one symbol and its neighbours, or search the frozen source."""
    from .business_map.workspace import Workspace

    if (symbol is None) == (search is None):
        raise typer.BadParameter("give exactly one of --symbol or --search")
    workspace = Workspace(repo, session)
    _map_call(lambda: workspace.query_symbol(symbol) if symbol else workspace.search(search))


@map_app.command("read")
def map_read(
    session: str = typer.Option(..., "--session"),
    evidence: str = typer.Option(..., "--evidence"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Read the frozen source behind one evidence reference."""
    from .business_map.workspace import Workspace

    _map_call(lambda: Workspace(repo, session).read(evidence))


@map_app.command("submit")
def map_submit(
    session: str = typer.Option(..., "--session"),
    task: str = typer.Option(..., "--task"),
    submission: Path = typer.Option(..., "--input"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Check one submission for a task. It is accepted or rejected as a whole."""
    from .business_map.workspace import Workspace

    _map_call(lambda: Workspace(repo, session).submit(task, _map_input(submission)))


@map_app.command("diff")
def map_diff(
    session: str = typer.Option(..., "--session"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """List what changed since the base revision, where it lands on the map, and the tests.

    Needs no agent: the changes, their place and the static test evidence come from the
    code alone. Explanations and coverage verdicts appear once the change task is done.
    """
    from .business_map.workspace import Workspace

    _map_call(lambda: Workspace(repo, session).change_summary())


@map_app.command("render")
def map_render(
    session: str = typer.Option(..., "--session"),
    repo: Path = typer.Option(Path("."), "--repo"),
    share: bool = typer.Option(False, "--share", help="Leave source excerpts out"),
    open_browser: bool = typer.Option(False, "--open", help="Open the page in a browser"),
) -> None:
    """Write graph.html and summary.md for a session. Exit 2 means a usable partial result.

    In a change session the page is the head map with each change shown on the step it
    belongs to; `change-report.json` holds the same changes as data.
    """
    from .business_map.render import render_html, render_summary
    from .business_map.session import load, load_report, publish

    try:
        stored, business_map, bundle = load(repo, session)
        report = load_report(repo, session)
        # The share page sits beside the private one and never replaces it.
        name = "graph.share.html" if share else "graph.html"
        files = {
            name: render_html(business_map, None if share else bundle, report),
            "summary.md": render_summary(business_map, report),
            "business-map.json": business_map.model_dump_json(indent=2, exclude_none=True) + "\n",
        }
        if report is not None:
            files["change-report.json"] = report.model_dump_json(indent=2, exclude_none=True) + "\n"
        latest = publish(repo, session, files)
    except (ValueError, OSError) as error:
        raise _map_failure(error) from error
    page = latest / name
    opened = False
    if open_browser and not os.environ.get("GENESIS_NO_BROWSER"):
        import webbrowser

        opened = bool(webbrowser.open(page.as_uri()))
    typer.echo(
        json.dumps(
            {
                "session_id": stored["session_id"],
                "analysis_status": business_map.analysis_status,
                **({} if report is None else {"change_status": report.analysis_status}),
                "share": share,
                "graph": str(page),
                "summary": str(latest / "summary.md"),
                **({} if report is None else {"change_report": str(latest / "change-report.json")}),
                "opened": opened,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    # A change session is judged by its report; only the affected flows have to be mapped.
    result = business_map.analysis_status if report is None else report.analysis_status
    if result != "complete":
        raise typer.Exit(2)


@agent_app.command("install")
def agent_install(
    agent: Agent = typer.Option(..., "--agent", help="codex, claude, or both"),
    scope: Scope = typer.Option(Scope.user, "--scope", help="user or project"),
    repo: Path | None = typer.Option(None, "--repo", help="Application Git root for project scope"),
    update: bool = typer.Option(False, "--update", help="Refresh an unmodified managed install"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show destinations without writing"),
) -> None:
    """Make Genesis discoverable in your coding agent; no analysis or upload."""
    from .agent_setup import install_skills

    try:
        for path, action in install_skills(agent, scope, repo, update=update, dry_run=dry_run):
            typer.echo(f"{'Would ' if dry_run else ''}{action}: {path}")
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot install Genesis skill: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo("Codex: $genesis | Claude Code: /genesis")
    typer.echo("If the skill is missing from the agent, open a new session or restart it.")
    typer.echo("No credentials or agent policies changed. Genesis calls no service or model.")


@agent_app.command("status")
def agent_status(
    agent: Agent = typer.Option(Agent.both, "--agent"),
    scope: Scope = typer.Option(Scope.user, "--scope"),
    repo: Path | None = typer.Option(None, "--repo"),
) -> None:
    """Inspect installed skill files; agent discovery still needs a session check."""
    from .agent_setup import skill_status

    try:
        for path, state in skill_status(agent, scope, repo):
            typer.echo(f"{state}: {path}")
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot inspect Genesis skill: {error}", err=True)
        raise typer.Exit(1) from error


def _connection_notice(connection) -> None:
    if connection.public_trial:
        typer.echo(
            f"使用官方公共试用：{connection.service_url}（无需 auth，额度由所有试用用户共享）。"
        )
    elif connection.service_url:
        typer.echo(f"使用已配置的 Genesis 服务：{connection.service_url}")


def _semantic_failure_message(code: str, *, public_trial: bool) -> str:
    from .public_trial import trial_failure_message

    if not public_trial:
        return "Semantic analysis unavailable; local facts, findings and estimates retained."
    return trial_failure_message(code)


@app.command()
def version() -> None:
    """Show the collaboration-base version."""
    typer.echo("genesis-ci 0.1.0")


@app.command()
def auth(service_url: str = typer.Option(..., "--service-url")) -> None:
    """Save an origin-bound API key in the user's private configuration directory."""
    from .config import save_credentials

    key = os.environ.get("GENESIS_API_KEY") or typer.prompt("Genesis API key", hide_input=True)
    try:
        save_credentials(key, service_url)
    except (OSError, ValueError) as error:
        typer.echo(
            "Cannot save credentials; check the key, service origin and storage permissions.",
            err=True,
        )
        raise typer.Exit(1) from error
    typer.echo("Saved credentials outside the repository (owner-only permissions).")


@flows_app.command("init")
def flows_init(
    repo: Path = typer.Option(Path("."), "--repo"),
    snapshot: Path | None = typer.Option(None, "--snapshot"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    offline: bool = typer.Option(False, "--offline"),
    service_url: str | None = typer.Option(None, "--service-url"),
    accept_send: bool = typer.Option(False, "--accept-send"),
    source_root: list[str] | None = typer.Option(None, "--source-root"),
) -> None:
    """Write a separate reviewable draft; never confirm flows or invent acceptance."""
    from genesis_contracts.models import FlowDefinition, FlowsDocument
    from genesis_contracts.python import PythonOptions
    from genesis_contracts.snapshot import SnapshotSpec

    from .client import SemanticClient, SemanticFailure
    from .config import load_settings, resolve_service_connection
    from .context import ContextOptions, preview_request
    from .flow_draft import prepare_draft, save_draft, static_drafts
    from .git_snapshot import capture_snapshot
    from .pipeline import analyze_snapshot
    from .snapshot_store import load_snapshot
    from .workflow import ci_offline_reason

    try:
        settings = load_settings(repo)
        captured = (
            load_snapshot(snapshot)
            if snapshot
            else capture_snapshot(
                repo, SnapshotSpec(base="HEAD", exclude_paths=tuple(settings.exclude))
            )
        )
        options = PythonOptions(source_roots=tuple(source_root)) if source_root else PythonOptions()
        result = analyze_snapshot(captured, options)
        request, selected = prepare_draft(
            result,
            options=ContextOptions(
                input_token_budget=settings.input_token_budget,
                max_excerpt_chars=settings.max_excerpt_chars,
                max_excerpts=settings.max_excerpts,
                exclude_paths=tuple(settings.exclude),
            ),
        )
        typer.echo(preview_request(selected))
        document = static_drafts(request)
        reason = ci_offline_reason()
        mode = "offline"
        if not offline and not reason:
            try:
                connection = resolve_service_connection(service_url)
                url, key = connection.service_url, connection.api_key
                _connection_notice(connection)
                reason = "No semantic service/key configured; static candidates only."
            except (OSError, ValueError):
                url = key = None
                reason = "Invalid credential/service configuration; retained static entry drafts."
            if url and key:
                approved = accept_send
                if not approved:
                    try:
                        approved = typer.confirm(
                            f"Send selected entries to {url} for drafting?", default=False
                        )
                    except (EOFError, typer.Abort):
                        approved = False
                if approved:
                    try:
                        response = SemanticClient(url, key).draft(request)
                        document = FlowsDocument(
                            flows=tuple(
                                FlowDefinition(
                                    id=flow.id,
                                    name=flow.name,
                                    status="draft",
                                    entries=flow.entries,
                                    notes=flow.description,
                                )
                                for flow in response.flows
                            )
                        )
                        mode, reason = (
                            "semantic",
                            "Review drafts before confirming. Acceptance remains empty.",
                        )
                    except SemanticFailure as error:
                        reason = f"{error.code}: retained static entry drafts."
                        if connection.public_trial:
                            reason += " " + _semantic_failure_message(error.code, public_trial=True)
                else:
                    reason = "Send not confirmed; retained static entry drafts."
        output = output or repo / ".genesis" / "flows.draft.yaml"
        save_draft(
            document, output, request, mode=mode, reason=reason or "Offline static entry drafts."
        )
    except (OSError, ValueError) as error:
        typer.echo(
            "invalid_flow_draft: Check frozen inputs, context limits and the new output path.",
            err=True,
        )
        raise typer.Exit(1) from error
    typer.echo(f"Wrote {output} ({mode}); {reason or 'Static candidates only.'}")
    if mode != "semantic":
        raise typer.Exit(2)


@app.command()
def demo(
    fixture: str,
    output: Path = typer.Option(Path(".genesis/analyses/demo"), "--output", "-o"),
    service_url: str = typer.Option("http://127.0.0.1:8765", "--service-url"),
    api_key: str = typer.Option("ci-demo-local-only", "--api-key", envvar="GENESIS_API_KEY"),
    fixtures_dir: Path = typer.Option(
        Path(
            os.environ.get("GENESIS_FIXTURES_DIR", Path(__file__).resolve().parents[4] / "fixtures")
        ),
        "--fixtures-dir",
    ),
    offline: bool = typer.Option(False, "--offline"),
) -> None:
    """Run synthetic fixtures; 0=complete, 2=partial, 1=invalid local input."""
    if fixture not in FIXTURE_NAMES:
        raise typer.BadParameter("unknown registered fixture")
    url = urlsplit(service_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise typer.BadParameter(
            "demo requires a loopback HTTP service URL without credentials or a path"
        )
    root = fixtures_dir / fixture
    path = root / "semantic.json"
    try:
        if any(item.is_symlink() for item in (path, *path.absolute().parents)):
            raise ValueError("fixture inputs cannot use symlinks")
        data = json.loads(path.read_text(encoding="utf-8"))
        request = AnalysisRequest.model_validate(data["request"])
        local = LocalAnalysis.model_validate(data["local_analysis"])
        reader = FrozenSnapshotReader.from_directory(root, local.snapshot, local.evidence)
        if request.excerpts != reader.read_selected(
            tuple(item.evidence_id for item in request.excerpts)
        ):
            raise ValueError("request excerpts differ from frozen files")
        validate_request_against_local(local, request)
    except (OSError, ValueError, KeyError) as error:
        typer.echo(f"Invalid local fixture: {error}", err=True)
        raise typer.Exit(code=1) from error
    semantic = None
    failure = None
    if not offline:
        try:
            with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    service_url.rstrip("/") + "/v1/analyze",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request.model_dump(mode="json"),
                )
            response.raise_for_status()
            semantic = SemanticAnalysisResponse.model_validate(response.json())
            # Validate before choosing the remote result; invalid output becomes a partial report.
            assemble_report(local, request, semantic)
        except (httpx.HTTPError, ValueError) as error:
            code = "provider_output_invalid"
            if isinstance(error, httpx.TimeoutException):
                code = "analysis_timeout"
            elif isinstance(error, httpx.HTTPStatusError):
                code = {
                    401: "invalid_api_key",
                    402: "quota_exceeded",
                    413: "request_too_large",
                    422: "invalid_request",
                    503: "service_unavailable",
                }.get(error.response.status_code, "service_unavailable")
                try:
                    envelope = ServiceError.model_validate(error.response.json()["error"])
                    if envelope.request_id in {request.request_id, "unknown"}:
                        code = envelope.code.value
                except (KeyError, TypeError, ValueError):
                    pass
            elif isinstance(error, httpx.HTTPError):
                code = "service_unavailable"
            failure = Limitation(
                code=code,
                message="Semantic service did not return a usable result; local findings and estimates are retained.",
                affects_completeness=True,
            )
            semantic = None
    report = assemble_report(local, request, semantic, failure=failure)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(render_markdown(report), encoding="utf-8")
    typer.echo(
        f"Wrote {output / 'report.md'} and {output / 'report.json'} ({report.analysis_status.value})"
    )
    if report.analysis_status != "complete":
        raise typer.Exit(code=2)


@app.command("snapshot")
def snapshot_command(
    repo: Path = typer.Option(Path("."), "--repo"),
    base: str = typer.Option(..., "--base"),
    head: str | None = typer.Option(None, "--head"),
    worktree: bool = typer.Option(False, "--worktree"),
    include_untracked: bool = typer.Option(False, "--include-untracked"),
    intent: list[str] | None = typer.Option(None, "--intent"),
    exclude: list[str] | None = typer.Option(None, "--exclude"),
    output: Path = typer.Option(..., "--output", "-o"),
) -> None:
    """Capture real frozen inputs locally; no parsing, network, or semantic analysis."""
    from genesis_contracts.snapshot import SnapshotInput, SnapshotSpec

    from .git_snapshot import SnapshotError, capture_snapshot
    from .snapshot_store import save_snapshot

    if worktree == (head is not None):
        raise typer.BadParameter("select exactly one of --head REV or --worktree")
    if include_untracked and not worktree:
        raise typer.BadParameter("--include-untracked requires --worktree")
    try:
        spec = SnapshotSpec(
            base=base,
            head=head,
            include_untracked=include_untracked,
            inputs=tuple(SnapshotInput(path=path, kind="intent") for path in intent or ()),
            exclude_paths=tuple(exclude or ()),
        )
        result = capture_snapshot(repo, spec)
        save_snapshot(result, output)
    except (SnapshotError, ValueError, OSError) as error:
        code = error.code if isinstance(error, SnapshotError) else "invalid_snapshot_input"
        typer.echo(f"{code}: {error}", err=True)
        raise typer.Exit(1) from error
    manifest = result.capture.manifest
    typer.echo(
        f"Saved {output / 'snapshot.json'}: {len(manifest.files)} side/file entries; "
        f"{len(result.capture.file_diff.changes)} file changes; "
        f"capture={manifest.integrity_status}; symbols=not_analyzed"
    )
    if manifest.integrity_status != "complete":
        raise typer.Exit(2)


@app.command("analyze")
def analyze_command(
    snapshot: Path | None = typer.Option(None, "--snapshot", help="Previously frozen A1 input"),
    output: Path | None = typer.Option(None, "--output", "-o", help="New private output directory"),
    repo: Path = typer.Option(Path("."), "--repo"),
    base: str | None = typer.Option(None, "--base"),
    head: str | None = typer.Option(None, "--head"),
    include_untracked: bool = typer.Option(False, "--include-untracked"),
    offline: bool = typer.Option(False, "--offline"),
    service_url: str | None = typer.Option(None, "--service-url"),
    accept_send: bool = typer.Option(
        False, "--accept-send", help="Approve the displayed bounded payload"
    ),
    preview_only: bool = typer.Option(
        False, "--preview-only", help="Save outbound payload without sending"
    ),
    task: list[str] | None = typer.Option(None, "--task"),
    requirements: list[str] | None = typer.Option(None, "--requirements"),
    review_request: Path | None = typer.Option(
        None,
        "--review-request",
        help="Bounded JSON reviewer goals/reference/schema; not business intent",
    ),
    plan: list[str] | None = typer.Option(None, "--plan"),
    pr_description: list[str] | None = typer.Option(None, "--pr-description"),
    intent_metadata: str | None = typer.Option(
        None,
        "--intent-metadata",
        help="Repository-relative frozen CI collection notices; not user requirements",
    ),
    exclude: list[str] | None = typer.Option(None, "--exclude"),
    input_token_budget: int | None = typer.Option(None, "--input-token-budget", min=100, max=40000),
    source_root: list[str] | None = typer.Option(None, "--source-root"),
    cost_inputs: Path | None = typer.Option(None, "--cost-inputs"),
    include_source_evidence: bool = typer.Option(
        False,
        "--include-source-evidence",
        help="Write a separate private review with frozen source excerpts",
    ),
) -> None:
    """Review Python changes; task/PR files and flow maps are optional. Sending requires consent."""
    import uuid
    from dataclasses import replace

    from genesis_contracts.cost import CostInputs
    from genesis_contracts.python import PythonOptions
    from genesis_contracts.snapshot import SnapshotInput, SnapshotSpec

    from .client import SemanticClient, SemanticFailure
    from .config import load_settings, resolve_service_connection
    from .git_snapshot import SnapshotError, capture_snapshot
    from .pipeline import analyze_snapshot
    from .snapshot_store import load_snapshot
    from .workflow import (
        ci_offline_reason,
        default_base,
        failure,
        new_output,
        publish_analysis,
        with_semantic,
    )

    try:
        if snapshot and (base or head or include_untracked):
            raise ValueError("--snapshot cannot be combined with capture options")
        from .review_request import load_review_request

        review_directives = load_review_request(review_request) if review_request else None
        repo = repo.absolute()
        settings = load_settings(repo)
        exclusions = tuple(dict.fromkeys((*settings.exclude, *(exclude or ()))))
        paths = [
            (path, kind)
            for kind, values in (
                ("task", task),
                ("requirements", requirements),
                ("agent_plan", plan),
                ("pr_description", pr_description),
            )
            for path in values or ()
        ]
        if len({path for path, _ in paths}) != len(paths):
            raise ValueError("Each intent path must have exactly one source type")
        captured = (
            load_snapshot(snapshot)
            if snapshot
            else capture_snapshot(
                repo,
                SnapshotSpec(
                    base=base or default_base(repo),
                    head=head,
                    include_untracked=include_untracked,
                    inputs=tuple(
                        SnapshotInput(path=path, kind="intent")
                        for path in dict.fromkeys(
                            [path for path, _ in paths]
                            + ([intent_metadata] if intent_metadata else [])
                        )
                    ),
                    exclude_paths=exclusions,
                ),
            )
        )
        inputs = None
        if cost_inputs:
            if cost_inputs.stat().st_size > 262144:
                raise ValueError("Cost inputs exceed 256 KiB")
            inputs = CostInputs.model_validate_json(cost_inputs.read_bytes())
        options = PythonOptions(source_roots=tuple(source_root)) if source_root else PythonOptions()
        result = analyze_snapshot(captured, options, inputs)
        reader = result.reader
        if paths:
            from .intent import IntentSource, collect_intents

            collected = collect_intents(
                result.local,
                reader,
                captured.source,
                tuple(IntentSource(path=path, source_type=kind) for path, kind in paths),
                exclude_paths=exclusions,
            )
            result, reader = replace(result, local=collected.local), collected.reader
            result = with_semantic(result, None, None)
        if intent_metadata:
            from .ci_intent import apply_ci_intent_metadata

            result = replace(
                result,
                local=apply_ci_intent_metadata(result.local, captured.source, intent_metadata),
            )
            result = with_semantic(result, None, None)
        output = output or new_output(repo)
        # Fork decisions precede credentials and any HTTP transport construction.
        forced = ci_offline_reason()
        request = preview = semantic = None
        selection_log = []
        if forced:
            result = with_semantic(result, None, None, failure("fork_pr_offline", forced))
        elif not offline:
            from .context import ContextOptions, build_context, preview_request

            connection_failed = False
            try:
                connection = resolve_service_connection(service_url)
                url, key = connection.service_url, connection.api_key
                _connection_notice(connection)
            except (OSError, ValueError):
                connection_failed = True
                url = key = None
                result = with_semantic(
                    result,
                    None,
                    None,
                    failure(
                        "invalid_api_key",
                        "Cannot load credential/service configuration; local analysis retained. Run genesis auth again.",
                    ),
                )
            if url or preview_only:
                try:
                    request = build_context(
                        result.local,
                        reader,
                        request_id=uuid.uuid4().hex,
                        review_directives=review_directives,
                        selection_log=selection_log,
                        options=ContextOptions(
                            input_token_budget=input_token_budget or settings.input_token_budget,
                            max_excerpt_chars=settings.max_excerpt_chars,
                            max_excerpts=settings.max_excerpts,
                            exclude_paths=exclusions,
                            behavior_review_version="2",
                        ),
                    )
                    preview = preview_request(request)
                    typer.echo(preview)
                    if preview_only:
                        result = with_semantic(
                            result,
                            request,
                            None,
                            failure("preview_only", "Payload prepared locally; nothing sent."),
                        )
                    elif not key:
                        result = with_semantic(
                            result,
                            request,
                            None,
                            failure(
                                "invalid_api_key",
                                "Configure genesis auth or GENESIS_API_KEY before sending.",
                            ),
                        )
                    else:
                        approved = accept_send
                        if not approved:
                            try:
                                approved = typer.confirm(
                                    f"Send this context to {url}?", default=False
                                )
                            except (EOFError, typer.Abort):
                                approved = False
                        if approved:
                            try:
                                client = SemanticClient(url, key)
                                capabilities = client.capabilities()
                                # Negotiation can only remove optional material
                                # from the locally approved preview, never add it.
                                updates = {}
                                negotiated = client.negotiate_review_version(
                                    request.behavior_review_version, capabilities
                                )
                                if negotiated != request.behavior_review_version:
                                    updates["behavior_review_version"] = negotiated
                                if (
                                    request.behavior_view is not None
                                    and request.behavior_view.version
                                    not in capabilities.get("behavior_view_versions", ())
                                ):
                                    updates["behavior_view"] = None
                                if updates:
                                    request = request.model_copy(update=updates)
                                    preview = preview_request(request)
                                    typer.echo("服务能力协商后，使用以下兼容请求：")
                                    typer.echo(preview)
                                semantic = client.analyze(request)
                                result = with_semantic(result, request, semantic)
                            except SemanticFailure as error:
                                if connection.public_trial:
                                    typer.echo(
                                        _semantic_failure_message(error.code, public_trial=True)
                                    )
                                result = with_semantic(
                                    result,
                                    request,
                                    None,
                                    failure(
                                        error.code,
                                        _semantic_failure_message(
                                            error.code, public_trial=connection.public_trial
                                        ),
                                    ),
                                )
                        else:
                            result = with_semantic(
                                result,
                                request,
                                None,
                                failure(
                                    "send_not_confirmed",
                                    "Outbound context was not approved; nothing sent.",
                                ),
                            )
                except ValueError:
                    request = None
                    result = with_semantic(
                        result,
                        None,
                        None,
                        failure(
                            "context_unavailable",
                            "Cannot build a valid bounded payload; nothing sent.",
                        ),
                    )
            elif not connection_failed:
                result = with_semantic(
                    result,
                    None,
                    None,
                    failure(
                        "service_unavailable",
                        "No semantic service or API key configured; run genesis auth --service-url ORIGIN. Local analysis retained.",
                    ),
                )
        publish_analysis(
            result,
            output,
            captured=captured if not snapshot else None,
            request=request,
            preview=preview,
            semantic=semantic,
            reader=reader,
            include_source_evidence=include_source_evidence,
            selection_log=selection_log,
        )
    except (SnapshotError, ValueError, OSError) as error:
        typer.echo(
            "invalid_analysis_input: Check configuration, frozen inputs and the new output path.",
            err=True,
        )
        raise typer.Exit(1) from error
    typer.echo(
        f"Wrote {output / 'report.md'} and report.json ({result.report.analysis_status.value})"
    )
    typer.echo(f"先看中文简报：{output / 'summary.md'}")
    if result.report.analysis_status != "complete":
        raise typer.Exit(2)

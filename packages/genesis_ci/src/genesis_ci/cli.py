import json
import os
from pathlib import Path

import typer

from . import __version__
from .agent_setup import Agent, Scope

app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
app.add_typer(agent_app, name="agent")
map_app = typer.Typer(no_args_is_help=True, help="Local business map; no service, no model.")
app.add_typer(map_app, name="map")


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
    from .business_map.session import load, load_report, publish, session_root
    from .business_map.source_links import github_source_links
    from .business_map.view import render_view
    from .snapshot_store import load_snapshot

    try:
        stored, business_map, bundle = load(repo, session)
        report = load_report(repo, session)
        snapshot = load_snapshot(session_root(repo, session) / "snapshot")
        source_links = github_source_links(
            repo,
            snapshot.capture,
            (*business_map.evidence, *(report.evidence if report else ())),
        )
        # The share page sits beside the private one and never replaces it.
        name = "graph.share.html" if share else "graph.html"
        # The interactive viewer is written beside the outline; --open shows the viewer.
        view_name = "view.share.html" if share else "view.html"
        files = {
            name: render_html(business_map, None if share else bundle, report),
            view_name: render_view(
                business_map, None if share else bundle, report, source_links=source_links
            ),
            "summary.md": render_summary(business_map, report),
            "business-map.json": business_map.model_dump_json(indent=2, exclude_none=True) + "\n",
        }
        if report is not None:
            files["change-report.json"] = report.model_dump_json(indent=2, exclude_none=True) + "\n"
        latest = publish(repo, session, files)
    except (ValueError, OSError) as error:
        raise _map_failure(error) from error
    page = latest / name
    view = latest / view_name
    opened = False
    if open_browser and not os.environ.get("GENESIS_NO_BROWSER"):
        import webbrowser

        opened = bool(webbrowser.open(view.as_uri()))
    typer.echo(
        json.dumps(
            {
                "session_id": stored["session_id"],
                "analysis_status": business_map.analysis_status,
                **({} if report is None else {"change_status": report.analysis_status}),
                "share": share,
                "graph": str(page),
                "view": str(view),
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


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(f"genesis-ci {__version__}")

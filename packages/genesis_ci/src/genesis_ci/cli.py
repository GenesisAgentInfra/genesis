import errno
import json
import os
import sys
from enum import StrEnum
from pathlib import Path

import typer

from . import __version__
from .agent_setup import Agent, Scope

app = typer.Typer(
    no_args_is_help=True,
    help="Genesis: a business flow map of a codebase and a review of a change. Your coding "
    "agent normally runs these commands through the installed skill; see docs/usage.md.",
)
agent_app = typer.Typer(
    no_args_is_help=True, help="Install the Genesis skill for a coding agent, or check it."
)
app.add_typer(agent_app, name="agent")
map_app = typer.Typer(
    no_args_is_help=True,
    help="Map business flows and review a change (prepare --base REV, then diff). "
    "Local; no service, no model.",
)
app.add_typer(map_app, name="map")


def _map_failure(error: Exception) -> typer.Exit:
    """Report a refusal as JSON on stdout, like every other result of `genesis map`."""
    from pydantic import ValidationError

    from .business_map.loop import LoopError, pydantic_problems

    if isinstance(error, LoopError):
        body = {"code": error.code, "message": str(error), "errors": error.errors}
    elif isinstance(error, ValidationError):
        body = {
            "code": "invalid_input",
            "message": "The input does not match the expected structure.",
            "errors": pydantic_problems(error),
        }
    elif getattr(error, "code", None) is None and (
        isinstance(error, PermissionError)
        or getattr(error, "errno", None) in (errno.EACCES, errno.EPERM, errno.EROFS)
    ):
        body = {
            "code": "cannot_write",
            "message": f"Genesis cannot write here: {error}. "
            "It needs write access to .genesis/ in the project.",
            "errors": [],
        }
    else:
        code = getattr(error, "code", None) or (
            "not_found" if isinstance(error, FileNotFoundError) else "invalid_map_input"
        )
        body = {"code": code, "message": str(error), "errors": []}
    typer.echo(json.dumps({"error": body}, ensure_ascii=False, indent=2))
    return typer.Exit(1)


REPO_HELP = "Git root of the project"
SESSION_HELP = "Session id printed by `map prepare`"
TASK_HELP = "Task id from `map status`"
UNTRACKED_HELP = "Also read new files Git does not track yet"


class Engine(StrEnum):
    """Who reads the code. `auto` uses the Python analyzers when they find Python source."""

    auto = "auto"
    python = "python"
    agent = "agent"


def _workspace(repo: Path, session: str):
    """The loop of a session, by the engine that prepared it."""
    from .business_map.store import session_root

    stored = session_root(repo.expanduser().resolve(strict=True), session) / "session.json"
    if not stored.is_file():
        raise FileNotFoundError(f"no such session: {session}")
    if json.loads(stored.read_text(encoding="utf-8")).get("engine") == "agent":
        from .agent_map import Workspace
    else:
        from .business_map.workspace import Workspace
    return Workspace(repo, session)


@map_app.command("size")
def map_size(
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    base: str | None = typer.Option(None, "--base", help="Count for a review from this revision"),
    head: str | None = typer.Option(None, "--head", help="Default: the working tree"),
    include_untracked: bool = typer.Option(False, "--include-untracked", help=UNTRACKED_HELP),
    max_files: int | None = typer.Option(
        None, "--max-files", min=1, help="The limit `prepare` will use (default 50000)"
    ),
) -> None:
    """Count the source files `prepare` would read and estimate how long it takes.

    Reads file names only and returns in seconds. Run it before `prepare` on a project
    you have not prepared, and tell the user when it says `tell_user`.
    """
    from .size import estimate

    try:
        result = estimate(
            repo, base=base, head=head, include_untracked=include_untracked, max_files=max_files
        )
    except (ValueError, OSError) as error:
        raise _map_failure(error) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@map_app.command("prepare")
def map_prepare(
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    base: str | None = typer.Option(None, "--base", help="Compare against this revision"),
    head: str | None = typer.Option(None, "--head", help="Default: the working tree"),
    include_untracked: bool = typer.Option(False, "--include-untracked", help=UNTRACKED_HELP),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        help="Leave out a file or folder, by its path from the repository root. "
        "Repeatable. No wildcards",
    ),
    engine: Engine = typer.Option(
        Engine.auto,
        "--engine",
        help="auto: Python analysis when there is Python source, otherwise agent. "
        "python: Python analysis only. agent: the coding agent reads the code, for a "
        "project whose main language is not Python",
    ),
    max_files: int | None = typer.Option(
        None,
        "--max-files",
        min=1,
        help="Read up to this many source files (default 50000); `map size` counts them",
    ),
) -> None:
    """Freeze a snapshot and open a session. Calls no model.

    Python source is analyzed into facts and a static skeleton. A repository without it,
    or `--engine agent`, gets a session in which the coding agent reads the code itself.

    A repository with many Python files is analyzed in several worker processes. Set
    GENESIS_WORKERS to choose how many; 1 keeps everything in one process.
    """
    options = {
        "base": base,
        "head": head,
        "include_untracked": include_untracked,
        "exclude": tuple(exclude or ()),
        "max_files": max_files,
    }
    try:
        result = None
        if engine != Engine.agent:
            from .business_map.session import UnsupportedRepository, prepare

            try:
                result = prepare(repo, **options)
            except UnsupportedRepository:
                if engine == Engine.python:
                    raise
        if result is None:
            from .agent_map import prepare

            result = prepare(repo, **options)
    except (ValueError, OSError) as error:
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
    """The JSON of a plan or submission: from a file, or from standard input for `-`."""
    if str(path) == "-":
        return json.loads(sys.stdin.read())
    return json.loads(path.read_text(encoding="utf-8"))


@map_app.command("plan")
def map_plan(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    plan_file: Path | None = typer.Option(
        None,
        "--input",
        help="Omit for the default plan (Python sessions only); - reads standard input",
    ),
) -> None:
    """Group entries into flows and create one task per flow."""

    def action():
        workspace = _workspace(repo, session)
        plan = None if plan_file is None else workspace.Plan.model_validate(_map_input(plan_file))
        return workspace.save_plan(plan)

    _map_call(action)


@map_app.command("status")
def map_status(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
) -> None:
    """List tasks, their state and what is still missing."""
    _map_call(lambda: _workspace(repo, session).status())


@map_app.command("context")
def map_context(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    task: str = typer.Option(..., "--task", help=TASK_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    claim: bool = typer.Option(False, "--claim", help="Hold the task for this worker"),
) -> None:
    """Everything needed to start one task: entries, source and, in a Python session, the
    facts to account for."""
    _map_call(lambda: _workspace(repo, session).context(task, claim))


@map_app.command("query")
def map_query(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    symbol: str | None = typer.Option(
        None, "--symbol", help="Symbol id such as path/file.py#function"
    ),
    search: str | None = typer.Option(None, "--search", help="Text to find in the frozen source"),
) -> None:
    """Look at one symbol and its neighbours (Python sessions only), or search the frozen
    source. Give exactly one of --symbol or --search."""

    def action():
        if (symbol is None) == (search is None):
            from .business_map.loop import LoopError

            raise LoopError("invalid_option", "Give exactly one of --symbol or --search.")
        workspace = _workspace(repo, session)
        return workspace.query_symbol(symbol) if symbol else workspace.search(search)

    _map_call(action)


@map_app.command("read")
def map_read(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    evidence: str = typer.Option(
        ..., "--evidence", help="Evidence id from `context`, `query` or `diff`"
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
) -> None:
    """Read the frozen source behind one evidence reference."""
    _map_call(lambda: _workspace(repo, session).read(evidence))


@map_app.command("submit")
def map_submit(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    task: str = typer.Option(..., "--task", help=TASK_HELP),
    submission: Path = typer.Option(..., "--input", help="A JSON file; - reads standard input"),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
) -> None:
    """Check one submission for a task. It is accepted or rejected as a whole."""
    _map_call(lambda: _workspace(repo, session).submit(task, _map_input(submission)))


@map_app.command("diff")
def map_diff(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
) -> None:
    """List what changed since the base revision, where it lands on the map, and the tests.

    In a Python session the changes, their place and the linked tests come from the code
    alone. In other sessions the changed lines are listed at once and get a place when a
    described flow cites them. Explanations and coverage verdicts appear once the change
    task is done.
    """
    _map_call(lambda: _workspace(repo, session).change_summary())


@map_app.command("render")
def map_render(
    session: str = typer.Option(..., "--session", help=SESSION_HELP),
    repo: Path = typer.Option(Path("."), "--repo", help=REPO_HELP),
    share: bool = typer.Option(
        False,
        "--share",
        help="Write view.share.html and graph.share.html, without source excerpts, in place "
        "of view.html and graph.html; pages from an earlier render stay. A review still "
        "shows the changed lines",
    ),
    open_browser: bool = typer.Option(False, "--open", help="Open the viewer page in a browser"),
) -> None:
    """Write view.html and graph.html (view.share.html and graph.share.html with --share),
    summary.md and business-map.json to .genesis/out/latest/ (and .genesis/out/SESSION/),
    plus change-report.json in a change session.

    Exit 2 means a usable partial result. In a change session both pages are the head
    map with each change shown on the step it belongs to; `change-report.json` holds
    the same changes as data.
    """
    from .business_map.render import render_html, render_summary
    from .business_map.source_links import github_source_links
    from .business_map.store import load, load_report, publish, session_root
    from .business_map.view import render_view
    from .snapshot_store import load_snapshot

    try:
        stored, business_map, bundle = load(repo, session)
        report = load_report(repo, session)
        missing = stored.get("files_over_size_limit")
        if missing:
            # Part of the project was never read: the result says so and is partial.
            from genesis_contracts.business_map import BusinessMap
            from genesis_contracts.change_report import ChangeReport

            from .size import limitation

            note = limitation(missing)
            business_map = BusinessMap.model_validate(
                {
                    **business_map.model_dump(mode="json", exclude_none=True),
                    "analysis_status": "partial",
                    "limitations": [
                        *(item.model_dump(mode="json") for item in business_map.limitations),
                        note,
                    ],
                }
            )
            if report is not None:
                report = ChangeReport.model_validate(
                    {
                        **report.model_dump(mode="json", exclude_none=True),
                        "analysis_status": "partial",
                        "limitations": [
                            *(item.model_dump(mode="json") for item in report.limitations),
                            note,
                        ],
                    }
                )
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


def _install_line(action: str, dry_run: bool) -> str:
    """How one planned action of `agent install` reads to a person."""
    if action == "unchanged":
        return "Already current"
    if action.startswith("kept"):
        return ("Would keep" if dry_run else "Kept") + " (edited or not ours)"
    if action.startswith("remove"):
        return ("Would remove" if dry_run else "Removed") + action[len("remove") :]
    past = {"install": "Installed", "update": "Updated"}
    return f"Would {action}" if dry_run else past.get(action, action)


@agent_app.command("install")
def agent_install(
    agent: Agent = typer.Option(
        ...,
        "--agent",
        help="claude: ~/.claude/skills. codex: ~/.agents/skills, which other agents "
        "read too. both: both directories.",
    ),
    scope: Scope = typer.Option(Scope.user, "--scope", help="user or project"),
    repo: Path | None = typer.Option(None, "--repo", help="Application Git root for project scope"),
    update: bool = typer.Option(False, "--update", help="Refresh an unmodified managed install"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show destinations without writing"),
) -> None:
    """Make Genesis discoverable in your coding agent; no analysis or upload."""
    from .agent_setup import install_skills

    try:
        for path, action in install_skills(agent, scope, repo, update=update, dry_run=dry_run):
            typer.echo(f"{_install_line(action, dry_run)}: {path}")
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot install Genesis skill: {error}", err=True)
        raise typer.Exit(1) from error
    if dry_run:
        typer.echo("Dry run: nothing was written.")
        return
    # Name only the agents this install reaches.
    typer.echo(
        {
            Agent.codex: "Codex: $genesis",
            Agent.claude: "Claude Code: /genesis",
            Agent.both: "Codex: $genesis | Claude Code: /genesis",
        }[agent]
    )
    typer.echo("If the skill is missing from the agent, open a new session or restart it.")
    typer.echo("No credentials or agent policies changed. Genesis calls no service or model.")


@agent_app.command("status")
def agent_status(
    agent: Agent = typer.Option(Agent.both, "--agent", help="codex, claude or both"),
    scope: Scope = typer.Option(Scope.user, "--scope", help="user or project"),
    repo: Path | None = typer.Option(None, "--repo", help="Application Git root for project scope"),
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
    """Show the installed version, and the commit it was built from when known."""
    commit = _installed_commit()
    typer.echo(f"genesis-ci {__version__}" + (f" (commit {commit})" if commit else ""))


def _installed_commit() -> str | None:
    """The short Git commit recorded when this package was installed from a repository."""
    from importlib import metadata

    try:
        raw = metadata.distribution("genesis-ci").read_text("direct_url.json")
        commit = json.loads(raw or "{}").get("vcs_info", {}).get("commit_id")
    except (metadata.PackageNotFoundError, ValueError, AttributeError, OSError):
        return None
    return commit[:7] if isinstance(commit, str) and commit else None

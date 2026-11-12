"""Entry detection: framework decorators, the __main__ guard, and the uncalled-root heuristic."""

from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

API = """from fastapi import APIRouter

from service import approve

router = APIRouter()


@router.post("/reports", status_code=201)
async def submit(report):
    return approve(report)


@router.api_route("/reports/{report_id}", methods=["GET", "HEAD"])
def read(report_id):
    return report_id


@router.websocket("/stream")
async def stream(socket):
    return socket


@router.cache("/not-a-route")
def cached():
    return 1
"""
JOBS = """import typer
from celery import shared_task
from langchain_core.tools import tool

cli = typer.Typer()


@cli.command("sync")
def sync():
    return nightly()


@shared_task(name="reports.nightly")
def nightly():
    return 1


@tool
def lookup(report_id):
    return report_id


def helper():
    return 2


def _private():
    return 3


def main():
    cli()


if __name__ == "__main__":
    main()
"""
SERVICE = """class Approver:
    def decide(self, report):
        return self._score(report)

    def _score(self, report):
        return 1


def approve(report):
    return report


def unused(report):
    return approve(report)
"""
PLAIN = """def post(path):
    def wrap(fn):
        return fn
    return wrap


class router:
    post = staticmethod(post)


@router.post("/looks-like-a-route")
def lookalike():
    return 1
"""


def entries(root, files):
    for path, text in files.items():
        write(root, path, text)
    commit(root)
    facts = python_facts(extract_python(capture_snapshot(root, SnapshotSpec(head="HEAD"))))
    return {entry.symbol_id: entry for entry in facts.entries}, facts


def test_framework_decorators_become_adapter_entries(source_repo):
    found, _ = entries(source_repo, {"api.py": API, "jobs.py": JOBS, "service.py": SERVICE})
    submit = found["api.py#submit"]
    assert (submit.kind, submit.detection, submit.framework) == ("http_route", "adapter", "fastapi")
    assert submit.attributes == {"method": "POST", "path": "/reports"}
    assert found["api.py#read"].attributes == {"method": "GET,HEAD", "path": "/reports/{report_id}"}
    assert found["api.py#stream"].attributes["method"] == "WEBSOCKET"
    assert found["jobs.py#sync"].kind == "cli_command"
    assert found["jobs.py#sync"].attributes == {"command": "sync"}
    nightly = found["jobs.py#nightly"]
    assert (nightly.kind, nightly.framework) == ("task", "celery")
    assert nightly.attributes == {"task": "reports.nightly"}
    assert (found["jobs.py#lookup"].kind, found["jobs.py#lookup"].framework) == (
        "agent_tool",
        "langchain_core",
    )
    # An unrecognised method name on the router is not a route.
    assert found["api.py#cached"].detection == "root_heuristic"


def test_main_guard_marks_the_functions_it_calls(source_repo):
    found, _ = entries(source_repo, {"jobs.py": JOBS})
    main = found["jobs.py#main"]
    assert (main.kind, main.detection, main.attributes) == (
        "main",
        "adapter",
        {"guard": "__main__"},
    )
    # A decorated command keeps its framework kind even when something else calls it.
    assert found["jobs.py#nightly"].kind == "task"


def test_root_heuristic_lists_only_public_uncalled_functions(source_repo):
    found, _ = entries(source_repo, {"api.py": API, "jobs.py": JOBS, "service.py": SERVICE})
    roots = {key for key, entry in found.items() if entry.detection == "root_heuristic"}
    assert "service.py#unused" in roots
    assert "service.py#Approver.decide" in roots
    assert "jobs.py#helper" in roots
    # Called by something, private, or already an adapter entry.
    assert "service.py#approve" not in roots
    assert "service.py#Approver._score" not in found
    assert "jobs.py#_private" not in found
    assert all(entry.kind == "root" for key, entry in found.items() if key in roots)


def test_decorator_shape_without_the_framework_import_is_not_an_entry(source_repo):
    found, _ = entries(source_repo, {"plain.py": PLAIN})
    assert found["plain.py#lookalike"].detection == "root_heuristic"
    assert not [entry for entry in found.values() if entry.detection == "adapter"]


def test_tests_are_never_root_candidates_and_entries_cite_evidence(source_repo):
    found, facts = entries(
        source_repo,
        {
            "service.py": SERVICE,
            "tests/test_service.py": "def test_approve():\n    assert True\n",
            "test_top.py": "def test_top():\n    assert True\n",
        },
    )
    assert not [key for key in found if "test_" in key.split("#")[0]]
    cited = {ref.evidence_id for ref in facts.evidence}
    assert found and all(set(entry.evidence_ids) <= cited for entry in found.values())
    assert len({entry.entry_id for entry in found.values()}) == len(found)


def test_entries_written_in_test_code_are_not_business_entries(source_repo):
    route = (
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n"
        '@router.get("/ping")\ndef ping():\n    return {"ok": True}\n\n\n'
        'if __name__ == "__main__":\n    ping()\n'
    )
    found, _ = entries(
        source_repo,
        {"app/api.py": route, "tests/test_client.py": route, "app/test_helpers.py": route},
    )
    adapter = sorted(
        (symbol, item.kind.value) for symbol, item in found.items() if item.detection == "adapter"
    )
    assert [symbol.partition("#")[0] for symbol, _ in adapter] == ["app/api.py"] * len(adapter)
    assert ("app/api.py#ping", "http_route") in adapter
    assert not any(symbol.startswith(("tests/", "app/test_")) for symbol in found)

"""A review starts from the entries the agent proposed in the project's last map, or in
the map `--entries-from` names."""

import json
import os
import shutil
from pathlib import Path

import pytest
from genesis_ci.business_map.session import prepare
from genesis_ci.business_map.skeleton import flow_id_for
from genesis_ci.business_map.workspace import CARRIED, LoopError, Workspace
from genesis_ci.cli import app
from genesis_contracts.map_tasks import MapPlan
from test_change_analysis import git
from test_git_snapshot import commit, write
from test_map_loop import entry
from typer.testing import CliRunner

FIXTURE_MAP = Path(__file__).resolve().parents[1] / "fixtures/business-map/expense-skeleton.json"
SPEC = "spec/business-map.json"

AGENT = "desk/agent.py"
REFUND = f"{AGENT}#Agent._refund"
STATUS = f"{AGENT}#Agent._status"
BEFORE = {
    "desk/__init__.py": "",
    "desk/__main__.py": """import sys

from desk.agent import Agent


def main(argv=None):
    print(Agent().handle(*(argv or sys.argv[1:])))


if __name__ == "__main__":
    main()
""",
    AGENT: """class Agent:
    def handle(self, intent, order):
        if intent == "refund":
            return self._refund(order)
        return self._status(order)

    def _refund(self, order):
        if order["amount"] <= 0:
            return "nothing to refund"
        return "refunded"

    def _status(self, order):
        return order["status"]
""",
}
AFTER = {
    **BEFORE,
    AGENT: BEFORE[AGENT].replace(
        '        return "refunded"\n',
        '        if order["amount"] > 100:\n            return "sent to review"\n'
        '        return "refunded"\n',
    ),
}


def proposal(symbol, line, quote):
    return {
        "symbol_id": symbol,
        "kind": "handler",
        "reason": "The intent dispatcher in Agent.handle runs it.",
        "evidence": [{"path": AGENT, "start_line": line, "end_line": line, "quote": quote}],
    }


def mapped(repo):
    """A map whose plan proposes the two intent handlers and gives each a flow."""
    for path, text in BEFORE.items():
        write(repo, path, text)
    commit(repo)
    git(repo, "tag", "base")
    workspace = Workspace(repo, prepare(repo)["session_id"])
    main = entry(workspace, "#main").entry_id
    plan = {
        "proposed_entries": [
            proposal(REFUND, 4, "return self._refund(order)"),
            proposal(STATUS, 5, "return self._status(order)"),
        ],
        "flows": [
            {"key": "message", "name": "Answer a message", "entry_ids": [main]},
            {"key": "refund", "name": "Refund an order", "entry_ids": [entry_of(REFUND)]},
            {"key": "status", "name": "Order status", "entry_ids": [entry_of(STATUS)]},
        ],
    }
    status = workspace.save_plan(MapPlan.model_validate(plan))
    return workspace, {task["name"]: task["flow_id"] for task in status["tasks"]}


def entry_of(symbol):
    from genesis_ci.business_map.python_entries import entry_id

    return entry_id(symbol)


def reviewed(repo, files=AFTER):
    for path, text in files.items():
        write(repo, path, text)
    for path in BEFORE.keys() - files.keys():
        (repo / path).unlink()
    commit(repo)
    result = prepare(repo, base="base", head="HEAD")
    return Workspace(repo, result["session_id"]), result


def test_a_review_puts_changes_on_the_flow_the_map_gave_them(source_repo):
    workspace, flows = mapped(source_repo)
    review, result = reviewed(source_repo)
    assert result["carried_entries"] == {
        "from_session": workspace.session["session_id"],
        "entries": 2,
        "not_found": [],
    }
    refund = flow_id_for([REFUND])
    assert flows["Refund an order"] == refund
    # Before any plan, the changes sit on the refund flow, as in the map; main only
    # reaches them.
    change = review.status()["change"]
    assert [item["flow_id"] for item in change["affected_flows"]] == [refund]
    changes = review.stored_report().changes
    assert changes and {item.projection.flow_id for item in changes} == {refund}
    carried = entry(review, "#Agent._refund")
    assert carried.detection == "agent_proposed"
    assert carried.attributes["carried_from"] == workspace.session["session_id"]
    # A review plan uses the carried entry by its id, and the task keeps the map's id.
    plan = {
        "flows": [{"key": "refund", "name": "Refund an order", "entry_ids": [carried.entry_id]}]
    }
    status = review.save_plan(MapPlan.model_validate(plan))
    assert [task["flow_id"] for task in status["tasks"]] == [refund]
    assert [item["flow_id"] for item in status["change"]["affected_flows"]] == [refund]


def test_only_entries_whose_function_still_exists_are_carried(source_repo):
    mapped(source_repo)
    gone = {**AFTER, AGENT: AFTER[AGENT].replace("_status", "_lookup")}
    review, result = reviewed(source_repo, gone)
    assert result["carried_entries"]["entries"] == 1
    assert result["carried_entries"]["not_found"] == [STATUS]
    assert set(review.carried) == {entry_of(REFUND)}


def test_a_carried_entry_is_kept_once_planned_and_is_not_proposed_again(source_repo):
    workspace, _ = mapped(source_repo)
    review, _ = reviewed(source_repo)
    refund = entry_of(REFUND)
    with pytest.raises(LoopError) as refused:
        review.save_plan(
            MapPlan.model_validate({"proposed_entries": [proposal(REFUND, 4, "self._refund")]})
        )
    assert refused.value.errors[0]["code"] == "already_an_entry"
    # Set aside when the code no longer bears it out.
    skip = {"entry_id": refund, "reason": "not_an_entry", "note": "handle() no longer calls it"}
    review.save_plan(MapPlan.model_validate({"skipped": [skip]}))
    # With a plan in place, a later map does not change what the review started from.
    (workspace.root / "plan.json").unlink()
    again = prepare(source_repo, base="base", head="HEAD")
    assert again["resumed"]
    assert again["carried_entries"] == {
        "from_session": workspace.session["session_id"],
        "entries": 2,
        "not_found": [],
    }
    assert set(Workspace(source_repo, again["session_id"]).carried) == {
        refund,
        entry_of(STATUS),
    }


def test_the_latest_map_is_the_one_carried(source_repo):
    workspace, _ = mapped(source_repo)
    older = workspace.root / "plan.json"
    stored = json.loads(older.read_text())
    newer = workspace.root.parent / "ses_0000000000000000"
    newer.mkdir()
    (newer / "session.json").write_text(json.dumps({**workspace.session, "session_id": newer.name}))
    (newer / "plan.json").write_text(
        json.dumps(
            {
                **stored,
                "proposed": [item for item in stored["proposed"] if item["symbol_id"] == STATUS],
            }
        )
    )
    os.utime(older, (1, 1))
    review, result = reviewed(source_repo)
    assert result["carried_entries"]["from_session"] == newer.name
    assert set(review.carried) == {entry_of(STATUS)}


def test_a_map_session_that_does_not_name_its_engine_is_a_python_one(source_repo):
    workspace, _ = mapped(source_repo)
    # Sessions written before they named their engine were all Python ones.
    session = {key: value for key, value in workspace.session.items() if key != "engine"}
    (workspace.root / "session.json").write_text(json.dumps(session))
    review, result = reviewed(source_repo)
    assert result["carried_entries"]["from_session"] == workspace.session["session_id"]
    assert set(review.carried) == {entry_of(REFUND), entry_of(STATUS)}


def test_a_review_without_a_map_starts_from_the_recognised_entries(source_repo):
    for path, text in BEFORE.items():
        write(source_repo, path, text)
    commit(source_repo)
    git(source_repo, "tag", "base")
    review, result = reviewed(source_repo)
    assert "carried_entries" not in result
    assert not (review.root / CARRIED).exists()
    change = review.status()["change"]
    assert [item["flow_id"] for item in change["affected_flows"]] == [
        flow_id_for(["desk/__main__.py#main"])
    ]


def test_a_root_candidate_the_map_confirmed_is_no_longer_offered(source_repo):
    jobs = "from desk.agent import Agent\n\n\ndef nightly():\n    return Agent()._refund({})\n"
    before = {**BEFORE, "desk/jobs.py": jobs}
    for path, text in before.items():
        write(source_repo, path, text)
    commit(source_repo)
    git(source_repo, "tag", "base")
    workspace = Workspace(source_repo, prepare(source_repo)["session_id"])
    nightly = entry(workspace, "#nightly")
    assert nightly.detection == "root_heuristic"
    scheduled = {
        "symbol_id": nightly.symbol_id,
        "kind": "scheduled",
        "reason": "cron runs it",
        "evidence": [{"path": "desk/jobs.py", "start_line": 4, "end_line": 4, "quote": "def"}],
    }
    flow = {"key": "nightly", "name": "Nightly refunds", "entry_ids": [nightly.entry_id]}
    workspace.save_plan(MapPlan.model_validate({"flows": [flow], "proposed_entries": [scheduled]}))
    review, result = reviewed(source_repo, {**AFTER, "desk/jobs.py": jobs})
    assert result["carried_entries"]["entries"] == 1
    carried = entry(review, "#nightly")
    assert (carried.kind, carried.detection) == ("scheduled", "agent_proposed")
    change = review.status()["change"]
    assert change["possible_entries"] == []
    assert flow_id_for([nightly.symbol_id]) in {
        item["flow_id"] for item in change["affected_flows"]
    } | {item.flow_id for item in review.stored_map().flows}


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setenv("GENESIS_NO_BROWSER", "1")

    def run(*arguments):
        result = CliRunner().invoke(app, ["map", *arguments])
        return result.exit_code, json.loads(result.stdout)

    return run


def committed_map(repo, cli, workspace):
    """The rendered map copied next to a spec, as Genesis EDD keeps it, not yet committed."""
    session = workspace.session["session_id"]
    code, _ = cli("render", "--repo", str(repo), "--session", session)
    assert code in (0, 2)
    write(repo, SPEC, (repo / ".genesis" / "out" / session / "business-map.json").read_text())
    return {"path": SPEC, "snapshot_id": workspace.session["snapshot_id"]}


def affected(workspace):
    return [item["flow_id"] for item in workspace.status()["change"]["affected_flows"]]


def test_a_clone_reviewed_from_a_committed_map_gets_the_flows_of_that_map(
    source_repo, tmp_path, cli
):
    workspace, flows = mapped(source_repo)
    source = committed_map(source_repo, cli, workspace)
    # The copy is committed with the change; the sessions stay behind, ignored by Git.
    original, _ = reviewed(source_repo)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(source_repo), str(clone))
    assert not (clone / ".genesis" / "sessions").exists()
    arguments = ("prepare", "--repo", str(clone), "--base", "base", "--head", "HEAD")
    code, result = cli(*arguments, "--entries-from", SPEC)
    assert code == 0
    assert result["carried_entries"] == {"from_map": source, "entries": 2, "not_found": []}
    review = Workspace(clone, result["session_id"])
    assert affected(review) == affected(original) == [flows["Refund an order"]]
    assert entry(review, "#Agent._refund").attributes["carried_from"] == SPEC
    # Without it, the clone has no map to start from.
    code, plain = cli(*arguments)
    assert code == 0 and "carried_entries" not in plain
    main = flow_id_for(["desk/__main__.py#main"])
    assert affected(Workspace(clone, plain["session_id"])) == [main]


def test_the_map_named_is_used_instead_of_the_latest_one(source_repo, tmp_path, cli):
    workspace, _ = mapped(source_repo)
    source = committed_map(source_repo, cli, workspace)
    # A later map that proposed only the status handler.
    stored = json.loads((workspace.root / "plan.json").read_text())
    newer = workspace.root.parent / "ses_0000000000000000"
    newer.mkdir()
    (newer / "session.json").write_text(json.dumps({**workspace.session, "session_id": newer.name}))
    only = [item for item in stored["proposed"] if item["symbol_id"] == STATUS]
    (newer / "plan.json").write_text(json.dumps({**stored, "proposed": only}))
    os.utime(workspace.root / "plan.json", (1, 1))
    review, result = reviewed(source_repo)
    assert result["carried_entries"]["from_session"] == newer.name
    assert set(review.carried) == {entry_of(STATUS)}
    # Before a plan, each prepare starts from what it is given.
    named = prepare(source_repo, base="base", head="HEAD", entries_from=SPEC)
    assert named["carried_entries"] == {"from_map": source, "entries": 2, "not_found": []}
    review = Workspace(source_repo, named["session_id"])
    assert set(review.carried) == {entry_of(REFUND), entry_of(STATUS)}
    assert json.loads((review.root / CARRIED).read_text())["from_map"] == source
    assert affected(review) == [flow_id_for([REFUND])]
    assert entry(review, "#Agent._refund").attributes["carried_from"] == SPEC
    # A file outside the repository is named in full, and in the entries by its name.
    outside = tmp_path / "elsewhere" / "business-map.json"
    outside.parent.mkdir()
    outside.write_text((source_repo / SPEC).read_text())
    named = prepare(source_repo, base="base", head="HEAD", entries_from=outside)
    assert named["carried_entries"]["from_map"]["path"] == str(outside.resolve())
    review = Workspace(source_repo, named["session_id"])
    assert entry(review, "#Agent._refund").attributes["carried_from"] == "business-map.json"


def test_a_file_that_is_not_a_map_is_refused(source_repo, cli):
    for path, text in BEFORE.items():
        write(source_repo, path, text)
    write(source_repo, SPEC, json.dumps({"flows": []}))
    commit(source_repo)
    for given in (SPEC, "spec/missing.json", "spec"):
        code, result = cli("prepare", "--repo", str(source_repo), "--entries-from", given)
        assert code == 1 and result["error"]["code"] == "invalid_input"
        assert given in result["error"]["message"]
    code, result = cli("prepare", "--repo", str(source_repo), "--entries-from", SPEC)
    assert {item["path"] for item in result["error"]["errors"]} >= {"snapshot_id", "coverage"}
    # Refused before anything was read or written.
    assert not (source_repo / ".genesis" / "sessions").exists()


def test_the_agent_engine_refuses_a_map_to_start_from(source_repo, cli):
    write(source_repo, "web/app.ts", "export function main() {\n  return 1;\n}\n")
    commit(source_repo)
    given = str(FIXTURE_MAP)
    for engine in ("agent", "auto"):
        code, result = cli(
            "prepare", "--repo", str(source_repo), "--engine", engine, "--entries-from", given
        )
        assert code == 1 and result["error"]["code"] == "invalid_input"
        assert "Only the Python engine supports --entries-from" in result["error"]["message"]
    assert not (source_repo / ".genesis" / "sessions").exists()
    code, result = cli("prepare", "--repo", str(source_repo))
    assert code == 0 and result["engine"] == "agent"


def test_a_planned_review_refuses_another_map_to_start_from(source_repo, cli):
    workspace, flows = mapped(source_repo)
    source = committed_map(source_repo, cli, workspace)
    review, _ = reviewed(source_repo)
    refund = entry_of(REFUND)
    plan = {"flows": [{"key": "refund", "name": "Refund an order", "entry_ids": [refund]}]}
    review.save_plan(MapPlan.model_validate(plan))
    arguments = ("prepare", "--repo", str(source_repo), "--base", "base", "--head", "HEAD")
    code, result = cli(*arguments, "--entries-from", SPEC)
    assert code == 1 and result["error"]["code"] == "invalid_input"
    message = result["error"]["message"]
    assert "was planned with other entries" in message
    assert workspace.session["session_id"] in message and SPEC in message
    assert f".genesis/sessions/{review.session['session_id']}" in message
    # Without the flag the plan goes on as it was.
    code, result = cli(*arguments)
    assert code == 0 and result["resumed"]
    assert result["carried_entries"]["from_session"] == workspace.session["session_id"]
    # Started over from the map named, the same flag resumes it and another is refused.
    shutil.rmtree(review.root)
    code, result = cli(*arguments, "--entries-from", SPEC)
    assert code == 0 and result["carried_entries"]["from_map"] == source
    review = Workspace(source_repo, result["session_id"])
    review.save_plan(MapPlan.model_validate(plan))
    code, result = cli(*arguments, "--entries-from", SPEC)
    assert code == 0 and result["resumed"] and result["carried_entries"]["from_map"] == source
    assert [task["flow_id"] for task in review.tasks()] == [flows["Refund an order"]]
    code, result = cli(*arguments, "--entries-from", str(FIXTURE_MAP))
    assert code == 1 and "was planned with other entries" in result["error"]["message"]
    # The same map planned again with other entries is another source too.
    copy = source_repo / SPEC
    copy.write_text(copy.read_text().replace('"agent_proposed"', '"adapter"', 1))
    code, result = cli(*arguments, "--entries-from", SPEC)
    assert code == 1 and "not those it proposes now" in result["error"]["message"]
    # A session planned with nothing carried refuses a map too.
    current = Workspace(source_repo, prepare(source_repo)["session_id"])
    current.save_plan(None)
    code, result = cli("prepare", "--repo", str(source_repo), "--entries-from", SPEC)
    assert code == 1 and "none carried from a map" in result["error"]["message"]


def test_a_map_session_starts_from_the_map_named(source_repo, cli):
    workspace, flows = mapped(source_repo)
    committed_map(source_repo, cli, workspace)
    for path, text in AFTER.items():
        write(source_repo, path, text)
    commit(source_repo)
    # A map starts from the recognised entries alone unless a map is named.
    plain = prepare(source_repo, head="HEAD")
    assert "carried_entries" not in plain
    remap = prepare(source_repo, entries_from=SPEC)
    assert remap["mode"] == "map" and remap["carried_entries"]["entries"] == 2
    again = Workspace(source_repo, remap["session_id"])
    assert {flow.flow_id for flow in again.stored_map().flows} >= {
        flows["Refund an order"],
        flows["Order status"],
    }
    # The default plan keeps them, and a plan names them by id.
    plan = {
        "flows": [
            {"key": "refund", "name": "Refund an order", "entry_ids": [entry_of(REFUND)]},
            {"key": "status", "name": "Order status", "entry_ids": [entry_of(STATUS)]},
        ]
    }
    status = again.save_plan(MapPlan.model_validate(plan))
    assert {task["name"]: task["flow_id"] for task in status["tasks"]} == {
        "Refund an order": flows["Refund an order"],
        "Order status": flows["Order status"],
    }


def test_entries_a_map_gave_one_flow_stay_in_one_flow(source_repo, cli):
    for path, text in BEFORE.items():
        write(source_repo, path, text)
    commit(source_repo)
    git(source_repo, "tag", "base")
    workspace = Workspace(source_repo, prepare(source_repo)["session_id"])
    main = entry(workspace, "#main").entry_id
    handlers = [entry_of(REFUND), entry_of(STATUS)]
    plan = {
        "proposed_entries": [
            proposal(REFUND, 4, "return self._refund(order)"),
            proposal(STATUS, 5, "return self._status(order)"),
        ],
        "flows": [
            {"key": "message", "name": "Answer a message", "entry_ids": [main]},
            # The lookups and upkeep of one thing in one supporting flow.
            {"key": "orders", "name": "Handle orders", "tier": "supporting", "entry_ids": handlers},
        ],
    }
    status = workspace.save_plan(MapPlan.model_validate(plan))
    orders = flow_id_for([REFUND, STATUS])
    assert {task["name"]: task["flow_id"] for task in status["tasks"]}["Handle orders"] == orders
    committed_map(source_repo, cli, workspace)
    review, result = reviewed(source_repo)
    assert result["carried_entries"]["entries"] == 2
    # The change to the refund handler lands on the flow the map gave it, with both
    # entries, not on a flow of its own the map never had.
    (flow,) = review.status()["change"]["affected_flows"]
    assert (flow["flow_id"], flow["entry_ids"]) == (orders, handlers)
    assert {item.projection.flow_id for item in review.stored_report().changes} == {orders}
    # So it does from a committed copy of the map.
    named = prepare(source_repo, base="base", head="HEAD", entries_from=SPEC)
    review = Workspace(source_repo, named["session_id"])
    assert affected(review) == [orders]
    # A plan with the entries it lists keeps the id, and so does the default plan.
    status = review.save_plan(None)
    assert orders in {task["flow_id"] for task in status["tasks"]}
    assert affected(review) == [orders]


def test_a_change_that_removes_a_carried_entry_shows_its_flow_as_removed(source_repo):
    _, flows = mapped(source_repo)
    without = BEFORE[AGENT].replace("return self._status(order)", 'return order["status"]')
    without = without[: without.index("    def _status")].rstrip() + "\n"
    review, result = reviewed(source_repo, {**AFTER, AGENT: without})
    assert result["carried_entries"]["not_found"] == [STATUS]
    report = review.stored_report()
    # The flow the map gave it is gone, as for an entry the analyzers recognise.
    assert [flow.flow_id for flow in report.removed_flows] == [flows["Order status"]]
    assert "handler · Agent._status" in review.change_summary()["removed_flows"][0]


MAIN = "desk/__main__.py#main"


def grouped_map(repo, *flows):
    """A map whose plan proposes both intent handlers and gives `flows`, each a list of
    symbols, one flow each; the base tag marks the code it was made of."""
    for path, text in BEFORE.items():
        write(repo, path, text)
    commit(repo)
    git(repo, "tag", "base")
    workspace = Workspace(repo, prepare(repo)["session_id"])
    plan = {
        "proposed_entries": [
            proposal(REFUND, 4, "return self._refund(order)"),
            proposal(STATUS, 5, "return self._status(order)"),
        ],
        "flows": [
            {"key": f"f{index}", "name": f"Flow {index}", "entry_ids": list(map(entry_of, symbols))}
            for index, symbols in enumerate(flows)
        ],
    }
    status = workspace.save_plan(MapPlan.model_validate(plan))
    assert {task["flow_id"] for task in status["tasks"]} == set(map(flow_id_for, flows))
    return workspace


def without_status(text=BEFORE[AGENT]):
    text = text.replace("return self._status(order)", 'return order["status"]')
    return text[: text.index("    def _status")].rstrip() + "\n"


def test_a_change_that_removes_one_entry_of_a_flow_shows_that_flow_as_removed(source_repo):
    grouped_map(source_repo, [MAIN], [REFUND, STATUS])
    review, result = reviewed(source_repo, {**AFTER, AGENT: without_status(AFTER[AGENT])})
    assert result["carried_entries"]["not_found"] == [STATUS]
    report = review.stored_report()
    # The flow the map had, by the id it had, with both its entries as they were.
    (removed,) = report.removed_flows
    assert removed.flow_id == flow_id_for([REFUND, STATUS])
    assert [item.symbol_id for item in removed.entries] == [REFUND, STATUS]
    # The handler left has a flow of its own now, which the change lands on.
    assert flow_id_for([REFUND]) in affected(review)
    assert removed.flow_id not in {flow.flow_id for flow in review.stored_map().flows}


def test_a_flow_that_loses_two_entries_is_shown_removed_once(source_repo):
    grouped_map(source_repo, [MAIN, REFUND, STATUS])
    gone = {**BEFORE, "desk/__main__.py": BEFORE["desk/__main__.py"].replace("main(", "run(")}
    gone[AGENT] = without_status().replace("_refund", "_repay")
    review, result = reviewed(source_repo, gone)
    assert sorted(result["carried_entries"]["not_found"]) == [REFUND, STATUS]
    flows = review.stored_report().removed_flows
    # The framework entry renamed with them is no flow of its own either.
    assert [flow.flow_id for flow in flows] == [flow_id_for([MAIN, REFUND, STATUS])]


def test_a_framework_entry_the_map_grouped_with_a_proposed_one_keeps_their_flow(source_repo):
    grouped_map(source_repo, [MAIN, REFUND], [STATUS])
    review, _ = reviewed(source_repo)
    together = flow_id_for([MAIN, REFUND])
    assert {flow.flow_id for flow in review.stored_map().flows} == {
        together,
        flow_id_for([STATUS]),
    }
    assert together in {task["flow_id"] for task in review.save_plan(None)["tasks"]}
    # Removed, the framework entry takes the flow with it.
    review, _ = reviewed(source_repo, {key: AFTER[key] for key in AFTER if "main" not in key})
    assert [flow.flow_id for flow in review.stored_report().removed_flows] == [together]


def test_an_entry_whose_function_the_base_lacks_has_no_flow_to_show_removed(source_repo):
    cancel = f"{AGENT}#Agent._cancel"
    for path, text in BEFORE.items():
        write(source_repo, path, text)
    commit(source_repo)
    git(source_repo, "tag", "base")
    # Mapped on a later commit that has a third handler, since taken out again.
    added = BEFORE[AGENT] + "\n    def _cancel(self, order):\n        return 'cancelled'\n"
    write(source_repo, AGENT, added)
    commit(source_repo)
    workspace = Workspace(source_repo, prepare(source_repo)["session_id"])
    plan = {
        "proposed_entries": [proposal(cancel, 15, "def _cancel(self, order):")],
        "flows": [{"key": "cancel", "name": "Cancel", "entry_ids": [entry_of(cancel)]}],
    }
    workspace.save_plan(MapPlan.model_validate(plan))
    review, result = reviewed(source_repo)
    assert result["carried_entries"]["not_found"] == [cancel]
    assert review.stored_report().removed_flows == ()


RULES_API = """from fastapi import FastAPI

app = FastAPI()
RULES = {}


@app.get("/rules")
def list_rules():
    return sorted(RULES)


@app.post("/rules/{name}")
def create_rule(name: str):
    RULES[name] = True
    return name


@app.delete("/rules/{name}")
def delete_rule(name: str):
    RULES.pop(name, None)
    return name


def purge_rules():
    RULES.clear()
"""


RULES_FILE = "rules/api.py"
PURGE = f"{RULES_FILE}#purge_rules"
DELETE_RULE = f"{RULES_FILE}#delete_rule"


@pytest.mark.parametrize("removed", ["purge_rules", "delete_rule"])
def test_a_removed_flow_shows_a_public_proposed_entry_as_the_map_had_it(source_repo, removed):
    write(source_repo, RULES_FILE, RULES_API)
    commit(source_repo)
    git(source_repo, "tag", "base")
    older = Workspace(source_repo, prepare(source_repo)["session_id"])
    line = RULES_API.splitlines().index("def purge_rules():") + 1
    others = [f"{RULES_FILE}#{name}" for name in ("list_rules", "create_rule")]
    plan = {
        # Nothing calls the job, so the analyzers also take it for a root.
        "proposed_entries": [
            {
                "symbol_id": PURGE,
                "kind": "scheduled",
                "reason": "cron runs it",
                "evidence": [
                    {"path": RULES_FILE, "start_line": line, "end_line": line, "quote": "def"}
                ],
            }
        ],
        "flows": [
            {"key": f"f{index}", "name": f"Flow {index}", "entry_ids": list(map(entry_of, group))}
            for index, group in enumerate([[DELETE_RULE, PURGE], *([item] for item in others)])
        ],
    }
    older.save_plan(MapPlan.model_validate(plan))
    if removed == "purge_rules":
        text = RULES_API[: RULES_API.index("def purge_rules")].rstrip() + "\n"
    else:
        start = RULES_API.index('@app.delete("/rules/{name}")')
        text = RULES_API[:start] + RULES_API[RULES_API.index("def purge_rules") :]
    write(source_repo, RULES_FILE, text)
    commit(source_repo)
    review = Workspace(source_repo, prepare(source_repo, base="base", head="HEAD")["session_id"])
    (flow,) = review.stored_report().removed_flows
    assert flow.flow_id == flow_id_for([DELETE_RULE, PURGE])
    entries = {item.symbol_id: (item.detection.value, item.kind.value) for item in flow.entries}
    # The entry the map proposed, not the root the analyzers would take it for.
    assert entries == {
        DELETE_RULE: ("adapter", "http_route"),
        PURGE: ("agent_proposed", "scheduled"),
    }
    assert flow.name.endswith(" + scheduled · purge_rules")


def test_the_latest_map_that_grouped_entries_is_carried_without_proposals(source_repo):
    api = "rules/api.py"
    rule = {name: f"{api}#{name}" for name in ("list_rules", "create_rule", "delete_rule")}
    purge = f"{api}#purge_rules"
    write(source_repo, api, RULES_API)
    commit(source_repo)
    git(source_repo, "tag", "base")
    older = Workspace(source_repo, prepare(source_repo)["session_id"])
    line = RULES_API.splitlines().index("def purge_rules():") + 1
    scheduled = {
        "symbol_id": purge,
        "kind": "scheduled",
        "reason": "cron runs it",
        "evidence": [{"path": api, "start_line": line, "end_line": line, "quote": "def"}],
    }
    flows = [
        [rule["list_rules"], rule["delete_rule"], purge],
        [rule["create_rule"]],
    ]
    plan = {
        "proposed_entries": [scheduled],
        "flows": [
            {"key": f"f{index}", "name": f"Flow {index}", "entry_ids": list(map(entry_of, flow))}
            for index, flow in enumerate(flows)
        ],
    }
    older.save_plan(MapPlan.model_validate(plan))
    stored = json.loads((older.root / "plan.json").read_text())
    for name, flows, when in (
        # Later, proposing nothing: the routes regrouped, the job no longer a flow.
        ("ses_0000000000000001", [["list_rules", "create_rule"], ["delete_rule"]], 2),
        # Later still, one flow per route as the default plan has it: passed over.
        ("ses_0000000000000002", [["list_rules"], ["create_rule"], ["delete_rule"]], 3),
    ):
        root = older.root.parent / name
        root.mkdir()
        (root / "session.json").write_text(json.dumps({**older.session, "session_id": name}))
        flows = [{"key": "f", "entry_ids": [entry_of(rule[key]) for key in flow]} for flow in flows]
        (root / "plan.json").write_text(
            json.dumps({**stored, "plan": {"flows": flows}, "proposed": []})
        )
        os.utime(root / "plan.json", (when, when))
    os.utime(older.root / "plan.json", (1, 1))
    write(source_repo, api, RULES_API.replace("RULES.pop(name, None)", "del RULES[name]"))
    commit(source_repo)
    result = prepare(source_repo, base="base", head="HEAD")
    assert result["carried_entries"] == {
        "from_session": "ses_0000000000000001",
        "entries": 0,
        "not_found": [],
    }
    review = Workspace(source_repo, result["session_id"])
    # The change lands on the flow the latest map gave it, not on one an older map had.
    assert affected(review) == [flow_id_for([rule["delete_rule"]])]
    assert flow_id_for([rule["list_rules"], rule["create_rule"]]) in {
        flow.flow_id for flow in review.stored_map().flows
    }

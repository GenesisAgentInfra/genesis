"""Static skeleton: control structure of each entry, built from facts without a model."""

from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.business_map.skeleton import build_skeleton
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.business_map import BusinessMap
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

APP = """import typer

from store import load, save

cli = typer.Typer()


@cli.command("submit")
def submit(report):
    amount = len(report)
    if amount >= 100:
        save(report, "pending")
        return "pending"
    elif amount < 0:
        raise ValueError("negative")
    save(report, "approved")
    return "approved"


@cli.command()
def drain_queue(queue):
    while queue:
        item = load(queue)
        if item is None:
            continue
        save(item, "done")
    return len(queue)
"""
STORE = """def save(report, status):
    return (report, status)


def load(queue):
    return queue
"""


def skeleton(root, files, **options):
    for path, text in files.items():
        write(root, path, text)
    commit(root)
    facts = python_facts(extract_python(capture_snapshot(root, SnapshotSpec(head="HEAD"))))
    return build_skeleton(facts, **options)


def flow(result, name):
    return next(item for item in result.flows if name in item.name)


def edges(item):
    names = {step.step_id: step.name for step in item.steps}
    return {
        (
            names[edge.source],
            edge.relation.value,
            edge.condition.branch if edge.condition else None,
            names[edge.target],
        )
        for edge in item.edges
    }


def test_branches_follow_the_source_and_results_end_a_path(source_repo):
    result = skeleton(source_repo, {"app.py": APP, "store.py": STORE})
    submit = flow(result, "command submit")
    assert [step.kind.value for step in submit.steps] == [
        "trigger",
        "decision",
        "action",
        "result",
        "decision",
        "result",
        "action",
        "result",
    ]
    found = edges(submit)
    trigger = "command submit · submit"
    assert (trigger, "sequence", None, "amount >= 100") in found
    assert ("amount >= 100", "branch", "true", 'save(report, "pending")') in found
    assert ("amount >= 100", "branch", "false", "amount < 0") in found
    assert ("amount < 0", "branch", "true", 'raise ValueError("negative")') in found
    # The statement after the if/elif is reached only when the elif is false.
    assert ("amount < 0", "branch", "false", 'save(report, "approved")') in found
    assert ('save(report, "approved")', "sequence", None, 'return "approved"') in found
    assert not [edge for edge in found if edge[0].startswith(("return", "raise"))]
    assert len(found) == 7


def test_loops_have_a_body_a_back_edge_and_an_exit(source_repo):
    result = skeleton(source_repo, {"app.py": APP, "store.py": STORE})
    drain = flow(result, "command drain-queue")
    found = edges(drain)
    assert ("while queue", "branch", "loop", "load(queue)") in found
    assert ("load(queue)", "sequence", None, "item is None") in found
    assert ("item is None", "branch", "false", 'save(item, "done")') in found
    # The end of the body and the untaken branch both return to the loop condition.
    assert ('save(item, "done")', "loop", None, "while queue") in found
    assert ("item is None", "branch", "true", "while queue") in found
    assert ("while queue", "branch", "exit", "return len(queue)") in found


def test_a_call_inside_a_result_is_evaluated_before_it(source_repo):
    result = skeleton(
        source_repo,
        {
            "app.py": """import typer

from store import save

cli = typer.Typer()


@cli.command()
def check(value):
    if not value:
        raise typer.BadParameter(save(value, "bad"))
    return save(value, "ok")
""",
            "store.py": STORE,
        },
    )
    check = flow(result, "command check")
    assert [step.name for step in check.steps][1:] == [
        "not value",
        'save(value, "bad")',
        'typer.BadParameter(save(value, "bad"))',
        'raise typer.BadParameter(save(value, "bad"))',
        'save(value, "ok")',
        'return save(value, "ok")',
    ]
    found = edges(check)
    assert ("not value", "branch", "true", 'save(value, "bad")') in found
    assert ("not value", "branch", "false", 'save(value, "ok")') in found
    assert not [edge for edge in found if edge[0].startswith(("return", "raise"))]
    assert len(found) == 6


def test_skeleton_is_a_valid_partial_map_of_static_steps(source_repo):
    result = skeleton(source_repo, {"app.py": APP, "store.py": STORE})
    assert BusinessMap.model_validate(result.model_dump(mode="json")) == result
    assert result.analysis_status == "partial"
    assert {item.stage.value for item in result.flows} == {"skeleton"}
    assert all(
        step.support == "static_fact" and step.anchors
        for item in result.flows
        for step in item.steps
    )
    assert [(domain.name, domain.support) for domain in result.domains] == [
        ("(repository root)", "path_grouping")
    ]
    assert result.coverage.entries_total == 2 and result.coverage.entries_unhandled == 2
    assert result.limitations == ()
    submit = flow(result, "command submit")
    assert submit.entries[0].attributes == {"command": "submit"}
    assert submit.accounting.accountable == submit.accounting.covered == 7


def test_long_entries_are_truncated_and_say_so(source_repo):
    result = skeleton(source_repo, {"app.py": APP, "store.py": STORE}, max_steps=3)
    submit = flow(result, "command submit")
    assert len(submit.steps) == 4
    assert submit.accounting.truncated is True
    assert submit.limitations[0].code == "skeleton_truncated"


def test_without_framework_entries_the_largest_roots_are_shown_with_a_warning(source_repo):
    result = skeleton(
        source_repo,
        {
            "lib.py": """def big(value):
    if value:
        return 1
    return 2


def small():
    return 3
"""
        },
    )
    assert [item.name for item in result.flows] == ["root · big", "root · small"]
    assert result.flows[0].entries[0].detection == "root_heuristic"
    assert result.limitations[0].code == "no_framework_entries"
    assert result.limitations[0].affects_completeness is True


def test_repository_without_python_gives_an_empty_but_valid_skeleton(source_repo):
    result = skeleton(source_repo, {"README.md": "# nothing to analyze\n"})
    assert result.flows == () and result.domains == ()
    assert result.coverage.entries_total == 0
    assert result.limitations[0].code == "no_framework_entries"

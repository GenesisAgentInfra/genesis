"""Item writes change objects, not module namespaces; only namespace writes block resolution."""

import pytest
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

HEAD = EvidenceSide.head
NAMESPACE_REASON = "Dynamic namespace mutation"


def analyze(root, files):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    return extract_python(capture_snapshot(root, SnapshotSpec(base=head, head=head)))


def call(result, text, path="app.py"):
    found = [
        item
        for item in result.analysis.calls
        if item.side == HEAD and item.path == path and item.expression == text
    ]
    assert len(found) == 1, [item.expression for item in result.analysis.calls]
    return found[0]


def flags(result, path="app.py"):
    file = result.files[(HEAD, path)]
    return file.dynamic_namespace, file.mutable_values


def test_item_assignment_does_not_block_resolution_in_or_into_a_module(source_repo):
    result = analyze(
        source_repo,
        {
            "helpers.py": """def save(report, status):
    report["status"] = status
    return report


def review(report):
    return "ok"
""",
            "app.py": """from helpers import review, save


def local_step(report):
    return report


def submit(report, cache):
    cache[report["id"]] = report
    local_step(report)
    review(report)
    return save(report, "approved")
""",
        },
    )
    assert flags(result) == (False, True)
    assert flags(result, "helpers.py") == (False, True)
    assert call(result, "local_step(report)").target.targets == ("app.py#local_step",)
    assert call(result, "review(report)").target.targets == ("helpers.py#review",)
    saved = call(result, 'save(report, "approved")')
    assert (saved.target.status, saved.target.targets) == ("resolved", ("helpers.py#save",))


def test_item_assignment_keeps_literal_containers_uncertain(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """def first():
    return 1


def second():
    return 2


def use(tools, model):
    return tools, model


TOOLS = {"first": first}
TOOLS["second"] = second
MODEL = "small"


def run():
    return use(TOOLS, MODEL)
"""
        },
    )
    assert flags(result) == (False, True)
    tools, model = (item.value for item in call(result, "use(TOOLS, MODEL)").arguments)
    mutated = result.resolver.value(tools, HEAD, "app.py")
    assert (mutated.kind, mutated.reason) == ("unknown", "Container may be mutated")
    constant = result.resolver.value(model, HEAD, "app.py")
    assert (constant.kind, constant.value) == ("literal", "small")


@pytest.mark.parametrize(
    "statement",
    [
        'globals()["helper"] = other',
        'vars()["helper"] = other',
        'vars(sys.modules[__name__])["helper"] = other',
        'sys.modules[__name__].__dict__["helper"] = other',
        'sys.modules["shadow"] = other',
        '__builtins__["helper"] = other',
        'del globals()["helper"]',
        "del helper",
        "del other, registry[0]",
    ],
)
def test_namespace_writes_and_name_deletion_still_block_resolution(source_repo, statement):
    result = analyze(
        source_repo,
        {
            "app.py": f"""import sys

registry = [1]


def helper():
    return 1


def other():
    return 2


def run():
    return helper()


{statement}
"""
        },
    )
    assert flags(result)[0] is True
    target = call(result, "helper()").target
    assert target.status == "unknown" and target.reason.startswith(NAMESPACE_REASON)


@pytest.mark.parametrize(
    ("statement", "notes"),
    [
        ("del registry[0]", 0),
        ("del registry[0], registry[1:]", 0),
        ("del run.cache", 0),
        ("del other", 1),
    ],
)
def test_only_name_deletion_is_reported_as_a_binding_limitation(source_repo, statement, notes):
    result = analyze(
        source_repo,
        {
            "app.py": f"""registry = [1, 2, 3]


def helper():
    return 1


def other():
    return 2


def run():
    return helper()


{statement}
"""
        },
    )
    deletions = [
        item
        for item in result.files[(HEAD, "app.py")].unresolved
        if item.reason.startswith("Deletion")
    ]
    assert len(deletions) == notes
    assert flags(result)[0] is bool(notes)
    resolved = call(result, "helper()").target.status == "resolved"
    assert resolved is not bool(notes)

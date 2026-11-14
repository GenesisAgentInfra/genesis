"""Method calls on self and on instances of local classes resolve as candidates, never as facts."""

from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

HEAD = EvidenceSide.head

SERVICE = """from repo import Repo


class Notifier:
    def send(self, report):
        return report

    def __call__(self, report):
        return self.send(report)


class Service:
    def __init__(self, limit):
        self.repo = Repo()
        self.limit = limit
        self.handler = self.fallback

    def run(self, report):
        self.validate(report)
        self.repo.save(report)
        self.repo.missing(report)
        self.limit.check(report)
        self.handler(report)
        return self.inherited(report)

    def validate(self, report):
        return bool(report)

    def fallback(self, report):
        return None


def main(report):
    service = Service(10)
    service.run(report)
    service.absent(report)
    notify = Notifier()
    notify(report)
    plain = Repo()
    plain(report)
    return Repo().save(report)
"""
REPO = """class Repo:
    def save(self, report):
        return report
"""


def analyze(root, files):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    return extract_python(capture_snapshot(root, SnapshotSpec(base=head, head=head)))


def target(result, text, path="service.py"):
    found = [
        item.target
        for item in result.analysis.calls
        if item.side == HEAD and item.path == path and item.expression == text
    ]
    assert len(found) == 1, sorted({item.expression for item in result.analysis.calls})
    return found[0]


def test_method_on_self_is_a_candidate_for_the_same_class(source_repo):
    result = analyze(source_repo, {"service.py": SERVICE, "repo.py": REPO})
    validated = target(result, "self.validate(report)")
    assert (validated.status, validated.targets) == ("candidate", ("service.py#Service.validate",))
    # A name assigned on the instance is an attribute, even if a method could match later.
    handler = target(result, "self.handler(report)")
    assert (handler.status, handler.targets) == ("candidate", ("service.py#Service.fallback",))
    # Not defined in this class: an inherited or dynamic member stays unresolved.
    assert target(result, "self.inherited(report)").status == "unknown"


def test_instance_attribute_of_a_local_class_resolves_its_own_methods(source_repo):
    result = analyze(source_repo, {"service.py": SERVICE, "repo.py": REPO})
    saved = target(result, "self.repo.save(report)")
    assert (saved.status, saved.targets) == ("candidate", ("repo.py#Repo.save",))
    assert target(result, "self.repo.missing(report)").status == "unknown"
    # A parameter has no statically known type.
    assert target(result, "self.limit.check(report)").status == "unknown"


def test_local_instance_resolves_methods_and_its_own_call_operator(source_repo):
    result = analyze(source_repo, {"service.py": SERVICE, "repo.py": REPO})
    ran = target(result, "service.run(report)")
    assert (ran.status, ran.targets) == ("candidate", ("service.py#Service.run",))
    assert target(result, "service.absent(report)").status == "unknown"
    chained = target(result, "Repo().save(report)")
    assert (chained.status, chained.targets) == ("candidate", ("repo.py#Repo.save",))
    called = target(result, "notify(report)")
    assert (called.status, called.targets) == ("candidate", ("service.py#Notifier.__call__",))
    assert target(result, "plain(report)").status == "unknown"
    constructed = target(result, "Service(10)")
    assert (constructed.status, constructed.targets) == ("resolved", ("service.py#Service",))


def test_no_call_target_keeps_an_instance_placeholder(source_repo):
    result = analyze(source_repo, {"service.py": SERVICE, "repo.py": REPO})
    targets = [item for call in result.analysis.calls for item in call.target.targets]
    assert targets and not any(item.startswith("instance:") for item in targets)
    facts = python_facts(result)
    internal = {
        fact.text: fact.boundary
        for fact in facts.facts
        if fact.side == HEAD and fact.kind == "call"
    }
    assert internal["self.repo.save(report)"] == "internal"
    assert internal["plain(report)"] == "unknown"


BARE = """from service import Notifier


def test_send():
    made = object.__new__(Notifier)
    assert made.send(1) == 1


def test_send_again():
    other = Notifier.__new__(Notifier)
    other.send(2)
    unknown = object.__new__(pick())
    unknown.send(3)
"""


def test_an_object_made_without_its_initializer_is_still_an_instance(source_repo):
    files = {"service.py": SERVICE, "repo.py": REPO, "tests/test_bare.py": BARE}
    result = analyze(source_repo, files)
    for text in ("made.send(1)", "other.send(2)"):
        sent = target(result, text, "tests/test_bare.py")
        assert (sent.status, sent.targets) == ("candidate", ("service.py#Notifier.send",))
    # Which class is made has to be readable from the argument.
    assert target(result, "unknown.send(3)", "tests/test_bare.py").status == "unknown"
    # So a test written this way is linked to the method it calls.
    tests = {item.symbol_id: item for item in python_facts(result).tests if item.side == HEAD}
    assert "service.py#Notifier.send" in tests["tests/test_bare.py#test_send"].called_symbol_ids

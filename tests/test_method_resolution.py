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


CASES = """import unittest
from unittest import IsolatedAsyncioTestCase

from service import Notifier, Service

FLAG = True


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.service = Service(10)

    def test_run(self):
        self.service.run(1)


class InheritedCase(ServiceCase):
    def test_inherited(self):
        self.service.run(2)


class ReplacedCase(ServiceCase):
    def setUp(self):
        self.service = Notifier()

    def test_replaced(self):
        self.service.send(3)


class AsyncCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = Service(10)

    async def test_async(self):
        self.service.run(4)


class ReassignedCase(unittest.TestCase):
    def setUp(self):
        self.service = Service(10)

    def test_reassigns(self):
        self.service = None

    def test_reassigned(self):
        self.service.run(5)


class ConditionalCase(unittest.TestCase):
    def setUp(self):
        if FLAG:
            self.service = Service(10)

    def test_conditional(self):
        self.service.run(6)


class NotACase:
    def setUp(self):
        self.service = Service(10)

    def test_not_a_case(self):
        self.service.run(7)


class ServiceMixin:
    def setUp(self):
        self.service = Service(10)


class MixedCase(ServiceMixin, unittest.TestCase):
    def test_mixed(self):
        self.service.run(8)
"""


def test_what_set_up_assigns_is_an_instance_attribute_of_a_test_case(source_repo):
    files = {"service.py": SERVICE, "repo.py": REPO, "tests/test_cases.py": CASES}
    result = analyze(source_repo, files)
    for text, expected in (
        ("self.service.run(1)", "service.py#Service.run"),
        # setUp inherited from a TestCase base written in the repository.
        ("self.service.run(2)", "service.py#Service.run"),
        # A subclass's own setUp comes first.
        ("self.service.send(3)", "service.py#Notifier.send"),
        ("self.service.run(4)", "service.py#Service.run"),
    ):
        found = target(result, text, "tests/test_cases.py")
        assert (found.status, found.targets) == ("candidate", (expected,)), text
    # Assigned twice, under a condition, by a setUp unittest never runs, or by a mixin's
    # setUp that unittest runs only if the mixin comes before TestCase: still unknown.
    for text in (
        "self.service.run(5)",
        "self.service.run(6)",
        "self.service.run(7)",
        "self.service.run(8)",
    ):
        assert target(result, text, "tests/test_cases.py").status == "unknown", text
    # So the test is linked to the method it calls.
    tests = {item.symbol_id: item for item in python_facts(result).tests if item.side == HEAD}
    called = tests["tests/test_cases.py#ServiceCase.test_run"].called_symbol_ids
    assert "service.py#Service.run" in called

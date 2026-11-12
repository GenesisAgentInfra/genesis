"""Receivers are resolved from what the source declares about them, always as candidates."""

import pytest
from genesis_ci.business_map.python_facts import python_facts
from genesis_ci.git_snapshot import capture_snapshot
from genesis_ci.python import extract_python
from genesis_contracts.models import EvidenceSide
from genesis_contracts.snapshot import SnapshotSpec
from test_git_snapshot import commit, write

HEAD = EvidenceSide.head

SERVICES = """from __future__ import annotations

from typing import Optional

from store import Store


class Mailer:
    def send(self, report):
        return report


class ReportService:
    limit: Limits
    fallback: Mailer = None

    def __init__(self, store: Store, mailer: Optional[Mailer] = None, audit=None):
        self.store = store
        self.mailer = mailer or Mailer()
        self.audit = audit
        self.cache: Cache = build_cache()

    @classmethod
    def build(cls) -> "ReportService":
        cls.check()
        return cls(Store())

    @classmethod
    def check(cls):
        return True

    @property
    def backup(self) -> Store:
        return Store()

    def submit(self, report):
        self.store.save(report)
        self.mailer.send(report)
        self.audit.record(report)
        self.cache.put(report)
        self.limit.allows(report)
        self.fallback.send(report)
        self.backup.save(report)
        return report


class Limits:
    def allows(self, report):
        return True


class Cache:
    def put(self, report):
        return report


def build_cache():
    return Cache()
"""
STORE = """class Store:
    def save(self, report):
        return report

    def close(self):
        return None
"""
API = """from contextlib import contextmanager
from typing import Annotated, Iterator, Optional, Union

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services import Mailer, ReportService
from store import Store

router = APIRouter()


def get_service() -> ReportService:
    return ReportService.build()


def get_store() -> Iterator[Store]:
    store = Store()
    yield store
    store.close()


async def load_service() -> ReportService:
    return ReportService.build()


def untyped():
    return ReportService.build()


@contextmanager
def open_store() -> Iterator[Store]:
    yield Store()


@router.post("/reports")
def create(
    report: dict,
    name: str,
    service: ReportService = Depends(get_service),
    store=Depends(get_store),
    mailer=Depends(Mailer),
    either: Union[Store, Mailer, None] = None,
    later: "Optional[Store]" = None,
    wrapped: Annotated[Store, Depends(get_store)] = None,
    db: Session = Depends(),
    client: httpx.Client | None = None,
    kind: type[Store] = Store,
    plain=None,
):
    service.submit(report)
    store.save(report)
    mailer.send(report)
    either.save(report)
    later.save(report)
    wrapped.save(report)
    db.add(report)
    client.post("/hook")
    kind.save(report)
    plain.save(report)
    report.get("id")
    name.strip()
    name.missing()
    service.store.save(report)
    service.absent(report)


async def background(report):
    made = get_service()
    made.submit(report)
    waited = await load_service()
    waited.submit(report)
    pending = load_service()
    pending.submit(report)
    guessed = untyped()
    guessed.submit(report)
    typed: ReportService = untyped()
    typed.submit(report)
    with open_store() as opened:
        opened.save(report)
    get_service().submit(report)
"""


def analyze(root, files):
    for path, text in files.items():
        write(root, path, text)
    head = commit(root)
    return extract_python(capture_snapshot(root, SnapshotSpec(base=head, head=head)))


@pytest.fixture
def result(source_repo):
    return analyze(source_repo, {"services.py": SERVICES, "store.py": STORE, "api.py": API})


def target(result, text, path="api.py"):
    found = [
        item.target
        for item in result.analysis.calls
        if item.side == HEAD and item.path == path and item.expression == text
    ]
    assert found, sorted({item.expression for item in result.analysis.calls if item.path == path})
    assert len({item.targets for item in found}) == 1, found
    return found[0]


def test_an_annotated_parameter_reaches_the_methods_of_its_class(result):
    submitted = target(result, "service.submit(report)")
    assert submitted.status == "candidate" and submitted.reason
    assert submitted.targets == ("services.py#ReportService.submit",)
    # A method the class does not define itself stays unknown, as does an untyped parameter.
    assert target(result, "service.absent(report)").status == "unknown"
    assert target(result, "plain.save(report)").status == "unknown"


def test_annotation_wrappers_and_forward_references_are_seen_through(result):
    both = target(result, "either.save(report)")
    assert (both.status, both.targets) == ("candidate", ("store.py#Store.save",))
    assert target(result, "later.save(report)").targets == ("store.py#Store.save",)
    assert target(result, "wrapped.save(report)").targets == ("store.py#Store.save",)
    # `type[Store]` is the class, whose own functions are looked up directly.
    assert target(result, "kind.save(report)").targets == ("store.py#Store.save",)


def test_a_dependency_without_annotation_takes_what_its_provider_makes(result):
    yielded = target(result, "store.save(report)")
    assert (yielded.status, yielded.targets) == ("candidate", ("store.py#Store.save",))
    assert target(result, "mailer.send(report)").targets == ("services.py#Mailer.send",)


def test_external_and_builtin_types_give_external_and_builtin_calls(result):
    added = target(result, "db.add(report)")
    assert (added.status, added.targets) == ("candidate", ("external:sqlalchemy.orm.Session.add",))
    assert target(result, 'client.post("/hook")').targets == ("external:httpx.Client.post",)
    assert target(result, 'report.get("id")').targets == ("builtin:dict.get",)
    assert target(result, "name.strip()").targets == ("builtin:str.strip",)
    assert target(result, "name.missing()").status == "unknown"
    boundaries = {
        fact.text: fact.boundary.value
        for fact in python_facts(result).facts
        if fact.side == HEAD and fact.kind == "call" and fact.symbol_id == "api.py#create"
    }
    assert boundaries["service.submit(report)"] == "internal"
    assert boundaries["db.add(report)"] == "external"
    assert boundaries["name.strip()"] == "builtin"
    assert boundaries["plain.save(report)"] == "unknown"


def test_a_return_annotation_types_the_result_of_a_call(result):
    for text in ("made.submit(report)", "waited.submit(report)", "get_service().submit(report)"):
        made = target(result, text)
        assert (made.status, made.targets) == (
            "candidate",
            ("services.py#ReportService.submit",),
        ), text
    # A coroutine that is not awaited is not the object it will produce.
    assert target(result, "pending.submit(report)").status == "unknown"
    assert target(result, "guessed.submit(report)").status == "unknown"
    # A variable annotation stands in when the value says nothing.
    assert target(result, "typed.submit(report)").targets == ("services.py#ReportService.submit",)
    # A generator used as a context manager binds what it yields.
    assert target(result, "opened.save(report)").targets == ("store.py#Store.save",)


def test_constructor_injection_carries_the_type_onto_the_instance(result):
    def member(text):
        return target(result, text, "services.py")

    assert member("self.store.save(report)").targets == ("store.py#Store.save",)
    # `mailer or Mailer()`: both sides are the same class here.
    assert member("self.mailer.send(report)").targets == ("services.py#Mailer.send",)
    assert member("self.audit.record(report)").status == "unknown"
    # The value is an untyped call, so the declared attribute type is used.
    assert member("self.cache.put(report)").targets == ("services.py#Cache.put",)
    # Attributes declared in the class body, one of them a class defined further down.
    assert member("self.limit.allows(report)").targets == ("services.py#Limits.allows",)
    assert member("self.fallback.send(report)").targets == ("services.py#Mailer.send",)
    # A property yields what it is annotated to return.
    assert member("self.backup.save(report)").targets == ("store.py#Store.save",)
    # The same attribute reached through another object.
    assert target(result, "service.store.save(report)").targets == ("store.py#Store.save",)


def test_cls_is_the_class_the_method_is_written_in(result):
    checked = target(result, "cls.check()", "services.py")
    assert (checked.status, checked.targets) == ("candidate", ("services.py#ReportService.check",))
    built = target(result, "cls(Store())", "services.py")
    assert (built.status, built.targets) == ("candidate", ("services.py#ReportService",))
    # Reached through the class name, the factory's result is typed by its own annotation.
    assert target(result, "ReportService.build()").targets == ("services.py#ReportService.build",)


def test_no_call_target_keeps_a_placeholder(result):
    targets = [item for call in result.analysis.calls for item in call.target.targets]
    assert not [item for item in targets if item.startswith("instance:")]


def test_a_reassigned_parameter_may_hold_either_value(source_repo):
    result = analyze(
        source_repo,
        {
            "store.py": STORE,
            "app.py": """from store import Store


class Memory:
    def save(self, report):
        return report


def run(report, store: Store = None, other=None):
    store = store or Memory()
    store.save(report)
    other = other or Memory()
    other.save(report)
""",
        },
    )
    saved = target(result, "store.save(report)", "app.py")
    assert saved.targets == ("app.py#Memory.save", "store.py#Store.save")
    assert target(result, "other.save(report)", "app.py").targets == ("app.py#Memory.save",)


def test_a_cycle_of_declarations_ends(source_repo):
    result = analyze(
        source_repo,
        {
            "app.py": """class Node:
    def __init__(self, parent: "Node"):
        self.parent = parent.parent

    def walk(self):
        return self.parent.walk()


def first() -> "second":
    return second()


def second() -> first:
    return first()


def run():
    return first().walk()
""",
        },
    )
    assert target(result, "self.parent.walk()", "app.py").status == "unknown"
    assert target(result, "first().walk()", "app.py").status == "unknown"


BASES = """import logging

from store import Store

logger = logging.getLogger(__name__)


class Sender:
    def send(self, report):
        return report

    def close(self):
        return None

    @classmethod
    def default(cls):
        return cls()


class Audited:
    def record(self, report):
        return report

    def close(self):
        return "audited"


class EmailSender(Sender, Audited):
    def __init__(self):
        super().__init__()
        self.store = Store()

    def deliver(self, report):
        self.send(report)
        self.record(report)
        self.close()
        self.missing(report)
        logger.info("sent")
        return super().send(report)

    @classmethod
    def make(cls):
        return cls.default()


class External(Exception):
    def explain(self):
        return self.with_traceback(None)


def run(sender: EmailSender, report):
    sender.send(report)
    sender.record(report)
    sender.store.save(report)
    sender.missing(report)
"""


def test_a_member_the_class_does_not_define_is_looked_up_in_its_bases(source_repo):
    result = analyze(source_repo, {"store.py": STORE, "senders.py": BASES})

    def member(text):
        return target(result, text, "senders.py")

    for text in ("self.send(report)", "sender.send(report)", "super().send(report)"):
        sent = member(text)
        assert (sent.status, sent.targets) == ("candidate", ("senders.py#Sender.send",)), text
    assert member("self.record(report)").targets == ("senders.py#Audited.record",)
    assert member("sender.record(report)").targets == ("senders.py#Audited.record",)
    # Both bases define it; the one listed first is taken.
    assert member("self.close()").targets == ("senders.py#Sender.close",)
    assert member("cls.default()").targets == ("senders.py#Sender.default",)
    # Its own attribute still comes from the class itself.
    assert member("sender.store.save(report)").targets == ("store.py#Store.save",)
    # No captured base defines these, and a base outside the code is not searched.
    assert member("self.missing(report)").status == "unknown"
    assert member("sender.missing(report)").status == "unknown"
    assert member("self.with_traceback(None)").status == "unknown"
    assert member("super().__init__()").status == "unknown"


def test_a_module_logger_is_a_library_object(source_repo):
    result = analyze(source_repo, {"store.py": STORE, "senders.py": BASES})
    logged = target(result, 'logger.info("sent")', "senders.py")
    assert (logged.status, logged.targets) == ("candidate", ("external:logging.Logger.info",))

"""Read bounded, repository-scoped GitHub intent before A1 freezes its inputs.

Only GitHub's closingIssuesReferences metadata establishes an issue association.
PR prose is never parsed for arbitrary URLs or issue numbers. Callers supply a
repository-scoped read-only token; fork and privileged PR events never use it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from genesis_contracts.models import EvidenceSide, Limitation, LocalAnalysis, validate_repo_path
from genesis_contracts.validation import validate_local_analysis

from .intent import IntentSource, is_canonical_ci_origin
from .source_snapshot import FrozenSourceSnapshot

API_ORIGIN = "https://api.github.com"
MAX_ISSUES = 8
MAX_TEXT_BYTES = 120_000
MAX_TOTAL_TEXT_BYTES = 240_000
MAX_RESPONSE_BYTES = 262_144
READ_DEADLINE_SECONDS = 15

_NOTICES = {
    "ci_issue_fetch_skipped": "Linked issues were not fetched for a fork, privileged or unverified PR event.",
    "ci_issue_token_missing": "Linked issues were not fetched: a repository-scoped GitHub read token is missing.",
    "ci_issue_api_unsupported": "Linked issues were not fetched: only the trusted api.github.com origin is supported.",
    "ci_issue_access_unavailable": "Linked issues could not be read; verify repository-scoped pull-request and issues read permissions.",
    "ci_issue_fetch_failed": "Linked issue retrieval failed or timed out; PR text and local analysis remain available.",
    "ci_issue_response_invalid": "GitHub returned invalid linked-issue metadata; unsupported content was omitted.",
    "ci_issue_response_over_budget": "Linked issue retrieval exceeded its response or text budget; omitted issues remain unknown.",
    "ci_issue_count_limited": "Linked issue retrieval stopped at eight issues; further linked issues were not analyzed.",
    "ci_issue_cross_repository": "A linked issue belongs to another repository and was not fetched with this repository's token.",
    "ci_pr_text_omitted": "PR text exceeded the supported text budget or was not valid text.",
    "ci_intent_metadata_invalid": "Frozen CI intent metadata is missing or invalid; linked-issue completeness is unknown.",
}

_CLOSING_QUERY = """query GenesisClosingIssues($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequest(number: $number) {
      number
      closingIssuesReferences(first: 8) {
        nodes { number repository { nameWithOwner } }
        pageInfo { hasNextPage }
      }
    }
  }
}"""


@dataclass(frozen=True)
class CIIntentText:
    source_type: Literal["task", "pr_description"]
    text: str
    origin: str


@dataclass(frozen=True)
class CIIntentBundle:
    sources: tuple[CIIntentText, ...] = ()
    limitations: tuple[Limitation, ...] = ()


@dataclass(frozen=True)
class CIIntentFiles:
    sources: tuple[IntentSource, ...]
    metadata_path: str


class _ReadFailure(Exception):
    def __init__(self, code: str):
        self.code = code


def _notice(code: str) -> Limitation:
    return Limitation(code=code, message=_NOTICES[code], affects_completeness=True)


def _valid_repository(value: object) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", value)
    )


def _valid_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return len(value.encode()) <= MAX_TEXT_BYTES
    except UnicodeError:
        return False


def _json_request(client, method, path, deadline, *, payload=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _ReadFailure("ci_issue_fetch_failed")
    with client.stream(
        method, API_ORIGIN + path, json=payload, timeout=min(3, remaining)
    ) as response:
        if response.status_code in {401, 403, 404}:
            raise _ReadFailure("ci_issue_access_unavailable")
        if response.status_code != 200:
            raise _ReadFailure("ci_issue_fetch_failed")
        # Read raw uncompressed bytes to bound both memory and decompression work.
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise _ReadFailure("ci_issue_response_invalid")
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise _ReadFailure("ci_issue_response_over_budget")
            if time.monotonic() >= deadline:
                raise _ReadFailure("ci_issue_fetch_failed")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise _ReadFailure("ci_issue_response_invalid")
        return value


def collect_ci_intents(
    event: dict,
    *,
    repository: str,
    event_name: str,
    token: str | None,
    api_url: str = API_ORIGIN,
    transport=None,
) -> CIIntentBundle:
    """Return source text and fixed notices; never log tokens, API bodies or exceptions.

    Repository and event name must come from trusted runner configuration. Only
    same-repository pull_request/review events may fetch. Requests use one fixed
    HTTPS origin, no redirects/proxies, at most nine calls and bounded bodies.
    """
    pr = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pr, dict):
        return CIIntentBundle(
            limitations=(_notice("ci_issue_fetch_skipped"),)
            if event_name.startswith("pull_request")
            else ()
        )
    sources, notices = [], []
    number = pr.get("number", event.get("number"))
    valid_number = type(number) is int and 0 < number < 2**31
    origin = (
        f"https://github.com/{repository}/pull/{number}"
        if _valid_repository(repository) and valid_number
        else "GitHub pull request event"
    )
    body = pr.get("body")
    if body is not None:
        if not _valid_text(body):
            notices.append(_notice("ci_pr_text_omitted"))
        elif body.strip():
            sources.append(CIIntentText("pr_description", body, origin))

    def finish(code=None):
        if code:
            notices.append(_notice(code))
        return CIIntentBundle(tuple(sources), tuple(dict.fromkeys(notices)))

    try:
        safe_event = (
            _valid_repository(repository)
            and valid_number
            and event_name in {"pull_request", "pull_request_review", "pull_request_review_comment"}
            and event["repository"]["full_name"].casefold() == repository.casefold()
            and pr["base"]["repo"]["full_name"].casefold() == repository.casefold()
            and pr["head"]["repo"]["full_name"].casefold() == repository.casefold()
        )
    except (KeyError, TypeError, AttributeError):
        safe_event = False
    if not safe_event:
        return finish("ci_issue_fetch_skipped")
    if api_url != API_ORIGIN:
        return finish("ci_issue_api_unsupported")
    if not token or not token.isascii() or any(c.isspace() for c in token) or len(token) > 4096:
        return finish("ci_issue_token_missing")
    deadline = time.monotonic() + READ_DEADLINE_SECONDS
    owner, name = repository.split("/")
    try:
        with httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ) as client:
            value = _json_request(
                client,
                "POST",
                "/graphql",
                deadline,
                payload={
                    "query": _CLOSING_QUERY,
                    "variables": {"owner": owner, "name": name, "number": number},
                },
            )
            if value.get("errors"):
                return finish("ci_issue_access_unavailable")
            result = value["data"]["repository"]
            pull = result["pullRequest"]
            if (
                result["nameWithOwner"].casefold() != repository.casefold()
                or pull["number"] != number
            ):
                return finish("ci_issue_response_invalid")
            closing = pull["closingIssuesReferences"]
            nodes, more = closing["nodes"], closing["pageInfo"]["hasNextPage"]
            if not isinstance(nodes, list) or type(more) is not bool:
                return finish("ci_issue_response_invalid")
            if more or len(nodes) > MAX_ISSUES:
                notices.append(_notice("ci_issue_count_limited"))
            seen = set()
            total = sum(len(source.text.encode()) for source in sources)
            for node in nodes[:MAX_ISSUES]:
                if node["repository"]["nameWithOwner"].casefold() != repository.casefold():
                    notices.append(_notice("ci_issue_cross_repository"))
                    continue
                issue_number = node["number"]
                if type(issue_number) is not int or not 0 < issue_number < 2**31:
                    return finish("ci_issue_response_invalid")
                if issue_number in seen:
                    continue
                seen.add(issue_number)
                path = f"/repos/{repository}/issues/{issue_number}"
                issue = _json_request(client, "GET", path, deadline)
                issue_origin = f"https://github.com/{repository}/issues/{issue_number}"
                if (
                    issue.get("number") != issue_number
                    or "pull_request" in issue
                    or issue.get("url", "").casefold() != (API_ORIGIN + path).casefold()
                    or issue.get("html_url", "").casefold() != issue_origin.casefold()
                    or issue.get("repository_url", "").casefold()
                    != f"{API_ORIGIN}/repos/{repository}".casefold()
                ):
                    return finish("ci_issue_response_invalid")
                title, text = issue["title"], issue.get("body")
                if text is None:
                    text = ""
                if not isinstance(title, str) or not isinstance(text, str):
                    return finish("ci_issue_response_invalid")
                text = title + "\n\n" + text
                size = len(text.encode())
                if size > MAX_TEXT_BYTES or total + size > MAX_TOTAL_TEXT_BYTES:
                    notices.append(_notice("ci_issue_response_over_budget"))
                    continue
                total += size
                sources.append(CIIntentText("task", text, issue_origin))
    except _ReadFailure as error:
        return finish(error.code)
    except httpx.HTTPError:
        return finish("ci_issue_fetch_failed")
    except (ValueError, TypeError, KeyError, AttributeError):
        return finish("ci_issue_response_invalid")
    return finish()


@contextmanager
def materialize_ci_intents(repo: Path, bundle: CIIntentBundle):
    """Expose private, repository-relative source files until A1 captures them.

    The caller must capture sources plus metadata_path as SnapshotInput(kind=intent)
    inside this context, or run the CLI synchronously while these files exist.
    Only sources become --task/--pr-description; metadata is never user intent.
    """
    codes = tuple(dict.fromkeys(item.code for item in bundle.limitations))
    if set(codes) - _NOTICES.keys() or len(bundle.sources) > MAX_ISSUES + 1:
        raise ValueError("Invalid CI intent bundle")
    root = repo.resolve()
    with tempfile.TemporaryDirectory(prefix="genesis-ci-intent-", dir=root) as directory:
        folder = Path(directory)

        def write(name, text):
            path = folder / name
            with path.open("x", encoding="utf-8") as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(text)
            return path.relative_to(root).as_posix()

        sources = []
        for index, source in enumerate(bundle.sources):
            if source.source_type not in {"task", "pr_description"}:
                raise ValueError("Invalid CI source classification")
            if not is_canonical_ci_origin(source.origin, source.source_type) and not (
                source.source_type == "pr_description"
                and source.origin == "GitHub pull request event"
            ):
                raise ValueError("Invalid CI source origin")
            if len(source.text.encode()) > MAX_TEXT_BYTES:
                raise ValueError("CI source exceeds text limit")
            path = write(f"source-{index}.md", f"# Source: {source.origin}\n\n{source.text}\n")
            sources.append(IntentSource(path, source.source_type))
        metadata_path = write(
            "collection.json", json.dumps({"version": 1, "limitation_codes": codes}) + "\n"
        )
        yield CIIntentFiles(tuple(sources), metadata_path)


def apply_ci_intent_metadata(
    local: LocalAnalysis, source: FrozenSourceSnapshot, path: str
) -> LocalAnalysis:
    """Apply allowlisted notices exclusively from the captured metadata bytes."""
    try:
        validate_repo_path(path)
        if source.manifest != local.snapshot:
            raise ValueError("CI metadata snapshot differs")
        if not any(
            item.side == EvidenceSide.head and item.path == path and item.kind == "intent"
            for item in source.manifest.files
        ):
            raise ValueError("CI metadata was not frozen")
        text = source.read_text(EvidenceSide.head, path)
        if len(text.encode()) > 16_384:
            raise ValueError("CI metadata exceeds limit")
        metadata = json.loads(text)
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"version", "limitation_codes"}
            or type(metadata["version"]) is not int
            or metadata["version"] != 1
            or not isinstance(metadata["limitation_codes"], list)
            or len(metadata["limitation_codes"]) > len(_NOTICES)
            or any(
                type(code) is not str or code not in _NOTICES
                for code in metadata["limitation_codes"]
            )
        ):
            raise ValueError("CI metadata is invalid")
        notices = tuple(_notice(code) for code in metadata["limitation_codes"])
    except (ValueError, KeyError, TypeError):
        notices = (_notice("ci_intent_metadata_invalid"),)
    updated = local.model_copy(
        update={"limitations": tuple(dict.fromkeys((*local.limitations, *notices)))}
    )
    validate_local_analysis(updated)
    return updated

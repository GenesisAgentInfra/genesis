"""Conservative, shared outbound-content exclusions (never executes input)."""

from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"(?<![A-Za-z0-9_-])gci_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
    re.compile(
        r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"
    ),
    re.compile(
        r"(?i)\b(?:[A-Za-z0-9_]*[_-])?(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?(?:access[_-]?)?key|client[_-]?secret|password)\b[\"']?\s*[:=]\s*[\"']?([^\s\"',;}{]{4,})"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:/]+:[^\s@]+@"),
)
_PLACEHOLDERS = {"none", "null", "false", "true", "redacted", "changeme", "example", "placeholder"}


def normalized_path(value: str) -> str:
    """Normalize separators without reading or resolving the working directory."""
    return str(PurePosixPath(value.replace("\\", "/"))).removeprefix("./")


def excluded_path(value: str, exclude: Iterable[str] = ()) -> bool:
    path = normalized_path(value).split("#", 1)[0]
    parts = PurePosixPath(path).parts
    name = PurePosixPath(path).name.lower()
    if any(part in {".git", ".ssh"} for part in parts):
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if name in {
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials",
        ".netrc",
        ".npmrc",
        ".pypirc",
    }:
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx", ".keystore")):
        return True
    if re.match(r"(?:secrets?|credentials?)(?:[._-]|$)", name):
        return True
    for raw in exclude:
        pattern = normalized_path(str(raw)).rstrip("/")
        if not pattern:
            continue
        # A directory exclusion matches itself and descendants, at any depth
        # for a bare directory name; patterns also support ordinary globs.
        if path == pattern or path.startswith(pattern + "/") or fnmatch.fnmatchcase(path, pattern):
            return True
        # CLI file arguments can be absolute while configured exclusions are
        # repository-relative. Apply relative globs at component boundaries
        # before portable input names discard the original host path.
        if not pattern.startswith("/") and fnmatch.fnmatchcase(path, "*/" + pattern):
            return True
        if not pattern.startswith("/") and ("/" + pattern + "/") in ("/" + path + "/"):
            return True
        if "/" not in pattern and any(fnmatch.fnmatchcase(part, pattern) for part in parts):
            return True
        if pattern.endswith("/**") and path == pattern[:-3]:
            return True
    return False


def contains_secret(text: str) -> bool:
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if match.lastindex:
                value = match.group(1).lower()
                if value in _PLACEHOLDERS or value.startswith(
                    ("${", "os.environ", "os.getenv", "process.env", "getenv(")
                ):
                    continue
            return True
    return False


def unsafe_value(value: Any, exclude: Iterable[str] = ()) -> bool:
    """Check entire objects, including derived facts and their textual fields."""
    patterns = tuple(exclude)
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, str):
        if contains_secret(value):
            return True
        # Paths can occur inside statements, symbols, graph edges and notes,
        # not just in a field named `file`.
        words = re.split(r"[\s`\"'<>()\[\]{},;]+", value)
        return any(excluded_path(word.rstrip(".:"), patterns) for word in words if word)
    if isinstance(value, dict):
        return any(unsafe_value(item, patterns) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(unsafe_value(item, patterns) for item in value)
    return False


def evidence_ids(value: Any) -> set[str]:
    """Collect reference IDs, including nested references and source snippets."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("evidence_ids") and isinstance(item, list):
                result.update(str(entry) for entry in item)
            elif key == "evidence_id" and isinstance(item, str):
                result.add(item)
            else:
                result.update(evidence_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.update(evidence_ids(item))
    return result

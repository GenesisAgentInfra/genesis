"""Load explicit reviewer goals separately from frozen business-intent inputs."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from genesis_contracts.models import ReviewDirectives

from .context.filters import contains_secret, excluded_path

MAX_REVIEW_REQUEST_BYTES = 262144


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate review request key")
        result[key] = value
    return result


def load_review_request(path: Path) -> ReviewDirectives:
    """Reject unsafe or ambiguous input without echoing document content."""
    try:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("Symlinked review request")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REVIEW_REQUEST_BYTES:
                raise ValueError("Review request must be a bounded regular file")
            raw = stream.read(MAX_REVIEW_REQUEST_BYTES + 1)
        if len(raw) > MAX_REVIEW_REQUEST_BYTES:
            raise ValueError("Review request exceeds byte limit")
        review = ReviewDirectives.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
        if any(
            contains_secret(doc.text) or contains_secret(doc.path) or excluded_path(doc.path)
            for doc in review.documents
        ):
            raise ValueError("Review request contains suspected credentials or excluded paths")
        return review
    except (OSError, ValueError, UnicodeError):
        raise ValueError(
            "Invalid review request; check format, hashes, bounds and content policy"
        ) from None

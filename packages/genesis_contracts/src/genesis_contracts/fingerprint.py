"""Position-independent identity for static facts.

A fingerprint identifies a fact by what it is, not by where it sits in a file. It
survives line shifts and unrelated edits, so the same fact can be matched across
snapshots. Line and column positions and the snapshot identity never take part.
"""

import hashlib

FINGERPRINT_PATTERN = r"^fp_[0-9a-f]{24}$"


def fact_fingerprint(*, symbol: str, kind: str, text: str, ordinal: int = 0) -> str:
    """Fingerprint one fact inside its owning symbol.

    `symbol` is the repository-relative symbol identity (`path#qualified.name`); it
    must not depend on the working directory or on the list of files passed in.
    `kind` is the fact kind, such as `condition` or `call`. `text` is the canonical
    expression text: the language adapter is responsible for rendering it the same
    way regardless of formatting, without altering string literal contents.
    `ordinal` separates repeated facts with the same kind and text inside one
    symbol, counted in source order from zero.
    """
    if not symbol or not kind:
        raise ValueError("a fingerprint needs an owning symbol and a fact kind")
    if ordinal < 0:
        raise ValueError("fingerprint ordinal must not be negative")
    identity = "\0".join((symbol, kind, text.strip(), str(ordinal)))
    return "fp_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

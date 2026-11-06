"""Shared offline o200k estimate for bounded review admission.

This encoding is an explicit budgeting estimate for configurable providers, not
a claim that arbitrary model IDs use this tokenizer and never a billing count.
"""

import base64
import gzip
import hashlib
import json
from functools import lru_cache
from importlib.metadata import version
from importlib.resources import files

import tiktoken

VERSION = "0.14.0"
ASSET_HASH = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"


@lru_cache(maxsize=1)
def encoding():
    if version("tiktoken") != VERSION:
        raise ValueError("Unexpected tokenizer version")
    assets = files("genesis_tokenizer").joinpath("assets")
    raw = gzip.decompress(assets.joinpath("o200k_base.tiktoken.gz").read_bytes())
    if hashlib.sha256(raw).hexdigest() != ASSET_HASH:
        raise ValueError("Packaged encoding integrity mismatch")
    spec = json.loads(assets.joinpath("o200k_base.json").read_text())
    if spec["asset_sha256"] != ASSET_HASH or spec["tiktoken_version"] != VERSION:
        raise ValueError("Encoding metadata mismatch")
    ranks = {
        base64.b64decode(token, validate=True): int(rank)
        for token, rank in (line.split() for line in raw.splitlines())
    }
    return tiktoken.Encoding(
        name=spec["name"],
        pat_str=spec["pat_str"],
        mergeable_ranks=ranks,
        special_tokens=spec["special_tokens"],
    )


def count_fragments(texts):
    # Literal special-token spellings are customer text, never control tokens.
    enc = encoding()
    return sum(len(enc.encode_ordinary(text)) for text in texts)

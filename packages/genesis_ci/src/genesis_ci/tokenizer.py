"""Backwards-compatible prompt measurement imports; budgeting shares the pinned encoding."""

from genesis_tokenizer import ASSET_HASH, VERSION, count_fragments, encoding

__all__ = ["ASSET_HASH", "VERSION", "MODELS", "count_fragments", "encoding"]

# Exact model mapping remains limited to the validated prompt-cost measurement route.
MODELS = frozenset({"gpt-4.1", "gpt-4.1-2025-04-14", "gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"})

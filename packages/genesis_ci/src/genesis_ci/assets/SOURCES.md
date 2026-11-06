# Offline assets

Verified 2026-11-04. No runtime downloads or price refresh.

- Encoding: https://github.com/openai/tiktoken/blob/0.14.0/tiktoken_ext/openai_public.py ; model mapping: https://github.com/openai/tiktoken/blob/0.14.0/tiktoken/model.py . Only exact GPT-4.1 / GPT-4.1 mini alias and 2025-04-14 snapshot IDs are supported. No guessed model prefixes.
- BPE bytes: https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken ; decompressed SHA-256 446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d. Packaged compressed with deterministic mtime=0. MIT license included in TIKTOKEN_LICENSE.txt.
- Standard uncached text input/output prices: https://developers.openai.com/api/docs/models/gpt-4.1 and https://developers.openai.com/api/docs/models/gpt-4.1-mini . Values per million tokens: 2.00/8.00 and 0.40/1.60 USD. Snapshot IDs are listed on those model pages. Verification date is not an invented effective date; effective_from remains null.
- Prices exclude cache/batch/priority, tools and multimodal fees. This small reproducible example catalog is not a production model selection, live price claim or availability guarantee. Update manually with new revision, source verification and review; never silently rewrite an existing revision.

Tokenizer bytes, metadata and MIT license now live in the shared genesis_tokenizer package; the original hashes and exact cost-model allowlist are unchanged.

# Repository ownership

This repository owns the CLI, static analysis, context selection, report rendering,
HTTP wire contracts, shared tokenizer, coding-agent skill/setup, and composite
Action. The private service consumes a pinned revision of these packages. Do not
copy them back into the server.

`genesis_contracts` is the authoritative Python contract implementation. The
`code-intelligence-protocol` repository holds generated versioned JSON Schemas
and synthetic report examples for non-Python consumers. Request and response
shape visibility does not expose the private model prompts or analysis strategy.

No customer snapshots, personal credentials, provider adapters, semantic prompts, server
authentication, database code, or production deployment config belongs here.
Fixtures and examples in this repository are synthetic. Their fixed mock keys
are not live credentials. Never publish personal or operator Genesis keys.

The sole live-credential exception is the intentionally public, revocable shared
trial asset at `packages/genesis_ci/src/genesis_ci/assets/public-trial.json`. It
provides limited shared trial access, not administrator or model-provider access.
The public boundary audit permits only this exact file content, pinned by SHA-256;
other keys or copies in other files still fail. Rotation requires reviewing both
the dedicated asset and its audit pin. CLI defaults bind it to the official origin.

The Git history starts with the reviewed client files only.

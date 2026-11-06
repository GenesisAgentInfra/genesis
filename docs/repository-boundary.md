# Repository ownership

This repository owns the CLI, static analysis, context selection, report rendering,
HTTP wire contracts, shared tokenizer, and composite Action. The private service
consumes a pinned revision of these packages. Do not copy them back into the server.

`genesis_contracts` is the authoritative Python contract implementation. The
`code-intelligence-protocol` repository holds generated versioned JSON Schemas
and synthetic report examples for non-Python consumers. Request and response
shape visibility does not expose the private model prompts or analysis strategy.

No customer snapshots, credentials, provider adapters, semantic prompts, server
authentication, database code, or production deployment config belongs here.
Fixtures and examples in this repository are synthetic. Their fixed mock keys
are not live credentials. Never publish real Genesis keys.

The Git history starts with the reviewed client files only.

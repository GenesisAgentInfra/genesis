# Development

The repository has two parts: the Python CLI (`packages/`) and the viewer page it
renders (`viewer/`).

## CLI

Use Python 3.12 and uv 0.13.7.

```sh
uv sync --all-packages --group dev --frozen
uv run --all-packages --frozen pytest -q
uv run --all-packages --frozen ruff check packages scripts tests
uv run --all-packages --frozen ruff format --check packages scripts tests
uv run --all-packages --frozen python scripts/check_public_boundary.py
uv run --all-packages --frozen python scripts/build_map_fixtures.py
uv build --package genesis-ci --wheel
uv build --package genesis-contracts --wheel
uv run --all-packages --frozen python scripts/check_packages.py
```

Tests build small synthetic Git repositories. They need no key, no model, no network
and no access to private source. Analyzed source is read as text and never imported
or executed; keep it that way.

The Python contracts in `packages/genesis_contracts` are authoritative for the files
the CLI reads and writes. `fixtures/business-map/` holds one worked example of each;
`scripts/build_map_fixtures.py` regenerates it, and CI fails when the result differs
from what is committed.

The bundled agent skill lives in
`packages/genesis_ci/src/genesis_ci/assets/skills/genesis/`. Edit that source, not an
installed copy under a user's home; `agent_setup.py` installs it. Keep the skill text
and the CLI's commands aligned.

## Viewer

See [viewer/README.md](viewer/README.md). `npm run build` writes the page into
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`; commit the built file
together with the source change that produced it.

## Licenses

Original contributions are provided under Apache-2.0; see LICENSE and NOTICE. Each
package directory carries a copy of both, checked by `scripts/check_packages.py`.
When a dependency bundled into the viewer page changes, update
THIRD_PARTY_NOTICES.md.

## Documentation language

Write `README.md`, `AGENTS.md`, the guides in `docs/`, this file and the bundled skill
in English. `README.zh-CN.md` and the `docs/*.zh-CN.md` files carry the same content in
Chinese; keep commands, paths and field names unchanged in them.

People hand installation and use to their coding agent, so the documents are written
for an agent to follow as well as for a person to read: `docs/install.md` from a clean
machine to a working skill, `docs/usage.md` for what to ask and where the result is,
and `AGENTS.md` for an agent that opens this repository. When an install command, a
flag, an output path or an error message changes, change these with it;
`tests/test_docs.py` checks the parts that can be checked.

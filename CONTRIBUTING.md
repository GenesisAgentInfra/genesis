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

Write `README.md`, this file and the bundled skill in English. `README.zh-CN.md`
carries the same content in Chinese; keep commands, paths and field names unchanged
in it.

# Client development

Use Python 3.12 and uv 0.13.7. This workspace contains no private service.

```sh
uv sync --all-packages --group dev --frozen
uv run --all-packages --frozen pytest -q
uv run --all-packages --frozen ruff check packages scripts tests action
uv run --all-packages --frozen ruff format --check packages scripts tests action
uv run --all-packages --frozen python scripts/evaluate_analysis.py
uv run --all-packages --frozen python scripts/check_public_boundary.py
uv build --package genesis-ci --wheel
uv build --package genesis-contracts --wheel
uv build --package genesis-tokenizer --wheel
uv run --all-packages --frozen python scripts/check_packages.py
```

Tests use synthetic repositories and scripted HTTP responses. They do not need
a Genesis key, a model key, a database or access to private source. Their success
does not establish real-model reasoning quality.

Do not consume shared trial quota in automated tests. Use mocked HTTP transports.
The only intentionally distributed live credential is the dedicated public trial
asset; its exact file hash is pinned in `scripts/check_public_boundary.py`. A
rotation must update that asset and pin together, never add an unrestricted
secret-scanner exception. See [repository ownership](docs/repository-boundary.md).

The Python contracts in `packages/genesis_contracts` are authoritative. For
protocol changes, clone the public `code-intelligence-protocol` repository beside
this one, check out `protocol-revision.txt`, and run `scripts/check_contracts.py`.
Regenerate schema/example changes with `scripts/export_public_schemas.py` and
`scripts/export_examples.py`, review both repositories, then update the pin.
The ordinary client test suite does not require the protocol checkout.

Client source, context selection, rendering and Action changes belong here.
The private service pins this repository as a submodule for shared contracts,
tokenization and compatibility tests. After a reviewed client commit, update
the private pin and run its full suite before deploying. Never edit the vendored
client checkout inside the service without contributing the change here.

Keep third-party license notices with bundled assets. Original contributions are
provided under Apache-2.0; see LICENSE and NOTICE. Changes to license notices
must also be reflected in the package copies checked by scripts/check_packages.py.

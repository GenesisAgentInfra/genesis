# Security

Please do not report a vulnerability in a public issue. Report it privately: open the
repository's Security tab and choose "Report a vulnerability", or go to
https://github.com/GenesisAgentInfra/genesis/security/advisories/new.

Say what an attacker controls, what happens, and how to reproduce it. A synthetic
example repository is the most useful proof.

## In scope

- The `genesis` CLI.
- The skill installer (`genesis agent install`), the bundled skill and its launcher,
  `scripts/run_genesis.py`.
- The pages `genesis map render` writes: `view.html`, `graph.html` and their `.share`
  copies.

For example: a repository whose content makes the CLI execute code from it, makes the
CLI write outside the project's `.genesis/` directory, makes the installer write outside
the `genesis` skill directory, or puts running script into a rendered page.

## Supported versions

There are no releases yet. Fixes land on `main`; to get one, install again from `main`
as [docs/install.md](docs/install.md) describes.

"""Fail closed on forbidden public paths/imports and common live-secret formats."""

import ast
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"genesis_ci", "genesis_contracts", "genesis_tokenizer"}
PUBLIC_TRIAL_ASSET = "packages/genesis_ci/src/genesis_ci/assets/public-trial.json"
# Deliberately public trial identity, approved for distribution. Pin the complete
# asset so adding a different key (even in this file) still fails the audit.
PUBLIC_TRIAL_SHA256 = "2b3ae09075a3ead9f3dfd3b04d5f6a99b47d0b3c3bb897da579eb8e3e9ed54db"
SECRET = re.compile(
    rb"(?:gci_[A-Za-z0-9_-]{40,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    rb"github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{32,}|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


def has_unapproved_secret(name: str, data: bytes) -> bool:
    if name == PUBLIC_TRIAL_ASSET:
        return hashlib.sha256(data).hexdigest() != PUBLIC_TRIAL_SHA256
    return bool(SECRET.search(data))


def main():
    packages = {path.name for path in (ROOT / "packages").iterdir() if path.is_dir()}
    if packages != ALLOWED:
        raise SystemExit("Unexpected package in public client")
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        text=True,
    ).split("\0")
    forbidden = {".env", "credentials.json", "pilot-key", "service.env"}
    count = 0
    for name in sorted(set(names) - {""}):
        path = ROOT / name
        if path.is_symlink():
            raise SystemExit(f"Public symlink: {name}")
        if any(part in forbidden or part.startswith(".env.") for part in path.parts):
            raise SystemExit(f"Private configuration path: {name}")
        if name.startswith(("deploy/", "packages/genesis_service/")):
            raise SystemExit(f"Private implementation path: {name}")
        data = path.read_bytes()
        if has_unapproved_secret(name, data):
            raise SystemExit(f"Potential secret in {name}; inspect locally (value redacted)")
        if path.suffix == ".py":
            for node in ast.walk(ast.parse(data, filename=name)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                if any(module.split(".")[0] == "genesis_service" for module in modules):
                    raise SystemExit(f"Private server import: {name}")
        count += 1
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    if any(p["name"] == "genesis-service" for p in lock["package"]):
        raise SystemExit("Public lockfile includes the private service")
    print(f"Audited {count} public files: package/import/path/secret checks passed")


if __name__ == "__main__":
    main()

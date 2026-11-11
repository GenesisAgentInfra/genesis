"""Invoke the installer's Genesis environment without searching the app's PATH."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    runtime = Path(__file__).resolve().parents[1] / "runtime.json"
    try:
        if runtime.is_symlink() or runtime.stat().st_size > 16384:
            raise ValueError("Invalid runtime metadata")
        data = json.loads(runtime.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format_version") != 1:
            raise ValueError("Invalid runtime metadata")
        executable = Path(data["python"])
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("Genesis environment is missing")
    except (OSError, ValueError, TypeError, KeyError):
        print(
            "Genesis skill environment is unavailable. Reinstall with genesis agent install.",
            file=sys.stderr,
        )
        return 1
    try:
        return subprocess.run(
            [str(executable), "-I", "-c", "from genesis_ci.cli import app; app()", *sys.argv[1:]],
            check=False,
        ).returncode
    except OSError:
        print(
            "Cannot start the installed Genesis environment; reinstall the skill.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

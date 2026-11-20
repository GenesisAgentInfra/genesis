"""Invoke the installer's Genesis environment without searching the app's PATH."""

import json
import subprocess
import sys
from pathlib import Path

UNAVAILABLE = (
    "Genesis skill environment is unavailable: the Python environment recorded at "
    "install time is missing. Reinstall Genesis, then run its agent install command "
    "with --update: https://github.com/GenesisAgentInfra/genesis/blob/main/docs/install.md"
)
# Run in the recorded environment; a missing package gets the same message, not a traceback.
CHILD = (
    "import sys\n"
    "try:\n"
    "    from genesis_ci.cli import app\n"
    "except ImportError:\n"
    f"    sys.stderr.write({UNAVAILABLE + chr(10)!r})\n"
    "    sys.exit(1)\n"
    "app(prog_name='genesis')\n"
)


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
        print(UNAVAILABLE, file=sys.stderr)
        return 1
    try:
        return subprocess.run(
            [str(executable), "-I", "-c", CHILD, *sys.argv[1:]], check=False
        ).returncode
    except OSError:
        print(UNAVAILABLE, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Check wheel isolation without importing the server or publishing packages."""

from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    for package in ("genesis_ci", "genesis_contracts"):
        wheels = sorted((ROOT / "dist").glob(f"{package}-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"Expected exactly one freshly built {package} wheel")
        with ZipFile(wheels[0]) as wheel:
            names = wheel.namelist()
            if any(not name.startswith((package + "/", package + "-")) for name in names):
                raise SystemExit(f"Unexpected packaged path in {wheels[0]}")
            if any("fixtures/" in name or "genesis_service/" in name for name in names):
                raise SystemExit("CLI/contracts package leaked server or fixture files")
            if package == "genesis_ci":
                required = {
                    "genesis_ci/assets/skills/genesis/SKILL.md",
                    "genesis_ci/assets/skills/genesis/agents/openai.yaml",
                    "genesis_ci/assets/skills/genesis/scripts/run_genesis.py",
                    "genesis_ci/assets/viewer/index.html",
                }
                if not required <= set(names):
                    raise SystemExit("CLI wheel lacks the agent skill or the viewer page")
            metadata = wheel.read(
                next(name for name in names if name.endswith("/METADATA"))
            ).decode()
            parsed = Parser().parsestr(metadata)
            if parsed["License-Expression"] != "Apache-2.0":
                raise SystemExit(f"Wrong license metadata in {wheels[0].name}")
            license_files = set(parsed.get_all("License-File", []))
            if not {"LICENSE", "NOTICE"} <= license_files:
                raise SystemExit("Distribution omits first-party license notices")
            for filename in ("LICENSE", "NOTICE"):
                expected = (ROOT / filename).read_bytes()
                if (ROOT / "packages" / package / filename).read_bytes() != expected:
                    raise SystemExit(f"Stale {filename} in {package}")
                suffix = ".dist-info/licenses/" + filename
                matching = [name for name in names if name.endswith(suffix)]
                if len(matching) != 1 or wheel.read(matching[0]) != expected:
                    raise SystemExit(f"Missing or changed {filename} in {package} wheel")
            dependencies = [
                line for line in metadata.splitlines() if line.startswith("Requires-Dist:")
            ]
            if any(
                any(word in line.lower() for word in ("genesis-service", "fastapi", "uvicorn"))
                for line in dependencies
            ):
                raise SystemExit("CLI/contracts package depends on server packages")
            print(f"{wheels[0].name}: {len(names)} entries; package boundary OK")


if __name__ == "__main__":
    main()

from pathlib import Path

from genesis_contracts.export_schemas import export

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT.parent / "code-intelligence-protocol" / "schemas" / "v0.1.0"


if __name__ == "__main__":
    export(DESTINATION)
    export(DESTINATION.parent / "v0.2.0", version="0.2.0")
    export(DESTINATION.parent / "v0.3.0", version="0.3.0")
    print(f"Exported public schemas to {DESTINATION}")

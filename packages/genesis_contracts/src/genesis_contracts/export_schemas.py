import json
from pathlib import Path

from .schemas import public_schemas


def export(destination: Path, *, version="0.1.0") -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename, schema in public_schemas(version).items():
        (destination / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    export(Path(__file__).resolve().parents[4] / "generated-schemas")

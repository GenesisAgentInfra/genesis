import json
from pathlib import Path

import yaml
from genesis_contracts.models import parse_analysis_response
from genesis_contracts.schemas import public_schemas
from genesis_contracts.validation import validate_public_response
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent / "code-intelligence-protocol" / "schemas" / "v0.1.0"


def main() -> None:
    expected = public_schemas()
    for filename, schema in expected.items():
        path = PUBLIC / filename
        if not path.is_file():
            raise SystemExit(f"missing public schema: {path}")
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != schema:
            raise SystemExit(
                f"public schema is stale: {filename}; run scripts/export_public_schemas.py"
            )
    validator = Draft202012Validator(expected["analysis-response.schema.json"])
    count = 0
    for schema in expected.values():
        Draft202012Validator.check_schema(schema)
    for path in sorted((ROOT / "fixtures").glob("*/report.json")):
        validator.validate(json.loads(path.read_text(encoding="utf-8")))
        public_example = PUBLIC.parent.parent / "examples" / "v0.1.0" / (path.parent.name + ".json")
        if path.read_bytes() != public_example.read_bytes():
            raise SystemExit(f"stale public example: {public_example}")
        count += 1
    flow_validator = Draft202012Validator(expected["flows.schema.json"])
    flow_validator.validate(
        yaml.safe_load(
            (
                ROOT.parent / "code-intelligence-protocol" / "examples" / "v0.1.0" / "flows.yaml"
            ).read_text(encoding="utf-8")
        )
    )
    print(f"validated {len(expected)} schemas, {count} fixture reports, and the flow example")
    for version in ("0.2.0", "0.3.0"):
        for filename, schema in public_schemas(version).items():
            actual = json.loads((PUBLIC.parent / ("v" + version) / filename).read_text())
            if actual != schema:
                raise SystemExit(f"public v{version} schema is stale: {filename}")
            Draft202012Validator.check_schema(schema)
            examples = sorted((PUBLIC.parent.parent / "examples" / ("v" + version)).glob("*.json"))
            if not examples:
                raise SystemExit(f"missing public v{version} examples")
            for example in examples:
                data = json.loads(example.read_text())
                Draft202012Validator(schema).validate(data)
                validate_public_response(parse_analysis_response(data))
    print("validated behavior comparison and execution path schemas and examples")


if __name__ == "__main__":
    main()

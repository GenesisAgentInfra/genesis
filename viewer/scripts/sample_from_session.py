"""Write a session's viewer data to a JSON file for `npm run dev`.

Usage: python scripts/sample_from_session.py <repo> <session-id> <out.json>
Run it with the Python environment of this repository (uv run ... python).
"""

import json
import sys
from pathlib import Path

from genesis_ci.business_map.session import load, load_report
from genesis_ci.business_map.view import view_payload


def main() -> None:
    repo, session, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    _, business_map, bundle = load(repo, session)
    payload = view_payload(business_map, bundle, load_report(repo, session))
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

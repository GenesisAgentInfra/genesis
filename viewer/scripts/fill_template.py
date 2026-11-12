"""Fill the built viewer with a sample payload: python scripts/fill_template.py <in.json> <out.html>."""

import json
import sys
from pathlib import Path

from genesis_ci.business_map.view import DATA_SLOT, _embed, viewer_template

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
page = viewer_template().replace(DATA_SLOT, DATA_SLOT.replace("null", _embed(payload)))
Path(sys.argv[2]).write_text(page, encoding="utf-8")
print(sys.argv[2])

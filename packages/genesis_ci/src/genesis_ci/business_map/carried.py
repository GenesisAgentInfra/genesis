"""Entries a session carries over from an earlier map, so that its flows keep their ids.

A flow's id comes from the symbols of all its entries. The entries the agent proposed
live only in the session that accepted them, so a review starts from the entries a map
was planned with, and from how that map grouped entries into flows: a flow of several
entries keeps its id only while they stay together. Then each change lands on the flow
the map gave it, as long as the flow's entries all still exist. They come from the
latest map session of the project that proposed entries of its own or gave several
entries one flow, or from a `business-map.json` named with `--entries-from`, such as a
copy committed with a spec, which every clone has.
"""

from __future__ import annotations

import json
from pathlib import Path

from genesis_contracts.business_map import BusinessMap, EntryDetection
from genesis_contracts.facts import FactSet
from genesis_contracts.models import EvidenceSide, ReferenceRange
from pydantic import ValidationError

from .loop import LoopError, pydantic_problems
from .python_entries import entry_id

CARRIED = "carried.json"
HEAD = EvidenceSide.head
SOURCES = ("from_session", "from_map")


def named_map(repo: Path, given: str | Path) -> dict:
    """The entries a `business-map.json` proposed, read from a path given by the user.

    The path is relative to the repository or absolute. A file that is not a map Genesis
    wrote is refused rather than read as no entries. The entries name a file outside the
    repository by its name alone, since a map may be committed and shared.
    """
    path = Path(given).expanduser()
    path = (path if path.is_absolute() else repo / path).resolve()
    try:
        shown = origin = path.relative_to(repo).as_posix()
    except ValueError:
        shown, origin = str(path), path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LoopError("invalid_input", f"--entries-from: cannot read {shown}.") from error
    try:
        business_map = BusinessMap.model_validate_json(text)
    except ValidationError as error:
        raise LoopError(
            "invalid_input",
            f"--entries-from: {shown} is not a business-map.json written by Genesis.",
            pydantic_problems(error),
        ) from error
    found = {}
    for flow in business_map.flows:
        for entry in flow.entries:
            if entry.detection == EntryDetection.agent_proposed:
                found.setdefault(entry.entry_id, entry.model_dump(mode="json", exclude_none=True))
    return {
        "source": {"from_map": {"path": shown, "snapshot_id": business_map.snapshot_id}},
        "origin": origin,
        "entries": list(found.values()),
        "groups": _groups(
            [entry.entry_id for entry in flow.entries] for flow in business_map.flows
        ),
        # The same map can be planned again with other entries; kept to tell them apart.
        "proposed": sorted(item["symbol_id"] for item in found.values()),
    }


def _groups(flows) -> list[list[str]]:
    """The entry ids of each flow that has more than one entry."""
    return [list(entries) for entries in flows if len(entries) > 1]


def _planned(root: Path) -> tuple[list[dict], list[list[str]]]:
    """The entries the agent added that a flow of a session's plan starts from, and the
    entries of each flow of that plan that has several.

    Those it proposed and those the session carried itself. One the plan only skipped
    is left out, as a map leaves it out of its flows.
    """
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    flows = plan["plan"].get("flows", [])
    used = {entry for flow in flows for entry in flow["entry_ids"]}
    carried = []
    if (root / CARRIED).is_file():
        carried = json.loads((root / CARRIED).read_text(encoding="utf-8")).get("entries", [])
    found = {}
    for raw in (*carried, *plan.get("proposed", [])):
        if raw["entry_id"] in used:
            found[raw["entry_id"]] = raw
    return list(found.values()), _groups(flow["entry_ids"] for flow in flows)


def latest_map(repo: Path) -> dict | None:
    """The entries the agent added in the latest map session of the project whose plan
    uses any or gives several entries one flow, and how that plan grouped entries.

    Latest by when its plan was last accepted. A later map whose plan does neither, such
    as the default plan, is passed over: it carries nothing a review lacks without it.
    """
    latest = None
    for path in (repo / ".genesis" / "sessions").glob("ses_*/plan.json"):
        root = path.parent
        try:
            session = json.loads((root / "session.json").read_text(encoding="utf-8"))
            # A session from before sessions named their engine is a Python one.
            if session.get("mode") != "map" or session.get("engine", "python") != "python":
                continue
            entries, groups = _planned(root)
            key = (path.stat().st_mtime_ns, root.name)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if (entries or groups) and (latest is None or key > latest[0]):
            latest = (key, root.name, entries, groups)
    if latest is None:
        return None
    _, origin, entries, groups = latest
    return {
        "source": {"from_session": origin},
        "origin": origin,
        "entries": entries,
        "groups": groups,
    }


def carry(found: dict, facts: FactSet, source) -> dict:
    """The entries of `found` this snapshot can start from, and those it no longer has.

    An entry is carried while its function exists at head and the analyzers do not
    recognise it. It cites the first line of the function, its first decorator if it
    has one, since evidence belongs to one snapshot; `attributes.carried_from` names
    where it came from. The groups of entries are kept as they are, and so is each entry
    no longer found, for a review to show the flow it started as removed.
    """
    symbols = {item.symbol_id: item for item in facts.symbols if item.side == HEAD}
    recognised = {
        item.symbol_id
        for item in facts.entries
        if item.side == HEAD and item.detection != EntryDetection.root_heuristic
    }
    entries, evidence, missing = [], [], []
    for raw in found["entries"]:
        symbol = symbols.get(raw["symbol_id"])
        if symbol is None or symbol.kind != "function":
            missing.append(raw)
            continue
        if symbol.symbol_id in recognised:
            continue
        line = symbol.range.start_line
        ref = source.evidence(HEAD, symbol.path, ReferenceRange(start_line=line, end_line=line))
        evidence.append(ref)
        entries.append(
            {
                "entry_id": entry_id(symbol.symbol_id),
                "symbol_id": symbol.symbol_id,
                "kind": raw["kind"],
                "detection": EntryDetection.agent_proposed.value,
                **({"framework": raw["framework"]} if raw.get("framework") else {}),
                "attributes": {**raw.get("attributes", {}), "carried_from": found["origin"]},
                "evidence_ids": [ref.evidence_id],
                "side": HEAD.value,
            }
        )
    return {
        **found["source"],
        "entries": entries,
        "not_found": [raw["symbol_id"] for raw in missing],
        **({"not_found_entries": missing} if missing else {}),
        **({"groups": found["groups"]} if found.get("groups") else {}),
        **({"proposed": found["proposed"]} if "proposed" in found else {}),
        "evidence": evidence,
    }


def read_carried(root: Path) -> dict:
    """What a session carried, as `carried.json` keeps it: nothing when it carried none."""
    path = root / CARRIED
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def reported(carried: dict) -> dict:
    """What `prepare` reports about the entries a session carried."""
    return {
        **{key: carried[key] for key in SOURCES if key in carried},
        "entries": len(carried.get("entries", ())),
        "not_found": list(carried.get("not_found", ())),
    }


def _named(source: dict) -> str | None:
    if "from_map" in source:
        found = source["from_map"]
        return f"{found['path']} (snapshot {found['snapshot_id']})"
    if "from_session" in source:
        return f"map session {source['from_session']}"
    return None


def check_planned(root: Path, session_id: str, found: dict) -> None:
    """Refuse a map to start from that is not the one a planned session started from.

    A plan is made with the entries the session had, so they stay as they were.
    """
    kept = read_carried(root)
    was = {key: kept[key] for key in SOURCES if key in kept}
    wanted = found["source"]
    if was == wanted and kept.get("proposed") == found["proposed"]:
        return
    if was == wanted:
        differs = f"those {_named(was)} proposed then, not those it proposes now"
    else:
        before = f"those of {_named(was)}" if was else "none carried from a map"
        differs = f"{before}, not those of {_named(wanted)}"
    raise LoopError(
        "invalid_input",
        f"Session {session_id} was planned with other entries: {differs}. Run prepare "
        "without --entries-from to go on with its plan. To start over from "
        f"{wanted['from_map']['path']}, remove .genesis/sessions/{session_id}, which "
        "discards its plan, flows and explanations, and run prepare again.",
    )

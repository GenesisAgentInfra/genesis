"""What every agent loop shares: refusals, located problems and checked citations.

A citation is a line range with a short quote from it. It is accepted only when the
quote is in that range of the frozen source, whatever language the file is in.
"""

from __future__ import annotations

import hashlib
import re

from genesis_contracts.business_map import FOLDED_WIDTH, StepKind
from genesis_contracts.map_tasks import EvidenceCite, FlowSubmission, place
from genesis_contracts.models import EvidenceRef, EvidenceSide, ReferenceRange
from pydantic import ValidationError

from genesis_ci.snapshot import slice_source

HEAD = EvidenceSide.head
# The one task of a change session that is not a flow: explaining the changes.
CHANGE_TASK = "task_change"
# The limitation of a flow that needs stages before a reader can take it in.
TOO_WIDE = "flow_too_wide"
SOURCE_CHARS = 12000
SEARCH_LIMIT = 40
# How far a quote cited as evidence for a risk or an observation may sit from the lines
# given for it. Such a citation decides no anchor, so the nearest match stands in.
NEARBY_LINES = 5


class LoopError(ValueError):
    """A request the session cannot accept. `errors` lists every problem found."""

    def __init__(self, code: str, message: str, errors: list[dict] | None = None):
        self.code = code
        self.errors = errors or []
        super().__init__(message)


def problem(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


_ITEM = re.compile(r"^(steps|edges|omitted|observations|changes)\[(\d+)\]")
_GROUPED = re.compile(r"^changes\[\d+\]\.change_ids\[(\d+)\]")
_NAMED_BY = {
    "steps": ("step {}", ("key",)),
    "edges": ("edge {} -> {}", ("source", "target")),
    "omitted": ("omitted {}", ("anchor",)),
    "observations": ("observation on {}", ("step",)),
    "changes": ("change {}", ("change_id",)),
}


def named(problems: list[dict], raw, describe=None) -> list[dict]:
    """Say which item each problem is about, by the name the submission gives it.

    A path names an item by its position, and among fifty steps a position is easy to
    misread: `steps[34]` was taken for another step twice in a row. `describe` adds what
    the name stands for where the name says nothing, as with a fingerprint.
    """
    for item in problems:
        found = _ITEM.match(item["path"])
        items = raw.get(found.group(1)) if found and isinstance(raw, dict) else None
        if not isinstance(items, list) or int(found.group(2)) >= len(items):
            continue
        entry = items[int(found.group(2))]
        grouped = _GROUPED.match(item["path"])
        ids = entry.get("change_ids") if grouped and isinstance(entry, dict) else None
        if isinstance(ids, list) and int(grouped.group(1)) < len(ids):
            # One explanation of several changes: name the change the problem is about.
            item["item"] = f"change {ids[int(grouped.group(1))]}"
            continue
        wording, fields = _NAMED_BY[found.group(1)]
        values = [entry.get(field) for field in fields] if isinstance(entry, dict) else []
        if values and all(isinstance(value, str) for value in values):
            item["item"] = wording.format(*values)
            about = describe(found.group(1), entry) if describe else None
            if about:
                item["item"] += f" ({about})"
    return problems


def pydantic_problems(error: ValidationError) -> list[dict]:
    """Contract errors in the form the CLI's own checks report: `steps[1].evidence[0]`."""
    found = error.errors()
    places = [tuple(item["loc"]) for item in found]

    def echo(item) -> bool:
        # A list reported as too short only because one of its items was invalid.
        at = tuple(item["loc"])
        return item["type"] == "too_short" and any(
            other != at and other[: len(at)] == at for other in places
        )

    return [
        problem(place(item["loc"]) or "(document)", "invalid_" + item["type"], item["msg"])
        for item in found
        if not echo(item)
    ]


def _near(text: str, span: ReferenceRange, quote: str) -> ReferenceRange | None:
    """The range of as many lines nearest to `span` that holds `quote`, earlier first."""
    for distance in range(1, NEARBY_LINES + 1):
        for shift in (-distance, distance):
            if span.start_line + shift < 1:
                continue
            found = ReferenceRange(
                start_line=span.start_line + shift, end_line=span.end_line + shift
            )
            try:
                if quote in slice_source(text, found):
                    return found
            except ValueError:
                continue
    return None


def cited_range(
    source, cite: EvidenceCite, at: str, problems: list, moved: list | None = None
) -> ReferenceRange | None:
    """The range a path-and-quote citation names, once the frozen source confirms it.

    With a `moved` list, a quote that is not in the lines given is looked for in a range
    of as many lines up to `NEARBY_LINES` away; the range found stands in and is recorded
    there. Pass one only for evidence that decides no anchor: a risk or an observation.
    """
    if cite.side != HEAD:
        problems.append(problem(at, "wrong_side", "Only head-side source can be cited here."))
        return None
    if cite.path not in source.list_files(cite.side):
        problems.append(
            problem(at, "file_not_in_snapshot", f"{cite.path} is not in the frozen snapshot.")
        )
        return None
    span = ReferenceRange(start_line=cite.start_line, end_line=cite.end_line)
    whole = source.read_text(cite.side, cite.path)
    try:
        text = slice_source(whole, span)
    except ValueError:
        problems.append(problem(at, "range_out_of_bounds", "The line range is outside the file."))
        return None
    if cite.quote in text:
        return span
    found = None if moved is None else _near(whole, span, cite.quote)
    if found is None:
        problems.append(
            problem(
                at,
                "quote_not_found",
                "The quote is not in that range of the frozen file; read it again through the CLI.",
            )
        )
        return None
    moved.append(
        {
            "path": at,
            "cited": [span.start_line, span.end_line],
            "found": [found.start_line, found.end_line],
        }
    )
    return found


def search_source(source, text: str, register) -> dict:
    """Lines of the frozen head source that contain `text`, each as citable evidence."""
    if not text.strip():
        raise LoopError("empty_search", "Search text must not be empty.")
    matches, truncated = [], False
    for path in source.list_files(HEAD):
        for number, line in enumerate(source.read_text(HEAD, path).split("\n"), 1):
            if text in line:
                if len(matches) >= SEARCH_LIMIT:
                    truncated = True
                    break
                span = ReferenceRange(start_line=number, end_line=number)
                matches.append(
                    {
                        "path": path,
                        "line": number,
                        "text": line.strip()[:240],
                        "evidence_id": register(HEAD, path, span).evidence_id,
                    }
                )
        if truncated:
            break
    return {"matches": matches, "truncated": truncated}


def read_source(source, ref: EvidenceRef) -> dict:
    """The frozen text behind one evidence reference."""
    text = slice_source(source.read_text(ref.side, ref.path), ref.range)
    return {
        "evidence_id": ref.evidence_id,
        "side": ref.side.value,
        "path": ref.path,
        "start_line": ref.range.start_line,
        "end_line": ref.range.end_line,
        "text": text[:SOURCE_CHARS],
        "truncated": len(text) > SOURCE_CHARS,
    }


def _forward(keys: list[str], starts: list[str], edges: list[tuple[str, str]]) -> dict:
    """What each block leads on to. A line back to a block already on the way is a loop."""
    leaving: dict[str, list[str]] = {}
    for source, target in edges:
        if target not in leaving.setdefault(source, []):
            leaving[source].append(target)
    onward: dict[str, list[str]] = {key: [] for key in keys}
    state: dict[str, str] = {}

    def visit(key: str) -> None:
        state[key] = "open"
        for target in leaving.get(key, ()):
            if target == key or state.get(target) == "open":
                continue
            onward[key].append(target)
            if target not in state:
                visit(target)
        state[key] = "done"

    for key in [*starts, *keys]:
        if key not in state:
            visit(key)
    return onward


def _reach(onward: dict, start: str) -> set[str]:
    found, walk = set(), [start]
    while walk:
        for target in onward[walk.pop()]:
            if target not in found:
                found.add(target)
                walk.append(target)
    return found


def fold_stages(
    submission: FlowSubmission, flow_id: str, step_ids: dict, problems: list
) -> tuple[list[dict], list[dict]]:
    """The stages of a description as the map stores them, and what is left to do about them.

    A stage that cannot be drawn as one block is a problem. A flow still wider than a
    reader takes in once its stages are folded is accepted with a limitation that keeps
    the map unfinished, like facts left unaccounted for.
    """
    keys = [step.key for step in submission.steps]
    triggers = [step.key for step in submission.steps if step.kind == StepKind.trigger]
    lines = [(edge.source, edge.target) for edge in submission.edges]
    onward = _forward(keys, triggers, lines)
    block = {key: key for key in keys}
    for index, stage in enumerate(submission.stages):
        where = f"stages[{index}]"
        inside = set(stage.steps)
        if inside & set(triggers):
            problems.append(
                problem(
                    where,
                    "trigger_in_stage",
                    "Leave the trigger out: a flow shows where it starts.",
                )
            )
        # Folded, the stage is one block; a step that leaves it and comes back cannot be drawn.
        between = sorted(
            key
            for member in stage.steps
            for key in onward[member]
            if key not in inside and _reach(onward, key) & inside
        )
        if between:
            problems.append(
                problem(
                    where,
                    "stage_not_one_run",
                    f"Step '{between[0]}' runs between the steps of this stage. Put it in the "
                    "stage, or end the stage before it.",
                )
            )
        block.update(dict.fromkeys(stage.steps, "stage:" + stage.key))
    blocks = list(dict.fromkeys(block[key] for key in keys))
    folded = _forward(
        blocks,
        [block[key] for key in triggers],
        [(block[a], block[b]) for a, b in lines if block[a] != block[b]],
    )
    column: dict[str, int] = {}

    def depth(key: str) -> int:
        if key not in column:
            column[key] = 0
            column[key] = 1 + max((depth(target) for target in folded[key]), default=0)
        return column[key]

    width = max((depth(key) for key in blocks), default=0)
    wide = []
    if width > FOLDED_WIDTH:
        wide.append(
            {
                "code": TOO_WIDE,
                "message": f"With its stages folded this flow is {width} blocks across; a "
                f"reader takes in {FOLDED_WIDTH}. Group steps that get one thing done into a "
                "stage and name it for that thing. Keep the decisions and outcomes a reader "
                "needs outside the stages.",
                "affects_completeness": True,
            }
        )
    stages = [
        {
            "stage_id": "stage_"
            + hashlib.sha256(f"{flow_id}\0{stage.key}".encode()).hexdigest()[:16],
            "name": stage.name,
            "step_ids": [step_ids[key] for key in stage.steps if key in step_ids],
        }
        for stage in submission.stages
    ]
    return stages, wide

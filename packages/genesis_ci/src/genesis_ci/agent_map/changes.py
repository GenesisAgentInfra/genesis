"""Changes between the two frozen sides, read as lines. No language is parsed.

A change is a run of lines that differ. It belongs to the step that cites those lines,
so describing a flow is what brings its changes onto the map.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from difflib import SequenceMatcher

from genesis_contracts.models import EvidenceSide

from genesis_ci.snapshot import physical_lines

from .session import is_test_path

BASE, HEAD = EvidenceSide.base, EvidenceSide.head
MAX_CHANGES = 200
TEXT_CHARS = 2000
# How many lines of a change are kept as its evidence; a new file is cited by its start.
EVIDENCE_LINES = 200


@dataclass(frozen=True)
class LineChange:
    """One run of changed lines. Ranges are 1-based and inclusive.

    `at` is where it sits in the head file: its own first line, or for a removal the
    line it was taken out after.
    """

    change_id: str
    kind: str
    path: str
    before: tuple[int, int] | None
    after: tuple[int, int] | None
    at: int

    @property
    def is_test(self) -> bool:
        return self.kind.startswith("test_")

    def reach(self) -> tuple[int, int]:
        """The head lines a step has to cite for this change to belong to it."""
        return self.after or (max(self.at, 1), self.at + 1)


def _lines(source, side, path) -> list[str]:
    return [line.rstrip("\r\n") for line in physical_lines(source.read_text(side, path))]


def _runs(before: list[str], after: list[str]):
    """Each run of differing lines as (first, end) on both sides, zero-based, end-exclusive."""
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    for word, *bounds in matcher.get_opcodes():
        old, new = (bounds[0], bounds[1]), (bounds[2], bounds[3])
        # Reformatting alone is no change to what the code does.
        if word != "equal" and (
            "".join(before[slice(*old)]).split() != "".join(after[slice(*new)]).split()
        ):
            yield old, new


def line_changes(snapshot) -> tuple[list[LineChange], bool]:
    """Every changed run of lines in the frozen files, and whether the list was cut."""
    source, found = snapshot.source, []

    def add(path, old, new, texts):
        """`old` and `new` are zero-based, end-exclusive; `None` when the file is not there."""
        gone = old is not None and old[1] > old[0]
        came = new is not None and new[1] > new[0]
        word = "modified" if gone and came else "added" if came else "removed"
        identity = "\0".join((path, word, *texts, str(len(found))))
        found.append(
            LineChange(
                change_id="chg_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                kind=("test_" if is_test_path(path) else "source_") + word,
                path=path,
                before=(old[0] + 1, old[1]) if gone else None,
                after=(new[0] + 1, new[1]) if came else None,
                at=new[0] + 1 if came else (new or (0, 0))[0],
            )
        )

    for delta in snapshot.capture.file_diff.changes:
        change = delta.change
        if change.change_type == "added":
            lines = _lines(source, HEAD, change.head_path)
            if lines:
                add(change.head_path, None, (0, len(lines)), ("", "\n".join(lines)))
        elif change.change_type == "deleted":
            lines = _lines(source, BASE, change.base_path)
            if lines:
                add(change.base_path, (0, len(lines)), None, ("\n".join(lines), ""))
        elif change.change_type == "modified":
            before = _lines(source, BASE, change.base_path)
            after = _lines(source, HEAD, change.head_path)
            for old, new in _runs(before, after):
                texts = ("\n".join(before[slice(*old)]), "\n".join(after[slice(*new)]))
                add(change.head_path, old, new, texts)
    return found[:MAX_CHANGES], len(found) > MAX_CHANGES


def shortened(text: str) -> str:
    return text if len(text) <= TEXT_CHARS else text[: TEXT_CHARS - 1] + "…"


def cited_lines(span: tuple[int, int]) -> tuple[int, int]:
    return span[0], min(span[1], span[0] + EVIDENCE_LINES - 1)


def overlap(first: tuple[int, int], second: tuple[int, int]) -> int:
    return min(first[1], second[1]) - max(first[0], second[0]) + 1


def placements(change: LineChange, cited: list[tuple[str, str, str, tuple[int, int]]]) -> list:
    """The steps that cite the changed lines: the closest fit first, one per flow.

    `cited` lists (flow_id, step_id, path, lines) for every range a step cites. A
    deleted file has no line left to cite, so its change has no place.
    """
    reach = change.reach()
    scored: dict[tuple[str, str], int] = {}
    for flow_id, step_id, path, lines in cited:
        shared = overlap(reach, lines) if path == change.path else 0
        if shared > 0:
            # A step that cites little else than the change fits it better than one
            # that cites the whole function around it.
            score = shared * 1000 - (lines[1] - lines[0])
            scored[(flow_id, step_id)] = max(score, scored.get((flow_id, step_id), score))
    chosen, flows = [], set()
    for (flow_id, step_id), _ in sorted(scored.items(), key=lambda item: -item[1]):
        if flow_id not in flows:
            flows.add(flow_id)
            chosen.append({"status": "projected", "flow_id": flow_id, "step_id": step_id})
    return chosen


def coverage(assessment: dict) -> dict | None:
    """The stored reading of the tests, in the form the change report states it."""
    if assessment.get("verdict") is None:
        return None
    return {
        "verdict": assessment["verdict"],
        "basis": ["agent_assessment"],
        "execution_data": "not_collected",
        "note": assessment["note"],
        "checks": [
            {"test_id": test["name"], **test["check"]}
            for test in assessment.get("tests", ())
            if test.get("check")
        ],
        "items": [
            {
                "test_id": test["name"],
                "tags": ["agent_identified", *(["assertion_found"] if test["asserts"] else [])],
                "evidence_ids": test["evidence_ids"],
            }
            for test in assessment.get("tests", ())
        ],
    }

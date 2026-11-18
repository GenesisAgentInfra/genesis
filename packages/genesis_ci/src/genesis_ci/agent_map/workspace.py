"""The agent loop for a repository no analyzer reads: plan, context, submit, assemble.

The agent names the entries, the steps and the paths between them. A description is
taken or rejected as a whole: every citation has to be found in the frozen source, and
the steps have to form one flow that starts at a trigger. Whether a path of the code
was left out is not checked here; there are no facts to check it against.
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import cached_property
from pathlib import Path

from genesis_contracts.agent_tasks import AgentChangeSubmission, AgentPlan
from genesis_contracts.business_map import BusinessMap, EdgeRelation, MapFlow, StepKind
from genesis_contracts.change_report import ChangeReport, validate_change_report_against_map
from genesis_contracts.fingerprint import fact_fingerprint
from genesis_contracts.map_tasks import EvidenceCite, FlowSubmission
from genesis_contracts.models import EvidenceRef, EvidenceSide, ReferenceRange
from pydantic import ValidationError

from genesis_ci.business_map.loop import (
    CHANGE_TASK,
    TOO_WIDE,
    LoopError,
    cited_range,
    fold_stages,
    named,
    problem,
    pydantic_problems,
    read_source,
    search_source,
)
from genesis_ci.business_map.store import evidence_bundle, session_root, write_json
from genesis_ci.snapshot_store import load_snapshot

from .changes import (
    MAX_CHANGES,
    LineChange,
    cited_lines,
    coverage,
    line_changes,
    overlap,
    placements,
    shortened,
)

BASE, HEAD = EvidenceSide.base, EvidenceSide.head
CLAIM_SECONDS = 900
UNUSED = "Leave this out: it refers to analyzer facts, and this repository has none."
OFF_MAP = "No step of the map cites these lines."
RULES = (
    "Name steps in business language; one step may cover several lines of code.",
    "Cite evidence for every step: path + start_line + end_line + quote, or an evidence_id "
    "from `map query --search`. Cite the lines that do what the step says, not the whole "
    "function around them.",
    "Start with one `trigger` step per entry. Every other step must be reachable from a "
    "trigger through edges.",
    "A `decision` step has an edge for each way it can go. A `branch` edge leaves a decision "
    "and names in `branch` the outcome it takes.",
    "Draw the failure paths and loops the code has, with `exception` and `loop` edges.",
    "A call to an outside system, such as a payment provider, a database, a model or a "
    "queue, is an `external` step.",
    "If the code does not show a relation, submit it as candidate or unknown with a reason.",
    "Leave out `anchors`, `omitted` and `unexpanded_reason`.",
)
CHANGE_RULES = (
    "Explain every change in `changes`: `summary` says what is different for a user or "
    "another system, not which lines moved.",
    "A change is on the map when a step cites its lines. For an `unassigned` change in "
    "code a flow runs through, add or widen a step in that flow so that it cites those "
    "lines, and submit the flow again.",
    "Every change outside test files needs a `verdict` with a `note`: `covered` (a cited "
    "test takes the changed path and asserts on the result), `reached_only` (tests run the "
    "code but miss the changed path or assert nothing about it), `not_reached` (no test "
    "gets there) or `unknown` (could not be told).",
    "Cite each test you rely on under `tests` with its name and its lines; set `asserts` "
    "when it checks what the changed code produces.",
    "A change to a test file gets a `summary` and no verdict.",
    "Verdicts come from reading the tests. Never say a test ran or passed.",
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Workspace:
    Plan = AgentPlan

    def __init__(self, repo: Path, session_id: str):
        self.repo = repo.expanduser().resolve(strict=True)
        self.root = session_root(self.repo, session_id)
        if not (self.root / "session.json").is_file():
            raise FileNotFoundError(f"no such session: {session_id}")
        self.session = self._read("session.json")
        stored = self._read("evidence.json") if (self.root / "evidence.json").is_file() else []
        self._minted = {item["evidence_id"]: EvidenceRef.model_validate(item) for item in stored}
        self._unsaved = False

    def _read(self, name: str):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    @cached_property
    def snapshot(self):
        return load_snapshot(self.root / "snapshot")

    @property
    def source(self):
        return self.snapshot.source

    @property
    def is_change(self) -> bool:
        return self.session.get("mode") == "change"

    # ----- evidence ----------------------------------------------------------------

    def evidence(self, evidence_id: str) -> EvidenceRef | None:
        return self._minted.get(evidence_id)

    def _register(self, side, path, span) -> EvidenceRef:
        ref = self.source.evidence(side, path, span)
        if ref.evidence_id not in self._minted:
            self._minted[ref.evidence_id] = ref
            self._unsaved = True
        return ref

    def _keep_evidence(self) -> None:
        """Store the references made so far, so a later command can read them back."""
        if self._unsaved:
            write_json(
                self.root / "evidence.json",
                [self._minted[key].model_dump(mode="json") for key in sorted(self._minted)],
            )
            self._unsaved = False

    def _cite(self, cites: tuple[EvidenceCite, ...], where: str, problems: list) -> list[str]:
        """Resolve citations against the frozen snapshot; report every one that fails."""
        resolved = []
        for index, cite in enumerate(cites):
            at = f"{where}[{index}]"
            if cite.evidence_id is not None:
                if self.evidence(cite.evidence_id) is None:
                    problems.append(problem(at, "unknown_evidence", cite.evidence_id))
                else:
                    resolved.append(cite.evidence_id)
                continue
            span = cited_range(self.source, cite, at, problems)
            if span is not None:
                resolved.append(self._register(cite.side, cite.path, span).evidence_id)
        return list(dict.fromkeys(resolved))

    def _anchors(self, evidence_ids) -> list[str]:
        """What a step or edge rests on: the cited text itself, wherever it moves to."""
        found = []
        for evidence_id in evidence_ids:
            ref = self.evidence(evidence_id)
            text = self.source.slice(ref.side, ref.path, ref.range)
            found.append(fact_fingerprint(symbol=ref.path, kind="cited", text=text))
        return list(dict.fromkeys(found))

    def search(self, text: str) -> dict:
        found = search_source(self.source, text, self._register)
        self._keep_evidence()
        return found

    def read(self, evidence_id: str) -> dict:
        ref = self.evidence(evidence_id)
        if ref is None:
            raise LoopError("unknown_evidence", f"No evidence {evidence_id} in this session.")
        return read_source(self.source, ref)

    def query_symbol(self, symbol_id: str) -> dict:
        raise LoopError(
            "no_symbol_index",
            "This session has no index of symbols. Read the files, or use `--search`.",
        )

    # ----- plan and tasks ------------------------------------------------------------

    @cached_property
    def plan(self) -> dict | None:
        return self._read("plan.json") if (self.root / "plan.json").is_file() else None

    def save_plan(self, plan: AgentPlan | None) -> dict:
        if plan is None:
            raise LoopError(
                "plan_required",
                "No entry points are detected for this repository. Find them in the code, "
                "write the plan and pass it with `--input`.",
            )
        problems, tasks, starts = [], [], {}
        for index, flow in enumerate(plan.flows):
            entries = []
            for position, entry in enumerate(flow.entries):
                where = f"flows[{index}].entries[{position}]"
                cited = self._cite(entry.evidence, where + ".evidence", problems)
                if not cited:
                    continue
                symbol = f"{self.evidence(cited[0]).path}#{entry.name}"
                if symbol in starts:
                    problems.append(
                        problem(
                            where + ".name",
                            "duplicate_entry",
                            f"{symbol} already starts the flow '{starts[symbol]}'.",
                        )
                    )
                    continue
                starts[symbol] = flow.key
                entries.append(
                    {
                        "entry_id": "entry_" + _digest(symbol),
                        "symbol_id": symbol,
                        "kind": entry.kind.value,
                        "detection": "agent_proposed",
                        "evidence_ids": cited,
                    }
                )
            identity = _digest("\0".join(sorted(item["symbol_id"] for item in entries)))
            tasks.append(
                {
                    "task_id": "task_" + identity,
                    "kind": "flow",
                    "flow_key": flow.key,
                    "flow_id": "flow_" + identity,
                    "entries": entries,
                }
            )
        if problems:
            raise LoopError("invalid_plan", "The plan was not accepted.", problems)
        write_json(
            self.root / "plan.json",
            {"plan": plan.model_dump(mode="json", exclude_none=True), "tasks": tasks},
        )
        self.__dict__.pop("plan", None)
        self.assemble()
        return {"status": "accepted", **self.status()}

    def tasks(self) -> list[dict]:
        if self.plan is None:
            raise LoopError("no_plan", "Run `genesis map plan` before working on tasks.")
        return self.plan["tasks"]

    def task(self, task_id: str) -> dict:
        found = next((item for item in self.tasks() if item["task_id"] == task_id), None)
        if found is None:
            raise LoopError("unknown_task", f"No task {task_id} in the current plan.")
        return found

    def _task_file(self, task_id: str, name: str) -> Path:
        return self.root / "tasks" / task_id / name

    def _stored(self, task_id: str, name: str):
        path = self._task_file(task_id, name)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def task_state(self, task: dict) -> str:
        if self._stored(task["task_id"], "accepted.json") is not None:
            return "validated"
        if self._stored(task["task_id"], "rejected.json") is not None:
            return "failed"
        claim = self._stored(task["task_id"], "claim.json")
        return "claimed" if claim and claim["expires_at"] > time.time() else "pending"

    def _outline(self, task: dict) -> dict:
        """What the plan said about the flow of a task."""
        return next(flow for flow in self.plan["plan"]["flows"] if flow["key"] == task["flow_key"])

    def context(self, task_id: str, claim: bool = False) -> dict:
        if task_id == CHANGE_TASK:
            return {
                "task_id": CHANGE_TASK,
                **self._change_views(),
                "rules": list(CHANGE_RULES),
            }
        task = self.task(task_id)
        if claim:
            current = self._stored(task_id, "claim.json")
            if current and current["expires_at"] > time.time():
                raise LoopError("task_claimed", "Another worker holds this task for now.")
            write_json(
                self._task_file(task_id, "claim.json"), {"expires_at": time.time() + CLAIM_SECONDS}
            )
        outline = self._outline(task)
        accepted = self._stored(task_id, "accepted.json")
        change = {}
        if self.is_change:
            # The changes this flow carries, and those still waiting for a step to cite them.
            views = self._change_views()["changes"]
            change = {
                "changes": [
                    item
                    for item in views
                    if item["placement"].get("flow_id") in (None, task["flow_id"])
                ]
            }
        return {
            "task_id": task_id,
            "kind": "flow",
            "state": self.task_state(task),
            "flow_id": task["flow_id"],
            "name": outline["name"],
            **({"summary": outline["summary"]} if outline.get("summary") else {}),
            "entries": [
                {
                    "entry_id": entry["entry_id"],
                    "name": entry["symbol_id"].partition("#")[2],
                    "kind": entry["kind"],
                    "source": [
                        read_source(self.source, self.evidence(ref))
                        for ref in entry["evidence_ids"]
                    ],
                }
                for entry in task["entries"]
            ],
            **change,
            "previous": accepted["result"] if accepted else None,
            "rules": list(RULES),
        }

    # ----- submission --------------------------------------------------------------

    def submit(self, task_id: str, raw) -> dict:
        if task_id == CHANGE_TASK:
            return self._submit_change(raw)
        task = self.task(task_id)
        try:
            submission = FlowSubmission.model_validate(raw)
        except ValidationError as error:
            return self._reject(task, pydantic_problems(error), raw)
        problems: list[dict] = []
        cited: set[str] = set()
        if submission.omitted:
            problems.append(problem("omitted", "not_used_here", UNUSED))
        steps, by_key, uncited = [], {}, set()
        for index, step in enumerate(submission.steps):
            where = f"steps[{index}]"
            for field in ("anchors", "unexpanded_reason"):
                if getattr(step, field):
                    problems.append(problem(f"{where}.{field}", "not_used_here", UNUSED))
            evidence = self._cite(step.evidence, where + ".evidence", problems)
            if not step.evidence:
                uncited.add(step.key)
            if step.resolution != "unknown" and not step.evidence:
                problems.append(
                    problem(
                        where + ".evidence",
                        "evidence_required",
                        "Cite the lines that do what this step says.",
                    )
                )
            cited.update(evidence)
            item = {
                "step_id": "step_" + _digest(task["flow_id"] + "\0" + step.key),
                "name": step.name,
                "kind": step.kind.value,
                "support": "agent_synthesis",
                "resolution": step.resolution.value,
                "anchors": self._anchors(evidence),
                "evidence_ids": evidence,
                "finding_ids": [],
            }
            if step.reason:
                item["reason"] = step.reason
            if step.contract is not None:
                item["contract"] = step.contract.model_dump(mode="json", exclude_none=True)
            steps.append(item)
            by_key[step.key] = item
        edges, leaving, drawn = [], {}, set()
        for index, edge in enumerate(submission.edges):
            where = f"edges[{index}]"
            source, target = by_key[edge.source], by_key[edge.target]
            evidence = self._cite(edge.evidence, where + ".evidence", problems)
            cited.update(evidence)
            leaving.setdefault(edge.source, []).append(edge.target)
            identity = (edge.source, edge.target, edge.relation, edge.branch)
            if identity in drawn:
                problems.append(problem(where, "duplicate_edge", "This edge is drawn twice."))
                continue
            drawn.add(identity)
            if edge.source == edge.target and edge.relation != EdgeRelation.loop:
                problems.append(
                    problem(where, "self_edge", "Only a loop edge may connect a step to itself.")
                )
                continue
            item = {
                "source": source["step_id"],
                "target": target["step_id"],
                "relation": edge.relation.value,
                "support": "agent_synthesis",
                "resolution": edge.resolution.value,
                # Without lines of its own, an edge rests on the two steps it connects;
                # two steps on one line of code share what they rest on.
                "anchors": self._anchors(evidence)
                or list(dict.fromkeys([*source["anchors"][:1], *target["anchors"][:1]])),
                "evidence_ids": evidence
                or list(dict.fromkeys([*source["evidence_ids"][:1], *target["evidence_ids"][:1]])),
            }
            if edge.reason:
                item["reason"] = edge.reason
            if edge.relation == EdgeRelation.branch:
                if source["kind"] != "decision" or not source["anchors"]:
                    # A decision whose citation was refused is reported there, once.
                    if source["kind"] != "decision" or edge.source in uncited:
                        problems.append(
                            problem(
                                where + ".source",
                                "branch_from_non_decision",
                                "A branch edge leaves a decision step that cites the condition.",
                            )
                        )
                    continue
                item["condition"] = {
                    "label": edge.label or edge.branch,
                    "branch": edge.branch,
                    "anchor": source["anchors"][0],
                }
            elif edge.label:
                item["label"] = edge.label
            if edge.resolution != "unknown" and not item["evidence_ids"]:
                problems.append(
                    problem(
                        where,
                        "edge_needs_evidence",
                        "Neither step of this edge cites code. Cite evidence on the edge, or "
                        "submit it as unknown with a reason.",
                    )
                )
            edges.append(item)
        triggers = [step.key for step in submission.steps if step.kind == StepKind.trigger]
        if not triggers:
            problems.append(
                problem(
                    "steps", "no_trigger", "Start the flow with a trigger step: what sets it off."
                )
            )
        reached, waiting = set(triggers), list(triggers)
        while waiting:
            for key in leaving.get(waiting.pop(), ()):
                if key not in reached:
                    reached.add(key)
                    waiting.append(key)
        for index, step in enumerate(submission.steps):
            if triggers and step.key not in reached:
                problems.append(
                    problem(
                        f"steps[{index}]",
                        "unreachable",
                        "No path of edges leads from a trigger to this step.",
                    )
                )
            ways = len(leaving.get(step.key, ()))
            if step.kind == StepKind.decision and ways < 2:
                problems.append(
                    problem(
                        f"steps[{index}]",
                        "decision_without_branches",
                        f"A decision has an edge for each way it can go; this one has {ways}.",
                    )
                )
        findings = []
        for index, item in enumerate(submission.observations):
            evidence = self._cite(item.evidence, f"observations[{index}].evidence", problems)
            cited.update(evidence)
            if not evidence:
                continue
            finding = {
                "finding_id": "find_" + _digest(task["flow_id"] + "\0" + item.statement),
                "source": "agent_observation",
                "severity": item.severity.value,
                "statement": item.statement,
                "evidence_ids": evidence,
            }
            if item.gap:
                finding["gap"] = item.gap
            if item.category is not None:
                finding["category"] = item.category.value
            findings.append(finding)
            by_key[item.step]["finding_ids"].append(finding["finding_id"])
        stages, wide = fold_stages(
            submission,
            task["flow_id"],
            {key: item["step_id"] for key, item in by_key.items()},
            problems,
        )
        flow = {
            "flow_id": task["flow_id"],
            "name": submission.name,
            "stage": "synthesized",
            "support": "agent_synthesis",
            "entries": task["entries"],
            "steps": steps,
            "edges": edges,
            "stages": stages,
            **({"limitations": wide} if wide else {}),
            "accounting": {"accountable": 0, "covered": 0, "omitted": 0, "unaccounted": 0},
        }
        if submission.summary:
            flow["summary"] = submission.summary
        cited.update(ref for entry in task["entries"] for ref in entry["evidence_ids"])
        if not problems:
            try:
                MapFlow.model_validate(flow)
            except ValidationError as error:
                problems = pydantic_problems(error)
        if problems:
            return self._reject(task, problems, raw)
        result = {
            "task_id": task_id,
            "status": "accepted",
            "flow_id": task["flow_id"],
            "steps": {step.key: by_key[step.key]["step_id"] for step in submission.steps},
            **({"too_wide": wide[0]["message"]} if wide else {}),
            "errors": [],
        }
        accepted = self._task_file(task_id, "accepted.json")
        previous = accepted.read_text(encoding="utf-8") if accepted.is_file() else None
        write_json(
            accepted,
            {"flow": flow, "findings": findings, "evidence_ids": sorted(cited), "result": result},
        )
        try:
            assembled = self.assemble()
        except ValidationError as error:
            # Never keep a submission the whole map cannot be built with.
            if previous is None:
                accepted.unlink()
            else:
                accepted.write_text(previous, encoding="utf-8")
            return self._reject(task, pydantic_problems(error), raw)
        self._task_file(task_id, "rejected.json").unlink(missing_ok=True)
        return {**result, "analysis_status": assembled.analysis_status, **self.change_counts()}

    def _reject(self, task: dict, problems: list[dict], raw=None) -> dict:
        """Keep the last accepted version; record why this attempt was refused."""
        named(problems, raw)
        counter = self._stored(task["task_id"], "attempts.json") or {"rejected": 0}
        counter["rejected"] += 1
        write_json(self._task_file(task["task_id"], "attempts.json"), counter)
        kept = self._stored(task["task_id"], "accepted.json") is not None
        if not kept:
            write_json(self._task_file(task["task_id"], "rejected.json"), {"errors": problems})
            self.assemble()
        return {
            "task_id": task["task_id"],
            "status": "rejected",
            "flow_id": task["flow_id"],
            "rejections": counter["rejected"],
            "accepted_version_kept": kept,
            "errors": problems,
        }

    # ----- assembly and status -----------------------------------------------------

    def stored_map(self) -> BusinessMap:
        return BusinessMap.model_validate_json(
            (self.root / "business-map.json").read_text(encoding="utf-8")
        )

    def assemble(self) -> BusinessMap:
        """Rebuild the map from the plan and the accepted descriptions."""
        flows, findings, cited, states = [], [], set(), []
        flow_of_key = {}
        for task in (self.plan or {}).get("tasks", []):
            outline = self._outline(task)
            accepted = self._stored(task["task_id"], "accepted.json")
            states.append(self.task_state(task))
            if accepted is not None:
                flow = accepted["flow"]
                findings += accepted["findings"]
                cited.update(accepted["evidence_ids"])
            else:
                # Until it is described, a flow is what the plan said about it.
                flow = {
                    "flow_id": task["flow_id"],
                    "name": outline["name"],
                    **({"summary": outline["summary"]} if outline.get("summary") else {}),
                    "stage": "skeleton",
                    "support": "static_fact",
                    "name_from_plan": True,
                    "entries": task["entries"],
                    "accounting": {"accountable": 0, "covered": 0, "omitted": 0, "unaccounted": 0},
                }
                cited.update(ref for entry in task["entries"] for ref in entry["evidence_ids"])
            flows.append({**flow, "tier": outline.get("tier", "primary")})
            flow_of_key[task["flow_key"]] = task["flow_id"]
        domains = []
        for domain in ((self.plan or {}).get("plan") or {}).get("domains", []):
            members = [
                flow_of_key[flow["key"]]
                for flow in self.plan["plan"]["flows"]
                if flow.get("domain") == domain["key"]
            ]
            if members:
                domains.append(
                    {
                        "domain_id": "domain_" + _digest(domain["key"]),
                        "name": domain["name"],
                        "support": "agent_synthesis",
                        "flow_ids": members,
                    }
                )
        entries = sum(len(flow["entries"]) for flow in flows)
        document = {
            "snapshot_id": self.session["snapshot_id"],
            "side": "head",
            "domains": domains,
            "flows": flows,
            "findings": findings,
            "coverage": {
                "scope": f"{len(flows)} planned flows starting at {entries} entries.",
                "entries_total": entries,
                "entries_planned": entries,
                "entries_skipped": 0,
                "entries_unhandled": 0,
                "tasks_total": len(states),
                "tasks_validated": states.count("validated"),
                "tasks_pending": states.count("pending") + states.count("claimed"),
                "tasks_failed": states.count("failed"),
            },
            "evidence": [self.evidence(key).model_dump(mode="json") for key in sorted(cited)],
        }
        assembled = None
        if flows:
            try:
                assembled = BusinessMap.model_validate({**document, "analysis_status": "complete"})
            except ValidationError:
                pass
        if assembled is None:
            # Without a plan there is nothing yet, which is not the same as nothing missing.
            assembled = BusinessMap.model_validate({**document, "analysis_status": "partial"})
        self._publish(assembled)
        return assembled

    def _publish(self, business_map: BusinessMap) -> ChangeReport | None:
        """Store the map, the change report that follows from it, and their excerpts."""
        write_json(
            self.root / "business-map.json",
            business_map.model_dump(mode="json", exclude_none=True),
        )
        evidence = {ref.evidence_id: ref for ref in business_map.evidence}
        report = None
        if self.is_change:
            report = self._report(business_map)
            write_json(
                self.root / "change-report.json", report.model_dump(mode="json", exclude_none=True)
            )
            evidence.update((ref.evidence_id, ref) for ref in report.evidence)
        bundle = evidence_bundle(self.snapshot, tuple(evidence[key] for key in sorted(evidence)))
        write_json(self.root / "evidence-bundle.json", bundle.model_dump(mode="json"))
        self._keep_evidence()
        return report

    def status(self) -> dict:
        stored = self.stored_map()
        tasks = []
        for task in (self.plan or {}).get("tasks", []):
            accepted = self._stored(task["task_id"], "accepted.json")
            rejected = self._stored(task["task_id"], "rejected.json")
            outline = self._outline(task)
            tasks.append(
                {
                    "task_id": task["task_id"],
                    "kind": "flow",
                    "state": self.task_state(task),
                    "flow_key": task["flow_key"],
                    "flow_id": task["flow_id"],
                    "name": (accepted or {}).get("flow", {}).get("name") or outline["name"],
                    "tier": outline.get("tier", "primary"),
                    "entries": [entry["symbol_id"] for entry in task["entries"]],
                    "too_wide": any(
                        item["code"] == TOO_WIDE
                        for item in (accepted or {}).get("flow", {}).get("limitations", ())
                    ),
                    "errors": len((rejected or {}).get("errors", [])),
                    "rejections": (self._stored(task["task_id"], "attempts.json") or {}).get(
                        "rejected", 0
                    ),
                }
            )

        def first(state, tier):
            return next(
                (
                    item["task_id"]
                    for item in tasks
                    if item["state"] == state and item["tier"] == tier
                ),
                None,
            )

        counts = self.change_counts()
        return {
            **self.session,
            "plan": "agent" if self.plan else None,
            "analysis_status": stored.analysis_status,
            "coverage": stored.coverage.model_dump(mode="json", exclude={"limitations", "scope"}),
            **({"change": {"task_id": CHANGE_TASK, **counts}} if counts else {}),
            "tasks": tasks,
            # Flows first: a change is on the map only once a step cites its lines.
            "next_task": first("pending", "primary")
            or first("failed", "primary")
            or first("pending", "supporting")
            or first("failed", "supporting")
            # Then the flows a reader cannot take in yet: they need stages.
            or next((item["task_id"] for item in tasks if item["too_wide"]), None)
            or (CHANGE_TASK if counts.get("changes_waiting") else None),
        }

    # ----- changes -----------------------------------------------------------------

    @cached_property
    def _line_changes(self) -> tuple[list[LineChange], bool]:
        return line_changes(self.snapshot)

    def _assessments(self) -> dict:
        path = self.root / "changes" / "accepted.json"
        return self._read("changes/accepted.json")["assessments"] if path.is_file() else {}

    def _waiting(self) -> list[str]:
        """Changes not explained yet, or outside the tests and without a verdict."""
        assessments = self._assessments()
        return [
            change.change_id
            for change in self._line_changes[0]
            if change.change_id not in assessments
            or (not change.is_test and assessments[change.change_id].get("verdict") is None)
        ]

    def _other_files(self) -> list[dict]:
        path = self.root / "changed-files.json"
        return self._read("changed-files.json")["files"] if path.is_file() else []

    def _report(self, business_map: BusinessMap) -> ChangeReport:
        changes, truncated = self._line_changes
        assessments = self._assessments()
        cited_steps, risks, step_of = [], [], {}
        for flow in business_map.flows:
            for step in flow.steps:
                for ref in map(self.evidence, step.evidence_ids):
                    lines = (ref.range.start_line, ref.range.end_line)
                    cited_steps.append((flow.flow_id, step.step_id, ref.path, lines))
                step_of.update(dict.fromkeys(step.finding_ids, (flow.flow_id, step.step_id)))
        for finding in business_map.findings:
            for ref in map(self.evidence, finding.evidence_ids):
                risks.append(
                    (finding.finding_id, ref.path, (ref.range.start_line, ref.range.end_line))
                )
        items, cited, introduced = [], set(), set()
        for change in changes:
            targets = placements(change, cited_steps) or [
                {"status": "unassigned", "reason": OFF_MAP}
            ]
            item = {
                "change_id": change.change_id,
                "kind": change.kind,
                "symbol_id": change.path,
                "projection": targets[0],
                "other_projections": targets[1:],
            }
            for name, side, span in (
                ("before", BASE, change.before),
                ("after", HEAD, change.after),
            ):
                if span is None:
                    continue
                first, last = cited_lines(span)
                ref = self._register(
                    side, change.path, ReferenceRange(start_line=first, end_line=last)
                )
                text = self.source.slice(side, change.path, ref.range)
                item[name] = {
                    "side": side.value,
                    "text": shortened(text) if text.strip() else "(blank lines)",
                    "anchor": fact_fingerprint(symbol=change.path, kind="lines", text=text),
                    "evidence_ids": [ref.evidence_id],
                }
                cited.add(ref.evidence_id)
            stored = assessments.get(change.change_id)
            if stored is not None:
                item["explanation"] = {
                    key: stored[key]
                    for key in ("summary", "short_summary", "effect")
                    if stored.get(key)
                }
                tests = None if change.is_test else coverage(stored)
                if tests is not None:
                    item["tests"] = tests
                    cited.update(ref for case in tests["items"] for ref in case["evidence_ids"])
            if change.after is not None:
                found = list(
                    dict.fromkeys(
                        finding_id
                        for finding_id, path, lines in risks
                        if path == change.path and overlap(change.after, lines) > 0
                    )
                )
                if found:
                    # The lines a risk is stated about are lines this change wrote.
                    item["finding_ids"] = found
                    introduced.update(found)
            items.append(item)
        finding_changes = []
        for finding in business_map.findings:
            if finding.finding_id in introduced:
                entry = {
                    "status": "introduced",
                    "finding": finding.model_dump(mode="json", exclude_none=True),
                }
                if finding.finding_id in step_of:
                    flow_id, step_id = step_of[finding.finding_id]
                    entry.update(flow_id=flow_id, step_id=step_id)
                finding_changes.append(entry)
                cited.update(finding.evidence_ids)
        limitations = []
        if truncated:
            limitations.append(
                {
                    "code": "changes_truncated",
                    "message": f"Only the first {MAX_CHANGES} changes are listed.",
                    "affects_completeness": True,
                }
            )
        waiting = len(self._waiting())
        if waiting:
            limitations.append(
                {
                    "code": "changes_unexplained",
                    "message": f"{waiting} of {len(changes)} changes are not explained yet.",
                    "affects_completeness": True,
                }
            )
        document = {
            "snapshot_id": self.session["snapshot_id"],
            **{
                key: self.session[key]
                for key in ("base_ref", "base_revision", "head_ref", "head_revision")
                if self.session.get(key)
            },
            "changes": items,
            "unanalyzed_changes": [
                {**item, "reason": "Not a source file Genesis reads."}
                for item in self._other_files()
            ],
            "finding_changes": finding_changes,
            "limitations": limitations,
            "evidence": [self.evidence(key).model_dump(mode="json") for key in sorted(cited)],
        }
        try:
            report = ChangeReport.model_validate({**document, "analysis_status": "complete"})
        except ValidationError:
            report = ChangeReport.model_validate({**document, "analysis_status": "partial"})
        validate_change_report_against_map(report, business_map)
        return report

    def _stored_report(self) -> ChangeReport:
        return ChangeReport.model_validate_json(
            (self.root / "change-report.json").read_text(encoding="utf-8")
        )

    def change_counts(self) -> dict:
        if not self.is_change:
            return {}
        report = self._stored_report()
        return {
            "change_status": report.analysis_status,
            "changes": len(report.changes),
            "changes_placed": sum(
                1 for item in report.changes if item.projection.status != "unassigned"
            ),
            "changes_waiting": len(self._waiting()),
            "changed_files_not_analyzed": len(report.unanalyzed_changes),
        }

    def _change_views(self) -> dict:
        """The changes as an agent reads them: both sides, where each sits, what is said."""
        if not self.is_change:
            raise LoopError(
                "not_a_change_session",
                "This session compares nothing. Run `genesis map prepare --base REV` to "
                "analyze the changes since a revision.",
            )
        report, stored = self._stored_report(), self.stored_map()
        names = {
            (flow.flow_id, step.step_id): (flow.name, step.name)
            for flow in stored.flows
            for step in flow.steps
        }
        by_id = {change.change_id: change for change in self._line_changes[0]}
        views = []
        for item in report.changes:
            change, target = by_id[item.change_id], item.projection
            placement = {"status": target.status.value}
            if target.flow_id:
                flow, step = names[(target.flow_id, target.step_id)]
                placement.update(
                    flow_id=target.flow_id, flow=flow, step_id=target.step_id, step=step
                )
            else:
                placement["reason"] = target.reason
            view = {"change_id": item.change_id, "kind": item.kind.value, "path": change.path}
            for name, part, span in (
                ("before", item.before, change.before),
                ("after", item.after, change.after),
            ):
                if part is not None:
                    view[name] = {
                        "start_line": span[0],
                        "end_line": span[1],
                        "text": part.text,
                        "evidence_id": part.evidence_ids[0],
                    }
            view["placement"] = placement
            if item.explanation is not None:
                view["summary"] = item.explanation.summary
            if item.tests is not None:
                view["verdict"] = item.tests.verdict.value
            views.append(view)
        return {
            "changes": views,
            "unanalyzed_changes": [
                item.model_dump(mode="json") for item in report.unanalyzed_changes
            ],
        }

    def change_summary(self) -> dict:
        views = self._change_views()
        return {**self.session, **self.change_counts(), **views}

    def _submit_change(self, raw) -> dict:
        """Check explanations and coverage verdicts for changes; all or nothing."""
        self._change_views()
        folder = self.root / "changes"
        known = {change.change_id: change for change in self._line_changes[0]}
        problems, accepted = [], {}
        try:
            submission = AgentChangeSubmission.model_validate(raw)
        except ValidationError as error:
            submission, problems = None, pydantic_problems(error)
        for index, item in enumerate(submission.changes if submission else ()):
            where = f"changes[{index}]"
            change = known.get(item.change_id)
            if change is None:
                problems.append(
                    problem(where + ".change_id", "unknown_change", f"No change {item.change_id}.")
                )
                continue
            tests = [
                {
                    "name": test.name,
                    "asserts": test.asserts,
                    "evidence_ids": self._cite(
                        test.evidence, f"{where}.tests[{position}].evidence", problems
                    ),
                }
                for position, test in enumerate(item.tests)
            ]
            trouble = None
            if change.is_test:
                if item.verdict is not None:
                    trouble = (
                        "no_verdict_for_tests",
                        "A change to a test gets a summary and no coverage verdict.",
                    )
            elif item.verdict is None:
                trouble = (
                    "verdict_required",
                    "Say whether tests cover this change: covered, reached_only, not_reached "
                    "or unknown, with a note.",
                )
            elif item.verdict in ("covered", "reached_only") and not tests:
                trouble = ("tests_required", "Cite under `tests` the tests that reach this change.")
            elif item.verdict == "covered" and not any(test["asserts"] for test in tests):
                trouble = (
                    "covered_needs_assertion",
                    "Covered needs a cited test that asserts on what the changed code produces; "
                    "without one it is reached_only.",
                )
            elif item.verdict == "not_reached" and tests:
                trouble = (
                    "tests_not_allowed",
                    "not_reached lists no test; a test that gets there makes it reached_only.",
                )
            if trouble:
                problems.append(problem(where + ".verdict", *trouble))
            accepted[item.change_id] = {
                **item.model_dump(mode="json", exclude={"change_id", "tests"}, exclude_none=True),
                "tests": tests,
            }
        if problems:
            named(problems, raw)
            counter = {"rejected": 0}
            if (folder / "attempts.json").is_file():
                counter = self._read("changes/attempts.json")
            counter["rejected"] += 1
            write_json(folder / "attempts.json", counter)
            return {
                "task_id": CHANGE_TASK,
                "status": "rejected",
                "rejections": counter["rejected"],
                "accepted_version_kept": True,
                "errors": problems,
            }
        write_json(folder / "accepted.json", {"assessments": {**self._assessments(), **accepted}})
        self._publish(self.stored_map())
        return {
            "task_id": CHANGE_TASK,
            "status": "accepted",
            "assessed": len(accepted),
            **self.change_counts(),
            "errors": [],
        }

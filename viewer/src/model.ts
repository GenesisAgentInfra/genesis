import { detectLang, type Lang } from "./i18n"
import { layoutRoute, type RouteLayout } from "./layout"
import type {
  ChangeItem,
  CoverageAssessment,
  EvidenceRef,
  FindingChange,
  MapFinding,
  MapFlow,
  MapLink,
  Payload,
  Projection,
} from "./types"

/** One change as it sits at one place: on a step, on a removed step, or off the map. */
export interface Coupon {
  /** The stop this change is, counted from 1 in the order the page walks through them. */
  no: number
  change: ChangeItem
  place: Projection
  primary: boolean
  /** The change brings a risk that was not there before. */
  risky: boolean
  /** How much the change asks to be looked at: the colour of its card. */
  tone: Tone
}

/** What the tests say about a change, in the three words the page shows. */
export type TestStatus = "tested" | "untested" | "unsure"

/** The one thing a card's colour says: a new risk first, else what the tests say. */
export type Tone = "risk" | TestStatus

/** What the reader may narrow the changes down to. */
export type Filter = Tone

export const TONES: Tone[] = ["risk", "untested", "unsure", "tested"]

export type StopKind = "step" | "removed_step" | "off_map" | "removed_flow"

/** One stop of the walk through a change report, the "1 / N" of the page. */
export interface Stop {
  no: number
  kind: StopKind
  /** The change at this stop. A removed flow carries the change that removed its entry, if any. */
  change?: ChangeItem
  coupon?: Coupon
  /** The flow the stop belongs to; none for a change off the map. */
  flowId?: string
  /** The canvas node of the change: a step, or the card of a removed step. */
  nodeId?: string
  /** None for a removed flow, which carries no verdict. */
  status?: TestStatus
  risky: boolean
  tone?: Tone
  /** Other flows the same change sits on, with its node there. */
  also: { flowId: string; nodeId: string }[]
  /** Flows that reach the changed code through calls, though no step of theirs rests on it. */
  maybe: string[]
}

export interface FlowView {
  flow: MapFlow
  removed: boolean
  layout: RouteLayout
  coupons: Coupon[]
  byStep: Map<string, Coupon[]>
  removedSteps: Coupon[]
  newSteps: Set<string>
  findings: MapFinding[]
}

/** A part of the product as the map groups it: the first level of the overview. */
export interface ModuleView {
  id: string
  /** None for the flows the map puts in no module. */
  name?: string
  flows: FlowView[]
}

export interface Counts {
  stops: number
  /** The report lists fewer changes than were found. */
  truncated: boolean
  untested: number
  unsure: number
  tested: number
  /** Changes that bring a new risk, and the new risks themselves. */
  risky: number
  newRisks: number
  files: number
  tests: number
  partial: boolean
}

export interface Model {
  lang: Lang
  share: boolean
  payload: Payload
  flows: FlowView[]
  flowById: Map<string, FlowView>
  /** Modules in map order; flows in no module come last, together. */
  modules: ModuleView[]
  moduleOf: Map<string, ModuleView>
  /** How flows lead into one another, between flows the page shows. */
  links: MapLink[]
  /** The stops whose change lives on each flow, in walk order. */
  stopsOn: Map<string, number[]>
  stops: Stop[]
  evidence: Map<string, EvidenceRef>
  excerpts: Record<string, string>
  findingStatus: Map<string, FindingChange["status"]>
  hasReport: boolean
  counts: Counts
}

const ADDED = new Set([
  "condition_added",
  "call_added",
  "result_added",
  "loop_added",
  "symbol_added",
  "source_added",
])

/** A change to test code is not product logic; the page only counts it. */
export function isTestChange(change: ChangeItem): boolean {
  return change.kind.startsWith("test_")
}

function staticOnly(tests: CoverageAssessment): boolean {
  const basis = tests.basis ?? []
  return basis.length > 0 && basis.every((item) => item === "static_fact")
}

/**
 * Covered is tested; no test reaching the change is untested; a test that reaches the code
 * but not the change is untested too, unless only static analysis says so, which by its own
 * note cannot tell. Everything else is unsure.
 */
export function statusOf(tests?: CoverageAssessment): TestStatus {
  if (!tests) return "unsure"
  if (tests.verdict === "covered") return "tested"
  if (tests.verdict === "not_reached") return "untested"
  if (tests.verdict === "reached_only")
    return staticOnly(tests) ? "unsure" : "untested"
  return "unsure"
}

/** How urgent a change is to look at: lower comes first. */
function tierOf(change: ChangeItem, introduced: Set<string>): number {
  if ((change.finding_ids ?? []).some((id) => introduced.has(id))) return 0
  const tests = change.tests
  if (tests?.verdict === "not_reached") return 1
  if (tests?.verdict === "reached_only" && !staticOnly(tests)) return 2
  if (tests?.verdict === "covered") return 4
  return 3
}

export interface Reach {
  /** Steps one edge after the step. */
  next: string[]
  /** End results it can reach further on. */
  far: string[]
  /** How many end results it reaches in all, itself included when it is one. */
  ends: number
}

/**
 * What a step leads to along forward edges. The ends are result steps; a flow without any
 * in reach falls back to the steps nothing leaves.
 */
export function reachOf(view: FlowView, stepId: string): Reach {
  const kind = new Map(
    (view.flow.steps ?? []).map((step) => [step.step_id, step.kind])
  )
  const out = new Map<string, string[]>()
  for (const edge of view.layout.forward) {
    if (edge.source === edge.target) continue
    out.set(edge.source, [...(out.get(edge.source) ?? []), edge.target])
  }
  const next = [...new Set(out.get(stepId) ?? [])]
  const seen = new Set([stepId])
  const queue = [stepId]
  const reached: string[] = []
  while (queue.length) {
    const id = queue.shift()!
    for (const target of out.get(id) ?? []) {
      if (seen.has(target)) continue
      seen.add(target)
      reached.push(target)
      queue.push(target)
    }
  }
  const isEnd = kind.get(stepId) === "result"
  let ends = reached.filter((id) => kind.get(id) === "result")
  if (!ends.length && !isEnd)
    ends = reached.filter((id) => !out.get(id)?.length)
  const nearby = new Set(next)
  return {
    next,
    far: ends.filter((id) => !nearby.has(id)),
    ends: ends.length + (isEnd ? 1 : 0),
  }
}

/** Whether a change is one the reader asked to see. */
export function matches(
  item: { risky: boolean; status?: TestStatus },
  filter?: Filter
): boolean {
  if (!filter) return true
  return filter === "risk" ? item.risky : item.status === filter
}

/** What identifies a stop from one opening of the page to the next. */
export function stopKey(stop: Stop): string {
  return stop.change?.change_id ?? `flow:${stop.flowId ?? stop.no}`
}

export function removedNodeId(stepId: string, no: number): string {
  return `removed-${stepId}-${no}`
}

function nodeOf(place: Projection, no: number): string | undefined {
  if (place.status === "projected") return place.step_id
  if (place.status === "removed_step" && place.removed_step)
    return removedNodeId(place.removed_step.step_id, no)
  return undefined
}

function samples(payload: Payload): string[] {
  const texts: string[] = []
  for (const flow of payload.map.flows ?? []) {
    if (flow.stage === "synthesized") {
      texts.push(flow.name, flow.summary ?? "")
      for (const step of flow.steps ?? []) texts.push(step.name)
    } else if (flow.name_from_plan) {
      // Named by the plan: the name and summary are written for the reader.
      texts.push(flow.name, flow.summary ?? "")
    }
  }
  for (const item of payload.report?.changes ?? []) {
    texts.push(item.explanation?.summary ?? "", item.explanation?.effect ?? "")
  }
  for (const finding of payload.map.findings ?? []) {
    if (finding.source === "agent_observation") texts.push(finding.statement)
  }
  return texts
}

export function buildModel(payload: Payload): Model {
  const map = payload.map
  const report = payload.report
  const evidence = new Map<string, EvidenceRef>()
  for (const ref of [...(map.evidence ?? []), ...(report?.evidence ?? [])])
    evidence.set(ref.evidence_id, ref)
  const findings = new Map(
    (map.findings ?? []).map((finding) => [finding.finding_id, finding])
  )
  const findingStatus = new Map<string, FindingChange["status"]>()
  for (const item of report?.finding_changes ?? []) {
    findingStatus.set(item.finding.finding_id, item.status)
    if (!findings.has(item.finding.finding_id))
      findings.set(item.finding.finding_id, item.finding)
  }
  const introduced = new Set(
    [...findingStatus]
      .filter(([, status]) => status === "introduced")
      .map(([id]) => id)
  )

  const view = (flow: MapFlow, removed: boolean): FlowView => {
    const steps = flow.steps ?? []
    const flowFindings = [
      ...(flow.finding_ids ?? []),
      ...steps.flatMap((step) => step.finding_ids ?? []),
    ]
      .map((id) => findings.get(id))
      .filter((item): item is MapFinding => Boolean(item))
    return {
      flow,
      removed,
      layout: layoutRoute(steps, flow.edges ?? []),
      coupons: [],
      byStep: new Map(),
      removedSteps: [],
      newSteps: new Set(),
      findings: flowFindings,
    }
  }

  // Flows in reading order: by domain as the map groups them, then ungrouped.
  const ordered: MapFlow[] = []
  const seen = new Set<string>()
  const allFlows = new Map(
    (map.flows ?? []).map((flow) => [flow.flow_id, flow])
  )
  for (const domain of map.domains ?? []) {
    for (const id of domain.flow_ids) {
      const flow = allFlows.get(id)
      if (flow && !seen.has(id)) {
        ordered.push(flow)
        seen.add(id)
      }
    }
  }
  for (const flow of map.flows ?? [])
    if (!seen.has(flow.flow_id)) ordered.push(flow)
  const removedFlows = report?.removed_flows ?? []
  const flows = [
    ...ordered.map((flow) => view(flow, false)),
    ...removedFlows.map((flow) => view(flow, true)),
  ]
  const flowById = new Map(flows.map((item) => [item.flow.flow_id, item]))

  // A change to test code is counted, never walked through.
  const all = report?.changes ?? []
  const product = all.filter((change) => !isTestChange(change))

  // Deleting an entry yields a removed flow and a change off the map for the same function:
  // one deletion, one stop, kept with the flow.
  const entryOf = new Map<string, string>()
  for (const flow of removedFlows)
    for (const entry of flow.entries ?? [])
      entryOf.set(entry.symbol_id, flow.flow_id)
  const mergedInto = new Map<string, ChangeItem>()
  for (const change of product) {
    const flowId = entryOf.get(change.symbol_id)
    if (
      change.projection.status === "unassigned" &&
      flowId &&
      !mergedInto.has(flowId)
    )
      mergedInto.set(flowId, change)
  }
  const merged = new Set(
    [...mergedInto.values()].map((change) => change.change_id)
  )

  // The walk: changes on the map first, then those off it, then removed flows. Within each,
  // the most urgent first; then the one that reaches more end results; then reading order.
  const rowOf = new Map<string, number>()
  for (const item of flows)
    item.layout.rows.forEach((row, index) => rowOf.set(row.step.step_id, index))
  const flowIndex = new Map(
    flows.map((item, index) => [item.flow.flow_id, index])
  )
  const keyed = product
    .filter((change) => !merged.has(change.change_id))
    .map((change, index) => {
      const place = change.projection
      const home =
        place.status === "unassigned"
          ? undefined
          : flowById.get(place.flow_id ?? "")
      const ends =
        home && place.status === "projected" && place.step_id
          ? reachOf(home, place.step_id).ends
          : 0
      return {
        change,
        key: [
          home ? 0 : 1,
          tierOf(change, introduced),
          -ends,
          home ? (flowIndex.get(home.flow.flow_id) ?? 0) : 0,
          place.status === "projected"
            ? (rowOf.get(place.step_id ?? "") ?? 9999)
            : 10000,
          index,
        ],
      }
    })
    .sort((a, b) => {
      for (let i = 0; i < a.key.length; i++)
        if (a.key[i] !== b.key[i]) return a.key[i] - b.key[i]
      return 0
    })

  const stops: Stop[] = []
  for (const { change } of keyed) {
    const no = stops.length + 1
    const places = [change.projection, ...(change.other_projections ?? [])]
    let primary: Coupon | undefined
    const status = statusOf(change.tests)
    const risky = (change.finding_ids ?? []).some((id) => introduced.has(id))
    const tone: Tone = risky ? "risk" : status
    places.forEach((place, order) => {
      const coupon: Coupon = {
        no,
        change,
        place,
        primary: order === 0,
        risky,
        tone,
      }
      if (order === 0) primary = coupon
      if (place.status === "unassigned") return
      const target = flowById.get(place.flow_id ?? "")
      if (!target) return
      target.coupons.push(coupon)
      if (place.status === "removed_step") target.removedSteps.push(coupon)
      else if (place.step_id)
        target.byStep.set(place.step_id, [
          ...(target.byStep.get(place.step_id) ?? []),
          coupon,
        ])
    })
    const home =
      change.projection.status === "unassigned"
        ? undefined
        : change.projection.flow_id
    const also: Stop["also"] = []
    for (const place of change.other_projections ?? []) {
      const nodeId = nodeOf(place, no)
      if (
        !place.flow_id ||
        place.flow_id === home ||
        !nodeId ||
        !flowById.has(place.flow_id)
      )
        continue
      if (also.some((item) => item.flowId === place.flow_id)) continue
      also.push({ flowId: place.flow_id, nodeId })
    }
    const maybe: string[] = []
    for (const reach of report?.possibly_affected ?? []) {
      if (
        !reach.change_ids.includes(change.change_id) ||
        reach.flow_id === home
      )
        continue
      if (
        !flowById.has(reach.flow_id) ||
        also.some((item) => item.flowId === reach.flow_id)
      )
        continue
      if (!maybe.includes(reach.flow_id)) maybe.push(reach.flow_id)
    }
    const kind: StopKind =
      change.projection.status === "projected"
        ? "step"
        : change.projection.status === "removed_step"
          ? "removed_step"
          : "off_map"
    stops.push({
      no,
      kind,
      change,
      coupon: primary,
      flowId: home,
      nodeId: nodeOf(change.projection, no),
      status,
      risky,
      tone,
      also,
      maybe,
    })
  }
  for (const flow of removedFlows) {
    const no = stops.length + 1
    const change = mergedInto.get(flow.flow_id)
    const risky = (change?.finding_ids ?? []).some((id) => introduced.has(id))
    stops.push({
      no,
      kind: "removed_flow",
      change,
      coupon: change
        ? {
            no,
            change,
            place: change.projection,
            primary: true,
            risky,
            tone: risky ? "risk" : "unsure",
          }
        : undefined,
      flowId: flow.flow_id,
      risky,
      also: [],
      maybe: [],
    })
  }

  // A step is new when every fact it rests on was added by this change.
  const addedAnchors = new Set(
    product
      .filter((item) => ADDED.has(item.kind) && item.after)
      .map((item) => item.after!.anchor)
  )
  for (const item of flows) {
    for (const step of item.flow.steps ?? []) {
      const anchors = step.anchors ?? []
      if (anchors.length && anchors.every((anchor) => addedAnchors.has(anchor)))
        item.newSteps.add(step.step_id)
    }
  }

  const stopsOn = new Map<string, number[]>()
  const add = (into: Map<string, number[]>, flowId: string, no: number) =>
    into.set(flowId, [...(into.get(flowId) ?? []), no])
  for (const stop of stops) {
    if (stop.flowId && stop.kind !== "off_map")
      add(stopsOn, stop.flowId, stop.no)
  }

  const modules: ModuleView[] = []
  const moduleOf = new Map<string, ModuleView>()
  const placed = new Set<string>()
  const shown = flows.filter((item) => !item.removed)
  for (const domain of map.domains ?? []) {
    const members = domain.flow_ids
      .map((id) => flowById.get(id))
      .filter(
        (item): item is FlowView =>
          Boolean(item) && !item!.removed && !placed.has(item!.flow.flow_id)
      )
    if (!members.length) continue
    const module: ModuleView = {
      id: domain.domain_id,
      name: domain.name,
      flows: members,
    }
    modules.push(module)
    for (const item of members) {
      placed.add(item.flow.flow_id)
      moduleOf.set(item.flow.flow_id, module)
    }
  }
  const loose = shown.filter((item) => !placed.has(item.flow.flow_id))
  if (loose.length) {
    const module: ModuleView = { id: "__loose", flows: loose }
    modules.push(module)
    for (const item of loose) moduleOf.set(item.flow.flow_id, module)
  }
  const links = (map.links ?? []).filter(
    (link) =>
      link.source.flow_id !== link.target.flow_id &&
      moduleOf.has(link.source.flow_id) &&
      moduleOf.has(link.target.flow_id)
  )

  return {
    lang: detectLang(samples(payload)),
    share: payload.share,
    payload,
    flows,
    flowById,
    modules,
    moduleOf,
    links,
    stopsOn,
    stops,
    evidence,
    excerpts: payload.excerpts ?? {},
    findingStatus,
    hasReport: Boolean(report),
    counts: {
      stops: stops.length,
      truncated: (report?.limitations ?? []).some(
        (item) => item.code === "changes_truncated"
      ),
      untested: stops.filter((stop) => stop.status === "untested").length,
      unsure: stops.filter((stop) => stop.status === "unsure").length,
      tested: stops.filter((stop) => stop.status === "tested").length,
      risky: stops.filter((stop) => stop.risky).length,
      newRisks: introduced.size,
      files: report?.unanalyzed_changes?.length ?? 0,
      tests: all.length - product.length,
      partial: (report?.analysis_status ?? map.analysis_status) === "partial",
    },
  }
}

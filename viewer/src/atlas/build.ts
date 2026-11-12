import type { Edge, Node } from "@xyflow/react"

import { buildGraph, type FlowEdge, type StepNode } from "@/canvas/graph"
import type { Strings } from "@/i18n"
import type { Coupon, FlowView, Model } from "@/model"
import type { EntryKind } from "@/types"

/**
 * The whole product on one canvas, at a size that reads. Each module is a frame holding its
 * flows. A flow the change touches is drawn cut down to the change: the steps it touches as
 * cards, the step each is reached from as a pill, and a dotted line for whatever lies
 * between. A flow it leaves alone is one row, which says so when changed code is on its
 * way. Opening a module draws every step of its flows. Every frame keeps to one grid: a
 * touched module runs the full width, the others share rows of equal cells under it.
 *
 * A row reads as what the product does: the business processes of a module come first, each
 * under the name and the one sentence the plan gave it, and its lookups and upkeep fold
 * into one line until the module is opened.
 */

export const SEP = "::"
const P = 24
const HEAD_H = 56
const LABEL_H = 44
const FLOW_GAP = 36
const MODULE_GAP = 32
export const OFFMAP_W = 252
const OFFMAP_H = 112
const OFFMAP_GAP = 20
/** The least a frame holds across: one row, or one change outside the flows. */
const ROW_W = 260
const ROW_H = 44
/** A row that also carries the sentence saying what the flow is for. */
const ROW_TALL = 62
const ROW_GAP = 8
const MORE_H = 34

export function stepNodeId(flowId: string, stepId: string): string {
  return `${flowId}${SEP}${stepId}`
}
export function moduleNodeId(id: string): string {
  return `module${SEP}${id}`
}
export function flowOfNode(id: string): string | undefined {
  const index = id.indexOf(SEP)
  return index > 0 ? id.slice(0, index) : undefined
}

export interface ModuleData extends Record<string, unknown> {
  title: string
  changes: number
  flows: number
  apart: boolean
  /** Every step of its flows is drawn. */
  open: boolean
}
export interface LabelData extends Record<string, unknown> {
  flowId: string
  name: string
  code: boolean
  struck: boolean
  changes: number
  /** How many steps the flow has, and how many of them are drawn when it is cut down. */
  steps: number
  shown?: number
  /** What starts the flow: a request, a task, a schedule. */
  entry?: EntryKind
}
/** A flow as one row: untouched by the change, or gone after it. */
export interface RowData extends Record<string, unknown> {
  flowId: string
  name: string
  /** What a user gets done with it, when the row has room for the sentence. */
  summary?: string
  steps: number
  /** Still named after its code. */
  code: boolean
  /** Named by the plan; its steps are not described yet. */
  pending: boolean
  struck: boolean
  entry?: EntryKind
  /** Changes on another flow whose code this one can reach. */
  passing?: number
}
/** The lookups and upkeep of a module, folded into one line until it is opened. */
export interface MoreData extends Record<string, unknown> {
  moduleId: string
  count: number
}
export interface OffMapData extends Record<string, unknown> {
  coupon: Coupon
}
export interface RelationData extends Record<string, unknown> {
  label?: string
  /** The change the line belongs to; it shows only while that change is picked. */
  no?: number
  change: boolean
  candidate: boolean
}

export type ModuleNode = Node<ModuleData, "module">
export type LabelNode = Node<LabelData, "label">
export type OffMapNode = Node<OffMapData, "offmap">
export type RowNode = Node<RowData, "row">
export type MoreNode = Node<MoreData, "more">
export type AtlasNode =
  StepNode | ModuleNode | LabelNode | OffMapNode | RowNode | MoreNode
export type RelationEdge = Edge<RelationData, "relation">
export type AtlasEdge = FlowEdge | RelationEdge

/** A flow placed on the atlas: what is drawn of it and where its steps begin. */
export interface PlacedFlow {
  view: FlowView
  /** One row, the steps a change touches with the way into them, or every step. */
  mode: "row" | "focus" | "full"
  nodes: StepNode[]
  edges: FlowEdge[]
  triggers: string[]
  w: number
  h: number
}

export interface Atlas {
  nodes: AtlasNode[]
  edges: AtlasEdge[]
  flows: Map<string, PlacedFlow>
  /** The module frame each flow sits in. */
  home: Map<string, string>
}

const FIXED = {
  draggable: false,
  connectable: false,
  selectable: false,
  focusable: false,
} as const
/** A node whose size the layout already knows, so it needs no measuring before it shows. */
const sized = (width: number, height: number) => ({
  width,
  height,
  measured: { width, height },
})

/** A flow drawn step by step, renamed so it can share a canvas with every other flow. */
function drawFlow(
  model: Model,
  view: FlowView,
  max: number,
  /** Words the line that stands for steps left out; given, the flow is cut down. */
  between?: (steps: number) => string
): PlacedFlow {
  const flowId = view.flow.flow_id
  const graph = buildGraph(
    view,
    model.findingStatus,
    !model.hasReport,
    max,
    between
  )
  const steps = view.flow.steps ?? []
  const triggerIds = steps
    .filter((step) => step.kind === "trigger")
    .map((step) => step.step_id)
  const firstRow = view.layout.rows[0]?.step.step_id
  const triggers = (
    triggerIds.length ? triggerIds : firstRow ? [firstRow] : []
  ).map((id) => stepNodeId(flowId, id))
  const nodes: StepNode[] = graph.nodes.map((node) => ({
    ...node,
    id: stepNodeId(flowId, node.id),
  }))
  const edges: FlowEdge[] = graph.edges.map((edge) => ({
    ...edge,
    id: stepNodeId(flowId, edge.id),
    source: stepNodeId(flowId, edge.source),
    target: stepNodeId(flowId, edge.target),
  }))
  return {
    view,
    mode: graph.cut ? "focus" : "full",
    nodes,
    edges,
    triggers,
    w: graph.w,
    h: graph.h,
  }
}

function placeFlow(
  model: Model,
  t: Strings,
  view: FlowView,
  open: boolean,
  max: number
): PlacedFlow {
  const flowId = view.flow.flow_id
  // A change counts where it stops, and wherever else the same change lands.
  const touched =
    model.stopsOn.has(flowId) ||
    [...view.byStep.values()].some((coupons) => coupons.length > 0)
  // A flow the agent has not described yet would only show code; with no change on it, it
  // stays one row that names it.
  const undescribed =
    view.flow.stage === "skeleton" && !view.removed && !touched
  // Until its module is opened, a flow shows of itself what the change is about.
  if (!undescribed && (open || (touched && !view.removed)))
    return drawFlow(model, view, max, open ? undefined : t.stepsBetween)
  return {
    view,
    mode: "row",
    nodes: [],
    edges: [],
    triggers: [`row${SEP}${flowId}`],
    w: ROW_W,
    h: planned(view) && view.flow.summary ? ROW_TALL : ROW_H,
  }
}

/** A flow the plan has named and nobody has described yet. */
function planned(view: FlowView): boolean {
  return view.flow.stage === "skeleton" && view.flow.name_from_plan === true
}
/** Still named after its code: a route or a function, not what a person would call it. */
function codeNamed(view: FlowView): boolean {
  return view.flow.stage === "skeleton" && !view.flow.name_from_plan
}
const supporting = (flow: PlacedFlow) =>
  flow.view.flow.tier === "supporting" && !flow.view.removed

/**
 * The atlas. `open` names the module frame whose flows are drawn step by step; `span` is
 * how wide the map may run, so it fits the reader's screen at a size that reads.
 */
export function buildAtlas(
  model: Model,
  t: Strings,
  open?: string,
  span = 1400
): Atlas {
  const flows = new Map<string, PlacedFlow>()
  const home = new Map<string, string>()
  // Changes that sit on another flow and are within reach of this one.
  const passing = new Map<string, number>()
  for (const stop of model.stops)
    for (const flowId of stop.maybe)
      passing.set(flowId, (passing.get(flowId) ?? 0) + 1)
  const changesOn = (views: FlowView[]) =>
    views.reduce(
      (sum, view) => sum + (model.stopsOn.get(view.flow.flow_id)?.length ?? 0),
      0
    )

  /** A module before it has a place: what it needs across, and how to draw its inside. */
  interface Block {
    id: string
    title: string
    apart: boolean
    changes: number
    flows: number
    ids: string[]
    /** Some flow in it is drawn out, so it takes a row of its own. */
    drawn: boolean
    need: number
    build: (inner: number) => {
      nodes: AtlasNode[]
      edges: AtlasEdge[]
      h: number
    }
  }
  const measure = (
    id: string,
    title: string,
    apart: boolean,
    views: FlowView[],
    offMap: Coupon[]
  ): Block => {
    const placed = views
      .map((view) => {
        const flow = placeFlow(model, t, view, id === open, span - 2 * P)
        flows.set(view.flow.flow_id, flow)
        home.set(view.flow.flow_id, id)
        return flow
      })
      // The business processes before the lookups and upkeep around them.
      .sort((a, b) => Number(supporting(a)) - Number(supporting(b)))
    // What is drawn comes first, the rows after it.
    const drawn = placed.filter((flow) => flow.mode !== "row")
    const every = placed.filter((flow) => flow.mode === "row")
    // Until the module is opened its lookups and upkeep are one line, unless it has
    // nothing else to show.
    const folded =
      id !== open && every.some((flow) => !supporting(flow))
        ? every.filter(supporting)
        : []
    const rows = every.filter((flow) => !folded.includes(flow))
    const cards = Math.min(offMap.length, 3)
    const need = Math.max(
      ROW_W,
      ...drawn.map((flow) => flow.w),
      cards * (OFFMAP_W + OFFMAP_GAP) - OFFMAP_GAP
    )
    const rowOf = (
      flow: PlacedFlow,
      x: number,
      y: number,
      w: number,
      h = ROW_H
    ): RowNode => ({
      id: flow.triggers[0],
      type: "row",
      position: { x, y },
      ...sized(w, h),
      draggable: false,
      connectable: false,
      selectable: false,
      data: {
        flowId: flow.view.flow.flow_id,
        name: flow.view.flow.name,
        summary: h > ROW_H ? flow.view.flow.summary : undefined,
        steps: flow.view.flow.steps?.length ?? 0,
        code: codeNamed(flow.view),
        pending: planned(flow.view),
        struck: flow.view.removed,
        entry: flow.view.flow.entries[0]?.kind,
        passing: passing.get(flow.view.flow.flow_id),
      },
    })
    // What is outside the flows runs as one strip: its changes, then the flows that are
    // gone, side by side.
    const strip = (inner: number) => {
      const nodes: AtlasNode[] = []
      let x = 0
      let y = HEAD_H
      const put = (w: number) => {
        if (x > 0 && x + w > inner) {
          x = 0
          y += OFFMAP_H + OFFMAP_GAP
        }
        const at = { x: P + x, y }
        x += w + OFFMAP_GAP
        return at
      }
      for (const coupon of offMap) {
        const at = put(OFFMAP_W)
        nodes.push({
          id: `offmap${SEP}${coupon.no}`,
          type: "offmap",
          position: at,
          ...sized(OFFMAP_W, OFFMAP_H),
          draggable: false,
          connectable: false,
          selectable: false,
          data: { coupon },
        })
      }
      for (const flow of rows) {
        const at = put(ROW_W)
        nodes.push(rowOf(flow, at.x, at.y + (OFFMAP_H - ROW_H) / 2, ROW_W))
      }
      return { nodes, edges: [] as AtlasEdge[], h: y + OFFMAP_H + P }
    }
    const build = (inner: number) => {
      if (apart && !drawn.length && offMap.length) return strip(inner)
      const nodes: AtlasNode[] = []
      const edges: AtlasEdge[] = []
      let y = HEAD_H
      let gap = 0
      for (const flow of drawn) {
        y += gap
        const view = flow.view
        nodes.push({
          id: `label${SEP}${view.flow.flow_id}`,
          type: "label",
          position: { x: P, y },
          ...sized(inner, LABEL_H),
          ...FIXED,
          data: {
            flowId: view.flow.flow_id,
            name: view.flow.name,
            code: codeNamed(view),
            struck: view.removed,
            changes: model.stopsOn.get(view.flow.flow_id)?.length ?? 0,
            steps: view.flow.steps?.length ?? 0,
            shown:
              flow.mode === "focus"
                ? flow.nodes.filter((node) => !node.data.ghost).length
                : undefined,
            entry: view.flow.entries[0]?.kind,
          },
        })
        for (const node of flow.nodes) {
          node.position = {
            x: node.position.x + P,
            y: node.position.y + y + LABEL_H,
          }
          nodes.push(node)
        }
        edges.push(...flow.edges)
        y += LABEL_H + flow.h
        gap = FLOW_GAP
      }
      if (offMap.length) {
        y += gap
        // Changes outside the flows, as many to a line as the frame holds.
        const perLine = Math.max(
          1,
          Math.floor((inner + OFFMAP_GAP) / (OFFMAP_W + OFFMAP_GAP))
        )
        offMap.forEach((coupon, index) =>
          nodes.push({
            id: `offmap${SEP}${coupon.no}`,
            type: "offmap",
            position: {
              x: P + (index % perLine) * (OFFMAP_W + OFFMAP_GAP),
              y: y + Math.floor(index / perLine) * (OFFMAP_H + OFFMAP_GAP),
            },
            ...sized(OFFMAP_W, OFFMAP_H),
            draggable: false,
            connectable: false,
            selectable: false,
            data: { coupon },
          })
        )
        const lines = Math.ceil(offMap.length / perLine)
        y += lines * (OFFMAP_H + OFFMAP_GAP) - OFFMAP_GAP
        gap = FLOW_GAP
      }
      rows.forEach((flow, index) => {
        y += index ? ROW_GAP : gap ? gap - 12 : 0
        nodes.push(rowOf(flow, P, y, inner, flow.h))
        y += flow.h
      })
      if (folded.length) {
        y += rows.length ? ROW_GAP : gap ? gap - 12 : 0
        nodes.push({
          id: `more${SEP}${id}`,
          type: "more",
          position: { x: P, y },
          ...sized(inner, MORE_H),
          draggable: false,
          connectable: false,
          selectable: false,
          data: { moduleId: id, count: folded.length },
        })
        y += MORE_H
      }
      return { nodes, edges, h: y + P }
    }
    return {
      id,
      title,
      apart,
      changes: changesOn(views) + offMap.length,
      flows: views.length,
      ids: views.map((view) => view.flow.flow_id),
      // Changes outside the flows are changes: they keep a row of their own too.
      drawn: drawn.length > 0 || (apart && offMap.length > 0),
      need,
      build,
    }
  }

  const blocks: Block[] = model.modules.map((module) =>
    measure(
      moduleNodeId(module.id),
      module.name ?? t.looseFlows,
      false,
      module.flows,
      []
    )
  )
  const removed = model.flows.filter((view) => view.removed)
  const offMap = model.stops
    .filter((stop) => stop.kind === "off_map" && stop.coupon)
    .map((stop) => stop.coupon!)
  if (removed.length || offMap.length)
    blocks.push(
      measure(moduleNodeId("__apart"), t.offMapCard, true, removed, offMap)
    )
  // What this change touches comes first, so the first look lands on it.
  blocks.sort((a, b) => Number(b.changes > 0) - Number(a.changes > 0))
  const wide = blocks.filter((block) => block.drawn)
  const cells = blocks.filter((block) => !block.drawn)

  // One width for the whole map: what the drawn flows need, and room for up to four
  // cells side by side, but no wider than the screen shows at a size that reads.
  const cell = ROW_W + 2 * P
  const across = Math.min(cells.length, 4)
  const room = across * cell + Math.max(across - 1, 0) * MODULE_GAP
  const full = Math.max(
    Math.min(Math.max(...wide.map((block) => block.need + 2 * P), room), span),
    cell
  )

  const nodes: AtlasNode[] = []
  const edges: AtlasEdge[] = []
  const frame = (block: Block, x: number, y: number, w: number, h?: number) => {
    const inside = block.build(w - 2 * P)
    const height = h ?? inside.h
    nodes.push({
      id: block.id,
      type: "module",
      position: { x, y },
      ...sized(w, height),
      zIndex: -1,
      ...FIXED,
      data: {
        title: block.title,
        changes: block.changes,
        flows: block.flows,
        apart: block.apart,
        open: block.id === open,
      },
    })
    for (const node of inside.nodes) {
      node.position = { x: node.position.x + x, y: node.position.y + y }
      nodes.push(node)
    }
    edges.push(...inside.edges)
    return height
  }
  let y = 0
  // A module with flows drawn out takes the full width; an opened one may run past it.
  for (const block of wide)
    y += frame(block, 0, y, Math.max(full, block.need + 2 * P)) + MODULE_GAP

  // The rest share rows of equal cells, each row as tall as its tallest cell.
  const fit = Math.max(
    1,
    Math.min(
      cells.length,
      Math.floor((full + MODULE_GAP) / (cell + MODULE_GAP))
    )
  )
  // As many columns as fit, then no more than the rows need, so the rows come out even.
  const columns = Math.ceil(cells.length / Math.ceil(cells.length / fit)) || 1
  const cellW = (full - (columns - 1) * MODULE_GAP) / columns
  const widthOf = (count: number) => count * cellW + (count - 1) * MODULE_GAP
  let row: { block: Block; at: number; over: number }[] = []
  let used = 0
  const flush = () => {
    if (!row.length) return
    // Every row ends on the same line: a short row shares the width out evenly, or its
    // last cell runs to the edge.
    const even = row.every((item) => item.over === 1)
    const share = (full - (row.length - 1) * MODULE_GAP) / row.length
    if (!even) row[row.length - 1].over += columns - used
    const place = row.map((item, index) => ({
      block: item.block,
      x: even ? index * (share + MODULE_GAP) : item.at * (cellW + MODULE_GAP),
      w: even ? share : widthOf(item.over),
    }))
    const height = Math.max(
      ...place.map((item) => item.block.build(item.w - 2 * P).h)
    )
    for (const item of place) frame(item.block, item.x, y, item.w, height)
    y += height + MODULE_GAP
    row = []
    used = 0
  }
  for (const block of cells) {
    let over = 1
    while (over < columns && widthOf(over) < block.need + 2 * P) over += 1
    if (used + over > columns) flush()
    row.push({ block, at: used, over })
    used += over
  }
  flush()

  // Where else a change sits. A flow that only reaches the changed code says so on its row.
  const has = new Set(nodes.map((node) => node.id))
  const named = (label: string, flowId: string) => {
    const name = model.flowById.get(flowId)?.flow.name ?? ""
    const chars = [...name]
    const short = chars.length > 16 ? chars.slice(0, 15).join("") + "…" : name
    return short ? `${label} · ${short}` : label
  }
  for (const stop of model.stops) {
    if (stop.kind !== "step" || !stop.flowId || !stop.nodeId) continue
    const from = stepNodeId(stop.flowId, stop.nodeId)
    if (!has.has(from)) continue
    for (const item of stop.also) {
      const to = stepNodeId(item.flowId, item.nodeId)
      if (has.has(to))
        edges.push(
          relation(
            `also${SEP}${stop.no}${SEP}${to}`,
            from,
            to,
            named(t.sameChange, item.flowId),
            true,
            false,
            stop.no
          )
        )
    }
  }
  for (const link of model.links) {
    const source = flows.get(link.source.flow_id)
    const target = flows.get(link.target.flow_id)
    if (!source || !target) continue
    const from = link.source.step_id
      ? stepNodeId(link.source.flow_id, link.source.step_id)
      : source.triggers[0]
    const to = link.target.step_id
      ? stepNodeId(link.target.flow_id, link.target.step_id)
      : target.triggers[0]
    if (from && to && has.has(from) && has.has(to))
      edges.push(
        relation(
          `link${SEP}${link.link_id}`,
          from,
          to,
          link.name,
          false,
          link.resolution === "candidate"
        )
      )
  }
  return { nodes, edges, flows, home }
}

function relation(
  id: string,
  source: string,
  target: string,
  label: string,
  change: boolean,
  candidate = false,
  no?: number
): RelationEdge {
  return {
    id,
    type: "relation",
    source,
    target,
    sourceHandle: "rel-out",
    targetHandle: "rel-in",
    focusable: false,
    // Over the cards: it shows only while its change is picked, and must not hide then.
    zIndex: change ? 6 : undefined,
    data: { label, change, candidate, no },
  }
}

/**
 * The way through a flow worth watching: from its trigger, at each decision the branch that
 * passes the most changes, then the one off the error path, then the longer one.
 */
export function mainPath(
  flow: Pick<PlacedFlow, "nodes" | "edges" | "triggers">
): {
  steps: string[]
  edges: string[]
} {
  const start = flow.triggers[0]
  if (!start) return { steps: [], edges: [] }
  const changed = new Set(
    flow.nodes.filter((node) => node.data.coupons.length).map((node) => node.id)
  )
  const out = new Map<string, FlowEdge[]>()
  for (const edge of flow.edges)
    if (!edge.data?.back)
      out.set(edge.source, [...(out.get(edge.source) ?? []), edge])
  interface Best {
    changes: number
    errors: number
    length: number
    edge?: FlowEdge
  }
  const memo = new Map<string, Best>()
  const better = (a: Best, b: Best) =>
    a.changes !== b.changes
      ? a.changes > b.changes
      : a.errors !== b.errors
        ? a.errors < b.errors
        : a.length > b.length
  const best = (id: string, trail: Set<string>): Best => {
    const known = memo.get(id)
    if (known) return known
    let pick: Best = { changes: 0, errors: 0, length: 0 }
    for (const edge of out.get(id) ?? []) {
      if (trail.has(edge.target)) continue
      trail.add(edge.target)
      const rest = best(edge.target, trail)
      trail.delete(edge.target)
      const next: Best = {
        changes: rest.changes + (changed.has(edge.target) ? 1 : 0),
        errors: rest.errors + (edge.data?.exception ? 1 : 0),
        length: rest.length + 1,
        edge,
      }
      if (!pick.edge || better(next, pick)) pick = next
    }
    memo.set(id, pick)
    return pick
  }
  best(start, new Set([start]))
  const steps = [start]
  const edges: string[] = []
  const seen = new Set(steps)
  let at = start
  for (;;) {
    const edge = memo.get(at)?.edge
    if (!edge || seen.has(edge.target)) break
    edges.push(edge.id)
    steps.push(edge.target)
    seen.add(edge.target)
    at = edge.target
  }
  return { steps, edges }
}

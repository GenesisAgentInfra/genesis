import type { Node } from "@xyflow/react"

import {
  buildGraph,
  graphOfDrawing,
  type CutWords,
  type FlowEdge,
  type StepNode,
} from "@/canvas/graph"
import type { FlowGraph } from "@/flow-graph"
import type { Strings } from "@/i18n"
import type { Coupon, FlowView, Model, Tone } from "@/model"
import { TONES } from "@/model"
import type { EntryKind } from "@/types"

/**
 * One canvas with a consistent diagram for every synthesized live flow. Changed flows
 * may fold intermediate steps while preserving decisions and outcomes. Only removed or
 * undescribed flows use compact rows. Opening a module reveals every intermediate step.
 */

export const SEP = "::"
const P = 0
/** The room a module's heading takes over its first flow. */
export const HEAD_H = 60
/** A drawn flow sits on a card of its own: its name in the head, its steps inset below. */
export const CARD_HEAD = 52
const CARD_X = 20
const CARD_B = 20
const FLOW_GAP = 20
const MODULE_GAP = 64
const OFFMAP_W = 252
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
/** What the changes on no flow go by, where a flow's id is asked for. */
export const OFF_MAP = "__offmap"
/** The frame that holds them, with the flows that are gone. */
export const APART = moduleNodeId("__apart")

export interface ModuleData extends Record<string, unknown> {
  title: string
  changes: number
  flows: number
  apart: boolean
  /** Every step of its flows is drawn. */
  open: boolean
  /** It runs the full width, with a flow drawn out in it. */
  wide: boolean
  /** The most pressing colour among the changes in it. */
  tone?: Tone
}
/** The card a drawn flow sits on, with its name at the head. */
export interface FlowCardData extends Record<string, unknown> {
  flowId: string
  name: string
  code: boolean
  struck: boolean
  changes: number
  /** The most pressing colour among the changes on it. */
  tone?: Tone
}
/** A flow as one row: not described yet, or gone after it. */
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
  /** The stop a flow that is gone goes by. */
  no?: number
}
/** The lookups and upkeep of a module, folded into one line until it is opened. */
export interface MoreData extends Record<string, unknown> {
  moduleId: string
  count: number
}
export interface OffMapData extends Record<string, unknown> {
  coupon: Coupon
}
/** The dashed box a flow's error path runs in. */
export interface BoxData extends Record<string, unknown> {
  flowId: string
}
/** The most pressing of some colours: a new risk before no test, and so on down. */
function worst(tones: (Tone | undefined)[]): Tone | undefined {
  return TONES.find((tone) => tones.includes(tone))
}
export type ModuleNode = Node<ModuleData, "module">
export type FlowCardNode = Node<FlowCardData, "flow">
export type OffMapNode = Node<OffMapData, "offmap">
export type RowNode = Node<RowData, "row">
export type MoreNode = Node<MoreData, "more">
export type BoxNode = Node<BoxData, "box">
export type AtlasNode =
  | StepNode
  | ModuleNode
  | FlowCardNode
  | OffMapNode
  | RowNode
  | MoreNode
  | BoxNode
type AtlasEdge = FlowEdge

/**
 * A flow placed on the atlas: what is drawn of it and where its steps begin. Its nodes and
 * lines keep the flow's own coordinates; the atlas holds the copies set down on the canvas.
 */
export interface PlacedFlow {
  view: FlowView
  /** One row, the steps a change touches with the way into them, or every step. */
  mode: "row" | "focus" | "full"
  nodes: StepNode[]
  edges: FlowEdge[]
  /** What is drawn of it, as a graph to travel, in the ids of the canvas. */
  graph: FlowGraph<FlowEdge>
  /** The boxes its error path runs in, drawn under its steps. */
  boxes: BoxNode[]
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

/** The map with each module open, or with none: each drawn once, when first asked for. */
export function atlasDrawer(
  model: Model,
  t: Strings,
  span?: number
): (open?: string) => Atlas {
  const drawn = new Map<string | undefined, Atlas>()
  return (open) => {
    if (!drawn.has(open)) drawn.set(open, buildAtlas(model, t, open, span))
    return drawn.get(open)!
  }
}

/** The flow something on the map belongs to (`OFF_MAP` for a change on no flow). */
export function flowIdOf(node: AtlasNode): string | undefined {
  if (node.type === "step") return flowOfNode(node.id)
  if (node.type === "offmap") return OFF_MAP
  if (node.type === "flow" || node.type === "row")
    return node.data.flowId || undefined
  return undefined
}
/** The module frame something on the map sits in. */
export function homeOf(atlas: Atlas, node: AtlasNode): string | undefined {
  if (node.type === "more") return node.data.moduleId
  const flowId = flowIdOf(node)
  return flowId === OFF_MAP ? APART : atlas.home.get(flowId ?? "")
}
/** The flows that sit in a module frame. */
export function flowsIn(atlas: Atlas, module: string): Set<string> {
  const inside = new Set(module === APART ? [OFF_MAP] : [])
  for (const [flowId, home] of atlas.home)
    if (home === module) inside.add(flowId)
  return inside
}

const FIXED = {
  draggable: false,
  connectable: false,
  selectable: false,
  focusable: false,
} as const
/** A node set down further on, as a copy: what it was built from keeps its own place. */
const movedNode = <N extends AtlasNode>(
  node: N,
  dx: number,
  dy: number
): N => ({
  ...node,
  position: { x: node.position.x + dx, y: node.position.y + dy },
})
/** A line set down further on with everything the layout drew of it. */
const movedEdge = (edge: AtlasEdge, dx: number, dy: number): AtlasEdge =>
  edge.data
    ? {
        ...edge,
        data: {
          ...edge.data,
          points: edge.data.points?.map((point) => ({
            x: point.x + dx,
            y: point.y + dy,
          })),
          labelAt: edge.data.labelAt && {
            x: edge.data.labelAt.x + dx,
            y: edge.data.labelAt.y + dy,
          },
        },
      }
    : edge

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
  /** Words what stands for steps left out; given, the flow is cut down. */
  words?: CutWords
): PlacedFlow {
  const flowId = view.flow.flow_id
  const graph = buildGraph(
    view,
    model.findingStatus,
    !model.hasReport,
    max,
    words
  )
  const steps = view.flow.steps ?? []
  const triggerIds = steps
    .filter((step) => step.kind === "trigger")
    .map((step) => step.step_id)
  const firstRow = view.graph.order[0]
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
  const boxes: BoxNode[] = graph.boxes.map((box, index) => ({
    id: `box${SEP}${flowId}${SEP}${index}`,
    type: "box",
    position: { x: box.x, y: box.y },
    ...sized(box.w, box.h),
    zIndex: -1,
    style: { pointerEvents: "none" },
    ...FIXED,
    data: { flowId },
  }))
  // The drawn steps in the flow's own reading order, then what stands for steps left out.
  const reading = new Map(view.graph.order.map((id, at) => [id, at]))
  const inOrder = [...graph.nodes]
    .sort(
      (a, b) =>
        (reading.get(a.id) ?? Infinity) - (reading.get(b.id) ?? Infinity)
    )
    .map((node) => ({ ...node, id: stepNodeId(flowId, node.id) }))
  return {
    view,
    mode: graph.cut ? "focus" : "full",
    nodes,
    edges,
    graph: graphOfDrawing(inOrder, edges),
    boxes,
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
  if (!undescribed && !view.removed)
    return drawFlow(
      model,
      view,
      max,
      open || !touched
        ? undefined
        : { between: t.stepsBetween, more: t.stepsMore }
    )
  return {
    view,
    mode: "row",
    nodes: [],
    edges: [],
    graph: graphOfDrawing([], []),
    boxes: [],
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
    tone?: Tone
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
      ...drawn.map((flow) => flow.w + 2 * CARD_X),
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
        no: flow.view.removed
          ? model.stops.find(
              (stop) =>
                stop.kind === "removed_flow" &&
                stop.flowId === flow.view.flow.flow_id
            )?.no
          : undefined,
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
        const height = CARD_HEAD + flow.h + CARD_B
        nodes.push({
          id: `flow${SEP}${view.flow.flow_id}`,
          type: "flow",
          position: { x: P, y },
          ...sized(inner, height),
          // Under the lines and the steps; only its head takes a click.
          zIndex: -1,
          style: { pointerEvents: "none" },
          ...FIXED,
          data: {
            flowId: view.flow.flow_id,
            name: view.flow.name,
            code: codeNamed(view),
            struck: view.removed,
            changes: model.stopsOn.get(view.flow.flow_id)?.length ?? 0,
            tone: worst(view.coupons.map((coupon) => coupon.tone)),
          },
        })
        // The flow keeps its drawing in its own coordinates; the card gets a copy in place.
        const dx = P + CARD_X
        const dy = y + CARD_HEAD
        for (const node of [...flow.boxes, ...flow.nodes])
          nodes.push(movedNode(node, dx, dy))
        for (const edge of flow.edges) edges.push(movedEdge(edge, dx, dy))
        y += height
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
      tone: worst([
        ...views.flatMap((view) => view.coupons.map((coupon) => coupon.tone)),
        ...offMap.map((coupon) => coupon.tone),
      ]),
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
    blocks.push(measure(APART, t.offMapCard, true, removed, offMap))
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
      style: { pointerEvents: "none" },
      ...FIXED,
      data: {
        title: block.title,
        changes: block.changes,
        flows: block.flows,
        apart: block.apart,
        open: block.id === open,
        wide: block.drawn,
        tone: block.tone,
      },
    })
    for (const node of inside.nodes) nodes.push(movedNode(node, x, y))
    for (const edge of inside.edges) edges.push(movedEdge(edge, x, y))
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

  return { nodes, edges, flows, home }
}

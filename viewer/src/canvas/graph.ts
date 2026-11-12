import dagre from "@dagrejs/dagre"
import type { Edge, Node } from "@xyflow/react"

import { edgeLabel } from "@/layout"
import { cutFlow } from "./focus"
import { removedNodeId, type Coupon, type FlowView } from "@/model"
import type { FindingChange, MapStep } from "@/types"

/**
 * A flow drawn left to right: a step the change leaves alone is a small pill, a step it
 * touches is a card that says what changed. Steps of one rank share a column, a branch is
 * named on its line, and every line runs at right angles in the gaps between columns.
 * A flow too long for the width it is given wraps onto a second band, like a line of text.
 *
 * Drawn for a change, a flow shows only the steps the change touches and the way into each
 * of them; a dotted line stands for the steps left out in between (see `cutFlow`).
 */

export const CARD_W = 216
const PILL_H = 44
/** Between two steps of one column, and the least between two columns. */
const NODE_SEP = 16
const COL_GAP = 40
/** How far past a column a line runs before it turns, and between two lines turning there. */
const TURN = 14
const LANE = 8
const BAND_GAP = 48
const GHOST_GAP = 28
/** A card for a step the change removed: its name and what was said about it. */
const GHOST_H = 172

export interface Point {
  x: number
  y: number
}

export interface StepNodeData extends Record<string, unknown> {
  step: MapStep
  coupons: Coupon[]
  isNew: boolean
  risk?: "new" | "known"
  ghost: boolean
  loops: { label: string }[]
  removedFlow: boolean
  skeleton: boolean
  /** A step with nothing to say but its name, drawn as a pill. */
  compact: boolean
  width: number
  hasIn: boolean
  hasOut: boolean
  /** The height of its place in the column; the card sits in the middle of it. */
  slot: number
}

export interface FlowEdgeData extends Record<string, unknown> {
  label?: string
  exception: boolean
  uncertain: boolean
  back: boolean
  /** The line stands for this many steps that are not drawn. */
  skipped?: number
  /** The corners of the line, as offsets from where it leaves its source. */
  route?: Point[]
  /** Where its label sits, as an offset from the same point. */
  labelAt?: Point
}

export type StepNode = Node<StepNodeData, "step">
export type FlowEdge = Edge<FlowEdgeData, "flow">

function textWidth(text: string, cjk = 13.5, latin = 7.4): number {
  let width = 0
  for (const char of text)
    width += /[\u3000-\u9fff\uff00-\uffef]/.test(char) ? cjk : latin
  return width
}
/** A label on a line: a small pill. */
const labelWidth = (text: string) => Math.ceil(textWidth(text, 11.5, 6.4)) + 18

export function heightOf(data: StepNodeData): number {
  if (data.compact) return PILL_H
  let height = 68
  if (data.coupons.length) height += 104
  if (data.loops.length) height += 24
  return height
}

export function buildGraph(
  view: FlowView,
  findingStatus: Map<string, FindingChange["status"]>,
  /** Risks that were already there show on cards (only with no report to walk). */
  knownRisks: boolean,
  /** How wide the flow may run before it wraps onto another band. */
  max = Infinity,
  /**
   * Given, the flow is cut down to the steps the change touches and the way into each;
   * it words the line that stands for the steps left out.
   */
  between?: (steps: number) => string
): {
  nodes: StepNode[]
  edges: FlowEdge[]
  w: number
  h: number
  /** Whether steps were left out. */
  cut: boolean
} {
  const steps = view.flow.steps ?? []
  const ids = new Set(steps.map((step) => step.step_id))
  const edges = (view.flow.edges ?? []).filter(
    (edge) => ids.has(edge.source) && ids.has(edge.target)
  )
  const keyOf = view.layout.edgeKey
  const forward = new Set(view.layout.forward)

  const findings = new Set(view.findings.map((finding) => finding.finding_id))
  let nodes: StepNode[] = steps.map((step) => {
    const coupons = view.byStep.get(step.step_id) ?? []
    const loops = edges
      .filter(
        (edge) => edge.source === step.step_id && edge.target === step.step_id
      )
      .map((edge) => ({ label: edgeLabel(edge) ?? "" }))
    const outgoing = edges.filter(
      (edge) => edge.source === step.step_id && edge.target !== step.step_id
    )
    const incoming = edges.filter(
      (edge) => edge.target === step.step_id && edge.source !== step.step_id
    )
    const stepFindings = (step.finding_ids ?? []).filter((id) =>
      findings.has(id)
    )
    const risk: StepNodeData["risk"] = stepFindings.length
      ? stepFindings.some((id) => findingStatus.get(id) === "introduced")
        ? "new"
        : "known"
      : undefined
    const isNew = view.newSteps.has(step.step_id)
    // A pill has room for its name only, so a step with a badge to show keeps its card.
    const badged =
      isNew ||
      step.resolution !== "resolved" ||
      risk === "new" ||
      (risk === "known" && knownRisks)
    const compact = !coupons.length && !loops.length && !badged
    const data: StepNodeData = {
      step,
      coupons,
      isNew,
      risk,
      ghost: false,
      loops,
      removedFlow: view.removed,
      skeleton: view.flow.stage === "skeleton",
      compact,
      width: compact
        ? Math.min(236, Math.max(120, 68 + Math.ceil(textWidth(step.name))))
        : CARD_W,
      hasIn: incoming.length > 0,
      hasOut: outgoing.length > 0,
      slot: 0,
    }
    data.slot = heightOf(data)
    return {
      id: step.step_id,
      type: "step",
      position: { x: 0, y: 0 },
      draggable: false,
      connectable: false,
      data,
    }
  })

  let flowEdges: FlowEdge[] = edges
    .filter((edge) => edge.target !== edge.source)
    .map((edge) => ({
      id: keyOf.get(edge) ?? `${edge.source}>${edge.target}`,
      type: "flow",
      source: edge.source,
      target: edge.target,
      sourceHandle: "out",
      targetHandle: "in",
      focusable: false,
      data: {
        label: edgeLabel(edge),
        exception: edge.relation === "exception",
        uncertain: edge.resolution !== "resolved",
        back: !forward.has(edge),
      },
    }))

  const cut = between
    ? cutFlow(
        steps,
        view.layout,
        new Set(
          nodes
            .filter(
              ({ data }) =>
                data.coupons.length > 0 || data.isNew || data.risk === "new"
            )
            .map((node) => node.id)
        )
      )
    : undefined
  if (cut && cut.keep.size < nodes.length) {
    nodes = nodes.filter((node) => cut.keep.has(node.id))
    flowEdges = flowEdges.filter(
      (edge) => cut.keep.has(edge.source) && cut.keep.has(edge.target)
    )
    for (const skip of cut.skips) {
      const count = between!(skip.steps)
      flowEdges.push({
        id: `skip>${skip.source}>${skip.target}`,
        type: "flow",
        source: skip.source,
        target: skip.target,
        sourceHandle: "out",
        targetHandle: "in",
        focusable: false,
        data: {
          label: skip.label ? `${skip.label} · ${count}` : count,
          exception: skip.exception,
          uncertain: false,
          back: false,
          skipped: skip.steps,
        },
      })
    }
    // A step keeps a handle only where a line still meets it.
    for (const node of nodes) {
      node.data.hasIn = flowEdges.some((edge) => edge.target === node.id)
      node.data.hasOut = flowEdges.some((edge) => edge.source === node.id)
    }
  }

  const gone = view.removedSteps.filter((coupon) => coupon.place.removed_step)
  const run = gone.length * (CARD_W + 20) - 20
  const size = arrange(
    nodes,
    flowEdges,
    max,
    gone.length ? { w: run, h: GHOST_H } : undefined
  )

  // Steps the change removed have no place among the current ones: they wait after the
  // end of the flow when there is room beside its last band, else in a row below.
  let h = size.h
  let w = size.w
  const beside =
    gone.length > 0 && nodes.length > 0 && size.tail.x + 40 + run <= max
  const below = nodes.length ? size.h + GHOST_GAP : 0
  gone.forEach((coupon, index) => {
    const removed = coupon.place.removed_step
    if (!removed) return
    const data: StepNodeData = {
      step: {
        step_id: removed.step_id,
        name: removed.name,
        kind: "action",
        support: "agent_synthesis",
        resolution: "resolved",
      },
      coupons: [coupon],
      isNew: false,
      ghost: true,
      loops: [],
      removedFlow: false,
      skeleton: false,
      compact: false,
      width: CARD_W,
      hasIn: false,
      hasOut: false,
      slot: 0,
    }
    data.slot = heightOf(data)
    const at = size.spot
      ? { x: size.spot.x + index * (CARD_W + 20), y: size.spot.y }
      : beside
        ? {
            x: size.tail.x + 40 + index * (CARD_W + 20),
            y: Math.max(
              0,
              Math.min(
                (size.tail.top + size.tail.bottom - data.slot) / 2,
                size.h - data.slot
              )
            ),
          }
        : { x: index * (CARD_W + 20), y: below }
    nodes.push({
      id: removedNodeId(removed.step_id, coupon.no),
      type: "step",
      position: at,
      draggable: false,
      connectable: false,
      data,
    })
    h = Math.max(h, at.y + data.slot)
    w = Math.max(w, at.x + CARD_W)
  })
  return {
    nodes,
    edges: flowEdges,
    w: Math.max(w, 120),
    h,
    cut: nodes.length - gone.length < steps.length,
  }
}

/**
 * Places the steps and routes the lines. dagre decides which column a step is in, the order
 * down a column and the lane a long line keeps to as it passes other columns; the rest is
 * a grid: columns as wide as their widest step, gaps as wide as the labels and turns in them
 * need, and bands of columns wrapped to the width given.
 */
function arrange(
  nodes: StepNode[],
  edges: FlowEdge[],
  max: number,
  /** Something to set down in a free corner of the last band, if one is large enough. */
  extra?: { w: number; h: number }
): {
  w: number
  h: number
  tail: { x: number; top: number; bottom: number }
  spot?: Point
} {
  if (!nodes.length) return { w: 0, h: 0, tail: { x: 0, top: 0, bottom: 0 } }
  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: "LR", nodesep: NODE_SEP, ranksep: 80 })
  graph.setDefaultEdgeLabel(() => ({}))
  for (const node of nodes)
    graph.setNode(node.id, { width: node.data.width, height: node.data.slot })
  const lines = edges.filter((edge) => !edge.data?.back)
  for (const edge of lines) graph.setEdge(edge.source, edge.target)
  dagre.layout(graph)

  // Columns: steps that dagre gave the same centre.
  const centres = [
    ...new Set(nodes.map((node) => Math.round(graph.node(node.id).x))),
  ].sort((a, b) => a - b)
  const rankOf = new Map(
    nodes.map((node) => [
      node.id,
      centres.indexOf(Math.round(graph.node(node.id).x)),
    ])
  )
  const ranks = centres.length
  const colW = Array.from({ length: ranks }, () => 0)
  for (const node of nodes) {
    const rank = rankOf.get(node.id)!
    colW[rank] = Math.max(colW[rank], node.data.width)
  }
  const cy = (id: string) => graph.node(id).y

  // The way of each line, column by column: the height it keeps to where it passes one.
  interface Way {
    edge: FlowEdge
    from: number
    to: number
    ys: number[]
  }
  const ways: Way[] = lines.map((edge) => {
    const from = rankOf.get(edge.source)!
    const to = rankOf.get(edge.target)!
    const points: Point[] = graph.edge(edge.source, edge.target)?.points ?? []
    const ys = [cy(edge.source)]
    for (let rank = from + 1; rank < to; rank++) {
      const through = points.find(
        (point) => Math.abs(point.x - centres[rank]) < 1.5
      )
      ys.push(through?.y ?? ys[ys.length - 1])
    }
    if (to > from) ys.push(cy(edge.target))
    return { edge, from, to, ys }
  })

  // Lines that turn in the same gap keep apart: each gets a lane of its own there, shared
  // only by lines that leave the same step.
  const laneOf = new Map<string, number>()
  const lanes = Array.from({ length: ranks }, () => 0)
  const laneKey = (way: Way, hop: number) =>
    `${way.from + hop}|${hop === 0 ? way.edge.source : way.edge.id}`
  for (const way of [...ways].sort((a, b) => a.ys[0] - b.ys[0]))
    for (let hop = 0; hop < way.ys.length - 1; hop++) {
      if (Math.abs(way.ys[hop] - way.ys[hop + 1]) < 0.5) continue
      const key = laneKey(way, hop)
      if (!laneOf.has(key)) laneOf.set(key, lanes[way.from + hop]++)
    }
  const gap = Array.from({ length: Math.max(ranks - 1, 0) }, (_, rank) => {
    const labels = ways
      .filter((way) => way.from === rank && way.edge.data?.label)
      .map((way) => labelWidth(way.edge.data!.label!))
    const turns = Math.max(lanes[rank] - 1, 0) * LANE
    return Math.max(
      COL_GAP + turns,
      labels.length ? TURN + turns + 8 + Math.max(...labels) + 14 : 0
    )
  })

  // Bands: as many columns to a band as the width holds, then evened out.
  const wrap = (limit: number) => {
    const of: number[] = []
    let band = 0
    let x = 0
    for (let rank = 0; rank < ranks; rank++) {
      if (rank && x + gap[rank - 1] + colW[rank] > limit) {
        band += 1
        x = 0
      }
      x += (x ? gap[rank - 1] : 0) + colW[rank]
      of[rank] = band
    }
    return { of, count: band + 1 }
  }
  let fitted = wrap(max)
  if (fitted.count > 1) {
    const total =
      colW.reduce((sum, width) => sum + width, 0) +
      gap.reduce((sum, width) => sum + width, 0)
    for (let limit = total / fitted.count; limit < max; limit += 24) {
      const tighter = wrap(limit)
      if (tighter.count > fitted.count) continue
      fitted = tighter
      break
    }
  }
  const bandOf = fitted.of
  const bands = fitted.count
  // A line that goes on to the next band leaves by the right and comes back in by the
  // left, so a wrapped flow keeps room on both sides for those lines.
  const crossing = Array.from({ length: bands }, () => 0)
  for (const way of ways)
    for (let rank = way.from; rank < way.to; rank++)
      if (bandOf[rank] !== bandOf[rank + 1]) crossing[bandOf[rank]] += 1
  const most = Math.max(...crossing, 0)
  const inset = bands > 1 ? TURN + Math.max(most - 1, 0) * LANE + 4 : 0

  const colX: number[] = []
  const bandRight = Array.from({ length: bands }, () => 0)
  let x = inset
  for (let rank = 0; rank < ranks; rank++) {
    if (rank && bandOf[rank] !== bandOf[rank - 1]) x = inset
    else if (rank) x += gap[rank - 1]
    colX[rank] = x
    x += colW[rank]
    bandRight[bandOf[rank]] = x
  }
  // Each band keeps the heights dagre gave, moved up to where the band starts.
  const top = Array.from({ length: bands }, () => Infinity)
  const bottom = Array.from({ length: bands }, () => -Infinity)
  const reach = (rank: number, from: number, to: number) => {
    const band = bandOf[rank]
    top[band] = Math.min(top[band], from)
    bottom[band] = Math.max(bottom[band], to)
  }
  for (const node of nodes) {
    const half = node.data.slot / 2
    reach(rankOf.get(node.id)!, cy(node.id) - half, cy(node.id) + half)
  }
  for (const way of ways)
    way.ys.forEach((value, hop) =>
      reach(way.from + hop, value - 10, value + 10)
    )
  const shift: number[] = []
  let y = 0
  for (let band = 0; band < bands; band++) {
    shift[band] = y - top[band]
    y +=
      bottom[band] -
      top[band] +
      BAND_GAP +
      Math.max(crossing[band] - 1, 0) * LANE
  }
  const height = y - BAND_GAP - Math.max(crossing[bands - 1] - 1, 0) * LANE
  const yIn = (rank: number, value: number) => value + shift[bandOf[rank]]

  const byId = new Map(nodes.map((node) => [node.id, node]))
  for (const node of nodes) {
    const rank = rankOf.get(node.id)!
    node.position = {
      x: colX[rank],
      y: yIn(rank, cy(node.id)) - node.data.slot / 2,
    }
  }

  // The lines: out to the right, a turn in the gap, on at the next height.
  const crossed = Array.from({ length: bands }, () => 0)
  for (const way of ways) {
    const source = byId.get(way.edge.source)!
    const target = byId.get(way.edge.target)!
    const start: Point = {
      x: source.position.x + source.data.width,
      y: source.position.y + source.data.slot / 2,
    }
    const end: Point = {
      x: target.position.x,
      y: target.position.y + target.data.slot / 2,
    }
    const points: Point[] = [start]
    let at = start
    let label: Point | undefined
    const text = way.edge.data?.label
    const half = text ? labelWidth(text) / 2 : 0
    for (let hop = 0; hop < way.ys.length - 1; hop++) {
      const rank = way.from + hop
      const next = rank + 1
      const last = next === way.to
      const to = last ? end.y : yIn(next, way.ys[hop + 1])
      if (bandOf[next] !== bandOf[rank]) {
        const band = bandOf[rank]
        const k = crossed[band]++
        const right = bandRight[band] + TURN + k * LANE
        const left = inset - TURN - k * LANE
        const between =
          bottom[band] +
          shift[band] +
          BAND_GAP / 2 +
          (k - (crossing[band] - 1) / 2) * LANE
        points.push(
          { x: right, y: at.y },
          { x: right, y: between },
          { x: left, y: between },
          { x: left, y: to }
        )
        if (hop === 0 && text) label = { x: right - 16 - half, y: between }
      } else {
        const lane = laneOf.get(laneKey(way, hop)) ?? 0
        const turn = colX[rank] + colW[rank] + TURN + lane * LANE
        const turns = Math.abs(to - at.y) >= 0.5
        if (turns) points.push({ x: turn, y: at.y }, { x: turn, y: to })
        if (hop === 0 && text)
          label = turns
            ? { x: turn + 8 + half, y: to }
            : { x: colX[rank] + colW[rank] + gap[rank] / 2, y: to }
      }
      at = { x: last ? end.x : colX[next], y: to }
    }
    points.push(end)
    way.edge.data = {
      ...way.edge.data!,
      route: points.map((point) => ({
        x: point.x - start.x,
        y: point.y - start.y,
      })),
      labelAt: label && { x: label.x - start.x, y: label.y - start.y },
    }
  }
  const end = bands - 1
  // A free corner at the right of the last band: under or over what stands there.
  let spot: Point | undefined
  if (extra) {
    const right = bandRight[end]
    const left = right - extra.w
    const bandTop = top[end] + shift[end]
    const bandBottom = bottom[end] + shift[end]
    let over = bandBottom
    let under = bandTop
    const block = (from: number, to: number) => {
      over = Math.min(over, from)
      under = Math.max(under, to)
    }
    for (const node of nodes) {
      if (bandOf[rankOf.get(node.id)!] !== end) continue
      if (node.position.x + node.data.width < left - 20) continue
      block(node.position.y, node.position.y + node.data.slot)
    }
    for (const way of ways)
      way.ys.forEach((value, hop) => {
        const rank = way.from + hop
        if (bandOf[rank] !== end || colX[rank] + colW[rank] < left - 20) return
        block(yIn(rank, value) - 12, yIn(rank, value) + 12)
      })
    if (left >= inset && bandBottom - under - 16 >= extra.h)
      spot = { x: left, y: bandBottom - extra.h }
    else if (left >= inset && over - bandTop - 16 >= extra.h)
      spot = { x: left, y: bandTop }
  }
  return {
    spot,
    w: Math.max(...bandRight) + inset,
    h: height,
    // Where the last band ends, for what is set down after the flow.
    tail: {
      x: bandRight[end] + (bands > 1 ? TURN + crossing[end] * LANE : 0),
      top: top[end] + shift[end],
      bottom: bottom[end] + shift[end],
    },
  }
}

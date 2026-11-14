import type { Edge, Node } from "@xyflow/react"

import { drawnGraph, edgeLabel, type Line } from "@/flow-graph"
import { cutFlow } from "./focus"
import { removedNodeId, type Coupon, type FlowView } from "@/model"
import type { FindingChange, MapFinding, MapStep } from "@/types"
import { sortAlerts } from "@/presentation"

/**
 * A flow drawn left to right in lanes: a step the change leaves alone is a small pill, a
 * step it touches is a card that says what changed. The way through that keeps off the
 * error path is one row; other branches run in rows under it and the error path in a dashed
 * box under those. Every step takes a column of one width, a branch is named on its line,
 * and every line runs at right angles. A flow never wraps: it runs as wide as it needs.
 *
 * Drawn for a change, a flow shows only the steps the change touches and the way into each
 * of them; a dotted line stands for the steps left out in between (see `cutFlow`).
 */

/** Every step, pill or card, takes a column of this width, so a flow reads as a grid. */
const CARD_W = 192
const PILL_H = 44
/** A pill whose name needs a second line. */
const PILL_TALL = 60
/** Room for a pill's name on one line: the column less its tile and padding. */
const PILL_TEXT = CARD_W - 58
/** Between two rows: room for a line running between them, or a label. */
const ROW_GAP = 28
/** The least between two columns. */
const COL_GAP = 44
/** The widest a gap grows for the label of a branch that could hang back instead. */
const LABEL_CAP = 96
/** How far past a column a line runs before it turns, and between two lines turning there. */
const TURN = 14
/** A line starts and ends this far clear of a step's box: its port is a dot on the edge
 *  of the box, and an arrowhead stops just short of it. */
const PORT = 3.5
/** How far a step back runs out past its ends, how far it keeps from the cards, and from
 *  another step back running over it. */
const LOOP_OUT = 24
const LOOP_GAP = 28
const LOOP_APART = 24
const LANE = 8
/** The box around the error path: its padding, and the room its name takes over its rows. */
const BOX_PAD = 14
const BOX_HEAD = 30
const GHOST_GAP = 28

export interface Point {
  x: number
  y: number
}

/** The dashed box the error path of a flow runs in, placed like a step. */
interface ErrorBox {
  x: number
  y: number
  w: number
  h: number
}

export interface StepNodeData extends Record<string, unknown> {
  step: MapStep
  /** The changes whose own place this step is. */
  coupons: Coupon[]
  /** Changes told on another card that land here too, by their number. */
  echoes: number[]
  isNew: boolean
  risk?: "new" | "known"
  alerts?: MapFinding[]
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
  /** Not a step: a pill that stands for this many steps left out after the one before it. */
  stub?: number
}

/** How the lines and pills that stand for steps left out are worded. */
export interface CutWords {
  between: (steps: number) => string
  more: (steps: number) => string
}

export interface FlowEdgeData extends Record<string, unknown> {
  label?: string
  exception: boolean
  uncertain: boolean
  back: boolean
  /** The line stands for this many steps that are not drawn. */
  skipped?: number
  /** The corners of the line where it is drawn, from the port it leaves to the port it
   *  reaches. The layout sets them; a view only draws through them. */
  points?: Point[]
  /** Where its label sits. */
  labelAt?: Point
}

export type StepNode = Node<StepNodeData, "step">
export type FlowEdge = Edge<FlowEdgeData, "flow">

function textWidth(text: string, cjk = 14, latin = 7.7): number {
  let width = 0
  for (const char of text)
    width += /[\u3000-\u9fff\uff00-\uffef]/.test(char) ? cjk : latin
  return width
}
/** Long conditions can be opened from the edge instead of widening the flow. */
export const EDGE_LABEL_LIMIT = 144
const fullLabelWidth = (text: string) =>
  Math.ceil(textWidth(text, 12, 7.3)) + 12
const labelWidth = (text: string) =>
  Math.min(EDGE_LABEL_LIMIT, fullLabelWidth(text))
export const isLongEdgeLabel = (text: string) =>
  fullLabelWidth(text) > EDGE_LABEL_LIMIT

function heightOf(data: StepNodeData): number {
  if (data.stub) return PILL_H
  if (data.compact)
    return textWidth(data.step.name) > PILL_TEXT ? PILL_TALL : PILL_H
  let height = 68
  if (data.coupons.length) height += 80
  if (data.loops.length) height += 24
  return height
}

export function buildGraph(
  view: FlowView,
  findingStatus: Map<string, FindingChange["status"]>,
  /** Risks that were already there show on cards (only with no report to walk). */
  knownRisks: boolean,
  /** How wide the flow may run with the steps it removed set down beside it. */
  max = Infinity,
  /**
   * Given, the flow is cut down to the steps the change touches and the way into each;
   * they word the lines and pills that stand for the steps left out.
   */
  words?: CutWords
): {
  nodes: StepNode[]
  edges: FlowEdge[]
  w: number
  h: number
  /** The dashed boxes the error paths run in. */
  boxes: ErrorBox[]
  /** Whether steps were left out. */
  cut: boolean
} {
  const steps = view.flow.steps ?? []
  const ids = new Set(steps.map((step) => step.step_id))
  const edges = (view.flow.edges ?? []).filter(
    (edge) => ids.has(edge.source) && ids.has(edge.target)
  )
  const lineOf = new Map(view.graph.lines.map((line) => [line.of, line]))

  const findings = new Set(view.findings.map((finding) => finding.finding_id))
  let nodes: StepNode[] = steps.map((step) => {
    // A change that lands on several steps is told once, on its own place; elsewhere the
    // step carries only its number.
    const placed = view.byStep.get(step.step_id) ?? []
    const coupons = placed.filter((coupon) => coupon.primary)
    const echoes = [
      ...new Set(
        placed.filter((coupon) => !coupon.primary).map((coupon) => coupon.no)
      ),
    ].filter((no) => !coupons.some((coupon) => coupon.no === no))
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
        : // A risk that was already there shows only with no report to walk.
          knownRisks
          ? "known"
          : undefined
      : undefined
    const isNew = view.newSteps.has(step.step_id)
    const alertIds = new Set([
      ...stepFindings,
      ...coupons.flatMap((coupon) => coupon.change.finding_ids ?? []),
    ])
    const alerts = sortAlerts(
      view.findings.filter(
        (finding) =>
          alertIds.has(finding.finding_id) &&
          findingStatus.get(finding.finding_id) !== "resolved" &&
          (knownRisks || findingStatus.get(finding.finding_id) === "introduced")
      )
    )
    // A pill has room for its name only, so a step with a badge to show keeps its card.
    const badged = isNew || step.resolution !== "resolved" || risk !== undefined
    const compact = !coupons.length && !loops.length && !badged
    const data: StepNodeData = {
      step,
      coupons,
      echoes,
      isNew,
      risk,
      alerts,
      ghost: false,
      loops,
      removedFlow: view.removed,
      skeleton: view.flow.stage === "skeleton",
      compact,
      width: CARD_W,
      hasIn: incoming.length > 0,
      hasOut: outgoing.length > 0,
      slot: 0,
    }
    data.slot = heightOf(data)
    // What a screen reader says for the card: the step, then the change written on it.
    const said = coupons[0]?.change.explanation?.summary
    return {
      id: step.step_id,
      type: "step",
      position: { x: 0, y: 0 },
      draggable: false,
      connectable: false,
      ariaLabel: said ? `${step.name}. ${said}` : step.name,
      data,
    }
  })

  let flowEdges: FlowEdge[] = edges
    .filter((edge) => edge.target !== edge.source)
    .map((edge) => ({
      id: lineOf.get(edge)?.id ?? `${edge.source}>${edge.target}`,
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
        back: lineOf.get(edge)?.back ?? true,
      },
    }))

  const cut = words
    ? cutFlow(
        steps,
        view.graph,
        new Set(
          nodes
            .filter(
              ({ data }) =>
                data.coupons.length > 0 ||
                data.echoes.length > 0 ||
                data.isNew ||
                data.risk === "new"
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
      const count = words!.between(skip.steps)
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
    // Where the flow goes on past what is drawn, a dotted pill says by how many steps.
    for (const tail of cut.tails) {
      const id = `more>${tail.source}`
      const name = words!.more(tail.steps)
      nodes.push({
        id,
        type: "step",
        position: { x: 0, y: 0 },
        draggable: false,
        connectable: false,
        ariaLabel: name,
        data: {
          step: {
            step_id: id,
            name,
            kind: "result",
            support: "static_fact",
            resolution: "resolved",
          },
          coupons: [],
          echoes: [],
          isNew: false,
          ghost: false,
          loops: [],
          removedFlow: false,
          skeleton: false,
          compact: true,
          width: Math.ceil(textWidth(name, 13, 7.2)) + 40,
          hasIn: true,
          hasOut: false,
          slot: PILL_H,
          stub: tail.steps,
        },
      })
      flowEdges.push({
        id: `tail>${tail.source}`,
        type: "flow",
        source: tail.source,
        target: id,
        sourceHandle: "out",
        targetHandle: "in",
        focusable: false,
        data: {
          label: tail.label,
          exception: tail.exception,
          uncertain: false,
          back: false,
          skipped: tail.steps,
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
  const size = arrange(nodes, flowEdges)

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
      echoes: [],
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
    const at = beside
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
    boxes: size.boxes,
    cut:
      nodes.filter((node) => !node.data.ghost && !node.data.stub).length <
      steps.length,
  }
}

/** What is drawn of a flow, as a graph: its steps in the order given, its lines as marked. */
export function graphOfDrawing(nodes: StepNode[], edges: FlowEdge[]) {
  return drawnGraph(
    nodes.map((node) => node.id),
    edges.map((edge): Line<FlowEdge> => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      back: Boolean(edge.data?.back),
      exception: Boolean(edge.data?.exception),
      of: edge,
    }))
  )
}

/**
 * Places the steps and routes the lines, as lanes. The way through the flow that keeps off
 * the error path is one row, read left to right; every other branch runs in a row below
 * it, and steps reached only by an error run in rows of their own under all of them, inside
 * one dashed box. A step's column is how many steps lead up to it at most, every column is
 * as wide as a card, and a gap between columns is as wide as the labels and turns in it.
 */
function arrange(
  nodes: StepNode[],
  edges: FlowEdge[]
): {
  w: number
  h: number
  tail: { x: number; top: number; bottom: number }
  boxes: ErrorBox[]
} {
  if (!nodes.length)
    return { w: 0, h: 0, tail: { x: 0, top: 0, bottom: 0 }, boxes: [] }
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const graph = graphOfDrawing(nodes, edges)
  const { out, into } = graph
  // The lines that lead on, in the order the flow lists them.
  const lines = graph.lines.filter((line) => !line.back).map((line) => line.of)

  // Reading order: every step after the steps that lead to it.
  const order: string[] = []
  const waiting = new Map(
    nodes.map((node) => [node.id, into.get(node.id)?.length ?? 0])
  )
  const ready = nodes
    .filter((node) => !waiting.get(node.id))
    .map((node) => node.id)
  while (ready.length) {
    const id = ready.shift()!
    order.push(id)
    for (const edge of out.get(id) ?? []) {
      const left = waiting.get(edge.target)! - 1
      waiting.set(edge.target, left)
      if (left === 0) ready.push(edge.target)
    }
  }
  for (const node of nodes) if (!order.includes(node.id)) order.push(node.id)

  // The main row: from the trigger, at each fork the branch off the error path, then a
  // real step before a pill for steps left out, then the one that runs longest.
  const rest = new Map<string, number>()
  for (const id of [...order].reverse())
    rest.set(
      id,
      1 +
        Math.max(
          0,
          ...(out.get(id) ?? []).map((edge) => rest.get(edge.target) ?? 0)
        )
    )
  const first =
    nodes.find(
      (node) => node.data.step.kind === "trigger" && !into.get(node.id)?.length
    )?.id ?? order[0]
  const main = [first]
  const onMain = new Set(main)
  for (let at = first; ;) {
    const next = (out.get(at) ?? [])
      .filter((edge) => !onMain.has(edge.target))
      .sort(
        (a, b) =>
          Number(a.exception) - Number(b.exception) ||
          Number(Boolean(byId.get(a.target)!.data.stub)) -
            Number(Boolean(byId.get(b.target)!.data.stub)) ||
          rest.get(b.target)! - rest.get(a.target)!
      )[0]
    if (!next) break
    at = next.target
    main.push(at)
    onMain.add(at)
  }

  // A step is on the error path when every way into it is an error or comes from one.
  const error = new Set<string>()
  for (const id of order) {
    if (onMain.has(id)) continue
    const ins = into.get(id) ?? []
    if (
      ins.length &&
      ins.every((edge) => edge.exception || error.has(edge.source))
    )
      error.add(id)
  }

  // Columns: a step comes after every step that leads to it. The error path is the
  // exception: it starts right after the first step that can fail into it, and a step
  // that an error leads back into does not move for it.
  const col = new Map<string, number>()
  for (const id of order) {
    const ins = (into.get(id) ?? []).filter((edge) => col.has(edge.source))
    const after = (edges: Line[]) =>
      edges.map((edge) => col.get(edge.source)! + 1)
    const fromErrors = after(ins.filter((edge) => error.has(edge.source)))
    const fromOthers = after(ins.filter((edge) => !error.has(edge.source)))
    col.set(
      id,
      error.has(id)
        ? Math.max(
            fromOthers.length ? Math.min(...fromOthers) : 0,
            ...fromErrors
          )
        : Math.max(0, ...fromOthers)
    )
  }

  // Rows. A branch keeps to the row of the step it follows while that row is free; a line
  // running along a row to its step takes the cells it passes.
  const row = new Map<string, number>()
  const used = new Map<number, Set<number>>()
  const take = (r: number, from: number, to: number) => {
    const cells = used.get(r) ?? new Set<number>()
    for (let c = from; c <= to; c++) cells.add(c)
    used.set(r, cells)
  }
  const isFree = (r: number, from: number, to: number) => {
    const cells = used.get(r)
    for (let c = from; c <= to; c++) if (cells?.has(c)) return false
    return true
  }
  for (const id of main) row.set(id, 0)
  take(0, col.get(main[0])!, col.get(main[main.length - 1])!)
  const place = (id: string, base: number) => {
    const c = col.get(id)!
    const ins = (into.get(id) ?? []).filter((edge) => row.has(edge.source))
    const from = (edge: Line) => Math.min(col.get(edge.source)! + 1, c)
    for (const edge of ins) {
      const r = row.get(edge.source)!
      if (r >= base && isFree(r, from(edge), c)) {
        row.set(id, r)
        take(r, from(edge), c)
        return
      }
    }
    const lead = ins.length ? Math.min(...ins.map(from)) : c
    for (let r = base; ; r++)
      if (isFree(r, lead, c)) {
        row.set(id, r)
        take(r, lead, c)
        return
      }
  }
  const others = order
    .filter((id) => !onMain.has(id))
    .sort((a, b) => col.get(a)! - col.get(b)!)
  for (const id of others) if (!error.has(id)) place(id, 1)
  const errorRow = Math.max(0, ...row.values()) + 1
  for (const id of others) if (error.has(id)) place(id, errorRow)
  const rows = Math.max(0, ...row.values()) + 1
  const boxed = error.size > 0

  const rowH = Array.from({ length: rows }, () => PILL_H)
  for (const node of nodes) {
    const r = row.get(node.id)!
    rowH[r] = Math.max(rowH[r], node.data.slot)
  }
  const rowTop: number[] = []
  let y = 0
  for (let r = 0; r < rows; r++) {
    if (r) y += ROW_GAP
    if (boxed && r === errorRow) y += BOX_HEAD
    rowTop[r] = y
    y += rowH[r]
  }
  const height = y + (boxed ? BOX_PAD : 0)
  const mid = (r: number) => rowTop[r] + rowH[r] / 2

  // How each line gets to its step: straight along its row, turning just after it leaves
  // (then along the row it arrives on), turning just before it arrives (after running
  // along the row it leaves), or through the gap between two rows when both are taken.
  const stepAt = new Set(
    nodes.map((node) => `${row.get(node.id)}:${col.get(node.id)}`)
  )
  const clear = (r: number, from: number, to: number) => {
    for (let c = from; c <= to; c++) if (stepAt.has(`${r}:${c}`)) return false
    return true
  }
  interface Way {
    edge: FlowEdge
    kind: "straight" | "early" | "late" | "between" | "drop" | "rise"
    rs: number
    rt: number
    cs: number
    ct: number
    width: number
    left?: number
    right?: number
    /** Its label hangs back over the empty cell before its step instead of widening the gap. */
    hang?: boolean
  }
  const ways: Way[] = lines.map((edge) => {
    const rs = row.get(edge.source)!
    const rt = row.get(edge.target)!
    const cs = col.get(edge.source)!
    const ct = col.get(edge.target)!
    const label = edge.data?.label
    const way = { edge, rs, rt, cs, ct, width: label ? labelWidth(label) : 0 }
    // Back to a column at or before its own: down into the top of a step on the error
    // path, or up into the bottom of a step an error leads back to.
    if (ct <= cs) return { ...way, kind: rt > rs ? "drop" : "rise" }
    if (rs === rt)
      return {
        ...way,
        kind: clear(rs, cs + 1, ct - 1) ? "straight" : "between",
      }
    const early = clear(rt, cs + 1, ct - 1)
    const late = clear(rs, cs + 1, ct - 1)
    // Into the main row a line comes late, so it never runs along the main row's cards.
    const kind =
      rt === 0
        ? late
          ? "late"
          : early
            ? "early"
            : "between"
        : early
          ? "early"
          : late
            ? "late"
            : "between"
    return { ...way, kind }
  })

  // Lines turning in one gap keep apart: those leaving a step turn near its left, those
  // arriving near its right, and lines that leave or arrive at the same step share a turn.
  const cols = Math.max(...col.values()) + 1
  const leaving = Array.from({ length: cols }, () => new Map<string, number>())
  const arriving = Array.from({ length: cols }, () => new Map<string, number>())
  const laneIn = (lanes: Map<string, number>, key: string) => {
    if (!lanes.has(key)) lanes.set(key, lanes.size)
    return lanes.get(key)!
  }
  for (const way of [...ways].sort((a, b) => b.rs - a.rs || a.rt - b.rt)) {
    if (way.kind !== "straight" && way.kind !== "late")
      way.left = laneIn(leaving[way.cs], way.edge.source)
    if (way.kind === "late" || way.kind === "between")
      way.right = laneIn(arriving[Math.max(way.ct - 1, 0)], way.edge.target)
  }
  // A label sits over an empty cell when its line passes one; else the gap makes room.
  const gap = Array.from({ length: cols }, (_, c) =>
    Math.max(
      COL_GAP,
      2 * TURN + Math.max(leaving[c].size + arriving[c].size - 1, 0) * LANE
    )
  )
  // A long label on a branch that drops one row to the next column hangs back over the
  // cell before its step when nothing stands there and no other line runs on below it.
  for (const way of ways) {
    if (way.kind !== "early" || !way.width || way.ct - way.cs !== 1) continue
    const room = TURN + (way.left ?? 0) * LANE + 8 + way.width + 14
    const further = (other: Way) =>
      other !== way &&
      other.edge.source === way.edge.source &&
      other.left === way.left &&
      (way.rt > way.rs ? other.rt > way.rt : other.rt < way.rt)
    way.hang =
      room > LABEL_CAP &&
      !stepAt.has(`${way.rt}:${way.cs}`) &&
      !ways.some(further)
  }
  for (const way of ways) {
    if (
      !way.width ||
      way.hang ||
      way.kind === "between" ||
      way.kind === "drop" ||
      way.kind === "rise" ||
      way.ct - way.cs >= 2
    )
      continue
    const room =
      way.kind === "straight"
        ? way.width + 24
        : way.kind === "early"
          ? TURN + (way.left ?? 0) * LANE + 8 + way.width + 14
          : 8 + way.width + 8 + TURN + (way.right ?? 0) * LANE
    gap[way.cs] = Math.max(gap[way.cs], room)
  }

  const colX: number[] = []
  let x = 0
  for (let c = 0; c < cols; c++) {
    colX[c] = x
    x += CARD_W + gap[c]
  }
  for (const node of nodes)
    node.position = {
      x: colX[col.get(node.id)!],
      y: mid(row.get(node.id)!) - node.data.slot / 2,
    }
  const width = Math.max(
    ...nodes.map((node) => node.position.x + node.data.width)
  )

  // Lines through the gap between two rows: each keeps a height of its own there.
  const between = new Map<number, number>()
  const betweenY = (way: Way) => {
    const above =
      way.kind === "drop" || (way.kind === "between" && way.rt > way.rs)
    // A line falling into the error box runs above the box, then drops in.
    const head = boxed && way.rt === errorRow ? BOX_HEAD : 0
    const at = above
      ? rowTop[way.rt] - head - ROW_GAP / 2
      : rowTop[way.rt] + rowH[way.rt] + ROW_GAP / 2
    const k = between.get(at) ?? 0
    between.set(at, k + 1)
    return at + (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 7
  }
  const cell = (c: number) => colX[c] + CARD_W / 2
  // Labels already set down, so a line running beside another puts its own label clear of
  // theirs: along its run, from the middle outward.
  const set: { x: number; y: number; w: number }[] = []
  const free = (x: number, y: number, w: number) =>
    set.every(
      (other) =>
        Math.abs(other.y - y) >= 22 ||
        Math.abs(other.x - x) >= (other.w + w) / 2 + 8
    )
  const along = (from: number, to: number, y: number, w: number) => {
    const lo = Math.min(from, to) + w / 2 + 8
    const hi = Math.max(from, to) - w / 2 - 8
    const middle = (from + to) / 2
    if (hi <= lo) return middle
    for (const share of [0.5, 0.3, 0.7, 0.15, 0.85]) {
      const x = lo + (hi - lo) * share
      if (free(x, y, w)) return x
    }
    return middle
  }
  // A label on a run between rows is set down last, the shortest runs first: they have
  // the least room to give way.
  const runs: {
    edge: FlowEdge
    width: number
    from: number
    to: number
    y: number
  }[] = []
  // Every line is drawn a port's width to the right of where the columns put it, since it
  // leaves from the port outside its step's box; it ends at the port of the step it reaches.
  const drawn = (point: Point): Point => ({ x: point.x + PORT, y: point.y })
  for (const way of ways) {
    const source = byId.get(way.edge.source)!
    const target = byId.get(way.edge.target)!
    const start: Point = {
      x: source.position.x + source.data.width,
      y: mid(way.rs),
    }
    const end: Point = { x: target.position.x, y: mid(way.rt) }
    const out = colX[way.cs] + CARD_W + TURN + (way.left ?? 0) * LANE
    const back = colX[Math.max(way.ct, 0)] - TURN - (way.right ?? 0) * LANE
    const passes = way.ct - way.cs >= 2
    const half = way.width / 2
    const nearExit = (x: number, y: number) => ({ x: x + 8 + half, y })
    let points: Point[]
    let label: Point | undefined
    let slide: { from: number; to: number; y: number } | undefined
    if (way.kind === "straight") {
      points = [start, end]
      label = nearExit(start.x, start.y)
    } else if (way.kind === "early") {
      points = [start, { x: out, y: start.y }, { x: out, y: end.y }, end]
      label = way.hang
        ? { x: end.x - 14 - half, y: end.y }
        : nearExit(out, end.y)
    } else if (way.kind === "late") {
      points = [start, { x: back, y: start.y }, { x: back, y: end.y }, end]
      label = passes
        ? { x: cell(way.cs + 1), y: start.y }
        : { x: start.x + 8 + half, y: start.y }
    } else if (way.kind === "drop" || way.kind === "rise") {
      const run = betweenY(way)
      // It comes straight down into the middle of the top, or up into the bottom.
      const x = target.position.x + target.data.width / 2 - PORT
      const edge =
        way.kind === "drop"
          ? target.position.y - PORT
          : target.position.y + target.data.slot + PORT
      points = [
        start,
        { x: out, y: start.y },
        { x: out, y: run },
        { x, y: run },
        { x, y: edge },
      ]
      slide = { from: out, to: x + PORT, y: run }
    } else {
      const run = betweenY(way)
      points = [
        start,
        { x: out, y: start.y },
        { x: out, y: run },
        { x: back, y: run },
        { x: back, y: end.y },
        end,
      ]
      slide = { from: out, to: back, y: run }
    }
    // A line into the side of its step stops at that step's port.
    if (way.kind !== "drop" && way.kind !== "rise")
      points[points.length - 1] = { x: end.x - 2 * PORT, y: end.y }
    way.edge.data = {
      ...way.edge.data!,
      points: points.map(drawn),
      labelAt: undefined,
    }
    if (!way.width) continue
    if (slide) runs.push({ edge: way.edge, width: way.width, ...slide })
    else if (label) {
      set.push({ ...label, w: way.width })
      way.edge.data.labelAt = drawn(label)
    }
  }

  // A step back to an earlier one leaves to the right, runs back in a lane just clear of
  // the cards between its ends (above or below, whichever is nearer) and comes in from the
  // left. Steps back that run over each other each keep a lane of their own.
  const lanes: { y: number; from: number; to: number; up: boolean }[] = []
  for (const edge of edges) {
    if (!edge.data?.back || edge.source === edge.target) continue
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) continue
    const start = {
      x: source.position.x + source.data.width,
      y: source.position.y + source.data.slot / 2,
    }
    const tx = target.position.x
    const ty = target.position.y + target.data.slot / 2
    const from = Math.min(start.x, tx) - LOOP_OUT
    const to = Math.max(start.x, tx) + LOOP_OUT
    let top = Math.min(start.y, ty)
    let bottom = Math.max(start.y, ty)
    for (const node of nodes) {
      if (node.position.x > to || node.position.x + node.data.width < from)
        continue
      top = Math.min(top, node.position.y)
      bottom = Math.max(bottom, node.position.y + node.data.slot)
    }
    const above = top - LOOP_GAP
    const below = bottom + LOOP_GAP
    const up = start.y + ty - 2 * above < 2 * below - start.y - ty
    let lane = up ? above : below
    const crossed = () =>
      lanes.find(
        (other) =>
          other.up === up &&
          other.from < to &&
          from < other.to &&
          Math.abs(other.y - lane) < LOOP_APART
      )
    for (let other = crossed(); other; other = crossed())
      lane = other.y + (up ? -LOOP_APART : LOOP_APART)
    lanes.push({ y: lane, from, to, up })
    const leave = start.x + PORT
    const reach = tx - PORT
    edge.data = {
      ...edge.data,
      points: [
        { x: leave, y: start.y },
        { x: leave + LOOP_OUT, y: start.y },
        { x: leave + LOOP_OUT, y: lane },
        { x: reach - LOOP_OUT, y: lane },
        { x: reach - LOOP_OUT, y: ty },
        { x: reach, y: ty },
      ],
      labelAt: undefined,
    }
    const label = edge.data.label
    if (label)
      runs.push({
        edge,
        width: labelWidth(label),
        from: start.x + LOOP_OUT,
        to: tx - LOOP_OUT,
        y: lane,
      })
  }

  runs.sort((a, b) => Math.abs(a.to - a.from) - Math.abs(b.to - b.from))
  for (const run of runs) {
    const x = along(run.from, run.to, run.y, run.width)
    set.push({ x, y: run.y, w: run.width })
    run.edge.data!.labelAt = drawn({ x, y: run.y })
  }

  // Lanes above the first row or below the last widen the flow to hold them and their
  // labels, so they stay on its card.
  const lift = Math.max(0, ...lanes.map((lane) => 12 - lane.y))
  const low = Math.max(height, ...lanes.map((lane) => lane.y + 12)) + lift
  if (lift) {
    for (const node of nodes) node.position.y += lift
    for (const edge of edges) {
      for (const point of edge.data?.points ?? []) point.y += lift
      if (edge.data?.labelAt) edge.data.labelAt.y += lift
    }
  }

  const boxes: ErrorBox[] = []
  if (boxed) {
    const members = [...error].map((id) => col.get(id)!)
    const left = colX[Math.min(...members)] - BOX_PAD
    const top = rowTop[errorRow] - BOX_HEAD
    boxes.push({
      x: left,
      y: top + lift,
      w: colX[Math.max(...members)] + CARD_W + BOX_PAD - left,
      h: height - top,
    })
  }
  return {
    w: width,
    h: low,
    tail: { x: width, top: 0, bottom: low },
    boxes,
  }
}

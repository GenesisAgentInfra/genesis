import type { Edge, Node } from "@xyflow/react"

import {
  buildGraph,
  heightOf,
  type FlowEdge,
  type StepNode,
} from "@/canvas/graph"
import type { Strings } from "@/i18n"
import type { Coupon, FlowView, Model } from "@/model"
import type { EntryKind } from "@/types"

/**
 * The whole product on one canvas. Each module is a large frame holding its flows, every
 * flow is drawn in full, the ways in (requests, tasks, schedules) sit on the left and lead
 * into the flows they start, and what a change also touches is drawn as a line to it.
 */

export const SEP = "::"
const P = 32
const HEAD_H = 88
const LABEL_H = 48
const FLOW_GAP = 56
const MODULE_GAP = 120
const ACTOR_W = 196
const ACTOR_GAP = 220
export const OFFMAP_W = 252
const OFFMAP_H = 112

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
}
export interface LabelData extends Record<string, unknown> {
  flowId: string
  name: string
  code: boolean
  struck: boolean
  changes: number
}
export interface ActorData extends Record<string, unknown> {
  kind: EntryKind
  flows: number
}
export interface OffMapData extends Record<string, unknown> {
  coupon: Coupon
}
export interface RelationData extends Record<string, unknown> {
  label?: string
  change: boolean
  candidate: boolean
}

export type ModuleNode = Node<ModuleData, "module">
export type LabelNode = Node<LabelData, "label">
export type ActorNode = Node<ActorData, "actor">
export type OffMapNode = Node<OffMapData, "offmap">
export type AtlasNode =
  StepNode | ModuleNode | LabelNode | ActorNode | OffMapNode
/** A line from a way in to a trigger, kept to the gaps between modules. */
export interface EntryData extends Record<string, unknown> {
  /** The lane in the gutter beside the ways in. */
  busX: number
  /** The gap above the target's row it runs along, when it must pass other modules. */
  gapY?: number
  /** The lane just left of the target module. */
  laneX: number
}
export type RelationEdge = Edge<RelationData, "relation">
export type EntryEdge = Edge<EntryData, "entry">
export type AtlasEdge = FlowEdge | RelationEdge | EntryEdge

/** A flow placed on the atlas: its nodes, edges and where its steps begin. */
export interface PlacedFlow {
  view: FlowView
  nodes: StepNode[]
  edges: FlowEdge[]
  triggers: string[]
}

export interface Atlas {
  nodes: AtlasNode[]
  edges: AtlasEdge[]
  flows: Map<string, PlacedFlow>
}

function boundsOf(nodes: StepNode[]) {
  const xs = nodes.map((node) => node.position.x)
  const ys = nodes.map((node) => node.position.y)
  const right = nodes.map((node) => node.position.x + node.data.width)
  const bottom = nodes.map((node) => node.position.y + heightOf(node.data))
  return {
    x: Math.min(...xs, 0),
    y: Math.min(...ys, 0),
    w: Math.max(...right, 160) - Math.min(...xs, 0),
    h: Math.max(...bottom, 60) - Math.min(...ys, 0),
  }
}

/** A flow's own graph, renamed so it can share a canvas with every other flow. */
function placeFlow(model: Model, view: FlowView): PlacedFlow {
  const flowId = view.flow.flow_id
  const graph = buildGraph(view, model.findingStatus, !model.hasReport)
  const steps = view.flow.steps ?? []
  const triggerIds = steps
    .filter((step) => step.kind === "trigger")
    .map((step) => step.step_id)
  const firstRow = view.layout.rows[0]?.step.step_id
  const triggers = (
    triggerIds.length ? triggerIds : firstRow ? [firstRow] : []
  ).map((id) => stepNodeId(flowId, id))
  const nodes = graph.nodes.map((node) => ({
    ...node,
    id: stepNodeId(flowId, node.id),
    data: {
      ...node.data,
      // A trigger takes the line from the way in on its left.
      hasIn: node.data.hasIn || triggers.includes(stepNodeId(flowId, node.id)),
    },
  }))
  const edges = graph.edges.map((edge) => ({
    ...edge,
    id: stepNodeId(flowId, edge.id),
    source: stepNodeId(flowId, edge.source),
    target: stepNodeId(flowId, edge.target),
  }))
  return { view, nodes, edges, triggers }
}

export function buildAtlas(model: Model, t: Strings): Atlas {
  const flows = new Map<string, PlacedFlow>()
  for (const view of model.flows)
    flows.set(view.flow.flow_id, placeFlow(model, view))

  interface Block {
    id: string
    title: string
    apart: boolean
    changes: number
    views: FlowView[]
    offMap: Coupon[]
    w: number
    h: number
  }
  const sizeOf = (views: FlowView[], offMap: Coupon[]) => {
    let w = 0
    let h = HEAD_H
    for (const view of views) {
      const box = boundsOf(flows.get(view.flow.flow_id)!.nodes)
      w = Math.max(w, box.w)
      h += LABEL_H + box.h + FLOW_GAP
    }
    if (offMap.length) {
      w = Math.max(w, offMap.length * (OFFMAP_W + 34) - 34)
      h += LABEL_H + OFFMAP_H + FLOW_GAP
    }
    return { w: w + 2 * P, h: h - FLOW_GAP + P }
  }
  const changesOn = (views: FlowView[]) =>
    views.reduce(
      (sum, view) => sum + (model.stopsOn.get(view.flow.flow_id)?.length ?? 0),
      0
    )

  const blocks: Block[] = model.modules.map((module) => ({
    id: moduleNodeId(module.id),
    title: module.name ?? t.looseFlows,
    apart: false,
    changes: changesOn(module.flows),
    views: module.flows,
    offMap: [],
    ...sizeOf(module.flows, []),
  }))
  // The modules this change touches come first, so the first look lands on them.
  blocks.sort((a, b) => Number(b.changes > 0) - Number(a.changes > 0))
  const removed = model.flows.filter((view) => view.removed)
  const offMap = model.stops
    .filter((stop) => stop.kind === "off_map" && stop.coupon)
    .map((stop) => stop.coupon!)
  if (removed.length || offMap.length)
    blocks.push({
      id: moduleNodeId("__apart"),
      title: t.offMapCard,
      apart: true,
      changes: changesOn(removed) + offMap.length,
      views: removed,
      offMap,
      ...sizeOf(removed, offMap),
    })

  // Rows of modules, wrapped to keep the whole atlas roughly the shape of a screen.
  const area = blocks.reduce((sum, block) => sum + block.w * block.h, 0)
  const rowWidth = Math.max(
    ...blocks.map((block) => block.w),
    Math.sqrt(area * 1.7)
  )
  const left = ACTOR_W + ACTOR_GAP
  let x = left
  let y = 0
  let rowHeight = 0
  const placed: {
    block: Block
    x: number
    y: number
    row: number
    first: boolean
  }[] = []
  const rows: { top: number; bottom: number }[] = []
  for (const block of blocks) {
    if (x > left && x + block.w > left + rowWidth) {
      x = left
      y += rowHeight + MODULE_GAP
      rowHeight = 0
    }
    if (x === left) rows.push({ top: y, bottom: y })
    placed.push({ block, x, y, row: rows.length - 1, first: x === left })
    rows[rows.length - 1].bottom = Math.max(
      rows[rows.length - 1].bottom,
      y + block.h
    )
    x += block.w + MODULE_GAP
    rowHeight = Math.max(rowHeight, block.h)
  }
  const blockOf = new Map<string, (typeof placed)[number]>()
  for (const item of placed)
    for (const view of item.block.views) blockOf.set(view.flow.flow_id, item)

  const nodes: AtlasNode[] = []
  const edges: AtlasEdge[] = []
  for (const { block, x: bx, y: by } of placed) {
    nodes.push({
      id: block.id,
      type: "module",
      position: { x: bx, y: by },
      width: block.w,
      height: block.h,
      zIndex: -1,
      draggable: false,
      connectable: false,
      selectable: false,
      focusable: false,
      data: {
        title: block.title,
        changes: block.changes,
        flows: block.views.length,
        apart: block.apart,
      },
    })
    let fy = by + HEAD_H
    for (const view of block.views) {
      const flow = flows.get(view.flow.flow_id)!
      const box = boundsOf(flow.nodes)
      nodes.push({
        id: `label${SEP}${view.flow.flow_id}`,
        type: "label",
        position: { x: bx + P, y: fy },
        width: Math.max(box.w, 320),
        height: LABEL_H,
        draggable: false,
        connectable: false,
        selectable: false,
        focusable: false,
        data: {
          flowId: view.flow.flow_id,
          name: view.flow.name,
          code: view.flow.stage === "skeleton",
          struck: view.removed,
          changes: model.stopsOn.get(view.flow.flow_id)?.length ?? 0,
        },
      })
      const dx = bx + P - box.x
      const dy = fy + LABEL_H - box.y
      for (const node of flow.nodes) {
        node.position = { x: node.position.x + dx, y: node.position.y + dy }
        nodes.push(node)
      }
      edges.push(...flow.edges)
      fy += LABEL_H + box.h + FLOW_GAP
    }
    if (block.offMap.length) {
      nodes.push({
        id: `label${SEP}__offmap`,
        type: "label",
        position: { x: bx + P, y: fy },
        width: 320,
        height: LABEL_H,
        draggable: false,
        connectable: false,
        selectable: false,
        focusable: false,
        data: {
          flowId: "",
          name: t.offMapRow(block.offMap.length),
          code: false,
          struck: false,
          changes: 0,
        },
      })
      block.offMap.forEach((coupon, index) =>
        nodes.push({
          id: `offmap${SEP}${coupon.no}`,
          type: "offmap",
          position: {
            x: bx + P + index * (OFFMAP_W + 34),
            y: fy + LABEL_H,
          },
          width: OFFMAP_W,
          height: OFFMAP_H,
          draggable: false,
          connectable: false,
          selectable: false,
          data: { coupon },
        })
      )
    }
  }

  // The ways in: who or what starts each flow, on the left, each line into its trigger.
  const byKind = new Map<EntryKind, string[]>()
  for (const module of model.modules)
    for (const view of module.flows) {
      const kind = view.flow.entries[0]?.kind
      if (!kind) continue
      byKind.set(kind, [...(byKind.get(kind) ?? []), view.flow.flow_id])
    }
  let ay = 0
  let lane = 0
  for (const [kind, ids] of byKind) {
    const id = `actor${SEP}${kind}`
    nodes.push({
      id,
      type: "actor",
      position: { x: 0, y: ay },
      width: ACTOR_W,
      height: 56,
      draggable: false,
      connectable: false,
      selectable: false,
      focusable: false,
      data: { kind, flows: ids.length },
    })
    // Each way in has its own lanes, so lines from different ones run side by side.
    const shift = lane * 10
    for (const flowId of ids) {
      const home = blockOf.get(flowId)
      if (!home) continue
      const gapY = home.first
        ? undefined
        : home.row === 0
          ? rows[0].top - 56 - shift
          : (rows[home.row - 1].bottom + rows[home.row].top) / 2 - shift
      for (const trigger of flows.get(flowId)!.triggers)
        edges.push({
          id: `${id}>${trigger}`,
          type: "entry",
          source: id,
          target: trigger,
          sourceHandle: "out",
          targetHandle: "in",
          focusable: false,
          data: {
            busX: ACTOR_W + 48 + shift,
            gapY,
            laneX: home.x - 60 + shift,
          },
        })
    }
    ay += 96
    lane += 1
  }

  // What else a change touches: the same change elsewhere, and flows that may reach it.
  const has = new Set(nodes.map((node) => node.id))
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
            t.sameChange,
            true
          )
        )
    }
    for (const flowId of stop.maybe)
      for (const to of flows.get(flowId)?.triggers ?? [])
        if (has.has(to))
          edges.push(
            relation(
              `maybe${SEP}${stop.no}${SEP}${to}`,
              from,
              to,
              t.mayAffect,
              true
            )
          )
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
  return { nodes, edges, flows }
}

function relation(
  id: string,
  source: string,
  target: string,
  label: string,
  change: boolean,
  candidate = false
): RelationEdge {
  return {
    id,
    type: "relation",
    source,
    target,
    sourceHandle: "rel-out",
    targetHandle: "rel-in",
    focusable: false,
    data: { label, change, candidate },
  }
}

/**
 * The way through a flow worth watching: from its trigger, at each decision the branch that
 * passes the most changes, then the one off the error path, then the longer one.
 */
export function mainPath(flow: PlacedFlow): {
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

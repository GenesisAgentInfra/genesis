import dagre from "@dagrejs/dagre"
import type { Edge, Node } from "@xyflow/react"

import { edgeLabel } from "@/layout"
import { removedNodeId, type Coupon, type FlowView } from "@/model"
import type { FindingChange, MapEdge, MapStep } from "@/types"

/**
 * A flow laid out left to right, the way agent builders draw a run: one card per step,
 * a decision card lists its branches as rows and each branch leaves from its own row.
 * The start and the plain ends are small pills, so the flow stays compact.
 */

export const NODE_WIDTH = 252
const PILL_HEIGHT = 44

export interface BranchRow {
  id: string
  label: string
  exception: boolean
  uncertain: boolean
}

export interface StepNodeData extends Record<string, unknown> {
  step: MapStep
  rows: BranchRow[]
  coupons: Coupon[]
  isNew: boolean
  risk?: "new" | "known"
  ghost: boolean
  loops: { label: string }[]
  removedFlow: boolean
  skeleton: boolean
  /** A start or a plain end, drawn as a pill. */
  compact: boolean
  width: number
  hasIn: boolean
  hasOut: boolean
}

export interface FlowEdgeData extends Record<string, unknown> {
  label?: string
  exception: boolean
  uncertain: boolean
  back: boolean
}

export type StepNode = Node<StepNodeData, "step">
export type FlowEdge = Edge<FlowEdgeData, "flow">

function textWidth(text: string): number {
  let width = 0
  for (const char of text)
    width += /[\u3000-\u9fff\uff00-\uffef]/.test(char) ? 13.5 : 7.4
  return width
}

export function heightOf(data: StepNodeData): number {
  if (data.compact) return PILL_HEIGHT
  let height = 64
  if (data.rows.length) height += 10 + data.rows.length * 36
  if (data.coupons.length) height += 86
  if (data.loops.length) height += 24
  return height
}

/**
 * The layout does not know which row of a decision each branch leaves from, so branches
 * can cross. Put the branch targets back in row order, carrying each branch's own chain
 * of steps with it (up to the step where branches meet again).
 */
function untangleBranches(nodes: StepNode[], edges: FlowEdge[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const forward = edges.filter((edge) => !edge.data?.back)
  const indegree = new Map<string, number>()
  for (const edge of forward)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  const center = (id: string) =>
    byId.get(id)!.position.y + heightOf(byId.get(id)!.data) / 2
  const chain = (start: string) => {
    const seen = new Set<string>([start])
    const queue = [start]
    while (queue.length) {
      const id = queue.shift()!
      for (const edge of forward) {
        if (
          edge.source !== id ||
          seen.has(edge.target) ||
          (indegree.get(edge.target) ?? 0) !== 1
        )
          continue
        seen.add(edge.target)
        queue.push(edge.target)
      }
    }
    return seen
  }
  for (const node of nodes) {
    if (node.data.rows.length < 2) continue
    const targets = node.data.rows
      .map(
        (row) =>
          forward.find(
            (edge) => edge.source === node.id && edge.sourceHandle === row.id
          )?.target
      )
      .filter(
        (id): id is string => Boolean(id) && (indegree.get(id!) ?? 0) === 1
      )
    const unique = [...new Set(targets)]
    if (unique.length < 2) continue
    const slots = unique.map(center).sort((a, b) => a - b)
    unique.forEach((id, index) => {
      const delta = slots[index] - center(id)
      if (!delta) return
      for (const member of chain(id)) byId.get(member)!.position.y += delta
    })
  }
}

export function buildGraph(
  view: FlowView,
  findingStatus: Map<string, FindingChange["status"]>,
  /** Risks that were already there show on cards (only with no report to walk). */
  knownRisks: boolean
): { nodes: StepNode[]; edges: FlowEdge[] } {
  const steps = view.flow.steps ?? []
  const ids = new Set(steps.map((step) => step.step_id))
  const edges = (view.flow.edges ?? []).filter(
    (edge) => ids.has(edge.source) && ids.has(edge.target)
  )
  const keyOf = view.layout.edgeKey
  const forward = new Set(view.layout.forward)
  const names = new Map(steps.map((step) => [step.step_id, step.name]))

  // A decision lists every way out of it as a row; anything else has one exit.
  const rowsOf = new Map<string, BranchRow[]>()
  const handleOf = new Map<MapEdge, string>()
  for (const step of steps) {
    if (step.kind !== "decision") continue
    const out = edges.filter(
      (edge) => edge.source === step.step_id && edge.target !== step.step_id
    )
    rowsOf.set(
      step.step_id,
      out.map((edge, index) => {
        const id = `row-${index}`
        handleOf.set(edge, id)
        return {
          id,
          label:
            edgeLabel(edge) ??
            edge.condition?.branch ??
            names.get(edge.target) ??
            "",
          exception: edge.relation === "exception",
          uncertain: edge.resolution !== "resolved",
        }
      })
    )
  }

  const findings = new Set(view.findings.map((finding) => finding.finding_id))
  const nodes: StepNode[] = steps.map((step) => {
    const coupons = view.byStep.get(step.step_id) ?? []
    const rows = rowsOf.get(step.step_id) ?? []
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
    const compact =
      !coupons.length &&
      !rows.length &&
      !loops.length &&
      !badged &&
      (step.kind === "trigger" ||
        (step.kind === "result" && !outgoing.some((edge) => forward.has(edge))))
    return {
      id: step.step_id,
      type: "step",
      position: { x: 0, y: 0 },
      draggable: false,
      connectable: false,
      data: {
        step,
        rows,
        coupons,
        isNew,
        risk,
        ghost: false,
        loops,
        removedFlow: view.removed,
        skeleton: view.flow.stage === "skeleton",
        compact,
        width: compact
          ? Math.min(236, Math.max(148, 62 + textWidth(step.name)))
          : NODE_WIDTH,
        hasIn: incoming.length > 0,
        hasOut: !rows.length && outgoing.length > 0,
      },
    }
  })

  const flowEdges: FlowEdge[] = edges
    .filter((edge) => edge.target !== edge.source)
    .map((edge) => ({
      id: keyOf.get(edge) ?? `${edge.source}>${edge.target}`,
      type: "flow",
      source: edge.source,
      target: edge.target,
      sourceHandle: handleOf.get(edge) ?? "out",
      targetHandle: "in",
      focusable: false,
      data: {
        // A decision's row already names its branch; only other edges carry a label.
        label: handleOf.has(edge) ? undefined : edgeLabel(edge),
        exception: edge.relation === "exception",
        uncertain: edge.resolution !== "resolved",
        back: !forward.has(edge),
      },
    }))

  const graph = new dagre.graphlib.Graph()
  graph.setGraph({
    rankdir: "LR",
    nodesep: 34,
    ranksep: 84,
    marginx: 24,
    marginy: 24,
  })
  graph.setDefaultEdgeLabel(() => ({}))
  for (const node of nodes)
    graph.setNode(node.id, {
      width: node.data.width,
      height: heightOf(node.data),
    })
  for (const edge of flowEdges)
    if (!edge.data?.back) graph.setEdge(edge.source, edge.target)
  dagre.layout(graph)
  for (const node of nodes) {
    const box = graph.node(node.id)
    node.position = { x: box.x - box.width / 2, y: box.y - box.height / 2 }
  }
  untangleBranches(nodes, flowEdges)

  // Steps the change removed have no place among the current ones: they wait in a row below.
  if (view.removedSteps.length) {
    const bottom = Math.max(
      ...nodes.map((node) => node.position.y + heightOf(node.data)),
      0
    )
    const left = Math.min(...nodes.map((node) => node.position.x), 0)
    view.removedSteps.forEach((coupon, index) => {
      const removed = coupon.place.removed_step
      if (!removed) return
      nodes.push({
        id: removedNodeId(removed.step_id, coupon.no),
        type: "step",
        position: { x: left + index * (NODE_WIDTH + 34), y: bottom + 72 },
        draggable: false,
        connectable: false,
        data: {
          step: {
            step_id: removed.step_id,
            name: removed.name,
            kind: "action",
            support: "agent_synthesis",
            resolution: "resolved",
          },
          rows: [],
          coupons: [coupon],
          isNew: false,
          ghost: true,
          loops: [],
          removedFlow: false,
          skeleton: false,
          compact: false,
          width: NODE_WIDTH,
          hasIn: false,
          hasOut: false,
        },
      })
    })
  }
  return { nodes, edges: flowEdges }
}

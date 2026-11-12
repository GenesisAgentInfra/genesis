import type { MapEdge, MapStep } from "./types"

/**
 * A flow laid out as a route: one row per step, read top to bottom, with each
 * branch running in its own lane until it reaches its stop. Edges that return to an
 * earlier step (retries, loops) are not drawn as lines; the row says where it goes back.
 */

export interface Segment {
  lane: number
  edge: string
  dashed: boolean
  exception: boolean
}

export interface RouteRow {
  step: MapStep
  lane: number
  incoming: Segment[]
  outgoing: Segment[]
  through: Segment[]
  labels: { text: string; exception: boolean; dashed: boolean }[]
  loops: { edge: MapEdge; target: MapStep | undefined }[]
  terminal: boolean
}

export interface RouteLayout {
  rows: RouteRow[]
  lanes: number
  edgeKey: Map<MapEdge, string>
  forward: MapEdge[]
}

export function edgeLabel(edge: MapEdge): string | undefined {
  return edge.condition?.label ?? edge.label
}

export function layoutRoute(steps: MapStep[], edges: MapEdge[]): RouteLayout {
  const byId = new Map(steps.map((step) => [step.step_id, step]))
  const edgeKey = new Map<MapEdge, string>()
  edges.forEach((edge, index) =>
    edgeKey.set(edge, `${edge.source}>${edge.target}#${index}`)
  )
  const out = new Map<string, MapEdge[]>()
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue
    out.set(edge.source, [...(out.get(edge.source) ?? []), edge])
  }

  // Edges that point back to a step already on the walk are loops.
  const back = new Set<MapEdge>()
  const state = new Map<string, 1 | 2>()
  const visit = (id: string) => {
    state.set(id, 1)
    for (const edge of out.get(id) ?? []) {
      const seen = state.get(edge.target)
      if (edge.target === id || seen === 1) back.add(edge)
      else if (!seen) visit(edge.target)
    }
    state.set(id, 2)
  }
  const triggers = steps.filter((step) => step.kind === "trigger")
  for (const step of [...triggers, ...steps])
    if (!state.has(step.step_id)) visit(step.step_id)
  const forward = edges.filter(
    (edge) => !back.has(edge) && out.get(edge.source)?.includes(edge)
  )

  // Order rows depth first, so each branch reads as one run of stops; a step where
  // branches meet comes after the last of them.
  const indegree = new Map(steps.map((step) => [step.step_id, 0]))
  for (const edge of forward)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  const starts = [
    ...triggers,
    ...steps.filter((step) => step.kind !== "trigger"),
  ].filter((step) => indegree.get(step.step_id) === 0)
  const stack = [...new Set(starts)].reverse().map((step) => step.step_id)
  const order: string[] = []
  const placed = new Set<string>()
  while (stack.length) {
    const id = stack.pop()!
    if (placed.has(id)) continue
    placed.add(id)
    order.push(id)
    const children = forward.filter((edge) => edge.source === id)
    for (const edge of [...children].reverse()) {
      const left = (indegree.get(edge.target) ?? 1) - 1
      indegree.set(edge.target, left)
      if (left === 0) stack.push(edge.target)
    }
  }
  for (const step of steps)
    if (!placed.has(step.step_id)) order.push(step.step_id)

  // Lanes: each pending edge owns a lane until its target row is reached.
  const pending: (({ target: string } & Segment) | null)[] = []
  const free = () => {
    const index = pending.findIndex((item) => item === null)
    return index === -1 ? pending.length : index
  }
  let lanes = 1
  const rows: RouteRow[] = []
  for (const id of order) {
    const step = byId.get(id)!
    const arriving = pending
      .map((item, lane) => (item && item.target === id ? lane : -1))
      .filter((lane) => lane >= 0)
    const lane = arriving.length ? Math.min(...arriving) : free()
    const incoming = arriving.map((index) => {
      const item = pending[index]!
      return {
        lane: index,
        edge: item.edge,
        dashed: item.dashed,
        exception: item.exception,
      }
    })
    for (const index of arriving) pending[index] = null
    const through: Segment[] = []
    pending.forEach((item, index) => {
      if (item)
        through.push({
          lane: index,
          edge: item.edge,
          dashed: item.dashed,
          exception: item.exception,
        })
    })
    const outgoing: Segment[] = []
    const children = forward.filter((edge) => edge.source === id)
    children.forEach((edge, index) => {
      const target = index === 0 && !pending[lane] ? lane : free()
      const segment = {
        lane: target,
        edge: edgeKey.get(edge)!,
        dashed: edge.resolution !== "resolved",
        exception: edge.relation === "exception",
      }
      pending[target] = { ...segment, target: edge.target }
      outgoing.push(segment)
    })
    lanes = Math.max(
      lanes,
      lane + 1,
      ...outgoing.map((item) => item.lane + 1),
      ...through.map((item) => item.lane + 1)
    )
    const labels = forward
      .filter((edge) => edge.target === id && edgeLabel(edge))
      .map((edge) => ({
        text: edgeLabel(edge)!,
        exception: edge.relation === "exception",
        dashed: edge.resolution !== "resolved",
      }))
    const loops = (out.get(id) ?? [])
      .filter((edge) => back.has(edge))
      .map((edge) => ({ edge, target: byId.get(edge.target) }))
    rows.push({
      step,
      lane,
      incoming,
      outgoing,
      through,
      labels,
      loops,
      terminal: children.length === 0,
    })
  }
  return { rows, lanes, edgeKey, forward }
}

/** The edges and steps on one route from a trigger to `target`, for lighting it. */
export function routeTo(
  layout: RouteLayout,
  target: string
): { edges: Set<string>; steps: Set<string> } {
  const starts = layout.rows
    .filter((row) => row.incoming.length === 0)
    .map((row) => row.step.step_id)
  const previous = new Map<string, { from: string; edge: string }>()
  const queue = [...starts]
  const seen = new Set(starts)
  while (queue.length) {
    const id = queue.shift()!
    if (id === target) break
    for (const edge of layout.forward) {
      if (edge.source !== id || seen.has(edge.target)) continue
      seen.add(edge.target)
      previous.set(edge.target, { from: id, edge: layout.edgeKey.get(edge)! })
      queue.push(edge.target)
    }
  }
  const edges = new Set<string>()
  const steps = new Set<string>([target])
  let cursor = target
  while (previous.has(cursor)) {
    const step = previous.get(cursor)!
    edges.add(step.edge)
    steps.add(step.from)
    cursor = step.from
  }
  return seen.has(target)
    ? { edges, steps }
    : { edges: new Set(), steps: new Set() }
}

import type { MapEdge, MapStep } from "./types"

/**
 * A flow as a graph to travel: which of its lines lead on and which step back, the order
 * its steps read in, what a step leads to, the way in to a step, and the way through worth
 * walking. Whatever follows a flow's lines asks here, whether it is the whole flow as the
 * map describes it or the part of it a diagram draws.
 */

/** One line of a flow, under the name its diagram draws it by. */
export interface Line<E = unknown> {
  id: string
  source: string
  target: string
  /** It returns to a step already on the way (a retry, a loop), or leads nowhere drawn. */
  back: boolean
  exception: boolean
  /** What it was made from. */
  of: E
}

export interface FlowGraph<E = unknown> {
  /** Its steps in reading order: a step comes after the steps that lead to it. */
  order: string[]
  /** Every line, in the order the flow lists them. */
  lines: Line<E>[]
  /** The lines that lead on, by the step they leave and by the step they reach. */
  out: Map<string, Line<E>[]>
  into: Map<string, Line<E>[]>
  /** The lines that step back to an earlier step, or onto the step they leave. */
  loops: Line<E>[]
  /** The steps nothing leads into, in reading order. */
  sources: string[]
}

/** What a line says: the condition it is taken on, or its own label. */
export function edgeLabel(edge: MapEdge): string | undefined {
  return edge.condition?.label ?? edge.label
}

function index<E>(lines: Line<E>[]): Pick<FlowGraph<E>, "out" | "into"> {
  const out = new Map<string, Line<E>[]>()
  const into = new Map<string, Line<E>[]>()
  for (const line of lines) {
    if (line.back) continue
    out.set(line.source, [...(out.get(line.source) ?? []), line])
    into.set(line.target, [...(into.get(line.target) ?? []), line])
  }
  return { out, into }
}

/**
 * The graph of a flow as the map describes it. A line that points back to a step already
 * on the walk from a trigger is a loop; the rest lead on. Steps read depth first, so each
 * branch is one run, and a step where branches meet comes after the last of them.
 */
export function graphOf(
  steps: MapStep[],
  edges: MapEdge[]
): FlowGraph<MapEdge> {
  const known = new Set(steps.map((step) => step.step_id))
  const leaving = new Map<string, MapEdge[]>()
  for (const edge of edges) {
    if (!known.has(edge.source) || !known.has(edge.target)) continue
    leaving.set(edge.source, [...(leaving.get(edge.source) ?? []), edge])
  }

  const returning = new Set<MapEdge>()
  const state = new Map<string, "open" | "done">()
  const visit = (id: string) => {
    state.set(id, "open")
    for (const edge of leaving.get(id) ?? []) {
      const seen = state.get(edge.target)
      if (edge.target === id || seen === "open") returning.add(edge)
      else if (!seen) visit(edge.target)
    }
    state.set(id, "done")
  }
  const triggers = steps.filter((step) => step.kind === "trigger")
  for (const step of [...triggers, ...steps])
    if (!state.has(step.step_id)) visit(step.step_id)

  const lines: Line<MapEdge>[] = edges.map((edge, at) => ({
    id: `${edge.source}>${edge.target}#${at}`,
    source: edge.source,
    target: edge.target,
    back:
      returning.has(edge) || !known.has(edge.source) || !known.has(edge.target),
    exception: edge.relation === "exception",
    of: edge,
  }))
  const { out, into } = index(lines)

  const waiting = new Map(
    steps.map((step) => [step.step_id, into.get(step.step_id)?.length ?? 0])
  )
  const starts = [
    ...triggers,
    ...steps.filter((step) => step.kind !== "trigger"),
  ].filter((step) => waiting.get(step.step_id) === 0)
  const stack = [...new Set(starts)].reverse().map((step) => step.step_id)
  const order: string[] = []
  const placed = new Set<string>()
  while (stack.length) {
    const id = stack.pop()!
    if (placed.has(id)) continue
    placed.add(id)
    order.push(id)
    for (const line of [...(out.get(id) ?? [])].reverse()) {
      const left = (waiting.get(line.target) ?? 1) - 1
      waiting.set(line.target, left)
      if (left === 0) stack.push(line.target)
    }
  }
  for (const step of steps)
    if (!placed.has(step.step_id)) order.push(step.step_id)

  return {
    order,
    lines,
    out,
    into,
    loops: lines.filter((line) => returning.has(line.of)),
    sources: order.filter((id) => !into.has(id)),
  }
}

/** The graph of what a diagram draws: its steps in the order given, its lines as marked. */
export function drawnGraph<E>(order: string[], lines: Line<E>[]): FlowGraph<E> {
  const known = new Set(order)
  const drawn = lines.filter(
    (line) =>
      known.has(line.source) &&
      known.has(line.target) &&
      line.source !== line.target
  )
  const { out, into } = index(drawn)
  return {
    order,
    lines: drawn,
    out,
    into,
    loops: drawn.filter((line) => line.back),
    sources: order.filter((id) => !into.has(id)),
  }
}

/** What a step leads to: the steps one line on, and every step further on, nearest first. */
export function after(
  graph: FlowGraph,
  id: string
): { next: string[]; reached: string[] } {
  const next = [
    ...new Set((graph.out.get(id) ?? []).map((line) => line.target)),
  ]
  const seen = new Set([id])
  const queue = [id]
  const reached: string[] = []
  while (queue.length)
    for (const line of graph.out.get(queue.shift()!) ?? []) {
      if (seen.has(line.target)) continue
      seen.add(line.target)
      reached.push(line.target)
      queue.push(line.target)
    }
  return { next, reached }
}

/** The shortest way in to a step from where the flow starts: its lines and its steps. */
export function wayIn(
  graph: FlowGraph,
  target: string,
  starts: string[] = graph.sources
): { lines: Set<string>; steps: Set<string> } {
  const previous = new Map<string, Line>()
  const seen = new Set(starts)
  const queue = [...starts]
  while (queue.length) {
    const id = queue.shift()!
    if (id === target) break
    for (const line of graph.out.get(id) ?? []) {
      if (seen.has(line.target)) continue
      seen.add(line.target)
      previous.set(line.target, line)
      queue.push(line.target)
    }
  }
  const lines = new Set<string>()
  const steps = new Set<string>()
  if (!seen.has(target)) return { lines, steps }
  steps.add(target)
  for (let at = target; previous.has(at); at = previous.get(at)!.source) {
    lines.add(previous.get(at)!.id)
    steps.add(previous.get(at)!.source)
  }
  return { lines, steps }
}

/**
 * The way through a flow worth watching: from `start`, at each fork the branch that passes
 * the most of the steps in `marked`, then the one off the error path, then the longer one.
 */
export function wayThrough(
  graph: FlowGraph,
  start: string | undefined,
  marked: Set<string>
): { steps: string[]; lines: string[] } {
  if (!start) return { steps: [], lines: [] }
  interface Best {
    marked: number
    errors: number
    length: number
    line?: Line
  }
  const memo = new Map<string, Best>()
  const better = (a: Best, b: Best) =>
    a.marked !== b.marked
      ? a.marked > b.marked
      : a.errors !== b.errors
        ? a.errors < b.errors
        : a.length > b.length
  const best = (id: string, trail: Set<string>): Best => {
    const known = memo.get(id)
    if (known) return known
    let pick: Best = { marked: 0, errors: 0, length: 0 }
    for (const line of graph.out.get(id) ?? []) {
      if (trail.has(line.target)) continue
      trail.add(line.target)
      const rest = best(line.target, trail)
      trail.delete(line.target)
      const next: Best = {
        marked: rest.marked + (marked.has(line.target) ? 1 : 0),
        errors: rest.errors + (line.exception ? 1 : 0),
        length: rest.length + 1,
        line,
      }
      if (!pick.line || better(next, pick)) pick = next
    }
    memo.set(id, pick)
    return pick
  }
  best(start, new Set([start]))
  const steps = [start]
  const lines: string[] = []
  const seen = new Set(steps)
  for (let at = start; ;) {
    const line = memo.get(at)?.line
    if (!line || seen.has(line.target)) break
    lines.push(line.id)
    steps.push(line.target)
    seen.add(line.target)
    at = line.target
  }
  return { steps, lines }
}

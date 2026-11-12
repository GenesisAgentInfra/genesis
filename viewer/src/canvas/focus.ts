import { edgeLabel, type RouteLayout } from "@/layout"
import type { MapEdge, MapStep } from "@/types"

/**
 * A flow cut down to what a change needs to be read: the steps it touches, the step each
 * of them is reached from, and where the flow starts. Whatever lies between two of those
 * is one line that says how many steps it stands for. A reader who wants the rest opens
 * the module.
 */

/** A line that stands for the steps left out between two that are drawn. */
export interface Skip {
  source: string
  target: string
  /** How many steps it leaves out. */
  steps: number
  /** The branch taken out of the source, when every way into the gap is the same one. */
  label?: string
  exception: boolean
}

export interface Cut {
  keep: Set<string>
  skips: Skip[]
}

/** A gap of one step is cheaper to draw than to announce. */
const WORTH_FOLDING = 2
const ROUNDS = 8

export function cutFlow(
  steps: MapStep[],
  layout: RouteLayout,
  /** The steps the change touches. */
  marked: Set<string>
): Cut | undefined {
  if (!marked.size) return undefined
  const out = new Map<string, MapEdge[]>()
  const into = new Map<string, MapEdge[]>()
  for (const edge of layout.forward) {
    if (edge.source === edge.target) continue
    out.set(edge.source, [...(out.get(edge.source) ?? []), edge])
    into.set(edge.target, [...(into.get(edge.target) ?? []), edge])
  }
  const triggers = steps.filter((step) => step.kind === "trigger")
  const starts = (
    triggers.length ? triggers : steps.filter((step) => !into.has(step.step_id))
  ).map((step) => step.step_id)

  // The step a changed one is reached from: the one before it on the shortest way in.
  const before = new Map<string, string>()
  const seen = new Set(starts)
  const queue = [...starts]
  while (queue.length) {
    const id = queue.shift()!
    for (const edge of out.get(id) ?? []) {
      if (seen.has(edge.target)) continue
      seen.add(edge.target)
      before.set(edge.target, id)
      queue.push(edge.target)
    }
  }
  const keep = new Set([...marked, ...starts.slice(0, triggers.length || 1)])
  for (const id of marked) {
    const sources = (into.get(id) ?? []).map((edge) => edge.source)
    // A changed step that follows another changed step already has its way in on show.
    if (!sources.length || sources.some((source) => marked.has(source)))
      continue
    keep.add(before.get(id) ?? sources[0])
  }

  /** The hidden steps one end of `edges` away from a kept step, and on from those. */
  const spread = (
    from: string,
    edges: Map<string, MapEdge[]>,
    end: "source" | "target"
  ) => {
    const found = new Set<string>()
    const walk = [from]
    while (walk.length)
      for (const edge of edges.get(walk.pop()!) ?? []) {
        const next = edge[end]
        if (keep.has(next) || found.has(next)) continue
        found.add(next)
        walk.push(next)
      }
    return found
  }
  const contract = (): (Skip & { inside: string[] })[] => {
    const after = new Map(
      [...keep].map((id) => [id, spread(id, out, "target")])
    )
    const ahead = new Map(
      [...keep].map((id) => [id, spread(id, into, "source")])
    )
    const drawn = new Map<string, Set<string>>()
    const link = (source: string, target: string) =>
      drawn.set(source, (drawn.get(source) ?? new Set()).add(target))
    for (const edge of layout.forward)
      if (keep.has(edge.source) && keep.has(edge.target))
        link(edge.source, edge.target)
    const found: (Skip & { inside: string[] })[] = []
    for (const source of keep)
      for (const target of keep) {
        if (source === target) continue
        const inside = [...after.get(source)!].filter((id) =>
          ahead.get(target)!.has(id)
        )
        if (!inside.length) continue
        const among = new Set(inside)
        const ways = (out.get(source) ?? []).filter((edge) =>
          among.has(edge.target)
        )
        const labels = new Set(ways.map((edge) => edgeLabel(edge) ?? ""))
        found.push({
          source,
          target,
          steps: inside.length,
          inside,
          label: labels.size === 1 ? [...labels][0] || undefined : undefined,
          exception:
            ways.length > 0 &&
            ways.every((edge) => edge.relation === "exception"),
        })
        link(source, target)
      }
    // A gap is drawn only where nothing on show already leads the same way.
    const reaches = (from: string, to: string, skip: Skip) => {
      const visited = new Set([from])
      const walk = [from]
      while (walk.length) {
        const at = walk.pop()!
        for (const next of drawn.get(at) ?? []) {
          if (at === skip.source && next === skip.target) continue
          if (next === to) return true
          if (visited.has(next)) continue
          visited.add(next)
          walk.push(next)
        }
      }
      return false
    }
    const direct = (skip: Skip) =>
      (out.get(skip.source) ?? []).some((edge) => edge.target === skip.target)
    return found.filter(
      (skip) => !direct(skip) && !reaches(skip.source, skip.target, skip)
    )
  }

  for (let round = 0; round < ROUNDS; round++) {
    const skips = contract()
    const short = skips.filter((skip) => skip.steps < WORTH_FOLDING)
    if (!short.length) return { keep, skips }
    for (const skip of short) for (const id of skip.inside) keep.add(id)
  }
  return { keep, skips: contract() }
}

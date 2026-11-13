import {
  APART,
  SEP,
  flowIdOf,
  homeOf,
  stepNodeId,
  type Atlas,
  type AtlasNode,
} from "@/atlas/build"
import { GLIDE_ARM, GLIDE_MS, type Shot } from "@/canvas/camera"
import { WALK_LEAD, walkTimes, type Trail } from "@/canvas/emphasis"
import type { StepNode } from "@/canvas/graph"
import { wayThrough } from "@/flow-graph"
import type { Model } from "@/model"

/**
 * Where the reader is on the map, and where each thing they do takes them. `act` is the
 * whole of it: from one place and one action it gives the next place, and with it what
 * the camera should look at. It holds no screen and moves nothing, so every rule about
 * what a click, a key or a link does can be read, and tested, right here.
 */

/** What the panel is about. */
export type Selected =
  | { type: "step"; node: string }
  | { type: "offMap"; no: number }
  | { type: "removedFlow"; flowId: string }

/** A walk through one flow, the way it usually runs. */
export interface Walk {
  /** Which walk this is: no two share a number. */
  run: number
  flowId: string
  steps: string[]
  /** How far it has got, and whether it is over. */
  at: number
  done: boolean
  /** When each of its lines draws and each step is reached. */
  trail: Trail
}

/** Something for the camera to look at; a new number is a new order. */
export interface Order {
  no: number
  shot: Shot
  /** How long the camera takes to get there. */
  ms: number
}

export interface Place {
  /** The module whose flows are drawn step by step; every other flow stays folded. */
  focused?: string
  selected?: Selected
  /** The change picked on the map: its card rings and what it leads to answers. */
  current?: { node: string; no: number }
  /** The ripple of the change picked: which one it is, whether it has played out, and
   *  how long after it starts the ring comes (while the camera is still on its way). */
  ripple: { run: number; settled: boolean; delay: number }
  walk?: Walk
  /** The last thing the camera was sent to look at. */
  camera: Order
}

/** The whole map, nothing picked. */
export const START: Place = {
  ripple: { run: 0, settled: true, delay: 0 },
  camera: { no: 0, shot: { of: "place" }, ms: 0 },
}

/** What the reader moves about in. */
export interface World {
  model: Model
  /** The map as it is drawn with a module open, or with none. */
  atlasOf: (focused?: string) => Atlas
  /** Things glide and play; off for a reader who asked for less motion. */
  motion: boolean
}

export type Act =
  /** A click, or Enter, on something drawn on the map. */
  | { do: "node"; id: string }
  /** A click on the empty canvas. */
  | { do: "pane" }
  /** A change asked for by its number: from the list, or from the address. */
  | { do: "change"; no: number }
  /** On to the next change, or back to the one before. */
  | { do: "step"; by: number }
  | { do: "walk"; flowId: string }
  | { do: "endWalk" }
  /** A walk's own beats: the camera sets off for a step, the walk reaches it. */
  | { do: "lead"; run: number; step: string }
  | { do: "reach"; run: number; step: string }
  /** The panel's own way out. */
  | { do: "close" }
  /** Back to the whole map. */
  | { do: "overview" }
  /** The button that puts the place back in frame. */
  | { do: "fit" }
  /** Esc: one step back. */
  | { do: "escape" }
  /** The reader took the canvas in hand, or typed something else. */
  | { do: "touch" }

/** A walk's camera sets off for each step this long before its line gets there, and takes
 *  this long to arrive. */
const WALK_AHEAD = 320
const WALK_GLIDE = 420

const glide = (world: World) => (world.motion ? GLIDE_MS : 0)
const look = (place: Place, shot: Shot, ms: number): Place => ({
  ...place,
  camera: { no: place.camera.no + 1, shot, ms },
})
/** The camera goes to wherever the reader now is. */
const follow = (place: Place, world: World) =>
  look(place, { of: "place" }, glide(world))
const endWalk = (place: Place): Place =>
  place.walk ? { ...place, walk: undefined } : place
const settle = (place: Place): Place =>
  place.ripple.settled
    ? place
    : { ...place, ripple: { ...place.ripple, settled: true } }
const open = (place: Place, selected: Selected, world: World) =>
  follow({ ...place, selected }, world)
const close = (place: Place, world: World) =>
  place.selected ? follow({ ...place, selected: undefined }, world) : place
const overview = (place: Place, world: World) =>
  follow(
    {
      ...endWalk(place),
      focused: undefined,
      current: undefined,
      selected: undefined,
    },
    world
  )

const stepOn = (atlas: Atlas, id: string) =>
  atlas.nodes.find(
    (node): node is StepNode => node.id === id && node.type === "step"
  )

/** Whether the panel is up, and the node on the map it is about. */
export function panelOf(
  selected: Selected | undefined,
  atlas: Atlas
): { open: boolean; node?: string } {
  if (!selected) return { open: false }
  if (selected.type === "offMap")
    return { open: true, node: `offmap${SEP}${selected.no}` }
  if (selected.type === "removedFlow")
    return { open: true, node: atlas.flows.get(selected.flowId)?.triggers[0] }
  // A step folded away when another module opened has no panel to show.
  return stepOn(atlas, selected.node)
    ? { open: true, node: selected.node }
    : { open: false }
}

/** The number of the change on show. */
export function pickedOf(place: Place, model: Model): number | undefined {
  const { selected } = place
  if (place.current) return place.current.no
  if (selected?.type === "offMap") return selected.no
  if (selected?.type === "removedFlow")
    return model.stops.find(
      (stop) => stop.kind === "removed_flow" && stop.flowId === selected.flowId
    )?.no
  return undefined
}

/** A module opens; asked for by one of its flows, that flow is what gets framed. */
function focusOn(
  place: Place,
  module: string,
  world: World,
  flowId?: string
): Place {
  if (place.focused === module) return place
  const next = { ...place, focused: module }
  // With the panel up, what it is about stays the subject.
  return flowId && !panelOf(next.selected, world.atlasOf(module)).open
    ? look(next, { of: "flow", flowId }, glide(world))
    : follow(next, world)
}

/** A change is picked on its step: it rings, and the steps it leads to answer. */
function pick(place: Place, node: StepNode, world: World, no?: number): Place {
  const { coupons } = node.data
  const shown =
    coupons.find((coupon) => coupon.no === (no ?? place.current?.no)) ??
    coupons[0]
  return {
    ...place,
    current: { node: node.id, no: shown.no },
    ripple: {
      run: place.ripple.run + 1,
      settled: false,
      delay: world.motion ? GLIDE_ARM : 0,
    },
  }
}

/** The map goes to a change and its details open. */
function toChange(place: Place, no: number, world: World): Place {
  const stop = world.model.stops[no - 1]
  if (!stop) return place
  let next = endWalk(place)
  const home =
    stop.kind === "off_map"
      ? APART
      : world.atlasOf(next.focused).home.get(stop.flowId ?? "")
  // A change outside the open module is shown on the whole map.
  if (next.focused && home !== next.focused)
    next = follow({ ...next, focused: undefined }, world)
  if (stop.kind === "off_map")
    return open({ ...next, current: undefined }, { type: "offMap", no }, world)
  if (stop.kind === "removed_flow" && stop.flowId)
    return open(
      { ...next, current: undefined },
      { type: "removedFlow", flowId: stop.flowId },
      world
    )
  const node =
    stop.flowId && stop.nodeId
      ? stepOn(
          world.atlasOf(next.focused),
          stepNodeId(stop.flowId, stop.nodeId)
        )
      : undefined
  if (!node) return next
  return pick(
    open(next, { type: "step", node: node.id }, world),
    node,
    world,
    no
  )
}

/** On to the next change, or back to the one before; past either end it wraps. */
function toNeighbour(place: Place, by: number, world: World): Place {
  const count = world.model.stops.length
  if (!count) return place
  const picked = pickedOf(place, world.model)
  const next = picked
    ? ((picked - 1 + by + count) % count) + 1
    : by > 0
      ? 1
      : count
  return toChange(place, next, world)
}

/** A flow is walked the way it usually runs, the camera riding along. */
function startWalk(place: Place, flowId: string, world: World): Place {
  const before = world.atlasOf(place.focused)
  if (!before.flows.has(flowId)) return place
  let next: Place = { ...endWalk(place), current: undefined }
  // A walk passes every step, so the flow's module opens first.
  const module = before.home.get(flowId)
  if (before.flows.get(flowId)!.mode !== "full" && module)
    next = focusOn(next, module, world, flowId)
  const placed = world.atlasOf(next.focused).flows.get(flowId)
  if (placed?.mode !== "full") return next
  const changed = new Set(
    placed.nodes
      .filter((node) => node.data.coupons.length)
      .map((node) => node.id)
  )
  const path = wayThrough(placed.graph, placed.triggers[0], changed)
  if (!path.steps.length) return next
  const run = next.camera.no + 1
  const trail = walkTimes(run, path.steps, path.lines, changed, world.motion)
  const last = path.steps.length - 1
  const walking: Place = {
    ...next,
    walk: {
      run,
      flowId,
      steps: path.steps,
      at: world.motion ? 0 : last,
      done: !world.motion,
      trail,
    },
  }
  // Without motion the whole way is shown at once.
  return world.motion
    ? look(walking, { of: "step", id: path.steps[0] }, WALK_LEAD - 40)
    : look(walking, { of: "steps", ids: path.steps }, 0)
}

/**
 * When the things of a walk happen, in milliseconds from its start, for whoever keeps the
 * time: the camera sets off for each step ahead of the line that reaches it.
 */
export function beats(trail: Trail): { at: number; act: Act }[] {
  if (!trail.animate) return []
  return [...trail.steps].flatMap(([step, arrive], index) => [
    ...(index > 0
      ? [
          {
            at: Math.max(arrive - WALK_AHEAD, 0),
            act: { do: "lead", run: trail.run, step } as const,
          },
        ]
      : []),
    { at: arrive, act: { do: "reach", run: trail.run, step } as const },
  ])
}

/** Something drawn on the map is clicked. */
function onNode(place: Place, node: AtlasNode, world: World): Place {
  if (node.type === "box") return place
  const atlas = world.atlasOf(place.focused)
  const next = endWalk(place)
  if (node.type === "module") return focusOn(next, node.id, world)
  const home = homeOf(atlas, node)
  // In a module other than the open one: a change is shown from the whole map, anything
  // else opens its own module.
  if (next.focused && home && home !== next.focused) {
    const change =
      node.type === "offmap"
        ? node.data.coupon.no
        : node.type === "step"
          ? node.data.coupons[0]?.no
          : undefined
    return change
      ? toChange(next, change, world)
      : focusOn(next, home, world, flowIdOf(node))
  }
  switch (node.type) {
    case "more":
      // The folded lookups and upkeep are listed by opening their module.
      return home ? focusOn(next, home, world) : next
    case "flow":
    case "row": {
      const { flowId, struck } = node.data
      if (struck) return open(next, { type: "removedFlow", flowId }, world)
      if (!flowId || !home) return next
      if (home !== next.focused) return focusOn(next, home, world, flowId)
      // Already open: its name brings its steps into frame.
      const steps = atlas.flows.get(flowId)?.nodes ?? []
      return steps.length
        ? look(
            next,
            { of: "steps", ids: steps.map((step) => step.id) },
            glide(world)
          )
        : next
    }
    case "offmap":
      return open(next, { type: "offMap", no: node.data.coupon.no }, world)
    case "step": {
      // The pill that stands for steps left out opens the module on its flow.
      if (node.data.stub)
        return home ? focusOn(next, home, world, flowIdOf(node)) : next
      const opened = open(next, { type: "step", node: node.id }, world)
      return node.data.coupons.length && !node.data.removedFlow
        ? pick(opened, node, world)
        : opened
    }
  }
}

export function act(place: Place, action: Act, world: World): Place {
  switch (action.do) {
    case "node": {
      const node = world
        .atlasOf(place.focused)
        .nodes.find((item) => item.id === action.id)
      return node ? onNode(place, node, world) : place
    }
    case "pane": {
      const closed = close(place, world)
      return closed.current ? { ...closed, current: undefined } : closed
    }
    case "change":
      return toChange(place, action.no, world)
    case "step":
      return toNeighbour(place, action.by, world)
    case "walk":
      return startWalk(place, action.flowId, world)
    case "endWalk":
      return endWalk(place)
    case "lead":
      return place.walk?.run === action.run
        ? look(place, { of: "step", id: action.step }, WALK_GLIDE)
        : place
    case "reach": {
      const { walk } = place
      if (walk?.run !== action.run) return place
      const at = walk.steps.indexOf(action.step)
      return {
        ...place,
        walk: { ...walk, at, done: at === walk.steps.length - 1 },
      }
    }
    case "close":
      return close(place, world)
    case "overview":
      return overview(place, world)
    case "fit":
      return place.focused ? overview(place, world) : follow(place, world)
    case "escape": {
      // One step back: out of the walk, the panel, the picked change, the open module.
      const calm = settle(place)
      if (calm.walk) return endWalk(calm)
      if (calm.selected) return close(calm, world)
      if (calm.current) return { ...calm, current: undefined }
      return calm.focused ? overview(calm, world) : calm
    }
    case "touch":
      return endWalk(settle(place))
  }
}

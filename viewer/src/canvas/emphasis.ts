import { SEP, stepNodeId, type PlacedFlow } from "@/atlas/build"
import { wayIn } from "@/flow-graph"
import { reachOf } from "@/model"

/**
 * How loud each step and each line is. From where the reader is (the change picked, the
 * step whose panel is open, a walk in progress, the module in focus) every step and every
 * line gets one look: whether it stands out, steps back or leaves the scene, and when its
 * part of the ripple or of the walk plays. Views draw the look they are given; none of
 * them works out again what the reader is looking at.
 */

const RING_MS = 240
export const DRAW_MS = 300
/** A walking line gets its arrowhead just before it arrives. */
export const HEAD_MS = 120
export const HEAD_EARLY = 80

/** Small motion sets the pace. Long branches share the last beat. */
export function changeTiming(small: number) {
  return {
    beat: small / 3,
    draw: small,
    panel: small * 1.1,
  }
}

/** The walk: the camera's lead before the first step, a pause at every step, a longer one
 *  at a change, and the ring a change takes as the walk reaches it. */
export const WALK_LEAD = 560
const DWELL = 140
const LINGER = 560
const WALK_RING_MS = 480

/** What a picked change lights on its flow. */
export interface Lit {
  /** The step the change is on. */
  current?: string
  /** Visible downstream steps and edges, indexed by distance from the change. */
  impactSteps: Map<string, number>
  impactLines: Map<string, number>
  /** End results it reaches beyond the next step. */
  far: Set<string>
  /** The way in from where the flow starts, drawn dark and still. */
  routeSteps: Set<string>
  routeLines: Set<string>
  /** Feedback loops touching the selected step or a downstream step. */
  loopLines: Set<string>
}
const NONE: Set<string> = new Set()
export const DARK: Lit = {
  impactSteps: new Map(),
  impactLines: new Map(),
  far: NONE,
  routeSteps: NONE,
  routeLines: NONE,
  loopLines: NONE,
}

/** A walk through one flow: when each of its lines draws and each step is reached. */
export interface Trail {
  run: number
  lines: Map<string, number>
  steps: Map<string, number>
  /** Steps that carry a change: the walk lingers there. */
  changed: Set<string>
  animate: boolean
}

/** Where the reader is, as far as loudness goes. */
export interface Spotlight {
  /** A report with changes: picking one quiets what it does not touch. */
  focus: boolean
  lit: Lit
  /** An unchanged step whose panel is open. */
  selected?: string
  /** One reveal per pick, timed by the current Graphical Small motion. */
  ripple: {
    run: number
    plays: boolean
    timing: ReturnType<typeof changeTiming>
  }
  trail?: Trail
  /** The flows inside the module in focus; everything else steps back. */
  focusedFlows?: Set<string>
}

/** What a change picked on `node` lights on the flow it is drawn in. */
export function litBy(placed: PlacedFlow | undefined, node: string): Lit {
  if (!placed) return DARK
  const flowId = placed.view.flow.flow_id
  const step = node.slice(flowId.length + SEP.length)
  // A step the change removed has no place on the flow: only its own card answers.
  if (!placed.view.graph.order.includes(step)) return { ...DARK, current: node }
  // What the change leads to is asked of the whole flow; the way in, of what is drawn.
  const reach = reachOf(placed.view, step)
  const route = wayIn(
    placed.graph,
    node,
    // A flow cut down to the change starts where its triggers are drawn.
    placed.mode === "focus" ? placed.triggers : undefined
  )
  const impactSteps = new Map<string, number>()
  const impactLines = new Map<string, number>()
  const queue = [node]
  for (const source of queue) {
    const depth = impactSteps.get(source) ?? 0
    for (const line of placed.graph.out.get(source) ?? []) {
      impactLines.set(line.id, depth)
      if (line.target === node || impactSteps.has(line.target)) continue
      impactSteps.set(line.target, depth + 1)
      queue.push(line.target)
    }
  }

  const routeSteps = new Set(route.steps)
  routeSteps.delete(node)
  return {
    current: node,
    impactSteps,
    impactLines,
    far: new Set(reach.far.map((id) => stepNodeId(flowId, id))),
    routeSteps,
    routeLines: route.lines,
    loopLines: new Set(
      placed.graph.loops
        .filter(
          (line) =>
            line.source === node ||
            line.target === node ||
            impactSteps.has(line.source)
        )
        .map((line) => line.id)
    ),
  }
}

function impactStart(depth: number, beat: number) {
  return (Math.min(depth, 2) + 1) * beat
}

/**
 * The timetable of a walk along `steps` and the `lines` between them: the camera's lead,
 * then each line drawn after a pause at the step it leaves, longer where that step carries
 * a change. Without animation everything is there at once.
 */
export function walkTimes(
  run: number,
  steps: string[],
  lines: string[],
  changed: Set<string>,
  animate: boolean
): Trail {
  const reached = new Map<string, number>()
  const drawn = new Map<string, number>()
  let at = animate ? WALK_LEAD : 0
  reached.set(steps[0], at)
  lines.forEach((line, index) => {
    const pause = DWELL + (changed.has(steps[index]) ? LINGER : 0)
    const start = at + (animate ? pause : 0)
    drawn.set(line, start)
    at = start + (animate ? DRAW_MS : 0)
    reached.set(steps[index + 1], at)
  })
  return {
    run,
    lines: drawn,
    steps: reached,
    changed: new Set(steps.filter((id) => changed.has(id))),
    animate,
  }
}

export interface StepLook {
  /** The change on show is on it. */
  current: boolean
  /** Its panel is open and it is not the change on show. */
  selected: boolean
  /** It is on a visible path downstream of the change. */
  reached: boolean
  /** It is on the route leading to the change. */
  context: boolean
  /** A walk passes it. */
  visited: boolean
  /** Its card steps back, and restores contrast on hover or focus. */
  quiet: boolean
  /** It sits outside the module in focus. */
  away: boolean
  /** Milliseconds before its border and shadow follow. */
  delay: number
  /** It is an end result the change can reach further on: the tag it carries, and how
   *  long before the tag comes up when it makes an entrance. One entrance per key. */
  tag?: { key: string; enters?: number }
  /** The ring that plays on it: once per `key`. */
  ring?: { key: string; delay: number; duration: number }
}

/** The flow a step or a line on the canvas belongs to, from its name. */
const flowOf = (id: string) => id.slice(0, Math.max(id.indexOf("::"), 0))

export function stepLook(
  spot: Spotlight,
  id: string,
  step: { changed: boolean; removedFlow: boolean }
): StepLook {
  const { lit, trail, ripple } = spot
  const current = lit.current === id
  const depth = lit.impactSteps.get(id)
  const reached = depth !== undefined
  const context = lit.routeSteps.has(id)
  const { beat, draw } = ripple.timing
  const impactArrival =
    reached && ripple.plays ? impactStart(depth - 1, beat) + draw : 0
  const selected = spot.selected === id && !current
  const arrive = trail?.steps.get(id)
  const visited = arrive !== undefined
  const quiet = trail
    ? !visited
    : spot.focus &&
      lit.current !== undefined &&
      !step.removedFlow &&
      !current &&
      !reached &&
      !selected &&
      !context
  const walked = visited && trail!.animate
  return {
    current,
    selected,
    reached,
    context,
    visited,
    quiet,
    away: Boolean(spot.focusedFlows && !spot.focusedFlows.has(flowOf(id))),
    delay: visited && trail!.animate ? arrive : impactArrival,
    tag: lit.far.has(id)
      ? {
          key: `tag-${ripple.run}`,
          enters: ripple.plays ? impactArrival : undefined,
        }
      : undefined,
    ring:
      walked || (current && ripple.plays)
        ? {
            key: visited ? `walk-${trail!.run}` : `ring-${ripple.run}`,
            delay: visited ? arrive : 0,
            duration: visited ? (step.changed ? WALK_RING_MS : RING_MS) : draw,
          }
        : undefined,
  }
}

export interface LineLook {
  /** It is on the way in, downstream, or on the walk. */
  dark: boolean
  impact: boolean
  quiet: boolean
  /** It sits outside the module in focus. */
  away: boolean
  dashed: boolean
  /** It makes an entrance: drawing itself, or fading in when it is dashed. */
  entering: boolean
  /** It draws itself from its first corner to its last. */
  draws: boolean
  /** A dot rides its tip while it draws. */
  travels: boolean
  /** Milliseconds before its entrance starts. */
  start: number
  duration: number
  /** One entrance per key. */
  key: string
}

export function lineLook(
  spot: Spotlight,
  id: string,
  line: { back: boolean; uncertain: boolean; skipped: boolean }
): LineLook {
  const { lit, trail, ripple } = spot
  const onRoute = lit.routeLines.has(id)
  const depth = lit.impactLines.get(id)
  const impact = depth !== undefined || lit.loopLines.has(id)
  const walkFrom = trail?.lines.get(id)
  const walked = walkFrom !== undefined
  const dark = walked || onRoute || impact
  const quiet = trail
    ? !walked
    : spot.focus &&
      (lit.current !== undefined || lit.routeLines.size > 0) &&
      !onRoute &&
      !impact
  // Keep feedback loops dashed while showing impact. A walk can trace its own lines.
  const dashed =
    line.uncertain ||
    line.skipped ||
    (line.back && (!dark || (impact && !trail)))
  const entering = walked
    ? trail!.animate
    : depth !== undefined && ripple.plays && !trail
  // A dashed line cannot draw itself; it fades in over the same stretch instead.
  const draws = entering && !dashed
  return {
    dark,
    impact: impact && !trail,
    quiet,
    away: Boolean(spot.focusedFlows && !spot.focusedFlows.has(flowOf(id))),
    dashed,
    entering,
    draws,
    travels: draws && walked,
    start: walked ? walkFrom : impactStart(depth ?? 0, ripple.timing.beat),
    duration: walked ? DRAW_MS : ripple.timing.draw,
    key: walked ? `walk-${trail!.run}` : `out-${ripple.run}`,
  }
}

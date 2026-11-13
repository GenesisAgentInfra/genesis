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

/**
 * The ripple, at most 0.6 s from its start: a ring on the change (0–240 ms), the lines
 * leaving it drawn together (120–420 ms), the next steps answering as the lines arrive, and
 * the tags on farther results last (420–600 ms).
 */
const RING_MS = 240
const DRAW_FROM = 120
export const DRAW_MS = 300
const TAG_FROM = 420
export const TAG_MS = 180
/** A drawing line gets its arrowhead as it arrives: this long, starting this much early. */
export const HEAD_MS = 120
export const HEAD_EARLY = 80
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
  /** Steps one line after it, and the end results it reaches further on. */
  next: Set<string>
  far: Set<string>
  /** The way in from where the flow starts, drawn dark and still. */
  routeSteps: Set<string>
  routeLines: Set<string>
  /** Lines leaving the change, which carry the ripple; loops on it stay in view. */
  outLines: Set<string>
  loopLines: Set<string>
  /** Lines leaving the change that are short enough to carry the travelling dot. */
  dotLines: Set<string>
}
const NONE: Set<string> = new Set()
export const DARK: Lit = {
  next: NONE,
  far: NONE,
  routeSteps: NONE,
  routeLines: NONE,
  outLines: NONE,
  loopLines: NONE,
  dotLines: NONE,
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
  /** The ripple of the change picked: which one, whether it still plays, and how long
   *  after it starts the ring comes. */
  ripple: { run: number; plays: boolean; delay: number }
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
  const out = (placed.graph.out.get(node) ?? []).map((line) => line.id)
  const routeSteps = new Set(route.steps)
  routeSteps.delete(node)
  return {
    current: node,
    next: new Set(reach.next.map((id) => stepNodeId(flowId, id))),
    far: new Set(reach.far.map((id) => stepNodeId(flowId, id))),
    routeSteps,
    routeLines: route.lines,
    outLines: new Set(out),
    loopLines: new Set(
      placed.graph.loops
        .filter((line) => line.source === node || line.target === node)
        .map((line) => line.id)
    ),
    dotLines: out.length ? shortest(placed, out) : NONE,
  }
}

/** Of some lines, those not much longer than the shortest one: they carry the dot. */
function shortest(placed: PlacedFlow, ids: string[]): Set<string> {
  const byId = new Map(placed.nodes.map((node) => [node.id, node]))
  const lengths = ids.map((id) => {
    const edge = placed.edges.find((item) => item.id === id)
    const source = byId.get(edge?.source ?? "")
    const target = byId.get(edge?.target ?? "")
    if (!source || !target) return [id, Infinity] as const
    const dx = target.position.x - (source.position.x + source.data.width)
    const dy =
      target.position.y +
      target.data.slot / 2 -
      (source.position.y + source.data.slot / 2)
    return [id, Math.hypot(dx, dy)] as const
  })
  const least = Math.min(...lengths.map(([, length]) => length))
  return new Set(
    lengths.filter(([, length]) => length <= least * 2).map(([id]) => id)
  )
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
  /** It is one line after the change on show. */
  reached: boolean
  /** A walk passes it. */
  visited: boolean
  /** Its surface and icon step back; its words stay readable. */
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
  const reached = lit.next.has(id)
  const selected = spot.selected === id && !current
  const arrive = trail?.steps.get(id)
  const visited = arrive !== undefined
  const standsOut = current || reached || selected
  // On a walk, whatever it does not pass steps back. With a change picked, so does every
  // unchanged step off its way in; a flow that is gone is shown whole.
  const quiet = trail
    ? !visited
    : spot.focus &&
      !step.removedFlow &&
      (lit.current !== undefined || lit.routeSteps.size > 0) &&
      !standsOut &&
      !step.changed &&
      !lit.routeSteps.has(id)
  const walked = visited && trail!.animate
  return {
    current,
    selected,
    reached,
    visited,
    quiet,
    away: Boolean(spot.focusedFlows && !spot.focusedFlows.has(flowOf(id))),
    delay: visited
      ? trail!.animate
        ? arrive
        : 0
      : reached && ripple.plays
        ? ripple.delay + TAG_FROM
        : 0,
    tag: lit.far.has(id)
      ? {
          key: `tag-${ripple.run}`,
          enters: ripple.plays ? ripple.delay + TAG_FROM : undefined,
        }
      : undefined,
    ring:
      walked || (current && ripple.plays)
        ? {
            key: visited ? `walk-${trail!.run}` : `ring-${ripple.run}`,
            delay: visited ? arrive : ripple.delay,
            duration: visited && step.changed ? WALK_RING_MS : RING_MS,
          }
        : undefined,
  }
}

export interface LineLook {
  /** It is on the way in, leaves the change, or a walk runs along it. */
  dark: boolean
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
  const leaves = lit.outLines.has(id)
  const walkFrom = trail?.lines.get(id)
  const walked = walkFrom !== undefined
  const dark = walked || onRoute || leaves
  const quiet = trail
    ? !walked
    : spot.focus &&
      (lit.current !== undefined || lit.routeLines.size > 0) &&
      !onRoute &&
      !leaves &&
      !lit.loopLines.has(id)
  // A line that stands for steps left out is dotted like an ellipsis; a step back is
  // dashed until something lights it.
  const dashed = line.uncertain || line.skipped || (line.back && !dark)
  const entering = walked ? trail!.animate : leaves && ripple.plays && !trail
  // A dashed line cannot draw itself; it fades in over the same stretch instead.
  const draws = entering && !dashed
  return {
    dark,
    quiet,
    away: Boolean(spot.focusedFlows && !spot.focusedFlows.has(flowOf(id))),
    dashed,
    entering,
    draws,
    travels: draws && (walked || lit.dotLines.has(id)),
    start: walked ? walkFrom : ripple.delay + DRAW_FROM,
    key: walked ? `walk-${trail!.run}` : `out-${ripple.run}`,
  }
}

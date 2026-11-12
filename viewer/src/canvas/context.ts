import * as React from "react"

import type { Strings } from "@/i18n"

/**
 * What the canvas shows about the current change. Nodes and edges read it to decide how
 * loud they are and what they animate.
 */
export interface CanvasState {
  t: Strings
  /** A report with stops: the canvas is about one change at a time. */
  focus: boolean
  /** The stop on show, so a card holding several changes shows this one. */
  stopNo?: number
  /** The node of the current change on this canvas. */
  current?: string
  /** Steps one edge after it, and the end results it reaches further on. */
  next: Set<string>
  far: Set<string>
  /** The way in from a trigger, drawn dark and still. */
  routeSteps: Set<string>
  routeEdges: Set<string>
  /** Edges leaving the change, which carry the ripple; loops on it stay in view. */
  outEdges: Set<string>
  loopEdges: Set<string>
  /** Edges leaving the change that are short enough to carry the travelling dot. */
  dotEdges: Set<string>
  /** A change off the map: the whole flow steps back. */
  dimAll: boolean
  /** An unchanged step whose panel is open. */
  selected?: string
  /** A change outside the flows, or a flow that is gone, whose panel is open. */
  apart?: string
  /** Pre-existing risks show on cards only when there is no report to walk. */
  knownRisks: boolean
  /** Bumped for every new ripple. */
  run: number
  /** The ripple may start: the camera is on its way or there. */
  armed: boolean
  /** The ripple is still to come: what it will draw is not on show yet. */
  pending: boolean
  /** The ripple plays; otherwise the end state shows at once. */
  animate: boolean
  /** Milliseconds from arming to the ring. */
  delay: number
  /** A walk through one flow: when each of its edges draws and each step is reached. */
  trail?: Trail
  trailActive: boolean
  /** A module in focus: everything outside it steps back. */
  focusedModule?: string
  /** The flows inside the focused module ("__offmap" for changes outside the flows). */
  focusedFlows?: Set<string>
}

/** Whether a node or edge of this flow sits outside the module in focus. */
export function outOfFocus(canvas: CanvasState, flowId: string): boolean {
  return Boolean(canvas.focusedFlows && !canvas.focusedFlows.has(flowId))
}

export interface Trail {
  run: number
  edges: Map<string, number>
  steps: Map<string, number>
  /** Steps that carry a change: the walk lingers there. */
  changed: Set<string>
  animate: boolean
}

export const CanvasContext = React.createContext<CanvasState | null>(null)

export function useCanvas(): CanvasState {
  const value = React.useContext(CanvasContext)
  if (!value) throw new Error("canvas context missing")
  return value
}

/**
 * The ripple, at most 0.6 s from its start: a ring on the change (0–240 ms), the edges
 * leaving it drawn together (120–420 ms), the next steps answering as the lines arrive, and
 * the tags on farther results last (420–600 ms).
 */
export const RING_MS = 240
export const DRAW_FROM = 120
export const DRAW_MS = 300
export const TAG_FROM = 420
export const TAG_MS = 180
/** The camera glide between changes of one flow; the ripple starts at 70 % of it. */
export const GLIDE_MS = 520
export const GLIDE_ARM = Math.round(GLIDE_MS * 0.7)
/** After a cut to a flow (or the first paint), the ripple waits this long. */
export const CUT_ARM = 120
/** Cards and edges dim or come back this fast. */
export const DIM_MS = 160

export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

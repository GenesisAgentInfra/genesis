import * as React from "react"

import type { Strings } from "@/i18n"
import type { LineLook, StepLook } from "./emphasis"

/**
 * What the canvas tells the things drawn on it: the words to use, and for each step and
 * line how loud it is (see `emphasis.ts`). None of them reads where the reader is.
 */
export interface CanvasState {
  t: Strings
  /** A report with changes to step through: the map is about one change at a time. */
  focus: boolean
  /** The change on show, so a card holding several changes shows this one. */
  stopNo?: number
  /** A change outside the flows, or a flow that is gone, whose panel is open. */
  apart?: string
  /** A walk through a flow is on. */
  walking: boolean
  /** The module in focus; every other one steps back. */
  focusedModule?: string
  /** How loud a step is, and how loud a line. */
  step: (
    id: string,
    facts: { changed: boolean; removedFlow: boolean }
  ) => StepLook
  line: (
    id: string,
    facts: { back: boolean; uncertain: boolean; skipped: boolean }
  ) => LineLook
  /** Whether a flow sits outside the module in focus ("__offmap": changes on no flow). */
  away: (flowId: string) => boolean
}

export const CanvasContext = React.createContext<CanvasState | null>(null)

export function useCanvas(): CanvasState {
  const value = React.useContext(CanvasContext)
  if (!value) throw new Error("canvas context missing")
  return value
}

import * as React from "react"

import { stopKey, type Model } from "./model"

/**
 * Which changes the reader has marked as seen. It is kept in the browser under the two
 * revisions compared, so reopening the same comparison picks up where the reader stopped;
 * where the browser keeps nothing (a private window, a blocked store) it lasts for the visit.
 */

function storeKey(model: Model): string {
  const report = model.payload.report
  const base = report?.base_revision ?? report?.base_ref ?? ""
  const head = report?.head_revision ?? report?.head_ref ?? ""
  return `genesis:seen:${base}..${head}`
}

function read(key: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]")
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : []
  } catch {
    return []
  }
}

export function useReviewed(model: Model): {
  /** The stops marked as seen, by their number. */
  reviewed: Set<number>
  /** Mark these stops as seen, or as not seen when every one of them already is. */
  toggle: (nos: number[]) => void
} {
  const key = React.useMemo(() => storeKey(model), [model])
  const [seen, setSeen] = React.useState(() => new Set(read(key)))
  React.useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify([...seen]))
    } catch {
      // Nothing to keep it in: the marks last as long as the page stays open.
    }
  }, [key, seen])
  const toggle = React.useCallback(
    (nos: number[]) =>
      setSeen((before) => {
        const keys = nos
          .map((no) => model.stops[no - 1])
          .filter((stop) => stop !== undefined)
          .map(stopKey)
        const on = !keys.every((item) => before.has(item))
        const after = new Set(before)
        for (const item of keys) {
          if (on) after.add(item)
          else after.delete(item)
        }
        return after
      }),
    [model]
  )
  const reviewed = React.useMemo(
    () =>
      new Set(
        model.stops
          .filter((stop) => seen.has(stopKey(stop)))
          .map((stop) => stop.no)
      ),
    [model, seen]
  )
  return { reviewed, toggle }
}

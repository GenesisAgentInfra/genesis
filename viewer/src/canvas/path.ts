import type { Point } from "./graph"

/**
 * A path through points at right angles, its corners rounded. A corner gives way on a run
 * too short for it, unless `full` keeps every corner at the whole radius.
 */
export function orthogonal(points: Point[], radius = 10, full = false): string {
  // Points on one line with their neighbours add nothing but a kink.
  const kept = points.filter((point, index) => {
    const before = points[index - 1]
    const after = points[index + 1]
    if (!before || !after) return true
    const flat =
      Math.abs(before.y - point.y) < 0.5 && Math.abs(point.y - after.y) < 0.5
    const upright =
      Math.abs(before.x - point.x) < 0.5 && Math.abs(point.x - after.x) < 0.5
    return !flat && !upright
  })
  const parts = [`M${kept[0].x},${kept[0].y}`]
  for (let i = 1; i < kept.length - 1; i++) {
    const [a, b, c] = [kept[i - 1], kept[i], kept[i + 1]]
    const before = Math.hypot(b.x - a.x, b.y - a.y)
    const after = Math.hypot(c.x - b.x, c.y - b.y)
    const r = full ? radius : Math.min(radius, before / 2, after / 2)
    if (!r) {
      parts.push(`L${b.x},${b.y}`)
      continue
    }
    const inX = b.x - ((b.x - a.x) / before) * r
    const inY = b.y - ((b.y - a.y) / before) * r
    const outX = b.x + ((c.x - b.x) / after) * r
    const outY = b.y + ((c.y - b.y) / after) * r
    parts.push(`L${inX},${inY}`, `Q${b.x},${b.y} ${outX},${outY}`)
  }
  const last = kept[kept.length - 1]
  parts.push(`L${last.x},${last.y}`)
  return parts.join(" ")
}

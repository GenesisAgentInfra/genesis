export type TextSize = "body-m" | "body-s" | "body-xl"

const measurements = new Map<string, number>()
let probe: HTMLDivElement | undefined
const type = {
  "body-m": { em: 14, line: 21, classes: "text-body-m font-medium" },
  "body-s": { em: 12, line: 17, classes: "text-body-s" },
  "body-xl": {
    em: 20,
    line: 23,
    classes: "font-display text-body-xl font-medium",
  },
}

/** Native canvas-scale text geometry, using the same fonts and wrapping as the cards. */
function measure(text: string, size: TextSize, width?: number) {
  if (!text) return 0
  const key = JSON.stringify([width, size, text])
  const saved = measurements.get(key)
  if (saved !== undefined) return saved
  const face = type[size]
  if (typeof document === "undefined") {
    const units = Array.from(text).reduce(
      (sum, char) => sum + (char.codePointAt(0)! < 256 ? 0.61 : 1),
      0
    )
    const natural = units * face.em
    return width === undefined
      ? Math.ceil(natural)
      : Math.max(1, Math.ceil(natural / width)) * face.line
  }
  if (!probe) {
    probe = document.createElement("div")
    probe.setAttribute("aria-hidden", "true")
    probe.style.cssText =
      "position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;contain:layout style paint;overflow-wrap:anywhere;"
    document.body.append(probe)
  }
  probe.className = face.classes
  probe.style.width = width === undefined ? "max-content" : `${width}px`
  probe.textContent = text
  const value =
    width === undefined
      ? Math.ceil(probe.getBoundingClientRect().width)
      : probe.offsetHeight
  probe.textContent = ""
  measurements.set(key, value)
  return value
}

export const wrappedHeight = (
  text: string,
  width: number,
  size: TextSize = "body-m"
) => measure(text, size, Math.max(width, 1))

export const singleLineWidth = (text: string, size: TextSize) =>
  measure(text, size)

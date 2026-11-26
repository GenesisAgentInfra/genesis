type TextSize = "body-m" | "body-s"

const heights = new Map<string, number>()
let probe: HTMLDivElement | undefined

/**
 * Height at canvas scale 1, before any interaction or camera transform. Let the browser
 * wrap actual words, CJK characters and unbroken identifiers with the card's typography.
 * Only the first encounter of a string at a given width requires a layout read.
 */
export function wrappedHeight(
  text: string,
  width: number,
  size: TextSize = "body-m"
) {
  if (!text) return 0
  const key = JSON.stringify([width, size, text])
  const saved = heights.get(key)
  if (saved !== undefined) return saved
  if (typeof document === "undefined") {
    // Non-browser graph consumers only need a deterministic box estimate.
    const em = size === "body-m" ? 14 : 12
    const units = Array.from(text).reduce(
      (sum, char) => sum + (char.codePointAt(0)! < 256 ? 0.61 : 1),
      0
    )
    return (
      Math.max(1, Math.ceil((units * em) / width)) *
      (size === "body-m" ? 21 : 17)
    )
  }
  if (!probe) {
    probe = document.createElement("div")
    probe.setAttribute("aria-hidden", "true")
    probe.style.cssText =
      "position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;contain:layout style paint;overflow-wrap:anywhere;"
    document.body.append(probe)
  }
  probe.className =
    size === "body-m" ? "text-body-m font-medium" : "text-body-s"
  probe.style.width = `${width}px`
  probe.textContent = text
  const height = probe.offsetHeight
  probe.textContent = ""
  heights.set(key, height)
  return height
}

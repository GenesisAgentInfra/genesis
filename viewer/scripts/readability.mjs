// Wait for the shipped page to mount and finish placing its nodes before measuring it.
// A row-only map still has React Flow nodes; a genuinely empty map renders a message.
export async function waitForMap(page) {
  await page
    .locator("#root header")
    .waitFor({ state: "visible", timeout: 10_000 })
  await page.waitForFunction(
    () => {
      if (document.fonts.status !== "loaded") return false
      const graph = document.querySelector("#root .react-flow")
      if (!graph)
        return /No flow to show\.|没有可以显示的流程。/.test(
          document.querySelector("#root").innerText
        )
      return (
        Number(getComputedStyle(graph).opacity) === 1 &&
        !!graph.querySelector(".react-flow__node")
      )
    },
    undefined,
    { timeout: 10_000 }
  )
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve))
      )
  )
}

// Runs inside the browser via page.evaluate. Positions include the canvas transform.
// Offscreen steps are valid on large diagrams and can be reached by panning.
export function inspectCards() {
  const problems = new Set()
  const viewport = document.querySelector(".react-flow__viewport")
  // Both callers inspect automatic camera positions, before any manual zoom.
  if (viewport) {
    const scale = new DOMMatrix(getComputedStyle(viewport).transform).a
    if (!(scale > 0 && scale <= 1.001))
      problems.add(`Automatic zoom is ${scale}×`)
  }
  const name = (el) => el.closest(".react-flow__node")?.dataset.id || el.tagName
  const cards = []
  for (const node of document.querySelectorAll(
    ".react-flow__node-step, .react-flow__node-row, .react-flow__node-offmap"
  )) {
    const card = node.querySelector("[data-slot=card]")
    if (
      card?.checkVisibility({ visibilityProperty: true, opacityProperty: true })
    ) {
      cards.push(card)
    } else {
      problems.add("Missing visible card in " + name(node))
    }
  }
  const box = (el) => el.getBoundingClientRect()
  const tolerance = 2
  const outside = (r, b) =>
    r.left < b.left - tolerance ||
    r.right > b.right + tolerance ||
    r.top < b.top - tolerance ||
    r.bottom > b.bottom + tolerance
  const overlaps = (a, b) =>
    Math.min(a.right, b.right) - Math.max(a.left, b.left) > tolerance &&
    Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > tolerance

  function inspectText(container, boundary, header = false) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
    const bounds = box(boundary)
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      const field = text.parentElement
      const content = text.textContent.trim()
      if (
        !content ||
        field.closest("svg, [aria-hidden=true]") ||
        !field.getClientRects().length
      )
        continue
      // Floating change counters and flags deliberately straddle the card border.
      let owner = field
      while (
        owner !== container &&
        getComputedStyle(owner).position !== "absolute"
      )
        owner = owner.parentElement
      if (owner !== container) continue
      const range = document.createRange()
      range.selectNodeContents(text)
      const fragments = [...range.getClientRects()].filter(
        (r) => r.width && r.height
      )
      const ident = name(field) + " ‘" + content.slice(0, 75) + "’"
      if (
        (field.clientHeight && field.scrollHeight > field.clientHeight + 1) ||
        (field.clientWidth && field.scrollWidth > field.clientWidth + 1) ||
        fragments.some((r) => outside(r, bounds))
      ) {
        problems.add("Clipped text in " + ident)
      }
      if (
        header &&
        [...boundary.querySelectorAll("button")].some((button) =>
          fragments.some((r) => overlaps(r, box(button)))
        )
      ) {
        problems.add("Heading overlaps a control in " + ident)
      }
    }
  }

  const placed = cards
    .map((el) => ({ el, rect: box(el) }))
    .sort((a, b) => a.rect.left - b.rect.left)
  for (let i = 0; i < placed.length; i++) {
    const { el, rect } = placed[i]
    inspectText(el, el)
    for (
      let j = i + 1;
      j < placed.length && placed[j].rect.left < rect.right;
      j++
    ) {
      if (overlaps(rect, placed[j].rect))
        problems.add(
          "Overlapping cards: " + name(el) + " and " + name(placed[j].el)
        )
    }
  }
  for (const heading of document.querySelectorAll(
    ".react-flow__node-module h2, .react-flow__node-flow [data-slot=card-title]"
  )) {
    inspectText(
      heading,
      heading.closest("[data-slot=card-header]") || heading.parentElement,
      true
    )
  }
  return { cards: cards.length, problems: [...problems] }
}

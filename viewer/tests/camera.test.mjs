import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"

// What each shot puts in frame, checked where it matters: on the reader's screen.

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
after(() => server.close())
const { MAX_ZOOM, PANEL_W, readingArea, readingSpan, viewOf } =
  await server.ssrLoadModule("/src/canvas/camera.ts")
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { atlasDrawer } = await server.ssrLoadModule("/src/atlas/build.ts")
const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")

const model = buildModel(
  JSON.parse(
    await readFile(new URL("../dev/sample-refund.json", import.meta.url))
  )
)
const desk = { width: 1440, height: 900, headline: 36, narrow: false }
const atlasOf = atlasDrawer(model, STRINGS.zh, readingSpan(desk.width))
const REFUNDS = "module::dom_refund"
const sceneOf = (more = {}) => ({
  atlas: atlasOf(more.focused),
  panel: false,
  screen: desk,
  ...more,
})

const near = (a, b) => Math.abs(a - b) < 0.5
/** Where a node of the scene ends up on the screen under a viewport. */
function onScreen(scene, view, id) {
  const node = scene.atlas.nodes.find((item) => item.id === id)
  const width = node.type === "step" ? node.data.width : (node.width ?? 0)
  const height = node.type === "step" ? node.data.slot : (node.height ?? 0)
  const left = node.position.x * view.zoom + view.x
  const top = node.position.y * view.zoom + view.y
  return {
    left,
    top,
    right: left + width * view.zoom,
    bottom: top + height * view.zoom,
  }
}
const edgesOf = (scene, view) => {
  const boxes = scene.atlas.nodes.map((node) => onScreen(scene, view, node.id))
  return {
    left: Math.min(...boxes.map((box) => box.left)),
    top: Math.min(...boxes.map((box) => box.top)),
    right: Math.max(...boxes.map((box) => box.right)),
  }
}

test("the reading area is clear of the headline, the controls and the panel", () => {
  assert.deepEqual(readingArea(desk, false), {
    x: 16,
    y: 76,
    width: 1364,
    height: 800,
  })
  assert.equal(readingArea(desk, true).width, 1440 - 16 - PANEL_W - 40)
  // A taller headline pushes the map down, and only that.
  const tall = readingArea({ ...desk, headline: 72 }, false)
  assert.deepEqual([tall.y, tall.height, tall.width], [112, 764, 1364])
})

test("a map that reads whole starts right under the headline, filling the screen across", async () => {
  const expense = buildModel(
    JSON.parse(
      await readFile(new URL("../dev/sample-expense.json", import.meta.url))
    )
  )
  const scene = {
    atlas: atlasDrawer(expense, STRINGS.zh, readingSpan(desk.width))(),
    panel: false,
    screen: desk,
  }
  const view = viewOf({ of: "place" }, scene)
  const area = readingArea(desk, false)
  const map = edgesOf(scene, view)
  assert.ok(near(map.top, area.y))
  assert.ok(near(map.left, area.x))
  assert.ok(near(map.right, area.x + area.width))
  assert.ok(view.zoom > 0.66 && view.zoom <= MAX_ZOOM)
})

test("a flow drawn wider than the screen keeps the map at reading size", () => {
  // The refund flow, cut down to its changes, is still wider than the desk shows at the
  // least size that reads: the map starts under the headline and runs on to the right.
  const scene = sceneOf()
  const view = viewOf({ of: "place" }, scene)
  const area = readingArea(desk, false)
  const map = edgesOf(scene, view)
  assert.equal(view.zoom, 0.66)
  assert.ok(near(map.top, area.y))
  assert.ok(near(map.left, area.x))
  assert.ok(map.right > area.x + area.width)
})

test("a map too wide to read whole keeps its size and runs on past the right edge", () => {
  const slim = { ...desk, width: 720 }
  const scene = sceneOf({ screen: slim })
  const view = viewOf({ of: "place" }, scene)
  const area = readingArea(slim, false)
  const map = edgesOf(scene, view)
  assert.equal(view.zoom, 0.66)
  assert.ok(near(map.left, area.x))
  assert.ok(map.right > area.x + area.width)
})

test("what the panel is about ends up in view beside it, wherever it sits on the map", () => {
  for (const screen of [
    desk,
    { ...desk, width: 1000 },
    { ...desk, height: 520 },
  ]) {
    const area = readingArea(screen, true)
    for (const focused of [undefined, REFUNDS]) {
      const base = sceneOf({ focused, screen, panel: true })
      const subjects = base.atlas.nodes.filter(
        (node) => node.type === "step" || node.type === "offmap"
      )
      for (const node of subjects) {
        const scene = { ...base, subject: node.id }
        const view = viewOf({ of: "place" }, scene)
        const box = onScreen(scene, view, node.id)
        const where = `${node.id} on ${screen.width}x${screen.height}`
        assert.ok(box.left >= area.x - 0.5, `${where}: off to the left`)
        assert.ok(
          box.right <= area.x + area.width + 0.5,
          `${where}: under the panel`
        )
        assert.ok(box.top >= area.y - 0.5, `${where}: under the headline`)
        assert.ok(
          box.bottom <= area.y + area.height + 0.5 ||
            box.bottom - box.top > area.height,
          `${where}: below the screen`
        )
      }
    }
  }
})

test("an open module is framed from its own top", () => {
  const scene = sceneOf({ focused: REFUNDS })
  const view = viewOf({ of: "place" }, scene)
  const area = readingArea(desk, false)
  const module = onScreen(scene, view, REFUNDS)
  assert.ok(near(module.top, area.y))
  assert.ok(module.left >= area.x - 0.5)
})

test("a flow at the top of its module brings the module's name; one further down starts at its own card", () => {
  const scene = sceneOf({ focused: REFUNDS })
  const area = readingArea(desk, false)
  const cards = scene.atlas.nodes
    .filter(
      (node) =>
        node.type === "flow" &&
        scene.atlas.home.get(node.data.flowId) === REFUNDS
    )
    .sort((a, b) => a.position.y - b.position.y)
  assert.ok(cards.length >= 2)
  const first = viewOf({ of: "flow", flowId: cards[0].data.flowId }, scene)
  assert.ok(near(onScreen(scene, first, REFUNDS).top, area.y))
  const second = viewOf({ of: "flow", flowId: cards[1].data.flowId }, scene)
  assert.ok(near(onScreen(scene, second, cards[1].id).top, area.y))
  assert.ok(onScreen(scene, second, REFUNDS).top < area.y)
})

test("steps asked for by name are whole and centred; a walk's step sits in the middle, close up", () => {
  const scene = sceneOf({ focused: REFUNDS })
  const area = readingArea(desk, false)
  const steps = scene.atlas.flows.get("flow_progress").nodes
  const view = viewOf({ of: "steps", ids: steps.map((node) => node.id) }, scene)
  const boxes = steps.map((node) => onScreen(scene, view, node.id))
  const left = Math.min(...boxes.map((box) => box.left))
  const right = Math.max(...boxes.map((box) => box.right))
  const top = Math.min(...boxes.map((box) => box.top))
  const bottom = Math.max(...boxes.map((box) => box.bottom))
  assert.ok(left >= area.x - 0.5 && right <= area.x + area.width + 0.5)
  assert.ok(top >= area.y - 0.5 && bottom <= area.y + area.height + 0.5)
  assert.ok(near((left + right) / 2, area.x + area.width / 2))
  assert.ok(near((top + bottom) / 2, area.y + area.height / 2))

  const one = viewOf({ of: "step", id: steps[0].id }, scene)
  const box = onScreen(scene, one, steps[0].id)
  assert.equal(one.zoom, 0.85)
  assert.ok(near((box.left + box.right) / 2, area.x + area.width / 2))
  assert.ok(near((box.top + box.bottom) / 2, area.y + area.height / 2))
})

test("there is no shot of what is not on the map", () => {
  const scene = sceneOf()
  assert.equal(viewOf({ of: "step", id: "nowhere" }, scene), undefined)
  assert.equal(viewOf({ of: "steps", ids: ["nowhere"] }, scene), undefined)
  assert.equal(viewOf({ of: "flow", flowId: "nowhere" }, scene), undefined)
})

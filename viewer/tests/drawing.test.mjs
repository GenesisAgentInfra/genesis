import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"

// What the layout hands the views is the finished drawing: every step's box and every
// line's corners, in canvas coordinates. These tests read it the way a view does.

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
after(() => server.close())
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { buildAtlas } = await server.ssrLoadModule("/src/atlas/build.ts")
const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")

const PORT = 3.5
const samples = {}
for (const name of ["expense", "refund", "map"])
  samples[name] = JSON.parse(
    await readFile(new URL(`../dev/sample-${name}.json`, import.meta.url))
  )

/** Every drawing a sample gives: the overview, and each module opened in turn. */
function drawings(name) {
  const model = buildModel(samples[name])
  const overview = buildAtlas(model, STRINGS.zh)
  const modules = overview.nodes.filter((node) => node.type === "module")
  return [
    [`${name} overview`, overview],
    ...modules.map((node) => [
      `${name} with ${node.id} open`,
      buildAtlas(model, STRINGS.zh, node.id),
    ]),
  ]
}
const all = Object.keys(samples).flatMap(drawings)

const boxOf = (node) => ({
  x: node.position.x,
  y: node.position.y,
  w: node.data.width,
  h: node.data.slot,
})
const stepsOf = (atlas) => atlas.nodes.filter((node) => node.type === "step")
const flowOf = (id) => id.slice(0, id.indexOf("::"))
const near = (a, b) => Math.abs(a - b) < 0.01

test("every line is drawn: it has corners and runs at right angles", () => {
  for (const [name, atlas] of all)
    for (const edge of atlas.edges) {
      const points = edge.data.points
      assert.ok(points?.length >= 2, `${name}: ${edge.id} has no corners`)
      for (let i = 1; i < points.length; i++)
        assert.ok(
          near(points[i - 1].x, points[i].x) ||
            near(points[i - 1].y, points[i].y),
          `${name}: ${edge.id} runs askew at corner ${i}`
        )
    }
})

test("a line leaves the port on its step's right and ends at a port of the step it reaches", () => {
  for (const [name, atlas] of all) {
    const byId = new Map(stepsOf(atlas).map((node) => [node.id, boxOf(node)]))
    for (const edge of atlas.edges) {
      const source = byId.get(edge.source)
      const target = byId.get(edge.target)
      const first = edge.data.points[0]
      const last = edge.data.points.at(-1)
      assert.ok(
        near(first.x, source.x + source.w + PORT) &&
          near(first.y, source.y + source.h / 2),
        `${name}: ${edge.id} does not leave its port`
      )
      const middle = target.x + target.w / 2
      const ports = [
        [target.x - PORT, target.y + target.h / 2],
        [middle, target.y - PORT],
        [middle, target.y + target.h + PORT],
      ]
      assert.ok(
        ports.some(([x, y]) => near(last.x, x) && near(last.y, y)),
        `${name}: ${edge.id} does not end at a port`
      )
    }
  }
})

test("no two steps of a flow stand on each other", () => {
  for (const [name, atlas] of all) {
    const steps = stepsOf(atlas)
    for (const a of steps)
      for (const b of steps) {
        if (a.id >= b.id || flowOf(a.id) !== flowOf(b.id)) continue
        const [p, q] = [boxOf(a), boxOf(b)]
        const apart =
          p.x + p.w <= q.x ||
          q.x + q.w <= p.x ||
          p.y + p.h <= q.y ||
          q.y + q.h <= p.y
        assert.ok(apart, `${name}: ${a.id} and ${b.id} overlap`)
      }
  }
})

test("no line runs behind a step", () => {
  for (const [name, atlas] of all) {
    const steps = stepsOf(atlas)
    for (const edge of atlas.edges) {
      const points = edge.data.points
      for (let i = 1; i < points.length; i++) {
        const [a, b] = [points[i - 1], points[i]]
        const [left, right] = [Math.min(a.x, b.x), Math.max(a.x, b.x)]
        const [top, bottom] = [Math.min(a.y, b.y), Math.max(a.y, b.y)]
        for (const step of steps) {
          if (flowOf(step.id) !== flowOf(edge.id)) continue
          const box = boxOf(step)
          const crosses =
            left < box.x + box.w &&
            right > box.x &&
            top < box.y + box.h &&
            bottom > box.y
          assert.ok(!crosses, `${name}: ${edge.id} runs behind ${step.id}`)
        }
      }
    }
  }
})

test("a label sits level with a run of its own line, on it or hanging just before it", () => {
  // A long label on a branch that drops a row hangs back over the empty cell before its
  // step, so it may start left of the run it names; it never leaves the run's height.
  const HANG = 160
  for (const [name, atlas] of all)
    for (const edge of atlas.edges) {
      const at = edge.data.labelAt
      if (!edge.data.label) continue
      assert.ok(at, `${name}: ${edge.id} has a label and no place for it`)
      const points = edge.data.points
      const level = points.some((b, i) => {
        if (!i) return false
        const a = points[i - 1]
        return (
          near(a.y, b.y) &&
          near(at.y, a.y) &&
          at.x >= Math.min(a.x, b.x) - HANG &&
          at.x <= Math.max(a.x, b.x) + 0.01
        )
      })
      assert.ok(level, `${name}: the label of ${edge.id} is off its line`)
    }
})

test("everything drawn of a flow stays on its card", () => {
  for (const [name, atlas] of all) {
    const cards = new Map(
      atlas.nodes
        .filter((node) => node.type === "flow")
        .map((node) => [node.data.flowId, node])
    )
    const inside = (flowId, x, y, what) => {
      const card = cards.get(flowId)
      assert.ok(card, `${name}: ${flowId} has no card`)
      assert.ok(
        x >= card.position.x &&
          x <= card.position.x + card.width &&
          y >= card.position.y &&
          y <= card.position.y + card.height,
        `${name}: ${what} is off the card of ${flowId}`
      )
    }
    for (const step of stepsOf(atlas)) {
      const box = boxOf(step)
      inside(flowOf(step.id), box.x, box.y, step.id)
      inside(flowOf(step.id), box.x + box.w, box.y + box.h, step.id)
    }
    for (const edge of atlas.edges)
      for (const point of edge.data.points)
        inside(flowOf(edge.id), point.x, point.y, edge.id)
  }
})

test("placing a flow leaves its own drawing where it was", () => {
  // The atlas sets copies down on the canvas; building it twice gives the same canvas.
  const model = buildModel(samples.refund)
  const first = buildAtlas(model, STRINGS.zh)
  const second = buildAtlas(model, STRINGS.zh)
  assert.deepEqual(
    first.nodes.map((node) => [node.id, node.position]),
    second.nodes.map((node) => [node.id, node.position])
  )
  for (const flow of first.flows.values())
    for (const node of flow.nodes) {
      const onCanvas = first.nodes.find((item) => item.id === node.id)
      assert.notEqual(onCanvas, node)
    }
})

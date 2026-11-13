import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"

// How loud a step and a line are, asked the way the views ask it: one call per step or
// line, with where the reader is.

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
after(() => server.close())
const { DARK, lineLook, litBy, stepLook, walkTimes } =
  await server.ssrLoadModule("/src/canvas/emphasis.ts")
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { buildAtlas } = await server.ssrLoadModule("/src/atlas/build.ts")
const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")

const plain = { changed: false, removedFlow: false }
const solid = { back: false, uncertain: false, skipped: false }
const resting = { run: 0, plays: false, delay: 0 }
/** A change picked on f::b: reached over f::a, leading to f::c and, further on, f::d. */
const lit = {
  current: "f::b",
  next: new Set(["f::c"]),
  far: new Set(["f::d"]),
  routeSteps: new Set(["f::a"]),
  routeLines: new Set(["f::a>b"]),
  outLines: new Set(["f::b>c", "f::b>x"]),
  loopLines: new Set(["f::c>b"]),
  dotLines: new Set(["f::b>c"]),
}
const picked = (ripple = resting, more = {}) => ({
  focus: true,
  lit,
  ripple,
  ...more,
})

test("with nothing picked, nothing steps back", () => {
  const spot = { focus: true, lit: DARK, ripple: resting }
  assert.equal(stepLook(spot, "f::a", plain).quiet, false)
  assert.equal(lineLook(spot, "f::a>b", solid).quiet, false)
  assert.equal(lineLook(spot, "f::a>b", solid).dark, false)
})

test("a picked change quiets unchanged steps off its way in, and nothing else", () => {
  const spot = picked()
  assert.equal(stepLook(spot, "f::z", plain).quiet, true)
  // The way in, the change itself, what it leads to, and any other changed step stay.
  for (const id of ["f::a", "f::b", "f::c"])
    assert.equal(stepLook(spot, id, plain).quiet, false, id)
  assert.equal(stepLook(spot, "f::z", { ...plain, changed: true }).quiet, false)
  // A flow that is gone is shown whole.
  assert.equal(
    stepLook(spot, "f::z", { ...plain, removedFlow: true }).quiet,
    false
  )
  // An unchanged step whose panel is open stands out too.
  const withPanel = picked(resting, { selected: "f::z" })
  assert.equal(stepLook(withPanel, "f::z", plain).selected, true)
  assert.equal(stepLook(withPanel, "f::z", plain).quiet, false)
})

test("the ripple: a ring on the change, then the next steps, then the tags", () => {
  const spot = picked({ run: 3, plays: true, delay: 364 })
  assert.deepEqual(stepLook(spot, "f::b", plain).ring, {
    key: "ring-3",
    delay: 364,
    duration: 240,
  })
  const next = stepLook(spot, "f::c", plain)
  assert.equal(next.reached, true)
  assert.equal(next.delay, 364 + 420)
  assert.equal(next.ring, undefined)
  assert.deepEqual(stepLook(spot, "f::d", plain).tag, {
    key: "tag-3",
    enters: 364 + 420,
  })
  // Once it has played, the end state shows at once.
  const settled = picked({ run: 3, plays: false, delay: 364 })
  assert.equal(stepLook(settled, "f::b", plain).ring, undefined)
  assert.equal(stepLook(settled, "f::c", plain).delay, 0)
  assert.deepEqual(stepLook(settled, "f::d", plain).tag, {
    key: "tag-3",
    enters: undefined,
  })
})

test("lines: the way in is dark and still, the lines out draw themselves", () => {
  const spot = picked({ run: 3, plays: true, delay: 364 })
  const wayIn = lineLook(spot, "f::a>b", solid)
  assert.deepEqual(
    [wayIn.dark, wayIn.quiet, wayIn.entering],
    [true, false, false]
  )
  const out = lineLook(spot, "f::b>c", solid)
  assert.deepEqual(
    [out.dark, out.draws, out.travels, out.start, out.key],
    [true, true, true, 364 + 120, "out-3"]
  )
  // A line out that is not among the shortest draws without the dot.
  assert.equal(lineLook(spot, "f::b>x", solid).travels, false)
  // A dashed line cannot draw itself: it fades in over the same stretch.
  const unsure = lineLook(spot, "f::b>x", { ...solid, uncertain: true })
  assert.deepEqual(
    [unsure.dashed, unsure.entering, unsure.draws],
    [true, true, false]
  )
  // A loop on the change stays in view; any other line steps back.
  assert.equal(lineLook(spot, "f::c>b", { ...solid, back: true }).quiet, false)
  assert.equal(lineLook(spot, "f::y>z", solid).quiet, true)
})

test("a step back is dashed until something lights it", () => {
  const back = { ...solid, back: true }
  assert.equal(lineLook(picked(), "f::c>b", back).dashed, true)
  assert.equal(lineLook(picked(), "f::a>b", back).dashed, false)
})

test("a walk quiets everything it does not pass, and replaces the ripple", () => {
  const trail = walkTimes(
    7,
    ["f::a", "f::b", "f::c"],
    ["f::a>b", "f::b>c"],
    new Set(["f::b"]),
    true
  )
  const spot = picked({ run: 3, plays: true, delay: 364 }, { trail })
  assert.equal(stepLook(spot, "f::d", plain).quiet, true)
  assert.equal(lineLook(spot, "f::b>x", solid).quiet, true)
  // The ripple's own lines do not enter while a walk is on.
  assert.equal(lineLook(spot, "f::b>x", solid).entering, false)
  const reached = stepLook(spot, "f::b", { ...plain, changed: true })
  assert.deepEqual(reached.ring, {
    key: "walk-7",
    delay: trail.steps.get("f::b"),
    duration: 480,
  })
  assert.equal(stepLook(spot, "f::c", plain).ring.duration, 240)
  const line = lineLook(spot, "f::b>c", solid)
  assert.deepEqual(
    [line.draws, line.travels, line.start, line.key],
    [true, true, trail.lines.get("f::b>c"), "walk-7"]
  )
})

test("the walk's timetable: a lead, a pause at each step, longer at a change", () => {
  const trail = walkTimes(
    1,
    ["a", "b", "c"],
    ["a>b", "b>c"],
    new Set(["b"]),
    true
  )
  assert.deepEqual(
    [...trail.steps],
    [
      ["a", 560],
      ["b", 560 + 140 + 300],
      ["c", 1000 + 140 + 560 + 300],
    ]
  )
  assert.deepEqual(
    [...trail.lines],
    [
      ["a>b", 700],
      ["b>c", 1700],
    ]
  )
  assert.deepEqual([...trail.changed], ["b"])
  // Without motion the whole walk is there at once.
  const still = walkTimes(1, ["a", "b"], ["a>b"], new Set(), false)
  assert.deepEqual(
    [...still.steps.values(), ...still.lines.values()],
    [0, 0, 0]
  )
})

test("a step outside the module in focus is away", () => {
  const spot = picked(resting, { focusedFlows: new Set(["g"]) })
  assert.equal(stepLook(spot, "f::a", plain).away, true)
  assert.equal(lineLook(spot, "f::a>b", solid).away, true)
  assert.equal(stepLook(spot, "g::a", plain).away, false)
})

test("what a picked change lights is asked of its drawn flow", async () => {
  const sample = JSON.parse(
    await readFile(new URL("../dev/sample-refund.json", import.meta.url))
  )
  const model = buildModel(sample)
  const atlas = buildAtlas(model, STRINGS.zh)
  const stop = model.stops.find((item) => item.flowId && item.nodeId)
  const placed = atlas.flows.get(stop.flowId)
  const node = `${stop.flowId}::${stop.nodeId}`
  const found = litBy(placed, node)
  assert.equal(found.current, node)
  // Everything it names is drawn on the canvas, under canvas names.
  const drawn = new Set(placed.nodes.map((item) => item.id))
  const lines = new Set(placed.edges.map((item) => item.id))
  for (const id of found.routeSteps) assert.ok(drawn.has(id), id)
  for (const id of [...found.routeLines, ...found.outLines, ...found.dotLines])
    assert.ok(lines.has(id), id)
  assert.equal(found.routeSteps.has(node), false)
  // A flow the change is not drawn on lights nothing.
  assert.equal(litBy(undefined, node), DARK)
})

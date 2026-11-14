import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"

// Where each thing the reader does takes them, asked the way the page asks it: one place,
// one action, the next place. The camera's orders are read off the place, so no screen
// and no canvas are needed.

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
after(() => server.close())
const { START, act, beats, panelOf, pickedOf } =
  await server.ssrLoadModule("/src/reader.ts")
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { atlasDrawer } = await server.ssrLoadModule("/src/atlas/build.ts")
const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")

const worldOf = async (name) => {
  const model = buildModel(
    JSON.parse(
      await readFile(new URL(`../dev/sample-${name}.json`, import.meta.url))
    )
  )
  return { model, atlasOf: atlasDrawer(model, STRINGS.zh), motion: true }
}
// A report with six changes: three on steps of the refund flow, a step that is gone,
// one on no flow (5) and a flow that is gone (6).
const refund = await worldOf("refund")
// A map with nothing changed, where flows are walked.
const tour = await worldOf("map")
const still = (world) => ({ ...world, motion: false })

/** One thing after another, from the whole map. */
const doing = (world, ...actions) =>
  actions.reduce((place, action) => act(place, action, world), START)
const nodes = (world, place) => world.atlasOf(place.focused).nodes
const cardOf = (world, place, flowId) =>
  nodes(world, place).find(
    (node) => node.type === "flow" && node.data.flowId === flowId
  ).id
const REFUNDS = "module::dom_refund"
const PAYMENTS = "module::dom_payments"
const PAY = "flow_refund::step_pay"

test("a change from the list opens its details on its step, and the step rings", () => {
  const place = doing(refund, { do: "change", no: 1 })
  assert.deepEqual(place.selected, { type: "step", node: PAY })
  assert.deepEqual(place.current, { node: PAY, no: 1 })
  assert.deepEqual(place.ripple, { run: 1, settled: false })
  assert.deepEqual(place.camera, { no: 1, shot: { of: "place" }, ms: 520 })
  assert.equal(pickedOf(place, refund.model), 1)
  assert.deepEqual(panelOf(place.selected, refund.atlasOf()), {
    open: true,
    node: PAY,
  })
  // For a reader who asked for less motion nothing glides and nothing waits.
  const calm = act(START, { do: "change", no: 1 }, still(refund))
  assert.equal(calm.camera.ms, 0)
  // A number the report does not have changes nothing.
  assert.equal(act(START, { do: "change", no: 99 }, refund), START)
})

test("a change on no flow and a flow that is gone open their own details, with no step to ring", () => {
  const off = doing(refund, { do: "change", no: 1 }, { do: "change", no: 5 })
  assert.deepEqual(off.selected, { type: "offMap", no: 5 })
  assert.equal(off.current, undefined)
  assert.equal(pickedOf(off, refund.model), 5)
  assert.equal(panelOf(off.selected, refund.atlasOf()).node, "offmap::5")
  const gone = doing(refund, { do: "change", no: 6 })
  assert.deepEqual(gone.selected, {
    type: "removedFlow",
    flowId: "flow_sms_receipt",
  })
  assert.equal(pickedOf(gone, refund.model), 6)
})

test("the arrows go round the changes and wrap at either end", () => {
  const picked = (...actions) =>
    pickedOf(doing(refund, ...actions), refund.model)
  const on = { do: "step", by: 1 }
  const back = { do: "step", by: -1 }
  assert.equal(picked(on), 1)
  assert.equal(picked(back), 6)
  assert.equal(picked(on, on), 2)
  assert.equal(picked(back, on), 1)
  assert.equal(picked(on, back), 6)
  // With nothing changed there is nowhere to go.
  assert.equal(act(START, on, tour), START)
})

test("Esc takes one step back: the walk, the panel, the picked change, the open module", () => {
  let place = doing(
    refund,
    { do: "node", id: REFUNDS },
    { do: "change", no: 1 }
  )
  assert.equal(place.focused, REFUNDS)
  const steps = []
  for (let i = 0; i < 4; i++) {
    const before = place
    place = act(place, { do: "escape" }, refund)
    steps.push({
      panel: Boolean(place.selected),
      picked: Boolean(place.current),
      module: Boolean(place.focused),
      // The camera moves when the panel goes and when the module closes, not in between.
      camera: place.camera.no - before.camera.no,
    })
  }
  assert.deepEqual(steps, [
    { panel: false, picked: true, module: true, camera: 1 },
    { panel: false, picked: false, module: true, camera: 0 },
    { panel: false, picked: false, module: false, camera: 1 },
    { panel: false, picked: false, module: false, camera: 0 },
  ])
  assert.equal(place.ripple.settled, true)
  // A walk in progress is what Esc ends first; the panel stays up.
  const walking = doing(
    tour,
    { do: "node", id: nodes(tour, START).find((n) => n.type === "step").id },
    { do: "walk", flowId: "flow_ba6d4948fa62" }
  )
  assert.ok(walking.walk && walking.selected)
  const stopped = act(walking, { do: "escape" }, tour)
  assert.equal(stopped.walk, undefined)
  assert.ok(stopped.selected)
})

test("a change outside the open module is shown on the whole map, one inside it in place", () => {
  const outside = doing(
    refund,
    { do: "node", id: PAYMENTS },
    { do: "change", no: 1 }
  )
  assert.equal(outside.focused, undefined)
  assert.deepEqual(outside.current, { node: PAY, no: 1 })
  const inside = doing(
    refund,
    { do: "node", id: REFUNDS },
    { do: "change", no: 1 }
  )
  assert.equal(inside.focused, REFUNDS)
  assert.deepEqual(inside.current, { node: PAY, no: 1 })
  // The same holds for a click on a changed step of another module.
  const clicked = doing(
    refund,
    { do: "node", id: PAYMENTS },
    { do: "node", id: PAY }
  )
  assert.equal(clicked.focused, undefined)
  assert.deepEqual(clicked.selected, { type: "step", node: PAY })
})

test("a click on a module opens it; on one of its flows, opens it on that flow", () => {
  const opened = doing(refund, { do: "node", id: PAYMENTS })
  assert.equal(opened.focused, PAYMENTS)
  assert.deepEqual(opened.camera.shot, { of: "place" })
  // Clicking it again changes nothing.
  assert.equal(act(opened, { do: "node", id: PAYMENTS }, refund), opened)

  const card = cardOf(refund, START, "flow_callback")
  const onFlow = doing(refund, { do: "node", id: card })
  assert.equal(onFlow.focused, PAYMENTS)
  assert.deepEqual(onFlow.camera.shot, { of: "flow", flowId: "flow_callback" })
  // With the panel up, what it is about stays the subject of the shot.
  const beside = doing(
    refund,
    { do: "change", no: 1 },
    { do: "node", id: card }
  )
  assert.equal(beside.focused, PAYMENTS)
  assert.deepEqual(beside.camera.shot, { of: "place" })
  // Once open, the flow's name brings its steps into frame.
  const again = act(
    onFlow,
    { do: "node", id: cardOf(refund, onFlow, "flow_callback") },
    refund
  )
  assert.equal(again.camera.shot.of, "steps")
  assert.deepEqual(
    again.camera.shot.ids,
    refund
      .atlasOf(PAYMENTS)
      .flows.get("flow_callback")
      .nodes.map((node) => node.id)
  )
})

test("a click on a step opens its details; only a changed step is picked", () => {
  const changed = doing(refund, { do: "node", id: PAY })
  assert.deepEqual(changed.current, { node: PAY, no: 1 })
  const plain = nodes(refund, START).find(
    (node) =>
      node.type === "step" &&
      !node.data.coupons.length &&
      !node.data.stub &&
      node.id.startsWith("flow_callback")
  )
  const other = act(changed, { do: "node", id: plain.id }, refund)
  assert.deepEqual(other.selected, { type: "step", node: plain.id })
  // The change picked before stays the one on show.
  assert.deepEqual(other.current, changed.current)
  assert.equal(other.ripple.run, changed.ripple.run)
})

test("the pill for steps left out opens the module on its flow", () => {
  const stub = nodes(refund, START).find(
    (node) => node.type === "step" && node.data.stub
  )
  const place = doing(refund, { do: "node", id: stub.id })
  assert.equal(place.focused, REFUNDS)
  assert.deepEqual(place.camera.shot, { of: "flow", flowId: "flow_refund" })
  assert.equal(place.selected, undefined)
})

test("what stands apart from the flows opens from its own card", () => {
  const all = nodes(refund, START)
  const offMap = all.find((node) => node.type === "offmap")
  assert.deepEqual(doing(refund, { do: "node", id: offMap.id }).selected, {
    type: "offMap",
    no: 5,
  })
  const gone = all.find((node) => node.type === "row" && node.data.struck)
  assert.deepEqual(doing(refund, { do: "node", id: gone.id }).selected, {
    type: "removedFlow",
    flowId: "flow_sms_receipt",
  })
  // The dashed box around an error path is not something to click.
  const box = all.find((node) => node.type === "box")
  assert.equal(act(START, { do: "node", id: box.id }, refund), START)
})

test("a click on the empty canvas closes the panel and drops the pick", () => {
  const place = doing(refund, { do: "change", no: 1 }, { do: "pane" })
  assert.equal(place.selected, undefined)
  assert.equal(place.current, undefined)
  assert.deepEqual(place.camera, { no: 2, shot: { of: "place" }, ms: 520 })
  // With nothing open the camera stays where the reader left it.
  assert.equal(act(START, { do: "pane" }, refund), START)
  // The panel's own way out keeps the pick, for the arrows to go on from.
  const closed = doing(refund, { do: "change", no: 1 }, { do: "close" })
  assert.equal(closed.selected, undefined)
  assert.equal(pickedOf(closed, refund.model), 1)
})

test("a step folded away when another module opens has no panel to show", () => {
  const open = doing(refund, { do: "node", id: REFUNDS })
  // A step only drawn while its module is open.
  const inside = nodes(refund, open).find(
    (node) =>
      node.type === "step" &&
      node.id.startsWith("flow_refund") &&
      !refund.atlasOf().nodes.some((item) => item.id === node.id)
  )
  const picked = act(open, { do: "node", id: inside.id }, refund)
  assert.equal(panelOf(picked.selected, refund.atlasOf(REFUNDS)).open, true)
  const moved = act(picked, { do: "node", id: PAYMENTS }, refund)
  assert.equal(panelOf(moved.selected, refund.atlasOf(PAYMENTS)).open, false)
})

test("back to the whole map, by its button or by the one that fits the view", () => {
  const deep = doing(
    refund,
    { do: "node", id: REFUNDS },
    { do: "change", no: 1 }
  )
  for (const action of [{ do: "overview" }, { do: "fit" }]) {
    const out = act(deep, action, refund)
    assert.equal(out.focused, undefined)
    assert.equal(out.selected, undefined)
    assert.equal(out.current, undefined)
    assert.deepEqual(out.camera.shot, { of: "place" })
  }
  // On the whole map already, fitting just puts it back in frame, panel and all.
  const beside = doing(refund, { do: "change", no: 1 })
  const fitted = act(beside, { do: "fit" }, refund)
  assert.deepEqual(fitted.selected, beside.selected)
  assert.equal(fitted.camera.no, beside.camera.no + 1)
})

test("a walk starts at the flow's trigger, the camera on its first step", () => {
  const flowId = "flow_ba6d4948fa62"
  const place = doing(tour, { do: "walk", flowId })
  const { walk } = place
  assert.equal(walk.flowId, flowId)
  assert.equal(walk.steps[0], tour.atlasOf().flows.get(flowId).triggers[0])
  assert.deepEqual([walk.at, walk.done], [0, false])
  assert.deepEqual(place.camera.shot, { of: "step", id: walk.steps[0] })
  assert.equal(place.camera.ms, 520)
  // Without motion the whole way is there at once, in one frame.
  const calm = act(START, { do: "walk", flowId }, still(tour))
  assert.deepEqual(
    [calm.walk.at, calm.walk.done],
    [calm.walk.steps.length - 1, true]
  )
  assert.deepEqual(calm.camera.shot, { of: "steps", ids: calm.walk.steps })
  assert.deepEqual(beats(calm.walk.trail), [])
})

test("a walk's beats: the camera sets off for each step before the walk reaches it", () => {
  const start = doing(tour, { do: "walk", flowId: "flow_ba6d4948fa62" })
  const all = beats(start.walk.trail)
  const steps = start.walk.steps
  // In the order they happen.
  assert.deepEqual(
    all.map((beat) => beat.at),
    all.map((beat) => beat.at).sort((a, b) => a - b)
  )
  assert.deepEqual(all[0], {
    at: 560,
    act: { do: "reach", run: start.walk.run, step: steps[0] },
  })
  for (const step of steps.slice(1)) {
    const lead = all.find((b) => b.act.do === "lead" && b.act.step === step)
    const reach = all.find((b) => b.act.do === "reach" && b.act.step === step)
    assert.equal(reach.at - lead.at, 320, step)
  }
  // Played through, the camera follows step by step and the walk ends on its last.
  let place = start
  const seen = []
  for (const beat of all) {
    place = act(place, beat.act, tour)
    if (beat.act.do === "lead") {
      assert.deepEqual(place.camera.shot, { of: "step", id: beat.act.step })
      assert.equal(place.camera.ms, 420)
    } else seen.push(place.walk.at)
  }
  assert.deepEqual(
    seen,
    steps.map((_, index) => index)
  )
  assert.equal(place.walk.done, true)
  // A beat left over from an earlier walk does nothing.
  const stale = { do: "reach", run: start.walk.run - 1, step: steps[1] }
  assert.equal(act(start, stale, tour), start)
  // Taking the canvas in hand ends the walk.
  assert.equal(act(start, { do: "touch" }, tour).walk, undefined)
  assert.equal(act(start, { do: "endWalk" }, tour).walk, undefined)
})

test("walking a flow that is folded opens its module first", () => {
  assert.equal(refund.atlasOf().flows.get("flow_refund").mode, "focus")
  const place = doing(
    refund,
    { do: "change", no: 1 },
    { do: "close" },
    { do: "walk", flowId: "flow_refund" }
  )
  assert.equal(place.focused, REFUNDS)
  assert.equal(place.walk.flowId, "flow_refund")
  // The camera goes to the first step, and the change picked before gives way.
  assert.deepEqual(place.camera.shot, { of: "step", id: place.walk.steps[0] })
  assert.equal(place.current, undefined)
  // The walk passes the changes on the flow.
  assert.ok(place.walk.steps.includes(PAY))
  assert.ok(place.walk.trail.changed.has(PAY))
})

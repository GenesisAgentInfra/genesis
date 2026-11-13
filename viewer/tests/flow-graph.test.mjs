import assert from "node:assert/strict"
import { after as afterAll, test } from "node:test"
import { createServer } from "vite"

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
afterAll(() => server.close())
const { after, drawnGraph, graphOf, wayIn, wayThrough } =
  await server.ssrLoadModule("/src/flow-graph.ts")

const step = (step_id, kind = "action") => ({ step_id, kind, name: step_id })
const edge = (source, target, relation = "sequence") => ({
  source,
  target,
  relation,
  resolution: "resolved",
})

// start → check ─┬→ work → done
//                └→ retry ⟲ check        check ⇢ failed (on an error)
const steps = [
  step("start", "trigger"),
  step("check", "decision"),
  step("work"),
  step("retry"),
  step("done", "result"),
  step("failed", "result"),
]
const edges = [
  edge("start", "check"),
  edge("check", "work"),
  edge("check", "retry"),
  edge("retry", "check"),
  edge("work", "done"),
  edge("check", "failed", "exception"),
]

test("a line back to a step already on the way is a loop, the rest lead on", () => {
  const graph = graphOf(steps, edges)
  assert.deepEqual(
    graph.loops.map((line) => [line.source, line.target]),
    [["retry", "check"]]
  )
  assert.deepEqual(
    graph.out.get("check").map((line) => line.target),
    ["work", "retry", "failed"]
  )
  assert.equal(graph.into.has("start"), false)
  assert.deepEqual(graph.sources, ["start"])
})

test("steps read with each branch as one run, the trigger first", () => {
  const graph = graphOf(steps, edges)
  assert.deepEqual(graph.order, [
    "start",
    "check",
    "work",
    "done",
    "retry",
    "failed",
  ])
})

test("a step where branches meet reads after the last of them", () => {
  const graph = graphOf(
    [step("a", "trigger"), step("b"), step("c"), step("join")],
    [edge("a", "b"), edge("a", "c"), edge("b", "join"), edge("c", "join")]
  )
  assert.deepEqual(graph.order, ["a", "b", "c", "join"])
})

test("a line to a step the flow does not list leads nowhere", () => {
  const graph = graphOf([step("a", "trigger")], [edge("a", "ghost")])
  assert.equal(graph.lines[0].back, true)
  assert.equal(graph.out.has("a"), false)
  assert.deepEqual(graph.loops, [])
})

test("what a step leads to: one line on, then everything further, nearest first", () => {
  const graph = graphOf(steps, edges)
  assert.deepEqual(after(graph, "check"), {
    next: ["work", "retry", "failed"],
    reached: ["work", "retry", "failed", "done"],
  })
  assert.deepEqual(after(graph, "done"), { next: [], reached: [] })
})

test("the way in is the shortest one from where the flow starts", () => {
  const graph = graphOf(steps, edges)
  const way = wayIn(graph, "done")
  assert.deepEqual([...way.steps].sort(), ["check", "done", "start", "work"])
  assert.equal(way.lines.size, 3)
  // A step nothing leads to from the given starts has no way in.
  assert.equal(wayIn(graph, "done", ["failed"]).steps.size, 0)
})

test("the way worth walking passes the marked steps, then keeps off the error path", () => {
  const graph = graphOf(steps, edges)
  assert.deepEqual(wayThrough(graph, "start", new Set()).steps, [
    "start",
    "check",
    "work",
    "done",
  ])
  assert.deepEqual(wayThrough(graph, "start", new Set(["failed"])).steps, [
    "start",
    "check",
    "failed",
  ])
  assert.deepEqual(wayThrough(graph, undefined, new Set()).steps, [])
})

test("the graph of a drawing only knows the lines between drawn steps", () => {
  const line = (source, target, back = false) => ({
    id: `${source}>${target}`,
    source,
    target,
    back,
    exception: false,
    of: null,
  })
  const graph = drawnGraph(
    ["a", "c"],
    [line("a", "b"), line("a", "c"), line("c", "a", true), line("a", "a")]
  )
  assert.deepEqual(
    graph.lines.map((item) => item.id),
    ["a>c", "c>a"]
  )
  assert.deepEqual(graph.sources, ["a"])
  assert.deepEqual(
    graph.loops.map((item) => item.id),
    ["c>a"]
  )
})

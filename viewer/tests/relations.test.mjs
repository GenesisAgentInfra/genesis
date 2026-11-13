import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"
const server = await createServer({
  server: { middlewareMode: true, ws: false },
  appType: "custom",
})
after(() => server.close())
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { buildRelations } = await server.ssrLoadModule("/src/relations.ts")
const { buildAtlas } = await server.ssrLoadModule("/src/atlas/build.ts")
const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")
const sample = JSON.parse(
  await readFile(new URL("../dev/sample-expense.json", import.meta.url))
)
function setup() {
  const payload = structuredClone(sample)
  const [a, b] = payload.map.flows
  payload.map.domains = [
    { domain_id: "a", name: "提交", flow_ids: [a.flow_id] },
    { domain_id: "b", name: "审批", flow_ids: [b.flow_id] },
  ]
  const link = (id, relation = "call", resolution = "resolved") => ({
    link_id: id,
    source: { flow_id: a.flow_id, step_id: a.steps[0].step_id },
    target: { flow_id: b.flow_id },
    relation,
    resolution,
    name: id,
  })
  payload.map.links = [
    link("call-a"),
    link("call-b"),
    link("event", "event"),
    link("possible", "call", "candidate"),
    link("state", "state_handoff"),
  ]
  return { model: buildModel(payload), a, b }
}
test("module overview aggregates real calls and separates event, candidate and state semantics", () => {
  const { model } = setup()
  const graph = buildRelations(model, new Set())
  assert.equal(graph.edges.length, 2)
  assert.equal(
    graph.edges.find((e) => e.data.relation === "call").data.links.length,
    2
  )
  assert.ok(graph.edges.every((e) => !e.data.candidate))
  assert.equal(new Set(graph.edges.map((e) => e.data.lane)).size, 2)
  const all = buildRelations(model, new Set(), true, true)
  assert.equal(all.edges.length, 4)
})
test("expansion moves relations to the correct flow entrances; collapse retains each underlying link", () => {
  const { model, a, b } = setup()
  const expanded = buildRelations(model, new Set(["a", "b"]))
  assert.ok(
    expanded.edges.every(
      (e) =>
        e.sourceHandle === `out:${a.flow_id}` &&
        e.targetHandle === `in:${b.flow_id}`
    )
  )
  const collapsed = buildRelations(model, new Set())
  assert.deepEqual(
    expanded.edges.flatMap((e) => e.data.links.map((l) => l.link_id)),
    collapsed.edges.flatMap((e) => e.data.links.map((l) => l.link_id))
  )
})
test("step canvas uses local jump entries instead of cross-canvas relationship lines", () => {
  const { model, a } = setup()
  const graph = buildAtlas(model, STRINGS[model.lang])
  assert.ok(graph.edges.every((e) => e.type !== "relation"))
  const entry = graph.flows
    .get(a.flow_id)
    .nodes.find((n) => n.data.step.step_id === a.steps[0].step_id)
  assert.equal(entry.data.links.length, 5)
  assert.equal(entry.data.compact, false)
  assert.ok(entry.data.slot >= 68 + 5 * 36)
})
test("a shared change and missing link data never manufacture a call", () => {
  const { model } = setup()
  model.links = []
  assert.equal(buildRelations(model, new Set()).edges.length, 0)
})

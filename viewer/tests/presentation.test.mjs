import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { after, test } from "node:test"
import { createServer } from "vite"

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
})
after(() => server.close())
const { categoryOf, coverageKind, shortSummary, sortAlerts } =
  await server.ssrLoadModule("/src/presentation.ts")
const { buildModel, matches } = await server.ssrLoadModule("/src/model.ts")
const { buildGraph } = await server.ssrLoadModule("/src/canvas/graph.ts")
const { cutFlow } = await server.ssrLoadModule("/src/canvas/focus.ts")
const { layoutRoute } = await server.ssrLoadModule("/src/layout.ts")
const expense = JSON.parse(
  await readFile(new URL("../dev/sample-expense.json", import.meta.url))
)

test("an uncategorized observation stays unclassified regardless of its wording", () => {
  assert.equal(
    categoryOf({ statement: "Security risk: infinite retries" }),
    "unclassified"
  )
  assert.equal(categoryOf({ category: "future_category" }), "unclassified")
  assert.equal(categoryOf({ category: "reliability" }), "reliability")
  assert.equal(matches({ risky: true }, "category:unclassified"), true)
})

test("test evidence distinguishes missing behavior checks from unknown coverage", () => {
  assert.equal(coverageKind(), "unknown")
  assert.equal(
    coverageKind({ verdict: "reached_only", basis: ["static_fact"] }),
    "unknown"
  )
  assert.equal(
    coverageKind({
      verdict: "reached_only",
      basis: ["static_fact", "agent_assessment"],
    }),
    "related"
  )
  assert.equal(coverageKind({ verdict: "not_reached" }), "uncovered")
  assert.equal(
    coverageKind({ verdict: "covered", execution_data: "not_collected" }),
    "asserted"
  )
})

test("concise copy leaves the complete explanation available and supports old reports", () => {
  const change = {
    explanation: {
      summary: "Full condition and consequence.",
      short_summary: "Short clause.",
    },
  }
  assert.equal(shortSummary(change), "Short clause.")
  assert.equal(change.explanation.summary, "Full condition and consequence.")
  assert.equal(
    shortSummary({ explanation: { summary: "Legacy explanation." } }),
    "Legacy explanation."
  )
})

test("multiple alerts are deduplicated and highest severity comes first", () => {
  const low = { finding_id: "low", severity: "low" }
  const high = { finding_id: "high", severity: "high" }
  assert.deepEqual(
    sortAlerts([low, high, low]).map((item) => item.finding_id),
    ["high", "low"]
  )
})

test("the expense overview exposes both outcomes without opening the module", () => {
  const model = buildModel(expense)
  const flow = model.flows.find((view) => view.flow.name === "提交报销单")
  const graph = buildGraph(flow, model.findingStatus, false, 1300, {
    between: String,
    more: String,
  })
  const outcomes = flow.flow.steps.filter((step) => step.kind === "result")
  for (const step of outcomes)
    assert.ok(graph.nodes.some((node) => node.id === step.step_id))
  assert.equal(
    graph.nodes.some((node) => node.data.stub),
    false
  )
  assert.equal(
    model.stops.filter((stop) => matches(stop, "category:reliability")).length,
    1
  )
  assert.equal(
    model.stops.filter((stop) => matches(stop, "untested")).length,
    2
  )
})

test("long affected branches preserve decisions, error outcomes and retry endpoints", () => {
  const steps = [
    ["start", "trigger"],
    ["changed", "action"],
    ["work", "action"],
    ["check", "decision"],
    ["retry", "action"],
    ["success", "result"],
    ["failure", "result"],
    ["otherStart", "trigger"],
    ["otherWork", "action"],
    ["otherResult", "result"],
  ].map(([step_id, kind]) => ({ step_id, kind, name: step_id }))
  const edges = [
    ["start", "changed"],
    ["changed", "work"],
    ["work", "check"],
    ["check", "retry", "branch"],
    ["retry", "work", "loop"],
    ["check", "success", "branch"],
    ["check", "failure", "exception"],
    ["otherStart", "otherWork"],
    ["otherWork", "otherResult"],
  ].map(([source, target, relation = "sequence"]) => ({
    source,
    target,
    relation,
  }))
  const cut = cutFlow(steps, layoutRoute(steps, edges), new Set(["changed"]))
  for (const id of ["check", "retry", "work", "success", "failure"])
    assert.ok(cut.keep.has(id), id)
  assert.equal(cut.keep.has("otherResult"), false)
})

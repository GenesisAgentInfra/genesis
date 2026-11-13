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
const { buildModel } = await server.ssrLoadModule("/src/model.ts")
const { buildGraph } = await server.ssrLoadModule("/src/canvas/graph.ts")
const { cutFlow } = await server.ssrLoadModule("/src/canvas/focus.ts")
const { graphOf } = await server.ssrLoadModule("/src/flow-graph.ts")
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
    model.stops.filter(
      (stop) => stop.risky && stop.categories?.includes("reliability")
    ).length,
    1
  )
  assert.equal(
    model.stops.filter((stop) => stop.status === "untested").length,
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
  const cut = cutFlow(steps, graphOf(steps, edges), new Set(["changed"]))
  for (const id of ["check", "retry", "work", "success", "failure"])
    assert.ok(cut.keep.has(id), id)
  assert.equal(cut.keep.has("otherResult"), false)
})

test("both submission and unchanged approval are diagrams in the overview", async () => {
  const { buildAtlas } = await server.ssrLoadModule("/src/atlas/build.ts")
  const { STRINGS } = await server.ssrLoadModule("/src/i18n.ts")
  const model = buildModel(expense)
  const atlas = buildAtlas(model, STRINGS.zh)
  for (const flow of model.flows) {
    assert.ok(
      atlas.nodes.some(
        (node) => node.type === "flow" && node.data.flowId === flow.flow.flow_id
      )
    )
    assert.equal(
      atlas.nodes.some(
        (node) => node.type === "row" && node.data.flowId === flow.flow.flow_id
      ),
      false
    )
  }
})

test("only immutable GitHub URLs become source actions", async () => {
  const { sourceLinkOf } = await server.ssrLoadModule("/src/presentation.ts")
  const link = Object.values(expense.source_links)[0]
  assert.equal(sourceLinkOf({ source_links: { a: link } }, ["a"]), link)
  assert.equal(sourceLinkOf({}, ["a"]), undefined)
  for (const url of [
    "javascript:alert(1)",
    "https://github.com.evil.test/o/r/blob/" + "a".repeat(40) + "/x",
    "https://github.com/o/r/blob/main/x",
    "https://user:secret@github.com/o/r/blob/" + "a".repeat(40) + "/x",
  ]) {
    assert.equal(
      sourceLinkOf({ source_links: { a: { url, exact: true } } }, ["a"]),
      undefined
    )
  }
})

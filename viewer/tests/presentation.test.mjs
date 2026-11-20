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
const { buildModel, risksOf } = await server.ssrLoadModule("/src/model.ts")
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

test("a risk the report names for a change shows on that change, once", () => {
  const plain = "chg_37bc7dab508b2941"
  const flagged = "chg_526315dc0e3a2feb"
  const repeated = expense.report.finding_changes[0].finding.statement
  const model = buildModel({
    ...expense,
    report: {
      ...expense.report,
      risks: [
        {
          risk_id: "risk_boundary",
          statement: "恰好等于门槛的报销单不再经过审核。",
          severity: "medium",
          category: "correctness",
          change_ids: [plain],
          evidence_ids: [],
        },
        // The same remark as the finding already on the change: not shown a second time.
        {
          risk_id: "risk_repeat",
          statement: repeated,
          severity: "medium",
          category: "reliability",
          change_ids: [flagged],
        },
        // A risk that names no change of this report is left out.
        {
          risk_id: "risk_stray",
          statement: "与本次改动无关。",
          severity: "low",
          change_ids: ["chg_unknown"],
        },
      ],
    },
  })
  const before = buildModel(expense)
  const stop = model.stops.find((item) => item.change?.change_id === plain)
  assert.equal(
    before.stops.find((item) => item.change?.change_id === plain).risky,
    false
  )
  assert.equal(stop.risky, true)
  assert.equal(stop.tone, "risk")
  assert.deepEqual(stop.categories, ["correctness"])
  assert.equal(model.findingStatus.get("risk_boundary"), "introduced")
  assert.equal(
    model.findings.get("risk_boundary").statement.includes("门槛"),
    true
  )
  assert.equal(model.findings.has("risk_repeat"), false)
  assert.equal(model.findings.has("risk_stray"), false)
  assert.equal(model.counts.newRisks, before.counts.newRisks + 1)
  assert.equal(model.counts.risky, before.counts.risky + 1)
  // The card of the step lists the risk, so its badge can count it.
  const flow = model.flowById.get(stop.flowId)
  const graph = buildGraph(flow, model.findingStatus, false, 1300, {
    between: String,
    more: String,
  })
  const node = graph.nodes.find((item) => item.id === stop.nodeId)
  assert.equal(
    node.data.alerts.some((item) => item.finding_id === "risk_boundary"),
    true
  )
  // The payload the page was given is left as it was.
  assert.deepEqual(expense.report.changes[0].finding_ids, [])
})

test("a stop that stands for several changes carries the risks of all of them", () => {
  const [first, second] = expense.report.changes
  // Told in the same words at the same place, the two changes read as one stop.
  const together = {
    ...first,
    projection: second.projection,
    explanation: second.explanation,
    finding_ids: [],
  }
  const model = buildModel({
    ...expense,
    report: {
      ...expense.report,
      changes: [{ ...second, finding_ids: [] }, together],
      finding_changes: [],
      risks: [
        {
          risk_id: "risk_one",
          statement: "第一条风险。",
          severity: "low",
          change_ids: [second.change_id],
        },
        {
          risk_id: "risk_two",
          statement: "第二条风险。",
          severity: "medium",
          change_ids: [first.change_id],
        },
      ],
    },
  })
  assert.equal(model.stops.length, 1)
  const [stop] = model.stops
  assert.equal(stop.group.length, 2)
  assert.deepEqual(
    risksOf(model, stop.change)
      .map((finding) => finding.finding_id)
      .sort(),
    ["risk_one", "risk_two"]
  )
  const flow = model.flowById.get(stop.flowId)
  const graph = buildGraph(flow, model.findingStatus, false, 1300, {
    between: String,
    more: String,
  })
  const node = graph.nodes.find((item) => item.id === stop.nodeId)
  assert.equal(node.data.alerts.length, 2)
})

test("a risk in the words of an older finding still marks the change, and reads once", () => {
  const [, flagged] = expense.report.changes
  const [known] = expense.report.finding_changes
  const model = buildModel({
    ...expense,
    report: {
      ...expense.report,
      // The finding was there before this change: it is not a risk the change brings.
      finding_changes: [{ ...known, status: "persisting" }],
      risks: [
        {
          risk_id: "risk_again",
          statement: known.finding.statement,
          severity: "medium",
          change_ids: [flagged.change_id],
        },
      ],
    },
  })
  const stop = model.stops.find(
    (item) => item.change?.change_id === flagged.change_id
  )
  assert.equal(stop.risky, true)
  assert.equal(risksOf(model, stop.change).length, 1)
})

test("a risk that names only a change to test code is left off the page", () => {
  const model = buildModel({
    ...expense,
    report: {
      ...expense.report,
      changes: [
        ...expense.report.changes,
        {
          ...expense.report.changes[0],
          change_id: "chg_test_only",
          kind: "test_modified",
          finding_ids: [],
        },
      ],
      risks: [
        {
          risk_id: "risk_on_test",
          statement: "测试不再检查边界。",
          severity: "low",
          change_ids: ["chg_test_only"],
        },
      ],
    },
  })
  const before = buildModel(expense)
  assert.equal(model.findings.has("risk_on_test"), false)
  assert.equal(model.counts.newRisks, before.counts.newRisks)
  assert.equal(model.stops.length, before.stops.length)
})

test("a step shows input and output only when both are structured", async () => {
  const { contractOf } = await server.ssrLoadModule("/src/presentation.ts")
  const step = { step_id: "s", name: "Check the amount", kind: "decision" }
  assert.equal(contractOf(), undefined)
  assert.equal(contractOf(step), undefined)
  // Older reports may carry prose: nothing structured to show.
  assert.equal(
    contractOf({
      ...step,
      contract: { input: "an amount", output: "yes or no" },
    }),
    undefined
  )
  assert.equal(
    contractOf({
      ...step,
      contract: { input: { type: "number" }, output: null },
    }),
    undefined
  )
  assert.deepEqual(
    contractOf({
      ...step,
      contract: {
        input: { type: "object", properties: { amount: { type: "number" } } },
        output: { type: "boolean" },
        constraints: "ignored",
      },
    }),
    {
      input: { type: "object", properties: { amount: { type: "number" } } },
      output: { type: "boolean" },
    }
  )
})

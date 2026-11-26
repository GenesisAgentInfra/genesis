import assert from "node:assert/strict"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { after, before, test } from "node:test"
import { pathToFileURL } from "node:url"
import { chromium } from "playwright"
import { inspectCards, waitForMap } from "../../scripts/readability.mjs"

const root = new URL("../../", import.meta.url)
const asset = new URL(
  "../packages/genesis_ci/src/genesis_ci/assets/viewer/index.html",
  root
)
const slot = '<script id="genesis-data" type="application/json">null</script>'
const loadSample = async (name) =>
  JSON.parse(await readFile(new URL(`dev/sample-${name}.json`, root), "utf8"))
let browser, directory, template

before(async () => {
  directory = await mkdtemp(join(tmpdir(), "genesis-viewer-"))
  template = await readFile(asset, "utf8")
  assert.equal(
    template.split(slot).length,
    2,
    "expected one payload slot in the shipped HTML"
  )
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  })
})
after(async () => {
  await browser?.close()
  if (directory) await rm(directory, { recursive: true, force: true })
})

async function openExport(t, payload, viewport) {
  const file = join(
    directory,
    `${viewport.width}-${payload.report ? "review" : "project"}.html`
  )
  const json = JSON.stringify(payload).replaceAll("<", "\\u003c")
  await writeFile(
    file,
    template.replace(slot, () => slot.replace("null", () => json))
  )
  const page = await browser.newPage({
    viewport,
    offline: true,
    reducedMotion: "reduce",
  })
  t.after(() => page.close())
  const pageErrors = []
  page.on("pageerror", (error) => pageErrors.push(error.message))
  t.after(() => assert.deepEqual(pageErrors, []))
  page.setDefaultTimeout(6_000)
  await page.goto(pathToFileURL(file).href)
  await waitForMap(page)
  return page
}

async function assertReadable(page, state) {
  const { cards, problems } = await page.evaluate(inspectCards)
  assert.ok(cards > 0, `${state}: expected at least one card`)
  assert.deepEqual(problems, [], state)
}

async function automaticScale(page) {
  return page
    .locator(".react-flow__viewport")
    .evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).a)
}

// A sparse review retains the pinned source and change evidence from the synthetic
// expense fixture. Long headings and a long summary expose fixed-box clamping.
async function sparseReview() {
  const data = await loadSample("expense")
  const change = data.report.changes[0]
  const flow = data.map.flows.find(
    (flow) => flow.flow_id === change.projection.flow_id
  )
  const step = flow.steps.find(
    (step) => step.step_id === change.projection.step_id
  )
  step.name =
    "Check the requested settlement amount against the partner expense threshold"
  flow.name = "Resolve settlement currency on a partner refund"
  flow.steps = [step]
  flow.edges = []
  data.map.flows = [flow]
  data.map.domains[0].name = "Partner settlement and reconciliation"
  data.map.domains[0].flow_ids = [flow.flow_id]
  data.report.finding_changes = []
  data.report.changes = [change]
  change.explanation.short_summary =
    "Amounts exactly at the threshold now skip manual review and proceed directly to the approval step."
  return data
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`sparse review stays readable on open, reload and inspection at ${viewport.width}px`, async (t) => {
    const payload = await sparseReview()
    const page = await openExport(t, payload, viewport)
    const firstScale = await automaticScale(page)
    assert.ok(
      firstScale >= 0.66 && firstScale <= 1.001,
      `unexpected opening zoom ${firstScale}`
    )
    await page.reload()
    await waitForMap(page)
    assert.equal(await automaticScale(page), firstScale)
    const flow = payload.map.flows[0]
    for (const name of [flow.name, payload.map.domains[0].name])
      assert.equal(await page.getByText(name, { exact: true }).count(), 1)
    const card = page.locator("[data-step-card]")
    const title = card.getByText(flow.steps[0].name, { exact: true })
    assert.equal(await title.count(), 1)
    const font = await title.evaluate((el) =>
      parseFloat(getComputedStyle(el).fontSize)
    )
    const visibleFont = font * firstScale
    assert.ok(
      font >= 12 && visibleFont <= 16,
      `step title is ${font}px at ${firstScale}x zoom (${visibleFont}px on screen)`
    )
    assert.ok(
      await card
        .getByText(payload.report.changes[0].explanation.short_summary, {
          exact: true,
        })
        .isVisible(),
      "change summary should be visible on the card"
    )
    await assertReadable(page, "overview")
    await title.click()
    const panel = page.locator("[data-panel]")
    await panel
      .getByText(payload.report.changes[0].tests.note, { exact: true })
      .waitFor()
    const link = await panel.getByRole("link").first().getAttribute("href")
    assert.ok(
      Object.values(payload.source_links).some((source) => source.url === link),
      "inspector lost the fixture's code link"
    )
    await waitForMap(page)
    await assertReadable(page, "selected change")
  })
}

test("project steps wrap Chinese, English and unbroken names", async (t) => {
  const payload = await loadSample("map")
  const steps = payload.map.flows[0].steps
  steps[0].name =
    "检查报销申请中的金额是否超过团队批准的上限，并保留此步骤的所有输入记录。".repeat(
      2
    )
  steps[1].name =
    "validate_requested_expense_threshold_and_configuration_override_".repeat(2)
  const page = await openExport(t, payload, { width: 960, height: 720 })
  await assertReadable(page, "project map")
  for (const step of steps.slice(0, 2))
    assert.equal(
      await page
        .locator("[data-step-card]")
        .getByText(step.name, { exact: true })
        .count(),
      1
    )
})

test("dense review retains readable off-map changes and compact rows", async (t) => {
  const payload = await loadSample("refund")
  const detached = payload.report.changes.find(
    (item) => item.projection.status === "unassigned"
  )
  detached.explanation.summary = "检查退款渠道返回的默认币种。".repeat(12)
  payload.report.removed_flows[0].name =
    "previous_refund_delivery_status_".repeat(5)
  const page = await openExport(t, payload, { width: 1280, height: 720 })
  await assertReadable(page, "dense review")
  assert.equal(
    await page
      .locator(".react-flow__node-offmap")
      .getByText(detached.explanation.summary, { exact: true })
      .count(),
    1
  )
  assert.equal(
    await page
      .locator(".react-flow__node-row")
      .getByText(payload.report.removed_flows[0].name, { exact: true })
      .count(),
    1
  )
  await page
    .getByRole("button", { name: "展开全部步骤", exact: true })
    .first()
    .click()
  await waitForMap(page)
  await assertReadable(page, "expanded module")
})

test("empty projects and projects with only skeleton rows finish rendering", async (t) => {
  const payload = await loadSample("map")
  for (const flow of payload.map.flows) flow.stage = "skeleton"
  const viewport = { width: 1024, height: 768 }
  const rows = await openExport(t, payload, viewport)
  assert.equal(await rows.locator("[data-step-card]").count(), 0)
  assert.equal(
    await rows.locator(".react-flow__node-row").count(),
    payload.map.flows.length
  )
  await assertReadable(rows, "row-only project")

  payload.map.flows = []
  payload.map.domains = []
  const empty = await openExport(t, payload, viewport)
  assert.deepEqual(await empty.evaluate(inspectCards), {
    cards: 0,
    problems: [],
  })
  assert.equal(
    await empty.getByText(/^(No flow to show\.|没有可以显示的流程。)$/).count(),
    1
  )
})

// Check the HTML someone will receive, including its own embedded template and data.
import { realpath } from "node:fs/promises"
import { pathToFileURL } from "node:url"
import { chromium } from "playwright"
import { inspectCards, waitForMap } from "./readability.mjs"

async function checkMap(browser, filename, viewport) {
  const url = pathToFileURL(await realpath(filename))
  const context = await browser.newContext({
    viewport,
    reducedMotion: "reduce",
    offline: true,
  })
  try {
    const page = await context.newPage()
    const errors = []
    page.on("pageerror", (error) => errors.push(error.message))
    await page.goto(url.href)
    const check = async (state) => {
      await waitForMap(page)
      const { cards, problems } = await page.evaluate(inspectCards)
      const findings = [...errors, ...problems]
      if (findings.length) {
        throw new Error(`${state}:\n  ${findings.join("\n  ")}`)
      }
      console.log(`  ${state}: ${cards} cards checked`)
    }
    await check("Overview")
    const changes = page.getByRole("button", { name: /^(Changes|改动清单)$/ })
    if (await changes.count()) {
      const count = Number((await changes.innerText()).match(/\d+\s*$/)?.[0])
      if (!Number.isSafeInteger(count) || count < 1)
        throw new Error("Could not read the number of changes in the overview")
      for (let number = 1; number <= count; number++) {
        // Reopen the export the way a recipient follows a shared change link.
        // A fresh document also ensures a previous panel cannot satisfy this check.
        await page.goto("about:blank")
        url.hash = `change=${number}`
        await page.goto(url.href)
        await page.locator("[data-panel] h2").waitFor()
        await check(`Change ${number} with details open`)
      }
    }
  } finally {
    await context.close()
  }
}

async function main(files) {
  if (!files.length)
    throw new Error(
      "Usage: npm run check:map -- path/to/view.html [more HTML files]"
    )
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  })
  try {
    for (const file of files) {
      for (const viewport of [
        { width: 1280, height: 720 },
        { width: 390, height: 844 },
      ]) {
        console.log(`${file} (${viewport.width}×${viewport.height})`)
        await checkMap(browser, file, viewport)
      }
    }
  } finally {
    await browser.close()
  }
}

main(process.argv.slice(2)).catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})

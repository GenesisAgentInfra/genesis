// Graphical import: the viewer's style analysis. Re-run from viewer/ with
// `node graphical/install/analyze-styles.mjs` before install, check or updates.
import { analyzeAppStyles } from "@graphical/editor/analyze-styles"
import { writeFile } from "node:fs/promises"

const inventory = await analyzeAppStyles({
  root: process.cwd(),
  // The whole viewer is one page: the canvas, its headline and the detail panel.
  roots: ["src"],
  appName: "Genesis",
  tailwind: true,
  // Written from JavaScript while the map pans and zooms, or measured after render.
  variables: { "--zoom": "1", "--lift": "1", "--graph": "28px" },
  classify() {
    return {}
  },
  // `cn` (src/lib/utils.ts) merges with tailwind-merge extended by Graphical's own config
  // (graphical/generated/tailwind-merge.cjs). The analyzer only recognises the stock
  // `twMerge`, which would drop `text-body-m` beside `text-ink-2`, so the helper and the
  // class constants passed through it are reviewed by hand.
  reviewCoverage(issue) {
    if (issue.path === "src/lib/utils.ts" && issue.kind === "unresolved-class-source")
      return "cn is clsx + extendTailwindMerge(graphical/generated/tailwind-merge.cjs); its arguments are class lists, converted."
    if (
      issue.kind === "mixed-class-data" &&
      ((issue.path === "src/canvas/step-node.tsx" && /\bcontent\b/.test(issue.detail)) ||
        (issue.path === "src/components/commit-range.tsx" && /\bclassName\b/.test(issue.detail)))
    )
      return "A class-list constant passed only to cn and className; it holds Graphical classes already."
    return undefined
  },
})
await writeFile(
  new URL("./style-inventory.json", import.meta.url),
  JSON.stringify(inventory)
)
console.log("analysis written")

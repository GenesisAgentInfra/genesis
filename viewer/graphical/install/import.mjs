// Graphical import: the viewer's tokens in Graphical's slots, and why each sits where it
// does. It ran once, before `npx graphical-install`, against src/index.css as it was then
// (authored colours; see git history), and wrote import.json. Do not run it again: the
// stylesheet now holds aliases, and graphical/role-map.json is the living map.
import { readFile, writeFile } from "node:fs/promises"
import { extendRoleMap, shadcnProfile } from "@graphical/editor/install"

const css = await readFile(new URL("../../src/index.css", import.meta.url), "utf8")
/** The custom properties a block defines, with their authored values. */
function block(selector) {
  const start = css.indexOf(`${selector} {`)
  const body = css.slice(start + selector.length + 2, css.indexOf("\n}", start))
  const values = {}
  for (const part of body.replace(/\/\*[\s\S]*?\*\//g, "").split(";")) {
    const match = /^\s*(--[\w-]+)\s*:\s*([\s\S]+?)\s*$/.exec(part)
    if (match) values[match[1]] = match[2].replace(/\s+/g, " ")
  }
  return values
}
const light = block(":root")
const dark = { ...light, ...block(':root[data-theme="dark"]') }

const defined = { path: "src/index.css", selector: ":root" }
const both = (lightToken, darkToken) => ({ light: lightToken, dark: darkToken })
const role = (variable, token, extra = {}) => ({ variable, token, defined, ...extra })

const roleMap = extendRoleMap(
  shadcnProfile({
    modes: { kind: "attribute", attribute: "data-theme", dark: "dark", light: "light" },
  }),
  {
    // Tailwind's own spacing builds sizes too; the rest the viewer never defines.
    remove: [
      "--spacing",
      "--destructive-foreground",
      "--accent-foreground",
      ...["", "-foreground", "-primary", "-primary-foreground", "-accent", "-accent-foreground", "-border", "-ring"].map((s) => `--sidebar${s}`),
      ...[1, 2, 3, 4, 5].map((n) => `--chart-${n}`),
      ...["xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl"].flatMap((s) => [`--text-${s}`, `--text-${s}--line-height`]),
      ...["tighter", "tight", "normal", "wide", "wider"].map((s) => `--tracking-${s}`),
      "--font-weight-normal",
      "--font-weight-medium",
      "--font-weight-semibold",
      "--font-serif",
    ],
    tokens: [
      // The canvas is the page; cards, the panel and menus sit a step lighter on it in
      // light and a step above it in dark. A flow's card is the half step between.
      role("--canvas", both("neutral-3", "neutral-1")),
      role("--background", both("neutral-3", "neutral-1")),
      role("--card", both("neutral-1", "neutral-3")),
      role("--popover", both("neutral-1", "neutral-3")),
      role("--handle", both("neutral-1", "neutral-3")),
      role("--flow-top", both("neutral-1", "neutral-2")),
      role("--flow-bottom", "neutral-2"),
      role("--flow-rim", "neutral-10-transparent"),
      role("--field", both("neutral-3", "neutral-4")),
      role("--secondary", both("neutral-3", "neutral-4")),
      role("--muted", both("neutral-3", "neutral-4")),
      role("--tile-result-bg", both("neutral-3", "neutral-4")),
      role("--line", both("neutral-4", "neutral-5")),
      role("--border", both("neutral-4", "neutral-5")),
      role("--input", both("neutral-4", "neutral-5")),
      role("--handle-rim", both("neutral-5", "neutral-6")),
      role("--scrollbar", both("neutral-5", "neutral-6")),
      role("--edge", both("neutral-6", "neutral-7")),
      role("--ink-3", "neutral-7"),
      role("--ink-2", "neutral-8"),
      role("--muted-foreground", "neutral-8"),
      role("--tile-result-ink", "neutral-8"),
      role("--edge-strong", "neutral-9"),
      role("--ink", "neutral-10"),
      role("--foreground", "neutral-10"),
      role("--selection-ink", "neutral-10"),
      // The primary action is ink, as on the canvas it sits on.
      role("--primary", "primary"),
      role("--primary-foreground", "primary.foreground"),
      // What a change asks of the reader: a risk, no test reaching it, a test that checks it.
      role("--risk", "error"),
      role("--destructive", "error"),
      role("--edge-exception-strong", "error"),
      role("--edge-exception", "error", { derive: { mix: 0.7, with: "neutral-1" } }),
      role("--change", "warning"),
      role("--warn", "warning", { derive: { mix: 0.85, with: "neutral-10" } }),
      role("--change-bg", "warning-transparent"),
      role("--ok", "success"),
      // Selection is the one blue; the step kinds are the categorical palette.
      role("--select", "color-1"),
      role("--ring", "color-1"),
      role("--selection-bg", "color-1-transparent"),
      role("--tile-action-ink", "color-2"),
      role("--tile-action-bg", "color-2-transparent"),
      role("--tile-trigger-ink", "color-3"),
      role("--tile-trigger-bg", "color-3-transparent"),
      role("--tile-decision-ink", "color-4"),
      role("--tile-decision-bg", "color-4-transparent"),
      role("--tile-external-ink", "color-5"),
      role("--tile-external-bg", "color-5-transparent"),
      // Elevation: a card at rest, under the pointer, and chrome floating over the map.
      role("--shadow-node", "shadow.s"),
      role("--shadow-node-hover", "shadow.m"),
      role("--shadow-float", "shadow.l"),
      role("--radius", "radius.m", { format: "rem" }),
      role("--ease-out", "motion.small.easing"),
      { variable: "--font-sans", token: "font.body", defined: { path: "src/index.css", selector: "@theme inline" } },
      { variable: "--font-mono", token: "font.data", defined: { path: "src/index.css", selector: "@theme inline" } },
    ],
    // A flow card's lift carries an inset highlight, which is not elevation. The tone
    // inks are text on a tone's pale tint: as the bright tone itself they fall below a
    // readable contrast, so they keep their darker authored values.
    fixed: ["--shadow-flow", "--change-ink", "--risk-ink"],
    appearance: {
      initial: { navigation: "blended", grouping: "cards", surface: "raised" },
      cards: { selector: '[data-slot="card"]', background: "--card" },
    },
  }
)

const SYSTEM =
  '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif'
const MONO = 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace'
const weights = { regular: 400, medium: 500, heavy: 600 }

const document = {
  name: "Genesis",
  theme: {
    primaryActionColor: "neutral-10",
    colors: {
      light: {
        "color-1": "#2f6feb",
        "color-2": "#6a3fd4",
        "color-3": "#1a7f45",
        "color-4": "#c9530a",
        "color-5": "#9a6200",
        "neutral-1": "#ffffff",
        "neutral-2": "#fafafa",
        "neutral-3": "#f4f4f5",
        "neutral-4": "#d9dadd",
        "neutral-5": "#c9cace",
        "neutral-6": "#7d818c",
        "neutral-7": "#62656e",
        "neutral-8": "#4d5058",
        "neutral-9": "#3a3b40",
        "neutral-10": "#111113",
        success: "#17803d",
        warning: "#e2860b",
        error: "#d92d20",
      },
      dark: {
        "color-1": "#6ea0ff",
        "color-2": "#b49cff",
        "color-3": "#6fd39a",
        "color-4": "#ffa066",
        "color-5": "#f2c14e",
        "neutral-1": "#101012",
        "neutral-2": "#161619",
        "neutral-3": "#1c1c20",
        "neutral-4": "#26262b",
        "neutral-5": "#3b3d44",
        "neutral-6": "#55565d",
        "neutral-7": "#8e9097",
        "neutral-8": "#b6b7bd",
        "neutral-9": "#d3d4d9",
        "neutral-10": "#f1f1f3",
        success: "#4cc27a",
        warning: "#f0a030",
        error: "#ff6b5e",
      },
    },
    fonts: {
      body: { family: SYSTEM, weights },
      display: { family: SYSTEM, weights },
      data: { family: MONO, weights },
    },
  },
}

// Fonts are written in the @theme block; give the source their authored stacks.
const fonts = { "--font-sans": SYSTEM, "--font-mono": MONO }
const mapped = new Set(roleMap.tokens.map((token) => token.variable))
/** A value with the viewer's own variables it reads resolved, as the page computes it. */
const resolve = (values, value, depth = 0) =>
  depth > 8
    ? value
    : value.replace(/var\((--[\w-]+)\)/g, (whole, name) =>
        values[name] ? resolve(values, values[name], depth + 1) : whole
      )
const pick = (values) =>
  Object.fromEntries(
    Object.entries({ ...values, ...fonts })
      .filter(([name]) => mapped.has(name))
      .map(([name, value]) => [name, resolve(values, value)])
  )
const source = { light: pick(light), dark: pick(dark) }

await writeFile(
  new URL("./import.json", import.meta.url),
  `${JSON.stringify({ document, roleMap, source }, null, 2)}\n`
)
console.log(`import written: ${roleMap.tokens.length} roles`)

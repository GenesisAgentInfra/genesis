import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"
import { viteSingleFile } from "vite-plugin-singlefile"

/**
 * graphical-install writes its tailwind-merge config as CommonJS
 * (graphical/generated/tailwind-merge.cjs); the dev server serves source as ES modules
 * only, so it gets the config wrapped as one. The build reads CommonJS itself.
 */
const graphicalConfig = {
  name: "graphical-commonjs",
  apply: "serve" as const,
  transform(code: string, id: string) {
    if (!/[\\/]graphical[\\/]generated[\\/][^\\/]+\.cjs(\?|$)/.test(id)) return
    return {
      code: `const module = { exports: {} };\n${code}\nexport default module.exports;\n`,
      map: null,
    }
  },
}

/** Graphical's editor is a paid package that a checkout may not have (see the README). */
const editorInstalled = existsSync(
  resolve(import.meta.dirname, "node_modules/@graphical/editor/package.json")
)

/**
 * A rendered page is often passed on as one file, so it carries its own third-party
 * notices: all of THIRD_PARTY_NOTICES.md goes into a comment at the top of its head.
 * The build fails when a package whose code ends up in the page is not named there.
 */
const noticesPath = resolve(import.meta.dirname, "../THIRD_PARTY_NOTICES.md")
/** Code the build tools add to the page, by the virtual module that holds it. */
const toolCode: Record<string, string> = {
  "vite/modulepreload-polyfill.js": "vite",
  "rolldown/runtime.js": "rolldown",
}

function packageOf(module: string): string | undefined {
  const id = module.replaceAll("\\", "/")
  if (id.startsWith("\0")) return toolCode[id.slice(1)] ?? id.slice(1)
  const at = id.lastIndexOf("/node_modules/")
  if (at < 0) return undefined
  const parts = id.slice(at + "/node_modules/".length).split("/")
  return parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0]
}

function names(notices: string, name: string): boolean {
  const word = name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")
  return new RegExp(`(^|[\\s,(|\`])${word}([\\s,)|\`]|$)`, "m").test(notices)
}

const thirdPartyNotices: Plugin = {
  name: "third-party-notices",
  apply: "build",
  transformIndexHtml: {
    order: "pre",
    handler(html) {
      // An HTML comment ends at the first "-->"; keep the text from closing it early.
      const text = readFileSync(noticesPath, "utf8")
        .replaceAll("-->", "- ->")
        .replaceAll("<!--", "<! --")
      return html.replace("<head>", `<head>\n    <!--\n${text}    -->`)
    },
  },
  generateBundle(_options, bundle) {
    const notices = readFileSync(noticesPath, "utf8")
    const missing = new Set<string>()
    for (const output of Object.values(bundle)) {
      if (output.type !== "chunk") continue
      for (const [id, module] of Object.entries(output.modules)) {
        const name = module.renderedLength > 0 ? packageOf(id) : undefined
        if (name && !names(notices, name)) missing.add(name)
      }
    }
    if (missing.size)
      this.error(
        `THIRD_PARTY_NOTICES.md does not name ${[...missing].sort().join(", ")}, ` +
          "whose code is in the page: add each with its license."
      )
  },
}

// The build is one HTML file with every script, style and font inlined, written into
// the CLI package. `genesis map render` fills its data slot; the page then opens
// from file:// with no network.
export default defineConfig({
  plugins: [
    graphicalConfig,
    thirdPartyNotices,
    react(),
    tailwindcss(),
    viteSingleFile({ removeViteModuleLoader: true }),
  ],
  define: {
    __GRAPHICAL_EDITOR__: JSON.stringify(editorInstalled),
  },
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
  build: {
    outDir: resolve(
      import.meta.dirname,
      "../packages/genesis_ci/src/genesis_ci/assets/viewer"
    ),
    emptyOutDir: true,
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
    cssCodeSplit: false,
    reportCompressedSize: false,
  },
})

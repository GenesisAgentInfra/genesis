import { existsSync } from "node:fs"
import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
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

// The build is one HTML file with every script, style and font inlined, written into
// the CLI package. `genesis map render` fills its data slot; the page then opens
// from file:// with no network.
export default defineConfig({
  plugins: [
    graphicalConfig,
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

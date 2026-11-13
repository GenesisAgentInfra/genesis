// The merge config graphical-install writes for tailwind-merge, read as a module.
declare module "*/graphical/generated/tailwind-merge.cjs" {
  import type { extendTailwindMerge } from "tailwind-merge"
  const config: Parameters<typeof extendTailwindMerge>[0]
  export default config
}

/** Whether Graphical's editor package is installed in this checkout (set by Vite). */
declare const __GRAPHICAL_EDITOR__: boolean

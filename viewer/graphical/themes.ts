import project from "./project.json"
import genesis from "./themes/graphical.json"
import alloy from "./themes/alloy.json"

export const themes = {
  "themes/graphical.json": genesis,
  "themes/alloy.json": alloy,
}

const activeTheme = project.themes.find((theme) => theme.id === project.active)
if (!activeTheme || !Object.hasOwn(themes, activeTheme.path)) {
  throw new Error("The active Graphical theme is missing from the viewer registry")
}

export const activeDocument = themes[activeTheme.path as keyof typeof themes]

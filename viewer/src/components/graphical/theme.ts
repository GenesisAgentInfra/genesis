import { activeDocument } from "../../../graphical/themes"
import type { ThemeDocument } from "./lib/theme-model"

// The installer and the component runtime share the active Genesis theme document.
export const theme = activeDocument as ThemeDocument

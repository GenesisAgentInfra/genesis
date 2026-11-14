import { createContext } from "react"
import type { ThemeDocument } from "@/components/graphical"

export const GraphicalPreview = createContext<{
  document: ThemeDocument
  portal: HTMLDivElement | null
} | null>(null)

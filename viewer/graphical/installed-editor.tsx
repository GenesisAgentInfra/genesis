// Graphical's editor around the viewer. Loaded only in development, through
// development-editor.tsx; nothing here reaches the built page.
import { useEffect, type ReactNode } from "react"
import {
  GraphicalInstalledEditor,
  isGraphicalInteraction,
  readGraphicalProject,
} from "@graphical/editor/native"
import "@graphical/editor/styles.css"

import project from "./project.json"
import roleMap from "./role-map.json"
import theme from "./themes/graphical.json"
import { registerEditorInteraction } from "./interaction-boundary"

const current = readGraphicalProject(
  project,
  { "themes/graphical.json": theme },
  roleMap
)

export default function InstalledEditor({
  children,
  route,
}: {
  children: ReactNode
  route: string
}) {
  // The arrows, Enter and Escape step through changes on the map; inside the editor
  // they belong to the editor.
  useEffect(() => registerEditorInteraction(isGraphicalInteraction), [])
  return (
    <GraphicalInstalledEditor
      document={current.document}
      roleMap={current.roleMap}
      handoffContext={current.handoffContext}
      route={route}
      initialPanelOpen
    >
      {children}
    </GraphicalInstalledEditor>
  )
}

// Graphical's editor around the viewer. Loaded only in development, through
// development-editor.tsx; nothing here reaches the built page.
import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  GraphicalInstalledEditor,
  isGraphicalInteraction,
  readGraphicalProject,
  useGraphicalTheme,
} from "@graphical/editor/native"
import "./installed-editor.css"

import project from "./project.json"
import roleMap from "./role-map.json"
import { themes } from "./themes"
import { registerEditorInteraction } from "./interaction-boundary"
import type { HostProps } from "./editor-root"
import { GraphicalPreview } from "./preview-context"
import type { ThemeDocument } from "@/components/graphical"

const current = readGraphicalProject(project, themes, roleMap)

export default function InstalledEditor({ children, ...props }: HostProps) {
  // The arrows, Enter and Escape step through changes on the map; inside the editor
  // they belong to the editor.
  useEffect(() => registerEditorInteraction(isGraphicalInteraction), [])
  const [portal, setPortal] = useState<HTMLDivElement | null>(null)
  return (
    <GraphicalInstalledEditor
      document={current.document}
      roleMap={current.roleMap}
      handoffContext={current.handoffContext}
      {...props}
      onAppPortalContainerChange={setPortal}
      initialPanelOpen={false}
    >
      <PreviewTheme portal={portal}>{children}</PreviewTheme>
    </GraphicalInstalledEditor>
  )
}

// An authoring iframe renders the host without an editor provider.
function PreviewTheme({
  portal,
  children,
}: {
  portal: HTMLDivElement | null
  children: ReactNode
}) {
  return portal ? (
    <ActivePreview portal={portal}>{children}</ActivePreview>
  ) : (
    children
  )
}

function ActivePreview({
  portal,
  children,
}: {
  portal: HTMLDivElement
  children: ReactNode
}) {
  const { document } = useGraphicalTheme()
  const value = useMemo(
    () => ({ document: document as ThemeDocument, portal }),
    [document, portal]
  )
  return <GraphicalPreview value={value}>{children}</GraphicalPreview>
}

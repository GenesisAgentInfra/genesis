// Loads the editor and keeps the viewer showing if it fails. Development only.
import type { ReactNode } from "react"
import { GraphicalEditorLoader } from "@graphical/editor/loader"

type HostProps = { children: ReactNode; route: string }

const loadEditor = async () => ({
  GraphicalInstalledEditor: (await import("./installed-editor")).default,
})

export default function DevelopmentEditor(props: HostProps) {
  return <GraphicalEditorLoader<HostProps> loadEditor={loadEditor} {...props} />
}

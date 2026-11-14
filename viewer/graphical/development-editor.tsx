// Loads the editor and keeps the viewer showing if it fails. Development only.
import { GraphicalEditorLoader } from "@graphical/editor/loader"

import type { HostProps } from "./editor-root"

const loadEditor = async () => ({
  GraphicalInstalledEditor: (await import("./installed-editor")).default,
})

export default function DevelopmentEditor(props: HostProps) {
  return <GraphicalEditorLoader<HostProps> loadEditor={loadEditor} {...props} />
}

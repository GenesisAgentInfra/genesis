// The viewer's root. Under `npm run dev`, in a checkout that has Graphical's editor
// installed (a paid package; see the README), the editor goes around it. The page
// `genesis map render` writes never carries it: no editor, no editor styles, no network.
import { useEffect, useState, type ComponentType, type ReactNode } from "react"

type HostProps = { children: ReactNode; route: string }

// Named by pattern rather than imported, so a checkout without the package type-checks
// and builds without ever opening the file that needs it.
const loadDevelopmentEditor =
  import.meta.env.DEV && __GRAPHICAL_EDITOR__
    ? import.meta.glob<{ default: ComponentType<HostProps> }>(
        "./development-editor.tsx"
      )["./development-editor.tsx"]
    : null

export default function EditorRoot(props: HostProps) {
  const [Editor, setEditor] = useState<ComponentType<HostProps> | null>(null)
  useEffect(() => {
    if (!loadDevelopmentEditor) return
    let active = true
    void loadDevelopmentEditor().then(
      ({ default: editor }) => {
        if (active) setEditor(() => editor)
      },
      (error) => {
        if (active)
          console.error("Graphical shell unavailable; app retained.", error)
      }
    )
    return () => {
      active = false
    }
  }, [])
  return Editor ? <Editor {...props} /> : props.children
}

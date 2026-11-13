// Graphical: lets the viewer's own shortcuts step aside for the development editor.
// No editor import lives here; the development adapter registers the check.

type Interaction = {
  target: EventTarget | null
  composedPath?: () => EventTarget[]
}
type Boundary = (event: Interaction) => boolean

let boundary: Boundary | undefined

/** Whether an event belongs to the editor; always false outside development. */
export function isEditorInteraction(event: Interaction) {
  return boundary?.(event) ?? false
}

export function registerEditorInteraction(next: Boundary) {
  boundary = next
  return () => {
    if (boundary === next) boundary = undefined
  }
}

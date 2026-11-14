import * as React from "react"

/**
 * Light or dark. The page opens light, whatever the system shows; once the reader switches
 * to dark, that is kept in the browser until they switch back. index.html sets the same
 * attribute before the first paint, so a kept choice never flashes the other rendition.
 */

type Theme = "light" | "dark"

const KEY = "genesis:theme"

function kept(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light"
  } catch {
    return "light"
  }
}

export function useTheme() {
  const [theme, setTheme] = React.useState(kept)
  React.useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      // Light is where the page starts, so only dark needs keeping.
      if (theme === "dark") localStorage.setItem(KEY, theme)
      else localStorage.removeItem(KEY)
    } catch {
      // Nothing to keep it in: the choice lasts as long as the page stays open.
    }
  }, [theme])
  const toggle = React.useCallback(
    () => setTheme((before) => (before === "dark" ? "light" : "dark")),
    []
  )
  return { theme, setTheme, toggle }
}

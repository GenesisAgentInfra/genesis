import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import EditorRoot from "../graphical/editor-root"
import { App } from "./App"
import { TooltipProvider } from "@/components/ui/tooltip"
import { buildModel } from "./model"
import { STRINGS, detectLang } from "./i18n"
import type { Payload } from "./types"

/** The CLI writes the session's data into this element; nothing is fetched in production. */
function embedded(): Payload | null {
  const text = document.getElementById("genesis-data")?.textContent?.trim()
  if (!text || text === "null") return null
  return JSON.parse(text) as Payload
}

async function load(): Promise<Payload | null> {
  const payload = embedded()
  if (payload || !import.meta.env.DEV) return payload
  // `npm run dev` only: pick a sample with ?sample=<name> (files in viewer/dev/).
  const name = new URLSearchParams(location.search).get("sample") ?? "expense"
  const response = await fetch(`/dev/sample-${name}.json`)
  return response.ok ? ((await response.json()) as Payload) : null
}

const root = createRoot(document.getElementById("root")!)
load().then((payload) => {
  if (!payload) {
    const t =
      STRINGS[detectLang([navigator.language.startsWith("zh") ? "中文" : "en"])]
    root.render(
      <p className="p-[calc(var(--space-xxl)*4/3)] text-body-m text-ink-2">
        {t.noData}
      </p>
    )
    return
  }
  root.render(
    <StrictMode>
      <TooltipProvider delay={150}>
        {/* Graphical's editor wraps the viewer in development; the built page is the
            viewer alone. */}
        <EditorRoot route={`${location.pathname}${location.search}`}>
          <App model={buildModel(payload)} />
        </EditorRoot>
      </TooltipProvider>
    </StrictMode>
  )
})

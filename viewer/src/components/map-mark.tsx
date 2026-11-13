import markDark from "@/assets/genesis-mark-dark.svg"
import type { Strings } from "@/i18n"
import type { Model } from "@/model"

/**
 * With no report to walk there is no headline, so this stands in its place: the mark and
 * the size of the map. It only says; opening a module and closing it again is the frame's
 * own button.
 */
export function MapMark({ model, t }: { model: Model; t: Strings }) {
  const flows = model.modules.reduce((sum, item) => sum + item.flows.length, 0)
  return (
    <div className="pointer-events-auto flex h-8 max-w-full min-w-0 items-center gap-1.5 rounded-full bg-card px-3 text-[13px] leading-5 text-ink-3 shadow-[var(--shadow-float)] ring-1 ring-line">
      <img
        src={markDark}
        alt="Genesis"
        className="mr-0.5 h-4 w-auto shrink-0 dark:invert"
      />
      <span className="truncate text-ink-2">
        {t.mapSize(model.modules.length, flows)}
      </span>
      {model.counts.partial && (
        <span className="hidden shrink-0 sm:inline">· {t.partial}</span>
      )}
    </div>
  )
}

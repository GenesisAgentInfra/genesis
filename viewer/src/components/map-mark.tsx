import markDark from "@/assets/genesis-mark-dark.svg"
import type { Strings } from "@/i18n"
import type { Model } from "@/model"

/**
 * Identify the viewer and, when there is no report, give the size of the map.
 */
export function MapMark({ model, t }: { model: Model; t: Strings }) {
  const flows = model.modules.reduce((sum, item) => sum + item.flows.length, 0)
  return (
    <div className="flex min-w-0 items-center gap-m text-body-m">
      <img
        src={markDark}
        alt="Genesis"
        className="h-5 w-auto shrink-0 dark:invert"
      />
      <span aria-hidden className="hidden font-heavy text-ink sm:inline">
        Genesis
      </span>
      {!model.hasReport && (
        <span className="truncate edge-l-s border-line pl-m text-body-s text-ink-2">
          {t.mapSize(model.modules.length, flows)}
          {model.counts.partial && ` · ${t.partial}`}
        </span>
      )}
    </div>
  )
}

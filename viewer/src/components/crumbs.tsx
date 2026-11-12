import markDark from "@/assets/genesis-mark-dark.svg"
import type { Strings } from "@/i18n"
import type { Model } from "@/model"

/**
 * Where the reader is on the atlas: the whole map, or one module brought into focus. With no
 * report to walk it also carries the mark and the size of the map.
 */
export function Crumbs({
  model,
  t,
  module,
  onOverview,
}: {
  model: Model
  t: Strings
  /** The module in focus, if any. */
  module?: string
  onOverview: () => void
}) {
  const bare = !model.hasReport
  const flows = model.modules.reduce((sum, item) => sum + item.flows.length, 0)
  return (
    <nav
      aria-label={t.overview}
      className="pointer-events-auto flex h-8 max-w-full min-w-0 items-center gap-1.5 rounded-full bg-card px-3 text-[12.5px] leading-5 text-ink-3 shadow-[var(--shadow-float)] ring-1 ring-line"
    >
      {bare && (
        <img
          src={markDark}
          alt="Genesis"
          className="mr-0.5 h-4 w-auto shrink-0"
        />
      )}
      {module ? (
        <>
          <button
            type="button"
            onClick={onOverview}
            className="shrink-0 rounded-sm text-ink-2 hover:text-ink"
          >
            {t.overview}
          </button>
          <span aria-hidden className="text-ink-3/60">
            /
          </span>
          <span className="min-w-0 truncate font-medium text-ink">
            {module}
          </span>
        </>
      ) : (
        <>
          <span className="shrink-0 font-medium text-ink">{t.overview}</span>
          <span className="truncate">
            · {t.mapSize(model.modules.length, flows)}
          </span>
        </>
      )}
      {bare && model.counts.partial && (
        <span className="hidden shrink-0 sm:inline">· {t.partial}</span>
      )}
    </nav>
  )
}

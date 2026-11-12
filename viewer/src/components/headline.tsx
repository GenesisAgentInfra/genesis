import * as React from "react"
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  CircleCheck,
  ListChecks,
  TriangleAlert,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { NumberDisc, StatusMark } from "@/canvas/step-node"
import { cn } from "@/lib/utils"
import { localizeLimitation, localizeReason, type Strings } from "@/i18n"
import { TONES, type Filter, type Model, type Stop } from "@/model"

const MAX_FILES = 8

/** Where in the product this change lands, in one sentence. */
export function overviewText(model: Model, t: Strings): string {
  const flows = [...model.stopsOn.keys()].filter(
    (id) => !model.flowById.get(id)?.removed
  )
  const modules = [
    ...new Set(flows.map((id) => model.moduleOf.get(id)).filter(Boolean)),
  ]
  const names = modules
    .map((module) => module!.name)
    .filter((name): name is string => Boolean(name))
  const apart = model.stops.filter(
    (stop) => stop.kind === "off_map" || stop.kind === "removed_flow"
  ).length
  // Flows no change sits on, though their code leads to one.
  const passing = new Set(
    model.stops
      .flatMap((stop) => stop.maybe)
      .filter((id) => !flows.includes(id))
  ).size
  return t.overviewSentence(names, modules.length, flows.length, apart, passing)
}

/** What a stop is called in the list, and where on the map it sits. */
function stopText(
  stop: Stop,
  model: Model,
  t: Strings
): { title: string; where: string } {
  const flow = stop.flowId
    ? model.flowById.get(stop.flowId)?.flow.name
    : undefined
  if (stop.kind === "removed_flow") {
    const said = stop.change?.explanation?.summary
    return {
      title: said ?? flow ?? t.removedFlowRow,
      // The flow's name is said once: as the title when nothing else names the change.
      where: [said ? flow : undefined, t.removedFlowRow]
        .filter(Boolean)
        .join(" · "),
    }
  }
  return {
    title:
      stop.change?.explanation?.summary ??
      (stop.change ? t.changeKind[stop.change.kind] : ""),
    where: stop.kind === "off_map" ? t.offMapCard : (flow ?? ""),
  }
}

function InfoTip({
  label,
  warn,
  children,
}: {
  label: React.ReactNode
  /** Something the map does not show: said with a warning glyph, not in passing. */
  warn?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(false)
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "inline-flex cursor-help items-center gap-1 rounded-sm underline decoration-ink-3/40 decoration-dotted underline-offset-[3px] hover:text-ink",
            warn && "text-ink-2"
          )}
        >
          {warn && <TriangleAlert aria-hidden className="size-3.5 text-warn" />}
          {label}
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        align="start"
        sideOffset={6}
        className="max-w-[360px] flex-col items-start gap-1 py-2"
      >
        {children}
      </TooltipContent>
    </Tooltip>
  )
}

/**
 * What the reader looks at first: what this change asks of them, where it lands, and the
 * ways through it: one kind of change at a time, one change after another, or the list.
 */
export function Headline({
  model,
  t,
  narrow,
  compact,
  picked,
  walk,
  filter,
  reviewed,
  onFilter,
  onToggleReviewed,
  onPick,
  onStep,
}: {
  model: Model
  t: Strings
  narrow: boolean
  /** On a phone with the panel open only the sentences stay. */
  compact: boolean
  /** The change on show. */
  picked?: number
  /** The stops the stepper walks, in order: all of them, or the kind the reader chose. */
  walk: number[]
  filter?: Filter
  reviewed: Set<number>
  onFilter: (filter?: Filter) => void
  onToggleReviewed: (no: number) => void
  onPick?: (no: number) => void
  onStep?: (by: number) => void
}) {
  const report = model.payload.report
  const counts = model.counts
  const files = report?.unanalyzed_changes ?? []
  const limits = (
    report ? (report.limitations ?? []) : (model.payload.map.limitations ?? [])
  ).filter((item) => item.affects_completeness)
  const total = model.stops.length
  const [listOpen, setListOpen] = React.useState(false)
  const root = React.useRef<HTMLDivElement>(null)

  // The list folds away when the reader turns to the map.
  React.useEffect(() => {
    if (!listOpen) return
    const away = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setListOpen(false)
    }
    document.addEventListener("pointerdown", away)
    return () => document.removeEventListener("pointerdown", away)
  }, [listOpen])

  const verdict = counts.stops
    ? t.verdictLine(
        counts.newRisks,
        counts.untested,
        counts.unsure,
        counts.stops,
        counts.tested === counts.stops
      )
    : counts.files && !report?.changes?.length
      ? t.filesOnly
      : t.summaryNoChange

  const size: Record<Filter, number> = {
    risk: counts.risky,
    untested: counts.untested,
    unsure: counts.unsure,
    tested: counts.tested,
  }
  const kinds = TONES.filter((tone) => size[tone] > 0)

  const notes: React.ReactNode[] = []
  if (counts.files)
    notes.push(
      <InfoTip key="files" warn label={t.filesNotAnalyzed(counts.files)}>
        <span className="font-medium">{t.unanalyzed}</span>
        {files.slice(0, MAX_FILES).map((item) => (
          <span key={item.path} className="[overflow-wrap:anywhere]">
            <span className="font-mono">{item.path}</span> ·{" "}
            {localizeReason(item.reason, model.lang)}
          </span>
        ))}
        {files.length > MAX_FILES && (
          <span>{t.andMore(files.length - MAX_FILES)}</span>
        )}
      </InfoTip>
    )
  if (counts.tests)
    notes.push(<span key="tests">{t.testsChanged(counts.tests)}</span>)
  if (counts.partial)
    notes.push(
      <InfoTip key="partial" warn label={t.partial}>
        <span className="font-medium">{t.partialHint}</span>
        {limits.map((item, index) => (
          <span key={index} className="[overflow-wrap:anywhere]">
            {localizeLimitation(item, model.lang)}
          </span>
        ))}
      </InfoTip>
    )

  const at = picked ? walk.indexOf(picked) : -1
  const done = model.stops.filter((stop) => reviewed.has(stop.no)).length
  const listed = model.stops.filter((stop) => walk.includes(stop.no))

  return (
    <div
      ref={root}
      className="pointer-events-auto relative"
      onKeyDown={(event) => {
        if (event.key === "Escape" && listOpen) {
          event.stopPropagation()
          setListOpen(false)
        }
      }}
    >
      <div
        className={cn(
          "rounded-[18px] bg-card shadow-[var(--shadow-float)] ring-1 ring-line",
          narrow ? "px-3.5 py-2.5" : "px-4 pt-3 pb-2"
        )}
      >
        <p
          className={cn(
            "font-medium [overflow-wrap:anywhere] text-ink",
            narrow ? "text-[16px] leading-[23px]" : "text-[18px] leading-[26px]"
          )}
        >
          {verdict}
        </p>
        {counts.stops > 0 && (
          <p
            className={cn(
              "mt-0.5 text-[13px] leading-[19px] [overflow-wrap:anywhere] text-ink-2",
              // The second sentence gives way first where room is short.
              compact ? "line-clamp-1" : "line-clamp-2"
            )}
          >
            {overviewText(model, t)}
          </p>
        )}
        {total > 0 && !compact && (
          <div className="mt-2 flex min-w-0 items-center gap-2 border-t border-line pt-2">
            <div
              role="group"
              aria-label={t.filterBy}
              className="flex min-w-0 flex-1 flex-wrap items-center gap-1"
            >
              <Chip
                label={t.filterAll}
                count={`${total}${counts.truncated ? "+" : ""}`}
                active={!filter}
                onClick={() => onFilter(undefined)}
              />
              {kinds.map((tone) => (
                <Chip
                  key={tone}
                  tone={tone}
                  label={t.tone[tone]}
                  count={String(size[tone])}
                  active={filter === tone}
                  onClick={() => onFilter(filter === tone ? undefined : tone)}
                />
              ))}
            </div>
            {onStep && (
              <div className="flex shrink-0 items-center gap-0.5 self-start text-[13px] leading-6 text-ink-2">
                <StepButton
                  label={t.prevChange}
                  keys="←"
                  onClick={() => onStep(-1)}
                >
                  <ChevronLeft />
                </StepButton>
                <span
                  aria-live="polite"
                  className="min-w-[44px] text-center tabular-nums"
                >
                  {at >= 0 ? `${at + 1} / ${walk.length}` : t.stepThrough}
                </span>
                <StepButton
                  label={t.nextChange}
                  keys="→"
                  onClick={() => onStep(1)}
                >
                  <ChevronRight />
                </StepButton>
              </div>
            )}
          </div>
        )}
        {!compact && (total > 0 || notes.length > 0) && (
          <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[13px] leading-5 text-ink-3">
            {total > 0 && onPick && (
              <button
                type="button"
                aria-expanded={listOpen}
                onClick={() => setListOpen((open) => !open)}
                className="-ml-1.5 inline-flex h-6 items-center gap-1 rounded-full px-1.5 text-ink-2 hover:bg-field hover:text-ink"
              >
                {done === total ? (
                  <CircleCheck aria-hidden className="size-3.5 text-ink" />
                ) : (
                  <ListChecks aria-hidden className="size-3.5" />
                )}
                <span className="font-medium">{t.list}</span>
                <span className="text-ink-3 tabular-nums">
                  {done === total
                    ? t.allReviewed(total)
                    : t.reviewedOf(done, total)}
                </span>
                <ChevronDown
                  aria-hidden
                  className={cn(
                    "size-3.5 transition-transform duration-160",
                    listOpen && "rotate-180"
                  )}
                />
              </button>
            )}
            {notes.length > 0 && (
              <div className="ml-auto flex min-w-0 flex-wrap items-center gap-x-1.5">
                {notes.map((note, index) => (
                  <React.Fragment key={index}>
                    {index > 0 && <span aria-hidden>·</span>}
                    {note}
                  </React.Fragment>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {listOpen && !compact && onPick && (
        // Over the map, under the headline: it takes no room from the canvas and folds
        // away as soon as a change is picked.
        <div className="absolute top-full left-0 z-20 mt-2 w-full rounded-[18px] bg-card p-1.5 shadow-[var(--shadow-float)] ring-1 ring-line fade-in">
          <ol
            aria-label={t.listTitle}
            className="flex max-h-[min(52dvh,440px)] [scrollbar-width:thin] flex-col gap-px overflow-y-auto"
          >
            {listed.map((stop) => {
              const text = stopText(stop, model, t)
              const seen = reviewed.has(stop.no)
              return (
                <li
                  key={stop.no}
                  data-tone={stop.tone ?? "unsure"}
                  className={cn(
                    "flex items-center gap-1 rounded-[12px] pr-1 transition-colors duration-160 hover:bg-field",
                    picked === stop.no && "bg-field"
                  )}
                >
                  <button
                    type="button"
                    aria-current={picked === stop.no ? "true" : undefined}
                    onClick={() => {
                      setListOpen(false)
                      onPick(stop.no)
                    }}
                    className="flex min-w-0 flex-1 items-start gap-2.5 rounded-[12px] py-1.5 pr-1 pl-2 text-left"
                  >
                    <NumberDisc no={stop.no} seen={seen} className="mt-0.5" />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span
                        className={cn(
                          "truncate text-[14px] leading-5",
                          seen ? "text-ink-2" : "text-ink"
                        )}
                      >
                        {text.title}
                      </span>
                      <span className="flex min-w-0 items-center gap-1.5 text-[12px] leading-4 text-ink-3">
                        <span className="truncate">{text.where}</span>
                        {stop.risky && (
                          <span className="shrink-0 rounded-[5px] bg-risk-bg px-1 font-medium text-risk-ink">
                            {t.newRisk}
                          </span>
                        )}
                        {stop.status && (
                          <StatusMark
                            status={stop.status}
                            label={t.status[stop.status]}
                            className="text-ink-2"
                          />
                        )}
                      </span>
                    </span>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-pressed={seen}
                    aria-label={`${t.changeNo(stop.no)}: ${seen ? t.unmarkReviewed : t.markReviewed}`}
                    title={seen ? t.unmarkReviewed : t.markReviewed}
                    onClick={() => onToggleReviewed(stop.no)}
                    className="shrink-0 rounded-full"
                  >
                    {seen ? (
                      <CircleCheck className="text-ink" />
                    ) : (
                      <Circle className="text-ink-3/70" />
                    )}
                  </Button>
                </li>
              )
            })}
          </ol>
          {!narrow && (
            <p className="px-2 pt-1.5 pb-0.5 text-[12px] leading-4 text-ink-3">
              {t.listHint}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/** One kind of change and how many there are; picking it narrows the page down to them. */
function Chip({
  label,
  count,
  tone,
  active,
  onClick,
}: {
  label: string
  count: string
  tone?: Filter
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-tone={tone}
      onClick={onClick}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[13px] leading-5 whitespace-nowrap transition-colors duration-160",
        active
          ? "bg-field font-medium text-ink ring-1 ring-ink-3/40"
          : "text-ink-2 hover:bg-field hover:text-ink"
      )}
    >
      {tone && (
        <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-tone" />
      )}
      {label}
      <span className={cn("tabular-nums", !active && "text-ink-3")}>
        {count}
      </span>
    </button>
  )
}

/** A stepper arrow that says which key does the same. */
function StepButton({
  label,
  keys,
  onClick,
  children,
}: {
  label: string
  keys: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={label}
          aria-keyshortcuts={keys === "←" ? "ArrowLeft" : "ArrowRight"}
          onClick={onClick}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        {label}
        <kbd
          data-slot="kbd"
          className="rounded-sm bg-background/20 px-1 font-sans"
        >
          {keys}
        </kbd>
      </TooltipContent>
    </Tooltip>
  )
}

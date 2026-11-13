import * as React from "react"
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  TriangleAlert,
} from "lucide-react"

import { ReviewBadge } from "@/components/review-badge"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { NumberDisc } from "@/canvas/step-node"
import { cn } from "@/lib/utils"
import { localizeLimitation, localizeReason, type Strings } from "@/i18n"
import type { Model, Stop } from "@/model"
import { shortSummary } from "@/presentation"

const MAX_FILES = 8

/** One concise description per change; its evidence lives in the detail panel. */
function stopTitle(stop: Stop, model: Model, t: Strings): string {
  if (stop.kind === "removed_flow") {
    return (
      stop.change?.explanation?.summary ??
      (stop.flowId ? model.flowById.get(stop.flowId)?.flow.name : undefined) ??
      t.removedFlowRow
    )
  }
  return stop.change
    ? (shortSummary(stop.change) ?? t.changeKind[stop.change.kind])
    : ""
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
 * A quiet entry to the change list. Only the change descriptions appear in the list;
 * incomplete analysis remains visible beside the compact controls.
 */
export function Headline({
  model,
  t,
  compact,
  picked,
  walk,
  onPick,
  onStep,
}: {
  model: Model
  t: Strings
  /** Hide secondary controls alongside a narrow detail panel. */
  compact: boolean
  /** The change on show. */
  picked?: number
  /** The changes the stepper walks, in order. */
  walk: number[]
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
  const trigger = React.useRef<HTMLButtonElement>(null)

  // The list folds away when the reader turns to the map.
  React.useEffect(() => {
    if (!listOpen) return
    const away = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setListOpen(false)
    }
    document.addEventListener("pointerdown", away)
    return () => document.removeEventListener("pointerdown", away)
  }, [listOpen])

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

  return (
    <div
      ref={root}
      className="pointer-events-auto relative"
      onKeyDown={(event) => {
        if (event.key === "Escape" && listOpen) {
          event.stopPropagation()
          setListOpen(false)
          trigger.current?.focus()
        }
      }}
    >
      <div className="flex w-fit items-center gap-2">
        {total > 0 && onPick ? (
          <div className="inline-flex items-center gap-1 rounded-full bg-card p-1 shadow-[var(--shadow-node)] ring-1 ring-line">
            <button
              ref={trigger}
              type="button"
              aria-expanded={listOpen}
              aria-label={t.openChanges}
              onClick={() => setListOpen((open) => !open)}
              className="inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[13px] text-ink-2 hover:bg-field hover:text-ink"
            >
              <ListChecks aria-hidden className="size-3.5" />
              <span>{t.openChanges}</span>
              <span className="text-ink-3 tabular-nums">{total}</span>
              <ChevronDown
                aria-hidden
                className={cn(
                  "size-3.5 transition-transform duration-160",
                  listOpen && "rotate-180"
                )}
              />
            </button>
            {onStep && !compact && (
              <div className="flex items-center gap-0.5 border-l border-line pl-1 text-[12px] text-ink-2">
                <StepButton
                  label={t.prevChange}
                  keys="←"
                  onClick={() => {
                    setListOpen(false)
                    onStep(-1)
                  }}
                >
                  <ChevronLeft />
                </StepButton>
                {at >= 0 && (
                  <span
                    aria-live="polite"
                    className="min-w-8 text-center tabular-nums"
                  >
                    {at + 1} / {walk.length}
                  </span>
                )}
                <StepButton
                  label={t.nextChange}
                  keys="→"
                  onClick={() => {
                    setListOpen(false)
                    onStep(1)
                  }}
                >
                  <ChevronRight />
                </StepButton>
              </div>
            )}
          </div>
        ) : (
          <span className="rounded-full bg-card px-3 py-2 text-[13px] text-ink-2 ring-1 ring-line">
            {counts.files ? t.filesOnly : t.summaryNoChange}
          </span>
        )}
        {(counts.files > 0 || counts.partial) && (
          <div className="flex items-center gap-2 rounded-full bg-card px-3 py-2 text-[12px] text-ink-2 ring-1 ring-line">
            {notes}
          </div>
        )}
      </div>

      {listOpen && !compact && onPick && (
        // Over the map, under the headline: it takes no room from the canvas and folds
        // away as soon as a change is picked.
        <div className="absolute top-full left-0 z-20 mt-2 w-[360px] max-w-[calc(100vw-32px)] rounded-[14px] bg-card p-1.5 shadow-[var(--shadow-float)] ring-1 ring-line fade-in">
          <ol
            aria-label={t.listTitle}
            className="flex max-h-[min(52dvh,440px)] [scrollbar-width:thin] flex-col gap-0.5 overflow-y-auto"
          >
            {model.stops.map((stop) => (
              <li key={stop.no} data-tone={stop.tone ?? "unsure"}>
                <button
                  type="button"
                  aria-current={picked === stop.no ? "true" : undefined}
                  onClick={() => {
                    setListOpen(false)
                    trigger.current?.focus()
                    onPick(stop.no)
                  }}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2.5 text-left transition-colors duration-160 hover:bg-field",
                    picked === stop.no && "bg-field"
                  )}
                >
                  <NumberDisc no={stop.no} />
                  <span className="min-w-0 flex-1 text-[14px] leading-5 text-ink">
                    {stopTitle(stop, model, t)}
                  </span>
                  <ReviewBadge risky={stop.risky} status={stop.status} t={t} />
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
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

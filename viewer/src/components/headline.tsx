import * as React from "react"
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ListChecks,
} from "lucide-react"

import { CommitRange } from "@/components/commit-range"
import { ReviewBadge } from "@/components/review-badge"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { NumberDisc } from "@/canvas/step-node"
import { cn } from "@/lib/utils"
import type { Strings } from "@/i18n"
import type { Model, Stop } from "@/model"
import { shortSummary } from "@/presentation"

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

/**
 * A quiet entry to the change list. Only the change descriptions appear in the list;
 * the canvas stays dedicated to the business flows.
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
  const counts = model.counts
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
      <div className="flex w-fit items-center gap-m">
        {total > 0 && onPick ? (
          <div className="inline-flex items-center gap-xs corner-full bg-card p-xs shadow-[var(--shadow-node)] ring-1 ring-line">
            <button
              ref={trigger}
              type="button"
              aria-expanded={listOpen}
              aria-label={t.openChanges}
              onClick={() => setListOpen((open) => !open)}
              className={cn(
                "inline-flex h-7 items-center gap-s",
                "corner-full px-l",
                "text-body-m",
                "text-ink-2",
                "hover:bg-field hover:text-ink"
              )}
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
              <div
                className={cn(
                  "flex items-center gap-xxs",
                  "edge-l-m pl-xs",
                  "text-body-s",
                  "border-line text-ink-2"
                )}
              >
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
          <span className="corner-full bg-card px-l py-m text-body-m text-ink-2 ring-1 ring-line">
            {counts.files ? t.filesOnly : t.summaryNoChange}
          </span>
        )}
        {!compact && <CommitRange model={model} t={t} />}
      </div>

      {listOpen && !compact && onPick && (
        // Over the map, under the headline: it takes no room from the canvas and folds
        // away as soon as a change is picked.
        <div className="fade-in absolute top-full left-0 z-20 mt-m w-[360px] max-w-[calc(100vw-32px)] corner-l bg-card p-s shadow-[var(--shadow-float)] ring-1 ring-line">
          <ol
            aria-label={t.listTitle}
            className="flex max-h-[min(52dvh,440px)] [scrollbar-width:thin] flex-col gap-xxs overflow-y-auto"
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
                    "flex w-full items-center gap-l",
                    "corner-m px-l py-l",
                    "text-left",
                    "transition-colors duration-160",
                    "hover:bg-field",
                    picked === stop.no && "bg-field"
                  )}
                >
                  <NumberDisc no={stop.no} />
                  <span className="min-w-0 flex-1 text-body-m text-ink">
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
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={label}
            aria-keyshortcuts={keys === "←" ? "ArrowLeft" : "ArrowRight"}
            onClick={onClick}
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        {label}
        <kbd
          data-slot="kbd"
          className="corner-xs bg-background/20 px-xs font-body"
        >
          {keys}
        </kbd>
      </TooltipContent>
    </Tooltip>
  )
}

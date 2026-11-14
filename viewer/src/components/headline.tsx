import * as React from "react"
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ListChecks,
} from "lucide-react"

import { ReviewBadge } from "@/components/review-badge"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
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
  const trigger = React.useRef<HTMLButtonElement>(null)
  const open = listOpen && !compact
  const pick = (no: number) => {
    setListOpen(false)
    trigger.current?.focus()
    onPick?.(no)
  }

  const at = picked ? walk.indexOf(picked) : -1

  return (
    <Popover open={open} onOpenChange={setListOpen}>
      <div className="flex w-fit items-center">
        {total > 0 && onPick ? (
          <div className="inline-flex items-center gap-1">
            <PopoverTrigger
              ref={trigger}
              aria-label={t.openChanges}
              render={<Button variant="secondary" size="sm" />}
            >
              <ListChecks aria-hidden className="size-3.5" />
              <span>{t.openChanges}</span>
              <span className="text-ink-2 tabular-nums">{total}</span>
              <ChevronDown
                aria-hidden
                className={cn(
                  "size-3.5 transition-transform duration-(--motion-duration) ease-(--motion-easing)",
                  open && "rotate-180"
                )}
              />
            </PopoverTrigger>
            {onStep && !compact && (
              <div className="flex items-center gap-xxs text-body-s text-ink-2">
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
          <span className="text-body-s text-ink-2">
            {counts.files ? t.filesOnly : t.summaryNoChange}
          </span>
        )}
      </div>

      {onPick && (
        <PopoverContent
          aria-label={t.listTitle}
          align="start"
          sideOffset={8}
          className="w-[360px] max-w-(--available-width)"
          initialFocus={(interaction) => interaction === "keyboard"}
        >
          <ol
            aria-label={t.listTitle}
            className="flex max-h-[min(52dvh,440px)] [scrollbar-width:thin] flex-col gap-xxs overflow-y-auto"
          >
            {model.stops.map((stop) => (
              <li key={stop.no} data-tone={stop.tone ?? "unsure"}>
                <Button
                  type="button"
                  variant="ghost"
                  aria-current={picked === stop.no ? "true" : undefined}
                  onClick={() => pick(stop.no)}
                  className="h-auto w-full justify-start gap-l rounded-2xl px-l py-l text-left whitespace-normal aria-[current=true]:bg-(--selection-bg)"
                >
                  <NumberDisc no={stop.no} />
                  <span className="min-w-0 flex-1 text-body-m text-ink">
                    {stopTitle(stop, model, t)}
                  </span>
                  <ReviewBadge risky={stop.risky} status={stop.status} t={t} />
                </Button>
              </li>
            ))}
          </ol>
        </PopoverContent>
      )}
    </Popover>
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
        <kbd data-slot="kbd" className="bg-background/20 px-xs font-body">
          {keys}
        </kbd>
      </TooltipContent>
    </Tooltip>
  )
}

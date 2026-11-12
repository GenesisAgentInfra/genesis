import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { localizeLimitation, localizeReason, type Strings } from "@/i18n"
import type { Model } from "@/model"

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
  return t.overviewSentence(names, modules.length, flows.length, apart)
}

function InfoTip({
  label,
  children,
}: {
  label: React.ReactNode
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(false)
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="cursor-help rounded-sm underline decoration-ink-3/40 decoration-dotted underline-offset-[3px] hover:text-ink-2"
        >
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

/** What the reader looks at first: where this change lands and what needs attention. */
export function Headline({
  model,
  t,
  narrow,
  compact,
  picked,
  onPick,
}: {
  model: Model
  t: Strings
  narrow: boolean
  /** On a phone with the panel open only the sentence stays. */
  compact: boolean
  /** The change on show, and the way to move to another one. */
  picked?: number
  onPick?: (no: number) => void
}) {
  const report = model.payload.report
  const counts = model.counts
  const files = report?.unanalyzed_changes ?? []
  const limits = (
    report ? (report.limitations ?? []) : (model.payload.map.limitations ?? [])
  ).filter((item) => item.affects_completeness)

  const segments: React.ReactNode[] = []
  if (counts.stops)
    segments.push(
      <span key="total">{t.totalChanges(counts.stops, counts.truncated)}</span>
    )
  if (counts.untested)
    segments.push(
      <span key="untested">{t.untestedCount(counts.untested)}</span>
    )
  if (counts.newRisks)
    segments.push(<span key="risks">{t.newRiskCount(counts.newRisks)}</span>)
  if (counts.files)
    segments.push(
      <InfoTip key="files" label={t.filesNotAnalyzed(counts.files)}>
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
    segments.push(<span key="tests">{t.testsChanged(counts.tests)}</span>)
  if (counts.partial)
    segments.push(
      <InfoTip key="partial" label={t.partial}>
        <span className="font-medium">{t.partialHint}</span>
        {limits.map((item, index) => (
          <span key={index} className="[overflow-wrap:anywhere]">
            {localizeLimitation(item, model.lang)}
          </span>
        ))}
      </InfoTip>
    )

  const sentence = counts.stops
    ? overviewText(model, t)
    : counts.files && !report?.changes?.length
      ? t.filesOnly
      : t.summaryNoChange

  const total = model.stops.length
  const step = (by: number) => {
    const from = picked ?? (by > 0 ? 0 : 1)
    onPick?.(((from - 1 + by + total) % total) + 1)
  }

  return (
    <div
      className={cn(
        "pointer-events-auto rounded-[18px] bg-card shadow-[var(--shadow-float)] ring-1 ring-line",
        narrow ? "px-3.5 py-2.5" : "px-4 pt-3 pb-2"
      )}
    >
      <p
        className={cn(
          "line-clamp-2 font-medium [overflow-wrap:anywhere] text-ink",
          narrow ? "text-[16px] leading-[23px]" : "text-[18px] leading-[26px]"
        )}
      >
        {sentence}
      </p>
      {segments.length > 0 && !compact && (
        <div className="mt-1.5 flex min-w-0 items-center gap-3 border-t border-line pt-1.5 text-[12.5px] leading-5 text-ink-3">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-1.5">
            {segments.map((segment, index) => (
              <React.Fragment key={index}>
                {index > 0 && <span aria-hidden>·</span>}
                {segment}
              </React.Fragment>
            ))}
          </div>
          {onPick && total > 0 && (
            <div className="flex shrink-0 items-center gap-0.5 text-ink-2">
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t.prevChange}
                onClick={() => step(-1)}
              >
                <ChevronLeft />
              </Button>
              <span
                aria-live="polite"
                className="min-w-[44px] text-center tabular-nums"
              >
                {picked ? `${picked} / ${total}` : t.stepThrough}
              </span>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t.nextChange}
                onClick={() => step(1)}
              >
                <ChevronRight />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

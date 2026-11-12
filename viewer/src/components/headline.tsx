import * as React from "react"

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
}: {
  model: Model
  t: Strings
  narrow: boolean
  /** On a phone with the panel open only the sentence stays. */
  compact: boolean
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

  return (
    <div
      className={cn(
        "pointer-events-auto rounded-[18px] bg-card shadow-[var(--shadow-float)] ring-1 ring-line",
        narrow ? "px-3.5 py-2.5" : "px-4 pt-3 pb-2.5"
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
        <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-1.5 border-t border-line pt-2 text-[12.5px] leading-5 text-ink-3">
          {segments.map((segment, index) => (
            <React.Fragment key={index}>
              {index > 0 && <span aria-hidden>·</span>}
              {segment}
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  )
}

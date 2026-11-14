import * as React from "react"
import { Check, ChevronRight, Copy, Play, X } from "lucide-react"

import githubMarkDark from "@/assets/github-mark-dark.svg"
import githubMarkLight from "@/assets/github-mark-light.svg"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardHeader,
  CardFooter,
  CardTitle,
} from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Evidence } from "@/components/evidence"
import { ReviewBadge } from "@/components/review-badge"
import { KindTile, NumberDisc, StatusMark } from "@/canvas/step-node"
import { localizeNote, type Strings } from "@/i18n"
import { statusOf, type Coupon, type FlowView, type Model } from "@/model"
import type { MapFinding, MapStep, StepContract } from "@/types"
import { coverageKind, sortAlerts, sourceLinkOf } from "@/presentation"

export type PanelSubject =
  | {
      type: "step"
      step: MapStep
      view?: FlowView
      ghost?: boolean
      coupons: Coupon[]
    }
  | { type: "offMap"; coupons: Coupon[] }
  | { type: "removedFlow"; name: string; code: boolean; coupons: Coupon[] }

interface PanelProps {
  model: Model
  t: Strings
  subject: PanelSubject
  focus?: number
  onWalk?: () => void
  onNext?: () => void
  onClose: () => void
}

/** A stable inspector: explanation and structured data each get their own reading space. */
export function DetailPanel({
  model,
  t,
  subject,
  focus,
  onWalk,
  onNext,
  onClose,
}: PanelProps) {
  const coupons = subject.coupons
  const step = subject.type === "step" ? subject.step : undefined
  const active = coupons.find((coupon) => coupon.no === focus) ?? coupons[0]
  const others = coupons.filter((coupon) => coupon !== active)
  const findings =
    subject.type === "step" && subject.view
      ? subject.view.findings.filter((finding) =>
          (step?.finding_ids ?? []).includes(finding.finding_id)
        )
      : []
  const carried = new Set(
    coupons.flatMap((coupon) => coupon.change.finding_ids ?? [])
  )
  const otherFindings = findings.filter(
    (finding) => !carried.has(finding.finding_id)
  )
  const title =
    subject.type === "step"
      ? step!.name
      : subject.type === "offMap"
        ? t.offMap
        : subject.name
  const removed =
    subject.type === "removedFlow" || (subject.type === "step" && subject.ghost)
  const evidenceIds = [
    ...new Set([
      ...(active?.change.after?.evidence_ids ??
        active?.change.before?.evidence_ids ??
        []),
      ...(step?.evidence_ids ?? []),
    ]),
  ]
  const source = sourceLinkOf(model.payload, evidenceIds)
  const sourceLabel = source?.exact ? t.githubCode : t.githubCommitted
  return (
    <Card className="h-full max-h-[inherit] min-h-0 gap-0 py-0">
      <CardHeader className="shrink-0 gap-m px-xxl pt-xxl pb-l">
        <div className="flex min-w-0 items-start gap-l">
          {step && <KindTile kind={step.kind} small />}
          <CardTitle className="flex min-w-0 flex-1 flex-wrap items-center gap-x-m gap-y-xs">
            <h2 className="min-w-0 text-body-l [overflow-wrap:anywhere]">
              {title}
            </h2>
            {active ? (
              <ReviewBadge
                risky={active.risky}
                status={statusOf(active.change.tests)}
                t={t}
              />
            ) : findings.length ? (
              <ReviewBadge risky t={t} />
            ) : (
              <Badge variant="secondary">
                {removed ? t.removed : step ? t.stepKind[step.kind] : t.offMap}
              </Badge>
            )}
          </CardTitle>
        </div>
        <CardAction className="-mt-xxs -mr-xs flex items-center">
          {source && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <a
                    aria-label={sourceLabel}
                    className={buttonVariants({
                      variant: "ghost",
                      size: "icon-sm",
                    })}
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
              >
                <img
                  src={githubMarkDark}
                  alt=""
                  className="size-4 object-contain dark:hidden"
                />
                <img
                  src={githubMarkLight}
                  alt=""
                  className="hidden size-4 object-contain dark:block"
                />
              </TooltipTrigger>
              <TooltipContent side="bottom">{sourceLabel}</TooltipContent>
            </Tooltip>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t.close}
          >
            <X />
          </Button>
        </CardAction>
      </CardHeader>
      <Tabs defaultValue="overview" className="min-h-0 flex-1 gap-0">
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-m px-xxl">
          <TabsList>
            <TabsTrigger value="overview">{t.changeOverview}</TabsTrigger>
            {step && !removed && (
              <TabsTrigger value="contract">{t.ioContract}</TabsTrigger>
            )}
          </TabsList>
          {!source && onWalk && (
            <Button variant="outline" size="sm" onClick={onWalk}>
              <Play data-icon="inline-start" />
              {t.runFlow}
            </Button>
          )}
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="min-w-0 p-xxl">
            <TabsContent value="overview" className="min-w-0 space-y-xl">
              {active && (
                <ChangeDetail
                  coupon={active}
                  model={model}
                  t={t}
                  evidenceIds={step?.evidence_ids ?? []}
                />
              )}
              <FindingDetails findings={otherFindings} />
              {others.length > 0 && (
                <Collapsible>
                  <CollapsibleTrigger
                    render={<Button variant="secondary" size="sm" />}
                    className="group/other-changes w-full justify-between"
                  >
                    {t.moreChanges(others.length)}
                    <ChevronRight
                      aria-hidden
                      data-icon="inline-end"
                      className="size-3.5 transition-transform duration-(--motion-duration) group-data-panel-open/other-changes:rotate-90"
                    />
                  </CollapsibleTrigger>
                  <CollapsibleContent className={COLLAPSIBLE_MOTION}>
                    <div className="space-y-xxl pt-xl">
                      {others.map((coupon) => (
                        <ChangeDetail
                          key={`${coupon.no}-${coupon.primary}`}
                          coupon={coupon}
                          model={model}
                          t={t}
                          evidenceIds={step?.evidence_ids ?? []}
                        />
                      ))}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              )}
              {!active && (
                <>
                  <p className="text-body-m [overflow-wrap:anywhere] text-ink-2">
                    {removed ? t.flowGone : (step?.reason ?? t.unchangedStep)}
                  </p>
                  {(!source || !source.exact) && (
                    <Evidence ids={evidenceIds} model={model} t={t} />
                  )}
                </>
              )}
            </TabsContent>
            {step && !removed && (
              <TabsContent value="contract" className="min-w-0">
                <ContractDetail contract={step.contract} t={t} />
              </TabsContent>
            )}
          </div>
        </ScrollArea>
      </Tabs>
      {onNext && (
        <CardFooter className="shrink-0 justify-end px-xxl py-l">
          <Button variant="secondary" size="sm" onClick={onNext}>
            {t.nextChange}
            <ChevronRight data-icon="inline-end" />
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

function FindingDetails({ findings }: { findings: MapFinding[] }) {
  if (!findings.length) return null
  return (
    <div className="space-y-s rounded-xl bg-destructive/10 p-l text-body-m font-medium [overflow-wrap:anywhere] text-risk-ink">
      {sortAlerts(findings).map((finding) => (
        <p key={finding.finding_id}>{finding.statement}</p>
      ))}
    </div>
  )
}

function ContractDetail({
  contract,
  t,
}: {
  contract?: StepContract
  t: Strings
}) {
  if (
    !contract ||
    typeof contract.input === "string" ||
    typeof contract.output === "string"
  )
    return <p className="text-body-m text-ink-3">{t.contractMissing}</p>
  return (
    <div className="space-y-xxl">
      <JsonBlock value={contract.input} label={t.contractInput} t={t} />
      <JsonBlock value={contract.output} label={t.contractOutput} t={t} />
    </div>
  )
}

function JsonBlock({
  value,
  label,
  t,
}: {
  value: Record<string, unknown>
  label: string
  t: Strings
}) {
  const json = JSON.stringify(value, null, 2)
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "error">(
    "idle"
  )
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json)
      setCopyState("copied")
    } catch {
      setCopyState("error")
    }
  }
  return (
    <section className="min-w-0 space-y-m">
      <div className="flex items-center justify-between gap-l">
        <h3 className="text-body-m font-medium">
          {label}
          <span className="ml-m font-data text-body-s font-regular text-ink-3">
            JSON
          </span>
        </h3>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={copy}
          aria-label={`${copyState === "copied" ? t.copied : t.copyJson} · ${label}`}
        >
          {copyState === "copied" ? <Check /> : <Copy />}
        </Button>
      </div>
      <pre className="max-w-full [scrollbar-width:thin] overflow-x-auto corner-m bg-field p-xl font-data text-body-s text-ink">
        <code>{json}</code>
      </pre>
      <span
        role="status"
        className={
          copyState === "error" ? "text-body-s text-risk-ink" : "sr-only"
        }
      >
        {copyState === "copied"
          ? t.copied
          : copyState === "error"
            ? t.copyFailed
            : ""}
      </span>
    </section>
  )
}

const COLLAPSIBLE_MOTION =
  "h-(--collapsible-panel-height) min-w-0 overflow-hidden data-ending-style:h-0 data-starting-style:h-0 motion-safe:transition-[height] motion-safe:duration-(--motion-duration) motion-safe:ease-(--motion-easing)"

function ChangeDetail({
  coupon,
  model,
  t,
  evidenceIds,
}: {
  coupon: Coupon
  model: Model
  t: Strings
  evidenceIds: string[]
}) {
  const { change } = coupon
  const tests = change.tests
  const status = statusOf(tests)
  const risks = (change.finding_ids ?? []).flatMap((id) => {
    const item = model.payload.report?.finding_changes?.find(
      (item) => item.finding.finding_id === id
    )
    return item && item.status !== "resolved" ? [item.finding] : []
  })
  // A stop may stand for several changes told in the same words: their code shows together.
  const members = coupon.group.length ? coupon.group : [change]
  const where = [
    ...new Set([
      ...members.flatMap(
        (member) =>
          member.after?.evidence_ids ?? member.before?.evidence_ids ?? []
      ),
      ...evidenceIds,
    ]),
  ]
  const source = sourceLinkOf(model.payload, where)
  const hasLocalCode =
    (!source || !source.exact) &&
    (members.some((member) => member.before || member.after) ||
      where.length > 0)
  return (
    <section data-tone={coupon.tone} className="min-w-0 space-y-xl">
      <FindingDetails findings={risks} />
      <div className="space-y-s">
        <div className="flex items-start gap-m">
          <NumberDisc no={coupon.no} className="mt-xxs" />
          <h3 className="min-w-0 text-body-l font-medium [overflow-wrap:anywhere]">
            {change.explanation?.summary ?? t.changeKind[change.kind]}
          </h3>
        </div>
        {change.explanation?.effect && (
          <p className="text-body-m [overflow-wrap:anywhere] text-ink-2">
            {change.explanation.effect}
          </p>
        )}
      </div>
      <section className="space-y-s">
        <h4 className="text-body-m font-medium">{t.testEvidence}</h4>
        <StatusMark
          status={status}
          label={t.coverage[coverageKind(tests)]}
          className="text-body-m text-ink-2"
        />
        {tests?.note && (
          <p className="text-body-m [overflow-wrap:anywhere] text-ink-2">
            {localizeNote(tests.note, model.lang)}
          </p>
        )}
      </section>
      {hasLocalCode && (
        <Collapsible>
          <CollapsibleTrigger
            render={<Button variant="outline" size="sm" />}
            className="group/code"
          >
            {t.localCode}
            <ChevronRight
              aria-hidden
              data-icon="inline-end"
              className="size-3.5 transition-transform duration-(--motion-duration) group-data-panel-open/code:rotate-90"
            />
          </CollapsibleTrigger>
          <CollapsibleContent className={COLLAPSIBLE_MOTION}>
            <div className="space-y-l pt-l">
              {members
                .flatMap((member) => [
                  {
                    side: member.before,
                    label: t.before,
                    id: member.change_id,
                  },
                  { side: member.after, label: t.after, id: member.change_id },
                ])
                .map(
                  ({ side, label, id }) =>
                    side && (
                      <section key={`${id}-${label}`} className="space-y-s">
                        <h4 className="text-body-s text-ink-3">{label}</h4>
                        <pre className="max-w-full overflow-x-auto corner-m bg-field p-l text-body-s">
                          <code>{side.text}</code>
                        </pre>
                      </section>
                    )
                )}
              <Evidence
                ids={where}
                model={model}
                t={t}
                skipText={(change.after ?? change.before)?.text}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  )
}

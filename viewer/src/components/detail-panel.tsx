import * as React from "react"
import { ArrowUpRight, Check, ChevronRight, Copy, Play, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardFooter, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Evidence } from "@/components/evidence"
import { ReviewBadge } from "@/components/review-badge"
import { KindTile, NumberDisc, StatusMark } from "@/canvas/step-node"
import { localizeNote, type Strings } from "@/i18n"
import { statusOf, type Coupon, type FlowView, type Model } from "@/model"
import { relationWords } from "@/relations"
import type { MapLink, MapFinding, MapStep, StepContract } from "@/types"
import { categoryOf, coverageKind, sourceLinkOf } from "@/presentation"

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
  onNavigate?: (flowId: string) => void
  onRelation?: (links: MapLink[]) => void
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
  onNavigate,
  onRelation,
}: PanelProps) {
  const coupons = subject.coupons
  const step = subject.type === "step" ? subject.step : undefined
  const active = coupons.find((coupon) => coupon.no === focus) ?? coupons[0]
  const findings =
    subject.type === "step" && subject.view
      ? subject.view.findings.filter((finding) =>
          (step?.finding_ids ?? []).includes(finding.finding_id)
        )
      : []
  const carried = new Set(
    coupons.flatMap((coupon) => coupon.change.finding_ids ?? [])
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
  const [tab, setTab] = React.useState("overview")

  return (
    <Card className="h-full max-h-[inherit] min-h-0 gap-0 rounded-2xl py-0 shadow-[var(--shadow-float)]">
      <CardHeader className="shrink-0 gap-4 p-5 pb-4">
        <div className="flex min-w-0 items-start gap-3">
          {step && <KindTile kind={step.kind} small />}
          <div className="min-w-0 flex-1">
            <CardTitle>
              <h2 className="text-[16px] leading-6 [overflow-wrap:anywhere]">
                {title}
              </h2>
            </CardTitle>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t.close}
            className="-mt-0.5 -mr-1 text-ink-3"
          >
            <X />
          </Button>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
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
          </div>
          {source ? (
            <Button asChild variant="outline" size="sm">
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.exact ? t.githubCode : t.githubCommitted}
                <ArrowUpRight data-icon="inline-end" />
              </a>
            </Button>
          ) : onWalk ? (
            <Button variant="outline" size="sm" onClick={onWalk}>
              <Play data-icon="inline-start" />
              {t.runFlow}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-0">
        <div className="shrink-0 border-b border-line px-5">
          <TabsList variant="line" className="h-10 gap-5 p-0">
            <TabsTrigger value="overview" className="px-0 pb-3">
              {t.changeOverview}
            </TabsTrigger>
            {step && !removed && (
              <TabsTrigger value="contract" className="px-0 pb-3">
                {t.ioContract}
              </TabsTrigger>
            )}
          </TabsList>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="min-w-0 p-5">
            <TabsContent value="overview" className="min-w-0 space-y-6">
              {coupons.map((coupon) => (
                <ChangeDetail
                  key={`${coupon.no}-${coupon.primary}`}
                  coupon={coupon}
                  model={model}
                  t={t}
                  focused={coupons.length > 1 && focus === coupon.no}
                  evidenceIds={step?.evidence_ids ?? []}
                />
              ))}
              {findings
                .filter((finding) => !carried.has(finding.finding_id))
                .map((finding) => (
                  <FindingDetail
                    key={finding.finding_id}
                    finding={finding}
                    t={t}
                  />
                ))}
              {!coupons.length && (
                <>
                  <p className="text-sm leading-6 [overflow-wrap:anywhere] text-ink-2">
                    {removed ? t.flowGone : (step?.reason ?? t.unchangedStep)}
                  </p>
                  {(!source || !source.exact) && (
                    <Evidence ids={evidenceIds} model={model} t={t} />
                  )}
                </>
              )}
              {subject.type === "step" && subject.view && (
                <StepRelations
                  model={model}
                  flowId={subject.view.flow.flow_id}
                  stepId={subject.step.step_id}
                  coupons={coupons}
                  onNavigate={onNavigate}
                  onRelation={onRelation}
                />
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
        <CardFooter className="shrink-0 justify-end bg-card px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onNext}>
            {t.nextChange}
            <ChevronRight data-icon="inline-end" />
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

function FindingDetail({ finding, t }: { finding: MapFinding; t: Strings }) {
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="destructive">{t.category[categoryOf(finding)]}</Badge>
        <span className="text-xs text-ink-3">
          {t.severityLabel} · {t.severity[finding.severity]}
        </span>
      </div>
      <p className="text-sm leading-6 [overflow-wrap:anywhere] text-ink-2">
        {finding.statement}
      </p>
    </section>
  )
}

export function ContractDetail({
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
    return <p className="text-sm leading-6 text-ink-3">{t.contractMissing}</p>
  return (
    <div className="space-y-5">
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
    <section className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium">
          {label}
          <span className="ml-2 font-mono text-[11px] font-normal text-ink-3">
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
      <pre className="max-w-full [scrollbar-width:thin] overflow-x-auto rounded-lg bg-field p-4 font-mono text-[12px] leading-5 text-ink">
        <code>{json}</code>
      </pre>
      <span
        role="status"
        className={copyState === "error" ? "text-xs text-risk-ink" : "sr-only"}
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

function ChangeDetail({
  coupon,
  model,
  t,
  focused,
  evidenceIds,
}: {
  coupon: Coupon
  model: Model
  t: Strings
  focused: boolean
  evidenceIds: string[]
}) {
  const ref = React.useRef<HTMLElement>(null)
  React.useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "nearest" })
  }, [focused])
  const { change } = coupon
  const tests = change.tests
  const status = statusOf(tests)
  const risks = (change.finding_ids ?? []).flatMap((id) => {
    const item = model.payload.report?.finding_changes?.find(
      (item) => item.finding.finding_id === id
    )
    return item && item.status !== "resolved" ? [item] : []
  })
  const where = [
    ...new Set([
      ...(change.after?.evidence_ids ?? change.before?.evidence_ids ?? []),
      ...evidenceIds,
    ]),
  ]
  const source = sourceLinkOf(model.payload, where)
  const hasLocalCode =
    (!source || !source.exact) &&
    (change.before || change.after || where.length > 0)
  return (
    <section
      ref={ref}
      data-tone={coupon.tone}
      className="min-w-0 scroll-mt-5 space-y-5"
    >
      <div className="flex items-start gap-2.5">
        <NumberDisc no={coupon.no} className="mt-1" />
        <h3 className="min-w-0 text-[17px] leading-7 font-medium [overflow-wrap:anywhere]">
          {change.explanation?.summary ?? t.changeKind[change.kind]}
        </h3>
      </div>
      {change.explanation?.effect && (
        <p className="text-sm leading-6 [overflow-wrap:anywhere] text-ink-2">
          {change.explanation.effect}
        </p>
      )}
      {risks.map((item) => (
        <FindingDetail
          key={item.finding.finding_id}
          finding={item.finding}
          t={t}
        />
      ))}
      <Separator />
      <section className="space-y-2.5">
        <h3 className="text-sm font-medium">{t.testEvidence}</h3>
        <StatusMark
          status={status}
          label={t.coverage[coverageKind(tests)]}
          className="text-[13px] text-ink-2"
        />
        {tests?.note && (
          <p className="text-[13px] leading-[21px] [overflow-wrap:anywhere] text-ink-2">
            {localizeNote(tests.note, model.lang)}
          </p>
        )}
      </section>
      {hasLocalCode && (
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="group -ml-2">
              <ChevronRight className="group-data-[state=open]:rotate-90" />
              {t.localCode}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="min-w-0 space-y-3 pt-3">
            {[
              { side: change.before, label: t.before },
              { side: change.after, label: t.after },
            ].map(
              ({ side, label }) =>
                side && (
                  <section key={label} className="space-y-1.5">
                    <h4 className="text-xs text-ink-3">{label}</h4>
                    <pre className="max-w-full overflow-x-auto rounded-lg bg-field p-3 text-xs leading-5">
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
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  )
}

function StepRelations({
  model,
  flowId,
  stepId,
  coupons,
  onNavigate,
  onRelation,
}: {
  model: Model
  flowId: string
  stepId: string
  coupons: Coupon[]
  onNavigate?: (id: string) => void
  onRelation?: (links: MapLink[]) => void
}) {
  const words = relationWords[model.lang]
  const outgoing = model.links.filter(
    (link) =>
      link.source.flow_id === flowId &&
      (!link.source.step_id || link.source.step_id === stepId)
  )
  const incoming = model.links.filter(
    (link) =>
      link.target.flow_id === flowId &&
      (!link.target.step_id || link.target.step_id === stepId)
  )
  const related = [
    ...new Set(
      coupons
        .flatMap((coupon) => {
          const stop = model.stops[coupon.no - 1]
          return [
            stop?.flowId,
            ...(stop?.also ?? []).map((item) => item.flowId),
          ]
        })
        .filter((id): id is string => Boolean(id && id !== flowId))
    ),
  ]
  if (!outgoing.length && !incoming.length && !related.length) return null
  return (
    <div className="space-y-5">
      <Separator />
      {[
        [words.outgoing, outgoing],
        [words.incoming, incoming],
      ].map(
        ([title, links]) =>
          (links as MapLink[]).length > 0 && (
            <section key={title as string} className="space-y-2">
              <h3 className="text-sm font-medium">{title as string}</h3>
              {(links as MapLink[]).map((link) => (
                <Button
                  key={link.link_id}
                  variant="ghost"
                  className="-ml-2 h-auto min-h-8 max-w-full justify-start px-2 text-left text-[13px] whitespace-normal"
                  onClick={() => onRelation?.([link])}
                >
                  {link.name}
                  {link.resolution === "candidate" && (
                    <Badge variant="outline">{words.pending}</Badge>
                  )}
                  <ArrowUpRight />
                </Button>
              ))}
            </section>
          )
      )}
      {related.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">{words.related}</h3>
          {related.map((id) => (
            <Button
              key={id}
              variant="ghost"
              className="-ml-2 h-auto min-h-8 max-w-full justify-start px-2 text-left text-[13px] whitespace-normal"
              onClick={() => onNavigate?.(id)}
            >
              {model.flowById.get(id)?.flow.name}
              <ArrowUpRight />
            </Button>
          ))}
        </section>
      )}
    </div>
  )
}

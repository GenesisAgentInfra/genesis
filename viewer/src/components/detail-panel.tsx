import * as React from "react"
import { ChevronRight, Play, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Evidence } from "@/components/evidence"
import { KindTile, NumberDisc, StatusMark } from "@/canvas/step-node"
import { cn } from "@/lib/utils"
import {
  localizeNote,
  localizeReason,
  type Strings,
  type VerdictDetail,
} from "@/i18n"
import {
  statusOf,
  type Coupon,
  type FlowView,
  type Model,
  type TestStatus,
} from "@/model"
import type { ChangeSide, CoverageAssessment, MapStep } from "@/types"
import { categoryOf, coverageKind } from "@/presentation"

/**
 * What a verdict rests on, said after the one word the page uses for it everywhere. A
 * change that is tested needs no more than that word.
 */
function detailOf(
  tests: CoverageAssessment | undefined,
  status: TestStatus
): VerdictDetail | undefined {
  if (!tests || tests.verdict === "covered") return undefined
  if (tests.verdict === "not_reached") return "not_reached"
  if (tests.verdict === "reached_only")
    return status === "untested" ? "reached_untested" : "reached_unsure"
  return "unknown"
}

/** What the panel is about: a step (changed or not), a change off the map, or a removed flow. */
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
  /** The stop on show, scrolled to when the step holds several changes. */
  focus?: number
  /** Walk the flow this step belongs to, from its trigger to its end. */
  onWalk?: () => void
  onNext?: () => void
  onClose: () => void
}

/** What a step or a change is, what it means for users, and what the tests say about it. */
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
  // A risk the change itself carries is shown with that change, not a second time here.
  const carried = new Set(
    coupons.flatMap((coupon) => coupon.change.finding_ids ?? [])
  )
  const findings =
    subject.type === "step" && subject.view
      ? (subject.step.finding_ids ?? [])
          .filter((id) => !carried.has(id))
          .map((id) =>
            subject.view!.findings.find((finding) => finding.finding_id === id)
          )
          .filter((finding) => finding !== undefined)
      : []
  const ghostSummary =
    subject.type === "step" && subject.ghost
      ? coupons[0]?.change.explanation?.summary
      : undefined
  const title =
    subject.type === "step"
      ? (ghostSummary ?? subject.step.name)
      : subject.type === "offMap"
        ? t.offMap
        : subject.name
  const titleIsCode =
    (subject.type === "step" &&
      (subject.view?.flow.stage === "skeleton" ||
        (subject.ghost && !ghostSummary))) ||
    (subject.type === "removedFlow" && subject.code)
  const subtitle =
    subject.type === "step"
      ? subject.ghost
        ? t.removed
        : t.stepKind[subject.step.kind]
      : subject.type === "offMap"
        ? t.offMapHint
        : t.removed

  return (
    <div className="flex h-full max-h-[inherit] min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2.5 px-4 pt-3.5 pb-3">
        {step && <KindTile kind={step.kind} small />}
        <div className="min-w-0 flex-1">
          <h2
            title={title}
            className={cn(
              "truncate text-[14px] leading-5 font-medium text-ink",
              titleIsCode && "font-mono text-[13px]"
            )}
          >
            {title}
          </h2>
          <p className="truncate text-[12px] leading-4 text-ink-3">
            {subtitle}
          </p>
        </div>
        {onWalk && (
          <Button
            variant="outline"
            size="xs"
            onClick={onWalk}
            className="shrink-0 rounded-full px-2.5 text-[12px] text-ink-2"
          >
            <Play data-icon="inline-start" />
            {t.runFlow}
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          aria-label={t.close}
          className="-mr-1 text-ink-3"
        >
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 [scrollbar-width:thin] overflow-y-auto overscroll-contain">
        <div className="flex flex-col gap-6 px-4 pb-5">
          {coupons.map((coupon) => (
            <ChangeDetail
              key={`${coupon.no}-${coupon.primary}`}
              coupon={coupon}
              model={model}
              t={t}
              focused={coupons.length > 1 && focus === coupon.no}
              // A removed step is already titled with its change's summary.
              titled={Boolean(ghostSummary)}
              step={
                subject.type === "step" && !subject.ghost ? step : undefined
              }
            />
          ))}
          {findings.map((finding) => (
            <section
              key={finding.finding_id}
              className="rounded-[12px] bg-risk-bg px-3 py-2.5"
            >
              <h3 className="text-[12px] leading-4 font-medium text-risk-ink">
                {t.riskTypes}：{t.category[categoryOf(finding)]} ·{" "}
                {t.severityLabel}：{t.severity[finding.severity]}
                {model.findingStatus.get(finding.finding_id) &&
                  ` · ${t.findingStatus[model.findingStatus.get(finding.finding_id)!]}`}
              </h3>
              <p className="mt-1 text-[13px] leading-[19px] text-ink">
                {finding.statement}
              </p>
            </section>
          ))}
          {subject.type === "removedFlow" && !coupons.length && (
            <p className="text-[14px] leading-[22px] text-ink-2">
              {t.flowGone}
            </p>
          )}
          {step && !coupons.length && (
            <section className="flex flex-col gap-2">
              {step.reason && (
                <p className="text-[13px] leading-[19px] text-ink-2">
                  {step.reason}
                </p>
              )}
              {subject.type === "step" && !subject.ghost && (
                <StepContractDetail step={step} t={t} />
              )}
              <Label>{t.inCode}</Label>
              <Evidence ids={step.evidence_ids ?? []} model={model} t={t} />
            </section>
          )}
        </div>
      </div>
      {onNext && (
        <div className="flex shrink-0 justify-end border-t border-line px-3 py-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onNext}
            className="rounded-full px-3 text-[13px] text-ink-2"
          >
            {t.nextChange}
            <ChevronRight data-icon="inline-end" />
          </Button>
        </div>
      )}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[12px] leading-4 font-medium text-ink-3">{children}</h3>
  )
}

/** Only explicit source-backed contracts are shown; old reports stay readable. */
function StepContractDetail({ step, t }: { step: MapStep; t: Strings }) {
  const contract = step.contract
  return (
    <section className="flex flex-col gap-2 border-t border-line pt-3">
      <Label>{t.ioContract}</Label>
      {contract ? (
        <dl className="grid grid-cols-[40px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[13px] leading-[19px]">
          <dt className="text-ink-3">{t.contractInput}</dt>
          <dd className="min-w-0 [overflow-wrap:anywhere] text-ink-2">
            {contract.input}
          </dd>
          <dt className="text-ink-3">{t.contractOutput}</dt>
          <dd className="min-w-0 [overflow-wrap:anywhere] text-ink-2">
            {contract.output}
          </dd>
          {contract.constraints && (
            <>
              <dt className="text-ink-3">{t.contractConstraints}</dt>
              <dd className="min-w-0 [overflow-wrap:anywhere] text-ink-2">
                {contract.constraints}
              </dd>
            </>
          )}
        </dl>
      ) : (
        <p className="text-[13px] leading-[19px] text-ink-3">
          {t.contractMissing}
        </p>
      )}
    </section>
  )
}

/** The changed code, before above after, so the two can be read at one glance. */
function CodeRow({
  side,
  label,
  tone,
}: {
  side: ChangeSide
  label: string
  tone: "before" | "after"
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-[36px_minmax(0,1fr)] items-baseline gap-2 rounded-[10px] px-2.5 py-1.5",
        tone === "before" ? "bg-risk-bg" : "bg-ok-bg"
      )}
    >
      <span className="text-[12px] leading-[18px] text-ink-3">{label}</span>
      {/* Code keeps its lines; one that is too long scrolls instead of breaking. */}
      <code
        className={cn(
          "block [scrollbar-width:thin] overflow-x-auto text-[12px] leading-[18px] whitespace-pre",
          tone === "before"
            ? "text-ink-2 line-through decoration-risk/50"
            : "text-ink"
        )}
      >
        {side.text}
      </code>
    </div>
  )
}

function ChangeDetail({
  coupon,
  model,
  t,
  focused,
  titled,
  step,
}: {
  coupon: Coupon
  model: Model
  t: Strings
  focused: boolean
  /** The panel title already says what changed. */
  titled: boolean
  step?: MapStep
}) {
  const ref = React.useRef<HTMLElement>(null)
  React.useEffect(() => {
    if (focused)
      ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [focused])
  const { change } = coupon
  const tests = change.tests
  const status = statusOf(tests)
  const risks = (change.finding_ids ?? [])
    .map((id) =>
      model.payload.report?.finding_changes?.find(
        (item) => item.finding.finding_id === id
      )
    )
    .filter((item) => item !== undefined)
  const where = [
    ...new Set([
      ...(change.after?.evidence_ids ?? change.before?.evidence_ids ?? []),
      ...(step?.evidence_ids ?? []),
    ]),
  ]
  const summary = change.explanation?.summary
  const detail = detailOf(tests, status)
  const hasCode = Boolean(
    change.before ||
    change.after ||
    where.length ||
    coupon.place.reason ||
    tests?.items?.length
  )
  return (
    <section
      ref={ref}
      data-tone={coupon.tone}
      className="flex scroll-mt-3 flex-col gap-3"
    >
      <div className="flex items-start gap-2">
        <NumberDisc no={coupon.no} className="mt-[3px]" />
        <p
          className={cn(
            "min-w-0 flex-1 font-medium text-ink",
            titled ? "text-[13px] leading-[26px]" : "text-[18px] leading-[26px]"
          )}
        >
          {titled
            ? t.changeNo(coupon.no)
            : (summary ?? t.changeKind[change.kind])}
        </p>
      </div>
      {change.explanation?.effect && (
        <div className="flex flex-col gap-1">
          <Label>{t.effect}</Label>
          <p className="text-[14px] leading-[22px] text-ink-2">
            {change.explanation.effect}
          </p>
        </div>
      )}
      {step && <StepContractDetail step={step} t={t} />}
      <div className="flex flex-col gap-1.5 border-t border-line pt-3">
        <Label>{t.testEvidence}</Label>
        {/* The same word as on the card, then what it rests on. */}
        <p className="text-[13px] leading-[18px] text-ink-2">
          <StatusMark
            status={status}
            label={t.coverage[coverageKind(tests)]}
            className="align-top font-medium text-ink [&_svg]:size-4"
          />
          {detail && <span> · {t.verdictDetail[detail]}</span>}
        </p>
        {tests?.note && (
          <p className="text-[13px] leading-[19px] text-ink-2">
            {localizeNote(tests.note, model.lang)}
          </p>
        )}
      </div>
      {risks.map((item) => (
        <div
          key={item.finding.finding_id}
          className="rounded-[12px] bg-risk-bg px-3 py-2.5"
        >
          <p className="text-[12px] leading-4 font-medium text-risk-ink">
            {t.riskTypes}：{t.category[categoryOf(item.finding)]} ·{" "}
            {t.severityLabel}：{t.severity[item.finding.severity]}
            <span className="ml-2 font-normal">
              {t.findingStatus[item.status]}
            </span>
          </p>
          <p className="mt-1 text-[13px] leading-[19px] text-ink">
            {item.finding.statement}
          </p>
        </div>
      ))}
      {hasCode && (
        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1 rounded-md text-[13px] leading-5 font-medium text-ink-2 hover:text-ink">
            <ChevronRight
              aria-hidden
              className="size-3.5 transition-transform duration-160 group-data-[state=open]:rotate-90"
            />
            <span className="group-data-[state=open]:hidden">{t.viewCode}</span>
            <span className="hidden group-data-[state=open]:inline">
              {t.hideCode}
            </span>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex flex-col gap-3 pt-2.5">
            {(change.before || change.after) && (
              <div className="flex flex-col gap-1.5">
                {change.before && (
                  <CodeRow
                    side={change.before}
                    label={t.before}
                    tone="before"
                  />
                )}
                {change.after && (
                  <CodeRow side={change.after} label={t.after} tone="after" />
                )}
              </div>
            )}
            <Evidence
              ids={where}
              model={model}
              t={t}
              skipText={(change.after ?? change.before)?.text}
            />
            {coupon.place.reason && (
              <div className="flex flex-col gap-0.5">
                <Label>{t.placed}</Label>
                <p className="text-[12px] leading-[18px] text-ink-3">
                  {localizeReason(coupon.place.reason, model.lang)}
                </p>
              </div>
            )}
            {tests?.items && tests.items.length > 0 && (
              <div className="flex flex-col gap-0.5">
                <Label>{t.tests}</Label>
                <ul className="flex flex-col gap-0.5">
                  {tests.items.map((item) => {
                    const [file, name] = item.test_id
                      .replace(/^head::|^base::/, "")
                      .split("#")
                    return (
                      <li
                        key={item.test_id}
                        className="font-mono text-[12px] leading-[17px] [overflow-wrap:anywhere] text-ink-2"
                      >
                        {name ?? file}{" "}
                        <span className="text-ink-3">{name ? file : ""}</span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  )
}

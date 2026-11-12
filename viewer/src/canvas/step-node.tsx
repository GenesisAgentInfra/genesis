import * as React from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import {
  Check,
  CircleCheck,
  CircleHelp,
  CircleX,
  Ellipsis,
  Flag,
  Minus,
  Pencil,
  Play,
  Plug,
  Plus,
  Repeat2,
  Split,
  Workflow,
} from "lucide-react"

import { BaseNode } from "@/components/base-node"
import { cn } from "@/lib/utils"
import { matches, statusOf, type TestStatus } from "@/model"
import type { StepKind } from "@/types"
import { RING_MS, TAG_FROM, TAG_MS, outOfFocus, useCanvas } from "./context"
import type { StepNode as StepNodeType } from "./graph"

/** One glyph per kind of step; its pastel pair comes from the tokens (see index.css). */
const TILE: Record<StepKind, typeof Play> = {
  trigger: Play,
  action: Workflow,
  decision: Split,
  external: Plug,
  result: Flag,
}

/**
 * What a change did to a step: put it there, took it away, or altered it. The glyph at the
 * card's corner says which; the card's colour is kept for how much the change needs a look.
 */
const DID = { added: Plus, removed: Minus, modified: Pencil } as const

/** One icon and one colour per test status, wherever it shows. */
export const STATUS_ICON: Record<
  TestStatus,
  { icon: typeof CircleCheck; className: string }
> = {
  tested: { icon: CircleCheck, className: "text-ok" },
  untested: { icon: CircleX, className: "text-warn" },
  unsure: { icon: CircleHelp, className: "text-ink-3" },
}

/**
 * The number a change goes by everywhere on the page: on its card, in the list and in the
 * stepper. Once the reader has marked it as seen it turns hollow and takes a tick.
 */
export function NumberDisc({
  no,
  seen,
  className,
}: {
  no: number
  seen: boolean
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex h-5 min-w-5 shrink-0 items-center justify-center gap-px rounded-full px-1 text-[12px] leading-none font-medium tabular-nums",
        seen
          ? "bg-card text-ink-3 ring-1 ring-ink-3/50"
          : "bg-tone-ink text-card",
        className
      )}
    >
      {seen && <Check className="size-2.5" strokeWidth={3} />}
      {no}
    </span>
  )
}

export function KindTile({
  kind,
  className,
  small,
}: {
  kind: StepKind
  className?: string
  small?: boolean
}) {
  const Icon = TILE[kind]
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center transition-[filter,opacity] duration-160",
        small ? "size-7 rounded-[8px]" : "size-8 rounded-[9px]",
        className
      )}
      style={{
        background: `var(--tile-${kind}-bg)`,
        color: `var(--tile-${kind}-ink)`,
      }}
    >
      <Icon
        aria-hidden
        className={small ? "size-3.5" : "size-4"}
        strokeWidth={2}
      />
    </span>
  )
}

export function StatusMark({
  status,
  label,
  className,
}: {
  status: TestStatus
  label: string
  className?: string
}) {
  const mark = STATUS_ICON[status]
  const Icon = mark.icon
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap",
        className
      )}
    >
      <Icon aria-hidden className={cn("size-3.5", mark.className)} />
      {label}
    </span>
  )
}

export function StepNode({ id, data }: NodeProps<StepNodeType>) {
  const canvas = useCanvas()
  const {
    t,
    focus,
    stopNo,
    current,
    next,
    far,
    routeSteps,
    dimAll,
    selected,
    knownRisks,
    filter,
    reviewed,
    run,
    armed,
    animate,
    delay,
    trail,
    trailActive,
  } = canvas
  const {
    step,
    coupons,
    isNew,
    risk,
    ghost,
    loops,
    removedFlow,
    skeleton,
    compact,
    width,
    hasIn,
    hasOut,
    slot,
    stub,
  } = data

  const isCurrent = current === id
  const isNext = next.has(id)
  const isSelected = selected === id && !isCurrent
  // The steps the change leads to come up when the ripple reaches them.
  const reached = isNext && armed
  // A walk through the flow reaches this step at this time, if it passes here at all.
  const arrive = trail?.steps.get(id)
  const visited = arrive !== undefined
  const lit = isCurrent || reached || isSelected
  // Narrowed down to one kind of change, the cards of every other kind step back.
  const filteredOut =
    filter !== undefined &&
    coupons.length > 0 &&
    !coupons.some((coupon) =>
      matches(
        { risky: coupon.risky, status: statusOf(coupon.change.tests) },
        filter
      )
    )
  // A removed flow is shown whole, except behind a change off the map, where every flow dims.
  const quiet =
    (trailActive && !visited) ||
    (filteredOut && !lit) ||
    (focus &&
      !trailActive &&
      (dimAll ||
        (!removedFlow &&
          (current !== undefined || routeSteps.size > 0) &&
          !lit)))
  const tagged = far.has(id) && armed
  const litDelay = visited
    ? trail!.animate
      ? arrive
      : 0
    : reached && animate
      ? delay + TAG_FROM
      : 0

  // A card holding several changes shows the current one, else the most urgent of them.
  const shown = coupons.find((coupon) => coupon.no === stopNo) ?? coupons[0]
  const change = shown?.change
  const summary = change?.explanation?.summary
  const status = change && !removedFlow ? statusOf(change.tests) : undefined
  // A removed step is named after its change; the line of code the CLI names it by comes last.
  const title = ghost ? (summary ?? step.name) : step.name
  const titleIsCode = skeleton || (ghost && !summary)

  // A changed card takes the colour of what it asks of the reader (a new risk, no test, a
  // verdict nobody can give, a test that checks it); the glyph at its corner says what the
  // change did to the step.
  const tone = coupons.length > 0 && !removedFlow ? shown?.tone : undefined
  const Did = tone
    ? DID[ghost ? "removed" : isNew ? "added" : "modified"]
    : undefined
  const card = cn(
    "border-line bg-card hover:ring-0",
    "transition-[box-shadow,border-color,background-color] [transition-delay:var(--lit-delay)] duration-160",
    quiet
      ? "bg-card/75 shadow-none"
      : "shadow-[var(--shadow-node)] hover:shadow-[var(--shadow-node-hover)]",
    tone && "border-[1.5px] border-tone/55",
    reached && "border-edge-strong/45",
    visited && !isCurrent && (tone ? "border-tone" : "border-edge-strong/35"),
    isCurrent && tone && "ring-tone",
    isSelected && "ring-select",
    ghost && "border-dashed"
  )
  const content = cn(
    "transition-opacity [transition-delay:var(--lit-delay)] duration-160",
    quiet && "opacity-60"
  )
  // Outside the module in focus the card steps back.
  const away = outOfFocus(canvas, id.slice(0, Math.max(id.indexOf("::"), 0)))
  const style = {
    width,
    // Every card sits in the middle of its place in the column, whatever its own height,
    // so lines meet it where the layout drew them.
    height: slot,
    display: "flex",
    flexDirection: "column" as const,
    justifyContent: "center",
    opacity: away ? 0.35 : undefined,
    transition: "opacity 160ms",
    "--lit-delay": `${litDelay}ms`,
  } as React.CSSProperties
  const changed = coupons.length > 0 && !removedFlow
  // Zoomed far out a change becomes a solid block of its colour, so the first look shows
  // where things changed and how much they need a look without reading a word.
  const marks = changed && (
    <span
      aria-hidden
      className={cn(
        "far-mark pointer-events-none absolute -inset-px",
        compact ? "rounded-[14px]" : "rounded-[18px]"
      )}
    />
  )

  const ringed = (isCurrent && armed && animate) || (visited && trail!.animate)
  const ring = ringed && (
    <span
      key={visited ? `walk-${trail!.run}` : `ring-${run}`}
      aria-hidden
      className={cn(
        "arrive pointer-events-none absolute -inset-px",
        compact ? "rounded-[14px]" : "rounded-[18px]"
      )}
      style={
        {
          "--arrive-delay": `${visited ? arrive : delay}ms`,
          "--arrive-duration": `${visited && coupons.length ? 480 : RING_MS}ms`,
        } as React.CSSProperties
      }
    />
  )
  // Lines from other flows (the same change elsewhere, a flow it may reach) land top and bottom.
  const relations = (
    <>
      <Handle
        type="target"
        position={Position.Top}
        id="rel-in"
        isConnectable={false}
        className="!opacity-0"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="rel-out"
        isConnectable={false}
        className="!opacity-0"
      />
    </>
  )
  const tag = tagged && (
    <span
      key={`tag-${run}`}
      className={cn(
        "pointer-events-none absolute -top-2.5 right-3 z-10 rounded-full bg-card px-2 py-px text-[12px] leading-4 font-medium whitespace-nowrap text-ink-2 shadow-[var(--shadow-node)] ring-1 ring-edge-strong/40",
        animate && "tag-in"
      )}
      style={
        {
          "--tag-delay": `${delay + TAG_FROM}ms`,
          "--tag-duration": `${TAG_MS}ms`,
        } as React.CSSProperties
      }
    >
      {t.mayAffect}
    </span>
  )

  const badges: React.ReactNode[] = []
  if (isNew) badges.push(<Badge key="new" tone="plain" label={t.newStep} />)
  if (ghost) badges.push(<Badge key="removed" tone="plain" label={t.removed} />)
  if (risk === "new")
    badges.push(<Badge key="risk" tone="risk" label={t.newRisk} />)
  else if (risk === "known" && knownRisks)
    badges.push(<Badge key="risk" tone="risk" label={t.knownRisk} />)
  if (step.resolution !== "resolved")
    badges.push(
      <span key="res">
        {step.resolution === "candidate" ? t.unconfirmed : t.unknown}
      </span>
    )

  // Steps left out after this point: a dotted pill that opens the whole flow.
  if (stub) {
    return (
      <div style={style}>
        <div
          data-slot="step-card"
          title={t.openStub}
          className={cn(
            "relative flex h-8 items-center gap-1 rounded-full border border-dashed border-ink-3/50 bg-card/60 pr-3 pl-2 text-[13px] leading-5 text-ink-2 transition-[color,border-color,opacity] duration-160 hover:border-ink-3 hover:text-ink",
            quiet && "opacity-60"
          )}
        >
          {hasIn && (
            <Handle
              type="target"
              position={Position.Left}
              id="in"
              isConnectable={false}
            />
          )}
          <Ellipsis aria-hidden className="size-3.5 shrink-0" />
          <span className="whitespace-nowrap">{step.name}</span>
        </div>
      </div>
    )
  }

  if (compact) {
    return (
      <div style={style}>
        <BaseNode
          data-slot="step-card"
          data-changed={changed ? "" : undefined}
          tabIndex={-1}
          className={cn(
            card,
            "flex h-11 items-center gap-2 rounded-[14px] py-1.5 pr-3.5 pl-1.5"
          )}
        >
          {ring}
          {tag}
          {marks}
          {relations}
          {hasIn && (
            <Handle
              type="target"
              position={Position.Left}
              id="in"
              isConnectable={false}
            />
          )}
          <div className={cn(content, "flex min-w-0 items-center gap-2")}>
            <KindTile
              kind={step.kind}
              small
              className={cn(quiet && "grayscale")}
            />
            <span
              title={step.name}
              className={cn(
                "min-w-0 truncate text-[14px] leading-5 font-medium text-ink",
                skeleton && "font-mono text-[13px] font-normal",
                removedFlow &&
                  "text-ink-2 line-through decoration-ink decoration-[1.5px]"
              )}
            >
              {step.name}
            </span>
          </div>
          {hasOut && (
            <Handle
              type="source"
              position={Position.Right}
              id="out"
              isConnectable={false}
            />
          )}
        </BaseNode>
      </div>
    )
  }

  return (
    <div style={style}>
      <BaseNode
        data-slot="step-card"
        data-changed={changed ? "" : undefined}
        data-tone={tone}
        tabIndex={-1}
        className={cn(card, "rounded-[18px] p-3")}
      >
        {ring}
        {tag}
        {marks}
        {tone && shown && (
          <NumberDisc
            no={shown.no}
            seen={reviewed.has(shown.no)}
            className="absolute -top-2 -left-2 z-[7]"
          />
        )}
        {Did && (
          <span
            aria-hidden
            className="absolute -top-2 -right-2 z-[7] flex size-[18px] items-center justify-center rounded-full border-[1.5px] border-current bg-card text-tone-ink"
          >
            <Did className="size-2.5" strokeWidth={2.75} />
          </span>
        )}
        {relations}
        {hasIn && (
          <Handle
            type="target"
            position={Position.Left}
            id="in"
            isConnectable={false}
          />
        )}
        <div className={content}>
          <div className="flex items-center gap-2.5">
            <KindTile
              kind={step.kind}
              className={cn(
                (ghost || quiet) && "grayscale",
                ghost && "opacity-70"
              )}
            />
            <div className="min-w-0 flex-1">
              <div
                title={title}
                className={cn(
                  "line-clamp-2 text-[14px] leading-5 font-medium [overflow-wrap:anywhere] text-ink",
                  titleIsCode && "font-mono text-[13px] font-normal",
                  ghost &&
                    !summary &&
                    "text-ink-2 line-through decoration-ink-3",
                  // The one sign on a removed flow's canvas, so it must read at a glance.
                  removedFlow &&
                    "text-ink-2 line-through decoration-ink decoration-[1.5px]"
                )}
              >
                {title}
              </div>
              {badges.length > 0 && (
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px] leading-4 text-ink-3">
                  {badges}
                </div>
              )}
            </div>
          </div>

          {change && (
            <div
              className={cn(
                "mt-2.5 rounded-[12px] px-2.5 py-2 transition-colors duration-160",
                tone ? "bg-tone-bg" : "bg-field"
              )}
            >
              {!(ghost && summary) && (
                <p
                  className={cn(
                    "mb-1 line-clamp-3 text-[13px] leading-[18px]",
                    tone ? "text-tone-ink" : "text-ink-2"
                  )}
                >
                  {summary ?? t.changeKind[change.kind]}
                </p>
              )}
              <div className="flex items-center justify-between gap-2 text-[12px] leading-4 text-ink-2">
                {status ? (
                  <StatusMark status={status} label={t.status[status]} />
                ) : (
                  <span />
                )}
                {coupons.length > 1 && (
                  <span>{t.moreChanges(coupons.length - 1)}</span>
                )}
              </div>
            </div>
          )}

          {loops.map((loop, index) => (
            <div
              key={index}
              className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-3"
            >
              <Repeat2 aria-hidden className="size-3.5" />
              <span className="line-clamp-1">{loop.label || t.repeats}</span>
            </div>
          ))}
        </div>

        {hasOut && (
          <Handle
            type="source"
            position={Position.Right}
            id="out"
            isConnectable={false}
          />
        )}
      </BaseNode>
    </div>
  )
}

/** A word on a card. Only a risk is coloured: added and removed are said by the glyph. */
function Badge({ tone, label }: { tone: "plain" | "risk"; label: string }) {
  return (
    <span
      className={cn(
        "rounded-[5px] px-1 text-[12px] leading-4 font-medium",
        tone === "plain" ? "bg-field text-ink-2" : "bg-risk-bg text-risk-ink"
      )}
    >
      {label}
    </span>
  )
}

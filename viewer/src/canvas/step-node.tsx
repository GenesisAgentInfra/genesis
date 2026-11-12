import * as React from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import {
  CircleCheck,
  CircleHelp,
  CircleX,
  Flag,
  Play,
  Plug,
  Repeat2,
  Split,
  Workflow,
} from "lucide-react"

import { BaseNode } from "@/components/base-node"
import { cn } from "@/lib/utils"
import { statusOf, type TestStatus } from "@/model"
import type { StepKind } from "@/types"
import { RING_MS, TAG_FROM, TAG_MS, useCanvas } from "./context"
import type { StepNode as StepNodeType } from "./graph"

const TILE: Record<StepKind, { icon: typeof Play; className: string }> = {
  trigger: { icon: Play, className: "bg-[#e6f5ec] text-[#1a7f45]" },
  action: { icon: Workflow, className: "bg-[#efeafd] text-[#6a3fd4]" },
  decision: { icon: Split, className: "bg-[#ffeee1] text-[#c9530a]" },
  external: { icon: Plug, className: "bg-[#fff4d1] text-[#9a6200]" },
  result: { icon: Flag, className: "bg-[#efeff1] text-[#4f5057]" },
}

/** One icon and one colour per test status, wherever it shows. */
export const STATUS_ICON: Record<
  TestStatus,
  { icon: typeof CircleCheck; className: string }
> = {
  tested: { icon: CircleCheck, className: "text-ok" },
  untested: { icon: CircleX, className: "text-risk" },
  unsure: { icon: CircleHelp, className: "text-ink-3" },
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
  const tile = TILE[kind]
  const Icon = tile.icon
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center transition-[filter,opacity] duration-160",
        small ? "size-7 rounded-[8px]" : "size-8 rounded-[9px]",
        tile.className,
        className
      )}
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
    run,
    armed,
    animate,
    delay,
    trail,
    trailActive,
  } = canvas
  const {
    step,
    rows,
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
  // A removed flow is shown whole, except behind a change off the map, where every flow dims.
  const quiet =
    (trailActive && !visited) ||
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
  // Every change on the map is written in amber; the one on show also takes the solid border.
  const loud = shown !== undefined
  const summary = change?.explanation?.summary
  const status = change && !removedFlow ? statusOf(change.tests) : undefined
  // A removed step is named after its change; the line of code the CLI names it by comes last.
  const title = ghost ? (summary ?? step.name) : step.name
  const titleIsCode = skeleton || (ghost && !summary)

  const card = cn(
    "border-line bg-card hover:ring-0",
    "transition-[box-shadow,border-color,background-color] [transition-delay:var(--lit-delay)] duration-160",
    quiet
      ? "bg-card/75 shadow-none"
      : "shadow-[var(--shadow-node)] hover:shadow-[var(--shadow-node-hover)]",
    isCurrent &&
      !removedFlow &&
      "border-change shadow-[0_0_0_3px_rgb(226_134_11_/_0.12),var(--shadow-node-hover)]",
    coupons.length > 0 && !removedFlow && !isCurrent && "border-change/45",
    reached && "border-change/45",
    visited &&
      !isCurrent &&
      (coupons.length ? "border-change" : "border-[#3a3b40]/35"),
    isSelected &&
      "border-select shadow-[0_0_0_3px_rgb(47_111_235_/_0.14),var(--shadow-node-hover)]",
    ghost && "border-dashed"
  )
  const content = cn(
    "transition-opacity [transition-delay:var(--lit-delay)] duration-160",
    quiet && "opacity-60"
  )
  const style = { width, "--lit-delay": `${litDelay}ms` } as React.CSSProperties

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
        "pointer-events-none absolute -top-2.5 right-3 z-10 rounded-full bg-card px-2 py-px text-[11px] leading-4 font-medium whitespace-nowrap text-change-ink shadow-[var(--shadow-node)] ring-1 ring-change/45",
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
  if (isNew) badges.push(<Badge key="new" tone="ok" label={t.newStep} />)
  if (ghost) badges.push(<Badge key="removed" tone="risk" label={t.removed} />)
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

  if (compact) {
    return (
      <div style={style}>
        <BaseNode
          data-slot="step-card"
          tabIndex={-1}
          className={cn(
            card,
            "flex h-11 items-center gap-2 rounded-[14px] py-1.5 pr-3.5 pl-1.5"
          )}
        >
          {ring}
          {tag}
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
                "min-w-0 truncate text-[13.5px] leading-5 font-medium text-ink",
                skeleton && "font-mono text-[12.5px] font-normal",
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
        tabIndex={-1}
        className={cn(card, "rounded-[18px] p-3")}
      >
        {ring}
        {tag}
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
                  titleIsCode && "font-mono text-[12.5px] font-normal",
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

          {rows.length > 0 && (
            <div className="mt-2.5 flex flex-col gap-1.5">
              {rows.map((row) => (
                <div
                  key={row.id}
                  className={cn(
                    "relative rounded-[10px] bg-field px-2.5 py-[7px] text-[12.5px] leading-[18px]",
                    row.exception ? "text-risk" : "text-ink-2",
                    row.uncertain &&
                      "outline-1 -outline-offset-1 outline-ink-3/40 outline-dashed"
                  )}
                >
                  <span className="line-clamp-1 [overflow-wrap:anywhere]">
                    {row.label}
                  </span>
                  <Handle
                    type="source"
                    position={Position.Right}
                    id={row.id}
                    isConnectable={false}
                    style={{ right: -17 }}
                  />
                </div>
              ))}
            </div>
          )}

          {change && (
            <div
              className={cn(
                "mt-2.5 rounded-[12px] px-2.5 py-2 transition-colors duration-160",
                loud ? "bg-change-bg" : "bg-field"
              )}
            >
              {!(ghost && summary) && (
                <p
                  className={cn(
                    "mb-1 line-clamp-2 text-[12.5px] leading-[18px]",
                    loud ? "text-change-ink" : "text-ink-2"
                  )}
                >
                  {summary ?? t.changeKind[change.kind]}
                </p>
              )}
              <div className="flex items-center justify-between gap-2 text-[11.5px] leading-4 text-ink-2">
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

function Badge({ tone, label }: { tone: "ok" | "risk"; label: string }) {
  return (
    <span
      className={cn(
        "rounded-[5px] px-1 text-[11px] leading-4 font-medium",
        tone === "ok" ? "bg-ok-bg text-ok" : "bg-risk-bg text-risk"
      )}
    >
      {label}
    </span>
  )
}

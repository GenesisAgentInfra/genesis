import * as React from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import {
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

import { Badge } from "@/components/ui/badge"
import { ReviewBadge } from "@/components/review-badge"
import { BaseNode } from "@/components/base-node"
import { cn } from "@/lib/utils"
import { statusOf, type TestStatus } from "@/model"
import type { StepKind } from "@/types"
import { coverageKind, shortSummary } from "@/presentation"
import { useCanvas } from "./context"
import { TAG_MS } from "./emphasis"
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
const STATUS_ICON: Record<TestStatus, typeof CircleCheck> = {
  tested: CircleCheck,
  untested: CircleX,
  unsure: CircleHelp,
}
const STATUS_COLOR: Record<TestStatus, string> = {
  tested: "text-ok",
  untested: "text-warn",
  unsure: "text-ink-3",
}

/**
 * The number a change goes by everywhere on the page: on its card, in the list and in the
 * stepper.
 */
export function NumberDisc({
  no,
  className,
}: {
  no: number
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex h-5 min-w-5 shrink-0 items-center justify-center gap-xxs",
        "corner-full px-xs",
        "text-body-s leading-none font-medium tabular-nums",
        "bg-tone-ink text-card",
        className
      )}
    >
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
        small ? "size-7 corner-m" : "size-8 corner-m",
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
  const Icon = STATUS_ICON[status]
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-xs whitespace-nowrap",
        className
      )}
    >
      <Icon aria-hidden className={cn("size-3.5", STATUS_COLOR[status])} />
      {label}
    </span>
  )
}

export function StepNode({ id, data }: NodeProps<StepNodeType>) {
  const canvas = useCanvas()
  const { t, stopNo } = canvas
  const {
    step,
    coupons,
    echoes = [],
    isNew,
    risk,
    alerts = [],
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

  const look = canvas.step(id, { changed: coupons.length > 0, removedFlow })
  const {
    current: isCurrent,
    selected: isSelected,
    reached,
    visited,
    quiet,
  } = look

  // A card holding several changes shows the current one, else the most urgent of them.
  const shown = coupons.find((coupon) => coupon.no === stopNo) ?? coupons[0]
  const change = shown?.change
  const summary = change ? shortSummary(change) : undefined
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
      ? "shadow-none"
      : "shadow-[var(--shadow-node)] hover:shadow-[var(--shadow-node-hover)]",
    tone && "edge-l border-tone/55",
    reached && "border-edge-strong/45",
    visited && !isCurrent && (tone ? "border-tone" : "border-edge-strong/35"),
    isCurrent && tone && "ring-tone",
    isSelected && "ring-select",
    ghost && "border-dashed"
  )
  // Quiet the surface and icon, not the words needed to read the surrounding path.
  const content =
    "transition-opacity [transition-delay:var(--lit-delay)] duration-160"
  const style = {
    width,
    // Every card sits in the middle of its place in the column, whatever its own height,
    // so lines meet it where the layout drew them.
    height: slot,
    display: "flex",
    flexDirection: "column" as const,
    justifyContent: "center",
    // Outside the module in focus the card steps back.
    opacity: look.away ? 0.35 : undefined,
    transition: "opacity 160ms",
    "--lit-delay": `${look.delay}ms`,
  } as React.CSSProperties
  const changed = coupons.length > 0 && !removedFlow
  const ring = look.ring && (
    <span
      key={look.ring.key}
      aria-hidden
      className={cn(
        "arrive pointer-events-none absolute -inset-px",
        compact ? "corner-l" : "corner-xl"
      )}
      style={
        {
          "--arrive-delay": `${look.ring.delay}ms`,
          "--arrive-duration": `${look.ring.duration}ms`,
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
  const tag = look.tag && (
    <span
      key={look.tag.key}
      className={cn(
        "absolute -top-2.5 right-3 z-10",
        "corner-full px-m py-xxs",
        "text-body-s font-medium whitespace-nowrap",
        "pointer-events-none bg-card text-ink-2 shadow-[var(--shadow-node)] ring-1 ring-edge-strong/40",
        look.tag.enters !== undefined && "tag-in"
      )}
      style={
        {
          "--tag-delay": `${look.tag.enters ?? 0}ms`,
          "--tag-duration": `${TAG_MS}ms`,
        } as React.CSSProperties
      }
    >
      {t.mayAffect}
    </span>
  )

  const badges: React.ReactNode[] = []
  if (isNew)
    badges.push(
      <Badge key="new" variant="secondary">
        {t.newStep}
      </Badge>
    )
  if (ghost)
    badges.push(
      <Badge key="removed" variant="secondary">
        {t.removed}
      </Badge>
    )
  if (alerts.length || shown?.risky || risk !== undefined)
    badges.push(<ReviewBadge key="risk" risky t={t} count={alerts.length} />)
  else if (change && status && status !== "tested")
    badges.push(
      <ReviewBadge key="validation" risky={false} status={status} t={t} />
    )
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
            "relative flex h-8 items-center gap-xs",
            "corner-full edge-m border-dashed pr-l pl-m",
            "text-body-m",
            "border-ink-3/50 bg-card text-ink-2 transition-[color,border-color] duration-160",
            "hover:border-ink-3 hover:text-ink"
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
            "flex h-full items-center gap-m corner-l py-s pr-xl pl-s"
          )}
        >
          {ring}
          {tag}
          {echoes.length > 0 && (
            // The change is told on its own card; here it is only its number, in grey.
            <span
              title={echoes.map((no) => t.echoOf(no)).join("\n")}
              className="absolute -top-2 -left-2 z-[7] flex h-5 min-w-5 items-center justify-center corner-full bg-field px-xs text-body-s leading-none font-medium text-ink-2 tabular-nums ring-1 ring-line"
            >
              {echoes.join(" · ")}
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
          <div className={cn(content, "flex min-w-0 items-center gap-m")}>
            <KindTile
              kind={step.kind}
              small
              className={cn(quiet && "grayscale")}
            />
            <span
              title={step.name}
              className={cn(
                "line-clamp-2 min-w-0 text-body-m font-medium [overflow-wrap:anywhere] text-ink",
                skeleton && "font-data text-body-m font-regular",
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
        className={cn(card, "corner-xl p-l")}
      >
        {ring}
        {tag}
        {tone && shown && (
          <NumberDisc no={shown.no} className="absolute -top-2 -left-2 z-[7]" />
        )}
        {Did && (
          <span
            aria-hidden
            className={cn(
              "absolute -top-2 -right-2 z-[7] flex size-[18px] items-center justify-center",
              "corner-full edge-l",
              "border-current bg-card text-tone-ink"
            )}
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
          <div className="flex items-center gap-l">
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
                  "line-clamp-2 text-body-m font-medium [overflow-wrap:anywhere] text-ink",
                  titleIsCode && "font-data text-body-m font-regular",
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
                <div className="mt-xs flex flex-wrap items-center gap-s text-body-s text-ink-3">
                  {badges}
                </div>
              )}
            </div>
          </div>

          {change && (
            <div className="mt-m edge-t-m border-line/60 pt-m">
              {!(ghost && summary) && (
                <p
                  className={cn(
                    "mb-m line-clamp-2 text-body-m",
                    tone ? "text-tone-ink" : "text-ink-2"
                  )}
                >
                  {summary ?? t.changeKind[change.kind]}
                </p>
              )}
              <div className="flex flex-wrap items-center justify-between gap-xs text-body-s text-ink-2">
                {status ? (
                  <StatusMark
                    status={status}
                    label={t.coverage[coverageKind(change.tests)]}
                  />
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
              className="mt-m flex items-center gap-s text-body-s text-ink-3"
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

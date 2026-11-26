import * as React from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import {
  Bot,
  ChevronDown,
  Clock,
  Code,
  Globe,
  ListTodo,
  Play,
  Workflow,
  SquareTerminal,
  Zap,
  FoldHorizontal,
  UnfoldHorizontal,
  type LucideIcon,
} from "lucide-react"

import { NumberDisc, StatusMark } from "@/canvas/step-node"
import { ReviewBadge } from "@/components/review-badge"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle } from "@/components/ui/card"
import { useCanvas } from "@/canvas/context"
import { cn } from "@/lib/utils"
import { coverageKind, shortSummary } from "@/presentation"
import { statusOf } from "@/model"
import type { EntryKind } from "@/types"
import {
  OFF_MAP,
  type BoxNode,
  type FlowCardNode,
  type ModuleNode,
  type MoreNode,
  type OffMapNode,
  type RowNode,
} from "./build"

/** Lift headings at low zoom only while their text and controls fit in the reserved space. */
function headingStyle(limit: number): React.CSSProperties {
  const scale = `min(var(--lift, 1), ${limit})`
  return { transform: `scale(${scale})`, width: `calc(100% / ${scale})` }
}

/** The card whose details are open, ringed in its own colour the way a picked change is. */
const PICKED = "border-solid ring-tone"

interface AtlasHandlers {
  onRun: (flowId: string) => void
  /** Close the module in focus: back to the whole map. */
  onOverview: () => void
}
export const AtlasContext = React.createContext<AtlasHandlers | null>(null)
function useAtlas(): AtlasHandlers {
  const value = React.useContext(AtlasContext)
  if (!value) throw new Error("atlas context missing")
  return value
}

/** A module is a heading on the canvas, with no enclosing surface. */
export function ModuleView({ id, data }: NodeProps<ModuleNode>) {
  const { t, walking, focusedModule } = useCanvas()
  const { onOverview } = useAtlas()
  const away = Boolean(focusedModule && focusedModule !== id)
  return (
    <div
      className={cn(
        "group @container pointer-events-none relative h-full w-full transition-opacity duration-160",
        walking && "opacity-80",
        away && "opacity-85"
      )}
    >
      {/* The row stands on a line 14px above the module's first card and grows upward. */}
      <div
        className="pointer-events-auto absolute left-0 flex origin-bottom-left flex-wrap items-center gap-x-m gap-y-xs"
        style={{
          ...headingStyle(data.heading.lift),
          bottom: `calc(100% - ${data.heading.height - 14}px)`,
        }}
      >
        <h2
          className={cn(
            "min-w-0 font-display text-body-xl font-medium [overflow-wrap:anywhere] text-ink",
            data.heading.stacked && "basis-full"
          )}
        >
          {data.title}
        </h2>
        <span
          className={cn(
            "shrink-0 corner-s px-s text-body-s font-medium tabular-nums",
            data.changes
              ? "bg-ink/[0.07] text-ink-2"
              : "bg-ink/[0.05] text-ink-3"
          )}
        >
          {data.changes
            ? t.moduleChanges(data.changes)
            : t.moduleFlows(data.flows)}
        </span>
        {/* One button in one place opens the module and closes it again, so the way in and
            the way back are never a guess. On a cell it sits at the heading's right; on a
            module that runs the full width it follows the count, so it stays in view when
            the map runs on past the screen. */}
        <Button
          variant="ghost"
          size="xs"
          type="button"
          aria-expanded={data.open}
          title={data.open ? t.closeModuleHint : t.openModule}
          // Closed, the click falls through to the frame, which opens.
          onClick={
            data.open
              ? (event) => {
                  event.stopPropagation()
                  onOverview()
                }
              : undefined
          }
          className={cn(
            "nodrag nopan shrink-0",
            data.wide ? "ml-xs" : "ml-auto",
            data.open ? "cursor-pointer" : "cursor-zoom-in"
          )}
        >
          {data.open ? (
            <FoldHorizontal aria-hidden className="size-3.5" />
          ) : (
            <UnfoldHorizontal aria-hidden className="size-3.5" />
          )}
          <span
            className={cn(
              !data.open &&
                !data.wide &&
                "hidden group-hover:inline @min-[300px]:inline"
            )}
          >
            {data.open ? t.closeModule : data.wide ? t.openModule : t.openShort}
          </span>
        </Button>
      </div>
    </div>
  )
}

/**
 * The card a drawn flow sits on: its name at the head, its steps and lines inset below.
 * Only the head takes a click; the rest of the card belongs to the canvas. With no change
 * to read, the head offers a walk through the flow.
 */
export function FlowCardView({ data }: NodeProps<FlowCardNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const { onRun } = useAtlas()
  const away = canvas.away(data.flowId || OFF_MAP)
  return (
    <Card
      data-tone={data.tone}
      className={cn(
        "pointer-events-none h-full w-full gap-0 rounded-3xl bg-(--flow) py-0 shadow-none ring-0 transition-opacity duration-160",
        away && "opacity-85"
      )}
    >
      <CardHeader
        className="flex shrink-0 items-center"
        style={{ height: data.heading.height }}
      >
        <div
          className="pointer-events-auto flex min-w-0 origin-left cursor-pointer flex-wrap items-center gap-x-m gap-y-xs"
          style={headingStyle(data.heading.lift)}
        >
          <div
            className={cn(
              "flex min-w-0 items-center gap-m",
              data.heading.stacked && "basis-full"
            )}
          >
            {data.tone && (
              // The most pressing change on the flow, in its one colour.
              <span
                aria-hidden
                className="size-1.5 shrink-0 corner-full bg-tone"
              />
            )}
            <CardTitle
              title={data.name}
              className={cn(
                "min-w-0 text-body-m font-medium [overflow-wrap:anywhere] text-ink",
                data.code && "font-data text-body-m font-regular",
                data.struck &&
                  "text-ink-2 line-through decoration-ink decoration-[1.5px]"
              )}
            >
              {data.name}
            </CardTitle>
          </div>
          {data.code && (
            <span className="shrink-0 corner-s bg-field px-xs pb-xxs text-body-s text-ink-3">
              {t.skeletonTag}
            </span>
          )}
          {data.flowId && !data.struck && !canvas.focus && (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={(event) => {
                event.stopPropagation()
                onRun(data.flowId)
              }}
              className="nodrag nopan ml-xs"
            >
              <Play aria-hidden className="size-3" />
              {t.runFlow}
            </Button>
          )}
        </div>
      </CardHeader>
    </Card>
  )
}

/** What starts a flow, as a glyph. */
const ENTRY_ICON: Record<EntryKind, LucideIcon> = {
  http_route: Globe,
  cli_command: SquareTerminal,
  task: ListTodo,
  scheduled: Clock,
  public_api: Code,
  agent_tool: Bot,
  handler: Zap,
  main: Play,
  root: Play,
}

/** A change that sits on no flow: kept on the map so it is not lost. */
export function OffMapView({ id, data }: NodeProps<OffMapNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const away = canvas.away(OFF_MAP)
  const change = data.coupon.change
  const status = statusOf(change.tests)
  const picked = canvas.apart === id
  return (
    <Card
      size="sm"
      data-tone={data.coupon.tone}
      className={cn(
        "relative h-full w-full cursor-pointer justify-start gap-2 overflow-visible rounded-2xl border border-dashed border-tone/60 p-3 ring-0 transition-[opacity,box-shadow,border-color] duration-160",
        "hover:shadow-[var(--shadow-node-hover)]",
        picked && PICKED,
        away && "opacity-85"
      )}
    >
      <NumberDisc
        no={data.coupon.no}
        className="absolute -top-2 -left-2 z-[7]"
      />
      {data.coupon.risky && (
        <ReviewBadge risky={data.coupon.risky} status={status} t={t} />
      )}
      <p className="text-body-m [overflow-wrap:anywhere] text-ink">
        {shortSummary(change) ?? t.changeKind[change.kind]}
      </p>
      <StatusMark
        status={status}
        label={t.coverage[coverageKind(change.tests)]}
        className="text-body-s text-ink-2"
      />
    </Card>
  )
}

/** A flow as one row: the change leaves it alone, or it is gone after it. */
export function RowView({ id, data }: NodeProps<RowNode>) {
  const canvas = useCanvas()
  const away = canvas.away(data.flowId)
  const Icon = (data.entry && ENTRY_ICON[data.entry]) || Workflow
  return (
    <Card
      size="sm"
      // A flow that is gone carries no verdict: it rings in the plain colour.
      data-tone={data.struck ? "unsure" : undefined}
      className={cn(
        "relative h-full w-full cursor-pointer flex-row items-center gap-2 overflow-visible rounded-2xl border border-line px-3 py-2 shadow-none ring-0 transition-[opacity,box-shadow] duration-160",
        "hover:shadow-[var(--shadow-node-hover)]",
        data.struck && "border-dashed",
        canvas.apart === id && PICKED,
        away && "opacity-85"
      )}
    >
      {data.no !== undefined && (
        <NumberDisc no={data.no} className="absolute -top-2 -left-2 z-[7]" />
      )}
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
      <span
        className={cn(
          "flex size-7 shrink-0 items-center justify-center",
          "corner-m",
          "bg-field text-ink-3"
        )}
      >
        <Icon aria-hidden className="size-3.5" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span
          title={data.name}
          className={cn(
            "text-body-m [overflow-wrap:anywhere] text-ink",
            data.code && "font-data text-body-m text-ink-2",
            data.struck &&
              "text-ink-2 line-through decoration-ink decoration-[1.5px]"
          )}
        >
          {data.name}
        </span>
        {data.summary && (
          <span
            title={data.summary}
            className="text-body-s [overflow-wrap:anywhere] text-ink-3"
          >
            {data.summary}
          </span>
        )}
        <span className="text-body-s [overflow-wrap:anywhere] text-ink-2">
          {data.note}
        </span>
      </span>
    </Card>
  )
}

/** The lookups and upkeep of a module in one line; opening the module lists them. */
export function MoreView({ data }: NodeProps<MoreNode>) {
  const { t, focusedModule } = useCanvas()
  return (
    <div
      className={cn(
        "flex h-full w-full items-center gap-s",
        "corner-l edge-m border-dashed px-l",
        "text-body-m",
        "cursor-pointer border-line text-ink-2 transition-[opacity,color,border-color] duration-160",
        "hover:border-ink-3/50 hover:text-ink",
        focusedModule && "opacity-85"
      )}
    >
      <ChevronDown aria-hidden className="size-3.5 shrink-0" />
      <span className="truncate">{t.supportingRow(data.count)}</span>
    </div>
  )
}

/**
 * The error path of a flow, in a dashed box under its other rows: the lines into it keep
 * their pale red, the box only gathers them and says what they are.
 */
export function BoxView({ data }: NodeProps<BoxNode>) {
  const canvas = useCanvas()
  const away = canvas.away(data.flowId)
  const { stage } = data
  if (stage)
    // An opened stage: a quiet frame round its steps, its name on top to fold it by.
    return (
      <div
        className={cn(
          "relative h-full w-full",
          "corner-xl bg-ink/[0.035] ring-1 ring-line",
          "pointer-events-none transition-opacity duration-160",
          away && "opacity-85"
        )}
      >
        <span
          title={stage.held ? undefined : canvas.t.foldStage}
          className={cn(
            "nodrag nopan absolute bottom-full left-2 mb-xs flex max-w-full items-center gap-xs",
            "text-body-s font-medium whitespace-nowrap text-ink-2",
            !stage.held && "pointer-events-auto cursor-pointer hover:text-ink"
          )}
        >
          {!stage.held && (
            <FoldHorizontal aria-hidden className="size-3 shrink-0" />
          )}
          <span className="truncate">{stage.name}</span>
        </span>
      </div>
    )
  return (
    <div
      aria-hidden
      className={cn(
        "relative h-full w-full",
        "corner-xl edge-m border-dashed",
        "pointer-events-none border-edge-exception/50 transition-opacity duration-160",
        away && "opacity-85"
      )}
    >
      <span className="absolute top-2 left-3.5 text-body-s font-medium text-ink-3">
        {canvas.t.errorPaths}
      </span>
    </div>
  )
}

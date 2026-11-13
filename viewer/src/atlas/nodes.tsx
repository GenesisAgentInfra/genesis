import * as React from "react"
import {
  Handle,
  Position,
  getBezierPath,
  EdgeLabelRenderer,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react"
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
  Maximize2,
  Minimize2,
  type LucideIcon,
} from "lucide-react"

import { NumberDisc, StatusMark } from "@/canvas/step-node"
import { ReviewBadge } from "@/components/review-badge"
import { outOfFocus, useCanvas } from "@/canvas/context"
import { cn } from "@/lib/utils"
import { coverageKind, shortSummary } from "@/presentation"
import { matches, statusOf } from "@/model"
import type { EntryKind } from "@/types"
import type {
  LabelNode,
  ModuleNode,
  MoreNode,
  OffMapNode,
  RelationEdge,
  RowNode,
} from "./build"

/** Text that keeps about the same size on screen however far the reader zooms out. */
const steady = (px: number, max: number) => ({
  fontSize: `clamp(${px}px, calc(${px}px / var(--zoom, 1)), ${max}px)`,
})

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

/** A module: a frame around its flows. Clicking it draws every step of them. */
export function ModuleView({ id, data }: NodeProps<ModuleNode>) {
  const { t, trailActive, focusedModule } = useCanvas()
  const { onOverview } = useAtlas()
  const away = Boolean(focusedModule && focusedModule !== id)
  return (
    <div
      data-tone={data.changes ? data.tone : undefined}
      className={cn(
        "group @container h-full w-full rounded-[24px] border-[1.5px] bg-card/45 transition-[opacity,border-color] duration-160",
        !data.open && "cursor-zoom-in",
        // A frame holding changes takes the colour of the most pressing one.
        data.changes && data.tone && !data.apart
          ? "border-tone/45"
          : "border-line",
        !data.open &&
          (data.changes && data.tone && !data.apart
            ? "hover:border-tone/80"
            : "hover:border-ink-3/50"),
        data.apart && "border-dashed",
        trailActive && "opacity-80",
        away && "opacity-35"
      )}
    >
      <div className="relative flex h-[56px] items-center gap-2.5 px-6">
        <span
          className="truncate leading-[1.2] font-medium text-ink"
          style={steady(16, 34)}
        >
          {data.title}
        </span>
        <span
          className={cn(
            "shrink-0 leading-[1.2]",
            data.changes ? "font-medium text-ink-2" : "text-ink-3"
          )}
          style={steady(12, 26)}
        >
          {data.changes
            ? t.moduleChanges(data.changes)
            : t.moduleFlows(data.flows)}
        </span>
        {/* One button in one place opens the module and closes it again, so the way in and
            the way back are never a guess. It says so in words wherever the frame has the
            room, and with its glyph alone on a narrow cell until it is pointed at. Laid over
            the header, so a module's name never gives up room to it. */}
        <button
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
            "nodrag nopan absolute top-1/2 right-4 inline-flex h-7 -translate-y-1/2 items-center gap-1 rounded-full bg-card px-2.5 text-[12px] leading-4 font-medium text-ink-2 shadow-[var(--shadow-node)] ring-1 ring-line transition-colors duration-160 hover:text-ink hover:ring-ink-3/50",
            data.open
              ? "cursor-pointer"
              : "cursor-zoom-in group-hover:text-ink group-hover:ring-ink-3/50"
          )}
        >
          {data.open ? (
            <Minimize2 aria-hidden className="size-3.5" />
          ) : (
            <Maximize2 aria-hidden className="size-3.5" />
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
        </button>
      </div>
    </div>
  )
}

/**
 * The name of a flow over its steps, and nothing beside it: what starts the flow is its
 * first card, and what is left out is said where it is left out. With no change to read,
 * it offers a walk through the flow.
 */
export function LabelView({ data }: NodeProps<LabelNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const { onRun } = useAtlas()
  const away = outOfFocus(canvas, data.flowId || "__offmap")
  return (
    <div
      className={cn(
        "flex h-full min-w-0 items-end gap-2.5 pb-2.5 transition-opacity duration-160",
        away && "opacity-35"
      )}
    >
      <span
        title={data.name}
        className={cn(
          "min-w-0 truncate leading-[1.25] font-medium text-ink",
          data.code && "font-mono font-normal",
          data.struck &&
            "text-ink-2 line-through decoration-ink decoration-[1.5px]"
        )}
        style={steady(14, 30)}
      >
        {data.name}
      </span>
      {data.code && (
        <span className="shrink-0 rounded-[5px] bg-field px-1 pb-px text-[12px] leading-4 text-ink-3">
          {t.skeletonTag}
        </span>
      )}
      {data.flowId && !data.struck && !canvas.focus && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            onRun(data.flowId)
          }}
          className="nodrag nopan inline-flex shrink-0 items-center gap-1 rounded-full bg-card px-2 py-0.5 text-[12px] leading-4 font-medium text-ink-2 shadow-[var(--shadow-node)] ring-1 ring-line transition-colors duration-160 hover:text-ink"
        >
          <Play aria-hidden className="size-3" />
          {t.runFlow}
        </button>
      )}
    </div>
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
  main: Play,
  root: Play,
}

/** A change that sits on no flow: kept on the map so it is not lost. */
export function OffMapView({ id, data }: NodeProps<OffMapNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const away = outOfFocus(canvas, "__offmap")
  const change = data.coupon.change
  const status = statusOf(change.tests)
  const picked = canvas.apart === id
  const out =
    !picked &&
    !matches(
      { risky: data.coupon.risky, status, categories: data.coupon.categories },
      canvas.filter
    )
  return (
    <div
      data-tone={data.coupon.tone}
      className={cn(
        "relative flex h-full w-full cursor-pointer flex-col justify-between rounded-[18px] border-[1.5px] border-dashed border-tone/60 bg-card p-3 shadow-[var(--shadow-node)] transition-[opacity,box-shadow,border-color] duration-160 hover:shadow-[var(--shadow-node-hover)]",
        picked && PICKED,
        out && "opacity-60 shadow-none",
        away && "opacity-35"
      )}
    >
      <span
        aria-hidden
        className="far-mark pointer-events-none absolute -inset-px rounded-[18px]"
      />
      <NumberDisc
        no={data.coupon.no}
        className="absolute -top-2 -left-2 z-[7]"
      />
      {(data.coupon.risky || status !== "tested") && (
        <ReviewBadge risky={data.coupon.risky} status={status} t={t} />
      )}
      <p className="line-clamp-2 text-[13px] leading-[19px] text-tone-ink">
        {shortSummary(change) ?? t.changeKind[change.kind]}
      </p>
      <StatusMark
        status={status}
        label={t.coverage[coverageKind(change.tests)]}
        className="text-[12px] leading-4 text-ink-2"
      />
    </div>
  )
}

/** What else a change touches: the same change on another flow, or a flow that may reach it. */
export function RelationView({
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<RelationEdge>) {
  const { trailActive, stopNo } = useCanvas()
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    curvature: 0.4,
  })
  // What a change also touches is drawn while that change is picked, not all the time.
  const hidden = Boolean(data?.change) && data?.no !== stopNo
  const tone = "var(--edge-strong)"
  return (
    <>
      <path
        d={path}
        fill="none"
        className="react-flow__edge-path transition-opacity duration-160"
        style={{
          stroke: tone,
          strokeWidth: 1.4,
          strokeDasharray: data?.change || data?.candidate ? "5 5" : undefined,
          opacity: hidden ? 0 : trailActive ? 0.2 : data?.change ? 0.8 : 0.5,
        }}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "nodrag nopan pointer-events-none absolute rounded-full bg-card px-2 py-0.5 text-[12px] leading-4 font-medium shadow-[var(--shadow-node)] ring-1 transition-opacity duration-160",
              data.change
                ? "text-ink ring-edge-strong/40"
                : "text-ink-2 ring-line"
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              opacity: hidden ? 0 : trailActive ? 0.3 : 1,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

/** A flow as one row: the change leaves it alone, or it is gone after it. */
export function RowView({ id, data }: NodeProps<RowNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const away = outOfFocus(canvas, data.flowId)
  const Icon = (data.entry && ENTRY_ICON[data.entry]) || Workflow
  return (
    <div
      // A flow that is gone carries no verdict: it rings in the plain colour.
      data-tone={data.struck ? "unsure" : undefined}
      className={cn(
        "relative flex h-full w-full cursor-pointer items-center gap-2 rounded-[14px] border border-line bg-card py-1.5 pr-3.5 pl-1.5 shadow-[var(--shadow-node)] transition-[opacity,box-shadow] duration-160 hover:shadow-[var(--shadow-node-hover)]",
        data.struck && "border-dashed",
        canvas.apart === id && PICKED,
        data.struck &&
          canvas.filter &&
          canvas.apart !== id &&
          "opacity-60 shadow-none",
        away && "opacity-35"
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
      <span className="flex size-7 shrink-0 items-center justify-center rounded-[8px] bg-field text-ink-3">
        <Icon aria-hidden className="size-3.5" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span
          title={data.name}
          className={cn(
            "truncate text-[14px] leading-5 text-ink",
            data.code && "font-mono text-[13px] text-ink-2",
            data.struck &&
              "text-ink-2 line-through decoration-ink decoration-[1.5px]"
          )}
        >
          {data.name}
        </span>
        {data.summary && (
          <span
            title={data.summary}
            className="truncate text-[12px] leading-[17px] text-ink-3"
          >
            {data.summary}
          </span>
        )}
      </span>
      {data.code && data.passing && !data.struck && (
        // Its name is still code, and the right of the row no longer says why.
        <span className="shrink-0 rounded-[5px] bg-field px-1 text-[12px] leading-4 text-ink-3">
          {t.skeletonTag}
        </span>
      )}
      <span
        className={cn(
          "shrink-0 text-[12px] leading-4",
          data.passing && !data.struck ? "font-medium text-ink-2" : "text-ink-3"
        )}
      >
        {data.struck
          ? t.removed
          : data.passing
            ? t.changesPass(data.passing)
            : data.pending
              ? // The tile already shows what starts it; the room goes to its name.
                t.notDescribed
              : [
                  data.entry && t.entryKind[data.entry],
                  data.code ? t.skeletonTag : t.stepsCount(data.steps),
                ]
                  .filter(Boolean)
                  .join(" · ")}
      </span>
    </div>
  )
}

/** The lookups and upkeep of a module in one line; opening the module lists them. */
export function MoreView({ data }: NodeProps<MoreNode>) {
  const { t, focusedModule } = useCanvas()
  return (
    <div
      className={cn(
        "flex h-full w-full cursor-pointer items-center gap-1.5 rounded-[14px] border border-dashed border-line px-3 text-[13px] leading-[18px] text-ink-2 transition-[opacity,color,border-color] duration-160 hover:border-ink-3/50 hover:text-ink",
        focusedModule && "opacity-35"
      )}
    >
      <ChevronDown aria-hidden className="size-3.5 shrink-0" />
      <span className="truncate">{t.supportingRow(data.count)}</span>
    </div>
  )
}

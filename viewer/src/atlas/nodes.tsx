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
  ZoomIn,
  type LucideIcon,
} from "lucide-react"

import { StatusMark } from "@/canvas/step-node"
import { outOfFocus, useCanvas } from "@/canvas/context"
import { cn } from "@/lib/utils"
import { statusOf } from "@/model"
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

/** The card whose details are open, ringed the way a picked change is. */
const PICKED =
  "border-solid border-change shadow-[0_0_0_3px_rgb(226_134_11_/_0.12),var(--shadow-node-hover)]"

interface AtlasHandlers {
  onRun: (flowId: string) => void
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
  const away = Boolean(focusedModule && focusedModule !== id)
  return (
    <div
      className={cn(
        "group h-full w-full rounded-[24px] border-[1.5px] bg-white/45 transition-[opacity,border-color] duration-160",
        !data.open && "cursor-zoom-in",
        data.changes && !data.apart ? "border-change/45" : "border-line",
        !data.open &&
          (data.changes && !data.apart
            ? "hover:border-change/80"
            : "hover:border-ink-3/50"),
        data.apart && "border-dashed",
        trailActive && "opacity-80",
        away && "opacity-35"
      )}
    >
      <div className="relative flex h-[56px] items-center gap-2.5 px-6">
        <span
          className="truncate leading-[1.2] font-medium text-ink"
          style={steady(15, 34)}
        >
          {data.title}
        </span>
        <span
          className={cn(
            "shrink-0 leading-[1.2]",
            data.changes ? "text-change-ink" : "text-ink-3"
          )}
          style={steady(12, 26)}
        >
          {data.changes
            ? t.moduleChanges(data.changes)
            : t.moduleFlows(data.flows)}
        </span>
        {!data.open && (
          // Laid over the header, so a module's name never gives up room to a hint.
          <span className="pointer-events-none absolute top-1/2 right-4 inline-flex -translate-y-1/2 items-center gap-1 rounded-full bg-card px-2 py-0.5 text-[12px] leading-4 text-ink-3 opacity-0 shadow-[var(--shadow-node)] ring-1 ring-line transition-opacity duration-160 group-hover:opacity-100">
            <ZoomIn aria-hidden className="size-3.5" />
            {t.openModule}
          </span>
        )}
      </div>
    </div>
  )
}

/**
 * The name of a flow over its steps. Cut down to a change it says how much of the flow is
 * on show; with no change to read, it offers a walk through the flow.
 */
export function LabelView({ data }: NodeProps<LabelNode>) {
  const canvas = useCanvas()
  const { t } = canvas
  const { onRun } = useAtlas()
  const away = outOfFocus(canvas, data.flowId || "__offmap")
  const Entry = data.entry ? ENTRY_ICON[data.entry] : undefined
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
        style={steady(13, 30)}
      >
        {data.name}
      </span>
      {data.code && (
        <span className="shrink-0 rounded-[5px] bg-field px-1 pb-px text-[11px] leading-4 text-ink-3">
          {t.skeletonTag}
        </span>
      )}
      {Entry && data.entry && (
        <span className="inline-flex shrink-0 items-center gap-1 pb-px text-[12px] leading-4 text-ink-3">
          <Entry aria-hidden className="size-3.5" />
          {t.entryKind[data.entry]}
        </span>
      )}
      {data.shown !== undefined && (
        <span className="shrink-0 pb-px text-[12px] leading-4 text-ink-3">
          {t.shownSteps(data.shown, data.steps)}
        </span>
      )}
      {data.flowId && !data.struck && !canvas.focus && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            onRun(data.flowId)
          }}
          className="nodrag nopan inline-flex shrink-0 items-center gap-1 rounded-full bg-card px-2 py-0.5 text-[11.5px] leading-4 font-medium text-ink-2 shadow-[var(--shadow-node)] ring-1 ring-line transition-colors duration-160 hover:text-ink"
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
  return (
    <div
      className={cn(
        "relative flex h-full w-full cursor-pointer flex-col justify-between rounded-[18px] border border-dashed border-change/60 bg-card p-3 shadow-[var(--shadow-node)] transition-[opacity,box-shadow,border-color] duration-160 hover:shadow-[var(--shadow-node-hover)]",
        canvas.apart === id && PICKED,
        away && "opacity-35"
      )}
    >
      <span
        aria-hidden
        className="far-mark pointer-events-none absolute -inset-px rounded-[18px]"
      />
      <p className="line-clamp-3 text-[13px] leading-[19px] text-change-ink">
        {change.explanation?.summary ?? t.changeKind[change.kind]}
      </p>
      <StatusMark
        status={status}
        label={t.status[status]}
        className="text-[11.5px] leading-4 text-ink-2"
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
  const tone = data?.change ? "var(--change)" : "var(--edge-strong)"
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
              "nodrag nopan pointer-events-none absolute rounded-full bg-card px-2 py-0.5 text-[11.5px] leading-4 font-medium shadow-[var(--shadow-node)] ring-1 transition-opacity duration-160",
              data.change
                ? "text-change-ink ring-change/45"
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
      className={cn(
        "flex h-full w-full cursor-pointer items-center gap-2 rounded-[14px] border border-line bg-card py-1.5 pr-3.5 pl-1.5 shadow-[var(--shadow-node)] transition-[opacity,box-shadow] duration-160 hover:shadow-[var(--shadow-node-hover)]",
        data.struck && "border-dashed",
        canvas.apart === id && PICKED,
        away && "opacity-35"
      )}
    >
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
            "truncate text-[13.5px] leading-5 text-ink",
            data.code && "font-mono text-[12.5px] text-ink-2",
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
      <span
        className={cn(
          "shrink-0 text-[11.5px] leading-4",
          data.passing && !data.struck ? "text-change-ink" : "text-ink-3"
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
        "flex h-full w-full cursor-pointer items-center gap-1.5 rounded-[14px] border border-dashed border-line px-3 text-[12.5px] leading-[18px] text-ink-2 transition-[opacity,color,border-color] duration-160 hover:border-ink-3/50 hover:text-ink",
        focusedModule && "opacity-35"
      )}
    >
      <ChevronDown aria-hidden className="size-3.5 shrink-0" />
      <span className="truncate">{t.supportingRow(data.count)}</span>
    </div>
  )
}

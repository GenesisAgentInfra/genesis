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
  Clock,
  Code,
  Globe,
  ListTodo,
  Play,
  SquareTerminal,
  type LucideIcon,
} from "lucide-react"

import { StatusMark } from "@/canvas/step-node"
import { useCanvas } from "@/canvas/context"
import { cn } from "@/lib/utils"
import { statusOf } from "@/model"
import type { EntryKind } from "@/types"
import type {
  ActorNode,
  EntryEdge,
  LabelNode,
  ModuleNode,
  OffMapNode,
  RelationEdge,
} from "./build"

/** Text that keeps about the same size on screen however far the reader zooms out. */
const steady = (px: number, max: number) => ({
  fontSize: `clamp(${px}px, calc(${px}px / var(--zoom, 1)), ${max}px)`,
})

interface AtlasHandlers {
  onRun: (flowId: string) => void
}
export const AtlasContext = React.createContext<AtlasHandlers | null>(null)
function useAtlas(): AtlasHandlers {
  const value = React.useContext(AtlasContext)
  if (!value) throw new Error("atlas context missing")
  return value
}

/** A module: a large frame around its flows, named so it reads from far away. */
export function ModuleView({ data }: NodeProps<ModuleNode>) {
  const { t, trailActive } = useCanvas()
  return (
    <div
      className={cn(
        "h-full w-full cursor-zoom-in rounded-[32px] border-[1.5px] bg-white/45 transition-[opacity,border-color] duration-160",
        data.changes && !data.apart ? "border-change/45" : "border-line",
        data.apart && "border-dashed",
        trailActive && "opacity-80"
      )}
    >
      <div className="flex h-[88px] items-center gap-3 px-8">
        <span
          className="truncate leading-[1.2] font-medium text-ink"
          style={steady(15, 56)}
        >
          {data.title}
        </span>
        <span
          className={cn(
            "shrink-0 leading-[1.2]",
            data.changes ? "text-change-ink" : "text-ink-3"
          )}
          style={steady(12, 40)}
        >
          {data.changes
            ? t.moduleChanges(data.changes)
            : t.moduleFlows(data.flows)}
        </span>
      </div>
    </div>
  )
}

/** The name of a flow over its steps, with the way to watch it run. */
export function LabelView({ data }: NodeProps<LabelNode>) {
  const { t } = useCanvas()
  const { onRun } = useAtlas()
  return (
    <div className="flex h-full min-w-0 items-end gap-2.5 pb-2.5">
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
      {data.changes > 0 && (
        <span className="shrink-0 pb-px text-[12px] leading-4 text-change-ink">
          {t.moduleChanges(data.changes)}
        </span>
      )}
      {data.code && (
        <span className="shrink-0 rounded-[5px] bg-field px-1 pb-px text-[11px] leading-4 text-ink-3">
          {t.skeletonTag}
        </span>
      )}
      {data.flowId && !data.struck && (
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

const ACTOR_ICON: Record<EntryKind, LucideIcon> = {
  http_route: Globe,
  cli_command: SquareTerminal,
  task: ListTodo,
  scheduled: Clock,
  public_api: Code,
  agent_tool: Bot,
  main: Play,
  root: Play,
}

/** A way in: requests, tasks, schedules. Each line leaves it for a flow it starts. */
export function ActorView({ data }: NodeProps<ActorNode>) {
  const { t, trailActive } = useCanvas()
  const Icon = ACTOR_ICON[data.kind]
  return (
    <div
      className={cn(
        "flex h-full items-center gap-2.5 rounded-full border border-line bg-card pr-4 pl-2 shadow-[var(--shadow-node)] transition-opacity duration-160",
        trailActive && "opacity-60"
      )}
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-field text-ink-2">
        <Icon aria-hidden className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="truncate text-[13.5px] leading-5 font-medium text-ink">
          {t.entryKind[data.kind]}
        </div>
        <div className="text-[11.5px] leading-4 text-ink-3">
          {t.moduleFlows(data.flows)}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        id="out"
        isConnectable={false}
      />
    </div>
  )
}

/** A change that sits on no flow: kept on the map so it is not lost. */
export function OffMapView({ data }: NodeProps<OffMapNode>) {
  const { t } = useCanvas()
  const change = data.coupon.change
  const status = statusOf(change.tests)
  return (
    <div className="flex h-full w-full cursor-pointer flex-col justify-between rounded-[18px] border border-dashed border-change/60 bg-card p-3 shadow-[var(--shadow-node)] hover:shadow-[var(--shadow-node-hover)]">
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
  const { trailActive } = useCanvas()
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    curvature: 0.4,
  })
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
          opacity: trailActive ? 0.2 : data?.change ? 0.7 : 0.5,
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
              opacity: trailActive ? 0.3 : 1,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

/** A path through points at right angles, its corners rounded. */
function orthogonal(points: { x: number; y: number }[], radius = 12): string {
  const parts = [`M${points[0].x},${points[0].y}`]
  for (let i = 1; i < points.length - 1; i++) {
    const [a, b, c] = [points[i - 1], points[i], points[i + 1]]
    const before = Math.hypot(b.x - a.x, b.y - a.y)
    const after = Math.hypot(c.x - b.x, c.y - b.y)
    const r = Math.min(radius, before / 2, after / 2)
    if (!r) {
      parts.push(`L${b.x},${b.y}`)
      continue
    }
    const inX = b.x - ((b.x - a.x) / before) * r
    const inY = b.y - ((b.y - a.y) / before) * r
    const outX = b.x + ((c.x - b.x) / after) * r
    const outY = b.y + ((c.y - b.y) / after) * r
    parts.push(`L${inX},${inY}`, `Q${b.x},${b.y} ${outX},${outY}`)
  }
  const last = points[points.length - 1]
  parts.push(`L${last.x},${last.y}`)
  return parts.join(" ")
}

/** From a way in to the flow it starts, along the gutters, never across another module. */
export function EntryView({
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<EntryEdge>) {
  const { trailActive, current } = useCanvas()
  if (!data) return null
  const points = [
    { x: sourceX, y: sourceY },
    { x: data.busX, y: sourceY },
  ]
  if (data.gapY !== undefined)
    points.push({ x: data.busX, y: data.gapY }, { x: data.laneX, y: data.gapY })
  else points.push({ x: data.laneX, y: sourceY })
  points.push({ x: data.laneX, y: targetY }, { x: targetX, y: targetY })
  // Drop the bend where the lane already is the bus.
  const path = orthogonal(
    points.filter(
      (point, index) =>
        index === 0 ||
        point.x !== points[index - 1].x ||
        point.y !== points[index - 1].y
    )
  )
  return (
    <path
      d={path}
      fill="none"
      className="react-flow__edge-path transition-opacity duration-160"
      style={{
        stroke: "var(--edge)",
        strokeWidth: 1.25,
        opacity: trailActive || current ? 0.45 : 1,
      }}
    />
  )
}

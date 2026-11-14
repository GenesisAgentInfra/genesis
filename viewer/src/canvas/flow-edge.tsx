import * as React from "react"
import { EdgeLabelRenderer, type EdgeProps } from "@xyflow/react"
import { ChevronDown } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { useCanvas } from "./context"
import { DRAW_MS, HEAD_EARLY, HEAD_MS } from "./emphasis"
import {
  EDGE_LABEL_LIMIT,
  isLongEdgeLabel,
  type FlowEdge as FlowEdgeType,
} from "./graph"
import { orthogonal } from "./path"

/** How round the corners of a step back are. */
const LOOP_R = 14

/**
 * A thin curve. The way in to the current change is dark and still; the edges leaving it
 * carry the ripple across the visible downstream branches. A walk uses a travelling dot.
 * Loops retain their dashed stroke and unrelated edges step back.
 */
export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<FlowEdgeType>) {
  const canvas = useCanvas()
  const back = Boolean(data?.back)
  // The layout says where the line runs; a line it gave no corners goes straight from
  // port to port.
  const points = data?.points ?? [
    { x: sourceX, y: sourceY },
    { x: targetX, y: targetY },
  ]
  const path = back ? orthogonal(points, LOOP_R, true) : orthogonal(points)
  const labelX = data?.labelAt?.x ?? (sourceX + targetX) / 2
  const labelY = data?.labelAt?.y ?? (sourceY + targetY) / 2
  const label = data?.label
  const longLabel = Boolean(label && isLongEdgeLabel(label))
  // A line that stands for steps left out is dotted, like an ellipsis.
  const skipped = Boolean(data?.skipped)
  const look = canvas.line(id, {
    back,
    uncertain: Boolean(data?.uncertain),
    skipped,
  })
  const { dark, impact, dashed, draws, travels, start, duration } = look
  const motionRef = React.useRef<SVGAnimateMotionElement>(null)
  const fadeRef = React.useRef<SVGAnimateElement>(null)

  React.useEffect(() => {
    if (!travels) return
    motionRef.current?.beginElementAt(start / 1000)
    fadeRef.current?.beginElementAt(start / 1000)
  }, [travels, start, look.key])

  const edge = data?.exception ? "edge-exception" : "edge"
  const arrow = data?.exception ? "arrow-exception" : "arrow"
  const stroke =
    impact && !data?.exception
      ? "var(--select)"
      : `var(--${edge}${dark ? "-strong" : ""})`
  const marker =
    impact && !data?.exception
      ? "arrow-impact"
      : `${arrow}${dark ? "-strong" : ""}`
  const quietOpacity = 0.38
  const opacity = (look.quiet ? quietOpacity : 1) * (look.away ? 0.35 : 1)
  const overlay = impact && look.entering
  const drawBase = draws && !impact
  const dash = skipped ? "1.5 5" : dashed ? "4 4" : undefined
  const timed = {
    "--edge-delay": `${start}ms`,
    "--edge-duration": `${duration}ms`,
  } as React.CSSProperties
  return (
    <>
      <path
        d={path}
        fill="none"
        className="react-flow__edge-interaction"
        stroke="transparent"
        strokeWidth={16}
      />
      <path
        d={path}
        fill="none"
        pathLength={drawBase ? 1 : undefined}
        markerEnd={drawBase ? undefined : `url(#${overlay ? arrow : marker})`}
        data-impact={impact ? "" : undefined}
        className={cn(
          "react-flow__edge-path map-edge",
          drawBase && "edge-draw",
          !impact && look.entering && dashed && "edge-fade"
        )}
        // Walks restart their own animations; a change always leaves its base path in place.
        key={!impact && look.entering ? look.key : "rest"}
        style={{
          ...timed,
          stroke: overlay ? `var(--${edge})` : stroke,
          strokeWidth: dark && !overlay ? 2.5 : 2,
          strokeDasharray: dash,
          strokeLinecap: skipped ? "round" : undefined,
          opacity: overlay ? opacity * quietOpacity : opacity,
        }}
      />
      {overlay && (
        <path
          key={look.key}
          d={path}
          fill="none"
          pathLength={draws ? 1 : undefined}
          markerEnd={draws ? undefined : `url(#${marker})`}
          className={cn("map-impact-edge", draws ? "edge-draw" : "edge-fade")}
          style={{
            ...timed,
            stroke,
            strokeWidth: 2.5,
            strokeDasharray: dash,
            strokeLinecap: skipped ? "round" : undefined,
            opacity,
          }}
        />
      )}
      {draws && (
        // The arrowhead of a line that draws itself, coming up as the line arrives.
        <path
          key={`head-${look.key}`}
          d={path}
          fill="none"
          stroke="transparent"
          markerEnd={`url(#${marker})`}
          className={cn("edge-fade", impact && "map-impact-edge")}
          style={{
            opacity,
            ["--edge-delay" as string]: `${start + duration - (impact ? duration / 3 : HEAD_EARLY)}ms`,
            ["--edge-duration" as string]: `${impact ? duration / 3 : HEAD_MS}ms`,
          }}
        />
      )}
      {travels && (
        <circle
          key={`dot-${look.key}`}
          r={3.5}
          fill="var(--edge-strong)"
          opacity={0}
        >
          <animateMotion
            ref={motionRef}
            begin="indefinite"
            dur={`${DRAW_MS}ms`}
            path={path}
            calcMode="spline"
            keyPoints="0;1"
            keyTimes="0;1"
            keySplines="0.45 0 0.55 1"
            fill="freeze"
          />
          <animate
            ref={fadeRef}
            begin="indefinite"
            attributeName="opacity"
            dur={`${DRAW_MS}ms`}
            values="0;1;1;0"
            keyTimes="0;0.12;0.85;1"
            fill="freeze"
          />
        </circle>
      )}
      {label && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "map-edge-label nodrag nopan absolute w-max text-body-s font-medium whitespace-nowrap",
              longLabel ? "pointer-events-auto" : "pointer-events-none px-xs",
              data?.exception ? "text-risk-ink" : "text-ink-2"
            )}
            style={
              {
                transform: `translate(-50%, -100%) translate(${labelX}px, ${labelY - 2}px)`,
                maxWidth: longLabel ? EDGE_LABEL_LIMIT : undefined,
                "--edge-label-opacity": opacity,
              } as React.CSSProperties
            }
          >
            {longLabel ? (
              <Popover>
                <PopoverTrigger
                  aria-label={label}
                  render={<Button variant="ghost" size="xs" />}
                  className="h-auto max-w-full justify-start gap-xxs rounded-md px-xs py-0 text-body-s text-inherit hover:text-inherit"
                >
                  <span className="min-w-0 truncate">{label}</span>
                  <ChevronDown aria-hidden className="size-3" />
                </PopoverTrigger>
                <PopoverContent
                  side="top"
                  className="text-body-m [overflow-wrap:anywhere]"
                >
                  {label}
                </PopoverContent>
              </Popover>
            ) : (
              label
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

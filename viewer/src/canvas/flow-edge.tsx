import * as React from "react"
import { EdgeLabelRenderer, type EdgeProps } from "@xyflow/react"

import { cn } from "@/lib/utils"
import { useCanvas } from "./context"
import { DRAW_MS, HEAD_EARLY, HEAD_MS } from "./emphasis"
import type { FlowEdge as FlowEdgeType } from "./graph"
import { orthogonal } from "./path"

/** How round the corners of a step back are. */
const LOOP_R = 14

/**
 * A thin curve. The way in to the current change is dark and still; the edges leaving it
 * carry the ripple: they draw themselves outward while a small dot rides the tip. Loops on
 * the change stay in view; everything else steps back.
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
  // A line that stands for steps left out is dotted, like an ellipsis.
  const skipped = Boolean(data?.skipped)
  const look = canvas.line(id, {
    back,
    uncertain: Boolean(data?.uncertain),
    skipped,
  })
  const { dark, dashed, draws, travels, start } = look
  const motionRef = React.useRef<SVGAnimateMotionElement>(null)
  const fadeRef = React.useRef<SVGAnimateElement>(null)

  React.useEffect(() => {
    if (!travels) return
    motionRef.current?.beginElementAt(start / 1000)
    fadeRef.current?.beginElementAt(start / 1000)
  }, [travels, start, look.key])

  const stroke = data?.exception
    ? dark
      ? "var(--edge-exception-strong)"
      : "var(--edge-exception)"
    : dark
      ? "var(--edge-strong)"
      : "var(--edge)"
  const marker = `arrow${data?.exception ? "-exception" : ""}${dark ? "-strong" : ""}`
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
        key={look.entering ? look.key : "rest"}
        d={path}
        fill="none"
        pathLength={draws ? 1 : undefined}
        // A line that is drawing itself gets its arrowhead once it has arrived.
        markerEnd={draws ? undefined : `url(#${marker})`}
        className={cn(
          "react-flow__edge-path transition-[opacity,stroke,stroke-width] duration-160",
          draws && "edge-draw",
          look.entering && dashed && "edge-fade"
        )}
        style={{
          stroke,
          strokeWidth: dark ? 2.5 : 2,
          strokeDasharray: draws
            ? undefined
            : skipped
              ? "1.5 5"
              : dashed
                ? "4 4"
                : undefined,
          strokeLinecap: skipped ? "round" : undefined,
          opacity: (look.quiet ? 0.7 : 1) * (look.away ? 0.35 : 1),
          ["--edge-delay" as string]: `${start}ms`,
          ["--edge-duration" as string]: `${DRAW_MS}ms`,
        }}
      />
      {draws && (
        // The arrowhead of a line that draws itself, coming up as the line arrives.
        <path
          key={`head-${look.key}`}
          d={path}
          fill="none"
          stroke="transparent"
          markerEnd={`url(#${marker})`}
          className="edge-fade"
          style={{
            ["--edge-delay" as string]: `${start + DRAW_MS - HEAD_EARLY}ms`,
            ["--edge-duration" as string]: `${HEAD_MS}ms`,
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
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "nodrag nopan absolute",
              "corner-full px-m py-xxs",
              "text-body-s font-medium",
              "pointer-events-none bg-card shadow-[var(--shadow-node)] ring-1 ring-line",
              data.exception
                ? "text-risk"
                : skipped
                  ? "text-ink-3"
                  : "text-ink-2"
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

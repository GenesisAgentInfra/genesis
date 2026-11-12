import * as React from "react"
import {
  EdgeLabelRenderer,
  getBezierPath,
  useStore,
  type EdgeProps,
  type ReactFlowState,
} from "@xyflow/react"

import { cn } from "@/lib/utils"
import { DRAW_FROM, DRAW_MS, useCanvas } from "./context"
import type { FlowEdge as FlowEdgeType } from "./graph"

/** How far a loop runs out past its ends, how round its corners are, how far from the cards. */
const LOOP_OUT = 24
const LOOP_R = 14
const LOOP_GAP = 28

/**
 * A loop goes back to an earlier step. Drawn straight it would run behind the cards in
 * between, so it leaves to the right, runs back in a lane clear of them (above or below,
 * whichever is nearer) and comes in from the left.
 */
function loopPath(sx: number, sy: number, tx: number, ty: number, y: number) {
  const right = sx + LOOP_OUT
  const left = tx - LOOP_OUT
  const turn = (y > sy ? 1 : -1) * LOOP_R
  const back = (y > ty ? 1 : -1) * LOOP_R
  return [
    `M${sx},${sy}`,
    `L${right - LOOP_R},${sy}`,
    `Q${right},${sy} ${right},${sy + turn}`,
    `L${right},${y - turn}`,
    `Q${right},${y} ${right - LOOP_R},${y}`,
    `L${left + LOOP_R},${y}`,
    `Q${left},${y} ${left},${y - back}`,
    `L${left},${ty + back}`,
    `Q${left},${ty} ${left + LOOP_R},${ty}`,
    `L${tx},${ty}`,
  ].join(" ")
}

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
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<FlowEdgeType>) {
  const {
    focus,
    current,
    routeEdges,
    outEdges,
    loopEdges,
    dotEdges,
    dimAll,
    run,
    armed,
    pending,
    animate,
    delay,
    trail,
    trailActive,
  } = useCanvas()
  // On the atlas many flows share the canvas; a loop only steps around cards of its own flow.
  const own = id.includes("::") ? id.slice(0, id.indexOf("::") + 2) : ""
  const back = Boolean(data?.back)
  // The lane a loop runs back in: just above or just below the cards between its ends.
  const lane = useStore(
    React.useCallback(
      (state: ReactFlowState) => {
        if (!back) return 0
        const from = Math.min(sourceX, targetX) - LOOP_OUT
        const to = Math.max(sourceX, targetX) + LOOP_OUT
        let top = Math.min(sourceY, targetY)
        let bottom = Math.max(sourceY, targetY)
        for (const node of state.nodeLookup.values()) {
          if (own && !node.id.startsWith(own)) continue
          if (node.id.includes("removed-")) continue
          const x = node.internals.positionAbsolute.x
          if (x > to || x + (node.measured.width ?? 0) < from) continue
          const y = node.internals.positionAbsolute.y
          top = Math.min(top, y)
          bottom = Math.max(bottom, y + (node.measured.height ?? 0))
        }
        const above = top - LOOP_GAP
        const below = bottom + LOOP_GAP
        const up = sourceY + targetY - 2 * above
        const down = 2 * below - sourceY - targetY
        return up < down ? above : below
      },
      [back, own, sourceX, sourceY, targetX, targetY]
    )
  )
  const [path, labelX, labelY] = back
    ? [
        loopPath(sourceX, sourceY, targetX, targetY, lane),
        (sourceX + targetX) / 2,
        lane,
      ]
    : getBezierPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
        curvature: 0.32,
      })
  const isRoute = routeEdges.has(id)
  const isOut = outEdges.has(id)
  const isLoop = loopEdges.has(id)
  // A walk through the flow draws its edges one after another, a dot riding each.
  const walkFrom = trail?.edges.get(id)
  const walked = walkFrom !== undefined
  const dark = walked || isRoute || (isOut && armed)
  const quiet =
    (trailActive && !walked) ||
    (focus &&
      !trailActive &&
      (dimAll ||
        ((current !== undefined || routeEdges.size > 0) &&
          !isRoute &&
          !isOut &&
          !isLoop)))
  const dashed = Boolean(data?.uncertain || (back && !dark))
  // A dashed line cannot draw itself; it fades in over the same stretch instead.
  const rippling = walked
    ? trail!.animate
    : isOut && armed && animate && !trailActive
  const draws = rippling && !dashed
  const travels = draws && (walked || dotEdges.has(id))
  const start = walked ? walkFrom : delay + DRAW_FROM
  const playKey = walked ? `walk-${trail!.run}` : `out-${run}`
  const motionRef = React.useRef<SVGAnimateMotionElement>(null)
  const fadeRef = React.useRef<SVGAnimateElement>(null)

  React.useEffect(() => {
    if (!travels) return
    motionRef.current?.beginElementAt(start / 1000)
    fadeRef.current?.beginElementAt(start / 1000)
  }, [travels, start, playKey])

  const stroke = data?.exception
    ? dark
      ? "var(--edge-exception-strong)"
      : "var(--edge-exception)"
    : dark
      ? "var(--edge-strong)"
      : "var(--edge)"
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
        key={rippling ? playKey : "rest"}
        d={path}
        fill="none"
        pathLength={draws ? 1 : undefined}
        className={cn(
          "react-flow__edge-path transition-[opacity,stroke,stroke-width] duration-160",
          draws && "edge-draw",
          rippling && dashed && "edge-fade"
        )}
        style={{
          stroke,
          strokeWidth: dark ? 1.6 : 1.25,
          strokeDasharray: draws ? undefined : dashed ? "4 4" : undefined,
          // Until the ripple draws them, the edges it will draw are not there yet.
          opacity: isOut && pending ? 0 : quiet ? 0.45 : 1,
          ["--edge-delay" as string]: `${start}ms`,
          ["--edge-duration" as string]: `${DRAW_MS}ms`,
        }}
      />
      {travels && (
        <circle key={`dot-${playKey}`} r={3.5} fill="var(--change)" opacity={0}>
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
              "nodrag nopan pointer-events-none absolute rounded-full bg-card px-2 py-0.5 text-[11.5px] leading-4 shadow-[var(--shadow-node)] ring-1 ring-line transition-opacity duration-160",
              data.exception ? "text-risk" : "text-ink-2"
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              opacity: isOut && pending ? 0 : quiet ? 0.6 : 1,
              // A label on a rippling edge comes up as its line starts to draw.
              transitionDelay: rippling ? `${start}ms` : "0ms",
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

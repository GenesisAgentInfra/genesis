import * as React from "react"
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useStore,
  useStoreApi,
  type NodeMouseHandler,
} from "@xyflow/react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { Crumbs } from "@/components/crumbs"
import { DetailPanel, type PanelSubject } from "@/components/detail-panel"
import { Headline } from "@/components/headline"
import {
  CUT_ARM,
  CanvasContext,
  DRAW_MS,
  GLIDE_ARM,
  GLIDE_MS,
  easeOut,
  type CanvasState,
  type Trail,
} from "@/canvas/context"
import { FlowEdge } from "@/canvas/flow-edge"
import {
  heightOf,
  type FlowEdge as FlowEdgeType,
  type StepNode as StepNodeType,
} from "@/canvas/graph"
import { StepNode } from "@/canvas/step-node"
import {
  SEP,
  buildAtlas,
  flowOfNode,
  mainPath,
  type AtlasNode,
  type LabelData,
  type ModuleData,
  type OffMapData,
} from "@/atlas/build"
import {
  ActorView,
  AtlasContext,
  EntryView,
  LabelView,
  ModuleView,
  OffMapView,
  RelationView,
} from "@/atlas/nodes"
import { cn } from "@/lib/utils"
import { STRINGS } from "@/i18n"
import { routeTo } from "@/layout"
import { reachOf, type Model } from "@/model"

const NODE_TYPES = {
  step: StepNode,
  module: ModuleView,
  label: LabelView,
  actor: ActorView,
  offmap: OffMapView,
}
const EDGE_TYPES = { flow: FlowEdge, relation: RelationView, entry: EntryView }
const PANEL_W = 384
const NONE = new Set<string>()
/** The walk through a flow: the camera's zoom, a pause per step, a longer one at a change. */
const WALK_ZOOM = 0.85
const WALK_LEAD = 560
const DWELL = 140
const LINGER = 560

type Selected =
  | { type: "step"; node: string }
  | { type: "offMap"; no: number }
  | { type: "removedFlow"; flowId: string }

interface Lit {
  current?: string
  next: Set<string>
  far: Set<string>
  routeSteps: Set<string>
  routeEdges: Set<string>
  outEdges: Set<string>
  loopEdges: Set<string>
  dotEdges: Set<string>
}
const DARK: Lit = {
  next: NONE,
  far: NONE,
  routeSteps: NONE,
  routeEdges: NONE,
  outEdges: NONE,
  loopEdges: NONE,
  dotEdges: NONE,
}

/** The panel slides in and out; with reduced motion it simply appears and goes. */
const panelMotion = (reduced: boolean) =>
  reduced
    ? { duration: 0 }
    : { duration: 0.26, ease: [0.16, 1, 0.3, 1] as const }

function useIsNarrow() {
  const [narrow, setNarrow] = React.useState(
    () => window.matchMedia("(max-width: 767px)").matches
  )
  React.useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)")
    const update = () => setNarrow(query.matches)
    query.addEventListener("change", update)
    return () => query.removeEventListener("change", update)
  }, [])
  return narrow
}

/** Edges leaving the change that are not much longer than the shortest one carry the dot. */
function dotted(edges: FlowEdgeType[], nodes: StepNodeType[]): Set<string> {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const lengths = edges.map((edge) => {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) return [edge.id, Infinity] as const
    const dx = target.position.x - (source.position.x + source.data.width)
    const dy =
      target.position.y +
      heightOf(target.data) / 2 -
      (source.position.y + heightOf(source.data) / 2)
    return [edge.id, Math.hypot(dx, dy)] as const
  })
  const shortest = Math.min(...lengths.map(([, length]) => length))
  return new Set(
    lengths.filter(([, length]) => length <= shortest * 2).map(([id]) => id)
  )
}

export function App({ model }: { model: Model }) {
  return (
    <ReactFlowProvider>
      <Viewer model={model} />
    </ReactFlowProvider>
  )
}

function Viewer({ model }: { model: Model }) {
  const t = STRINGS[model.lang]
  const reducedMotion = Boolean(useReducedMotion())
  const narrow = useIsNarrow()
  const flow = useReactFlow()
  const store = useStoreApi()
  const initialized = useNodesInitialized()
  const width = useStore((state) => state.width)
  const height = useStore((state) => state.height)
  const atlas = React.useMemo(() => buildAtlas(model, t), [model, t])
  const nodeById = React.useMemo(
    () => new Map(atlas.nodes.map((node) => [node.id, node])),
    [atlas]
  )
  const focus = model.stops.length > 0

  const [selected, setSelected] = React.useState<Selected>()
  // The change picked on the map: its card rings and what it leads to answers.
  const [current, setCurrent] = React.useState<{ node: string; no: number }>()
  const [play, setPlay] = React.useState({
    run: 0,
    armed: false,
    settled: false,
    delay: CUT_ARM,
  })
  const [trail, setTrail] = React.useState<Trail>()
  const [focused, setFocused] = React.useState<string>()
  const [ready, setReady] = React.useState(false)
  const headRef = React.useRef<HTMLDivElement>(null)
  const wrapper = React.useRef<HTMLDivElement>(null)
  const opener = React.useRef<HTMLElement | null>(null)
  const timers = React.useRef<number[]>([])
  const walks = React.useRef(0)

  // Names on the map keep their size on screen as the reader zooms out.
  React.useEffect(() => {
    const set = (zoom: number) =>
      wrapper.current?.style.setProperty("--zoom", String(zoom))
    set(store.getState().transform[2])
    return store.subscribe((state) => set(state.transform[2]))
  }, [store])

  React.useEffect(() => {
    document.documentElement.lang = model.lang === "zh" ? "zh-CN" : "en"
  }, [model.lang])

  const lit = React.useMemo<Lit>(() => {
    if (!current) return DARK
    const flowId = flowOfNode(current.node)
    const placed = flowId ? atlas.flows.get(flowId) : undefined
    if (!flowId || !placed) return DARK
    const local = current.node.slice(flowId.length + SEP.length)
    if (local.startsWith("removed-")) return { ...DARK, current: current.node }
    const prefix = (id: string) => `${flowId}${SEP}${id}`
    const reach = reachOf(placed.view, local)
    const route = routeTo(placed.view.layout, local)
    const out: FlowEdgeType[] = []
    const loopEdges = new Set<string>()
    for (const edge of placed.edges) {
      if (edge.data?.back) {
        if (edge.source === current.node || edge.target === current.node)
          loopEdges.add(edge.id)
      } else if (edge.source === current.node) out.push(edge)
    }
    const routeSteps = new Set([...route.steps].map(prefix))
    routeSteps.delete(current.node)
    return {
      current: current.node,
      next: new Set(reach.next.map(prefix)),
      far: new Set(reach.far.map(prefix)),
      routeSteps,
      routeEdges: new Set([...route.edges].map(prefix)),
      outEdges: new Set(out.map((edge) => edge.id)),
      loopEdges,
      dotEdges: out.length ? dotted(out, placed.nodes) : NONE,
    }
  }, [current, atlas])

  const subject = React.useMemo<PanelSubject | undefined>(() => {
    if (!selected) return undefined
    if (selected.type === "offMap") {
      const stop = model.stops[selected.no - 1]
      return { type: "offMap", coupons: stop?.coupon ? [stop.coupon] : [] }
    }
    if (selected.type === "removedFlow") {
      const view = model.flowById.get(selected.flowId)
      const stop = model.stops.find(
        (item) =>
          item.kind === "removed_flow" && item.flowId === selected.flowId
      )
      return {
        type: "removedFlow",
        name: view?.flow.name ?? "",
        code: view?.flow.stage === "skeleton",
        coupons: stop?.coupon ? [stop.coupon] : [],
      }
    }
    const node = nodeById.get(selected.node)
    if (!node || node.type !== "step") return undefined
    const step = node as StepNodeType
    return {
      type: "step",
      step: step.data.step,
      view: atlas.flows.get(flowOfNode(step.id) ?? "")?.view,
      ghost: step.data.ghost,
      coupons: step.data.coupons,
    }
  }, [selected, nodeById, atlas, model])
  const showPanel = Boolean(subject)
  const focusedTitle = focused
    ? (nodeById.get(focused)?.data as ModuleData | undefined)?.title
    : undefined

  React.useEffect(() => {
    document.title = focusedTitle ? `${focusedTitle} · Genesis` : "Genesis"
  }, [focusedTitle])

  /** The part of the screen left once the headline, the panel and the margins are set aside. */
  const area = React.useCallback(
    (withPanel: boolean) => {
      const head = headRef.current?.getBoundingClientRect()
      const top = Math.max(head ? head.bottom + 16 : 0, 24)
      const left = narrow ? 12 : 32
      const right = narrow ? 12 : withPanel ? PANEL_W + 40 : 32
      const bottom = narrow ? (withPanel ? height * 0.52 + 16 : 24) : 32
      return {
        x: left,
        y: top,
        w: Math.max(width - left - right, 80),
        h: Math.max(height - top - bottom, 80),
      }
    },
    [narrow, width, height]
  )
  const padding = React.useCallback(
    (withPanel: boolean) => {
      const box = area(withPanel)
      const px = (value: number): `${number}px` =>
        `${Math.max(Math.round(value), 0)}px`
      return {
        top: px(box.y),
        left: px(box.x),
        right: px(width - box.x - box.w),
        bottom: px(height - box.y - box.h),
      }
    },
    [area, width, height]
  )
  const glide = reducedMotion ? 0 : GLIDE_MS
  const motionOf = (duration: number) => ({
    duration,
    ease: easeOut,
    interpolate: "linear" as const,
  })

  const fitAll = React.useCallback(
    (duration: number, withPanel = false) =>
      void flow.fitView({
        padding: padding(withPanel),
        maxZoom: 1,
        minZoom: 0.05,
        duration,
        ease: easeOut,
        interpolate: "linear",
      }),
    [flow, padding]
  )
  const fitTo = (ids: string[], duration: number, withPanel = showPanel) =>
    void flow.fitView({
      nodes: ids.map((id) => ({ id })),
      padding: padding(withPanel),
      maxZoom: 1,
      minZoom: 0.05,
      ...motionOf(duration),
    })
  /** Put a node in the middle of the free area, at least this close. */
  const centerOn = (
    id: string,
    zoom: number,
    duration: number,
    withPanel: boolean
  ) => {
    const node = flow.getInternalNode(id)
    if (!node) return
    const box = area(withPanel)
    const cx =
      node.internals.positionAbsolute.x + (node.measured.width ?? 0) / 2
    const cy =
      node.internals.positionAbsolute.y + (node.measured.height ?? 0) / 2
    void flow.setCenter(
      cx + (width / 2 - (box.x + box.w / 2)) / zoom,
      cy + (height / 2 - (box.y + box.h / 2)) / zoom,
      { zoom, ...motionOf(duration) }
    )
  }
  const inView = (id: string, withPanel: boolean) => {
    const node = flow.getInternalNode(id)
    if (!node) return true
    const { x: vx, y: vy, zoom } = flow.getViewport()
    const box = area(withPanel)
    const left = node.internals.positionAbsolute.x * zoom + vx
    const top = node.internals.positionAbsolute.y * zoom + vy
    return (
      zoom >= 0.55 &&
      left >= box.x &&
      top >= box.y &&
      left + (node.measured.width ?? 0) * zoom <= box.x + box.w &&
      top + (node.measured.height ?? 0) * zoom <= box.y + box.h
    )
  }

  // The whole map, framed before its first paint.
  const framed = React.useRef(false)
  React.useLayoutEffect(() => {
    if (framed.current || !initialized || !width || !height) return
    framed.current = true
    fitAll(0)
    setReady(true)
  }, [initialized, width, height, fitAll])

  // A new window size keeps what was framed in frame.
  const size = React.useRef({ width, height })
  React.useEffect(() => {
    const before = size.current
    size.current = { width, height }
    if (!ready || (before.width === width && before.height === height)) return
    if (focused)
      void flow.fitView({
        nodes: [{ id: focused }],
        padding: padding(false),
        maxZoom: 1,
        minZoom: 0.05,
      })
    else fitAll(0)
    // Only the size matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height])

  const settle = React.useCallback(
    () =>
      setPlay((value) =>
        value.armed && value.settled
          ? value
          : { ...value, armed: true, settled: true }
      ),
    []
  )
  const stopWalk = React.useCallback(() => {
    for (const handle of timers.current) window.clearTimeout(handle)
    timers.current = []
    setTrail(undefined)
  }, [])

  const openPanel = (next: Selected) => {
    if (!showPanel)
      opener.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null
    setSelected(next)
  }
  const closePanel = () => {
    if (document.activeElement?.closest("[data-panel]")) opener.current?.focus()
    setSelected(undefined)
  }

  /** Pick a change on the map: it rings, and the steps it leads to answer. */
  const pick = (node: StepNodeType) => {
    const shown =
      node.data.coupons.find((coupon) => coupon.no === current?.no) ??
      node.data.coupons[0]
    const run = play.run + 1
    setCurrent({ node: node.id, no: shown.no })
    if (inView(node.id, true)) {
      setPlay({ run, armed: true, settled: false, delay: 0 })
      return
    }
    centerOn(node.id, Math.max(flow.getViewport().zoom, 0.8), glide, true)
    setPlay({
      run,
      armed: true,
      settled: false,
      delay: glide ? GLIDE_ARM : 0,
    })
  }

  // The camera follows the focus once the breadcrumbs above the headline have settled.
  const framedFocus = React.useRef<string | undefined>(undefined)
  React.useEffect(() => {
    if (!ready || framedFocus.current === focused) return
    framedFocus.current = focused
    if (focused)
      void flow.fitView({
        nodes: [{ id: focused }],
        padding: padding(showPanel),
        maxZoom: 1,
        minZoom: 0.05,
        ...motionOf(glide),
      })
    else fitAll(glide)
    // Runs when the focus changes; the rest is read fresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused, ready])
  const focusModule = (id: string) => setFocused(id)
  const toOverview = () => {
    stopWalk()
    setFocused(undefined)
    setCurrent(undefined)
    setSelected(undefined)
  }

  /** Walk through a flow the way it usually runs, the camera riding along. */
  const walk = (flowId: string) => {
    const placed = atlas.flows.get(flowId)
    if (!placed) return
    stopWalk()
    setSelected(undefined)
    setCurrent(undefined)
    const path = mainPath(placed)
    if (!path.steps.length) return
    const isChanged = (id: string) =>
      Boolean(
        (nodeById.get(id) as StepNodeType | undefined)?.data.coupons.length
      )
    const animate = !reducedMotion
    const steps = new Map<string, number>()
    const edges = new Map<string, number>()
    let at = animate ? WALK_LEAD : 0
    steps.set(path.steps[0], at)
    path.edges.forEach((edge, index) => {
      const from = path.steps[index]
      const start = at + (animate ? DWELL + (isChanged(from) ? LINGER : 0) : 0)
      edges.set(edge, start)
      at = start + (animate ? DRAW_MS : 0)
      steps.set(path.steps[index + 1], at)
    })
    walks.current += 1
    setTrail({
      run: walks.current,
      edges,
      steps,
      changed: new Set(path.steps.filter(isChanged)),
      animate,
    })
    if (!animate) {
      fitTo(path.steps, 0, false)
      return
    }
    centerOn(path.steps[0], WALK_ZOOM, WALK_LEAD - 40, false)
    for (const id of path.steps.slice(1)) {
      const arrive = steps.get(id)!
      timers.current.push(
        window.setTimeout(
          () => centerOn(id, WALK_ZOOM, 420, false),
          Math.max(arrive - 320, 0)
        )
      )
    }
  }

  const onNodeClick: NodeMouseHandler<AtlasNode> = (_, node) => {
    stopWalk()
    if (node.type === "module") {
      focusModule(node.id)
      return
    }
    if (node.type === "label") {
      const data = node.data as LabelData
      if (data.struck) openPanel({ type: "removedFlow", flowId: data.flowId })
      else if (data.flowId) {
        const placed = atlas.flows.get(data.flowId)
        if (placed)
          fitTo(
            placed.nodes.map((item) => item.id),
            glide
          )
      }
      return
    }
    if (node.type === "offmap") {
      openPanel({ type: "offMap", no: (node.data as OffMapData).coupon.no })
      return
    }
    if (node.type !== "step") return
    const step = node as StepNodeType
    openPanel({ type: "step", node: step.id })
    if (step.data.coupons.length && !step.data.removedFlow) pick(step)
    else if (!inView(step.id, true))
      centerOn(step.id, Math.max(flow.getViewport().zoom, 0.8), glide, true)
  }

  // Keys: Esc steps back (the walk, the panel, the picked change, the focused module).
  const keys = React.useRef({
    escape: () => {},
    other: () => {},
    enter: (id: string) => void id,
  })
  React.useEffect(() => {
    keys.current = {
      escape: () => {
        settle()
        if (trail) stopWalk()
        else if (selected) closePanel()
        else if (current) setCurrent(undefined)
        else if (focused) toOverview()
      },
      other: () => {
        settle()
        stopWalk()
      },
      enter: (id: string) => {
        const node = nodeById.get(id)
        if (node) onNodeClick({} as React.MouseEvent, node)
      },
    }
  })
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null
      if (target?.closest("[data-panel]")) {
        if (event.key === "Escape") keys.current.escape()
        return
      }
      if (
        target?.closest("[role=listbox], input, textarea, select, button") ||
        target?.isContentEditable
      )
        return
      if (event.key === "Escape") {
        keys.current.escape()
        return
      }
      if (event.key === "Enter" || event.key === " ") {
        const id = (target?.closest(".react-flow__node") as HTMLElement | null)
          ?.dataset.id
        if (id) {
          event.preventDefault()
          keys.current.enter(id)
        }
        return
      }
      keys.current.other()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const hint = React.useMemo(
    () => ({
      "node.a11yDescription.default": t.nodeHint,
      "node.a11yDescription.keyboardDisabled": t.nodeHint,
    }),
    [t]
  )
  const canvas: CanvasState = {
    t,
    focus,
    stopNo: current?.no,
    current: lit.current,
    next: lit.next,
    far: lit.far,
    routeSteps: lit.routeSteps,
    routeEdges: lit.routeEdges,
    outEdges: lit.outEdges,
    loopEdges: lit.loopEdges,
    dotEdges: lit.dotEdges,
    dimAll: false,
    selected: selected?.type === "step" ? selected.node : undefined,
    knownRisks: !model.hasReport,
    run: play.run,
    armed: play.armed,
    pending: Boolean(current) && !play.armed && !reducedMotion,
    animate: play.armed && !play.settled && !reducedMotion,
    delay: play.delay,
    trail,
    trailActive: Boolean(trail),
  }
  const walkRef = React.useRef(walk)
  React.useEffect(() => {
    walkRef.current = walk
  })
  const handlers = React.useMemo(
    () => ({ onRun: (flowId: string) => walkRef.current(flowId) }),
    []
  )

  return (
    <CanvasContext.Provider value={canvas}>
      <AtlasContext.Provider value={handlers}>
        <div
          className="relative h-dvh w-full overflow-hidden bg-canvas"
          onPointerDownCapture={(event) => {
            if ((event.target as HTMLElement).closest(".react-flow")) {
              settle()
              stopWalk()
            }
          }}
          onWheelCapture={(event) => {
            if ((event.target as HTMLElement).closest(".react-flow")) {
              settle()
              stopWalk()
            }
          }}
        >
          <div ref={wrapper} className="absolute inset-0">
            {atlas.nodes.length ? (
              <ReactFlow
                defaultNodes={atlas.nodes}
                defaultEdges={atlas.edges}
                nodeTypes={NODE_TYPES}
                edgeTypes={EDGE_TYPES}
                onNodeClick={onNodeClick}
                onPaneClick={() => {
                  setSelected(undefined)
                  setCurrent(undefined)
                }}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                edgesFocusable={false}
                ariaLabelConfig={hint}
                panOnScroll
                zoomOnScroll={false}
                zoomOnDoubleClick={false}
                minZoom={0.05}
                maxZoom={1.6}
                className={cn(!ready && "opacity-0")}
              />
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-[14px] text-ink-2">
                {t.noFlow}
              </div>
            )}
          </div>

          <div
            ref={headRef}
            className="pointer-events-none absolute top-3 left-3 z-10 flex max-w-[calc(100%-24px)] flex-col items-start gap-2"
          >
            {(!model.hasReport || focusedTitle) && (
              <Crumbs
                model={model}
                t={t}
                module={focusedTitle}
                onOverview={toOverview}
              />
            )}
            {model.hasReport && (
              <div
                className={
                  narrow
                    ? "w-[calc(100vw-24px)]"
                    : showPanel
                      ? "w-[min(600px,calc(100vw-448px))] min-w-[340px]"
                      : "w-[min(600px,calc(100vw-24px))]"
                }
              >
                <Headline
                  model={model}
                  t={t}
                  narrow={narrow}
                  compact={narrow && showPanel}
                />
              </div>
            )}
          </div>

          <AnimatePresence>
            {/* The strip behind the panel keeps cards from showing through the gap around it. */}
            {subject && !narrow && (
              <motion.div
                key="strip"
                aria-hidden
                initial={reducedMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={panelMotion(reducedMotion)}
                className="pointer-events-none absolute inset-y-0 right-0 z-[15] w-[408px] bg-canvas"
              />
            )}
            {subject && (
              <motion.aside
                key="panel"
                data-panel
                initial={
                  reducedMotion
                    ? false
                    : narrow
                      ? { opacity: 0, y: 24 }
                      : { opacity: 0, x: 20 }
                }
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={
                  reducedMotion
                    ? { opacity: 0 }
                    : narrow
                      ? { opacity: 0, y: 24 }
                      : { opacity: 0, x: 20 }
                }
                transition={panelMotion(reducedMotion)}
                className={cn(
                  "absolute z-20 overflow-hidden rounded-[20px] bg-card shadow-[var(--shadow-float)] ring-1 ring-line",
                  narrow
                    ? "inset-x-2 bottom-2 h-[52dvh]"
                    : "top-3 right-3 bottom-3 w-[384px]"
                )}
              >
                <DetailPanel
                  // Each new subject starts at the top with its code folded.
                  key={JSON.stringify(selected)}
                  model={model}
                  t={t}
                  subject={subject}
                  focus={current?.no}
                  onClose={closePanel}
                />
              </motion.aside>
            )}
          </AnimatePresence>
        </div>
      </AtlasContext.Provider>
    </CanvasContext.Provider>
  )
}

import * as React from "react"
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useStore,
  useStoreApi,
} from "@xyflow/react"
import { Maximize, Minus, Moon, Play, Plus, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DetailPanel, type PanelSubject } from "@/components/detail-panel"
import { Headline } from "@/components/headline"
import { MapMark } from "@/components/map-mark"
import {
  MAX_ZOOM,
  PANEL_W,
  ZOOM_MS,
  easeOut,
  readingArea,
  readingSpan,
  viewOf,
  type Scene,
  type Shot,
} from "@/canvas/camera"
import { CanvasContext, type CanvasState } from "@/canvas/context"
import {
  DARK,
  lineLook,
  litBy,
  stepLook,
  type Spotlight,
} from "@/canvas/emphasis"
import { FlowEdge } from "@/canvas/flow-edge"
import { type StepNode as StepNodeType } from "@/canvas/graph"
import { StepNode } from "@/canvas/step-node"
import {
  SEP,
  atlasDrawer,
  flowOfNode,
  flowsIn,
  type ModuleData,
} from "@/atlas/build"
import {
  AtlasContext,
  BoxView,
  FlowCardView,
  ModuleView,
  OffMapView,
  MoreView,
  RowView,
} from "@/atlas/nodes"
import { cn } from "@/lib/utils"
import { isEditorInteraction } from "../graphical/interaction-boundary"
import { STRINGS } from "@/i18n"
import type { Model } from "@/model"
import {
  START,
  act,
  beats,
  panelOf,
  pickedOf,
  type Act,
  type Place,
  type World,
} from "@/reader"
import { useTheme } from "@/theme"

const NODE_TYPES = {
  step: StepNode,
  module: ModuleView,
  flow: FlowCardView,
  offmap: OffMapView,
  row: RowView,
  more: MoreView,
  box: BoxView,
}
const EDGE_TYPES = {
  flow: FlowEdge,
}
/** Arrowheads for the lines, one per line colour. */
const ARROWS = [
  ["arrow", "var(--edge)"],
  ["arrow-strong", "var(--edge-strong)"],
  ["arrow-exception", "var(--edge-exception)"],
  ["arrow-exception-strong", "var(--edge-exception-strong)"],
] as const
/** How long cards take to slide to their places when a module opens or closes; the
 *  styles read it as `--morph`. */
const MORPH_MS = 320

/** Whether a media query holds, kept up to date. */
function useMedia(query: string) {
  const [holds, setHolds] = React.useState(
    () => window.matchMedia(query).matches
  )
  React.useEffect(() => {
    const list = window.matchMedia(query)
    const update = () => setHolds(list.matches)
    update()
    list.addEventListener("change", update)
    return () => list.removeEventListener("change", update)
  }, [query])
  return holds
}

/**
 * What is on show, kept while it leaves: when the value goes, the last one stays, marked
 * as leaving, until `done` is called at the end of its exit. Without an exit to wait for
 * (`animate` false) it goes at once.
 */
function usePresence<T>(value: T | undefined, animate: boolean) {
  const [last, setLast] = React.useState(value)
  if (value !== undefined && value !== last) setLast(value)
  if (value === undefined && last !== undefined && !animate) setLast(undefined)
  const done = React.useCallback(() => setLast(undefined), [])
  return {
    shown: value ?? (animate ? last : undefined),
    leaving: value === undefined && last !== undefined && animate,
    done,
  }
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
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)")
  const narrow = useMedia("(max-width: 767px)")
  const flow = useReactFlow()
  const store = useStoreApi()
  const initialized = useNodesInitialized()
  const width = useStore((state) => state.width)
  const height = useStore((state) => state.height)
  const { theme, toggle: toggleTheme } = useTheme()
  const focus = model.stops.length > 0

  const span = readingSpan(width || window.innerWidth)
  const atlasOf = React.useMemo(
    () => atlasDrawer(model, t, span),
    [model, t, span]
  )
  const world = React.useMemo<World>(
    () => ({ model, atlasOf, motion: !reducedMotion }),
    [model, atlasOf, reducedMotion]
  )

  // Where the reader is. Everything they do goes through `go`, which starts from where
  // they are now and leaves the rest to `act`.
  const [place, setPlace] = React.useState<Place>(START)
  const { focused, selected, current, walk } = place
  const now = React.useRef({ place, world })
  React.useEffect(() => {
    now.current = { place, world }
  })
  const opener = React.useRef<HTMLElement | null>(null)
  const go = React.useCallback((action: Act) => {
    const before = now.current.place
    const next = act(before, action, now.current.world)
    if (next === before) return
    // The keyboard goes back to where it was once the panel that took it closes.
    const active = document.activeElement
    if (!before.selected && next.selected)
      opener.current = active instanceof HTMLElement ? active : null
    if (before.selected && !next.selected && active?.closest("[data-panel]"))
      opener.current?.focus()
    now.current = { ...now.current, place: next }
    setPlace(next)
  }, [])

  const atlas = atlasOf(focused)
  const nodeById = React.useMemo(
    () => new Map(atlas.nodes.map((node) => [node.id, node])),
    [atlas]
  )
  // The map shows once it can be framed: its nodes measured, its screen known.
  const [ready, setReady] = React.useState(false)
  if (!ready && initialized && width && height) setReady(true)
  const [headlineHeight, setHeadlineHeight] = React.useState(0)
  const headRef = React.useRef<HTMLDivElement>(null)
  const wrapper = React.useRef<HTMLDivElement>(null)

  // Opening details can wrap or compact the headline without resizing the window.
  React.useLayoutEffect(() => {
    const head = headRef.current
    if (!head) return
    const measure = () => {
      const measured = head.getBoundingClientRect().height
      // A hidden tab or a hot-reloaded subtree can briefly report zero. Keep the last
      // visible size, and measure synchronously whenever the reading layout changes.
      if (measured > 0) setHeadlineHeight(measured)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(head)
    return () => observer.disconnect()
  }, [narrow, width, selected])

  // Names on the map keep their size on screen as the reader zooms out.
  React.useEffect(() => {
    const set = (zoom: number) => {
      const style = wrapper.current?.style
      style?.setProperty("--zoom", String(zoom))
      // Headings are lifted back to their size on screen, up to twice it.
      style?.setProperty("--lift", String(Math.min(2, Math.max(1, 1 / zoom))))
    }
    set(store.getState().transform[2])
    return store.subscribe((state) => set(state.transform[2]))
  }, [store])

  React.useEffect(() => {
    document.documentElement.lang = model.lang === "zh" ? "zh-CN" : "en"
  }, [model.lang])

  const lit = React.useMemo(
    () =>
      current
        ? litBy(atlas.flows.get(flowOfNode(current.node) ?? ""), current.node)
        : DARK,
    [current, atlas]
  )

  const shown = React.useMemo(() => panelOf(selected, atlas), [selected, atlas])
  const showPanel = shown.open
  const subject = React.useMemo<PanelSubject | undefined>(() => {
    if (!selected || !shown.open) return undefined
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
    const step = nodeById.get(selected.node) as StepNodeType
    return {
      type: "step",
      step: step.data.step,
      view: atlas.flows.get(flowOfNode(step.id) ?? "")?.view,
      ghost: step.data.ghost,
      coupons: step.data.coupons,
    }
  }, [selected, shown, nodeById, atlas, model])
  // The panel keeps its last subject while it slides away.
  const panel = usePresence(
    React.useMemo(
      () => subject && { subject, key: JSON.stringify(selected) },
      [subject, selected]
    ),
    !reducedMotion
  )
  const focusedTitle = focused
    ? (nodeById.get(focused)?.data as ModuleData | undefined)?.title
    : undefined
  const focusedFlows = React.useMemo(
    () => (focused ? flowsIn(atlas, focused) : undefined),
    [focused, atlas]
  )

  React.useEffect(() => {
    document.title = focusedTitle ? `${focusedTitle} · Genesis` : "Genesis"
  }, [focusedTitle])

  // Another module opened or closed: the map is redrawn, its cards sliding to their places.
  const drawn = React.useRef(atlas)
  React.useLayoutEffect(() => {
    if (drawn.current === atlas) return
    drawn.current = atlas
    flow.setNodes(atlas.nodes)
    flow.setEdges(atlas.edges)
    const element = wrapper.current
    if (!element || reducedMotion) return
    element.classList.add("is-morphing")
    const done = window.setTimeout(
      () => element.classList.remove("is-morphing"),
      MORPH_MS + 40
    )
    return () => {
      window.clearTimeout(done)
      element.classList.remove("is-morphing")
    }
  }, [atlas, flow, reducedMotion])

  // The camera. An order from the reader is carried out as given. When the screen or the
  // drawing changes under them instead, a glide still on its way carries on to where it
  // should now end, and otherwise their place is put back in frame at once.
  const screen = React.useMemo(
    () => ({ width, height, headline: headlineHeight, narrow }),
    [width, height, headlineHeight, narrow]
  )
  const scene = React.useMemo<Scene>(
    () => ({
      atlas,
      focused,
      panel: shown.open,
      subject: shown.node,
      screen,
    }),
    [atlas, focused, shown, screen]
  )
  const order = place.camera
  const flown = React.useRef({ no: -1, lands: 0 })
  React.useLayoutEffect(() => {
    if (!ready) return
    const send = (shot: Shot, ms: number) => {
      const view = viewOf(shot, scene)
      if (view)
        void flow.setViewport(view, {
          duration: ms,
          ease: easeOut,
          interpolate: "linear",
        })
    }
    if (flown.current.no !== order.no) {
      flown.current = { no: order.no, lands: performance.now() + order.ms }
      send(order.shot, order.ms)
      return
    }
    const left = flown.current.lands - performance.now()
    if (left > 0) send(order.shot, left)
    else send({ of: "place" }, 0)
  }, [ready, order, scene, flow])

  // A walk's beats are kept here: its camera sets off for a step, the walk reaches it.
  const trail = walk?.trail
  React.useEffect(() => {
    if (!trail) return
    const handles = beats(trail).map((beat) =>
      window.setTimeout(() => go(beat.act), beat.at)
    )
    return () => {
      for (const handle of handles) window.clearTimeout(handle)
    }
  }, [trail, go])

  // Keys: Esc steps back, the arrows walk the changes, Enter opens what has the focus.
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Keys typed into Graphical's development editor are the editor's.
      if (isEditorInteraction(event)) return
      const target = event.target instanceof HTMLElement ? event.target : null
      const escape = event.key === "Escape"
      if (target?.closest("[data-panel]")) {
        if (escape) go({ do: "escape" })
        return
      }
      if (
        target?.closest("[role=listbox], input, textarea, select") ||
        target?.isContentEditable
      )
        return
      if (escape) {
        go({ do: "escape" })
        return
      }
      // The arrows walk the changes, also right after an arrow of the stepper was
      // clicked and the button still has the focus.
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault()
        go({ do: "step", by: event.key === "ArrowRight" ? 1 : -1 })
        return
      }
      // A button keeps every other key for itself.
      if (target?.closest("button")) return
      if (event.key === "Enter" || event.key === " ") {
        const id = (target?.closest(".react-flow__node") as HTMLElement | null)
          ?.dataset.id
        if (id) {
          event.preventDefault()
          go({ do: "node", id })
        }
        return
      }
      go({ do: "touch" })
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [go])

  // The change on show is part of the address ("#change=3"), so a link opens on it.
  const pickedNo = pickedOf(place, model)
  React.useEffect(() => {
    if (!ready) return
    const open = () => {
      const no = Number(/^#change=(\d+)$/.exec(location.hash)?.[1] ?? 0)
      if (
        no &&
        no <= model.stops.length &&
        no !== pickedOf(now.current.place, model)
      )
        go({ do: "change", no })
    }
    open()
    window.addEventListener("hashchange", open)
    return () => window.removeEventListener("hashchange", open)
  }, [ready, model, go])
  React.useEffect(() => {
    if (!ready) return
    // Asked afresh: the address may have named this change a moment ago, just above.
    const no = pickedOf(now.current.place, model)
    const hash = no ? `#change=${no}` : ""
    if (location.hash === hash) return
    try {
      history.replaceState(
        history.state,
        "",
        hash || location.pathname + location.search
      )
    } catch {
      // Some browsers refuse this on a page opened from a file; the page works without.
    }
  }, [pickedNo, ready, model])

  const walkable = React.useMemo(
    () => model.stops.map((stop) => stop.no),
    [model]
  )
  /** The stops the panel is about, for marking them as seen. */
  const panelStops = subject
    ? subject.coupons.length
      ? [...new Set(subject.coupons.map((coupon) => coupon.no))]
      : pickedNo && subject.type !== "step"
        ? [pickedNo]
        : []
    : []
  const hint = React.useMemo(
    () => ({
      "node.a11yDescription.default": t.nodeHint,
      "node.a11yDescription.keyboardDisabled": t.nodeHint,
    }),
    [t]
  )
  const spot: Spotlight = {
    focus,
    lit,
    selected: selected?.type === "step" ? selected.node : undefined,
    ripple: {
      run: place.ripple.run,
      plays: !place.ripple.settled && !reducedMotion,
      delay: place.ripple.delay,
    },
    trail,
    focusedFlows,
  }
  const canvas: CanvasState = {
    t,
    focus,
    stopNo: current?.no,
    apart:
      selected?.type === "offMap"
        ? `offmap${SEP}${selected.no}`
        : selected?.type === "removedFlow"
          ? `row${SEP}${selected.flowId}`
          : undefined,
    walking: Boolean(walk),
    focusedModule: focused,
    step: (id, facts) => stepLook(spot, id, facts),
    line: (id, facts) => lineLook(spot, id, facts),
    away: (flowId) => Boolean(focusedFlows && !focusedFlows.has(flowId)),
  }
  const handlers = React.useMemo(
    () => ({
      onRun: (flowId: string) => go({ do: "walk", flowId }),
      onOverview: () => go({ do: "overview" }),
    }),
    [go]
  )
  const zoomBy = {
    duration: reducedMotion ? 0 : ZOOM_MS,
    ease: easeOut,
    interpolate: "linear" as const,
  }

  const visibleCanvas = readingArea(screen, showPanel)
  return (
    <CanvasContext.Provider value={canvas}>
      <AtlasContext.Provider value={handlers}>
        <div
          className="relative h-dvh w-full overflow-hidden bg-canvas"
          style={
            {
              "--panel-w": `${PANEL_W}px`,
              "--morph": `${MORPH_MS}ms`,
            } as React.CSSProperties
          }
          onPointerDownCapture={(event) => {
            if ((event.target as HTMLElement).closest(".react-flow"))
              go({ do: "touch" })
          }}
          onWheelCapture={(event) => {
            if ((event.target as HTMLElement).closest(".react-flow"))
              go({ do: "touch" })
          }}
        >
          <svg aria-hidden className="pointer-events-none absolute size-0">
            <defs>
              {ARROWS.map(([id, color]) => (
                <marker
                  key={id}
                  id={id}
                  viewBox="0 0 10 10"
                  markerWidth="9"
                  markerHeight="9"
                  refX="9.5"
                  refY="5"
                  orient="auto"
                  markerUnits="userSpaceOnUse"
                >
                  <path d="M1 1.2 L9.5 5 L1 8.8 Z" style={{ fill: color }} />
                </marker>
              ))}
            </defs>
          </svg>
          <div
            ref={wrapper}
            className="absolute inset-0"
            style={
              narrow
                ? undefined
                : {
                    // Panning and zooming must never put graph content under the floating UI.
                    clipPath: `inset(${Math.max(0, visibleCanvas.y - 12)}px ${Math.max(0, width - visibleCanvas.x - visibleCanvas.width - 12)}px 0 0)`,
                  }
            }
          >
            {atlas.nodes.length ? (
              <ReactFlow
                defaultNodes={atlas.nodes}
                defaultEdges={atlas.edges}
                nodeTypes={NODE_TYPES}
                edgeTypes={EDGE_TYPES}
                onNodeClick={(_, node) => go({ do: "node", id: node.id })}
                onPaneClick={() => go({ do: "pane" })}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                edgesFocusable={false}
                ariaLabelConfig={hint}
                panOnScroll
                zoomOnScroll={false}
                zoomOnDoubleClick={false}
                minZoom={0.05}
                maxZoom={MAX_ZOOM}
                className={cn(!ready && "opacity-0")}
              />
            ) : (
              <div
                className={cn(
                  "flex h-full items-center justify-center",
                  "px-xxl",
                  "text-center text-body-m",
                  "text-ink-2"
                )}
              >
                {t.noFlow}
              </div>
            )}
          </div>

          <div
            ref={headRef}
            className={cn(
              "absolute top-3 left-3 z-10 flex max-w-[calc(100%-24px)] flex-col items-start gap-m",
              "pointer-events-none",
              "md:top-4 md:left-4"
            )}
          >
            {model.hasReport && (
              <div
                className={
                  narrow
                    ? "w-[calc(100vw-24px)]"
                    : showPanel
                      ? "max-w-[calc(100vw-var(--panel-w)-48px)]"
                      : "max-w-[calc(100vw-32px)]"
                }
              >
                <Headline
                  model={model}
                  t={t}
                  compact={narrow && showPanel}
                  picked={pickedNo}
                  walk={walkable}
                  onPick={focus ? (no) => go({ do: "change", no }) : undefined}
                  onStep={focus ? (by) => go({ do: "step", by }) : undefined}
                />
              </div>
            )}
            {!model.hasReport && <MapMark model={model} t={t} />}
          </div>

          {/* The walk says what it walks, where it is, and how to stop it. */}
          {walk && (
            <div
              className={cn(
                "pointer-events-none absolute bottom-8 left-3 z-10 flex justify-center",
                showPanel && !narrow
                  ? "right-[calc(var(--panel-w)+36px)]"
                  : "right-16"
              )}
            >
              <WalkBar
                t={t}
                flow={model.flowById.get(walk.flowId)?.flow.name ?? ""}
                step={
                  nodeById.get(walk.steps[walk.at]) as StepNodeType | undefined
                }
                done={walk.done}
                onStop={() => go({ do: "endWalk" })}
              />
            </div>
          )}

          {/* The light or dark rendition; under it zoom, for readers without a trackpad, and
              the way back to the whole map. */}
          {!(narrow && showPanel) && (
            <div className="absolute right-3 bottom-8 z-10 flex flex-col gap-m">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={theme === "dark" ? t.toLight : t.toDark}
                title={theme === "dark" ? t.toLight : t.toDark}
                className="corner-full bg-card text-ink-2 shadow-[var(--shadow-float)] ring-1 ring-line hover:bg-card hover:text-ink"
                onClick={toggleTheme}
              >
                {theme === "dark" ? <Sun /> : <Moon />}
              </Button>
              {atlas.nodes.length > 0 && (
                <div className="flex flex-col overflow-hidden corner-full bg-card shadow-[var(--shadow-float)] ring-1 ring-line">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.zoomIn}
                    className="corner-zero text-ink-2"
                    onClick={() => void flow.zoomIn(zoomBy)}
                  >
                    <Plus />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.zoomOut}
                    className="corner-zero text-ink-2"
                    onClick={() => void flow.zoomOut(zoomBy)}
                  >
                    <Minus />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.fitView}
                    className="corner-zero edge-t-m border-line text-ink-2"
                    onClick={() => go({ do: "fit" })}
                  >
                    <Maximize />
                  </Button>
                </div>
              )}
            </div>
          )}

          {panel.shown && (
            <aside
              data-panel
              onAnimationEnd={(event) => {
                if (panel.leaving && event.target === event.currentTarget)
                  panel.done()
              }}
              className={cn(
                "absolute z-20 overflow-hidden corner-xl",
                // A stable desktop inspector fits both tabs and leaves controls below it.
                narrow
                  ? "inset-x-2 bottom-2 h-[52dvh] [--panel-from:0_24px]"
                  : "top-4 right-4 h-[min(720px,calc(100dvh-112px))] w-(--panel-w) [--panel-from:20px_0]",
                panel.leaving ? "panel-out" : "panel-in"
              )}
            >
              <DetailPanel
                // Each new subject starts at the top with its code folded.
                key={panel.shown.key}
                model={model}
                t={t}
                subject={panel.shown.subject}
                focus={current?.no}
                onWalk={
                  // With a change to read, the page steps through the changes instead.
                  !focus &&
                  subject?.type === "step" &&
                  subject.view &&
                  !subject.view.removed &&
                  !subject.ghost
                    ? () =>
                        go({ do: "walk", flowId: subject.view!.flow.flow_id })
                    : undefined
                }
                onNext={
                  focus && panelStops.length > 0 && walkable.length > 1
                    ? () => go({ do: "step", by: 1 })
                    : undefined
                }
                onClose={() => go({ do: "close" })}
              />
            </aside>
          )}
        </div>
      </AtlasContext.Provider>
    </CanvasContext.Provider>
  )
}

/** A pill under the map while a flow is walked: the flow, the step reached, and a way out. */
function WalkBar({
  t,
  flow,
  step,
  done,
  onStop,
}: {
  t: (typeof STRINGS)["zh"]
  flow: string
  step?: StepNodeType
  done: boolean
  onStop: () => void
}) {
  const change = step?.data.coupons[0]?.change
  const said = change?.explanation?.summary
  return (
    <div className="pointer-events-auto flex max-w-full min-w-0 items-center gap-l corner-full bg-card py-s pr-s pl-l text-body-m shadow-[var(--shadow-float)] ring-1 ring-line">
      <Play
        aria-hidden
        className={cn("size-3.5 shrink-0", done ? "text-ink-3" : "text-ink")}
      />
      <span className="shrink-0 text-ink-2">
        {done ? t.walkDone : t.walking}
      </span>
      <span className="max-w-[180px] min-w-0 truncate font-medium text-ink">
        {flow}
      </span>
      {step && (
        <>
          <span aria-hidden className="shrink-0 text-ink-3">
            ·
          </span>
          <span
            aria-live="polite"
            className={cn(
              "min-w-0 truncate",
              said ? "font-medium text-ink" : "text-ink-2"
            )}
          >
            {said ?? step.data.step.name}
          </span>
        </>
      )}
      <Button
        variant="ghost"
        size="xs"
        onClick={onStop}
        className="shrink-0 corner-full px-l text-body-m text-ink-2"
      >
        {done ? t.endWalk : t.stopWalk}
      </Button>
    </div>
  )
}

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
import { Maximize, Minus, Moon, Play, Plus, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DetailPanel, type PanelSubject } from "@/components/detail-panel"
import { Headline } from "@/components/headline"
import { MapMark } from "@/components/map-mark"
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
  moduleNodeId,
  stepNodeId,
  type AtlasNode,
  type LabelData,
  type ModuleData,
  type OffMapData,
  type MoreData,
  type PlacedFlow,
  type RowData,
} from "@/atlas/build"
import {
  AtlasContext,
  LabelView,
  ModuleView,
  OffMapView,
  RelationView,
  MoreView,
  RowView,
} from "@/atlas/nodes"
import { cn } from "@/lib/utils"
import { STRINGS } from "@/i18n"
import { routeTo } from "@/layout"
import { matches, reachOf, type Filter, type Model } from "@/model"
import { useReviewed } from "@/review"
import { useTheme } from "@/theme"

const NODE_TYPES = {
  step: StepNode,
  module: ModuleView,
  label: LabelView,
  offmap: OffMapView,
  row: RowView,
  more: MoreView,
}
const EDGE_TYPES = {
  flow: FlowEdge,
  relation: RelationView,
}
/** Arrowheads for the lines, one per line colour. */
const ARROWS = [
  ["arrow", "var(--edge)"],
  ["arrow-strong", "var(--edge-strong)"],
  ["arrow-exception", "var(--edge-exception)"],
  ["arrow-exception-strong", "var(--edge-exception-strong)"],
] as const
const PANEL_W = 384
/** The first look is never smaller than this: a map nobody can read is no overview. */
const READ_ZOOM = 0.8
const APART = moduleNodeId("__apart")
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

/** The way into a step along the lines that are drawn of its flow, from where it starts. */
function drawnRoute(
  placed: PlacedFlow,
  target: string
): { edges: Set<string>; steps: Set<string> } {
  const previous = new Map<string, FlowEdgeType>()
  const seen = new Set(placed.triggers)
  const queue = [...placed.triggers]
  while (queue.length) {
    const id = queue.shift()!
    if (id === target) break
    for (const edge of placed.edges) {
      if (edge.data?.back || edge.source !== id || seen.has(edge.target))
        continue
      seen.add(edge.target)
      previous.set(edge.target, edge)
      queue.push(edge.target)
    }
  }
  const edges = new Set<string>()
  const steps = new Set<string>()
  if (!seen.has(target)) return { edges, steps }
  steps.add(target)
  for (let at = target; previous.has(at); at = previous.get(at)!.source) {
    edges.add(previous.get(at)!.id)
    steps.add(previous.get(at)!.source)
  }
  return { edges, steps }
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
  // The module whose flows are drawn step by step; every other flow stays folded.
  const [focused, setFocused] = React.useState<string>()
  // A row of modules is as wide as the screen shows at a size that still reads.
  const span = Math.max(
    Math.floor(((width || window.innerWidth) - 84) / READ_ZOOM / 20) * 20,
    880
  )
  const atlas = React.useMemo(
    () => buildAtlas(model, t, focused, span),
    [model, t, focused, span]
  )
  const nodeById = React.useMemo(
    () => new Map(atlas.nodes.map((node) => [node.id, node])),
    [atlas]
  )
  const focus = model.stops.length > 0

  const [selected, setSelected] = React.useState<Selected>()
  // The one kind of change the reader narrowed the page down to, and what they have seen.
  const [filter, setFilter] = React.useState<Filter>()
  const { reviewed, toggle: toggleReviewed } = useReviewed(model)
  const { theme, toggle: toggleTheme } = useTheme()
  const walkable = React.useMemo(
    () =>
      model.stops
        .filter((stop) => matches(stop, filter))
        .map((stop) => stop.no),
    [model, filter]
  )
  // The change picked on the map: its card rings and what it leads to answers.
  const [current, setCurrent] = React.useState<{ node: string; no: number }>()
  const [play, setPlay] = React.useState({
    run: 0,
    armed: false,
    settled: false,
    delay: CUT_ARM,
  })
  const [trail, setTrail] = React.useState<Trail>()
  // The walk on show: its flow, its steps in order, how far it has got, whether it is over.
  const [walking, setWalking] = React.useState<{
    flowId: string
    steps: string[]
    at: number
    done: boolean
  }>()
  const [ready, setReady] = React.useState(false)
  const headRef = React.useRef<HTMLDivElement>(null)
  const wrapper = React.useRef<HTMLDivElement>(null)
  const opener = React.useRef<HTMLElement | null>(null)
  const timers = React.useRef<number[]>([])
  const walks = React.useRef(0)
  const morph = React.useRef(0)
  // What to do once the map has been redrawn for another module: walk a flow, show a change.
  const pending = React.useRef<{ walk?: string; stop?: number } | undefined>(
    undefined
  )
  // The flow to frame when its module opens.
  const aim = React.useRef<string | undefined>(undefined)

  // Names on the map keep their size on screen as the reader zooms out.
  React.useEffect(() => {
    // Far out, changes turn into solid blocks and the rest recedes (see index.css).
    const set = (zoom: number) => {
      wrapper.current?.style.setProperty("--zoom", String(zoom))
      wrapper.current?.classList.toggle("is-far", zoom < 0.5)
    }
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
    // A flow cut down to the change is lit along the lines that are drawn of it.
    const route =
      placed.mode === "focus"
        ? drawnRoute(placed, current.node)
        : routeTo(placed.view.layout, local)
    const lead = placed.mode === "focus" ? (id: string) => id : prefix
    const out: FlowEdgeType[] = []
    const loopEdges = new Set<string>()
    for (const edge of placed.edges) {
      if (edge.data?.back) {
        if (edge.source === current.node || edge.target === current.node)
          loopEdges.add(edge.id)
      } else if (edge.source === current.node) out.push(edge)
    }
    const routeSteps = new Set([...route.steps].map(lead))
    routeSteps.delete(current.node)
    return {
      current: current.node,
      next: new Set(reach.next.map(prefix)),
      far: new Set(reach.far.map(prefix)),
      routeSteps,
      routeEdges: new Set([...route.edges].map(lead)),
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
  const focusedFlows = React.useMemo(() => {
    if (!focused) return undefined
    const data = nodeById.get(focused)?.data as ModuleData | undefined
    if (data?.apart)
      return new Set([
        "__offmap",
        ...model.flows
          .filter((view) => view.removed)
          .map((view) => view.flow.flow_id),
      ])
    const module = model.modules.find(
      (item) => `module${SEP}${item.id}` === focused
    )
    return new Set(module?.flows.map((view) => view.flow.flow_id) ?? [])
  }, [focused, nodeById, model])

  React.useEffect(() => {
    document.title = focusedTitle ? `${focusedTitle} · Genesis` : "Genesis"
  }, [focusedTitle])

  /** The part of the screen left once the headline, the panel and the margins are set aside. */
  const area = React.useCallback(
    (withPanel: boolean) => {
      const head = headRef.current?.getBoundingClientRect()
      const top = Math.max(head ? head.bottom + 16 : 0, 24)
      const left = narrow ? 12 : 24
      // The zoom controls stand at the right edge, under the panel when it is open.
      const right = narrow ? 12 : withPanel ? PANEL_W + 40 : 60
      const bottom = narrow ? (withPanel ? height * 0.52 + 16 : 24) : 28
      return {
        x: left,
        y: top,
        w: Math.max(width - left - right, 80),
        h: Math.max(height - top - bottom, 80),
      }
    },
    [narrow, width, height]
  )
  const glide = reducedMotion ? 0 : GLIDE_MS
  const motionOf = (duration: number) => ({
    duration,
    ease: easeOut,
    interpolate: "linear" as const,
  })

  /** Where a node sits on the map, from the layout itself: no waiting to be measured. */
  const boxOf = React.useCallback(
    (id: string) => {
      const node = nodeById.get(id)
      if (!node) return undefined
      const step = node.type === "step" ? (node as StepNodeType) : undefined
      return {
        x: node.position.x,
        y: node.position.y,
        width: step ? step.data.width : (node.width ?? 0),
        height: step ? heightOf(step.data) : (node.height ?? 0),
      }
    },
    [nodeById]
  )
  const boundsOf = React.useCallback(
    (ids: Iterable<string>) => {
      let x0 = Infinity
      let y0 = Infinity
      let x1 = -Infinity
      let y1 = -Infinity
      for (const id of ids) {
        const box = boxOf(id)
        if (!box) continue
        x0 = Math.min(x0, box.x)
        y0 = Math.min(y0, box.y)
        x1 = Math.max(x1, box.x + box.width)
        y1 = Math.max(y1, box.y + box.height)
      }
      return x1 < x0
        ? undefined
        : { x: x0, y: y0, width: x1 - x0, height: y1 - y0 }
    },
    [boxOf]
  )
  /**
   * Bring a part of the map into the free area, never smaller than `min`. When that is
   * wider or taller than the area, start from its top left, where the flows begin; with
   * `fromTop` it starts at the top even when it fits, so nothing blank stands over it.
   */
  const frame = React.useCallback(
    (
      bounds: { x: number; y: number; width: number; height: number },
      withPanel: boolean,
      duration: number,
      min: number,
      max = 1,
      fromTop = false
    ) => {
      const box = area(withPanel)
      const zoom = Math.min(
        max,
        Math.max(min, Math.min(box.w / bounds.width, box.h / bounds.height))
      )
      const across = bounds.width * zoom <= box.w
      const down = !fromTop && bounds.height * zoom <= box.h
      void flow.setViewport(
        {
          x: across
            ? box.x + (box.w - bounds.width * zoom) / 2 - bounds.x * zoom
            : box.x - bounds.x * zoom,
          y: down
            ? box.y + (box.h - bounds.height * zoom) / 2 - bounds.y * zoom
            : box.y - bounds.y * zoom,
          zoom,
        },
        { duration, ease: easeOut, interpolate: "linear" }
      )
    },
    [area, flow]
  )
  const fitAll = React.useCallback(
    (duration: number, withPanel = false) => {
      const bounds = boundsOf(nodeById.keys())
      if (bounds) frame(bounds, withPanel, duration, READ_ZOOM)
    },
    [boundsOf, nodeById, frame]
  )
  const fitTo = (ids: string[], duration: number, withPanel = showPanel) => {
    const bounds = boundsOf(ids)
    if (bounds) frame(bounds, withPanel, duration, 0.5)
  }
  /** Put a node in the middle of the free area, at least this close. */
  const centerOn = (
    id: string,
    zoom: number,
    duration: number,
    withPanel: boolean
  ) => {
    const node = boxOf(id)
    if (!node) return
    const box = area(withPanel)
    void flow.setCenter(
      node.x + node.width / 2 + (width / 2 - (box.x + box.w / 2)) / zoom,
      node.y + node.height / 2 + (height / 2 - (box.y + box.h / 2)) / zoom,
      { zoom, ...motionOf(duration) }
    )
  }
  const inView = (id: string, withPanel: boolean) => {
    const node = boxOf(id)
    if (!node) return true
    const { x: vx, y: vy, zoom } = flow.getViewport()
    const box = area(withPanel)
    const left = node.x * zoom + vx
    const top = node.y * zoom + vy
    return (
      zoom >= 0.55 &&
      left >= box.x &&
      top >= box.y &&
      left + node.width * zoom <= box.x + box.w &&
      top + node.height * zoom <= box.y + box.h
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

  // Another module opened or closed: the map is redrawn, its cards sliding to their places.
  const drawn = React.useRef(atlas)
  React.useLayoutEffect(() => {
    if (drawn.current === atlas) return
    drawn.current = atlas
    const element = wrapper.current
    if (element && !reducedMotion) {
      element.classList.add("is-morphing")
      window.clearTimeout(morph.current)
      morph.current = window.setTimeout(
        () => element.classList.remove("is-morphing"),
        360
      )
    }
    flow.setNodes(atlas.nodes)
    flow.setEdges(atlas.edges)
  }, [atlas, flow, reducedMotion])

  // A new window size keeps what was framed in frame.
  const size = React.useRef({ width, height })
  React.useEffect(() => {
    const before = size.current
    size.current = { width, height }
    if (!ready || (before.width === width && before.height === height)) return
    const bounds = focused ? boundsOf([focused]) : undefined
    if (bounds) frame(bounds, false, 0, 0.5)
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
    setWalking(undefined)
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
  const pick = (node: StepNodeType, no?: number) => {
    const shown =
      node.data.coupons.find((coupon) => coupon.no === (no ?? current?.no)) ??
      node.data.coupons[0]
    const run = play.run + 1
    setCurrent({ node: node.id, no: shown.no })
    if (inView(node.id, true)) {
      setPlay({ run, armed: true, settled: false, delay: 0 })
      return
    }
    // Frame the change with the steps it leads to and the results it may reach while they
    // stay readable; else the change and its next steps; else the change alone.
    const flowId = flowOfNode(node.id) ?? ""
    const placed = atlas.flows.get(flowId)
    const local = node.id.slice(flowId.length + SEP.length)
    const reach =
      placed && !local.startsWith("removed-")
        ? reachOf(placed.view, local)
        : { next: [], far: [] }
    const prefix = (id: string) => `${flowId}${SEP}${id}`
    const box = area(true)
    const fits = (ids: string[]) => {
      const bounds = boundsOf(ids)
      return (
        bounds &&
        Math.min(
          box.w / Math.max(bounds.width, 1),
          box.h / Math.max(bounds.height, 1)
        ) >= 0.6 &&
        bounds
      )
    }
    const bounds =
      fits([node.id, ...reach.next.map(prefix), ...reach.far.map(prefix)]) ||
      fits([node.id, ...reach.next.map(prefix)])
    // Stepping between changes moves the map, it does not zoom in on each one.
    if (bounds)
      frame(
        bounds,
        true,
        glide,
        0.6,
        Math.max(flow.getViewport().zoom, READ_ZOOM)
      )
    else centerOn(node.id, Math.max(flow.getViewport().zoom, 0.8), glide, true)
    setPlay({
      run,
      armed: true,
      settled: false,
      delay: glide ? GLIDE_ARM : 0,
    })
  }

  /** The flow a node belongs to ("__offmap" for a change outside the flows). */
  const flowIdOf = (node: AtlasNode): string | undefined =>
    node.type === "step"
      ? flowOfNode(node.id)
      : node.type === "offmap"
        ? "__offmap"
        : node.type === "label" || node.type === "row"
          ? (node.data as LabelData | RowData).flowId || undefined
          : undefined
  const homeOf = (node: AtlasNode): string | undefined => {
    if (node.type === "more") return (node.data as MoreData).moduleId
    const flowId = flowIdOf(node)
    return flowId === "__offmap" ? APART : atlas.home.get(flowId ?? "")
  }

  // The camera follows the focus: into the opened module, or back out to the whole map.
  const framedFocus = React.useRef<string | undefined>(undefined)
  React.useEffect(() => {
    if (!ready || framedFocus.current === focused) return
    framedFocus.current = focused
    const wanted = aim.current
    aim.current = undefined
    if (!focused) {
      fitAll(glide, showPanel)
      return
    }
    const inside = atlas.nodes.filter((node) =>
      focusedFlows?.has(flowIdOf(node) ?? "")
    )
    // The flow that was asked for; else the changed cards with the names of their flows;
    // else everything in the module.
    const asked = wanted
      ? inside.filter((node) => flowIdOf(node) === wanted)
      : []
    const changed = inside.filter(
      (node) =>
        node.type === "offmap" ||
        (node.type === "step" && (node as StepNodeType).data.coupons.length > 0)
    )
    const flows = new Set(changed.map(flowIdOf))
    const picked = asked.length
      ? asked
      : changed.length
        ? [
            ...changed,
            ...inside.filter(
              (node) => node.type === "label" && flows.has(flowIdOf(node))
            ),
          ]
        : inside
    const bounds = boundsOf(
      picked.length ? picked.map((node) => node.id) : [focused]
    )
    if (!bounds) return
    // At the top of the module its name comes along.
    const frameBox = boxOf(focused)
    if (frameBox && bounds.y - frameBox.y < 140) {
      bounds.height += bounds.y - frameBox.y
      bounds.y = frameBox.y
      bounds.width += bounds.x - frameBox.x
      bounds.x = frameBox.x
    }
    // An open module starts right under the headline, the way the whole map does.
    frame(bounds, showPanel, glide, READ_ZOOM, 1, true)
    // Runs when the focus changes; the rest is read fresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused, ready])
  const focusModule = (id: string, flowId?: string) => {
    aim.current = flowId
    setFocused(id)
  }
  const toOverview = () => {
    stopWalk()
    setFocused(undefined)
    setCurrent(undefined)
    setSelected(undefined)
  }

  /** A change picked in the list: the map flies to it and its details open. */
  const pickStop = (no: number) => {
    const stop = model.stops[no - 1]
    if (!stop) return
    stopWalk()
    // A change outside the open module: back to the whole map first, then to the change.
    const at =
      stop.kind === "off_map" ? APART : atlas.home.get(stop.flowId ?? "")
    if (focused && at !== focused) {
      pending.current = { stop: no }
      setFocused(undefined)
      return
    }
    if (stop.kind === "off_map") {
      setCurrent(undefined)
      openPanel({ type: "offMap", no })
      const id = `offmap${SEP}${no}`
      if (!inView(id, true))
        centerOn(id, Math.max(flow.getViewport().zoom, READ_ZOOM), glide, true)
      return
    }
    if (stop.kind === "removed_flow" && stop.flowId) {
      setCurrent(undefined)
      openPanel({ type: "removedFlow", flowId: stop.flowId })
      const placed = atlas.flows.get(stop.flowId)
      if (placed?.nodes.length)
        fitTo(
          placed.nodes.map((item) => item.id),
          glide,
          true
        )
      else if (placed && !inView(placed.triggers[0], true))
        centerOn(
          placed.triggers[0],
          Math.max(flow.getViewport().zoom, READ_ZOOM),
          glide,
          true
        )
      return
    }
    if (!stop.flowId || !stop.nodeId) return
    const node = nodeById.get(stepNodeId(stop.flowId, stop.nodeId))
    if (!node || node.type !== "step") return
    openPanel({ type: "step", node: node.id })
    pick(node as StepNodeType, no)
  }
  const pickedNo =
    current?.no ??
    (selected?.type === "offMap"
      ? selected.no
      : selected?.type === "removedFlow"
        ? model.stops.find(
            (item) =>
              item.kind === "removed_flow" && item.flowId === selected.flowId
          )?.no
        : undefined)

  /** On to the next change the stepper walks, or back to the one before; it wraps. */
  const stepBy = (by: number) => {
    if (!walkable.length) return
    const at = pickedNo ? walkable.indexOf(pickedNo) : -1
    const next =
      at < 0
        ? by > 0
          ? 0
          : walkable.length - 1
        : (at + by + walkable.length) % walkable.length
    pickStop(walkable[next])
  }
  /** The stops the panel is about, for marking them as seen. */
  const panelStops = subject
    ? subject.coupons.length
      ? [...new Set(subject.coupons.map((coupon) => coupon.no))]
      : pickedNo && subject.type !== "step"
        ? [pickedNo]
        : []
    : []

  /** Walk through a flow the way it usually runs, the camera riding along. */
  const walk = (flowId: string) => {
    const placed = atlas.flows.get(flowId)
    if (!placed) return
    stopWalk()
    setCurrent(undefined)
    // A walk passes every step, so the flow's module opens first.
    const module = atlas.home.get(flowId)
    if (placed.mode !== "full" && module && module !== focused) {
      pending.current = { walk: flowId }
      focusModule(module, flowId)
      return
    }
    if (placed.mode !== "full") return
    const path = mainPath(placed)
    if (!path.steps.length) return
    const withPanel = Boolean(selected)
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
    setWalking({
      flowId,
      steps: path.steps,
      at: animate ? 0 : path.steps.length - 1,
      done: !animate,
    })
    setTrail({
      run: walks.current,
      edges,
      steps,
      changed: new Set(path.steps.filter(isChanged)),
      animate,
    })
    if (!animate) {
      fitTo(path.steps, 0, withPanel)
      return
    }
    centerOn(path.steps[0], WALK_ZOOM, WALK_LEAD - 40, withPanel)
    path.steps.forEach((id, index) => {
      const arrive = steps.get(id)!
      if (index > 0)
        timers.current.push(
          window.setTimeout(
            () => centerOn(id, WALK_ZOOM, 420, withPanel),
            Math.max(arrive - 320, 0)
          )
        )
      timers.current.push(
        window.setTimeout(
          () =>
            setWalking((value) =>
              value
                ? {
                    ...value,
                    at: index,
                    done: index === path.steps.length - 1,
                  }
                : value
            ),
          arrive
        )
      )
    })
  }

  const onNodeClick: NodeMouseHandler<AtlasNode> = (_, node) => {
    stopWalk()
    if (node.type === "module") {
      if (node.id !== focused) focusModule(node.id)
      return
    }
    const at = homeOf(node)
    const changeOn =
      node.type === "offmap"
        ? (node.data as OffMapData).coupon.no
        : node.type === "step"
          ? (node as StepNodeType).data.coupons[0]?.no
          : undefined
    // Something in a module other than the open one: a change is shown from the whole map,
    // anything else opens its own module.
    if (focused && at && at !== focused) {
      if (changeOn) pickStop(changeOn)
      else focusModule(at, flowIdOf(node))
      return
    }
    if (node.type === "more") {
      // The folded lookups and upkeep are listed by opening their module.
      if (at) focusModule(at)
      return
    }
    if (node.type === "label" || node.type === "row") {
      const data = node.data as LabelData | RowData
      if (data.struck) openPanel({ type: "removedFlow", flowId: data.flowId })
      else if (!data.flowId || !at) return
      else if (at !== focused) focusModule(at, data.flowId)
      else {
        const placed = atlas.flows.get(data.flowId)
        if (placed?.nodes.length)
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
    if (step.data.stub) {
      // The pill that stands for steps left out opens the module on its flow.
      if (at) focusModule(at, flowIdOf(node))
      return
    }
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
    step: (by: number): void => void by,
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
      step: stepBy,
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
        target?.closest("[role=listbox], input, textarea, select") ||
        target?.isContentEditable
      )
        return
      if (event.key === "Escape") {
        keys.current.escape()
        return
      }
      // A button keeps Enter and Space for itself; the arrows still walk the changes, so
      // they go on working right after an arrow of the stepper was clicked.
      if (target?.closest("button")) {
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault()
          keys.current.step(event.key === "ArrowRight" ? 1 : -1)
        }
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
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault()
        keys.current.step(event.key === "ArrowRight" ? 1 : -1)
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
    apart:
      selected?.type === "offMap"
        ? `offmap${SEP}${selected.no}`
        : selected?.type === "removedFlow"
          ? `row${SEP}${selected.flowId}`
          : undefined,
    knownRisks: !model.hasReport,
    filter,
    reviewed,
    run: play.run,
    armed: play.armed,
    pending: Boolean(current) && !play.armed && !reducedMotion,
    animate: play.armed && !play.settled && !reducedMotion,
    delay: play.delay,
    trail,
    trailActive: Boolean(trail),
    focusedModule: focused,
    focusedFlows,
  }
  const walkRef = React.useRef(walk)
  React.useEffect(() => {
    walkRef.current = walk
  })
  const overviewRef = React.useRef(toOverview)
  React.useEffect(() => {
    overviewRef.current = toOverview
  })
  const handlers = React.useMemo(
    () => ({
      onRun: (flowId: string) => walkRef.current(flowId),
      onOverview: () => overviewRef.current(),
    }),
    []
  )
  const pickStopRef = React.useRef(pickStop)
  React.useEffect(() => {
    pickStopRef.current = pickStop
  })
  // The map has been redrawn: do what was waiting for it.
  React.useEffect(() => {
    const todo = pending.current
    pending.current = undefined
    if (todo?.walk) walkRef.current(todo.walk)
    else if (todo?.stop) pickStopRef.current(todo.stop)
  }, [atlas])

  // The change on show is part of the address ("#change=3"), so a link opens on it.
  const pickedRef = React.useRef(pickedNo)
  React.useEffect(() => {
    pickedRef.current = pickedNo
  })
  const asked = React.useRef<number | undefined>(undefined)
  React.useEffect(() => {
    if (!ready) return
    const open = () => {
      const no = Number(/^#change=(\d+)$/.exec(location.hash)?.[1] ?? 0)
      if (!no || no > model.stops.length || no === pickedRef.current) return
      asked.current = no
      pickStopRef.current(no)
    }
    open()
    window.addEventListener("hashchange", open)
    return () => window.removeEventListener("hashchange", open)
  }, [ready, model])
  React.useEffect(() => {
    if (!ready) return
    // A change asked for by the address is still on its way: leave the address alone.
    if (asked.current !== undefined) {
      if (pickedNo === undefined) return
      asked.current = undefined
    }
    const hash = pickedNo ? `#change=${pickedNo}` : ""
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
  }, [pickedNo, ready])

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
            {model.hasReport && (
              <div
                className={
                  narrow
                    ? "w-[calc(100vw-24px)]"
                    : showPanel
                      ? "w-[min(600px,calc(100vw-432px))] min-w-[340px]"
                      : "w-[min(600px,calc(100vw-24px))]"
                }
              >
                <Headline
                  model={model}
                  t={t}
                  narrow={narrow}
                  compact={narrow && showPanel}
                  picked={pickedNo}
                  walk={walkable}
                  filter={filter}
                  reviewed={reviewed}
                  onFilter={setFilter}
                  onToggleReviewed={(no) => toggleReviewed([no])}
                  onPick={focus ? pickStop : undefined}
                  onStep={focus ? stepBy : undefined}
                />
              </div>
            )}
            {!model.hasReport && <MapMark model={model} t={t} />}
          </div>

          {/* The walk says what it walks, where it is, and how to stop it. */}
          {walking && (
            <div
              className={cn(
                "pointer-events-none absolute bottom-8 left-3 z-10 flex justify-center",
                showPanel && !narrow ? "right-[420px]" : "right-16"
              )}
            >
              <WalkBar
                t={t}
                flow={model.flowById.get(walking.flowId)?.flow.name ?? ""}
                step={
                  nodeById.get(walking.steps[walking.at]) as
                    StepNodeType | undefined
                }
                done={walking.done}
                onStop={stopWalk}
              />
            </div>
          )}

          {/* The light or dark rendition; under it zoom, for readers without a trackpad, and
              the way back to the whole map. */}
          {!(narrow && showPanel) && (
            <div className="absolute right-3 bottom-8 z-10 flex flex-col gap-2">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={theme === "dark" ? t.toLight : t.toDark}
                title={theme === "dark" ? t.toLight : t.toDark}
                className="rounded-full bg-card text-ink-2 shadow-[var(--shadow-float)] ring-1 ring-line hover:bg-card hover:text-ink"
                onClick={toggleTheme}
              >
                {theme === "dark" ? <Sun /> : <Moon />}
              </Button>
              {atlas.nodes.length > 0 && (
                <div className="flex flex-col overflow-hidden rounded-full bg-card shadow-[var(--shadow-float)] ring-1 ring-line">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.zoomIn}
                    className="rounded-none text-ink-2"
                    onClick={() => void flow.zoomIn(motionOf(glide ? 200 : 0))}
                  >
                    <Plus />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.zoomOut}
                    className="rounded-none text-ink-2"
                    onClick={() => void flow.zoomOut(motionOf(glide ? 200 : 0))}
                  >
                    <Minus />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t.fitView}
                    className="rounded-none border-t border-line text-ink-2"
                    onClick={() =>
                      focused ? toOverview() : fitAll(glide, showPanel)
                    }
                  >
                    <Maximize />
                  </Button>
                </div>
              )}
            </div>
          )}

          <AnimatePresence>
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
                  // On a desk the panel is as tall as what it says, and never so tall that
                  // it covers the controls under it.
                  narrow
                    ? "inset-x-2 bottom-2 h-[52dvh]"
                    : "top-3 right-3 max-h-[calc(100dvh-180px)] w-[384px]"
                )}
              >
                <DetailPanel
                  // Each new subject starts at the top with its code folded.
                  key={JSON.stringify(selected)}
                  model={model}
                  t={t}
                  subject={subject}
                  focus={current?.no}
                  onWalk={
                    // With a change to read, the page steps through the changes instead.
                    !focus &&
                    subject?.type === "step" &&
                    subject.view &&
                    !subject.view.removed &&
                    !subject.ghost
                      ? () => walk(subject.view!.flow.flow_id)
                      : undefined
                  }
                  review={
                    focus && panelStops.length
                      ? {
                          seen: panelStops.every((no) => reviewed.has(no)),
                          reviewed,
                          onToggle: () => toggleReviewed(panelStops),
                          onNext:
                            walkable.length > 1 ? () => stepBy(1) : undefined,
                        }
                      : undefined
                  }
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
    <div className="pointer-events-auto flex max-w-full min-w-0 items-center gap-2.5 rounded-full bg-card py-1.5 pr-1.5 pl-3 text-[13px] leading-5 shadow-[var(--shadow-float)] ring-1 ring-line">
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
        className="shrink-0 rounded-full px-2.5 text-[13px] text-ink-2"
      >
        {done ? t.endWalk : t.stopWalk}
      </Button>
    </div>
  )
}

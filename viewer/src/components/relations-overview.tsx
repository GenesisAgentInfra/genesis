import * as React from "react"
import {
  ReactFlow,
  ReactFlowProvider,
  Handle,
  Position,
  EdgeLabelRenderer,
  getBezierPath,
  type NodeProps,
  type EdgeProps,
} from "@xyflow/react"
import { ArrowUpRight, ChevronDown, ChevronRight, Maximize } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import {
  buildRelations,
  relationWords,
  type RelationModuleNode,
  type RelationGroupEdge,
} from "@/relations"
import type { Model } from "@/model"
import type { MapLink } from "@/types"

interface Actions {
  words: (typeof relationWords)["zh"]
  toggle: (id: string) => void
  navigate: (id: string) => void
  inspect: (links: MapLink[]) => void
}
const Context = React.createContext<Actions>(null!)

function Module({ data }: NodeProps<RelationModuleNode>) {
  const { words, toggle, navigate } = React.useContext(Context)
  return (
    <Card className="pointer-events-auto h-full gap-0 overflow-visible rounded-2xl py-0 shadow-none">
      <div className="flex h-[88px] items-center justify-between gap-3 px-5">
        <div className="min-w-0">
          <h2 className="truncate text-base font-medium" title={data.name}>
            {data.name}
          </h2>
          <p className="mt-1 text-xs text-ink-3">
            {data.flows.length} {words.flows === "流程图" ? "条流程" : "flows"}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          className="nodrag"
          aria-label={`${data.expanded ? words.collapse : words.expand} · ${data.name}`}
          aria-expanded={data.expanded}
          onClick={() => toggle(data.moduleId)}
        >
          {data.expanded ? <ChevronDown /> : <ChevronRight />}
        </Button>
      </div>
      {!data.expanded && (
        <>
          <Handle type="target" position={Position.Left} id="in" />
          <Handle type="source" position={Position.Right} id="out" />
        </>
      )}
      {data.expanded && (
        <div className="pb-2">
          {data.flows.map((flow) => (
            <div
              key={flow.id}
              className="relative flex h-[52px] items-center border-t border-line/60 px-3"
            >
              <Handle
                type="target"
                position={Position.Left}
                id={`in:${flow.id}`}
              />
              <Button
                variant="ghost"
                className="nodrag h-10 w-full justify-between gap-2 px-2 text-[13px]"
                title={flow.name}
                onClick={() => navigate(flow.id)}
              >
                <span className="truncate">{flow.name}</span>
                <ArrowUpRight />
              </Button>
              <Handle
                type="source"
                position={Position.Right}
                id={`out:${flow.id}`}
              />
              <Handle
                type="target"
                position={Position.Right}
                id={`internal:${flow.id}`}
              />
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function Relation({
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<RelationGroupEdge>) {
  const { words, inspect } = React.useContext(Context)
  if (!data) return null
  const [path, x, y] = data.internal
    ? [
        `M${sourceX},${sourceY} C${sourceX + 240},${sourceY} ${targetX + 240},${targetY} ${targetX},${targetY}`,
        sourceX + 180,
        (sourceY + targetY) / 2,
      ]
    : data.lane
      ? [
          `M${sourceX},${sourceY} C${(sourceX + targetX) / 2},${sourceY + (data.lane * 4) / 3} ${(sourceX + targetX) / 2},${targetY + (data.lane * 4) / 3} ${targetX},${targetY}`,
          (sourceX + targetX) / 2,
          (sourceY + targetY) / 2 + data.lane,
        ]
      : getBezierPath({
          sourceX,
          sourceY,
          targetX,
          targetY,
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
        })
  const dashed = data.candidate
    ? "2 5"
    : data.relation === "event" || data.relation === "state_handoff"
      ? "7 5"
      : undefined
  return (
    <>
      <path
        d={path as string}
        fill="none"
        stroke="var(--edge)"
        strokeWidth={1.5}
        strokeDasharray={dashed}
        markerEnd="url(#arrow)"
      />
      <EdgeLabelRenderer>
        <Button
          variant="outline"
          size="sm"
          className="nodrag nopan pointer-events-auto absolute max-w-[240px] gap-2 bg-card text-xs shadow-none"
          style={{
            transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
          }}
          title={data.label}
          onClick={() => inspect(data.links)}
        >
          <span className="truncate">{data.label}</span>
          {data.candidate && <Badge variant="secondary">{words.pending}</Badge>}
          <ChevronRight />
        </Button>
      </EdgeLabelRenderer>
    </>
  )
}
const nodeTypes = { relationModule: Module }
const edgeTypes = { relationGroup: Relation }

export function RelationsOverview({
  model,
  active,
  panel,
  onNavigate,
  onInspect,
}: {
  model: Model
  active: boolean
  panel: boolean
  onNavigate: (flowId: string) => void
  onInspect: (links: MapLink[]) => void
}) {
  const words = relationWords[model.lang]
  const [expanded, setExpanded] = React.useState(
    () =>
      new Set(
        model.modules.length === 1
          ? model.modules.map((module) => module.id)
          : []
      )
  )
  const [candidates, setCandidates] = React.useState(false)
  const [state, setState] = React.useState(false)
  const [fit, setFit] = React.useState(0)
  const graph = React.useMemo(
    () => buildRelations(model, expanded, candidates, state),
    [model, expanded, candidates, state]
  )
  const [instance, setInstance] =
    React.useState<
      import("@xyflow/react").ReactFlowInstance<
        RelationModuleNode,
        RelationGroupEdge
      >
    >()
  React.useEffect(() => {
    if (!instance || !active) return
    const handle = requestAnimationFrame(() => {
      const nodes = graph.nodes
      if (!nodes.length) return
      const left = Math.min(...nodes.map((node) => node.position.x))
      const top = Math.min(...nodes.map((node) => node.position.y))
      const right =
        Math.max(...nodes.map((node) => node.position.x + node.width!)) +
        (graph.edges.some((edge) => edge.data?.internal) ? 240 : 0)
      const available = window.innerWidth - (panel ? 448 : 0) - 100
      const zoom = Math.max(0.65, Math.min(1.15, available / (right - left)))
      void instance.setViewport(
        {
          x: (available + 100 - (right - left) * zoom) / 2 - left * zoom,
          y: 120 - top * zoom,
          zoom,
        },
        { duration: 0 }
      )
    })
    return () => cancelAnimationFrame(handle)
  }, [graph, instance, panel, fit, active])
  return (
    <Context.Provider
      value={{
        words,
        toggle: (id) =>
          setExpanded((previous) => {
            const next = new Set(previous)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
          }),
        navigate: onNavigate,
        inspect: onInspect,
      }}
    >
      <div
        className="absolute inset-0 bg-canvas"
        style={{ right: panel ? 448 : 0, display: active ? undefined : "none" }}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onInit={setInstance}
            fitView
            fitViewOptions={{ maxZoom: 1.15, padding: 0.25 }}
            minZoom={0.35}
            maxZoom={1.6}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnScroll
            zoomOnScroll={false}
            zoomOnDoubleClick={false}
          />
        </ReactFlowProvider>
        <div className="absolute top-4 right-5 flex gap-2">
          {model.links.some((link) => link.relation === "state_handoff") && (
            <Button
              variant={state ? "secondary" : "outline"}
              size="sm"
              aria-pressed={state}
              onClick={() => setState(!state)}
            >
              {words.state}
            </Button>
          )}
          {model.links.some((link) => link.resolution === "candidate") && (
            <Button
              variant={candidates ? "secondary" : "outline"}
              size="sm"
              aria-pressed={candidates}
              onClick={() => setCandidates(!candidates)}
            >
              {words.pending} ·{" "}
              {
                model.links.filter((link) => link.resolution === "candidate")
                  .length
              }
            </Button>
          )}
        </div>
        {!graph.edges.length && (
          <p className="absolute bottom-12 left-8 max-w-md text-sm leading-6 text-ink-3">
            {model.links.length
              ? model.lang === "zh"
                ? "展开模块查看内部关系；待确认与状态关联可按需显示。"
                : "Expand modules for internal relations. Unconfirmed and state relations are optional."
              : words.empty}
          </p>
        )}
        <Button
          variant="outline"
          size="icon-sm"
          className="absolute right-5 bottom-8 rounded-full"
          aria-label={
            model.lang === "zh" ? "适应模块关系" : "Fit module relations"
          }
          onClick={() => setFit(fit + 1)}
        >
          <Maximize />
        </Button>
      </div>
    </Context.Provider>
  )
}

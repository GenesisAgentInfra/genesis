import dagre from "@dagrejs/dagre"
import type { Edge, Node } from "@xyflow/react"
import type { Model } from "@/model"
import type { MapLink } from "@/types"

export const relationWords = {
  zh: {
    overview: "模块关系",
    flows: "流程图",
    expand: "展开流程",
    collapse: "收起流程",
    open: "进入流程",
    back: "返回",
    pending: "待确认",
    state: "状态关联",
    confirmed: "代码已确认",
    evidence: "调用依据",
    caller: "来源流程",
    target: "目标流程",
    related: "同一改动也影响",
    outgoing: "调用其他流程",
    incoming: "被这些流程调用",
    empty: "尚未提取到流程之间的关系。可以展开模块查看已有流程。",
    noContract: "尚未提供目标流程入口的结构化输入 / 输出。",
    kind: {
      call: "调用",
      async_task: "触发任务",
      event: "事件通知",
      state_handoff: "状态交接",
    },
  },
  en: {
    overview: "Module relations",
    flows: "Flows",
    expand: "Expand flows",
    collapse: "Collapse flows",
    open: "Open flow",
    back: "Back",
    pending: "Unconfirmed",
    state: "State relations",
    confirmed: "Confirmed in code",
    evidence: "Call evidence",
    caller: "Source flow",
    target: "Target flow",
    related: "Also changed",
    outgoing: "Calls other flows",
    incoming: "Called by",
    empty:
      "No relations between flows have been extracted. Expand a module to explore its flows.",
    noContract:
      "No structured input / output has been provided for the target flow entry.",
    kind: {
      call: "Call",
      async_task: "Trigger task",
      event: "Event",
      state_handoff: "State handoff",
    },
  },
}

export interface RelationGroup extends Record<string, unknown> {
  links: MapLink[]
  label: string
  relation: MapLink["relation"]
  candidate: boolean
  internal: boolean
  lane?: number
}
export interface RelationModule extends Record<string, unknown> {
  moduleId: string
  name: string
  expanded: boolean
  flows: { id: string; name: string }[]
}
export type RelationModuleNode = Node<RelationModule, "relationModule">
export type RelationGroupEdge = Edge<RelationGroup, "relationGroup">

/** Only explicit map links are execution relations. Shared changes never imply calls. */
export function buildRelations(
  model: Model,
  expanded: Set<string>,
  candidates = false,
  state = false
) {
  const words = relationWords[model.lang]
  const groups = new Map<string, RelationGroupEdge>()
  for (const link of model.links) {
    if (link.resolution === "candidate" && !candidates) continue
    if (link.relation === "state_handoff" && !state) continue
    const source = model.moduleOf.get(link.source.flow_id)!
    const target = model.moduleOf.get(link.target.flow_id)!
    const internal = source.id === target.id
    if (internal && !expanded.has(source.id)) continue
    const sourceHandle = expanded.has(source.id)
      ? `out:${link.source.flow_id}`
      : "out"
    const targetHandle = expanded.has(target.id)
      ? `${internal ? "internal" : "in"}:${link.target.flow_id}`
      : "in"
    const key = JSON.stringify([
      source.id,
      sourceHandle,
      target.id,
      targetHandle,
      link.relation,
      link.resolution,
    ])
    const found = groups.get(key)
    if (found) found.data!.links.push(link)
    else
      groups.set(key, {
        id: key,
        source: source.id,
        target: target.id,
        sourceHandle,
        targetHandle,
        type: "relationGroup",
        data: {
          links: [link],
          label: link.name,
          relation: link.relation,
          candidate: link.resolution === "candidate",
          internal,
        },
      })
  }
  const edges = [...groups.values()]
  for (const edge of edges) {
    const group = edge.data!
    const names = new Set(group.links.map((link) => link.name))
    group.label =
      group.links.length === 1
        ? group.links[0].name
        : `${names.size === 1 ? group.links[0].name : words.kind[group.relation]} · ${group.links.length}`
    const parallel = edges.filter(
      (other) =>
        other.source === edge.source &&
        other.target === edge.target &&
        other.sourceHandle === edge.sourceHandle &&
        other.targetHandle === edge.targetHandle
    )
    group.lane = (parallel.indexOf(edge) - (parallel.length - 1) / 2) * 44
  }
  const graph = new dagre.graphlib.Graph({ multigraph: true })
  graph.setGraph({
    rankdir: "LR",
    nodesep: 72,
    ranksep: 260,
    marginx: 40,
    marginy: 40,
  })
  graph.setDefaultEdgeLabel(() => ({}))
  const nodes: RelationModuleNode[] = model.modules.map((module) => {
    const open = expanded.has(module.id)
    const height = 88 + (open ? module.flows.length * 52 + 8 : 0)
    graph.setNode(module.id, { width: 300, height })
    return {
      id: module.id,
      type: "relationModule",
      position: { x: 0, y: 0 },
      width: 300,
      height,
      draggable: false,
      data: {
        moduleId: module.id,
        name: module.name ?? (model.lang === "zh" ? "其他流程" : "Other flows"),
        expanded: open,
        flows: module.flows.map(({ flow }) => ({
          id: flow.flow_id,
          name: flow.name,
        })),
      },
    }
  })
  for (const edge of edges)
    if (edge.source !== edge.target)
      graph.setEdge(edge.source, edge.target, {}, edge.id)
  dagre.layout(graph)
  for (const node of nodes) {
    const placed = graph.node(node.id)
    node.position = {
      x: placed.x - placed.width / 2,
      y: placed.y - placed.height / 2,
    }
  }
  return { nodes, edges }
}

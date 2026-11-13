// The parts of the Genesis contracts the viewer reads. Source of truth:
// packages/genesis_contracts/src/genesis_contracts/{business_map,change_report}.py

export type Side = "base" | "head"
export type Resolution = "resolved" | "candidate" | "unknown"
export type StepKind = "trigger" | "action" | "decision" | "external" | "result"
export type EdgeRelation = "sequence" | "branch" | "loop" | "exception" | "call"
export type EntryKind =
  | "http_route"
  | "cli_command"
  | "task"
  | "scheduled"
  | "public_api"
  | "agent_tool"
  | "main"
  | "root"
export type Severity = "info" | "low" | "medium" | "high"
export type RiskCategory =
  | "reliability"
  | "correctness"
  | "data_integrity"
  | "security"
  | "performance"
  | "other"

export interface EvidenceRef {
  evidence_id: string
  side: Side
  path: string
  range: { start_line: number; end_line: number }
}

export interface Limitation {
  code: string
  message: string
  affects_completeness?: boolean
}

export interface MapEntry {
  entry_id: string
  symbol_id: string
  kind: EntryKind
  detection: "adapter" | "root_heuristic" | "agent_proposed"
  framework?: string
  attributes?: Record<string, string>
  evidence_ids: string[]
}

export interface StepContract {
  input: string
  output: string
  constraints?: string
}

export interface MapStep {
  step_id: string
  name: string
  kind: StepKind
  support: "static_fact" | "agent_synthesis"
  resolution: Resolution
  reason?: string
  contract?: StepContract
  anchors?: string[]
  evidence_ids?: string[]
  finding_ids?: string[]
}

export interface MapEdge {
  source: string
  target: string
  relation: EdgeRelation
  condition?: { label: string; branch?: string; anchor: string }
  label?: string
  support: "static_fact" | "agent_synthesis"
  resolution: Resolution
  reason?: string
  evidence_ids?: string[]
}

export interface MapFlow {
  flow_id: string
  name: string
  summary?: string
  stage: "skeleton" | "synthesized"
  support: "static_fact" | "agent_synthesis"
  /** `supporting` flows are lookups and upkeep around the business processes. */
  tier?: "primary" | "supporting"
  /** A skeleton flow the plan has named: a business name over steps not described yet. */
  name_from_plan?: boolean
  entries: MapEntry[]
  steps?: MapStep[]
  edges?: MapEdge[]
  accounting: {
    accountable: number
    covered: number
    omitted: number
    unaccounted: number
    truncated?: boolean
  }
  omitted?: { anchor: string; reason: string; note?: string }[]
  unaccounted?: string[]
  finding_ids?: string[]
  limitations?: Limitation[]
}

export interface MapDomain {
  domain_id: string
  name: string
  support: "agent_synthesis" | "path_grouping"
  flow_ids: string[]
}

export interface MapFinding {
  finding_id: string
  source: "rule" | "agent_observation"
  rule?: string
  severity: Severity
  category?: RiskCategory
  statement: string
  evidence_ids: string[]
  condition?: string
  gap?: string
}

export interface MapLink {
  link_id: string
  source: { flow_id: string; step_id?: string }
  target: { flow_id: string; step_id?: string }
  relation: "call" | "async_task" | "event" | "state_handoff"
  name: string
  support?: "static_fact" | "agent_synthesis"
  resolution: "resolved" | "candidate"
  reason?: string
  anchors?: string[]
  source_evidence_ids?: string[]
  target_evidence_ids?: string[]
}

export interface BusinessMap {
  snapshot_id: string
  side: Side
  analysis_status: "complete" | "partial"
  domains?: MapDomain[]
  flows?: MapFlow[]
  links?: MapLink[]
  findings?: MapFinding[]
  unassigned_finding_ids?: string[]
  coverage: {
    scope: string
    entries_total: number
    entries_planned: number
    entries_skipped: number
    skipped_entries?: {
      entry_id: string
      symbol_id: string
      reason: string
      note?: string
    }[]
    entries_unhandled: number
    tasks_total: number
    tasks_validated: number
    tasks_pending: number
    tasks_failed?: number
    limitations?: Limitation[]
  }
  limitations?: Limitation[]
  evidence?: EvidenceRef[]
}

export type ChangeKind =
  | "condition_added"
  | "condition_removed"
  | "condition_modified"
  | "call_added"
  | "call_removed"
  | "call_modified"
  | "call_target_changed"
  | "result_added"
  | "result_removed"
  | "result_modified"
  | "loop_added"
  | "loop_removed"
  | "loop_bound_changed"
  | "symbol_added"
  | "symbol_removed"
  | "symbol_moved"
  | "source_added"
  | "source_removed"
  | "source_modified"
  | "test_added"
  | "test_removed"
  | "test_modified"

export interface ChangeSide {
  side: Side
  text: string
  anchor: string
  evidence_ids: string[]
}

export interface Projection {
  status: "projected" | "removed_step" | "unassigned"
  flow_id?: string
  step_id?: string
  removed_step?: { step_id: string; name: string }
  reason?: string
}

export type Verdict = "covered" | "reached_only" | "not_reached" | "unknown"

export interface CoverageAssessment {
  verdict: Verdict
  basis?: ("static_fact" | "agent_assessment" | "imported_coverage")[]
  execution_data: "imported" | "not_collected"
  note?: string
  items?: {
    test_id: string
    tags?: string[]
    executed?: boolean
    evidence_ids: string[]
  }[]
}

export interface ChangeItem {
  change_id: string
  kind: ChangeKind
  symbol_id: string
  before?: ChangeSide
  after?: ChangeSide
  detail?: string
  projection: Projection
  other_projections?: Projection[]
  explanation?: { summary: string; short_summary?: string; effect?: string }
  tests?: CoverageAssessment
  finding_ids?: string[]
}

export interface FindingChange {
  status: "introduced" | "resolved" | "persisting"
  finding: MapFinding
  flow_id?: string
  step_id?: string
}

export interface ChangeReport {
  base_ref?: string
  base_revision?: string
  head_ref?: string
  head_revision?: string
  analysis_status: "complete" | "partial"
  changes?: ChangeItem[]
  removed_flows?: MapFlow[]
  possibly_affected?: {
    flow_id: string
    change_ids: string[]
    reason: string
  }[]
  unanalyzed_changes?: {
    path: string
    change: "added" | "modified" | "deleted" | "renamed"
    reason: string
  }[]
  finding_changes?: FindingChange[]
  limitations?: Limitation[]
  evidence?: EvidenceRef[]
}

export interface Payload {
  format_version: number
  share: boolean
  map: BusinessMap
  report: ChangeReport | null
  excerpts: Record<string, string>
}

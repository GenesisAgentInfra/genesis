import type {
  ChangeItem,
  CoverageAssessment,
  MapFinding,
  RiskCategory,
} from "./types"

export const RISK_CATEGORIES = [
  "reliability",
  "correctness",
  "data_integrity",
  "security",
  "performance",
  "other",
] as const satisfies readonly RiskCategory[]
export type DisplayCategory = RiskCategory | "unclassified"

/** Older reports remain readable; unknown categories are never inferred from prose. */
export function categoryOf(finding: MapFinding): DisplayCategory {
  return RISK_CATEGORIES.includes(finding.category as RiskCategory)
    ? finding.category!
    : "unclassified"
}

export function shortSummary(change: ChangeItem): string | undefined {
  return change.explanation?.short_summary || change.explanation?.summary
}

/** These describe source evidence, never test execution or freedom from bugs. */
export function coverageKind(tests?: CoverageAssessment) {
  if (!tests) return "unknown"
  if (tests.verdict === "covered") return "asserted"
  if (tests.verdict === "not_reached") return "uncovered"
  if (tests.verdict === "reached_only") {
    const staticOnly =
      tests.basis?.length && tests.basis.every((item) => item === "static_fact")
    return staticOnly ? "unknown" : "related"
  }
  return "unknown"
}

const severityOrder = { high: 0, medium: 1, low: 2, info: 3 }
export function sortAlerts(findings: MapFinding[]): MapFinding[] {
  return [
    ...new Map(
      findings.map((finding) => [finding.finding_id, finding])
    ).values(),
  ].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity])
}

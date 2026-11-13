import type {
  ChangeItem,
  CoverageAssessment,
  MapFinding,
  Payload,
  RiskCategory,
} from "./types"

const RISK_CATEGORIES = [
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

/** Accept only immutable GitHub blob links supplied by the renderer. */
export function sourceLinkOf(payload: Payload, ids: string[]) {
  for (const id of ids) {
    const link = payload.source_links?.[id]
    if (!link) continue
    try {
      const url = new URL(link.url)
      if (
        url.protocol === "https:" &&
        url.hostname === "github.com" &&
        !url.username &&
        !url.password &&
        /^\/[^/]+\/[^/]+\/blob\/[a-f0-9]{40,64}\//i.test(url.pathname)
      )
        return link
    } catch {
      /* Older reports and invalid links keep their local source evidence. */
    }
  }
  return undefined
}

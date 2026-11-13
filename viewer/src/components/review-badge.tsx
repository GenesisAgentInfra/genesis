import { Badge } from "@/components/ui/badge"
import type { Strings } from "@/i18n"
import type { TestStatus } from "@/model"

/** One category label, with risk taking precedence over missing validation. */
export function ReviewBadge({
  risky,
  status,
  t,
  count = 1,
}: {
  risky: boolean
  status?: TestStatus
  t: Strings
  count?: number
}) {
  if (risky)
    return (
      <Badge variant="destructive">
        {t.riskLabel}
        {count > 1 ? ` +${count - 1}` : ""}
      </Badge>
    )
  if (status === "tested")
    return <Badge variant="secondary">{t.coverage.asserted}</Badge>
  return (
    <Badge
      variant="secondary"
      className={
        status === "untested" ? "bg-change-bg text-change-ink" : undefined
      }
    >
      {t.needsValidation}
    </Badge>
  )
}

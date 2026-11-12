import type { Strings } from "@/i18n"
import type { Model } from "@/model"

/** Code compared line by line, whatever it was indented by. */
function plain(text?: string): string | undefined {
  return text
    ?.split("\n")
    .map((line) => line.trim())
    .join("\n")
    .trim()
}

/** Where a statement comes from in the code, and the code itself when the page carries it. */
export function Evidence({
  ids,
  model,
  t,
  skipText,
}: {
  ids: string[]
  model: Model
  t: Strings
  skipText?: string
}) {
  const refs = ids
    .map((id) => model.evidence.get(id))
    .filter((ref) => ref !== undefined)
  if (!refs.length) return null
  return (
    <div className="flex flex-col gap-2" aria-label={t.code}>
      {refs.map((ref) => {
        const lines =
          ref.range.start_line === ref.range.end_line
            ? `${ref.range.start_line}`
            : `${ref.range.start_line}–${ref.range.end_line}`
        const excerpt = model.excerpts[ref.evidence_id]
        // The code already shown above it is not shown twice.
        const text =
          excerpt !== undefined && plain(excerpt) !== plain(skipText)
            ? excerpt
            : undefined
        return (
          <figure key={ref.evidence_id} className="m-0">
            <figcaption className="font-mono text-[11.5px] leading-[17px] text-ink-3">
              {ref.path}:{lines}
            </figcaption>
            {text !== undefined && (
              <pre className="mt-1 max-h-64 overflow-auto rounded-[10px] bg-field px-3 py-2 text-[12px] leading-[18px] text-ink">
                {text}
              </pre>
            )}
          </figure>
        )
      })}
    </div>
  )
}

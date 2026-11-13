import { sourceLinkOf } from "@/presentation"
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
    <div className="flex flex-col gap-m" aria-label={t.code}>
      {refs.map((ref) => {
        const lines =
          ref.range.start_line === ref.range.end_line
            ? `${ref.range.start_line}`
            : `${ref.range.start_line}–${ref.range.end_line}`
        const source = sourceLinkOf(model.payload, [ref.evidence_id])
        const excerpt = model.excerpts[ref.evidence_id]
        // The code already shown above it is not shown twice.
        const text =
          excerpt !== undefined && plain(excerpt) !== plain(skipText)
            ? excerpt
            : undefined
        return (
          <figure key={ref.evidence_id} className="m-zero">
            <figcaption className="font-data text-body-s [overflow-wrap:anywhere] text-ink-3">
              {source ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-4"
                >
                  {ref.path}
                  {source.exact ? `:${lines}` : ""}
                </a>
              ) : (
                `${ref.path}:${lines}`
              )}
            </figcaption>
            {text !== undefined && (
              <pre className="mt-xs max-h-64 overflow-auto corner-l bg-field px-l py-m text-body-s text-ink">
                {text}
              </pre>
            )}
          </figure>
        )
      })}
    </div>
  )
}

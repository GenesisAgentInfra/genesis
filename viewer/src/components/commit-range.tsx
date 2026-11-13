import * as React from "react"
import { CommitGraph, type Branch } from "commit-graph"
import { ArrowRight, ArrowUpRight, GitGraph } from "lucide-react"

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  commitUrl,
  compareUrl,
  isSha,
  loadHistory,
  repoOf,
  type History,
  type Repo,
} from "@/history"
import type { Strings } from "@/i18n"
import { cn } from "@/lib/utils"
import type { Model } from "@/model"

/** A commit by its short name, opening on GitHub when the repository is known. */
function Sha({ sha, repo, t }: { sha: string; repo?: Repo; t: Strings }) {
  const short = sha.slice(0, 7)
  const className =
    "corner-s px-xs font-data text-body-s text-ink-2 tabular-nums"
  if (!repo || !isSha(sha))
    return (
      <span title={sha} className={className}>
        {short}
      </span>
    )
  return (
    <a
      href={commitUrl(repo, sha)}
      target="_blank"
      rel="noreferrer"
      title={t.openCommit(short)}
      className={cn(
        className,
        "underline decoration-line underline-offset-[3px] transition-colors duration-160 hover:text-ink hover:decoration-ink-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-select"
      )}
    >
      {short}
    </a>
  )
}

/** The two revisions the report compares; clicking it opens the commits between them. */
export function CommitRange({ model, t }: { model: Model; t: Strings }) {
  const report = model.payload.report
  const base = report?.base_revision
  const head = report?.head_revision
  const repo = React.useMemo(() => repoOf(model.payload), [model.payload])
  const [open, setOpen] = React.useState(false)
  const anchor = React.useRef<HTMLDivElement>(null)
  if (!base || !head) return null
  return (
    <Popover
      open={open}
      onOpenChange={(next, details) => {
        // The pill toggles the tree itself, so a press on it is not a press outside.
        const target = details.event.target
        if (
          details.reason === "outside-press" &&
          target instanceof Node &&
          anchor.current?.contains(target)
        )
          return
        setOpen(next)
      }}
    >
      <div
        ref={anchor}
        // The commits open on GitHub; anywhere else on the pill opens the tree.
        onClick={(event) => {
          const target = event.target as HTMLElement
          if (target.closest("a, [data-slot=popover-trigger]")) return
          setOpen((value) => !value)
        }}
        className={cn(
          "hidden h-9 items-center gap-xxs",
          "corner-full py-xs pr-m pl-xs",
          "cursor-pointer bg-card shadow-[var(--shadow-node)] ring-1 ring-line transition-shadow duration-160",
          "hover:shadow-[var(--shadow-node-hover)] md:inline-flex",
          open && "ring-ink-3/40"
        )}
      >
        <PopoverTrigger
          aria-label={t.showHistory}
          title={t.showHistory}
          className={cn(
            "inline-flex size-7 items-center justify-center",
            "corner-full",
            "text-ink-3 transition-colors duration-160",
            "hover:bg-field hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-select",
            "data-popup-open:bg-field data-popup-open:text-ink"
          )}
        >
          <GitGraph aria-hidden className="size-3.5" />
        </PopoverTrigger>
        <Sha sha={base} repo={repo} t={t} />
        <ArrowRight aria-hidden className="size-3 shrink-0 text-ink-3" />
        <Sha sha={head} repo={repo} t={t} />
      </div>
      <PopoverContent
        anchor={anchor}
        align="start"
        sideOffset={8}
        className="w-[440px] max-w-[calc(100vw-32px)] gap-zero corner-xl p-zero shadow-[var(--shadow-float)] ring-line"
      >
        <Tree base={base} head={head} repo={repo} t={t} />
      </PopoverContent>
    </Popover>
  )
}

type Read =
  | { state: "loading" }
  | { state: "done"; history: History }
  | { state: "failed" }

/** A colour the graph draws with, as the rendition on show resolves it. */
const token = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

function Tree({
  base,
  head,
  repo,
  t,
}: {
  base: string
  head: string
  repo?: Repo
  t: Strings
}) {
  const readable = Boolean(repo && isSha(base) && isSha(head))
  const [read, setRead] = React.useState<Read>(() =>
    readable ? { state: "loading" } : { state: "failed" }
  )
  React.useEffect(() => {
    if (!repo || !readable) return
    let live = true
    loadHistory(repo, base, head).then(
      (history) => live && setRead({ state: "done", history }),
      () => live && setRead({ state: "failed" })
    )
    return () => {
      live = false
    }
  }, [repo, readable, base, head])

  // The graph keeps 250px for its lines whatever their number; the rows start where the
  // lines end instead.
  const tree = React.useRef<HTMLDivElement>(null)
  React.useLayoutEffect(() => {
    const svg = tree.current?.querySelector("svg")
    if (svg)
      tree.current?.style.setProperty(
        "--graph",
        `${svg.getAttribute("width") ?? 28}px`
      )
  })

  const lang = document.documentElement.lang || undefined
  const date = React.useCallback(
    (value: string | number | Date) =>
      new Date(value).toLocaleString(lang, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
    [lang]
  )
  const branches = React.useMemo<Branch[]>(() => {
    const at = (name: string, sha: string): Branch => ({
      name,
      commit: { sha },
      link: repo ? commitUrl(repo, sha) : undefined,
    })
    const heads = [at(t.revAfter, head), at(t.revBefore, base)]
    if (read.state === "done" && read.history.relation === "diverged")
      heads.push(at(t.commonAncestor, read.history.mergeBase))
    return heads
  }, [base, head, read, repo, t])

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-l px-xl pt-xl pb-l">
        <p className="min-w-0 flex-1 truncate text-body-m font-medium text-ink">
          {read.state === "done"
            ? t.relation(
                read.history.relation,
                read.history.ahead,
                read.history.behind
              )
            : `${base.slice(0, 7)} → ${head.slice(0, 7)}`}
        </p>
        {repo && isSha(base) && isSha(head) && (
          <a
            href={compareUrl(repo, base, head)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center gap-xs corner-full px-m py-xs text-body-s font-medium text-ink-2 transition-colors duration-160 hover:bg-field hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-select"
          >
            {t.compareOnGitHub}
            <ArrowUpRight aria-hidden className="size-3" />
          </a>
        )}
      </div>
      <div className="h-px bg-line/70" />
      {read.state === "loading" && (
        <div aria-busy className="flex flex-col gap-xxl px-xl py-xl">
          <span className="sr-only">{t.historyLoading}</span>
          {[0, 1].map((row) => (
            <div key={row} className="flex items-center gap-l">
              <span className="size-3 shrink-0 animate-pulse corner-full bg-field" />
              <span className="flex flex-1 flex-col gap-s">
                <span className="h-3 w-3/4 animate-pulse corner-full bg-field" />
                <span className="h-2.5 w-1/3 animate-pulse corner-full bg-field" />
              </span>
            </div>
          ))}
        </div>
      )}
      {read.state === "failed" && (
        <p className="px-xl py-xl text-body-m text-ink-2">{t.historyFailed}</p>
      )}
      {read.state === "done" && (
        <div
          ref={tree}
          className="commit-tree max-h-[min(56dvh,420px)] [scrollbar-width:thin] overflow-y-auto px-l pt-xxl pb-xs"
        >
          <CommitGraph
            commits={read.history.commits}
            branchHeads={branches}
            currentBranch={t.revAfter}
            dateFormatFn={date}
            graphStyle={{
              commitSpacing: 60,
              branchSpacing: 18,
              nodeRadius: 2,
              branchColors: [
                token("--edge-strong"),
                token("--edge"),
                token("--ink-3"),
              ],
            }}
          />
          {read.history.more > 0 && (
            <p className="px-xs pb-xs text-body-s text-ink-3">
              {t.historyMore(read.history.more)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

import type { Commit } from "commit-graph"

import type { Payload } from "@/types"

/** The GitHub repository the report's source links point into. */
export interface Repo {
  owner: string
  name: string
  url: string
}

const GITHUB = "https://github.com"
const GITHUB_API = "https://api.github.com"
/** A source link the renderer wrote: `<GITHUB>/<owner>/<name>/blob/…`. */
const BLOB = new RegExp(
  `^${GITHUB.replaceAll(".", "\\.")}/([\\w.-]+)/([\\w.-]+)/blob/`
)

/**
 * The renderer links source only into a repository whose commits it found published, so a
 * repository with a source link is one whose commits GitHub can show.
 */
export function repoOf(payload: Payload): Repo | undefined {
  for (const link of Object.values(payload.source_links ?? {})) {
    const match = BLOB.exec(link.url)
    if (match)
      return {
        owner: match[1],
        name: match[2],
        url: `${GITHUB}/${match[1]}/${match[2]}`,
      }
  }
  return undefined
}

/** A worktree pseudo-revision or a branch name is not a commit GitHub can open. */
export const isSha = (value?: string): value is string =>
  Boolean(value && /^[0-9a-f]{7,40}$/i.test(value))

export const commitUrl = (repo: Repo, sha: string) =>
  `${repo.url}/commit/${sha}`
export const compareUrl = (repo: Repo, base: string, head: string) =>
  `${repo.url}/compare/${base}...${head}`

/** How the commit after the change stands to the one before it. */
export type Relation = "ahead" | "behind" | "diverged" | "identical"

export interface History {
  relation: Relation
  /** Commits only the side after the change has. */
  ahead: number
  /** Commits only the side before the change has. */
  behind: number
  /** Newest first, ending on the common ancestor. */
  commits: Commit[]
  mergeBase: string
  /** Commits between the two that the list leaves out. */
  more: number
}

/** The most commits drawn on either side; GitHub shows the rest. */
const SHOWN = 40

interface GitHubCommit {
  sha: string
  html_url?: string
  parents: { sha: string }[]
  commit: {
    message: string
    author?: { name?: string; email?: string; date?: string }
    committer?: { date?: string }
  }
}
interface Comparison {
  status: Relation
  ahead_by: number
  behind_by: number
  total_commits: number
  base_commit: GitHubCommit
  merge_base_commit: GitHubCommit
  commits: GitHubCommit[]
}

const asked = new Map<string, Promise<History>>()

async function compare(repo: Repo, from: string, to: string) {
  const response = await fetch(
    `${GITHUB_API}/repos/${repo.owner}/${repo.name}/compare/${from}...${to}`,
    { headers: { Accept: "application/vnd.github+json" } }
  )
  if (!response.ok) throw new Error(`GitHub ${response.status}`)
  return (await response.json()) as Comparison
}

const dateOf = (commit: GitHubCommit) =>
  commit.commit.committer?.date ?? commit.commit.author?.date ?? ""

/**
 * The commits between the two revisions, read from GitHub when the reader asks for them:
 * the page itself loads nothing when it opens.
 */
export function loadHistory(
  repo: Repo,
  base: string,
  head: string
): Promise<History> {
  const key = `${repo.url}|${base}|${head}`
  const known = asked.get(key)
  if (known) return known
  const pending = (async (): Promise<History> => {
    const forward = await compare(repo, base, head)
    // A side the other does not contain needs its own list of commits.
    const backward =
      forward.status === "diverged" || forward.status === "behind"
        ? await compare(repo, head, base)
        : undefined
    const after = [...forward.commits].reverse()
    const before = backward ? [...backward.commits].reverse() : []
    const shown = [...after.slice(0, SHOWN), ...before.slice(0, SHOWN)].sort(
      (a, b) => dateOf(b).localeCompare(dateOf(a))
    )
    const mergeBase = forward.merge_base_commit
    const list = [...shown, mergeBase].filter(
      (commit, index, all) =>
        all.findIndex((other) => other.sha === commit.sha) === index
    )
    const present = new Set(list.map((commit) => commit.sha))
    return {
      relation: forward.status,
      ahead: forward.ahead_by,
      behind: forward.behind_by,
      mergeBase: mergeBase.sha,
      more:
        Math.max(0, after.length - SHOWN) +
        Math.max(0, before.length - SHOWN) +
        Math.max(0, forward.total_commits - forward.commits.length),
      commits: list.map((commit) => ({
        sha: commit.sha,
        html_url: commit.html_url ?? commitUrl(repo, commit.sha),
        // Only the lines the list can draw: a parent outside it ends the line there.
        parents: commit.parents.filter((parent) => present.has(parent.sha)),
        commit: {
          message: commit.commit.message.split("\n")[0],
          author: {
            name: commit.commit.author?.name ?? "",
            email: commit.commit.author?.email,
            date: dateOf(commit),
          },
        },
      })),
    }
  })()
  asked.set(key, pending)
  // A failed read may be asked again, once the reader is back online.
  pending.catch(() => asked.delete(key))
  return pending
}

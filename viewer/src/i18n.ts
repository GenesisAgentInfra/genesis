import type { TestStatus } from "./model"
import type {
  ChangeKind,
  EntryKind,
  Limitation,
  Severity,
  StepKind,
  Verdict,
} from "./types"

export type Lang = "zh" | "en"

const CJK = /[㐀-鿿豈-﫿]/g
const LATIN = /[A-Za-z]/g

/** Fixed interface text follows the language the agent wrote the content in. */
export function detectLang(samples: string[]): Lang {
  let cjk = 0
  let latin = 0
  for (const text of samples) {
    cjk += text.match(CJK)?.length ?? 0
    latin += text.match(LATIN)?.length ?? 0
  }
  // A Chinese description still carries identifiers; one CJK character outweighs
  // a few Latin letters of code.
  return cjk > 0 && cjk * 3 >= latin ? "zh" : "en"
}

const zh = {
  flowGone: "这条流程在改动后不存在了。",
  mayAffect: "可能影响",
  andMore: (n: number) => `等 ${n} 个`,
  untestedCount: (n: number) => `${n} 处没测到`,
  newRiskCount: (n: number) => `${n} 个新风险`,
  testsChanged: (n: number) => `改了 ${n} 个测试`,
  nodeHint: "按 Enter 或空格查看详情，按 ← → 切换改动。",
  overview: "总览",
  stepsCount: (n: number) => `${n} 步`,
  stepsBetween: (n: number) => `中间 ${n} 步`,
  shownSteps: (shown: number, total: number) => `${total} 步中的 ${shown} 步`,
  changesPass: (n: number) => `${n} 处改动会经过这里`,
  openModule: "展开全部步骤",
  stepThrough: "逐个看",
  prevChange: "上一处改动",
  nextChange: "下一处改动",
  walking: "走一遍",
  walkDone: "走完了",
  stopWalk: "停止",
  endWalk: "结束",
  zoomIn: "放大",
  zoomOut: "缩小",
  sameChange: "同一处改动",
  runFlow: "走一遍",
  skeletonTag: "代码结构",
  notDescribed: "未归纳",
  supportingRow: (n: number) => `另有 ${n} 条查询和维护流程`,
  entryKind: {
    http_route: "接口请求",
    cli_command: "命令",
    task: "后台任务",
    scheduled: "定时任务",
    public_api: "公开函数",
    agent_tool: "Agent 工具",
    main: "程序入口",
    root: "入口候选",
  } satisfies Record<EntryKind, string>,
  looseFlows: "其他流程",
  offMapCard: "流程之外",
  moduleFlows: (n: number) => `${n} 条流程`,
  moduleChanges: (n: number) => `${n} 处改动`,
  mapSize: (modules: number, flows: number) =>
    `${modules} 个模块 · ${flows} 条流程`,
  overviewSentence: (
    names: string[],
    modules: number,
    flows: number,
    apart: number,
    passing: number
  ) => {
    let head: string
    if (!flows) head = "这次改动都在流程之外"
    else if (!names.length) head = `这次改动落在 ${flows} 条流程上`
    else {
      const listed = names
        .slice(0, 2)
        .map((name) => `「${name}」`)
        .join("")
      const many =
        modules > 2
          ? `等 ${modules} 个模块`
          : modules > 1
            ? `${modules} 个模块`
            : "模块"
      head = `这次改动落在${listed}${many}的 ${flows} 条流程上`
    }
    const more = [
      apart && flows ? `另有 ${apart} 处在流程之外` : "",
      passing
        ? `${apart && flows ? "还" : "另"}有 ${passing} 条流程会经过这些改动`
        : "",
    ].filter(Boolean)
    return `${[head, ...more].join("，")}。`
  },
  status: {
    tested: "有测试",
    untested: "没测到",
    unsure: "不确定",
  } satisfies Record<TestStatus, string>,
  filesOnly: "改过的文件都没能分析。",
  partialHint: "这次分析没有全部完成：",
  refs: "对比",
  workingTree: "工作区",
  partial: "部分完成",
  flows: "流程",
  changes: "改动",
  risks: "风险",
  offMap: "不在流程上的改动",
  offMapHint: "这处改动没有落在任何一个步骤上",
  basis: "测试结论来自阅读测试源码，没有运行测试。",
  effect: "对用户的影响",
  before: "之前",
  after: "之后",
  placed: "放在这一步的原因",
  tests: "相关测试",
  viewCode: "查看代码",
  hideCode: "收起代码",
  code: "代码",
  removed: "已删除",
  removedFlow: "这条流程在改动后不存在了，下面是改动前的样子。",
  removedSteps: "被删除的步骤",
  removedFlows: "被删除的流程",
  noData: "这个页面里没有地图数据。请用 genesis map render 重新生成。",
  newStep: "新增",
  totalChanges: (n: number, more = false) => `共 ${n}${more ? "+" : ""} 处改动`,
  newRisk: "新风险",
  knownRisk: "风险",
  fitView: "看全图",
  close: "关闭",
  inCode: "所在代码",
  moreChanges: (n: number) => `另有 ${n} 处改动`,
  unconfirmed: "待确认",
  unknown: "未知",
  repeats: "重复这一步",
  noFlow: "没有可以显示的流程。",
  unanalyzed: "这些改过的文件没有被分析",
  summaryNoChange: "这次对比没有发现产品逻辑上的改动。",
  filesNotAnalyzed: (n: number) => `${n} 个文件没分析`,
  limitations: "说明",
  severity: {
    info: "提示",
    low: "低",
    medium: "中",
    high: "高",
  } satisfies Record<Severity, string>,
  findingStatus: {
    introduced: "本次引入",
    resolved: "本次消除",
    persisting: "原本就有",
  },
  stepKind: {
    trigger: "触发",
    action: "动作",
    decision: "判断",
    external: "外部调用",
    result: "结果",
  } satisfies Record<StepKind, string>,
  verdict: {
    covered: "有测试覆盖",
    reached_only: "测到代码 · 没测到改动",
    not_reached: "没有测试",
    unknown: "无法判断",
  } satisfies Record<Verdict, string>,
  changeKind: {
    condition_added: "新增判断",
    condition_removed: "删除判断",
    condition_modified: "判断条件改了",
    call_added: "新增调用",
    call_removed: "删除调用",
    call_modified: "调用改了",
    call_target_changed: "调用对象换了",
    result_added: "新增结果",
    result_removed: "删除结果",
    result_modified: "结果改了",
    loop_added: "新增循环",
    loop_removed: "删除循环",
    loop_bound_changed: "循环次数改了",
    symbol_added: "新增函数",
    symbol_removed: "删除函数",
    symbol_moved: "函数移动",
    source_added: "新增代码",
    source_removed: "删除代码",
    source_modified: "代码改了",
    test_added: "新增测试",
    test_removed: "删除测试",
    test_modified: "测试改了",
  } satisfies Record<ChangeKind, string>,
}

export type Strings = typeof zh

const en: Strings = {
  flowGone: "This flow no longer exists after the change.",
  mayAffect: "May affect",
  andMore: (n) => `and ${n} more`,
  untestedCount: (n) => `${n} untested`,
  newRiskCount: (n) => `${n} new risk${n === 1 ? "" : "s"}`,
  testsChanged: (n) => `${n} test${n === 1 ? "" : "s"} changed`,
  nodeHint: "Press Enter or Space for details; ← and → move between changes.",
  overview: "Overview",
  stepsCount: (n) => `${n} step${n === 1 ? "" : "s"}`,
  stepsBetween: (n) => `${n} step${n === 1 ? "" : "s"} between`,
  shownSteps: (shown, total) => `${shown} of ${total} steps`,
  changesPass: (n) =>
    `${n} change${n === 1 ? " passes" : "s pass"} through here`,
  openModule: "Show every step",
  stepThrough: "One by one",
  prevChange: "Previous change",
  nextChange: "Next change",
  walking: "Walking through",
  walkDone: "Walked through",
  stopWalk: "Stop",
  endWalk: "Done",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  sameChange: "Same change",
  runFlow: "Walk through",
  skeletonTag: "Code structure",
  notDescribed: "Not described yet",
  supportingRow: (n) => `${n} more lookup and upkeep flow${n === 1 ? "" : "s"}`,
  entryKind: {
    http_route: "HTTP request",
    cli_command: "Command",
    task: "Background task",
    scheduled: "Scheduled job",
    public_api: "Public API",
    agent_tool: "Agent tool",
    main: "Program entry",
    root: "Candidate entry",
  },
  looseFlows: "Other flows",
  offMapCard: "Outside the flows",
  moduleFlows: (n) => `${n} flow${n === 1 ? "" : "s"}`,
  moduleChanges: (n) => `${n} change${n === 1 ? "" : "s"}`,
  mapSize: (modules, flows) =>
    `${modules} module${modules === 1 ? "" : "s"} · ${flows} flow${flows === 1 ? "" : "s"}`,
  overviewSentence: (names, modules, flows, apart, passing) => {
    const plural = flows === 1 ? "" : "s"
    let head: string
    if (!flows) head = "All of this change sits outside the flows"
    else if (!names.length) head = `This change lands on ${flows} flow${plural}`
    else {
      const listed =
        modules > 2
          ? `${names.slice(0, 2).join(", ")} and ${modules - 2} more modules`
          : names.join(" and ")
      head = `This change lands on ${flows} flow${plural} in ${listed}`
    }
    const more = [
      apart && flows
        ? `${apart} more ${apart === 1 ? "sits" : "sit"} outside the flows`
        : "",
      passing
        ? `${passing} other flow${passing === 1 ? " reaches" : "s reach"} the changed code`
        : "",
    ].filter(Boolean)
    return `${[head, ...more].join("; ")}.`
  },
  status: { tested: "Tested", untested: "Untested", unsure: "Unsure" },
  filesOnly: "None of the changed files could be analyzed.",
  partialHint: "This analysis is not complete:",
  refs: "Comparing",
  workingTree: "working tree",
  partial: "Partial",
  flows: "Flows",
  changes: "Changes",
  risks: "Risks",
  offMap: "Change off the map",
  offMapHint: "This change sits on no step of any flow",
  basis: "Test verdicts come from reading test source. No test was run.",
  effect: "What it means for users",
  before: "Before",
  after: "After",
  placed: "Why it sits on this step",
  tests: "Related tests",
  viewCode: "View code",
  hideCode: "Hide code",
  code: "Code",
  removed: "Removed",
  removedFlow:
    "This flow no longer exists after the change. This is how it looked before.",
  removedSteps: "Removed steps",
  removedFlows: "Removed flows",
  noData: "This page carries no map data. Run genesis map render again.",
  newStep: "New",
  totalChanges: (n, more = false) =>
    `${n}${more ? "+" : ""} change${n === 1 && !more ? "" : "s"}`,
  newRisk: "New risk",
  knownRisk: "Risk",
  fitView: "Fit to view",
  close: "Close",
  inCode: "In the code",
  moreChanges: (n) => `${n} more change${n === 1 ? "" : "s"}`,
  unconfirmed: "Unconfirmed",
  unknown: "Unknown",
  repeats: "Repeats",
  noFlow: "No flow to show.",
  unanalyzed: "Changed files that were not analyzed",
  summaryNoChange: "No change to product logic was found in this comparison.",
  filesNotAnalyzed: (n) => `${n} file${n === 1 ? "" : "s"} not analyzed`,
  limitations: "Notes",
  severity: { info: "Info", low: "Low", medium: "Medium", high: "High" },
  findingStatus: {
    introduced: "Introduced",
    resolved: "Resolved",
    persisting: "Persisting",
  },
  stepKind: {
    trigger: "Trigger",
    action: "Action",
    decision: "Decision",
    external: "External",
    result: "Result",
  },
  verdict: {
    covered: "Covered",
    reached_only: "Reached · change untested",
    not_reached: "No test",
    unknown: "Can’t tell",
  },
  changeKind: {
    condition_added: "Condition added",
    condition_removed: "Condition removed",
    condition_modified: "Condition changed",
    call_added: "Call added",
    call_removed: "Call removed",
    call_modified: "Call changed",
    call_target_changed: "Call target changed",
    result_added: "Result added",
    result_removed: "Result removed",
    result_modified: "Result changed",
    loop_added: "Loop added",
    loop_removed: "Loop removed",
    loop_bound_changed: "Loop bound changed",
    symbol_added: "Function added",
    symbol_removed: "Function removed",
    symbol_moved: "Function moved",
    source_added: "Code added",
    source_removed: "Code removed",
    source_modified: "Code changed",
    test_added: "Test added",
    test_removed: "Test removed",
    test_modified: "Test changed",
  },
}

export const STRINGS: Record<Lang, Strings> = { zh, en }

/**
 * The CLI writes some sentences in English whatever the page language. Known ones are put in
 * the page language; anything else is shown as written.
 */
const REASONS_ZH: Record<string, string> = {
  "This entry was removed; its flow is listed under removed flows.":
    "这个入口被删掉了，它的流程列在被删除的流程里。",
  "No step on the map covers this code; flows that can reach it are listed as possibly affected.":
    "流程图上没有哪一步覆盖这段代码，能走到它的流程列为可能受影响。",
  "This code is not reachable from any entry on the map.":
    "流程图上没有哪个入口能走到这段代码。",
  "No step is anchored on this code; placed on the nearest step of the same function.":
    "没有哪一步直接建立在这段代码上，按同一个函数放在最近的一步。",
  "No step is anchored on this code; it runs under this decision.":
    "没有哪一步直接建立在这段代码上，它在这个判断之下执行。",
  "No step is anchored on this code; this step cites the changed lines.":
    "没有哪一步直接建立在这段代码上，这一步引用了改动的那几行。",
  "No step covers the body of this function; this step calls it.":
    "没有哪一步覆盖这个函数的内部，这一步调用了它。",
  "Removed code; placed on the nearest remaining step of the same function.":
    "被删掉的代码，按同一个函数放在剩下的最近一步。",
  "Configuration file; not analyzed for behaviour.": "配置文件，没有分析行为。",
  "Not a supported source language; not analyzed.":
    "不是支持的语言，没有分析。",
}

export function localizeReason(text: string, lang: Lang): string {
  if (lang !== "zh") return text
  if (REASONS_ZH[text]) return REASONS_ZH[text]
  const refers =
    /^This step's code refers to `(.+)`, which the changed line defines\.$/.exec(
      text
    )
  if (refers) return `这一步的代码用到了改动行定义的 \`${refers[1]}\`。`
  const failed = /^Could not be analyzed: (.*)$/.exec(text)
  return failed ? `无法分析：${failed[1]}` : text
}

function tail(message: string): string {
  const index = message.indexOf(": ")
  return index >= 0 ? message.slice(index + 2).replace(/\.$/, "") : ""
}

export function localizeLimitation(item: Limitation, lang: Lang): string {
  if (lang !== "zh") return item.message
  const count = /\d+/.exec(item.message)?.[0] ?? ""
  switch (item.code) {
    case "changed_file_not_analyzed":
      return `这些改过的源文件无法分析：${tail(item.message)}。`
    case "changed_files_outside_languages":
      return `${count} 个改过的文件不是支持的语言，没有分析。`
    case "affected_flow_not_synthesized":
      return `改动落在还没写成业务语言的流程上：${tail(item.message)}。`
    case "changes_truncated":
      return `找到的改动比列出的 ${count} 处更多。`
    case "source_comparison_skipped":
      return `文件太大，没有逐行对比：${tail(item.message)}。`
    case "no_execution_data":
      return "没有运行测试，也没有导入覆盖率数据，测试结论来自阅读源码。"
    default:
      return item.message
  }
}

const NOTES_ZH: Record<string, string> = {
  "The snapshot contains no test functions.": "代码里没有任何测试函数。",
  "The code no longer exists on the head side; check the tests of the code that used to call it.":
    "这段代码在改动后已经不存在了，请看原来调用它的代码有哪些测试。",
  "No test was found that calls this code or requests a route leading to it. A test may still reach it in a way static analysis does not follow.":
    "没有找到调用这段代码、或请求能走到它的接口的测试。测试仍可能以静态分析跟不到的方式走到它。",
}
const REACHED_NOTE =
  "These tests call the changed code. Static analysis cannot tell whether their inputs take the changed path or whether they assert on its result."

/** The CLI's own notes on a verdict, in the page language when they are known. */
export function localizeNote(text: string, lang: Lang): string {
  if (lang !== "zh") return text
  if (NOTES_ZH[text]) return NOTES_ZH[text]
  if (text.startsWith(REACHED_NOTE)) {
    const more = /(\d+) more tests are not listed/.exec(text)?.[1]
    return (
      "这些测试调用了改过的代码。静态分析判断不了它们的输入是否走到改动、是否检查了结果。" +
      (more ? `另有 ${more} 个测试没有列出。` : "")
    )
  }
  return text
}

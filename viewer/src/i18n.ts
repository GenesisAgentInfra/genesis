import type { TestStatus, Tone } from "./model"
import type { ChangeKind, Severity, StepKind } from "./types"

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
  nodeHint: "按 Enter 或空格查看详情，按 ← → 切换改动。",
  stepsBetween: (n: number) => `中间 ${n} 步`,
  stepsMore: (n: number) => `还有 ${n} 步`,
  openChanges: "改动清单",
  riskLabel: "风险",
  needsValidation: "待验证",
  severityLabel: "严重程度",
  testEvidence: "测试依据",
  ioContract: "输入 / 输出",
  changeOverview: "改动说明",
  githubCode: "在 GitHub 查看",
  githubCommitted: "GitHub 已提交版本",
  localCode: "本地代码",
  unchangedStep: "这个步骤没有改动。",
  copyJson: "复制 JSON",
  copied: "已复制",
  copyFailed: "复制失败，请选择 JSON 文本复制。",
  contractInput: "输入",
  contractOutput: "输出",
  contractMissing: "尚未提供这个步骤的结构化输入 / 输出。",
  category: {
    reliability: "可靠性",
    correctness: "逻辑正确性",
    data_integrity: "数据与副作用",
    security: "权限与安全",
    performance: "性能与成本",
    other: "其他风险",
    unclassified: "待分类",
  },
  coverage: {
    asserted: "有行为验证",
    related: "缺少行为验证",
    uncovered: "未找到覆盖",
    unknown: "覆盖待确认",
  },
  tone: {
    risk: "新风险",
    untested: "缺少验证",
    unsure: "待确认",
    tested: "有验证",
  } satisfies Record<Tone, string>,
  listTitle: "这次的改动",
  removedFlowRow: "流程被删除",
  openStub: "展开这条流程的全部步骤",
  changesPass: (n: number) => `${n} 处改动会经过这里`,
  openModule: "展开全部步骤",
  openShort: "展开",
  closeModule: "收起",
  closeModuleHint: "收起，回到总览（Esc）",
  prevChange: "上一处改动",
  nextChange: "下一处改动",
  walking: "走一遍",
  walkDone: "走完了",
  stopWalk: "停止",
  endWalk: "结束",
  zoomIn: "放大",
  zoomOut: "缩小",
  toDark: "切换到深色",
  toLight: "切换到浅色",
  errorPaths: "异常与回退",
  echoOf: (n: number) => `这一步也属于改动 #${n}，说明在它自己的卡片上`,
  revBefore: "改动前",
  revAfter: "改动后",
  showHistory: "查看两次提交之间的提交树",
  openCommit: (sha: string) => `在 GitHub 打开 ${sha}`,
  compareOnGitHub: "在 GitHub 比较",
  relation: (
    relation: "ahead" | "behind" | "diverged" | "identical",
    ahead: number,
    behind: number
  ) =>
    relation === "identical"
      ? "两次是同一个提交"
      : relation === "ahead"
        ? `相隔 ${ahead} 个提交`
        : relation === "behind"
          ? `改动后落后 ${behind} 个提交`
          : `从共同祖先分开：改动后 ${ahead} 个，改动前 ${behind} 个`,
  historyLoading: "正在从 GitHub 读取提交",
  historyFailed: "没能从 GitHub 读到两次之间的提交",
  historyMore: (n: number) => `另有 ${n} 个提交没有列出`,
  commonAncestor: "共同祖先",
  runFlow: "走一遍",
  skeletonTag: "代码结构",
  notDescribed: "未归纳",
  supportingRow: (n: number) => `另有 ${n} 条查询和维护流程`,
  looseFlows: "其他流程",
  offMapCard: "流程之外",
  moduleFlows: (n: number) => `${n} 条流程`,
  moduleChanges: (n: number) => `${n} 处改动`,
  mapSize: (modules: number, flows: number) =>
    `${modules} 个模块 · ${flows} 条流程`,
  status: {
    tested: "有行为验证",
    untested: "缺少行为验证",
    unsure: "覆盖待确认",
  } satisfies Record<TestStatus, string>,
  filesOnly: "改过的文件都没能分析。",
  partial: "部分完成",
  flows: "流程",
  changes: "改动",
  offMap: "不在流程上的改动",
  basis: "测试结论来自阅读测试源码，没有运行测试。",
  effect: "对用户的影响",
  before: "之前",
  after: "之后",
  placed: "放在这一步的原因",
  tests: "相关测试",
  code: "代码",
  removed: "已删除",
  removedFlow: "这条流程在改动后不存在了，下面是改动前的样子。",
  removedSteps: "被删除的步骤",
  removedFlows: "被删除的流程",
  noData: "这个页面里没有地图数据。请用 genesis map render 重新生成。",
  newStep: "新增",
  fitView: "看全图",
  close: "关闭",
  moreChanges: (n: number) => `另有 ${n} 处改动`,
  unconfirmed: "待确认",
  unknown: "未知",
  repeats: "重复这一步",
  noFlow: "没有可以显示的流程。",
  summaryNoChange: "这次对比没有发现产品逻辑上的改动。",
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
  nodeHint: "Press Enter or Space for details; ← and → move between changes.",
  stepsBetween: (n) => `${n} step${n === 1 ? "" : "s"} between`,
  stepsMore: (n) => `${n} more step${n === 1 ? "" : "s"}`,
  openChanges: "Changes",
  riskLabel: "Risk",
  needsValidation: "Needs validation",
  severityLabel: "Severity",
  testEvidence: "Test evidence",
  ioContract: "Input / output",
  changeOverview: "Overview",
  githubCode: "View on GitHub",
  githubCommitted: "GitHub committed version",
  localCode: "Local code",
  unchangedStep: "This step has not changed.",
  copyJson: "Copy JSON",
  copied: "Copied",
  copyFailed: "Could not copy. Select and copy the JSON text.",
  contractInput: "Input",
  contractOutput: "Output",
  contractMissing:
    "Structured input / output is not available for this step yet.",
  category: {
    reliability: "Reliability",
    correctness: "Correctness",
    data_integrity: "Data & side effects",
    security: "Permissions & security",
    performance: "Performance & cost",
    other: "Other risk",
    unclassified: "Unclassified",
  },
  coverage: {
    asserted: "Behavior checked",
    related: "Behavior not checked",
    uncovered: "No coverage found",
    unknown: "Coverage unclear",
  },
  tone: {
    risk: "New risk",
    untested: "Missing checks",
    unsure: "Unclear",
    tested: "Has checks",
  },
  listTitle: "Changes in this comparison",
  removedFlowRow: "Flow removed",
  openStub: "Show every step of this flow",
  changesPass: (n) =>
    `${n} change${n === 1 ? " passes" : "s pass"} through here`,
  openModule: "Show every step",
  openShort: "Open",
  closeModule: "Collapse",
  closeModuleHint: "Collapse, back to the overview (Esc)",
  prevChange: "Previous change",
  nextChange: "Next change",
  walking: "Walking through",
  walkDone: "Walked through",
  stopWalk: "Stop",
  endWalk: "Done",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  toDark: "Switch to dark",
  toLight: "Switch to light",
  errorPaths: "Errors and fallbacks",
  echoOf: (n) => `Also part of change #${n}, told on its own card`,
  revBefore: "Before",
  revAfter: "After",
  showHistory: "Show the commits between the two",
  openCommit: (sha) => `Open ${sha} on GitHub`,
  compareOnGitHub: "Compare on GitHub",
  relation: (relation, ahead, behind) =>
    relation === "identical"
      ? "The same commit"
      : relation === "ahead"
        ? `${ahead} commit${ahead === 1 ? "" : "s"} apart`
        : relation === "behind"
          ? `After is ${behind} commit${behind === 1 ? "" : "s"} behind`
          : `Split from a common ancestor: ${ahead} after, ${behind} before`,
  historyLoading: "Reading commits from GitHub",
  historyFailed: "Could not read the commits between them from GitHub",
  historyMore: (n) => `${n} more commit${n === 1 ? "" : "s"} not listed`,
  commonAncestor: "Common ancestor",
  runFlow: "Walk through",
  skeletonTag: "Code structure",
  notDescribed: "Not described yet",
  supportingRow: (n) => `${n} more lookup and upkeep flow${n === 1 ? "" : "s"}`,
  looseFlows: "Other flows",
  offMapCard: "Outside the flows",
  moduleFlows: (n) => `${n} flow${n === 1 ? "" : "s"}`,
  moduleChanges: (n) => `${n} change${n === 1 ? "" : "s"}`,
  mapSize: (modules, flows) =>
    `${modules} module${modules === 1 ? "" : "s"} · ${flows} flow${flows === 1 ? "" : "s"}`,
  status: {
    tested: "Behavior checked",
    untested: "Behavior not checked",
    unsure: "Coverage unclear",
  },
  filesOnly: "None of the changed files could be analyzed.",
  partial: "Partial",
  flows: "Flows",
  changes: "Changes",
  offMap: "Change off the map",
  basis: "Test verdicts come from reading test source. No test was run.",
  effect: "What it means for users",
  before: "Before",
  after: "After",
  placed: "Why it sits on this step",
  tests: "Related tests",
  code: "Code",
  removed: "Removed",
  removedFlow:
    "This flow no longer exists after the change. This is how it looked before.",
  removedSteps: "Removed steps",
  removedFlows: "Removed flows",
  noData: "This page carries no map data. Run genesis map render again.",
  newStep: "New",
  fitView: "Fit to view",
  close: "Close",
  moreChanges: (n) => `${n} more change${n === 1 ? "" : "s"}`,
  unconfirmed: "Unconfirmed",
  unknown: "Unknown",
  repeats: "Repeats",
  noFlow: "No flow to show.",
  summaryNoChange: "No change to product logic was found in this comparison.",
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

---
name: Genesis Viewer
description: A product's modules and flows on one quiet agent-builder canvas, with each change written on the card it touches.
colors:
  canvas: "#f4f4f5"
  card: "#ffffff"
  ink: "#111113"
  ink-2: "#5c5d63"
  ink-3: "#74757b"
  line: "#e6e6e9"
  field: "#f4f4f5"
  muted-tint: "#f1f1f3"
  handle-rim: "#c9cace"
  edge: "#cfd0d5"
  edge-strong: "#3a3b40"
  edge-exception: "#e8b7b1"
  edge-exception-strong: "#b5524a"
  select: "#2f6feb"
  change: "#e2860b"
  change-bg: "#fff6e8"
  change-ink: "#8a4a00"
  risk: "#d92d20"
  risk-bg: "#fdf0ef"
  ok: "#17803d"
  ok-bg: "#ebf7ef"
  tile-trigger-bg: "#e6f5ec"
  tile-trigger-ink: "#1a7f45"
  tile-action-bg: "#efeafd"
  tile-action-ink: "#6a3fd4"
  tile-decision-bg: "#ffeee1"
  tile-decision-ink: "#c9530a"
  tile-external-bg: "#fff4d1"
  tile-external-ink: "#9a6200"
  tile-result-bg: "#efeff1"
  tile-result-ink: "#4f5057"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: "26px"
  subhead:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: "26px"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: "20px"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "22px"
  body-sm:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: "18px"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: "16px"
  tag:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: "16px"
  mono:
    fontFamily: "ui-monospace, SF Mono, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "18px"
rounded:
  tag: "5px"
  tile-sm: "8px"
  tile: "9px"
  row: "10px"
  field: "12px"
  pill: "14px"
  bar: "16px"
  card: "18px"
  panel: "20px"
  full: "9999px"
spacing:
  hair: "4px"
  row-gap: "6px"
  row-x: "10px"
  card: "12px"
  inset: "12px"
  gutter: "16px"
  section: "24px"
  node-gap: "34px"
  rank-gap: "84px"
components:
  step-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    rounded: "{rounded.card}"
    padding: "12px"
    width: "252px"
  step-card-current:
    borderColor: "{colors.change}"
  step-card-next:
    borderColor: "rgb(226 134 11 / 0.45)"
  step-card-quiet:
    backgroundColor: "rgb(255 255 255 / 0.75)"
    textColor: "{colors.ink}"
  step-pill:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "6px 14px 6px 6px"
    height: "44px"
  kind-tile:
    rounded: "{rounded.tile}"
    size: "32px"
  kind-tile-small:
    rounded: "{rounded.tile-sm}"
    size: "28px"
  branch-row:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink-2}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.row}"
    padding: "7px 10px"
  change-field:
    backgroundColor: "{colors.change-bg}"
    textColor: "{colors.change-ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  change-field-other:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink-2}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  tag-new:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "0 4px"
  tag-risk:
    backgroundColor: "{colors.risk-bg}"
    textColor: "{colors.risk}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "0 4px"
  far-tag:
    backgroundColor: "{colors.card}"
    textColor: "{colors.change-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.full}"
    padding: "1px 8px"
  headline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.headline}"
    rounded: "{rounded.card}"
    padding: "12px 16px 10px"
    width: "600px"
  flow-chip:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    padding: "1px 8px"
  flow-chip-current:
    backgroundColor: "{colors.change-bg}"
    textColor: "{colors.change-ink}"
    rounded: "{rounded.full}"
    padding: "1px 8px"
  back-button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "28px"
  module-frame:
    backgroundColor: "rgb(255 255 255 / 0.45)"
    textColor: "{colors.ink}"
    rounded: "32px"
    padding: "32px"
  way-in:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    height: "56px"
  crumbs:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "32px"
  button-icon-ghost:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.full}"
    size: "28px"
  button-icon-ghost-hover:
    backgroundColor: "{colors.muted-tint}"
    textColor: "{colors.ink}"
  detail-panel:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.panel}"
    width: "384px"
  detail-panel-mobile:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.panel}"
    height: "52dvh"
  code-row-before:
    backgroundColor: "{colors.risk-bg}"
    textColor: "{colors.ink-2}"
    typography: "{typography.mono}"
    rounded: "{rounded.row}"
    padding: "6px 10px"
  code-row-after:
    backgroundColor: "{colors.change-bg}"
    textColor: "{colors.ink}"
    typography: "{typography.mono}"
    rounded: "{rounded.row}"
    padding: "6px 10px"
  edge-label:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
---

# Design System: Genesis Viewer

## Overview

**Creative North Star: "The Quiet Builder Canvas"**

The viewer is an agent-builder canvas: white cards on a light grey field, joined by thin curves, read left to right. The look follows OpenAI Agent Builder's canvas, which the user pinned. Nothing on the field is decorative. A card shows what kind of step it is, its name, its branches as rows, and the change it carries when it has one. All chrome floats over the canvas: a headline block top left and a panel on the right. None of it is docked into columns.

The whole product is one map. Each module is a large frame holding its flows, each flow drawn in full under its name; on the left, the ways in (requests, background tasks, schedules) send lines along the gutters into the flows they start. Every change on the map is written in amber on its card, and dashed amber lines run from a change to the same change on another flow ("同一处改动") and to flows it may reach ("可能影响"). The headline above says where the change lands and what needs attention. Clicking a module brings it into focus; "走一遍" on a flow walks it from its trigger to its end; clicking a change rings it and opens its details. Nothing switches pages and nothing is stepped through one by one.

Three signal colours do all the talking. Amber marks change and what it reaches, red marks risk and loss, and blue marks selection. Everything else is ink on white or grey. The density suits reading at a desk: 18px headline, 14px cards, 12 to 12.5px secondary text, and generous space between ranks.

This world replaces the earlier ticket-wallet world. Stamps, perforations, condensed display type and navy carrier colour belong to that world and are gone. The pan-and-zoom canvas it refused is now the primary surface.

**Key Characteristics:**
- Light grey canvas (#f4f4f5) with white cards, 18px corners, a hairline border and a soft two-layer shadow.
- Pastel kind tiles (trigger green, action violet, decision orange, external yellow, result grey) are the only colour at rest.
- Amber is change and what it reaches; red is risk and removal; blue is selection.
- Floating chrome only: headline block top left, right panel (bottom sheet on phones). Nothing sits in the corners for its own sake.
- One light rendition and system sans throughout. Mono is used only for code, paths, revisions and flows still named after their code.
- Motion explains the change and nothing else: one ripple of at most 0.6s, a camera glide between changes of one flow, no entrance.

## Colors

The palette is neutral grey and white, with five pastel kind tiles and three reserved signal hues.

### Primary
- **Change Amber** (`change`): the current card's solid border and its 3px halo at 12%, the 45% border the next steps take when the ripple reaches them, the ring of the ripple, the travelling dot, and the 45% ring of the "可能影响" tag. Its tint (`change-bg`) fills the change field of the current change only, the "after" code row, and the "也影响" chip of the flow now on the canvas. Its deep ink (`change-ink`) is the text set on that tint and the tag's text.

### Secondary
- **Risk Red** (`risk`, `risk-bg`): risk tags, risk boxes in the panel, exception branch rows (text only), the "已删除" tag on removed steps, the untested status icon, and the struck "before" code row. Exception edges use a pale red (`edge-exception`) that deepens to `edge-exception-strong` wherever edges turn dark: on the way in and once the ripple has drawn them.
- **Selection Blue** (`select`): an unchanged card opened in the panel takes a blue border with a 3px ring at 14%; focus outlines; the shadcn `ring`. The current change is never blue.

### Tertiary
- **Covered Green** (`ok`, `ok-bg`): the tested status icon and the "新增" tag. It means reassurance and is never decoration.
- **Kind Tiles** (`tile-*-bg` / `tile-*-ink`): a pastel square with a coloured Lucide glyph for each step kind. Trigger is green, action violet, decision orange, external yellow and result grey. On quiet cards the tiles turn grayscale.

### Neutral
- **Canvas Grey** (`canvas`): the field behind everything. It also fills the solid strip behind the desktop panel and, at 85%, the skeleton note.
- **Card White** (`card`): cards, pills, the headline block, the panel, tags and edge labels.
- **Ink** (`ink`): names, the headline sentence and primary text. It is also shadcn `primary` and the strike on a removed flow's cards.
- **Ink 2** (`ink-2`): body text in the panel, branch rows, the change field of other changes, test status labels.
- **Ink 3** (`ink-3`): counts, field labels, paths and the attribution.
- **Hairline** (`line`): card borders, chrome rings, the divider above the counts and panel dividers.
- **Field Grey** (`field`, `muted-tint`): branch rows, the change field of changes not on show, "也影响" chips, code excerpts and hover fills.
- **Edge Grey / Edge Strong** (`edge`, `edge-strong`): resting curves, and the way in plus the drawn ripple.

### Named Rules
**The Three Signals Rule.** Amber means change and what it reaches, red means risk or what a change removed, and blue means selection. No other element may use these hues, and none of them may appear as decoration.

**The Change-Is-Amber Rule.** Every change on the map carries an amber field and a 45% amber border, and only changes do. The change the reader picks takes the solid border and halo, and the steps it leads to answer in amber; lines to what a change also touches are dashed amber.

## Typography

**Body Font:** the system sans stack (-apple-system / SF Pro Text / Segoe UI / PingFang SC / Microsoft YaHei / Noto Sans CJK SC)
**Label/Mono Font:** ui-monospace / SF Mono / Menlo / Consolas

**Character:** One native sans at modest weights (400 and 500, no bold). It reads the same in Chinese and English. Mono is reserved for code a reader might want to search for.

### Hierarchy
- **Headline** (500, 18px, 26px; 16px / 23px on phones): the sentence in the headline block, clamped to two lines with the test status after it. This is the largest type in the product.
- **Subhead** (500, 17px, 26px): the change summary at the top of each change in the panel. The off-map line in the middle of the canvas uses 15px / 23px at 400.
- **Title** (500, 14px, 20px): card names (clamped to two lines) and the panel header. Compact pills use 13.5px.
- **Body** (400, 14px, 22px): the "对用户的影响" paragraph in the panel.
- **Body Small** (400, 12.5px, 18px): branch rows, the change field on cards, the counts and the flows line of the headline. Panel notes use 13px / 19px.
- **Label** (500, 12px, 16px, ink-3, sentence case): field labels in the panel ("对用户的影响", "放在这一步的原因").
- **Tag** (500, 11px, 16px): 新增 / 已删除 / 新风险 / 风险 tags and the "可能影响" tag. Edge labels and the skeleton note use 11.5px at 400.
- **Mono** (400, 12px, 18px): before/after code rows and excerpts. Paths and test ids use 11.5px / 17px.

### Named Rules
**The No-Bold Rule.** Hierarchy comes from size and ink tone, with weights capped at 500. Text is never uppercase or letterspaced.

**The Mono-Means-Code Rule.** Monospace is only for code, file paths, test ids and revisions. Flows and steps still named after their code use it because their names are raw identifiers.

## Layout

The canvas is a React Flow pane laid out by dagre, left to right (rank gap 84px, node gap 34px, margins 24px). Full cards are 252px wide. Compact pills are 44px tall and 148 to 236px wide, sized to their text. Steps a change removed wait as ghost cards in a row 72px below the flow. Panning is by scroll, zoom ranges from 0.25 to 1.6, and nodes cannot be dragged or connected.

The atlas places module frames in rows wrapped to roughly the shape of a screen, the modules this change touches first, 120px apart; removed flows and changes on no flow share a last dashed frame, "不在当前地图上". Inside a frame (32px padding, an 88px header) flows stack 56px apart, each under a 48px name row. The ways in sit in a column on the left; their lines keep to the gutter beside them, the gaps between rows and the lane just left of each module, so they never cross a flow. Module and flow names keep their size on screen as the reader zooms out (15px and 13px, growing up to 56px and 30px in map units). The first view frames the whole atlas.

All chrome floats 12px from the viewport edges. With a module in focus, breadcrumbs ("总览 / 模块") sit top left above the headline block; with no report to walk they always show, carrying the mark and the map's size. The headline block sits top left, up to 600px wide (with the panel open, never under it: at most the width left of the panel, at least 340px). The detail panel is 384px wide, inset 12px top, right and bottom. A solid canvas-grey strip (408px) sits behind it so cards never show through the gap.

The camera frames the free area: the canvas minus the measured headline stack (plus 16px), the open panel (384px plus 40px) and a 56px bottom margin. It frames the change and the steps it leads to first, then adds the farther results and the way in while everything still fits between zoom 0.62 and 1, and never drops the steps ahead for the way in. When even the change and its next steps do not fit at 0.62, the change sits a third in at 0.62 so what it leads to gets the rest. Opening the panel pans only when the panel would cover them; a resized window keeps the change framed unless the reader has moved away from it.

Below 768px the headline spans the width at 16px, the panel becomes a bottom sheet (inset 8px, 52dvh tall), and with the sheet open the counts give way to the sentence alone.

Panel rhythm: 16px gutters, 24px between sections, 12px within a change, 6px between before/after rows. Card rhythm: 12px padding, 10px from header to rows, 6px between rows.

## Elevation & Depth

The system is flat with a soft lift. White surfaces sit on grey and carry a hairline plus a faint two-layer shadow. Floating chrome takes a deeper version of the same shadow. Depth tracks state: quiet cards lose their shadow entirely, and hover deepens it.

### Shadow Vocabulary
- **Node** (`box-shadow: 0 1px 2px rgb(17 17 19 / 0.04), 0 4px 14px rgb(17 17 19 / 0.05)`): cards, pills, tags and edge labels at rest.
- **Node Hover** (`box-shadow: 0 2px 4px rgb(17 17 19 / 0.05), 0 10px 26px rgb(17 17 19 / 0.08)`): card hover. It also sits under the current card's halo and the selection ring.
- **Float** (`box-shadow: 0 1px 2px rgb(17 17 19 / 0.05), 0 12px 32px rgb(17 17 19 / 0.1)`): the headline block, the breadcrumbs and the panel.
- **Current** (`box-shadow: 0 0 0 3px rgb(226 134 11 / 0.12)` plus node hover): the current change's card, with a solid amber border.
- **Selection** (`box-shadow: 0 0 0 3px rgb(47 111 235 / 0.14)` plus node hover): an unchanged card opened in the panel.
- **Ring** (`0 0 0 0 → 0 0 0 12px`, amber 38% to 0, 240ms): the first beat of the ripple, once per change.

### Named Rules
**The Quiet-Around-The-Change Rule.** When a change is on show, every card but the change, the steps it leads to (once the ripple reaches them) and a card opened in the panel drops its shadow, turns 75% white, fades its content to 60% and takes a grayscale tile. Edges outside the ripple, the way in and the change's own loops fall to 45%, their labels to 60%. A change off the map quiets the whole flow behind it. Quiet cards stay legible. They are never hidden.

## Shapes

Corners are generous and nest inward: panel 20px, card, module card and headline block 18px, pill and menu 14px, change field 12px, branch and code rows 10px, tiles 9px (8px small), tags 5px. Chips, tags, buttons, breadcrumbs and edge labels are full pills. Borders are 1px hairlines. Ghost cards switch to a dashed border, and uncertain branch rows take a dashed 40% ink-3 outline. Edges are bezier curves (curvature 0.32), 1.25px at rest and 1.6px when dark, dashed 4/4 when uncertain. A loop back to an earlier step leaves its handle to the right, runs back in a lane 28px above or below the cards between its ends (whichever is nearer) and comes in from the left, with 14px corners; it stays dashed. Handles are 9px white circles with a 1.25px grey rim.

## Components

### Headline Block
What the reader looks at first: a white 18px float, 12px 16px 10px padding.
- **Sentence:** where this change lands, in the headline style, two lines at most: "这次改动落在「退款」模块的 1 条流程上，另有 2 处不在当前地图上。" With no change it says so, or that no changed file could be analyzed.
- **Counts:** after a hairline, "共 N 处改动 · X 处没测试 · Y 个新风险 · Z 个文件没分析 · 改了 T 个测试 · 部分完成" in 12.5px ink-3, zeros left out. The files and "部分完成" carry a dotted underline and open a tooltip on hover, focus or tap.

### Step Card
Quiet and white, a card that holds the change it carries.
- **Shape:** 18px radius, 1px hairline, node shadow, 252px wide, 12px padding.
- **Header:** a 32px kind tile, then the name (title, clamped to two lines). Under it, only when there is one, a row of tags: 新增, 已删除, 新风险 (an introduced risk on the step), 风险 (with no report to walk), and 待确认 / 未知 in plain ink-3. Kind words live in the panel only.
- **Branch rows:** field-grey rows of 12.5px text, one per branch, each with its own source handle on the right. Exception rows use red text. Uncertain rows are outlined with a dash.
- **Change field:** the change summary (two lines) over the test status and "另有 N 处改动". It is amber tint with change-ink text on the current change and field grey with ink-2 text on every other. A card holding several changes shows the current one, else the most urgent.
- **States:** the current change takes a solid amber border with its halo; the steps it leads to take a 45% amber border as the ripple reaches them; farther results it may reach stay quiet and carry the "可能影响" tag. An unchanged card opened in the panel takes the blue border and ring. Ghost cards are dashed, titled with their change's summary (or the struck line of removed code in mono), with a 70% grayscale tile. A removed flow's cards are struck through in ink at 1.5px, never amber and never quiet. Quiet: see Elevation.
- **No entrance:** the first paint is the framed canvas, already in the ripple's starting state.

### Step Pill
The compact form for a start or a plain end with no change, rows, loops or tags: a 44px row with a 28px tile and a 13.5px name, 14px radius.

### Chips and Tags
- **Tags:** 11px / 500 on a tint with a 5px radius. "新增" is green; "已删除", "新风险" and "风险" are red.
- **"可能影响" tag:** a white full pill, 11px / 500 change-ink, a 45% amber ring and node shadow, hung on the card's top edge 12px from the right, outside the layout box.
- **Flow chips:** field-grey full pills in the headline's flows line; the flow on the canvas is amber tint.
- **Edge label:** a white full pill with a hairline ring and node shadow, 11.5px ink-2 text (red for exceptions), at the curve midpoint, or on the lane of a loop.

### Buttons
- **"走一遍":** a white full pill on a flow's name row, 11.5px / 500 ink-2 with a play glyph, node shadow and hairline ring.
- **Icon buttons:** the panel's close is a 28px ghost button.
- **Focus:** 2px blue outline at a 2px offset (3px on cards).
- The shadcn variants are restyled through tokens: primary is ink, destructive is risk at 10%.

### Module Frame
A module of the product around its flows.
- **Shape:** 32px radius, 1.5px border, white at 45% over the canvas. The header (88px) holds the module name in ink at 500 and "N 处改动" in change-ink or "N 条流程" in ink-3, both keeping their size on screen.
- **States:** a frame holding changes takes a 45% amber border; the frame for what is not on the current map is dashed. Clicking a frame brings it into focus (520ms glide, ease-out).
- **Flow name row:** the flow's name (13px on screen, mono for flows still named after their code, struck through in ink at 1.5px for removed flows), "N 处改动" in change-ink, a "代码结构" tag for skeleton flows, and the "走一遍" pill.

### Ways In
White 56px full pills in a column on the left: a 36px grey disc with the glyph of the entry kind (request, task, schedule, command, API, agent tool), the kind in 13.5px ink and "N 条流程" in ink-3. Each line leaves its right side and turns at right angles with 12px corners, staying in the gutters, into the trigger of every flow it starts.

### Change Lines
Dashed amber curves (5/5, 70%) from a change's card to the same change on another flow, labelled "同一处改动", and to the trigger of each flow that may reach it, labelled "可能影响"; labels are white pills with change-ink text and a 45% amber ring. Links between flows from the map, when there are any, are the same curves in strong grey with the link's name.

### Changes Off the Map
A dashed amber card (252×112) per change on no flow, in the last frame: its summary in change-ink and its test status. Clicking it opens the panel.

### Breadcrumbs
A white full pill, 32px, 12.5px ink-3: "总览" is a link back to the whole atlas and the module in focus follows in ink at 500. With no report to walk it reads "总览 · N 个模块 · M 条流程" after the mark, plus "部分完成" from 640px.

### Detail Panel
A white 20px float, closed by default. Clicking a card opens it on that step (a changed card also rings); clicking a change off the map or a removed flow's name opens it on that; clicking the canvas or Esc closes it, and focus returns to what opened it. It slides in over 260ms; a new subject replaces the content in place, scrolled to the top with the code folded. Esc steps back one thing at a time: the walk, the panel, the picked change, the focused module.
- **Header:** a small kind tile, the step name (or the removed step's summary, or "不在流程上的改动"), the step kind (or 已删除) in ink-3, and a ghost close button.
- **Each change:** the summary as a subhead (left out when the header already says it), "对用户的影响", then after a hairline the test status with its full wording and the CLI's note in the page language, then risk boxes in red tint. "查看代码" folds away the before/after rows, the evidence (a mono path over a field-grey excerpt, never repeating the code just shown), why the change sits on this step, and the test ids in mono. An unchanged step shows its reason and code at once.
- **Before / after:** before is a risk-tinted row with struck ink-2 text; after is an amber-tinted row with ink text; each has a 36px label column.
- **Refs:** "对比 base → head" in 11.5px ink-3 with mono refs closes the panel.

### Walk Through (signature)
"走一遍" walks a flow the way worth watching: from its trigger, at each decision the branch passing the most changes, then the one off the error path, then the longer one. The camera moves to the trigger (560ms) at 0.85 zoom and rides along; each edge draws itself in 300ms with a dot on its tip, each step it reaches lifts its border (amber on a change, strong grey otherwise) and rings once; the walk pauses 140ms at a step and 560ms more at a change. Everything off the walk steps back. Any click, scroll or key ends it; with reduced motion the whole walk shows at once, framed.

### Ripple (signature)
One ripple per change, at most 0.6s from its start, counted from when it is armed:
- 0–240ms, a ring on the change.
- 120–420ms, every edge leaving it draws itself outward (300ms, cubic-bezier(0.45, 0, 0.55, 1)), a 3.5px amber dot riding the tip of edges no longer than twice the shortest; dashed edges fade in over the same stretch.
- At 420ms the steps the change leads to take their amber border.
- 420–600ms, the "可能影响" tags fade up 2px.

It plays when the reader clicks a change: at once when the card is already in view and readable, otherwise after the camera glides to it (520ms, ease-out cubic), armed at 70% of the glide. Edges the ripple will draw stay hidden until then. Dimming and lighting take 160ms. A drag, scroll, click or key settles it at its end state. Only a newly picked change plays it again. A removed flow shows its end state at once; a removed step, a result or a step with no way out plays only the ring. Reduced motion removes all of it, including the panel slide and the headline fade.

## Do's and Don'ts

### Do:
- **Do** write the change on the card it touches, as a field inside the card.
- **Do** keep amber for change: the changed cards, the one picked, the lines to what it touches.
- **Do** keep red to risk and removal, and blue to selection.
- **Do** float every piece of chrome over the canvas with the float shadow and a hairline ring, 12px from the edge.
- **Do** quiet cards around the change (no shadow, grayscale tile, faded content) instead of hiding them.
- **Do** give every step kind its pastel tile and Lucide glyph, at 32px on cards and 28px on pills and in the panel.
- **Do** stack before above after in the panel so both can be read at a glance.
- **Do** let only what changes move: the sentence fades, the flow prefix stays.

### Don't:
- **Don't** split the product into pages or step through changes one by one; it is one map, and focus is a camera move.
- **Don't** dock side columns of change records beside the canvas. The panel shows one step at a time.
- **Don't** add a navigator, a second counter or a change list; the headline walks the changes.
- **Don't** add an entrance animation or a canvas fade-in.
- **Don't** use stamps, perforations, condensed display faces, uppercase labels or letterspacing.
- **Don't** add a dark rendition or tinted card backgrounds. Cards are white and the canvas is #f4f4f5.
- **Don't** use bold type. Hierarchy stops at 500.
- **Don't** imply a test ran. Statuses say what reading the code found and never claim more.
- **Don't** add a footer, a byline or a provenance line; the canvas runs to the bottom edge.

---
name: Genesis Viewer
description: A product's modules and flows on one quiet agent-builder canvas, with each change written on the card it touches.
colors:
  canvas: "#f4f4f5"
  card: "#ffffff"
  ink: "#111113"
  ink-2: "#4d5058"
  ink-3: "#62656e"
  line: "#d9dadd"
  field: "#f4f4f5"
  muted-tint: "#f1f1f3"
  handle-rim: "#c9cace"
  edge: "#7d818c"
  edge-strong: "#3a3b40"
  edge-exception: "#c57368"
  edge-exception-strong: "#b5524a"
  select: "#2f6feb"
  change: "#e2860b"
  change-bg: "#fff6e8"
  change-ink: "#8a4a00"
  risk: "#d92d20"
  risk-bg: "#fdf0ef"
  risk-ink: "#b42318"
  warn: "#c26d00"
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
    fontSize: "18px"
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
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "18px"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: "16px"
  tag:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: "12px"
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
    borderColor: "the card's own tone"
  step-card-next:
    borderColor: "rgb(58 59 64 / 0.45)"
  step-card-quiet:
    backgroundColor: "{colors.card}"
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
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink-2}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "0 4px"
  tag-risk:
    backgroundColor: "{colors.risk-bg}"
    textColor: "{colors.risk-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "0 4px"
  far-tag:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-2}"
    typography: "{typography.tag}"
    rounded: "{rounded.full}"
    padding: "1px 8px"
  headline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.headline}"
    rounded: "{rounded.card}"
    padding: "0 6px 0 12px"
    height: "36px"
    width: "fit-content"
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
  map-mark:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-2}"
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
    rounded: "calc(var(--radius) * 1.8)"
    width: "420px"
    height: "min(720px, calc(100dvh - 112px))"
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
    backgroundColor: "{colors.ok-bg}"
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

The viewer is an agent-builder canvas: white cards on a light grey field, joined by thin lines that turn at right angles, read left to right. The look follows OpenAI Agent Builder's canvas, which the user pinned. Nothing on the field is decorative. A card shows what kind of step it is, its name, and the change it carries when it has one; a branch is named on its line. All chrome floats over the canvas: a headline block top left and a panel on the right. None of it is docked into columns.

The whole product is one map, and the first look at it reads: it is never framed below 0.8. Each module is a neutral frame holding its flows. Every synthesized live flow is a diagram, whether changed or unchanged. A touched flow may fold intermediate work while preserving its changed steps, way in, trigger, affected decisions, outcomes, exception targets and retry endpoints. Dotted lines and pills count omitted steps ("中间 6 步", "还有 4 步") and open the whole flow. Unchanged live flows are drawn whole. Only removed or undescribed flows use compact rows. Flow names carry no entry-kind text or step-count metadata; the trigger and graph explain the flow. Long flows wrap onto bands rather than shrink below a readable scale.

A step the change leaves alone is a small pill; a step it touches is a card with a short clause, a native risk or validation badge and its test evidence. Red means a reported risk; amber means missing behavior checks, not lower severity. A change keeps one number across the card, list, panel and address ("#change=3"). Its corner glyph says added, removed or altered. Module frames remain neutral, so these signals belong to the changes themselves.

The compact "改动清单" entry steps through changes and opens their temporary list. It has no category filters, review marking or progress row. Picking a change rings its card, opens the inspector on the right and draws dashed links to the same change on other flows. Clicking a module opens its complete diagrams in place; the same frame button closes it ("收起"), as do Esc and the fit button. With no report to walk, "走一遍" follows a live diagram from trigger to end with a small status bar. Nothing switches pages: changes stay on the map, the list folds away, and the inspector separates the overview from structured input and output.

Five signal colours do all the talking, and each means one thing. Red is a reported risk, amber is a change no test reaches, grey is a change nobody can give a verdict on, green is a change a test checks, and blue is selection. Everything else is ink on white or grey. The density suits reading at a desk: 14px for canvas names and body, 13px for secondary text, 12px for labels, tags and code. Module names are 16px and keep their size as the reader zooms; the desktop inspector uses a 16px title and a 17px change summary.

The page has a light and a dark rendition of the same tokens. It opens light, whatever the reader's system shows; a round button above the zoom controls switches to the other (a moon in light, a sun in dark). A switch to dark is kept in the browser until the reader switches back.

This world replaces the earlier ticket-wallet world. Stamps, perforations, condensed display type and navy carrier colour belong to that world and are gone. The pan-and-zoom canvas it refused is now the primary surface.

**Key Characteristics:**
- Light grey canvas (#f4f4f5) with white cards, 18px corners, a hairline border and a soft two-layer shadow.
- Pastel kind tiles (trigger green, action violet, decision orange, external yellow, result grey) are the only colour at rest.
- A changed card's colour is what it asks of the reader: red a new risk, amber no test, grey no verdict, green tested. Blue is selection. What the change did to the step is a glyph, not a colour.
- Floating chrome only: the headline block top left, the details panel on the right, the theme button and zoom controls at the bottom right. The map itself carries the changes; their list folds out of the headline and never stays docked.
- Light and dark from the same tokens, light until the reader switches, and system sans throughout. Mono is used only for code, paths, revisions and flows still named after their code.
- Motion explains the change and nothing else: one ripple of at most 0.6s, a camera glide between changes of one flow, no entrance.

## Colors

The palette is neutral grey and white, with five pastel kind tiles and three reserved signal hues.

### The four tones
A changed card's border, number, far-view block and review badge carry its tone. Module frames, inspector surfaces and code blocks remain neutral; no nested tinted summary surface is added.
- **Risk Red** (`risk`, `risk-bg`, `risk-ink`): a reported risk, its review and category badges, and exception branch rows (text only). Inspector code remains neutral. Exception edges use a pale red (`edge-exception`) that deepens to `edge-exception-strong` wherever edges turn dark.
- **Untested Amber** (`change`, `change-bg`, `change-ink`; `warn` for a small glyph on white): a change no test reaches, and the untested status icon.
- **Unsure Grey** (`ink-3`, `field`, `ink-2`): a change nobody can give a verdict on, and a flow that is gone.
- **Tested Green** (`ok`, `ok-bg`): a change a test checks and the tested status icon. It describes source evidence and is never decoration; inspector code remains neutral.

A change that is both risky and untested is red, with its missing behavior checks stated in the test evidence: the tone is the most pressing thing, the words say the rest. A module frame keeps its neutral hairline regardless of the changes inside it.

### Selection
- **Selection Blue** (`select`): an unchanged card opened in the panel takes a blue border with a 4px ring at 18%; focus outlines; the shadcn `ring`. The current change is never blue: it rings in its own tone.
- **Kind Tiles** (`tile-*-bg` / `tile-*-ink`): a pastel square with a coloured Lucide glyph for each step kind. Trigger is green, action violet, decision orange, external yellow and result grey. On quiet cards the tiles turn grayscale.

### Neutral
- **Canvas Grey** (`canvas`): the field behind everything. At 85% it backs the skeleton note.
- **Card White** (`card`): cards, pills, the headline block, the panel, tags and edge labels. In the dark rendition it is one step above the canvas (#1c1c20 on #101012).
- **Ink** (`ink`): names, the headline sentence and primary text. It is also shadcn `primary` and the strike on a removed flow's cards.
- **Ink 2** (`ink-2`): body text in the panel, branch rows, the change field of other changes, test status labels.
- **Ink 3** (`ink-3`): counts, field labels, paths and the attribution.
- **Hairline** (`line`): card borders, chrome rings, the divider above the counts and panel dividers.
- **Field Grey** (`field`, `muted-tint`): branch rows, the change field of changes not on show, "也影响" chips, code excerpts and hover fills.
- **Edge Grey / Edge Strong** (`edge`, `edge-strong`): resting curves, and the way in plus the drawn ripple. Strong grey is also what a change reaches: the border of the steps it leads to, the "可能影响" tag, the travelling dot and the dashed lines to the same change on other flows.

### Named Rules
**The One-Meaning Rule.** Red is a new risk, amber is no test, grey is no verdict, green is tested, blue is selection. No other element may use these hues, none may appear as decoration, and none may stand for what a change did to a step: that is the glyph's job.

**The Tone-On-The-Card Rule.** Every change on the map carries a review badge and a border in its tone, and only changes do. The change the reader picks takes the solid border and a halo of the same tone; what it leads to answers in strong grey. Keep the card body and module frame neutral.

**The Same-Words Rule.** Use the same source-evidence labels on the card and in details. Distinguish behavior assertions, related tests, missing checks and uncertainty; then explain what the assessment rests on. These labels never claim a test ran or guarantee safety.

**The Both-Renditions Rule.** No colour is written into a component. Every hue is a token with a light and a dark value, so a new element works after dark without a second look.

## Typography

**Body Font:** the system sans stack (-apple-system / SF Pro Text / Segoe UI / PingFang SC / Microsoft YaHei / Noto Sans CJK SC)
**Label/Mono Font:** ui-monospace / SF Mono / Menlo / Consolas

**Character:** One native sans at modest weights (400 and 500, no bold). It reads the same in Chinese and English. Mono is reserved for code a reader might want to search for.

### Hierarchy
The canvas uses one compact scale; the desktop inspector adds a 16px title and 17px change summary for its narrower reading measure.
- **Headline / Subhead** (500, 18px, 26px): the retained headline scale. The compact change-list entry does not show a large verdict; the desktop inspector uses a 17px / 28px change summary and a 16px / 24px title.
- **Title / Body** (500 or 400, 14px, 20 to 24px): card names (clamped to two lines), pills, rows of the list, and the inspector's impact and finding text.
- **Body Small** (400, 13px, 18 to 19px): the second sentence of the headline, the change field on cards, the kinds and the stepper, panel notes.
- **Label / Tag / Mono** (12px, 16 to 18px): field labels in the panel (500, ink-3, sentence case), tags (500), edge labels, the numbers on cards, code rows, paths and test ids.
- **Module name** (500, 16px on screen, growing with the zoom) and **flow name** (500, 14px on screen) keep their size as the reader zooms out.

### Named Rules
**The No-Bold Rule.** Hierarchy comes from size and ink tone, with weights capped at 500. Text is never uppercase or letterspaced.

**The Mono-Means-Code Rule.** Monospace is only for code, file paths, test ids and revisions. Flows and steps still named after their code use it because their names are raw identifiers.

## Layout

The canvas is a React Flow pane. A drawn flow is a grid of columns: dagre decides which column a step is in, the order down it, and the height a long line keeps to as it passes other columns; a column is as wide as its widest step, steps 16px apart down it; a gap between columns is at least 40px and as wide as the label and the turning lines in it need. Cards are 216px wide; pills are 44px tall and 120 to 236px wide, sized to their name. When a flow is wider than the frame allows it wraps onto bands 48px apart, the bands made about equally long; a line that goes on to the next band leaves by the right, runs back in the gap between the bands and comes in from the left. A step the change removed sets down in a free corner at the end of the last band, else in a row 28px below the flow. Panning is by scroll, zoom ranges from 0.05 to 1.6, and nodes cannot be dragged or connected.

The atlas is one grid, as wide as the drawn flows need and no wider than the reader's screen shows at 0.8 (the canvas width less 84px, over 0.8). A module with a flow drawn out runs the full width, whether changed or unchanged; "流程之外" holds changes on no flow and removed-flow rows. Modules containing only compact rows share equal cells, as many to a row as fit at 308px or more, each row's cells equally wide and as tall as its tallest, a short last row sharing the width evenly. Frames sit 32px apart and all end on the same left and right edge. Inside a frame (24px padding, a 56px header) drawn flows stack 36px apart, each under a 44px name row, and any undescribed-flow rows follow, 8px apart. A drawn flow never runs wider than its frame's inside: it wraps onto bands instead. Module and flow names keep their size on screen as the reader zooms out (16px and 14px, growing up to 34px and 30px in map units). The first view frames the whole atlas between zoom 0.8 and 1.6; when it is larger than that, it starts from the top left, where the touched modules are.

The headline and detail panel float 16px from the desktop viewport edges (12px on narrow screens). The overview starts 24px below the headline and shares its left edge; it never floats in the vertical center of a tall window. The compact change-list entry sits top left and fits within the area left of an open panel; opening its temporary popover does not reframe the canvas. With no report to walk a pill with the mark and the map's size stands in its place. Zoom controls sit 12px from the right and 32px from the bottom, and stay there, with the round theme button 8px above them. The desktop inspector uses the width and viewport-clamped height in `components.detail-panel`, inset 16px from the top and right. Its header, tabs and footer stay in place while its content scrolls.

The camera frames the free area below the measured headline with 24px separation, left of the open inspector (its width plus 40px), and above a 96px bottom margin. Desktop automatic framing grows small maps up to 1.6 zoom. Opening details first fits the complete selected module if it stays readable at 0.8 or above; otherwise it fits the selected step and its immediate neighbors, falling back to the step alone. Detail framing includes 12 map units of padding and never forces the content beyond the free area. The desktop map is clipped outside that area, with 12px of shadow clearance, so manual panning cannot draw content underneath the headline or details.

Below 768px the panel retains its existing bottom-sheet layout (inset 8px, 52dvh tall). These refinements target the desktop layout.

Desktop inspector rhythm: 20px horizontal insets shared by the header, tabs, body and footer; 24px between overview groups and 20px between blocks within a change or the input/output tab. Card rhythm: 12px padding, 10px from header to rows, 6px between rows.

## Elevation & Depth

The system is flat with a soft lift. White surfaces sit on grey and carry a hairline plus a faint two-layer shadow. Floating chrome takes a deeper version of the same shadow. Depth tracks state: quiet cards lose their shadow entirely, and hover deepens it.

### Shadow Vocabulary
- **Node** (`box-shadow: 0 1px 2px rgb(17 17 19 / 0.04), 0 4px 14px rgb(17 17 19 / 0.05)`): cards, pills, tags and edge labels at rest.
- **Node Hover** (`box-shadow: 0 2px 4px rgb(17 17 19 / 0.05), 0 10px 26px rgb(17 17 19 / 0.08)`): card hover. It also sits under the current card's halo and the selection ring.
- **Float** (`box-shadow: 0 1px 2px rgb(17 17 19 / 0.05), 0 12px 32px rgb(17 17 19 / 0.1)`): the headline block, the map mark and the panel.
- **Current** (`.ring-tone`: `0 0 0 4px` of the card's tone at 20%, plus node hover): the current change's card, with a solid border of its tone.
- **Selection** (`.ring-select`: `0 0 0 4px` of blue at 18%, plus node hover): an unchanged card opened in the panel.
- **Ring** (`0 0 0 0 → 0 0 0 12px`, the card's tone 38% to 0, 240ms): the first beat of the ripple, once per change.

### Named Rules
**The Quiet-Around-The-Change Rule.** Keep other changed cards and the incoming path readable. Unrelated cards lose their shadow and take a grayscale tile, while their white surface and text retain full contrast. Edges outside the ripple, the way in and the change's own loops fall to 70%; branch labels remain fully legible at weight 500. Modules outside the focused module may still recede. Quiet cards are never hidden.

## Shapes

Corners are generous and nest inward: the desktop inspector uses the native shadcn card radius specified in `components.detail-panel`; card, module card and headline block 18px, pill and menu 14px, change field 12px, branch and code rows 10px, tiles 9px (8px small), tags 5px. Chips, tags, buttons, the map mark and edge labels are full pills. Borders are 1px hairlines. Ghost cards switch to a dashed border, and uncertain branch rows take a dashed 40% ink-3 outline. Edges are bezier curves (curvature 0.32), 1.25px at rest and 1.6px when dark, dashed 4/4 when uncertain. A loop back to an earlier step leaves its handle to the right, runs back in a lane 28px above or below the cards between its ends (whichever is nearer) and comes in from the left, with 14px corners; it stays dashed. Handles are 9px white circles with a 1.25px grey rim.

## Components

### Drawn Flow (signature)
Every synthesized live flow uses the same diagram grammar. Unchanged flows are drawn whole; a touched flow may fold intermediate work until its module opens.
- **What is drawn:** every step the change touches (a card, below), its way in and trigger, plus affected decision nodes, outcomes, exception targets and retry endpoints. Retain source-authored branch labels; never invent conditions or edges missing from the input.
- **Left out:** the steps between two drawn ones are one dotted line (1.5/5, round caps) with a pill that counts them, after the branch they follow when there is one ("拆解完成 · 中间 4 步"). A line is left out where what is drawn already leads the same way. Steps left out with nothing drawn further on (the rest of the flow after a change, a branch the change does not touch) are a dotted 32px pill after the step they follow, "还有 4 步", on a dotted line named after the branch when there is one; clicking it opens the module on that flow. A gap or a tail of one step is drawn as that step.
- **Unchanged steps** that are drawn are pills (below), their branches named on their lines.
- **Changed steps** are cards (below), each marked for what the change did to it.
- **Picking a card** rings it in its own tone and darkens the way in and out. After details and the headline have laid out, fit the complete module or the selected step's local context into the free canvas, aligned below the headline. Resizing keeps that context in view; closing details returns to the larger top-aligned overview or module. Manual panning remains free between these explicit transitions.
- **"走一遍"** walks a flow drawn whole from its trigger to its end where it stands. It is offered only with no report to walk: with one, the headline steps through the changes.

### Flow Row
Only a removed or undescribed flow uses a row: a white 44px card as wide as its frame, a 28px grey entry glyph, and the flow's name in 14px ink (mono for flows still named after their code). The right shows only its state: "代码结构", "未归纳" or "已删除". A removed flow has a dashed border and struck name. Do not add entry-kind text, step counts or passing-change counts. Clicking a live row opens its module; a removed flow opens its panel and takes the grey ring.

A flow the plan has named and nobody has described yet reads as what the product does, not as code: its name is set in ink like any other, the right says "未归纳" alone (the tile already shows what starts it, and the room goes to the name), and when the plan gave it a sentence the row is 62px tall with that sentence under the name in 12px ink-3, one line, cut with an ellipsis and whole in the tooltip.

The business processes of a module come first, followed by its lookups and upkeep (`tier: supporting`). Synthesized supporting flows remain diagrams. Only supporting flows already represented as undescribed rows may fold into one 34px line, "另有 N 条查询和维护流程", with a chevron, dashed hairline and 13px ink-2; opening the module reveals those rows. A module with only supporting rows shows them directly.

### Far View
Below 0.5 zoom a changed card is covered by a solid block of its tone (red, amber, grey or green); changes off the map do the same; every other card fades to 40%. The first view never goes there; it is what a reader sees after zooming out by hand.

### Walk Bar
A white full pill centred under the map while a flow is walked: a play glyph, "走一遍" (or "走完了"), the flow's name at 500, and the step reached, in change-ink with the change's summary when that step carries one; a ghost "停止" (or "结束") button ends it. It never counts steps.

### Zoom Controls
A white full pill, three 28px ghost icon buttons stacked (zoom in, zoom out, whole map), float shadow and hairline ring. The last returns from a focused module to the whole map.

### Change List Entry
A compact 36px white pill at the top left contains “改动清单”, the change count, and
previous/next buttons. The current position appears once a change is selected. No large
verdict card, location sentence, always-visible category chips, or review-progress row.
The diagram already carries the changes and their locations.

The button opens a 360px popover containing one clickable row per change: its number,
concise description, and a native shadcn Badge for “风险”, “待验证” or existing behavior
checks. No heading, progress counter, filters, review buttons or shortcut footer. Picking a change closes the popover; Escape closes it and
returns focus to its trigger.
Warnings about unanalyzed files and incomplete analysis stay visible beside the pill.
When there are no product changes, a short neutral status replaces the entry.

### Step Card
A step the change touched (or one with a tag to show): quiet and white, holding the change it carries.
- **Shape:** 18px radius, node shadow, 216px wide, 12px padding; it sits in the middle of its place in the column, so lines meet it at its centre.
- **Header:** a 32px kind tile, then the name (title, clamped to two lines). Under it, only when there is one, a row of tags: 新增 and 已删除 in plain grey, 新风险 in red (an introduced risk on the step), 风险 (with no report to walk), and 待确认 / 未知 in plain ink-3.
- **What the change asks:** a border in the card's tone and an explicit native shadcn Badge for "风险" or "待验证". Red means a reported risk; amber means missing behavior checks, not lower severity. Additional findings add a count to the risk badge. Keep the card white and omit the nested tinted summary surface.
- **Which change it is:** a 20px disc at the top left corner with the change's number, filled with the tone's ink. The same disc stands in the list and in the panel. There is no reviewed state or tick.
- **What the change did:** an 18px white disc at the top right corner with a glyph in the tone's ink: a plus for a step it added, a minus for one it removed (whose border is dashed), a pencil for one it altered.
- **Summary:** one short clause over the test evidence and "另有 N 处改动". Use authored `short_summary` when supplied; otherwise show the existing summary with a two-line visual limit and its full text in details. A card holding several changes shows the current one, else the most urgent.
- **States:** the picked change takes the solid border of its tone with a 4px halo; the steps it leads to take a 45% strong-grey border as the ripple reaches them; farther results it may reach stay quiet and carry the "可能影响" tag. An unchanged card opened in the panel takes the blue border and ring. A removed flow's cards are struck through in ink at 1.5px and carry no tone. The change list has no category filter.
- **Pointer:** every card and pill is a hand under the pointer, since each opens something.
- **No entrance:** the first paint is the framed canvas, already in the ripple's starting state.

### Step Pill
Every step the change leaves alone, with no loop or tag to show: a 44px row with a 28px kind tile and a 14px name, 14px radius, as wide as its name.

### Chips and Tags
- **Review badges:** risk and validation labels on cards, in the change list and in the inspector use the same native shadcn Badge (radix-nova).
- **Tags:** 12px / 500 on a tint with a 5px radius. "新风险" and "风险" are red; "新增" and "已删除" are plain grey, since the glyph at the corner already says them.
- **"可能影响" tag:** a white full pill, 12px / 500 ink-2, a 40% strong-grey ring and node shadow, hung on the card's top edge 12px from the right, outside the layout box.
- **Flow chips:** field-grey full pills in the headline's flows line; the flow on the canvas is amber tint.
- **Edge label:** a white full pill with a hairline ring and node shadow, 12px ink-2 text (red for exceptions), at the curve midpoint, or on the lane of a loop.

### Buttons
- **"走一遍":** a white full pill on a flow's name row, 12px / 500 ink-2 with a play glyph, node shadow and hairline ring. Not shown while there are changes to step through.
- **Icon buttons:** the panel's close is a 28px ghost button.
- **Focus:** 2px blue outline at a 2px offset (3px on cards).
- The shadcn variants are restyled through tokens: primary is ink, destructive is risk at 10%.

### Module Frame
A module of the product around its flows.
- **Shape:** 24px radius, a neutral 1.5px hairline and white at 45% over the canvas. The header (56px) holds the module name in ink at 500 and "N 处改动" in ink-2 or "N 条流程" in ink-3, both keeping their size on screen.
- **States:** every frame keeps its neutral border, deepening to 50% ink-3 on hover; the frame for changes outside the flows is dashed. One white pill button (28px, 12px at 500) laid over the header's right opens the frame and closes it again, so a module's name never gives up room to it and the way back is where the way in was: closed it reads "展开全部步骤" with an expand glyph for a drawn module and "展开" on a cell (the glyph alone on a cell under 300px until it is pointed at); open it reads "收起" with a collapse glyph. While a module is open every other frame, its cards and lines drop to 35%.
- **Opening:** clicking a closed frame (or a row inside it) unfolds intermediate steps in its touched flows and reveals any folded undescribed rows, in place. Unchanged synthesized flows are already drawn. Cards that stay slide to their new places over 320ms ease-out, new ones fade in over 220ms, and the lines return when the cards have settled; the camera glides (520ms) to the changed cards and their flow names, never below 0.8, starting right under the headline whether or not they fit, so nothing blank stands over the open module. Reduced motion cuts.
- **Flow name row:** over a drawn flow: its name (13px on screen, mono for flows still named after their code, struck through in ink at 1.5px for removed flows), a "代码结构" tag for skeleton flows, and the "走一遍" pill when there is no report. Nothing else stands beside the name: not what starts the flow, not how much of it is on show.

### Lines
Every line reads against the canvas, turns at right angles and says which way it goes.
- **At rest:** #7d818c at 2px, corners rounded at 10px, ending in a small filled arrowhead of the same colour; error paths in #c57368, dashed. The port a line leaves is a 9px white dot; the port it lands on is not drawn, the arrowhead is.
- **Way:** out of the right of its step, a turn in the gap after that column, on at the height of its target. A line that passes other columns keeps the lane dagre reserved for it; lines turning in the same gap keep 8px apart, and only lines leaving the same step share a turn. A line that goes on to the next band of a wrapped flow leaves by the right, runs back between the bands and comes in from the left; there each line keeps a level of its own, the one that ends lowest running highest and turning furthest out, so they come down without crossing. A step back to an earlier one (a retry) runs dashed in a lane clear of the cards between its ends.
- **Labels:** a branch or a condition is a white pill (12px ink-2, red for an error path) on the line just after its first turn, so two branches of one decision are named where they part. On a line that wraps to the next band the pill sits on its run between the bands; two such lines keep 26px apart there, and the second pill sits further back along its line than the first, so the two never stand one over the other.
- **Lit:** the way in to the picked change, the lines leaving it and the lines of a walk go to #3a3b40 (error paths #b5524a) at 2.5px, arrowheads with them; a line that draws itself gets its arrowhead as it arrives.
- **No shared lanes:** no line runs from one frame to another at rest. The trigger shows what starts a flow; lines between frames appear only for the picked change (below).

### Change Lines
Drawn only while their change is picked. Dashed strong-grey curves (5/5, 80%) from a change's card to the same change on another flow, labelled "同一处改动 · 流程名"; labels are white pills with ink text and a 40% strong-grey ring. Both cards carry the same number. Links between flows from the map, when there are any, are the same curves in strong grey with the link's name.

### Changes Off the Map
A dashed card in its tone (252×112) per change on no flow, in the "流程之外" strip, followed there by a 260px row for each flow that is gone: its summary in the tone's ink, its test status, and its number at the corner like any other change. Clicking it opens the panel.

### Map Mark
Only with no report to walk, where there is no headline: a white full pill, 32px, 13px, with the mark and "N 个模块 · M 条流程" in ink-2, plus "部分完成" in ink-3 from 640px. It only says; it is not a way between views.

### Detail Panel
A white floating inspector, closed by default, built with native shadcn Card, Tabs, Badge and Separator. Clicking a card opens it on that step (a changed card also rings); clicking a change off the map or a removed flow's name opens it on that; clicking the canvas or Esc closes it, and focus returns to what opened it. It slides in over 260ms; a new subject starts on the overview tab, scrolled to the top with local code folded. Esc steps back one thing at a time: the walk, the panel, the picked change, the focused module.
- **Header:** a small kind tile, the step name (or removed-flow name or "不在流程上的改动") and a ghost close button. A second row carries the review Badge, or a neutral step-kind/deleted Badge when there is no change or finding. A direct GitHub code action sits opposite it when a verified link is available; otherwise a live flow without a report may offer "走一遍".
- **Tabs:** the line-style "改动说明" / "Overview" tab contains explanations and evidence. Live steps also have "输入 / 输出" / "Input / output". Removed subjects and off-map changes have no input/output tab. Tabs sit beneath the header and share its inset; only the active body scrolls.
- **Overview:** each change shows its number, full summary, user impact when supplied, risk details, then a Separator and test evidence with its localized note. Risk category, severity, finding lifecycle and test evidence are distinct. Categories are reliability, correctness, data integrity and side effects, permissions and security, performance and cost, and other; absent or unknown categories display as unclassified, never inferred from prose. Risk details use a category Badge, severity text and the finding's statement. An unchanged step shows its reason or an honest unchanged message.
- **Structured input/output:** show the step's explicit input and output as separate formatted JSON objects, including JSON Schema objects when supplied. Each block has its own label, JSON marker and copy action with success/failure feedback; long lines scroll horizontally. No prose constraints section is rendered. These objects are source-backed descriptions, not a promise of runtime schema validation. Never infer fields or validation from names. Legacy prose contracts remain accepted by the backend, but if either side is a string, or the contract is missing, show "尚未提供这个步骤的结构化输入 / 输出。" rather than presenting prose as structured data.
- **Code action:** "在 GitHub 查看" opens an immutable blob URL pinned to the captured base or head commit, only when the renderer can establish a GitHub origin and the commit appears in its local origin remote-tracking refs. It never links to a mutable branch or a worktree pseudo-revision. A line anchor is included only after the captured evidence snippet digest matches that committed source range. If the worktree excerpt differs, the action reads "GitHub 已提交版本" and opens the committed file without a line anchor, while the local code remains available. With no usable repository metadata, published commit or source link, retain local code evidence.
- **Local code:** when no exact GitHub match is available, "本地代码" folds away a change's before/after snippets and evidence. Before and after stack as labelled neutral code blocks; paths use mono, excerpts are not repeated, and long lines scroll horizontally. An unchanged step shows its local evidence directly when its source link is absent or inexact. Shared files may omit excerpts; do not invent them.
- **Next:** the footer contains only “下一处改动” when another change exists. Review marking and local review-state persistence remain removed.
- **Height and spacing:** use the desktop dimensions in `components.detail-panel` and the shared 20px insets described in Layout. The header, tabs and optional footer remain fixed around the scrolling body.
- **Secondary copy:** omit the base/head revision comparison and standalone source-assessment disclaimer. Test labels describe source evidence without claiming execution.

### Walk Through (signature)
"走一遍" walks a flow the way worth watching: from its trigger, at each decision the branch passing the most changes, then the one off the error path, then the longer one. The camera moves to the trigger (560ms) at 0.85 zoom and rides along; each edge draws itself in 300ms with a dot on its tip, each step it reaches lifts its border (its tone on a change, strong grey otherwise) and rings once; the walk pauses 140ms at a step and 560ms more at a change. Everything off the walk steps back; the details panel stays open if it was. Any click, scroll or key on the map ends it, as does the bar's button; with reduced motion the whole walk shows at once, framed.

### Ripple (signature)
One ripple per change, at most 0.6s from its start, counted from when it is armed:
- 0–240ms, a ring on the change.
- 120–420ms, every edge leaving it draws itself outward (300ms, cubic-bezier(0.45, 0, 0.55, 1)), a 3.5px strong-grey dot riding the tip of edges no longer than twice the shortest; dashed edges fade in over the same stretch.
- At 420ms the steps the change leads to take their strong-grey border.
- 420–600ms, the "可能影响" tags fade up 2px.

It plays when the reader clicks a change, after the camera begins gliding to the reading area beside its details (520ms, ease-out cubic), armed at 70% of the glide. Edges the ripple will draw stay hidden until then. Dimming and lighting take 160ms. A drag, scroll, click or key settles it at its end state. Only a newly picked change plays it again. A removed flow shows its end state at once; a removed step, a result or a step with no way out plays only the ring. Reduced motion removes all of it, including the panel slide and the headline fade.

## Do's and Don'ts

### Do:
- **Do** write the change on the card it touches, with a concise summary and native review Badge.
- **Do** colour a change by what it asks of the reader: red for a new risk, amber for no test, grey for no verdict, green for tested; blue for selection. Say what the change did to the step with the glyph at its corner.
- **Do** give a change one number and show it wherever the change shows: on its card, in the list, in the panel, in the address.
- **Do** make every hue a token with a light and a dark value.
- **Do** keep the headline and details floating 16px from desktop edges, with the existing float shadow and hairline ring.
- **Do** quiet unrelated surfaces and icons instead of fading the words or hiding the surrounding path.
- **Do** give every step kind its pastel tile and Lucide glyph, at 32px on cards and 28px on pills and in the panel.
- **Do** stack before above after in the panel so both can be read at a glance.
- **Do** let only what changes move: the sentence fades, the flow prefix stays.

### Don't:
- **Don't** split the product into pages; it is one map, a module opens in place, and stepping through the changes only moves the camera.
- **Don't** show the first look smaller than it reads (0.8): wrap long diagrams instead of shrinking the map. Unchanged synthesized flows are diagrams too.
- **Don't** hide the steps around a change, leave steps out without a trace, or give added, removed and altered steps one glyph.
- **Don't** run lines between frames at rest, share one lane between several lines, or place a frame off the grid: every frame ends on the same left and right edge.
- **Don't** dock columns beside the canvas: the changes are written on the map, their list folds out of the headline and away again, and details live in the one panel, one subject at a time.
- **Don't** add a second navigator or a second counter; the compact entry walks all changes one by one or from its list, without filters or review marking.
- **Don't** use a tone for anything but its one meaning, or a second word for a test status.
- **Don't** add an entrance animation or a canvas fade-in.
- **Don't** use stamps, perforations, condensed display faces, uppercase labels or letterspacing.
- **Don't** add a switch, tabs or breadcrumbs between the whole map and a module. The frame's button opens it and closes it, in one place.
- **Don't** put entry-kind text or a step count beside a flow's name, whether diagram or compact row.
- **Don't** add tinted card backgrounds: cards are the card token and the canvas the canvas token, in both renditions.
- **Don't** read `prefers-color-scheme` in a component or a stylesheet. The rendition is the root's `data-theme`, set in one place (`viewer/src/theme.ts`, and `index.html` before the first paint); the `dark:` variant follows it.
- **Don't** use bold type. Hierarchy stops at 500.
- **Don't** imply a test ran. Statuses say what reading the code found and never claim more.
- **Don't** add a footer, a byline or a provenance line; the canvas runs to the bottom edge.

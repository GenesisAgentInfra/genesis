# Genesis viewer

The page `genesis map render` writes as `view.html`: a product's business flows on one
canvas, with a change's effect written on the steps it touches.

It builds into **one self-contained HTML file**,
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`, which the CLI fills with
data. The built page loads nothing from the network when it opens; the one request it can
make is to GitHub's compare API, and only when the reader opens the commit tree.

## Commands

Run these in `viewer/`.

| Command | What it does |
| --- | --- |
| `npm install` | Install dependencies. |
| `npm run dev` | Dev server. Pick a sample with `?sample=expense`, `refund`, `map` or `empty` (files in `dev/`). |
| `npm run build` | Type-check, then write the single HTML file into the CLI package. Commit the result. |
| `npm test` | Unit tests for the model and layout (`tests/`). |
| `npm run lint` · `npm run typecheck` · `npm run format` | ESLint, TypeScript, Prettier. |

To see a real session's data in the dev server, from the repository root:

```bash
uv run python viewer/scripts/sample_from_session.py <repo> <session-id> viewer/dev/sample-mine.json
```

To fill the built page with a sample without the CLI:

```bash
uv run python viewer/scripts/fill_template.py viewer/dev/sample-refund.json out.html
```

## Layout of the code

| Path | Holds |
| --- | --- |
| `src/types.ts` | The payload the CLI embeds (business map and change report). |
| `src/model.ts`, `src/presentation.ts` | The payload turned into what the page shows: flows, changes, their tones. |
| `src/canvas/` | One flow as a diagram: lane layout (`graph.ts`), step cards, lines. |
| `src/atlas/` | The whole product on one canvas: modules, flow cards, rows. |
| `src/components/` | Headline, change list, commit tree, detail panel; `ui/` are shadcn components. |
| `src/i18n.ts` | Interface text, Chinese and English; the page follows the content's language. |
| `graphical/` | The theme (see below). |

Stack: React 19, Vite, Tailwind CSS 4, React Flow for the canvas, Base UI primitives through
shadcn components. Compose with Base UI's `render` prop (not `asChild`); a link that looks
like a button takes `buttonVariants` instead of being rendered through `Button`.

## Theme

Styles run on [Graphical](https://www.graphicalui.com/)'s tokens. The theme is
`graphical/themes/graphical.json`; `graphical/generated/` holds the CSS built from it, which
`src/index.css` imports. Everything the page needs is in this repository: installing,
testing and building take nothing from Graphical.

Graphical's editor, for changing the theme, is a paid package and is not in the repository.
With a licence, put its archive at `graphical/packages/editor-1.0.4.tgz` and run
`npm install`; it is an optional dependency, skipped where the archive is missing.
`npm run dev` then loads the editor around the page (`graphical/editor-root.tsx`), and each
person signs in with their own Graphical account. The built page never carries it. The
guide and skills that ship with the package (`GUI.md`, `gui/`, `.agents/skills/`) stay
local too.

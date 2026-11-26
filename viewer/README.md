# Genesis viewer

The page `genesis map render` writes as `view.html`: a product's business flows on one
canvas, with a change's effect written on the steps it touches.

It builds into **one self-contained HTML file**,
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`, which the CLI fills with
data. The built page loads nothing from the network when it opens; the one request it can
make is to GitHub's compare API, and only when the reader opens the commit tree.

## Commands

Run these in `viewer/`. They need Node.js 20.19 or later in the 20 line, 22.13 or later in
the 22 line, or 24 and later (the versions Vite 8 and ESLint 10 accept), with its npm.

| Command | What it does |
| --- | --- |
| `npm install` | Install dependencies. |
| `npm run dev` | Dev server. Pick a sample with `?sample=expense`, `refund`, `map` or `empty` (files in `dev/`). |
| `npm run build` | Type-check, then write the single HTML file into the CLI package. Commit the result. |
| `npm test` | Unit tests for the model and layout (`tests/`). |
| `npm run test:browser` | Open the built HTML with synthetic maps in Chromium and check its rendered layout. |
| `npm run check:map -- /path/to/view.html` | Check an actual local export at desktop and phone widths. You can pass several files, including share exports. |
| `npm run typecheck` | Type-check the page and `vite.config.ts` (`tsc -b`), as the build does first. |
| `npm run lint` · `npm run format` | ESLint, Prettier. |

Before a pull request that changes `viewer/`, run `npm test`, `npm run lint` and
`npm run build`, and commit the rebuilt
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html` with the source change.
Then run the Python tests again from the repository root
(`uv run --all-packages --frozen pytest -q`), since `tests/test_view.py` reads the built
page. CI runs the same commands on Node.js 22 and fails when the committed page differs
from the one the source builds.

For the browser checks, install Chromium once with `npx playwright install --only-shell chromium`, or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to an existing Chromium executable. CI runs `npm run test:browser` after building. The file checker opens the supplied HTML offline, checks its overview and opens each change listed in the viewer. A failure identifies the affected viewport and element.

The Python scripts below run from the repository root with the workspace packages
(`--all-packages`), as in [CONTRIBUTING.md](../CONTRIBUTING.md).

To see a real session's data in the dev server, write it into
`dev/sample-mine.local/`, which Git ignores (the file holds excerpts of that project's
source; do not commit it or rename it to a tracked path):

```bash
mkdir -p viewer/dev/sample-mine.local
uv run --all-packages --frozen python viewer/scripts/sample_from_session.py <repo> <session-id> viewer/dev/sample-mine.local/data.json
```

`<repo>` is the analyzed project and `<session-id>` the `ses_...` directory name under
`<repo>/.genesis/sessions/`. Then open the dev server with `?sample=mine.local/data`.

To fill the built page with a sample without the CLI, writing into `dist/`, which Git also
ignores:

```bash
mkdir -p viewer/dist
uv run --all-packages --frozen python viewer/scripts/fill_template.py viewer/dev/sample-refund.json viewer/dist/sample.html
```

`dev/sample-refund.json` is written by `scripts/make_refund_sample.py`, and the tests read
it. To change it, edit the script, rerun it with
`uv run --all-packages --frozen python viewer/scripts/make_refund_sample.py` and commit
both.

## Layout of the code

| Path | Holds |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Entry (the embedded data, or a dev sample) and the page itself: canvas, controls, keyboard. |
| `src/types.ts` | The payload the CLI embeds (business map and change report). |
| `src/model.ts`, `src/presentation.ts` | The payload turned into what the page shows: flows, changes, their tones. |
| `src/canvas/` | One flow as a diagram: lane layout (`graph.ts`), step cards, lines. |
| `src/atlas/` | The whole product on one canvas: modules, flow cards, rows. |
| `src/components/` | Headline, change list, commit tree, detail panel. `ui/` holds the shadcn Base UI Luma components. |
| `src/reader.ts` | Where the reader is on the map and where each click, key or link takes them. |
| `src/flow-graph.ts` | A flow as a graph to walk: reading order, lines that lead on or step back. |
| `src/history.ts` | The commit list, read from GitHub's compare API when the reader opens the commit tree. |
| `src/theme.ts` | The light/dark switch and the reader's kept choice (not the Graphical theme). |
| `src/i18n.ts` | Interface text, Chinese and English; the page follows the content's language. |
| `graphical/` | The theme (see below). |

Stack: React 19, Vite, Tailwind CSS 4, React Flow for the canvas, and shadcn Luma
components built on Base UI. Luma components use the viewer's theme aliases and Geist Mono.
Compose controls using Base UI's `render` prop.

## Theme

Styles run on [Graphical](https://www.graphicalui.com/)'s tokens. The active theme is
selected in `graphical/project.json` (now `alloy`, `graphical/themes/alloy.json`) from the
documents in `graphical/themes/`. `graphical/generated/` holds what is built from it: the
CSS `src/index.css` imports and the tailwind-merge config `src/lib/utils.ts` reads.
Installing, testing and building need neither the Graphical editor nor a Graphical
account. Without the editor archive (below), `npm install` prints a warning that the
tarball data for `@graphical/editor` "seems to be corrupted" and then finishes normally;
the warning only means the optional archive is absent.

The Graphical export in `src/components/graphical/` supplies the theme provider and
motion settings for the canvas. The viewer imports its controls and cards from
`@/components/ui`. The development editor previews theme and mode changes.

Graphical's editor, for changing the theme, is a paid package and is not in the repository.
With a licence, put its archive at `graphical/packages/editor-1.0.4.tgz` and run
`npm install`; it is an optional dependency, skipped where the archive is missing.
`npm run dev` then loads the editor around the page (`graphical/editor-root.tsx`), and each
person signs in with their own Graphical account. The built page never carries it. The
guide and skills that ship with the package (`GUI.md`, `gui/`, `.agents/skills/`) stay
local too.

`graphical-install`, the command that rebuilds `graphical/generated/` from a theme, ships
in the same package and is not on npm. With the package installed, run it from `viewer/`
as `npx --no-install graphical-install --theme <id>`, where `<id>` is a theme id from
`graphical/project.json`. Do not run a bare `npx graphical-install`: without the package,
npm would look the name up on the public registry. The headers of the generated CSS files
show the bare command; read them with this in mind.

Without the package you can change anything in `src/` using the existing classes and
variables: Graphical's are in `graphical/generated/tailwind-theme.css` and `theme.css`, the
viewer's own aliases in `src/index.css`. You cannot change the theme itself. A hand edit to
`graphical/project.json` or a file in `graphical/themes/` changes the theme document the
page reads at runtime while the CSS in `graphical/generated/` stays as it was. Leave those
files, `graphical/role-map.json` and `graphical/generated/` as they are, and describe the
theme change in an issue.

`graphical/install/` holds the style analysis and import scripts, their inputs and the
report of the one-time conversion to Graphical. Nothing at runtime reads it. `import.mjs`
is not run again; with the paid package, `analyze-styles.mjs` is re-run before
`graphical-install` (see its header).

# Viewer: agent notes

The viewer's styles run on Graphical: its tokens and classes come from
`graphical/generated/`, built from the theme marked `active` in `graphical/project.json`
(now `alloy`, `graphical/themes/alloy.json`). New UI uses them even when a request does
not name Graphical.

Graphical's own guide and skills are not in the repository; they come with its paid editor
package (see [README.md](README.md)). Where they are installed, read `GUI.md` before
changing UI (`gui/themes.md` describes the theme in use) and use the skills in
`.agents/skills/`: **graphical-ui** for new or edited UI, **graphical-import** for the
initial conversion and editor installation, **graphical-adopt** for later editor batches
("Copy for agent"), theme changes and package updates. The editor
(`graphical/editor-root.tsx`) runs in `npm run dev` only, and only where the package is
installed; the built page carries none of it.

Where they are not installed (any checkout without `node_modules/@graphical/editor`): the
classes are in `graphical/generated/tailwind-theme.css`, the variables in
`graphical/generated/theme.css`, and the viewer's own aliases in `src/index.css`; controls
and cards come from `src/components/ui/`. The theme cannot be changed there. Leave
`graphical/project.json`, `graphical/themes/`, `graphical/role-map.json` and
`graphical/generated/` as they are, and do not run `npx graphical-install`: the command
comes only with the paid package, and a bare `npx` would fetch the name from the public
npm registry.

A change to the page is finished only when `npm run build` has rewritten
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html` and that file is committed
with the source change, and the Python tests pass again after the build
(`uv run --all-packages --frozen pytest -q` from the repository root), since
`tests/test_view.py` reads the built page. CI tests, lints and builds the viewer and fails
when the committed page is not the one the source builds; the commands are in
[README.md](README.md).

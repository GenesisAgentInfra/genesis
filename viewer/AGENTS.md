# Viewer: agent notes

The viewer's styles run on Graphical: its tokens and classes come from
`graphical/generated/`, built from the theme in `graphical/themes/graphical.json`. New UI
uses them even when a request does not name Graphical.

Graphical's own guide and skills are not in the repository; they come with its paid editor
package (see [README.md](README.md)). Where they are installed, read `GUI.md` before
changing UI (`gui/themes.md` describes the theme in use) and use the skills in
`.agents/skills/`: **graphical-ui** for new or edited UI, **graphical-import** for the
initial conversion and editor installation, **graphical-adopt** for later editor batches
("Copy for agent"), theme changes and package updates. The editor
(`graphical/editor-root.tsx`) runs in `npm run dev` only, and only where the package is
installed; the built page carries none of it.

# Graphical

This app runs on Graphical. This folder is its Graphical project.

- `project.json`, `themes/` and `role-map.json` are the project: its themes and which one is active, and how the app's tokens map to Graphical's. Change them through the editor or Graphical's skills.
- `generated/` holds the files graphical-install writes from the active theme: `theme.css` (the theme's variables), `tailwind-theme.css` (Graphical's Tailwind classes, which read those variables) and `tailwind-merge.cjs` (the class groups `cn()` passes to tailwind-merge). The app's own token aliases are in `../src/index.css`. Don't edit the generated files. To change one, edit the theme, then, from `viewer/` with Graphical's paid editor package installed, run `npx --no-install graphical-install --theme <id>`, where `<id>` is a theme id from `project.json`. The command comes only with that package and is not on npm (see [../README.md](../README.md#theme)).
- `install/` records the import: the analysis and import scripts, their inputs and the install report. Nothing at runtime reads it.

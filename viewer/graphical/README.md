# Graphical

This app runs on Graphical. This folder is its Graphical project.

- `project.json`, `themes/` and `role-map.json` are the project: its themes and which one is active, and how the app's tokens map to Graphical's. Change them through the editor or Graphical's skills.
- `generated/` holds files graphical-install writes from the active theme: `theme.css`, the Tailwind classes and the app's token aliases. Don't edit them. To change one, edit the theme, then run `npx graphical-install --theme <id>`.
- `install/` records the import: the analysis and import scripts, their inputs and the install report. Nothing at runtime reads it.

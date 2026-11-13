# Graphical install

Rewrote 19 source files and wrote the project files in `graphical`.

## Use sites

| Family         | Rewritten | Removed | Skipped | Tokens | Kept | Preserved |
| -------------- | --------: | ------: | ------: | -----: | ---: | --------: |
| border-width   |        20 |       0 |       0 |      0 |    0 |         8 |
| color          |         0 |       0 |       0 |     18 |    8 |       252 |
| font-family    |        12 |       0 |       0 |      0 |    0 |         0 |
| font-size      |        81 |       0 |       0 |      0 |    0 |         0 |
| font-weight    |         6 |       0 |       0 |     25 |    0 |         0 |
| letter-spacing |         6 |       0 |       0 |      0 |    0 |         0 |
| line-height    |         6 |      41 |       0 |      0 |    4 |         3 |
| radius         |        73 |       0 |       0 |      0 |    0 |         6 |
| shadow         |         0 |       0 |       0 |      0 |    4 |        29 |
| spacing        |       193 |       0 |       0 |      0 |    0 |         0 |
| token          |       111 |       0 |       0 |      0 |    0 |         0 |

Removed: line heights and tracking a text style carries instead. Tokens: uses of the app’s own tokens, such as `bg-background`, which follow the token once it aliases a Graphical one, and classes that already have Graphical’s name, such as `font-medium`. Kept: values the conversion keeps as authored. Preserved: values the analysis preserved, such as content colors, artwork, state recipes and dynamic values.

## Units

| Family       | Values | Units | Multiples | Kept |
| ------------ | -----: | ----: | --------: | ---: |
| Colors       |     37 |    18 |         0 |    0 |
| Text sizes   |     10 |     5 |         0 |    0 |
| Font weights |      2 |     2 |         0 |    0 |
| Spacing      |     15 |     7 |         2 |    0 |
| Corners      |     11 |     5 |         0 |    0 |
| Borders      |      2 |     2 |         0 |    0 |
| Shadows      |      4 |     3 |         0 |    0 |

## Font classes

- `font-sans` → `font-body`
- `font-heading` → `font-display`
- `font-mono` → `font-data`

## Skipped sites

None.

## Text style overrides

0 already present in source; 2 retained during this conversion.

These stay beside their text style, so the inspector shows each as an override of it.

- `src/canvas/step-node.tsx:71` `leading-none` on Body S: leading that sets a box’s height
- `src/canvas/step-node.tsx:410` `leading-none` on Body S: leading that sets a box’s height

## Cleanup

Install grouped 25 long class lists by layout, box, type and appearance, then states.

## Spacing multiples

Spacing past the largest step is written as a multiple of it. Name the large ones in a few places for what they are, such as `--page-gutter` or `--toolbar-clearance`: a custom property in a CSS rule beside the layout, with its responsive values, that the layout reads through `var(--page-gutter)`. A multiple used widely is ordinary spacing the scale doesn’t reach: raise it rather than naming it. Steps such as `gap-m` and `px-l` stay as classes.

| Multiple  | Value | Uses | Files | Most used as                         |
| --------- | ----: | ---: | ----: | ------------------------------------ |
| XXL × 4/3 |  32px |    1 |     1 | `p-[calc(var(--space-xxl)*4/3)]` (1) |

## Kept values

None.

## Left to the agent

- Load `graphical/generated/theme.css` before the app’s styles. Install rewrote the token definitions written in CSS as aliases. Semantic names such as `bg-background` stay as aliases.
- Import `graphical/generated/tailwind-theme.css` right after `@import "tailwindcss"`.
- Pass `graphical/generated/tailwind-merge.cjs` to the app’s `extendTailwindMerge`, and have every `cn()` use that merger.
- Resolve the skipped sites, install the theme’s fonts and mount the editor.
- Check the running app. This report and `graphical-install --check` read source, so they show the conversion is complete, not that the app runs. Load the home page and one other page with the dev server: each renders with the editor mounted, and the browser console and the framework’s error overlay show no errors. A page can answer HTTP 200 while a client error stops the editor from loading.

'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { ComponentTheme, createAppearanceResolver } from "./component-theme";
import {
  previewCssVariables,
  type ColorMode,
  type ThemeDefinition,
  type ThemeDocument,
} from "../../lib/theme-model";

const DocumentContext = createContext<{
  document: ThemeDocument;
  colorMode: ColorMode;
} | null>(null);
const IconThemeContext = createContext<{
  iconFamily: ThemeDefinition['iconFamily'];
  iconStyle: ThemeDefinition['iconStyle'];
  iconWeight: ThemeDefinition['iconWeight'];
} | null>(null);

/** Application-wide theme scope. ComponentTheme also carries these values into portals. */
export function GraphicalProvider({
  document,
  colorMode = 'light',
  children,
}: {
  document: ThemeDocument;
  colorMode?: ColorMode;
  children: ReactNode;
}) {
  const variables = useMemo(
    () => previewCssVariables(document.theme, colorMode),
    [document.theme, colorMode],
  );
  const resolve = useMemo(
    () => createAppearanceResolver(document, colorMode),
    [document, colorMode],
  );
  const value = useMemo(() => ({ document, colorMode }), [document, colorMode]);
  const { iconFamily, iconStyle, iconWeight } = document.theme;
  const iconTheme = useMemo(
    () => ({ iconFamily, iconStyle, iconWeight }),
    [iconFamily, iconStyle, iconWeight],
  );
  return (
    <DocumentContext value={value}>
      <IconThemeContext value={iconTheme}>
        <ComponentTheme
          component="button"
          appearances={resolve('button')}
          variables={variables}
          resolveComponent={resolve}
        >
          <div
            className="graphical-theme"
            data-graphical-theme={document.theme.name}
            data-color-mode={colorMode}
            style={{ ...variables, colorScheme: colorMode }}
          >
            {children}
          </div>
        </ComponentTheme>
      </IconThemeContext>
    </DocumentContext>
  );
}

export function useGraphicalTheme() {
  const value = useContext(DocumentContext);
  if (!value) throw new Error('useGraphicalTheme requires GraphicalProvider');
  return value;
}

/**
 * For host icon wrappers: the theme's iconFamily and iconStyle, as authored on
 * document.theme. Consumers re-render only when one of them changes, not on
 * every theme edit.
 */
export function useGraphicalIconTheme() {
  const value = useContext(IconThemeContext);
  if (!value)
    throw new Error('useGraphicalIconTheme requires GraphicalProvider');
  return value;
}

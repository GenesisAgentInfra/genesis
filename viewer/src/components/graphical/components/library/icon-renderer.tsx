'use client';

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
  type SVGProps,
} from 'react';
import type { ThemeDefinition } from "../../lib/theme-model";
import type { HugeiconsVariant } from "../../lib/hugeicons-options";
import type { ThemeIconName } from "./icon";

export type ThemeIconRenderProps = SVGProps<SVGSVGElement> & {
  name: ThemeIconName;
  family: NonNullable<ThemeDefinition['iconFamily']>;
  variant: 'filled' | 'outlined';
  weight?: number;
  hugeiconsVariant?: HugeiconsVariant;
};
export type ThemeIconRenderer = {
  renderIcon: (props: ThemeIconRenderProps) => ReactNode | undefined;
  /** Optional installed catalogs; licensed artwork stays in the receiving app. */
  families?: readonly NonNullable<ThemeDefinition['iconFamily']>[];
  loadNames?: (
    family: NonNullable<ThemeDefinition['iconFamily']>,
    variant: 'filled' | 'outlined',
  ) => Promise<ThemeIconName[]>;
};
const IconRendererContext = createContext<ThemeIconRenderer | null>(null);

/** Supply separately installed artwork without bundling it into the editor. */
export function IconRendererProvider({
  children,
  renderIcon,
  families,
  loadNames,
}: ThemeIconRenderer & { children: ReactNode }) {
  const renderer = useMemo(
    () => ({ renderIcon, families, loadNames }),
    [renderIcon, families, loadNames],
  );
  return <IconRendererContext value={renderer}>{children}</IconRendererContext>;
}
export function useThemeIconRenderer() {
  return useContext(IconRendererContext);
}

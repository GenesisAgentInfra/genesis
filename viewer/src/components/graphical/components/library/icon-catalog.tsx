import type { SVGProps } from 'react';

export type CatalogIconFamily = 'Lucide' | 'Phosphor';
export type CatalogIconName = `lucide:${string}` | `phosphor:${string}`;

export function catalogIconFamily(_name: string): CatalogIconFamily | undefined {
  return undefined;
}

export function CatalogIcon(
  _props: SVGProps<SVGSVGElement> & {
    name: CatalogIconName;
    variant: 'filled' | 'outlined';
    weight?: number;
  },
) {
  return null;
}

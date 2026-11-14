import type { NeutralTone } from "./theme-color-options";
import { hugeiconsIconStyle, type HugeiconsVariant } from "./hugeicons-options";
import { themeStyleName } from "./theme-style-names";
import { componentRadius, RADIUS_CORNERS } from "./component-radius";
import type { CSSProperties } from 'react';
import { colorWithOpacity } from "./dialkit-color";
import { contrastingTextColor } from "./color-contrast";
import {
  iconWeightVariables,
  themeIconWeightVariables,
} from "./theme-icon-weight";
import {
  componentSurfaceRelief,
  resolveSurfaceDetails,
  type SurfaceDetails,
  type SurfaceRelief,
} from "./theme-surfaces";
import { BASE_UI_COMPONENTS, type CatalogComponentId } from "./base-ui-catalog";
import type { PaletteForeground, ThemeColorPalette } from "./palette-types";
import {
  DEFAULT_SPRING_BOUNCE,
  motionDuration,
  resolveMotionCss,
} from "./theme-motion";

export type ColorMode = 'light' | 'dark';
export type ComponentId =
  | 'button'
  | 'input'
  | 'select'
  | 'combobox'
  | 'checkbox'
  | 'switch'
  | CatalogComponentId;
export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'ghost'
  | 'danger';
export type ComponentState =
  | 'rest'
  | 'hover'
  | 'focus'
  | 'disabled'
  | 'highlighted'
  | 'selected'
  | 'checked'
  | 'indeterminate'
  | 'open'
  | 'pressed'
  | 'invalid'
  | 'valid'
  | 'readonly'
  | 'loading'
  | 'complete'
  | 'low'
  | 'high';

// Theme Maker's shared vocabulary, with concrete theme values instead of axes.
export const SIZE_KEYS = ['xxs', 'xs', 's', 'm', 'l', 'xl', 'xxl'] as const;
export type SizeKey = (typeof SIZE_KEYS)[number];
/**
 * Neighboring text sizes stay at least this far apart (14%), so no two read
 * as the same size: 14px and 16px are distinct, 16px and 18px are not.
 */
export const MIN_TEXT_STEP = 1.14;
/** Both type scales, body and display, have the same seven steps. */
export const TEXT_KEYS = SIZE_KEYS;
export type TextKey = SizeKey;
/**
 * Body sets interface and reading text; display sets headings. The font role
 * picks the scale: display text uses the display scale, body and data text
 * the body scale.
 */
export const TYPE_SCALES = ['body', 'display'] as const;
export type TypeScale = (typeof TYPE_SCALES)[number];
export const LETTER_SPACING_KEYS = ['xs', 's', 'm', 'l', 'xl'] as const;
export type LetterSpacingKey = (typeof LETTER_SPACING_KEYS)[number];
/** Tracking in em; the editor presents these relative values as percentages. */
export const DEFAULT_LETTER_SPACING: Record<LetterSpacingKey, number> = {
  xs: -0.02,
  s: -0.01,
  m: 0,
  l: 0.01,
  xl: 0.02,
};
/** Larger text tightens; small labels open up slightly. */
export const TEXT_LETTER_SPACING: Record<TextKey, LetterSpacingKey> = {
  xxs: 'xl',
  xs: 'l',
  s: 'l',
  m: 'm',
  l: 's',
  xl: 's',
  xxl: 'xs',
};

export function letterSpacingScale(theme: ThemeDefinition) {
  return theme.letterSpacing ?? DEFAULT_LETTER_SPACING;
}

export function resolveLetterSpacing(
  theme: ThemeDefinition,
  textSize: TextKey,
  token: LetterSpacingKey = TEXT_LETTER_SPACING[textSize],
): number {
  return letterSpacingScale(theme)[token];
}

/**
 * The tracking a text style carries. Body steps pair by name. Display steps
 * run larger than their names, so each pairs as the body step nearest its
 * size would, and steps past Body XXL tighten like XXL: a 25px heading
 * tightens whatever its step is called.
 */
export function textLetterSpacingKey(
  theme: ThemeDefinition,
  scale: TypeScale,
  key: TextKey,
): LetterSpacingKey {
  if (scale === 'body') return TEXT_LETTER_SPACING[key];
  const body = themeText(theme);
  const size = themeDisplay(theme)[key].size;
  const away = (step: TextKey) =>
    Math.abs(Math.log(Math.max(body[step].size, 0.01) / Math.max(size, 0.01)));
  return TEXT_LETTER_SPACING[
    TEXT_KEYS.reduce((best, step) => (away(step) < away(best) ? step : best))
  ];
}

export const SPACE_KEYS = ['zero', ...SIZE_KEYS] as const;
export type SpaceKey = (typeof SPACE_KEYS)[number];
/**
 * Text sizes, line heights, spacing, and corner radii keep sub-pixel
 * precision so continuous edits never accumulate rounding. Everything that
 * renders, displays, or exports a length resolves it through here to whole
 * pixels. Border widths stay fractional: hairlines are intentional.
 */
export const themePx = (value: number) => Math.round(value);
/**
 * Every preset starts on the same whole-pixel scale, Charter's grid, so a
 * Size of 100% means the same text and spacing sizes in every theme. Letter
 * spacing stays per theme.
 */
export const PRESET_SCALE = {
  text: {
    xxs: { size: 10, lineHeight: 14 },
    xs: { size: 12, lineHeight: 16 },
    s: { size: 14, lineHeight: 20 },
    m: { size: 16, lineHeight: 24 },
    l: { size: 24, lineHeight: 32 },
    xl: { size: 36, lineHeight: 40 },
    xxl: { size: 48, lineHeight: 52 },
  },
  spacing: { zero: 0, xxs: 4, xs: 8, s: 12, m: 16, l: 24, xl: 32, xxl: 48 },
} satisfies {
  text: Record<SizeKey, Pick<TextStep, 'size' | 'lineHeight'>>;
  spacing: Record<SpaceKey, number>;
};
/** Independent copies of the shared text sizes and line heights. */
export function presetText(): Record<SizeKey, TextStep> {
  return Object.fromEntries(
    SIZE_KEYS.map((key) => [key, { ...PRESET_SCALE.text[key] }]),
  ) as Record<SizeKey, TextStep>;
}

/**
 * Keep neighboring text sizes at least `MIN_TEXT_STEP` apart, working out
 * from M, the base: a size too close to the one nearer M moves away from it,
 * keeping its own leading. Proportion applies this to every theme.
 */
export function distinctTextSteps(
  text: Record<SizeKey, TextStep>,
): Record<SizeKey, TextStep> {
  const keys = SIZE_KEYS.filter((key) => text[key]);
  const anchor = keys.indexOf('m');
  const next = { ...text };
  const move = (key: SizeKey, size: number) => {
    const step = next[key];
    next[key] = {
      ...step,
      size,
      lineHeight: (step.lineHeight * size) / Math.max(step.size, 0.01),
    };
  };
  // Sizes render in whole pixels, so the gap holds between rendered sizes.
  for (let index = anchor + 1; index < keys.length; index++) {
    const floor = Math.ceil(
      themePx(next[keys[index - 1]].size) * MIN_TEXT_STEP,
    );
    if (themePx(next[keys[index]].size) < floor) move(keys[index], floor);
  }
  for (let index = anchor - 1; index >= 0; index--) {
    const ceiling = Math.floor(
      themePx(next[keys[index + 1]].size) / MIN_TEXT_STEP,
    );
    if (themePx(next[keys[index]].size) > ceiling) move(keys[index], ceiling);
  }
  return next;
}

/** The body scale: interface, reading and data text. */
export function themeText(theme: ThemeDefinition): Record<SizeKey, TextStep> {
  return theme.text;
}

/**
 * The display scale, for headings. A theme without its own uses the body
 * scale's values, so its headings look as they did before display existed.
 */
export function themeDisplay(
  theme: ThemeDefinition,
): Record<SizeKey, TextStep> {
  return theme.display ?? theme.text;
}

/** The scale a font role sets its text on. */
export function fontScale(font: FontKey): TypeScale {
  return font === 'display' ? 'display' : 'body';
}

export function themeScale(
  theme: ThemeDefinition,
  scale: TypeScale,
): Record<SizeKey, TextStep> {
  return scale === 'display' ? themeDisplay(theme) : themeText(theme);
}

/** One text style: a font role's step on the scale that role uses. */
export function textStep(
  theme: ThemeDefinition,
  font: FontKey,
  size: SizeKey,
): TextStep {
  return themeScale(theme, fontScale(font))[size];
}
export const RADIUS_KEYS = ['zero', 'xs', 's', 'm', 'l', 'xl', 'full'] as const;
export type RadiusKey = (typeof RADIUS_KEYS)[number];
export const WEIGHT_KEYS = ['regular', 'medium', 'heavy'] as const;
export type WeightKey = (typeof WEIGHT_KEYS)[number];
/** Body sets interface text, display sets headings, data sets numbers and code. */
export const FONT_KEYS = ['body', 'display', 'data'] as const;
export type FontKey = (typeof FONT_KEYS)[number];
/** Roles before Display absorbed Brand and Editorial, and Body was UI. */
const LEGACY_FONT_KEYS: Readonly<Record<string, FontKey>> = {
  ui: 'body',
  brand: 'display',
  editorial: 'display',
};
/** A font role by its current or legacy name. */
export function fontKey(value: string): FontKey | undefined {
  return (FONT_KEYS as readonly string[]).includes(value)
    ? (value as FontKey)
    : LEGACY_FONT_KEYS[value];
}

const plain = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

/**
 * Read an older document in today's shape: four font roles (UI, Brand,
 * Editorial, Data) become three, with Body taking UI's face and Display
 * Brand's (every preset set Editorial to the same face). Component tokens
 * that named a legacy role follow it, and text steps beyond XXL from the
 * retired ten-step scale are dropped. Current documents pass through.
 */
export function upgradeThemeDocument<T>(value: T): T {
  if (!plain(value)) return value;
  const theme = plain(value.theme) ? { ...value.theme } : undefined;
  if (theme && plain(theme.fonts)) {
    const fonts = theme.fonts;
    if (!('body' in fonts) || !('display' in fonts) || 'ui' in fonts)
      theme.fonts = {
        body: fonts.body ?? fonts.ui,
        display: fonts.display ?? fonts.brand ?? fonts.editorial ?? fonts.ui,
        data: fonts.data ?? fonts.ui,
      };
  }
  if (theme && plain(theme.text))
    theme.text = Object.fromEntries(
      Object.entries(theme.text).filter(([key]) =>
        (SIZE_KEYS as readonly string[]).includes(key),
      ),
    );
  const fontsIn = (tokens: unknown): unknown => {
    if (Array.isArray(tokens)) return tokens.map(fontsIn);
    if (!plain(tokens)) return tokens;
    return Object.fromEntries(
      Object.entries(tokens).map(([key, entry]) => [
        key,
        key === 'font' && typeof entry === 'string'
          ? (fontKey(entry) ?? entry)
          : fontsIn(entry),
      ]),
    );
  };
  return {
    ...value,
    ...(theme ? { theme } : {}),
    ...('componentTokens' in value
      ? { componentTokens: fontsIn(value.componentTokens) }
      : {}),
    ...('componentVariants' in value
      ? { componentVariants: fontsIn(value.componentVariants) }
      : {}),
  } as T;
}
export const BORDER_KEYS = ['none', 's', 'm', 'l'] as const;
export type BorderKey = (typeof BORDER_KEYS)[number];
export const SHADOW_KEYS = ['none', 's', 'm', 'l'] as const;
export type ShadowKey = (typeof SHADOW_KEYS)[number];
export const PALETTE_KEYS = [
  'color-1',
  'color-2',
  'color-3',
  'color-4',
  'color-5',
  'color-6',
  'color-7',
  'color-8',
  'color-9',
  'color-10',
] as const;
export const NEUTRAL_KEYS = [
  'neutral-1',
  'neutral-2',
  'neutral-3',
  'neutral-4',
  'neutral-5',
  'neutral-6',
  'neutral-7',
  'neutral-8',
  'neutral-9',
  'neutral-10',
] as const;
export const SEMANTIC_KEYS = ['success', 'warning', 'error'] as const;
export type PaletteKey = (typeof PALETTE_KEYS)[number];
export type SemanticKey = (typeof SEMANTIC_KEYS)[number];
export type BaseColorKey =
  | PaletteKey
  | (typeof NEUTRAL_KEYS)[number]
  | SemanticKey;
/**
 * Every color has three levels: solid, translucent (stronger) and transparent
 * (lighter). Each style sets both opacities per color and mode.
 */
export type ColorKey =
  | BaseColorKey
  | 'none'
  | `${BaseColorKey}-translucent`
  | `${BaseColorKey}-transparent`;

export type TextStep = {
  size: number;
  lineHeight: number;
};
export type FontDefinition = {
  family: string;
  weights: Record<WeightKey, number>;
};
export type ShadowDefinition = {
  /** Omitted values use a layered, realistic shadow outside the surface. */
  type?: 'realistic' | 'box';
  position?: 'outside' | 'inside';
  x: number;
  y: number;
  blur: number;
  spread: number;
  opacity: number;
  color: Record<ColorMode, ColorKey>;
};
/** Named elevation stays linked to its scale until that layer is customized. */
export type ComponentShadow =
  | Exclude<ShadowKey, 'none'>
  | (ShadowDefinition & {
      /** Keep a control's highlight inside its edge instead of washing it out. */
      clipToBorder?: boolean;
    });
export type ThemeMotionCurve = {
  duration: number;
  easing: [number, number, number, number];
  /** Missing type preserves existing easing-based themes. */
  type?: 'easing' | 'spring';
  /** Motion for React visual duration, in seconds. Easing duration stays in ms. */
  visualDuration?: number;
  bounce?: number;
};
export type ThemeAnimation = ThemeMotionCurve & {
  // Older in-memory documents keep their small curve and gain a large default.
  large?: ThemeMotionCurve;
  popupScale: number;
  pressDistance: number;
};
export const DEFAULT_LARGE_MOTION: ThemeMotionCurve = {
  duration: 300,
  easing: [0.16, 1, 0.3, 1],
};
export function largeMotionCurve(animation: ThemeAnimation): ThemeMotionCurve {
  return animation.large ?? DEFAULT_LARGE_MOTION;
}
export type ThemeFocusRing = {
  color: ColorKey;
  width: BorderKey;
  opacity: number;
};
export type ComponentFocusRing = Omit<ThemeFocusRing, 'width'> & {
  width: BorderKey | number;
};
export function themeFocusRing(
  theme: ThemeDefinition,
): ThemeFocusRing | undefined {
  return (
    theme.focusRing ??
    (theme.name === 'Grove' && theme.border.l > 0
      ? { color: 'neutral-10', width: 'l', opacity: 50 }
      : undefined)
  );
}
/** Match the native focus outline, including borderless themes' 2px fallback. */
export function componentFocusRing(
  theme: ThemeDefinition,
  tokens: Pick<ComponentTokens, 'focusRing'>,
): ComponentFocusRing {
  return (
    tokens.focusRing ??
    themeFocusRing(theme) ?? {
      color: 'color-1',
      width: Math.max(2, theme.border.m),
      opacity: 100,
    }
  );
}

export function componentFocusOutline(
  theme: ThemeDefinition,
  mode: ColorMode,
  tokens: Pick<ComponentTokens, 'focusRing'>,
) {
  const ring = componentFocusRing(theme, tokens);
  const width = resolveBorderWidth(theme, ring.width);
  const color = resolveColor(theme, mode, ring.color);
  return `${width}px solid ${ring.opacity === 100 ? color : `color-mix(in srgb, ${color} ${ring.opacity}%, transparent)`}`;
}

export function resolveBorderWidth(
  theme: ThemeDefinition,
  width: BorderKey | number,
) {
  return typeof width === 'number'
    ? Math.max(0, Math.min(32, width))
    : theme.border[width];
}

/** Choosing a visible edge must work even when the theme has no border scale. */
export function componentBorderEdit<K extends keyof ComponentTokens>(
  theme: ThemeDefinition,
  tokens: ComponentTokens,
  key: K,
  value: ComponentTokens[K],
): Partial<ComponentTokens> {
  if (
    key === 'borderColor' &&
    value !== 'none' &&
    resolveBorderWidth(theme, tokens.borderWidth) === 0
  )
    return { borderWidth: theme.border.s > 0 ? 's' : 1 };
  if (
    key === 'borderWidth' &&
    resolveBorderWidth(theme, value as ComponentTokens['borderWidth']) > 0 &&
    tokens.borderColor === 'none'
  )
    return { borderColor: 'neutral-4' };
  return {};
}
export function themeIconStyle(theme: ThemeDefinition) {
  if (theme.iconFamily === 'Hugeicons' && theme.hugeiconsVariant)
    return hugeiconsIconStyle(theme.hugeiconsVariant);
  return theme.iconStyle ?? (theme.name === 'Grove' ? 'outlined' : 'filled');
}
export function themeHugeiconsVariant(
  theme: ThemeDefinition,
): HugeiconsVariant {
  return (
    theme.hugeiconsVariant ??
    (themeIconStyle(theme) === 'filled' ? 'solid-standard' : 'stroke-standard')
  );
}
/** Lustre starts from Atlas and shares its component styling rules. */
export function isAtlasTheme(theme: { name: string }): boolean {
  return theme.name === 'Atlas' || theme.name === 'Lustre';
}

export type ThemeCharacterProfile =
  | 'imported'
  | 'generic'
  | 'grove'
  | 'atlas'
  | 'lustre'
  | 'charter'
  | 'forma'
  | 'base';

/** Stable authored reference for relative Scale and Character controls. */
export type ThemeAdjustmentBaseline = {
  version: 1;
  textM: number;
  text: Record<SizeKey, TextStep>;
  display?: Record<SizeKey, TextStep>;
  spacing: Record<SpaceKey, number>;
  character: {
    /** Preserve the authored Character mapping across host wrappers and renames. */
    profile?: ThemeCharacterProfile;
    radius: Record<RadiusKey, number>;
    border: Record<BorderKey, number>;
    weights: Record<FontKey, Record<WeightKey, number>>;
    colorEmphasis?: number;
    buttonRadius?: 's' | 'full';
  };
};

export type ThemeDefinition = {
  /** Metadata only: concrete tokens remain the rendering source of truth. */
  adjustmentBaseline?: ThemeAdjustmentBaseline;
  /** Character thumb position when an authored emphasis endpoint clamps one side. */
  characterX?: number;
  /** Curated default key-color stops; custom colors remain unrestricted. */
  keyColorPalette?: readonly string[];
  /** Authored companions and text choices applied when a palette is selected. */
  colorPalettes?: readonly ThemeColorPalette[];
  /** Neutral defaults used when a palette omits an authored neutral override. */
  paletteBaseNeutrals?: Record<
    ColorMode,
    Record<(typeof NEUTRAL_KEYS)[number], string>
  >;
  primaryForeground?: Partial<Record<ColorMode, PaletteForeground>>;
  /** Independently selected reference for the default primary action. */
  primaryActionColor?: 'neutral-10' | 'color-1';
  /** Selected neutral ramp; values remain directly editable in colors. */
  neutralTone?: NeutralTone;
  /** Quiet–Bold's color distribution, from small accents to larger surfaces. */
  colorEmphasis?: number;
  /** Imported styles keep authored corners and strokes when Character changes. */
  characterProfile?: 'imported';
  /** The theme's default button shape, before individual component edits. */
  buttonRadius?: 's' | 'full';
  iconFamily?: 'Lucide' | 'Phosphor' | 'Central' | 'Hugeicons';
  /** Independent icon weight; absent themes retain typography-driven defaults. */
  iconWeight?: number;
  iconStyle?: 'filled' | 'outlined';
  hugeiconsVariant?: HugeiconsVariant;
  /** Optional material detailing, independent of the elevation shadow scale. */
  surfaceDetails?: SurfaceDetails;
  /** Shared keyboard-focus outline, separate from component edges and elevation. */
  focusRing?: ThemeFocusRing;
  animation: ThemeAnimation;
  name: string;
  colors: Record<
    ColorMode,
    Record<Exclude<BaseColorKey, Exclude<PaletteKey, 'color-1'>>, string> &
      Partial<Record<Exclude<PaletteKey, 'color-1'>, string>>
  >;
  /** Per-color opacity percentages for transparent tokens; omitted values use 20%. */
  colorTranslucency?: Partial<
    Record<ColorMode, Partial<Record<BaseColorKey, number>>>
  >;
  /** Per-color opacity percentages for translucent tokens; omitted values use 40%. */
  colorTranslucent?: Partial<
    Record<ColorMode, Partial<Record<BaseColorKey, number>>>
  >;
  spacing: Record<SpaceKey, number>;
  /** The body scale: interface, reading and data text. */
  text: Record<SizeKey, TextStep>;
  /**
   * The display scale, for headings. Omitted, it uses the body scale's values;
   * read it through `themeDisplay`.
   */
  display?: Record<SizeKey, TextStep>;
  /** Omitted by older documents; resolves to the shared five-step defaults. */
  letterSpacing?: Record<LetterSpacingKey, number>;
  fonts: Record<FontKey, FontDefinition>;
  radius: Record<RadiusKey, number>;
  border: Record<BorderKey, number>;
  shadows: Record<Exclude<ShadowKey, 'none'>, ShadowDefinition>;
};

/** Component declarations use named tokens, with optional local visual effects. */
export type ComponentTokens = {
  background: ColorKey;
  foreground: ColorKey;
  borderColor: ColorKey;
  /** A named width, or a local pixel width independent of the shared scale. */
  borderWidth: BorderKey | number;
  /** Local keyboard-focus treatment; omission follows the theme's outline. */
  focusRing?: ComponentFocusRing;
  /** Percentages multiply the existing color alpha or the entire layer. */
  backgroundOpacity?: number;
  opacity?: number;
  /** Local effects in pixels; omitted values are off. */
  blur?: number;
  backdropBlur?: number;
  radius: RadiusKey;
  /** Omitted corners follow the unified radius token. */
  radiusTopLeft?: RadiusKey;
  radiusTopRight?: RadiusKey;
  radiusBottomRight?: RadiusKey;
  radiusBottomLeft?: RadiusKey;
  paddingTop: SpaceKey;
  paddingBottom: SpaceKey;
  paddingX: SpaceKey;
  /** Omitted sides retain the existing horizontal padding token. */
  paddingLeft?: SpaceKey;
  paddingRight?: SpaceKey;
  gap: SpaceKey;
  textSize: TextKey;
  /** Omission follows the text size; a named choice stays linked to the theme. */
  lineHeight?: SizeKey;
  /** Omission follows the text size; a named choice stays linked to the theme. */
  letterSpacing?: LetterSpacingKey;
  font: FontKey;
  weight: WeightKey;
  shadow: ShadowKey;
  /** Ordered effects per mode. An empty list explicitly removes all shadows. */
  shadows?: Partial<Record<ColorMode, ComponentShadow[]>>;
  controlSize: SizeKey;
};
export type ComponentStyle = {
  background: string;
  backgroundImage?: string;
  /** Inset button lighting, painted separately so it cannot wash out the stroke. */
  bevelShadow?: string;
  /** Effective editable effects, including preset material highlights. */
  shadowLayers?: ComponentShadow[];
  foreground: string;
  borderColor: string;
  borderWidth: number;
  /** Distinguish an authored perimeter from a component's structural divider. */
  borderAuthored?: boolean;
  /** Native focus outline, painted separately from edges and elevation. */
  focusOutline?: string;
  opacity?: number;
  blur?: number;
  backdropBlur?: number;
  borderInset?: boolean;
  radius: number;
  radiusTopLeft?: number;
  radiusTopRight?: number;
  radiusBottomRight?: number;
  radiusBottomLeft?: number;
  paddingTop: number;
  paddingBottom: number;
  paddingX: number;
  paddingLeft?: number;
  paddingRight?: number;
  gap: number;
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  letterSpacing: number;
  fontWeight: number;
  shadow: string;
  controlSize: number;
};

/** Keep a selected surface's fill, stroke placement, and elevation when focusing it. */
export function withFocusBorder(
  style: ComponentStyle,
  focus?: ComponentStyle,
): ComponentStyle {
  return focus?.borderAuthored
    ? {
        ...style,
        borderColor: focus.borderColor,
        borderWidth: focus.borderWidth,
      }
    : style;
}

/** State overrides replace only the modes they explicitly author. */
export function mergeComponentShadows(
  ...values: (ComponentTokens['shadows'] | undefined)[]
): Pick<Partial<ComponentTokens>, 'shadows'> {
  const shadows = Object.assign({}, ...values) as NonNullable<
    ComponentTokens['shadows']
  >;
  return Object.keys(shadows).length ? { shadows } : {};
}
export type ThemeDocument = {
  schemaVersion: 2;
  name: string;
  theme: ThemeDefinition;
  componentTokens: Record<string, Partial<ComponentTokens>>;
  componentVariants?: Record<string, ButtonVariant>;
};

export const COMPONENTS: Array<{
  id: ComponentId;
  label: string;
  description: string;
}> = [
  { id: 'button', label: 'Button', description: 'Actions and intent' },
  { id: 'input', label: 'Text field', description: 'Single-line entry' },
  { id: 'select', label: 'Select', description: 'Option choice' },
  {
    id: 'combobox',
    label: 'Combobox',
    description: 'Searchable option choice',
  },
  { id: 'checkbox', label: 'Checkbox', description: 'Boolean choice' },
  { id: 'switch', label: 'Switch', description: 'Immediate setting' },
  ...BASE_UI_COMPONENTS.map(([id, label]) => ({
    id,
    label,
    description: label,
  })),
].sort((a, b) => a.label.localeCompare(b.label)) as Array<{
  id: ComponentId;
  label: string;
  description: string;
}>;

const font = (family: string): FontDefinition => ({
  family,
  weights: { regular: 400, medium: 500, heavy: 700 },
});
export const SYSTEM_UI_FONT =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
export const DEFAULT_DOCUMENT: ThemeDocument = {
  schemaVersion: 2,
  name: 'Grove UI',
  theme: {
    name: 'Grove',
    iconStyle: 'outlined',
    animation: {
      duration: 150,
      easing: [0.2, 0.8, 0.2, 1],
      large: { duration: 300, easing: [0.16, 1, 0.3, 1] },
      popupScale: 0.96,
      pressDistance: 1,
    },
    colors: {
      light: {
        'color-1': '#76ef6b',
        'color-2': '#00c9bb',
        'color-3': '#E0E709',
        'color-4': '#e864ff',
        'neutral-1': '#ffffff',
        'neutral-2': '#fafafa',
        'neutral-3': '#f0f0f0',
        'neutral-4': '#dedede',
        'neutral-5': '#c5c5c5',
        'neutral-6': '#969696',
        'neutral-7': '#6c6c6c',
        'neutral-8': '#454545',
        'neutral-9': '#252525',
        'neutral-10': '#000000',
        success: '#76ef6b',
        warning: '#ffa344',
        error: '#ff5263',
      },
      dark: {
        'color-1': '#76ef6b',
        'color-2': '#00c9bb',
        'color-3': '#f4f83b',
        'color-4': '#e864ff',
        'neutral-1': '#000000',
        'neutral-2': '#202020',
        'neutral-3': '#2b2b2b',
        'neutral-4': '#383838',
        'neutral-5': '#505050',
        'neutral-6': '#777777',
        'neutral-7': '#a3a3a3',
        'neutral-8': '#c6c6c6',
        'neutral-9': '#e5e5e5',
        'neutral-10': '#ffffff',
        success: '#76ef6b',
        warning: '#ffa344',
        error: '#ff5263',
      },
    },
    spacing: { zero: 0, xxs: 4, xs: 8, s: 12, m: 16, l: 24, xl: 32, xxl: 48 },
    letterSpacing: { ...DEFAULT_LETTER_SPACING },
    text: {
      xxs: { size: 10, lineHeight: 15 },
      xs: { size: 12, lineHeight: 16 },
      s: { size: 14, lineHeight: 20 },
      m: { size: 16, lineHeight: 24 },
      l: { size: 24, lineHeight: 33.6 },
      xl: { size: 36, lineHeight: 45 },
      xxl: { size: 54, lineHeight: 59.4 },
    },
    fonts: {
      body: font(SYSTEM_UI_FONT),
      display: font(SYSTEM_UI_FONT),
      data: font('ui-monospace, SFMono-Regular, Menlo, monospace'),
    },
    radius: { zero: 0, xs: 4, s: 8, m: 12, l: 24, xl: 36, full: 9999 },
    border: { none: 0, s: 1, m: 1, l: 2 },
    shadows: {
      s: {
        x: 0,
        y: 1,
        blur: 2,
        spread: 0,
        opacity: 0,
        color: { light: 'neutral-10', dark: 'neutral-1' },
      },
      m: {
        x: 0,
        y: 8,
        blur: 24,
        spread: 0,
        opacity: 0,
        color: { light: 'neutral-10', dark: 'neutral-1' },
      },
      l: {
        x: 0,
        y: 12,
        blur: 30,
        spread: 0,
        opacity: 0,
        color: { light: 'neutral-10', dark: 'neutral-1' },
      },
    },
  },
  componentTokens: {},
};
export function tokenLabel(key: string): string {
  if (key === 'zero') return '0';
  if (SIZE_KEYS.includes(key as SizeKey)) return key.toUpperCase();
  return key
    .split('-')
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}
/** The solid color behind any level: `color-1` for `color-1-translucent`. */
export function baseColorKey(key: Exclude<ColorKey, 'none'>): BaseColorKey {
  return key.replace(/-(?:translucent|transparent)$/, '') as BaseColorKey;
}
/** Whether a key is one of a color's translucent levels. */
export function isTranslucentColorKey(key: ColorKey) {
  return /-(?:translucent|transparent)$/.test(key);
}
export function transparentColorKey(key: ColorKey): ColorKey {
  return key === 'none' ? key : `${baseColorKey(key)}-transparent`;
}
export function translucentColorKey(key: ColorKey): ColorKey {
  return key === 'none' ? key : `${baseColorKey(key)}-translucent`;
}

export function paletteKeys(theme: ThemeDefinition, mode: ColorMode) {
  return PALETTE_KEYS.filter((key) => theme.colors[mode][key] !== undefined);
}

export function themeColorTranslucency(
  theme: ThemeDefinition,
  mode: ColorMode,
  key: BaseColorKey,
) {
  return Math.max(
    0,
    Math.min(100, theme.colorTranslucency?.[mode]?.[key] ?? 20),
  );
}

/** The translucent level's opacity percentage. */
export function themeColorTranslucent(
  theme: ThemeDefinition,
  mode: ColorMode,
  key: BaseColorKey,
) {
  return Math.max(
    0,
    Math.min(100, theme.colorTranslucent?.[mode]?.[key] ?? 40),
  );
}

export function resolveColor(
  theme: ThemeDefinition,
  mode: ColorMode,
  key: ColorKey,
): string {
  if (key === 'none') return 'transparent';
  const base = baseColorKey(key);
  const color = theme.colors[mode][base];
  if (!color) return 'transparent';
  if (key.endsWith('-transparent'))
    return colorWithOpacity(
      color,
      themeColorTranslucency(theme, mode, base) / 100,
    );
  if (key.endsWith('-translucent'))
    return colorWithOpacity(
      color,
      themeColorTranslucent(theme, mode, base) / 100,
    );
  return color;
}
export function resolveShadow(
  theme: ThemeDefinition,
  mode: ColorMode,
  key: ShadowKey,
): string {
  if (key === 'none') return 'none';
  return resolveShadowDefinition(theme, mode, theme.shadows[key]);
}
export function resolveShadowDefinition(
  theme: ThemeDefinition,
  mode: ColorMode,
  value: ShadowDefinition,
): string {
  const ink = resolveColor(theme, mode, value.color[mode]);
  const opacity = Math.max(0, Math.min(1, value.opacity / 100));
  const inset = value.position === 'inside' ? 'inset ' : '';
  const layer = (scale: number, alpha: number) => {
    const px = (amount: number) =>
      `${Math.round(amount * scale * 100) / 100}px`;
    return `${inset}${px(value.x)} ${px(value.y)} ${px(value.blur)} ${px(value.spread)} ${colorWithOpacity(ink, alpha)}`;
  };
  if (value.type === 'box' || value.blur === 0 || opacity === 0)
    return layer(1, opacity);
  // A tight contact layer grounds the softer ambient layer. Split opacity so
  // their overlap retains the authored strength instead of doubling it.
  return [
    layer(0.25, 1 - (1 - opacity) ** 0.4),
    layer(1, 1 - (1 - opacity) ** 0.6),
  ].join(', ');
}
function resolveColorOptions(theme: ThemeDefinition, mode: ColorMode) {
  const baseGroups = [
    { label: 'Palette', keys: paletteKeys(theme, mode) },
    { label: 'Neutrals', keys: NEUTRAL_KEYS },
    { label: 'Status', keys: SEMANTIC_KEYS },
  ];
  return [
    {
      label: 'None',
      options: [
        { value: 'none' as ColorKey, label: 'None', color: 'transparent' },
      ],
    },
    ...baseGroups.map((group) => ({
      label: group.label,
      options: group.keys.flatMap((base) =>
        [base, translucentColorKey(base), transparentColorKey(base)].map(
          (value) => ({
            value,
            label: tokenLabel(value),
            color: resolveColor(theme, mode, value),
            // Embedded inspectors serialize values as CSS references; retain
            // the family and authored opacity independently of that spelling.
            colorToken: {
              base,
              level: value.endsWith('-translucent')
                ? ('translucent' as const)
                : value.endsWith('-transparent')
                  ? ('transparent' as const)
                  : ('full' as const),
              opacity: value.endsWith('-translucent')
                ? themeColorTranslucent(theme, mode, base)
                : value.endsWith('-transparent')
                  ? themeColorTranslucency(theme, mode, base)
                  : 100,
            },
          }),
        ),
      ),
    })),
  ];
}
type ColorOptionGroups = ReturnType<typeof resolveColorOptions>;
// Options depend only on one mode's colors and translucency. Theme edits copy
// those records rather than mutating them, so their identity keys the cache.
const colorOptionCache = new WeakMap<
  object,
  {
    translucency: object | undefined;
    translucent: object | undefined;
    groups: ColorOptionGroups;
  }
>();
/** Shared, read-only option groups; editors request these on every render. */
export function colorOptions(
  theme: ThemeDefinition,
  mode: ColorMode,
): ColorOptionGroups {
  const colors = theme.colors[mode];
  const translucency = theme.colorTranslucency?.[mode];
  const translucent = theme.colorTranslucent?.[mode];
  const cached = colorOptionCache.get(colors);
  if (
    cached &&
    cached.translucency === translucency &&
    cached.translucent === translucent
  )
    return cached.groups;
  const groups = resolveColorOptions(theme, mode);
  colorOptionCache.set(colors, { translucency, translucent, groups });
  return groups;
}
export function componentKey(
  componentId: ComponentId,
  variant = 'default',
  state: ComponentState = 'rest',
) {
  return `${componentId}:${variant}:${state}`;
}
const BUTTON_COLORS: Record<
  ButtonVariant,
  Pick<ComponentTokens, 'background' | 'foreground' | 'borderColor'>
> = {
  primary: {
    background: 'color-1',
    foreground: 'neutral-1',
    borderColor: 'color-1-transparent',
  },
  secondary: {
    background: 'neutral-3',
    foreground: 'neutral-10',
    borderColor: 'neutral-3-transparent',
  },
  outline: {
    background: 'none',
    foreground: 'neutral-10',
    borderColor: 'neutral-4-transparent',
  },
  ghost: {
    background: 'none',
    foreground: 'neutral-10',
    borderColor: 'none',
  },
  danger: {
    background: 'error',
    foreground: 'neutral-1',
    borderColor: 'error-transparent',
  },
};
const BUTTON_HOVER: Record<ButtonVariant, Partial<ComponentTokens>> = {
  primary: { shadow: 's' },
  secondary: {
    background: 'neutral-4-transparent',
    borderColor: 'neutral-4-transparent',
  },
  outline: { background: 'neutral-3-transparent' },
  ghost: { background: 'neutral-3-transparent' },
  danger: { shadow: 's' },
};

/** Distribute color through named references without changing palette opacity. */
function emphasisColor(
  theme: ThemeDefinition,
  quiet: ColorKey,
  balanced: ColorKey,
  bold: ColorKey,
): ColorKey {
  const emphasis = theme.colorEmphasis ?? 50;
  return emphasis < 34 ? quiet : emphasis > 66 ? bold : balanced;
}

export function resolveComponentTokens(
  document: ThemeDocument,
  componentId: ComponentId,
  state: ComponentState,
  variant: ButtonVariant | 'default' = 'default',
): ComponentTokens {
  const choice = componentId === 'checkbox' || componentId === 'switch';
  const buttonVariant = variant === 'default' ? 'primary' : variant;
  const outlinedButton =
    componentId === 'button' &&
    buttonVariant === 'outline' &&
    ['Grove', 'Lustre', 'Charter'].includes(document.theme.name);
  const lustreSecondary =
    componentId === 'button' &&
    buttonVariant === 'secondary' &&
    document.theme.name === 'Lustre';
  const lustreSecondaryFill =
    document.theme.primaryActionColor === 'neutral-10'
      ? 'neutral-3'
      : emphasisColor(
          document.theme,
          'neutral-3',
          'neutral-3',
          'color-1-transparent',
        );
  const base: ComponentTokens = {
    background: choice ? 'color-1' : 'neutral-1',
    foreground: choice ? 'neutral-1' : 'neutral-10',
    borderColor: choice ? 'color-1-transparent' : 'neutral-4',
    borderWidth:
      outlinedButton && document.theme.border.s === 0
        ? 1
        : componentId === 'button' &&
            document.theme.name === 'Charter' &&
            !outlinedButton
          ? 'none'
          : 's',
    radius:
      componentId === 'button'
        ? (document.theme.buttonRadius ?? 's')
        : componentId === 'checkbox'
          ? 'xs'
          : componentId === 'switch'
            ? document.theme.name === 'Grove'
              ? 's'
              : 'full'
            : 's',
    paddingTop: 'xs',
    paddingBottom: 'xs',
    paddingX: componentId === 'button' ? 'm' : 's',
    gap: 'xs',
    textSize: document.theme.name === 'Grove' ? 'm' : 's',
    font: 'body',
    weight: componentId === 'button' ? 'medium' : 'regular',
    controlSize: componentId === 'checkbox' ? 'm' : 'l',
    shadow: 'none',
    ...(componentId === 'button' ? BUTTON_COLORS[buttonVariant] : {}),
    // An outline is the control's visible boundary, even in otherwise borderless themes.
    ...(outlinedButton && { borderColor: 'neutral-4' }),
    // A neutral primary action keeps its secondary companion uncolored too.
    ...(componentId === 'button' &&
      buttonVariant === 'secondary' &&
      document.theme.colorEmphasis !== undefined &&
      document.theme.primaryActionColor !== 'neutral-10' && {
        background: emphasisColor(
          document.theme,
          'neutral-3',
          'neutral-3',
          'color-1-transparent',
        ),
      }),
    ...(componentId === 'button' &&
      buttonVariant === 'secondary' &&
      document.theme.name === 'Charter' && {
        background:
          document.theme.primaryActionColor === 'neutral-10'
            ? 'neutral-3'
            : 'color-1-transparent',
      }),
    ...(lustreSecondary && { background: lustreSecondaryFill }),
    ...(componentId === 'button' &&
      buttonVariant === 'primary' && {
        background: document.theme.primaryActionColor ?? 'color-1',
        // Felt primary actions stay borderless as Character increases emphasis.
        ...(document.theme.name === 'Atlas' && { borderWidth: 'none' }),
        borderColor: transparentColorKey(
          document.theme.primaryActionColor ?? 'color-1',
        ),
      }),
  };
  const stateDefaults: Partial<
    Record<ComponentState, Partial<ComponentTokens>>
  > = {
    hover:
      componentId === 'button'
        ? {
            ...BUTTON_HOVER[buttonVariant],
            ...(lustreSecondary && {
              background:
                lustreSecondaryFill === 'color-1-transparent'
                  ? ('color-1-transparent' as const)
                  : ('neutral-4' as const),
              ...(lustreSecondaryFill === 'color-1-transparent' && {
                borderColor: 'color-1-transparent' as const,
                shadow: 's' as const,
              }),
            }),
            ...(buttonVariant === 'secondary' &&
              document.theme.name === 'Charter' &&
              document.theme.primaryActionColor !== 'neutral-10' && {
                background: 'color-1-transparent' as const,
                shadow: 's' as const,
              }),
          }
        : { borderColor: 'neutral-5' },
    focus: { borderColor: 'color-1-transparent' },
    ...(componentId === 'input'
      ? {
          invalid: { borderColor: 'error' as const },
          valid: { borderColor: 'success' as const },
          readonly: {
            background: 'neutral-2' as const,
            foreground: 'neutral-8' as const,
          },
        }
      : {}),
    disabled: {
      background:
        componentId === 'button' &&
        (buttonVariant === 'ghost' || buttonVariant === 'outline')
          ? 'none'
          : 'neutral-3',
      foreground: 'neutral-6',
      borderColor:
        componentId === 'button' && buttonVariant === 'ghost'
          ? 'none'
          : 'neutral-4-transparent',
      shadow: 'none',
    },
  };
  return {
    ...base,
    ...document.componentTokens[componentKey(componentId, variant)],
    ...(state === 'rest' ? {} : stateDefaults[state]),
    ...(state === 'rest'
      ? {}
      : document.componentTokens[componentKey(componentId, variant, state)]),
    ...mergeComponentShadows(
      document.componentTokens[componentKey(componentId, variant)]?.shadows,
      state === 'rest'
        ? undefined
        : document.componentTokens[componentKey(componentId, variant, state)]
            ?.shadows,
    ),
  };
}
export function setComponentToken<K extends keyof ComponentTokens>(
  document: ThemeDocument,
  componentId: ComponentId,
  variant: ButtonVariant | 'default',
  state: ComponentState,
  key: K,
  value: ComponentTokens[K],
): ThemeDocument {
  const id = componentKey(componentId, variant, state);
  const borderEdit = componentBorderEdit(
    document.theme,
    resolveComponentTokens(document, componentId, state, variant),
    key,
    value,
  );
  return {
    ...document,
    componentTokens: {
      ...document.componentTokens,
      [id]: { ...document.componentTokens[id], ...borderEdit, [key]: value },
    },
  };
}
export function resolveComponentStyle(
  document: ThemeDocument,
  mode: ColorMode,
  componentId: ComponentId,
  state: ComponentState,
  variant: ButtonVariant | 'default' = 'default',
): ComponentStyle {
  const tokens = resolveComponentTokens(document, componentId, state, variant);
  const style = resolveTokenStyle(document.theme, mode, tokens, state, {
    surface: componentSurfaceRelief(componentId),
    borderInset: componentBorderInset(document.theme, componentId, variant),
    borderColorAuthored:
      (componentId === 'button' && variant === 'outline') ||
      hasComponentBorderColorOverride(document, componentId, variant, state),
  });
  if (!hasComponentForegroundOverride(document, componentId, variant, state))
    style.foreground = resolveAutomaticForeground(document.theme, mode, tokens);
  style.focusOutline = componentFocusOutline(
    document.theme,
    mode,
    resolveComponentTokens(document, componentId, 'focus', variant),
  );
  return style;
}

export function hasComponentForegroundOverride(
  document: ThemeDocument,
  component: ComponentId,
  variant: ButtonVariant | 'default',
  state: ComponentState,
) {
  return (
    document.componentTokens[componentKey(component, variant)]?.foreground !==
      undefined ||
    document.componentTokens[componentKey(component, variant, state)]
      ?.foreground !== undefined
  );
}

export function hasComponentBorderColorOverride(
  document: ThemeDocument,
  component: ComponentId,
  variant: ButtonVariant | 'default',
  state: ComponentState,
) {
  return (
    document.componentTokens[componentKey(component, variant)]?.borderColor !==
      undefined ||
    document.componentTokens[componentKey(component, variant, state)]
      ?.borderColor !== undefined
  );
}

const GROVE_BORDER_COLOR = 'rgb(0 0 0 / 0.1)';

/** Default accent text follows its authored choice or contrast; explicit tokens stay literal. */
export function resolveAutomaticForeground(
  theme: ThemeDefinition,
  mode: ColorMode,
  tokens: Pick<ComponentTokens, 'background' | 'foreground'>,
) {
  const isAccent = [...PALETTE_KEYS, ...SEMANTIC_KEYS].some(
    (key) => key === tokens.background,
  );
  return isAccent &&
    (tokens.foreground === 'neutral-1' || tokens.foreground === 'neutral-10')
    ? tokens.background === 'color-1' && theme.primaryForeground?.[mode]
      ? resolveColor(theme, mode, theme.primaryForeground[mode])
      : contrastingTextColor(
          resolveColor(theme, mode, tokens.background),
          resolveColor(theme, mode, 'neutral-1'),
        )
    : resolveColor(theme, mode, tokens.foreground);
}

/**
 * Controls whose strokes sit inside: buttons, except Grove's secondary
 * button, and Grove's checkbox. Grove and Lustre apply it (see below).
 */
export function componentBorderInset(
  theme: Pick<ThemeDefinition, 'name'>,
  componentId: ComponentId,
  variant: ButtonVariant | 'default' = 'default',
): boolean {
  return (
    (componentId === 'button' &&
      !(theme.name === 'Grove' && variant === 'secondary')) ||
    (theme.name === 'Grove' && componentId === 'checkbox')
  );
}

/** Filled surfaces contain their edges in Charter and Forma; light surfaces keep outer edges. */
export function themeBorderInset(
  theme: ThemeDefinition,
  mode: ColorMode,
  background: ColorKey,
  controlInset = false,
): boolean {
  if (theme.name !== 'Charter' && theme.name !== 'Forma')
    return (theme.name === 'Grove' || theme.name === 'Lustre') && controlInset;
  if (background === 'none') return false;
  const base = baseColorKey(background);
  return (
    [...PALETTE_KEYS, ...SEMANTIC_KEYS].some((key) => key === base) ||
    contrastingTextColor(
      resolveColor(theme, mode, background),
      resolveColor(theme, mode, 'neutral-1'),
    ) === '#ffffff'
  );
}

export function resolveTokenStyle(
  theme: ThemeDefinition,
  mode: ColorMode,
  tokens: ComponentTokens,
  state: ComponentState = 'rest',
  {
    borderColorAuthored = false,
    borderInset = false,
    suppressFocusRing = false,
    surface,
  }: {
    borderColorAuthored?: boolean;
    borderInset?: boolean;
    suppressFocusRing?: boolean;
    surface?: SurfaceRelief;
  } = {},
): ComponentStyle {
  const face = theme.fonts[tokens.font];
  const text = themeText(theme)[tokens.textSize];
  const borderWidth = resolveBorderWidth(theme, tokens.borderWidth);
  const backgroundOpacity = Math.max(
    0,
    Math.min(100, tokens.backgroundOpacity ?? 100),
  );
  const background = resolveColor(theme, mode, tokens.background);
  // Flat fills, text-only parts, translucent levels, and disabled controls stay flat.
  const details =
    surface &&
    tokens.background !== 'none' &&
    !isTranslucentColorKey(tokens.background) &&
    state !== 'disabled' &&
    backgroundOpacity === 100 &&
    (borderWidth > 0 || tokens.shadow !== 'none')
      ? resolveSurfaceDetails(
          theme,
          mode,
          state === 'pressed' ? 'recessed' : surface,
          (theme.name === 'Lustre' || theme.name === 'Forma') && borderInset
            ? borderWidth
            : undefined,
        )
      : { backgroundImage: 'none', shadow: 'none', shadowLayers: [] };
  const shadowLayers: ComponentShadow[] = tokens.shadows?.[mode] ?? [
    ...details.shadowLayers,
    ...(tokens.shadow === 'none' ? [] : [tokens.shadow]),
  ];
  const resolvedShadows = shadowLayers.map((layer) => ({
    value:
      typeof layer === 'string'
        ? resolveShadow(theme, mode, layer)
        : resolveShadowDefinition(theme, mode, layer),
    bevel:
      typeof layer !== 'string' &&
      layer.clipToBorder &&
      layer.position === 'inside',
  }));
  const shadow =
    resolvedShadows
      .filter((layer) => !layer.bevel)
      .map((layer) => layer.value)
      .join(', ') || 'none';
  const bevelShadow =
    resolvedShadows
      .filter((layer) => layer.bevel)
      .map((layer) => layer.value)
      .join(', ') || 'none';
  const focus = `0 0 0 ${theme.border.l}px color-mix(in srgb, ${resolveColor(theme, mode, 'color-1-transparent')} 24%, transparent)`;
  return {
    background:
      backgroundOpacity === 100 || background === 'transparent'
        ? background
        : `color-mix(in srgb, ${background} ${backgroundOpacity}%, transparent)`,
    opacity: Math.max(0, Math.min(100, tokens.opacity ?? 100)) / 100,
    blur: Math.max(0, Math.min(100, tokens.blur ?? 0)),
    backdropBlur: Math.max(0, Math.min(100, tokens.backdropBlur ?? 0)),
    backgroundImage: details.backgroundImage,
    bevelShadow,
    shadowLayers,
    foreground: resolveColor(theme, mode, tokens.foreground),
    borderColor:
      theme.name === 'Grove' &&
      tokens.borderColor !== 'none' &&
      !borderColorAuthored &&
      state !== 'invalid' &&
      state !== 'valid'
        ? GROVE_BORDER_COLOR
        : resolveColor(theme, mode, tokens.borderColor),
    borderWidth,
    ...(tokens.focusRing && {
      focusOutline: componentFocusOutline(theme, mode, tokens),
    }),
    borderInset: themeBorderInset(theme, mode, tokens.background, borderInset),
    radius: themePx(theme.radius[tokens.radius]),
    ...Object.fromEntries(
      RADIUS_CORNERS.map((corner) => [
        corner,
        tokens[corner] === undefined
          ? undefined
          : themePx(theme.radius[tokens[corner]]),
      ]),
    ),
    paddingTop: themePx(theme.spacing[tokens.paddingTop]),
    paddingBottom: themePx(theme.spacing[tokens.paddingBottom]),
    paddingX: themePx(theme.spacing[tokens.paddingX]),
    paddingLeft: themePx(theme.spacing[tokens.paddingLeft ?? tokens.paddingX]),
    paddingRight: themePx(
      theme.spacing[tokens.paddingRight ?? tokens.paddingX],
    ),
    gap: themePx(theme.spacing[tokens.gap]),
    fontFamily: face.family,
    fontSize: themePx(text.size),
    lineHeight: themePx(
      themeText(theme)[tokens.lineHeight ?? tokens.textSize].lineHeight,
    ),
    letterSpacing: resolveLetterSpacing(
      theme,
      tokens.textSize,
      tokens.letterSpacing,
    ),
    fontWeight: face.weights[tokens.weight],
    controlSize: themePx(theme.spacing[tokens.controlSize]),
    shadow:
      [
        shadow,
        state === 'focus' &&
        !themeFocusRing(theme) &&
        !tokens.focusRing &&
        !suppressFocusRing
          ? focus
          : 'none',
      ]
        .filter((layer) => layer !== 'none')
        .join(', ') || 'none',
  };
}
/** Omitted effects stay neutral; blur(0) would unnecessarily create a containing block. */
export function componentEffectStyle(style: ComponentStyle): CSSProperties {
  return {
    ...({ '--focus-ring-outline': style.focusOutline } as CSSProperties),
    opacity: `var(--component-presence-opacity, ${style.opacity ?? 1})`,
    filter: style.blur ? `blur(${style.blur}px)` : 'none',
    backdropFilter: style.backdropBlur
      ? `blur(${style.backdropBlur}px)`
      : 'none',
    WebkitBackdropFilter: style.backdropBlur
      ? `blur(${style.backdropBlur}px)`
      : 'none',
  };
}
export function componentCssStyle(style: ComponentStyle): CSSProperties {
  return {
    ...iconWeightVariables(style.fontWeight),
    ...componentEffectStyle(style),
    ...({
      '--button-bevel-content':
        style.bevelShadow && style.bevelShadow !== 'none' ? '""' : 'none',
      '--button-bevel-shadow': style.bevelShadow ?? 'none',
      '--button-bevel-inset': `${style.borderWidth}px`,
      '--button-bevel-radius': componentRadius(style, style.borderWidth),
    } as CSSProperties),
    backgroundColor: style.background,
    backgroundImage: style.backgroundImage,
    color: style.foreground,
    borderWidth: 0,
    borderStyle: 'none',
    borderRadius: componentRadius(style),
    paddingTop: style.paddingTop,
    paddingBottom: style.paddingBottom,
    paddingLeft: style.paddingLeft ?? style.paddingX,
    paddingRight: style.paddingRight ?? style.paddingX,
    gap: style.gap,
    boxShadow: componentBoxShadow(style),
    fontFamily: style.fontFamily,
    fontSize: style.fontSize,
    fontWeight: style.fontWeight,
    lineHeight: `${style.lineHeight}px`,
    letterSpacing: `${style.letterSpacing ?? 0}em`,
    height: 'auto',
    minHeight: 0,
  };
}

/** Full edges use zero-blur shadows; placement never changes layout or elevation. */
export function componentBoxShadow(
  style: Pick<
    ComponentStyle,
    'borderWidth' | 'borderColor' | 'borderInset' | 'shadow'
  >,
): string {
  return (
    [
      style.borderWidth > 0 && style.borderColor !== 'transparent'
        ? `${style.borderInset ? 'inset ' : ''}0 0 0 ${style.borderWidth}px ${style.borderColor}`
        : '',
      style.shadow === 'none' ? '' : style.shadow,
    ]
      .filter(Boolean)
      .join(', ') || 'none'
  );
}
export function resolveModeTokens(theme: ThemeDefinition, mode: ColorMode) {
  const color = (key: ColorKey) => resolveColor(theme, mode, key);
  return {
    canvas: color('neutral-1'),
    surface: color('neutral-2'),
    surfaceMuted: color('neutral-3'),
    text: color('neutral-10'),
    textMuted: color('neutral-7'),
    border:
      theme.name === 'Grove'
        ? GROVE_BORDER_COLOR
        : color(theme.surfaceDetails?.edgeColor ?? 'neutral-4-transparent'),
    accent: color('color-1'),
    accentText: resolveAutomaticForeground(theme, mode, {
      background: 'color-1',
      foreground: 'neutral-1',
    }),
    danger: color('error'),
    dangerText: contrastingTextColor(color('error'), color('neutral-1')),
    focus: color('color-1'),
  };
}
export type ModeTokens = ReturnType<typeof resolveModeTokens>;
export function previewCssVariables(
  theme: ThemeDefinition,
  mode: ColorMode,
): CSSProperties {
  const colors = resolveModeTokens(theme, mode);
  // Atlas's brand-filled preview labels retain the palette's light-mode ink.
  const accentText =
    theme.name === 'Atlas'
      ? resolveAutomaticForeground(theme, 'light', {
          background: 'color-1',
          foreground: 'neutral-1',
        })
      : colors.accentText;
  const large = largeMotionCurve(theme.animation);
  const smallMotion = resolveMotionCss(theme.animation);
  const largeMotion = resolveMotionCss(large);
  const focusRing = themeFocusRing(theme);
  const textSize = theme.name === 'Grove' ? 'm' : 's';
  const detailSize = theme.name === 'Grove' ? 'm' : 'xs';
  const text = theme.text[textSize];
  const detailText = theme.text[detailSize];
  const vars: Record<string, string | number> = {
    '--theme-name': themeStyleName(theme.name),
    '--theme-icon-family': theme.iconFamily ?? 'Lucide',
    '--theme-icon-style': themeIconStyle(theme),
    '--theme-hugeicons-variant': themeHugeiconsVariant(theme),
    ...themeIconWeightVariables(theme),
    '--toolbar-divider-bleed': theme.name === 'Grove' ? 1 : 0,
    '--focus-ring-outline': focusRing
      ? `${theme.border[focusRing.width]}px solid color-mix(in srgb, ${resolveColor(theme, mode, focusRing.color)} ${focusRing.opacity}%, transparent)`
      : 'initial',
    ...iconWeightVariables(theme.fonts.body.weights.regular),
    '--motion-duration': `${smallMotion.duration}ms`,
    '--motion-easing': smallMotion.easing,
    '--motion-type': theme.animation.type ?? 'easing',
    '--motion-visual-duration': motionDuration(theme.animation) / 1000,
    '--motion-bounce': theme.animation.bounce ?? DEFAULT_SPRING_BOUNCE,
    '--motion-enabled': smallMotion.duration === 0 ? 0 : 1,
    '--motion-small-iterations': smallMotion.duration === 0 ? 0 : 'infinite',
    '--motion-large-duration': `${largeMotion.duration}ms`,
    '--motion-large-easing': largeMotion.easing,
    '--motion-large-type': large.type ?? 'easing',
    '--motion-large-visual-duration': motionDuration(large) / 1000,
    '--motion-large-bounce': large.bounce ?? DEFAULT_SPRING_BOUNCE,
    '--motion-large-iterations': largeMotion.duration === 0 ? 0 : 'infinite',
    '--motion-popup-scale': theme.animation.popupScale,
    '--motion-press-distance': `${smallMotion.duration === 0 ? 0 : theme.animation.pressDistance}px`,
    '--option-badge-background': isAtlasTheme(theme)
      ? colors.accent
      : 'color-mix(in srgb, var(--color-1) 10%, transparent)',
    '--option-badge-foreground': isAtlasTheme(theme)
      ? accentText
      : colors.accent,
    '--navigation-active-foreground': accentText,
    '--emphasis-chart-fill': resolveColor(
      theme,
      mode,
      theme.name === 'Grove'
        ? emphasisColor(theme, 'none', 'color-1-transparent', 'color-1')
        : 'color-1-transparent',
    ),
  };
  if (theme.colorEmphasis !== undefined) {
    // Atlas concentrates figure accents on the balance-card backdrop.
    const atlas = theme.name === 'Atlas';
    const emphasis = (quiet: ColorKey, balanced: ColorKey, bold: ColorKey) =>
      emphasisColor(theme, quiet, balanced, bold);
    const foreground = (background: ColorKey) =>
      background === 'color-1'
        ? accentText
        : resolveAutomaticForeground(theme, mode, {
            background,
            foreground: 'neutral-10',
          });
    const companion = (key: PaletteKey): ColorKey =>
      theme.colors[mode][key] ? key : 'color-1';
    const iconBackground = emphasis(
      'neutral-3',
      'neutral-3',
      atlas ? 'neutral-3' : companion('color-3'),
    );
    const typeBackground = emphasis(
      'neutral-3',
      'neutral-3',
      atlas ? 'neutral-3' : 'color-1',
    );
    const navigationBackground = emphasis(
      atlas ? 'neutral-4' : 'neutral-3',
      isAtlasTheme(theme) ? 'color-1' : 'color-1-transparent',
      'color-1',
    );
    vars['--emphasis-balance-background'] = resolveColor(
      theme,
      mode,
      emphasis(
        atlas ? 'neutral-5' : 'neutral-3',
        atlas ? 'neutral-5' : 'neutral-3',
        companion('color-4'),
      ),
    );
    vars['--emphasis-rewards-background'] = resolveColor(
      theme,
      mode,
      emphasis(
        'neutral-3',
        'neutral-3',
        atlas ? 'neutral-3' : companion('color-2'),
      ),
    );
    vars['--emphasis-icon-background'] = resolveColor(
      theme,
      mode,
      iconBackground,
    );
    vars['--emphasis-icon-foreground'] = foreground(iconBackground);
    vars['--emphasis-type-background'] = resolveColor(
      theme,
      mode,
      typeBackground,
    );
    vars['--emphasis-type-foreground'] = foreground(typeBackground);
    vars['--navigation-active-background'] = resolveColor(
      theme,
      mode,
      navigationBackground,
    );
    vars['--navigation-active-foreground'] = foreground(navigationBackground);
    if (theme.colorEmphasis < 34 || theme.colorEmphasis > 66) {
      const badgeBackground = emphasis(
        atlas ? 'neutral-4' : 'neutral-3',
        'neutral-3',
        'color-1',
      );
      vars['--option-badge-background'] = resolveColor(
        theme,
        mode,
        badgeBackground,
      );
      vars['--option-badge-foreground'] = foreground(badgeBackground);
    }
  }
  for (const relief of ['raised', 'recessed'] as const) {
    const details = resolveSurfaceDetails(theme, mode, relief);
    vars[`--surface-${relief}-image`] = details.backgroundImage;
    vars[`--surface-${relief}-shadow`] =
      details.shadow === 'none' ? '0 0 0 0 transparent' : details.shadow;
  }
  for (const key of SPACE_KEYS)
    vars[`--space-${key}`] = `${themePx(theme.spacing[key])}px`;
  for (const key of LETTER_SPACING_KEYS)
    vars[`--tracking-${key}`] = `${letterSpacingScale(theme)[key]}em`;
  const textScale = themeText(theme);
  const displayScale = themeDisplay(theme);
  for (const key of SIZE_KEYS) {
    const tracking = (scale: TypeScale) =>
      `${resolveLetterSpacing(theme, key, textLetterSpacingKey(theme, scale, key))}em`;
    vars[`--size-${key}`] = `${themePx(textScale[key].size)}px`;
    vars[`--line-${key}`] = `${themePx(textScale[key].lineHeight)}px`;
    vars[`--letter-spacing-${key}`] = tracking('body');
    vars[`--display-size-${key}`] = `${themePx(displayScale[key].size)}px`;
    vars[`--display-line-${key}`] =
      `${themePx(displayScale[key].lineHeight)}px`;
    vars[`--display-letter-spacing-${key}`] = tracking('display');
  }
  for (const key of RADIUS_KEYS)
    vars[`--radius-${key}`] = `${themePx(theme.radius[key])}px`;
  for (const key of BORDER_KEYS)
    vars[`--border-${key}`] = `${theme.border[key]}px`;
  vars['--border-default-color'] = colors.border;
  for (const key of BORDER_KEYS) {
    const edge = componentBoxShadow({
      borderWidth: theme.border[key],
      borderColor: colors.border,
      borderInset: themeBorderInset(theme, mode, 'neutral-1'),
      shadow: 'none',
    });
    // A zero-width layer can compose with elevation; `none, <shadow>` cannot.
    vars[`--border-shadow-${key}`] =
      edge === 'none' ? '0 0 0 0 transparent' : edge;
  }
  for (const key of FONT_KEYS) {
    vars[`--font-${key}`] = theme.fonts[key].family;
    for (const weight of WEIGHT_KEYS)
      vars[`--weight-${key}-${weight}`] = theme.fonts[key].weights[weight];
  }
  for (const group of colorOptions(theme, mode)) {
    for (const option of group.options)
      vars[`--${option.value === 'none' ? 'color-none' : option.value}`] =
        option.color;
  }
  // Readable text on each color, which `on:<color>` app tokens alias.
  const inks = (['neutral-1', 'neutral-10'] as const).map((key) =>
    resolveColor(theme, mode, key),
  );
  const [darkInk, lightInk] =
    contrastingTextColor(inks[0]) === '#000000' ? [inks[1], inks[0]] : inks;
  for (const key of [...PALETTE_KEYS, ...SEMANTIC_KEYS, ...NEUTRAL_KEYS]) {
    if (!theme.colors[mode][key]) continue;
    vars[`--on-${key}`] = (NEUTRAL_KEYS as readonly string[]).includes(key)
      ? contrastingTextColor(resolveColor(theme, mode, key)) === '#000000'
        ? darkInk
        : lightInk
      : resolveAutomaticForeground(theme, mode, {
          background: key,
          foreground: 'neutral-10',
        });
  }
  for (const key of SHADOW_KEYS)
    vars[`--shadow-${key}`] = resolveShadow(theme, mode, key);
  return {
    ...vars,
    '--cte-canvas': colors.canvas,
    '--cte-surface': colors.surface,
    '--cte-surface-muted': colors.surfaceMuted,
    '--cte-text': colors.text,
    '--cte-text-muted': colors.textMuted,
    '--cte-border': colors.border,
    '--cte-accent': colors.accent,
    '--cte-accent-text': colors.accentText,
    '--cte-danger': colors.danger,
    '--cte-focus': colors.focus,
    '--cte-font': theme.fonts.body.family,
    '--cte-font-size': `${themePx(text.size)}px`,
    '--cte-font-weight': theme.fonts.body.weights.regular,
    '--cte-line-height': `${themePx(text.lineHeight)}px`,
    '--cte-letter-spacing': `${resolveLetterSpacing(theme, textSize)}em`,
    '--cte-detail-font-size': `${themePx(detailText.size)}px`,
    '--cte-detail-line-height': `${themePx(detailText.lineHeight)}px`,
    '--cte-detail-letter-spacing': `${resolveLetterSpacing(theme, detailSize)}em`,
  } as CSSProperties;
}

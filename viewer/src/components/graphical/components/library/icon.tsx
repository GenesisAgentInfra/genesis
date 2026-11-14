'use client';

import {
  createContext,
  createElement,
  useContext,
  useId,
  useMemo,
  type CSSProperties,
  type ReactNode,
  type SVGProps,
} from 'react';
import {
  AtSign,
  Link2,
  MoreHorizontal,
  Sparkles,
  Zap,
  Building2,
  Clock3,
  Volume2,
  VolumeX,
  RotateCcw,
  RotateCw,
  Archive,
  PanelLeft,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  X,
  Info,
  Bold,
  Italic,
  Underline,
  Copy,
  Download,
  FilePlus,
  FolderOpen,
  Printer,
  Save,
  Undo2,
  Redo2,
  ArrowUp,
  CalendarPlus,
  CalendarDays,
  MapPin,
  Tag,
  Package,
  Truck,
  ListOrdered,
  LoaderCircle,
  Timer,
  BookOpen,
  CheckCheck,
  ShieldCheck,
  TrendingUp,
  ArrowDownToLine,
  ArrowRight,
  Award,
  Bell,
  Bookmark,
  CreditCard,
  FileText,
  Folder,
  Gift,
  Globe,
  House,
  Inbox,
  Mailbox,
  Paperclip,
  Pause,
  Pencil,
  Play,
  Search,
  Settings,
  ShoppingBag,
  SlidersHorizontal,
  Stamp,
  Trash2,
  UsersRound,
} from 'lucide-react';
import type { ThemeDefinition } from "../../lib/theme-model";
import {
  iconWeightVariables,
  themeIconWeightVariables,
} from "../../lib/theme-icon-weight";
import { ICON_SEMANTICS } from "../../lib/icon-semantics";
import {
  useThemeIconRenderer,
  type ThemeIconRenderProps,
} from "./icon-renderer";
export {
  IconRendererProvider,
  useThemeIconRenderer,
  type ThemeIconRenderProps,
  type ThemeIconRenderer,
} from "./icon-renderer";

import {
  CatalogIcon,
  catalogIconFamily,
  type CatalogIconName,
} from "./icon-catalog";
import {
  isHugeiconsVariant,
  type HugeiconsVariant,
} from "../../lib/hugeicons-options";

const lucide = {
  home: House,
  folder: Folder,
  team: UsersRound,
  settings: Settings,
  inboxTray: Inbox,
  shoppingBag: ShoppingBag,
  gift: Gift,
  creditCard: CreditCard,
  award: Award,
  pause: Pause,
  play: Play,
  bookmark: Bookmark,
  arrowRight: ArrowRight,
  archive: Archive,
  inbox: ArrowDownToLine,
  adjust: SlidersHorizontal,
  document: FileText,
  search: Search,
  paperclip: Paperclip,
  bell: Bell,
  trash: Trash2,
  stamp: Stamp,
  globe: Globe,
  pencil: Pencil,
  mailbox: Mailbox,
};
const controls = {
  atSign: AtSign,
  link: Link2,
  more: MoreHorizontal,
  sparkles: Sparkles,
  lightning: Zap,
  buildings: Building2,
  clock: Clock3,
  volume: Volume2,
  volumeOff: VolumeX,
  rotateLeft: RotateCcw,
  rotateRight: RotateCw,

  panelLeft: PanelLeft,
  check: Check,
  chevronDown: ChevronDown,
  chevronLeft: ChevronLeft,
  chevronRight: ChevronRight,
  minus: Minus,
  plus: Plus,
  close: X,
  info: Info,
  bold: Bold,
  italic: Italic,
  underline: Underline,
  copy: Copy,
  download: Download,
  filePlus: FilePlus,
  folderOpen: FolderOpen,
  printer: Printer,
  save: Save,
  undo: Undo2,
  redo: Redo2,
  arrowUp: ArrowUp,
  calendarPlus: CalendarPlus,
  calendarDays: CalendarDays,
  mapPin: MapPin,
  tag: Tag,
  package: Package,
  truck: Truck,
  listOrdered: ListOrdered,
  loader: LoaderCircle,
  timer: Timer,
  bookOpen: BookOpen,
  checkCheck: CheckCheck,
  shieldCheck: ShieldCheck,
  trendingUp: TrendingUp,
};
const allIcons = { ...lucide, ...controls };
export type ThemeIconName =
  | keyof typeof allIcons
  | CatalogIconName
  | `hugeicons:${string}`;
export const THEME_ICON_NAMES = Object.keys(lucide) as ThemeIconName[];
export const CONTROL_ICON_NAMES = Object.keys(
  controls,
) as (keyof typeof controls)[];

type IconSettings = {
  family?: ThemeDefinition['iconFamily'];
  variant?: 'filled' | 'outlined';
  weight?: number;
  hugeiconsVariant?: HugeiconsVariant;
};
const IconThemeContext = createContext<IconSettings>({});

/** Reusable theme scope. React context carries the selected artwork through portals. */
export function IconTheme({
  variables,
  children,
}: {
  variables: CSSProperties;
  children: ReactNode;
}) {
  const inherited = useContext(IconThemeContext);
  const tokens = variables as Record<string, string | number | undefined>;
  const requestedFamily = tokens['--theme-icon-family'];
  const requestedVariant = tokens['--theme-icon-style'];
  const family =
    requestedFamily === 'Hugeicons' ||
    requestedFamily === 'Central' ||
    requestedFamily === 'Phosphor' ||
    requestedFamily === 'Lucide'
      ? requestedFamily
      : inherited.family;
  const weight =
    Number(tokens['--theme-icon-weight']) ||
    Number(tokens['--weight-body-regular']) ||
    inherited.weight;
  const variant =
    requestedVariant === 'filled' || requestedVariant === 'outlined'
      ? requestedVariant
      : inherited.variant;
  const requestedHugeicons = tokens['--theme-hugeicons-variant'];
  const hugeiconsVariant = isHugeiconsVariant(requestedHugeicons)
    ? requestedHugeicons
    : inherited.hugeiconsVariant;
  // Theme variables change on every edit; icons follow only these settings.
  const value = useMemo(
    () => ({ family, weight, variant, hugeiconsVariant }),
    [family, weight, variant, hugeiconsVariant],
  );
  return <IconThemeContext value={value}>{children}</IconThemeContext>;
}

const IconNameContext = createContext<
  ((instance: string, name: ThemeIconName) => ThemeIconName) | null
>(null);

/** Optional instance-level name resolution; ordinary icons need no provider. */
export function IconNameProvider({
  resolveName,
  children,
}: {
  resolveName: (instance: string, name: ThemeIconName) => ThemeIconName;
  children: ReactNode;
}) {
  return <IconNameContext value={resolveName}>{children}</IconNameContext>;
}

/** The host owns the actual artwork and forwards SVG identity, styling, and refs. */
export type HostIconProps = SVGProps<SVGSVGElement> & {
  name: ThemeIconName;
  family: ThemeDefinition['iconFamily'];
  variant: 'filled' | 'outlined';
  semantic: boolean;
  weight?: number;
};
export type HostIconRenderer = import('react').ComponentType<HostIconProps>;
const HostIconContext = createContext<HostIconRenderer | null>(null);

/** Supply the app's existing icon component; no artwork is copied into this kit. */
export function HostIconProvider({
  renderIcon,
  children,
}: {
  renderIcon: HostIconRenderer;
  children: ReactNode;
}) {
  return <HostIconContext value={renderIcon}>{children}</HostIconContext>;
}

/** Bundled semantic artwork; return undefined to use the Lucide fallback. */
export type ThemeIconArtwork = (
  props: Omit<ThemeIconRenderProps, 'weight'>,
) => ReactNode | undefined;
const IconArtworkContext = createContext<ThemeIconArtwork | null>(null);

/**
 * Graphical registers its own Central, Phosphor and filled Lucide artwork at
 * its app roots. The editor package never imports that artwork, so installed
 * hosts render catalog Phosphor or an identified Lucide fallback instead.
 */
export function IconArtworkProvider({
  renderArtwork,
  children,
}: {
  renderArtwork: ThemeIconArtwork;
  children: ReactNode;
}) {
  return (
    <IconArtworkContext value={renderArtwork}>{children}</IconArtworkContext>
  );
}

/** True where Graphical's own artwork is registered, so hosted artwork isn't needed. */
export function useHasIconArtwork() {
  return useContext(IconArtworkContext) !== null;
}

/** Decorative artwork; the containing control owns its accessible name. */
export function ThemedIcon({
  name: authoredName,
  family: explicitFamily,
  centralStyle,
  variant,
  weight,
  semantic = false,
  style,
  ...props
}: SVGProps<SVGSVGElement> & {
  name: ThemeIconName;
  family?: ThemeDefinition['iconFamily'];
  centralStyle?: 'filled' | 'outlined';
  variant?: 'filled' | 'outlined';
  weight?: number;
  /** Fixed control meaning; editor icon replacement applies only to decorative icons. */
  semantic?: boolean;
}) {
  const inherited = useContext(IconThemeContext);
  const renderer = useThemeIconRenderer();
  const HostIcon = useContext(HostIconContext);
  const renderArtwork = useContext(IconArtworkContext);
  const family = explicitFamily ?? inherited.family ?? 'Lucide';
  const instance = useId();
  const resolveName = useContext(IconNameContext);
  const name =
    (!semantic && resolveName?.(instance, authoredName)) || authoredName;
  const identity = {
    'data-icon-name': name,
    ...(!semantic && { 'data-icon-instance': instance }),
  };
  const resolvedStyle =
    variant ??
    centralStyle ??
    inherited.variant ??
    (family === 'Central' ? 'filled' : 'outlined');
  const iconStyle = {
    ...(weight !== undefined && {
      ...themeIconWeightVariables({ iconFamily: family, iconWeight: weight }),
      ...iconWeightVariables(weight),
    }),
    ...style,
  } as CSSProperties;
  const customIcon = renderer?.renderIcon({
    'aria-hidden': true,
    ...props,
    ...identity,
    style: iconStyle,
    name,
    family,
    variant: resolvedStyle,
    hugeiconsVariant: inherited.hugeiconsVariant,
    weight: weight ?? inherited.weight,
  });
  if (customIcon !== undefined) return customIcon;
  if (catalogIconFamily(name)) {
    return (
      <CatalogIcon
        name={name as CatalogIconName}
        variant={resolvedStyle}
        weight={weight ?? inherited.weight}
        {...props}
        {...identity}
        style={iconStyle}
      />
    );
  }
  if (HostIcon) {
    return createElement(HostIcon, {
      'aria-hidden': true,
      ...props,
      ...identity,
      name,
      family,
      variant: resolvedStyle,
      semantic,
      weight,
      style: iconStyle,
    });
  }
  if (family === 'Hugeicons' || name.startsWith('hugeicons:')) {
    return (
      <svg
        width={24}
        height={24}
        {...props}
        {...identity}
        style={iconStyle}
        data-icon-family="Hugeicons"
        data-icon-style={resolvedStyle}
        data-icon-unavailable="true"
      >
        <title>Hugeicons catalog is not connected</title>
      </svg>
    );
  }
  const artwork = renderArtwork?.({
    ...props,
    ...identity,
    style: iconStyle,
    name,
    family,
    variant: resolvedStyle,
  });
  if (artwork !== undefined) return artwork;
  const semanticName = name as keyof typeof allIcons;
  if (family === 'Phosphor') {
    return (
      <CatalogIcon
        name={`phosphor:${ICON_SEMANTICS[semanticName].phosphor}`}
        variant={resolvedStyle}
        weight={weight ?? inherited.weight}
        {...props}
        {...identity}
        style={iconStyle}
      />
    );
  }
  const Icon = allIcons[semanticName];
  // Preview vocabulary beyond the named set draws from the free catalog.
  // An app's own glyph can reach the picker as its current value, unmapped.
  if (!Icon && !Object.hasOwn(ICON_SEMANTICS, name))
    return <svg width={24} height={24} {...props} {...identity} style={iconStyle} />;
  if (!Icon) {
    return (
      <CatalogIcon
        name={`lucide:${ICON_SEMANTICS[semanticName].lucide}`}
        variant="outlined"
        weight={weight ?? inherited.weight}
        {...props}
        {...identity}
        data-icon-fallback={
          family !== 'Lucide' || resolvedStyle !== 'outlined'
            ? 'lucide-outlined'
            : undefined
        }
        style={iconStyle}
      />
    );
  }
  // Without registered artwork, preserve the requested tokens and identify
  // the actual fallback artwork honestly.
  const fallback = family !== 'Lucide' || resolvedStyle !== 'outlined';
  return (
    <Icon
      aria-hidden="true"
      strokeWidth="var(--icon-stroke-width, 2)"
      {...props}
      {...identity}
      data-icon-family="Lucide"
      data-icon-style="outlined"
      data-icon-fallback={fallback ? 'lucide-outlined' : undefined}
      data-icon-requested-family={fallback ? family : undefined}
      data-icon-requested-style={fallback ? resolvedStyle : undefined}
      style={iconStyle}
    />
  );
}

import { HUGEICONS_NAMES } from "./hugeicons-names";
/**
 * Graphical's semantic icon vocabulary, with the names other libraries use
 * for the same meaning. Used to preview an icon-family swap on a live app and
 * to describe the source rewrite during adoption.
 */
type IconSemantic = {
  /** Normalized phrases from other libraries that mean this icon. */
  synonyms: readonly string[];
  lucide: string;
  phosphor: string;
};

export const ICON_SEMANTICS = {
  home: { synonyms: ['home', 'house'], lucide: 'House', phosphor: 'House' },
  folder: { synonyms: ['folder'], lucide: 'Folder', phosphor: 'Folder' },
  team: {
    synonyms: [
      'users',
      'user group',
      'team',
      'people',
      'group',
      'participants',
    ],
    lucide: 'UsersRound',
    phosphor: 'Users',
  },
  settings: {
    synonyms: [
      'settings',
      'gear',
      'cog',
      'cog tooth',
      'cog 6 tooth',
      'cog 8 tooth',
      'preferences',
    ],
    lucide: 'Settings',
    phosphor: 'Gear',
  },
  inboxTray: {
    synonyms: ['inbox', 'tray', 'inbox stack'],
    lucide: 'Inbox',
    phosphor: 'Tray',
  },
  shoppingBag: {
    synonyms: ['shopping bag', 'bag', 'shopping'],
    lucide: 'ShoppingBag',
    phosphor: 'ShoppingBag',
  },
  gift: { synonyms: ['gift', 'present'], lucide: 'Gift', phosphor: 'Gift' },
  creditCard: {
    synonyms: ['credit card', 'card', 'payment', 'billing'],
    lucide: 'CreditCard',
    phosphor: 'CreditCard',
  },
  award: {
    synonyms: ['award', 'trophy', 'medal', 'badge'],
    lucide: 'Award',
    phosphor: 'Medal',
  },
  pause: {
    synonyms: ['pause', 'player pause'],
    lucide: 'Pause',
    phosphor: 'Pause',
  },
  play: { synonyms: ['play', 'player play'], lucide: 'Play', phosphor: 'Play' },
  bookmark: {
    synonyms: ['bookmark', 'saved'],
    lucide: 'Bookmark',
    phosphor: 'BookmarkSimple',
  },
  arrowRight: {
    synonyms: [
      'arrow right',
      'arrow forward',
      'right arrow',
      'arrow narrow right',
    ],
    lucide: 'ArrowRight',
    phosphor: 'ArrowRight',
  },
  archive: {
    synonyms: ['archive', 'archive box'],
    lucide: 'Archive',
    phosphor: 'Archive',
  },
  inbox: {
    synonyms: ['arrow down to line', 'arrow line down', 'arrow bar to down'],
    lucide: 'ArrowDownToLine',
    phosphor: 'ArrowLineDown',
  },
  adjust: {
    synonyms: [
      'adjustments',
      'adjustments horizontal',
      'sliders',
      'sliders horizontal',
      'tune',
      'options',
    ],
    lucide: 'SlidersHorizontal',
    phosphor: 'SlidersHorizontal',
  },
  document: {
    synonyms: [
      'document',
      'document text',
      'file text',
      'description',
      'notes',
      'article',
      'page',
    ],
    lucide: 'FileText',
    phosphor: 'FileText',
  },
  search: {
    synonyms: ['search', 'magnifying glass', 'magnifier', 'find', 'zoom'],
    lucide: 'Search',
    phosphor: 'MagnifyingGlass',
  },
  paperclip: {
    synonyms: ['paperclip', 'paper clip', 'attachment', 'attach'],
    lucide: 'Paperclip',
    phosphor: 'Paperclip',
  },
  bell: {
    synonyms: ['bell', 'notification', 'notifications', 'alert'],
    lucide: 'Bell',
    phosphor: 'Bell',
  },
  trash: {
    synonyms: ['trash', 'delete', 'bin', 'trash can', 'remove'],
    lucide: 'Trash2',
    phosphor: 'Trash',
  },
  stamp: { synonyms: ['stamp'], lucide: 'Stamp', phosphor: 'Stamp' },
  globe: {
    synonyms: ['globe', 'world', 'language', 'globe alt', 'earth', 'public'],
    lucide: 'Globe',
    phosphor: 'Globe',
  },
  pencil: {
    synonyms: ['pencil', 'edit', 'pencil square', 'pen', 'write', 'create'],
    lucide: 'Pencil',
    phosphor: 'PencilSimple',
  },
  mailbox: {
    synonyms: ['mailbox'],
    lucide: 'Mailbox',
    phosphor: 'Mailbox',
  },
  panelLeft: {
    synonyms: [
      'panel left',
      'sidebar',
      'layout sidebar',
      'sidebar simple',
      'bars 3',
    ],
    lucide: 'PanelLeft',
    phosphor: 'SidebarSimple',
  },
  check: {
    synonyms: ['check', 'checkmark', 'done', 'tick', 'check circle'],
    lucide: 'Check',
    phosphor: 'Check',
  },
  chevronDown: {
    synonyms: [
      'chevron down',
      'caret down',
      'angle down',
      'expand more',
      'chevron up down',
      'mini chevron down',
    ],
    lucide: 'ChevronDown',
    phosphor: 'CaretDown',
  },
  chevronLeft: {
    synonyms: [
      'chevron left',
      'caret left',
      'angle left',
      'arrow back ios',
      'navigate before',
    ],
    lucide: 'ChevronLeft',
    phosphor: 'CaretLeft',
  },
  chevronRight: {
    synonyms: [
      'chevron right',
      'caret right',
      'angle right',
      'arrow forward ios',
      'navigate next',
    ],
    lucide: 'ChevronRight',
    phosphor: 'CaretRight',
  },
  minus: {
    synonyms: ['minus', 'subtract', 'remove line', 'dash'],
    lucide: 'Minus',
    phosphor: 'Minus',
  },
  plus: {
    synonyms: ['plus', 'add', 'new', 'create new', 'plus small'],
    lucide: 'Plus',
    phosphor: 'Plus',
  },
  close: {
    synonyms: ['x', 'x mark', 'close', 'times', 'cross', 'dismiss', 'cancel'],
    lucide: 'X',
    phosphor: 'X',
  },
  info: {
    synonyms: [
      'info',
      'information',
      'information circle',
      'info circle',
    ],
    lucide: 'Info',
    phosphor: 'Info',
  },
  bold: {
    synonyms: ['bold', 'text b', 'format bold'],
    lucide: 'Bold',
    phosphor: 'TextB',
  },
  italic: {
    synonyms: ['italic', 'text italic', 'format italic'],
    lucide: 'Italic',
    phosphor: 'TextItalic',
  },
  underline: {
    synonyms: ['underline', 'text underline', 'format underlined'],
    lucide: 'Underline',
    phosphor: 'TextUnderline',
  },
  copy: {
    synonyms: [
      'copy',
      'duplicate',
      'document duplicate',
      'clipboard',
      'content copy',
    ],
    lucide: 'Copy',
    phosphor: 'Copy',
  },
  download: {
    synonyms: [
      'download',
      'arrow down tray',
      'download simple',
      'cloud download',
    ],
    lucide: 'Download',
    phosphor: 'DownloadSimple',
  },
  filePlus: {
    synonyms: ['file plus', 'document plus', 'file add', 'note add'],
    lucide: 'FilePlus',
    phosphor: 'FilePlus',
  },
  folderOpen: {
    synonyms: ['folder open'],
    lucide: 'FolderOpen',
    phosphor: 'FolderOpen',
  },
  printer: {
    synonyms: ['printer', 'print'],
    lucide: 'Printer',
    phosphor: 'Printer',
  },
  save: {
    synonyms: ['save', 'floppy disk', 'floppy'],
    lucide: 'Save',
    phosphor: 'FloppyDisk',
  },
  undo: {
    synonyms: ['undo', 'arrow uturn left'],
    lucide: 'Undo2',
    phosphor: 'ArrowCounterClockwise',
  },
  redo: {
    synonyms: ['redo', 'arrow uturn right'],
    lucide: 'Redo2',
    phosphor: 'ArrowClockwise',
  },
  arrowUp: {
    synonyms: ['arrow up', 'arrow upward', 'arrow narrow up'],
    lucide: 'ArrowUp',
    phosphor: 'ArrowUp',
  },
  calendarPlus: {
    synonyms: ['calendar plus', 'calendar add', 'event add'],
    lucide: 'CalendarPlus',
    phosphor: 'CalendarPlus',
  },
  calendarDays: {
    synonyms: [
      'calendar',
      'calendar days',
      'calendar blank',
      'event',
      'date',
      'calendar today',
    ],
    lucide: 'CalendarDays',
    phosphor: 'CalendarBlank',
  },
  mapPin: {
    synonyms: ['map pin', 'location', 'pin', 'place', 'location marker'],
    lucide: 'MapPin',
    phosphor: 'MapPin',
  },
  tag: {
    synonyms: ['tag', 'label', 'price tag'],
    lucide: 'Tag',
    phosphor: 'Tag',
  },
  package: {
    synonyms: ['package', 'box', 'cube', 'parcel', 'inventory'],
    lucide: 'Package',
    phosphor: 'Package',
  },
  truck: {
    synonyms: ['truck', 'delivery', 'shipping', 'local shipping'],
    lucide: 'Truck',
    phosphor: 'Truck',
  },
  listOrdered: {
    synonyms: [
      'list ordered',
      'numbered list',
      'list numbers',
      'format list numbered',
    ],
    lucide: 'ListOrdered',
    phosphor: 'ListNumbers',
  },
  loader: {
    synonyms: [
      'loader',
      'spinner',
      'loading',
      'circle notch',
      'loader circle',
    ],
    lucide: 'LoaderCircle',
    phosphor: 'CircleNotch',
  },
  timer: {
    synonyms: ['timer', 'stopwatch', 'schedule', 'history'],
    lucide: 'Timer',
    phosphor: 'Timer',
  },
  bookOpen: {
    synonyms: ['book open', 'book', 'docs', 'documentation', 'menu book'],
    lucide: 'BookOpen',
    phosphor: 'BookOpen',
  },
  checkCheck: {
    synonyms: ['check check', 'checks', 'done all', 'double check'],
    lucide: 'CheckCheck',
    phosphor: 'Checks',
  },
  shieldCheck: {
    synonyms: [
      'shield check',
      'shield',
      'security',
      'verified',
      'verified user',
    ],
    lucide: 'ShieldCheck',
    phosphor: 'ShieldCheck',
  },
  trendingUp: {
    synonyms: [
      'trending up',
      'trend up',
      'arrow trending up',
      'chart line up',
    ],
    lucide: 'TrendingUp',
    phosphor: 'TrendUp',
  },
  atSign: {
    synonyms: ['at sign', 'at', 'mention'],
    lucide: 'AtSign',
    phosphor: 'At',
  },
  link: {
    synonyms: ['link', 'link 2', 'chain link'],
    lucide: 'Link2',
    phosphor: 'Link',
  },
  more: {
    synonyms: ['more', 'more horizontal', 'ellipsis', 'dots three'],
    lucide: 'MoreHorizontal',
    phosphor: 'DotsThree',
  },
  sparkles: {
    synonyms: ['sparkles', 'sparkle', 'insights'],
    lucide: 'Sparkles',
    phosphor: 'Sparkle',
  },
  lightning: {
    synonyms: ['zap', 'lightning', 'lightning bolt', 'automation'],
    lucide: 'Zap',
    phosphor: 'Lightning',
  },
  buildings: {
    synonyms: ['building', 'buildings', 'building 2', 'company', 'companies'],
    lucide: 'Building2',
    phosphor: 'Buildings',
  },
  clock: {
    synonyms: ['clock', 'clock 3', 'time'],
    lucide: 'Clock3',
    phosphor: 'Clock',
  },
  volume: {
    synonyms: ['volume', 'volume 2', 'speaker high', 'audio'],
    lucide: 'Volume2',
    phosphor: 'SpeakerHigh',
  },
  volumeOff: {
    synonyms: ['volume x', 'volume off', 'speaker x', 'mute'],
    lucide: 'VolumeX',
    phosphor: 'SpeakerX',
  },
  rotateLeft: {
    synonyms: ['rotate ccw', 'rotate left', 'arrow counter clockwise'],
    lucide: 'RotateCcw',
    phosphor: 'ArrowCounterClockwise',
  },
  rotateRight: {
    synonyms: ['rotate cw', 'rotate right', 'arrow clockwise'],
    lucide: 'RotateCw',
    phosphor: 'ArrowClockwise',
  },
  user: {
    synonyms: ['user', 'person', 'profile', 'account', 'user round', 'user circle'],
    lucide: 'User',
    phosphor: 'User',
  },
  userPlus: {
    synonyms: ['user plus', 'user add', 'add user', 'invite'],
    lucide: 'UserPlus',
    phosphor: 'UserPlus',
  },
  mail: {
    synonyms: ['mail', 'envelope', 'email'],
    lucide: 'Mail',
    phosphor: 'Envelope',
  },
  send: {
    synonyms: ['send', 'paper plane', 'paper plane tilt', 'sent'],
    lucide: 'Send',
    phosphor: 'PaperPlaneTilt',
  },
  message: {
    synonyms: ['message', 'message square', 'message circle', 'chat', 'chat circle', 'comment', 'comments'],
    lucide: 'MessageSquare',
    phosphor: 'ChatCircle',
  },
  file: {
    synonyms: ['file', 'file blank'],
    lucide: 'File',
    phosphor: 'File',
  },
  camera: {
    synonyms: ['camera'],
    lucide: 'Camera',
    phosphor: 'Camera',
  },
  image: {
    synonyms: ['image', 'images', 'photo', 'picture'],
    lucide: 'Image',
    phosphor: 'Image',
  },
  video: {
    synonyms: ['video', 'video camera', 'film'],
    lucide: 'Video',
    phosphor: 'VideoCamera',
  },
  arrowLeft: {
    synonyms: ['arrow left', 'back'],
    lucide: 'ArrowLeft',
    phosphor: 'ArrowLeft',
  },
  lock: {
    synonyms: ['lock', 'lock keyhole', 'locked', 'padlock', 'lock closed'],
    lucide: 'Lock',
    phosphor: 'Lock',
  },
  unlock: {
    synonyms: ['unlock', 'lock open', 'lock keyhole open', 'unlocked'],
    lucide: 'LockOpen',
    phosphor: 'LockOpen',
  },
  key: {
    synonyms: ['key', 'key round', 'password'],
    lucide: 'Key',
    phosphor: 'Key',
  },
  eye: {
    synonyms: ['eye', 'view', 'show', 'visible'],
    lucide: 'Eye',
    phosphor: 'Eye',
  },
  eyeOff: {
    synonyms: ['eye off', 'eye slash', 'hide', 'hidden', 'view off'],
    lucide: 'EyeOff',
    phosphor: 'EyeSlash',
  },
  star: {
    synonyms: ['star'],
    lucide: 'Star',
    phosphor: 'Star',
  },
  heart: {
    synonyms: ['heart', 'favorite', 'favourite', 'like'],
    lucide: 'Heart',
    phosphor: 'Heart',
  },
  arrowDown: {
    synonyms: ['arrow down'],
    lucide: 'ArrowDown',
    phosphor: 'ArrowDown',
  },
  share: {
    synonyms: ['share', 'share network'],
    lucide: 'Share2',
    phosphor: 'ShareNetwork',
  },
  upload: {
    synonyms: ['upload', 'upload simple', 'arrow up tray'],
    lucide: 'Upload',
    phosphor: 'UploadSimple',
  },
  cloudUpload: {
    synonyms: ['cloud upload', 'cloud arrow up'],
    lucide: 'CloudUpload',
    phosphor: 'CloudArrowUp',
  },
  cloud: {
    synonyms: ['cloud'],
    lucide: 'Cloud',
    phosphor: 'Cloud',
  },
  externalLink: {
    synonyms: ['external link', 'arrow square out', 'open in new', 'link external', 'arrow top right on square'],
    lucide: 'ExternalLink',
    phosphor: 'ArrowSquareOut',
  },
  filter: {
    synonyms: ['filter', 'funnel', 'list filter'],
    lucide: 'ListFilter',
    phosphor: 'Funnel',
  },
  sort: {
    synonyms: ['sort', 'arrow up down', 'arrows up down', 'arrows down up'],
    lucide: 'ArrowUpDown',
    phosphor: 'ArrowsDownUp',
  },
  menu: {
    synonyms: ['menu', 'hamburger', 'bars'],
    lucide: 'Menu',
    phosphor: 'List',
  },
  grid: {
    synonyms: ['grid', 'layout grid', 'squares four', 'apps', 'view grid'],
    lucide: 'LayoutGrid',
    phosphor: 'SquaresFour',
  },
  list: {
    synonyms: ['list', 'list bullets', 'view list', 'rows'],
    lucide: 'List',
    phosphor: 'ListBullets',
  },
  table: {
    synonyms: ['table', 'table cells'],
    lucide: 'Table2',
    phosphor: 'Table',
  },
  database: {
    synonyms: ['database', 'circle stack'],
    lucide: 'Database',
    phosphor: 'Database',
  },
  server: {
    synonyms: ['server', 'hard drives', 'server stack'],
    lucide: 'Server',
    phosphor: 'HardDrives',
  },
  code: {
    synonyms: ['code', 'code bracket', 'code xml', 'brackets'],
    lucide: 'Code',
    phosphor: 'Code',
  },
  terminal: {
    synonyms: ['terminal', 'command line'],
    lucide: 'Terminal',
    phosphor: 'Terminal',
  },
  chart: {
    synonyms: ['chart', 'chart column', 'chart bar', 'bar chart', 'analytics'],
    lucide: 'ChartColumn',
    phosphor: 'ChartBar',
  },
  pieChart: {
    synonyms: ['pie chart', 'chart pie'],
    lucide: 'ChartPie',
    phosphor: 'ChartPie',
  },
  activity: {
    synonyms: ['activity', 'pulse'],
    lucide: 'Activity',
    phosphor: 'Pulse',
  },
  dollar: {
    synonyms: ['dollar', 'dollar sign', 'currency dollar', 'money'],
    lucide: 'DollarSign',
    phosphor: 'CurrencyDollar',
  },
  receipt: {
    synonyms: ['receipt', 'invoice', 'bill'],
    lucide: 'Receipt',
    phosphor: 'Receipt',
  },
  chevronUp: {
    synonyms: ['chevron up', 'caret up'],
    lucide: 'ChevronUp',
    phosphor: 'CaretUp',
  },
  alertTriangle: {
    synonyms: ['triangle alert', 'alert triangle', 'warning', 'exclamation triangle'],
    lucide: 'TriangleAlert',
    phosphor: 'Warning',
  },
  alertCircle: {
    synonyms: ['circle alert', 'alert circle', 'warning circle', 'exclamation circle', 'error'],
    lucide: 'CircleAlert',
    phosphor: 'WarningCircle',
  },
  help: {
    synonyms: ['help', 'circle help', 'circle question mark', 'question', 'question mark circle'],
    lucide: 'CircleQuestionMark',
    phosphor: 'Question',
  },
  refresh: {
    synonyms: ['refresh', 'refresh cw', 'arrows clockwise', 'sync', 'reload', 'arrow path'],
    lucide: 'RefreshCw',
    phosphor: 'ArrowsClockwise',
  },
  logOut: {
    synonyms: ['log out', 'logout', 'sign out'],
    lucide: 'LogOut',
    phosphor: 'SignOut',
  },
  logIn: {
    synonyms: ['log in', 'login', 'sign in'],
    lucide: 'LogIn',
    phosphor: 'SignIn',
  },
  sun: {
    synonyms: ['sun', 'light mode'],
    lucide: 'Sun',
    phosphor: 'Sun',
  },
  moon: {
    synonyms: ['moon', 'dark mode'],
    lucide: 'Moon',
    phosphor: 'Moon',
  },
  hash: {
    synonyms: ['hash', 'hashtag', 'number sign'],
    lucide: 'Hash',
    phosphor: 'Hash',
  },
  type: {
    synonyms: ['type', 'text t', 'text', 'case sensitive', 'text font'],
    lucide: 'Type',
    phosphor: 'TextT',
  },
  phone: {
    synonyms: ['phone', 'call', 'telephone'],
    lucide: 'Phone',
    phosphor: 'Phone',
  },
} as const satisfies Record<string, IconSemantic>;

export type SemanticIconName = keyof typeof ICON_SEMANTICS;

// Library prefixes are only removed before an uppercase letter, e.g. FiHome.
const PREFIX =
  /^(?:Icon|Fi|Hi2|Hi|Md|Io5|Io|Fa6|Fa|Tb|Pi|Lu|Bi|Bx|Bxs|Ri|Bs|Ai|Gi|Go|Ci|Cg|Sl|Vsc|Tfi|Rx|Gr|Im|Ti|Wi|Di|Si|Lia|Fc)(?=[A-Z])/;
const SUFFIX =
  /(?:Icon|Outlined|Outline|Solid|Filled|Fill|Bold|Regular|Light|Thin|Duotone|Rounded|Sharp|Mini|Micro|TwoTone)$/;
const MODIFIERS = new Set([
  'circle',
  'square',
  'box',
  'small',
  'big',
  'alt',
  'simple',
  'round',
  'rounded',
  'outline',
  'fill',
  'filled',
  'mini',
  'micro',
  'sharp',
  'line',
  'solid',
]);

/** Library or component name → space-separated lowercase words. */
export function normalizeIconName(name: string): string {
  let text = name.trim().replace(/^lucide-/, '');
  if (/^[a-z0-9]+(?:[-_][a-z0-9]+)*$/.test(text))
    return text.replace(/[-_]+/g, ' ').replace(/\s*\d+$/, '');
  text = text.replace(PREFIX, '');
  for (let previous = ''; previous !== text;) {
    previous = text;
    text = text.replace(SUFFIX, '').replace(/\d+$/, '');
  }
  return text
    .replace(/([a-z])([A-Z0-9])/g, '$1 $2')
    .replace(/([0-9])([A-Za-z])/g, '$1 $2')
    .replace(/([A-Z])([A-Z][a-z])/g, '$1 $2')
    .toLowerCase()
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const BY_PHRASE = new Map<string, SemanticIconName>(
  (Object.keys(ICON_SEMANTICS) as SemanticIconName[]).flatMap((key) =>
    ICON_SEMANTICS[key].synonyms.map((phrase) => [phrase, key] as const),
  ),
);

/** Match a library or component icon name to Graphical's vocabulary. */
export function semanticIconName(name: string): SemanticIconName | null {
  const phrase = normalizeIconName(name);
  if (!phrase) return null;
  const direct = BY_PHRASE.get(phrase);
  if (direct) return direct;
  const withoutDigits = phrase
    .replace(/\b\d+\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const core = withoutDigits
    .split(' ')
    .filter((word) => !MODIFIERS.has(word))
    .join(' ');
  return BY_PHRASE.get(withoutDigits) ?? BY_PHRASE.get(core) ?? null;
}

/** The replacement component in a Graphical icon family. */
export function iconFamilyComponent(
  name: SemanticIconName,
  family: 'Lucide' | 'Phosphor' | 'Central' | 'Hugeicons',
): { package: string; component: string; glyph?: string } {
  if (family === 'Hugeicons')
    return {
      package: '@hugeicons/react',
      component: 'HugeiconsIcon',
      glyph: HUGEICONS_NAMES[name],
    };
  if (family === 'Phosphor')
    return {
      package: '@phosphor-icons/react',
      component: ICON_SEMANTICS[name].phosphor,
    };
  // Central is licensed; adoption uses the app's installed Central package when
  // present and otherwise this documented free fallback.
  return { package: 'lucide-react', component: ICON_SEMANTICS[name].lucide };
}

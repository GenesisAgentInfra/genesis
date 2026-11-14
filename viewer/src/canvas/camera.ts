import { HEAD_H, flowIdOf, type Atlas, type AtlasNode } from "@/atlas/build"

/**
 * Where the camera looks. A shot names what should be in frame; `viewOf` works out the
 * viewport that shows it on the reader's screen: under the headline, beside the panel when
 * it is up, at a size whose words still read. Nothing here moves anything; whoever holds
 * the canvas sends the viewport to it.
 */

export interface Box {
  x: number
  y: number
  width: number
  height: number
}
export interface Viewport {
  x: number
  y: number
  zoom: number
}
/** The screen the map is read on. */
export interface Screen {
  width: number
  height: number
  /** How tall the headline stands over the map. */
  headline: number
  /** No room for the panel beside the map: it comes up from below instead. */
  narrow: boolean
}

export type Shot =
  /** Where the reader is: the whole map, or the open module, from its top; what the
   *  panel is about stays in view. */
  | { of: "place" }
  /** One flow of the open module. */
  | { of: "flow"; flowId: string }
  /** Some steps, whole and centred. */
  | { of: "steps"; ids: string[] }
  /** One step, at walking distance. */
  | { of: "step"; id: string }

/** What is on the canvas and on the screen as the shot is taken. */
export interface Scene {
  atlas: Atlas
  /** The module opened. */
  focused?: string
  /** The panel is up; `subject` is the node on the map it is about. */
  panel: boolean
  subject?: string
  screen: Screen
}

/** The panel's width beside the map. */
export const PANEL_W = 420
/** The most the canvas zooms in, so a small map does not make its cards oversized. */
export const MAX_ZOOM = 1.6
/** The size the map is laid out to be read at across the screen. */
const READ_ZOOM = 0.8
/** The least the whole map or a module is framed at, so its words stay readable: a map
 *  wider than that runs on past the right edge and is reached by panning. */
const READ_FLOOR = 0.66
/** Without room beside the panel there is no size that reads: the map just fits. */
const NARROW_FLOOR = 0.05
/** The least some steps asked for by name are framed at. */
const STEPS_FLOOR = 0.5
/** A walk follows its flow from this close. */
const WALK_ZOOM = 0.85
/** A flow this near its module's top is framed with the module's name over it. */
const NAME_REACH = HEAD_H + 80
/** The glide from one place to the next. */
export const GLIDE_MS = 520
/** One press of a zoom button. */
export const ZOOM_MS = 200
export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

/** How wide the map may run, so its modules fill the screen at reading size. */
export const readingSpan = (width: number) =>
  Math.max(Math.floor((width - 84) / READ_ZOOM / 20) * 20, 880)

/** The part of the screen the map is read in, between the header, toolbar and panel. */
export function readingArea(screen: Screen, panel: boolean): Box {
  const { narrow, width, height } = screen
  const inset = narrow ? 12 : 16
  const top = inset + screen.headline + (narrow ? 16 : 24)
  const right = narrow ? 12 : panel ? PANEL_W + 40 : inset
  const bottom = 64 + (narrow && panel ? height * 0.52 : 0)
  return {
    x: inset,
    y: top,
    width: Math.max(width - inset - right, 80),
    height: Math.max(height - top - bottom, 1),
  }
}

/** Where a node sits on the map, from the layout itself: no waiting to be measured. */
function boxOf(node: AtlasNode): Box {
  const step = node.type === "step" ? node : undefined
  return {
    x: node.position.x,
    y: node.position.y,
    width: step ? step.data.width : (node.width ?? 0),
    height: step ? step.data.slot : (node.height ?? 0),
  }
}
function around(boxes: Box[]): Box | undefined {
  if (!boxes.length) return undefined
  const x = Math.min(...boxes.map((box) => box.x))
  const y = Math.min(...boxes.map((box) => box.y))
  return {
    x,
    y,
    width: Math.max(...boxes.map((box) => box.x + box.width)) - x,
    height: Math.max(...boxes.map((box) => box.y + box.height)) - y,
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max))
}

/** Where a manual pan can settle at its current zoom. */
export function settlePan(view: Viewport, scene: Scene): Viewport {
  const bounds = around(scene.atlas.nodes.map(boxOf))
  if (!bounds) return view
  const area = readingArea(scene.screen, scene.panel)
  const { zoom } = view
  const spareX = area.width - bounds.width * zoom
  const spareY = area.height - bounds.height * zoom
  const left = area.x - bounds.x * zoom
  const top = area.y - bounds.y * zoom
  const x = spareX >= 0 ? left + spareX / 2 : clamp(view.x, left + spareX, left)
  const y = spareY >= 0 ? top : clamp(view.y, top + spareY, top)
  const bounded = { x, y, zoom }

  // The outer rectangle can contain empty space between modules. In that case,
  // bring the closest readable card into view.
  let nearest = bounded
  let distance = Infinity
  for (const node of scene.atlas.nodes) {
    if (node.type === "module" || node.type === "flow" || node.type === "box")
      continue
    const box = boxOf(node)
    const cardLeft = box.x * zoom
    const cardTop = box.y * zoom
    const cardWidth = box.width * zoom
    const cardHeight = box.height * zoom
    const visibleWidth =
      Math.min(x + cardLeft + cardWidth, area.x + area.width) -
      Math.max(x + cardLeft, area.x)
    const visibleHeight =
      Math.min(y + cardTop + cardHeight, area.y + area.height) -
      Math.max(y + cardTop, area.y)
    if (
      visibleWidth >= Math.min(cardWidth / 2, area.width, 48) &&
      visibleHeight >= Math.min(cardHeight / 2, area.height, 24)
    )
      return bounded

    const left = area.x - cardLeft
    const right = left + area.width - cardWidth
    const top = area.y - cardTop
    const bottom = top + area.height - cardHeight
    const nextX = clamp(x, Math.min(left, right), Math.max(left, right))
    const nextY = clamp(y, Math.min(top, bottom), Math.max(top, bottom))
    const offset = Math.hypot(nextX - x, nextY - y)
    if (offset < distance) {
      nearest = { x: nextX, y: nextY, zoom }
      distance = offset
    }
  }
  return nearest
}

/**
 * The viewport that frames `bounds` in `area`. Read from the top, it fits across only and
 * starts under the headline: a long map runs on down the canvas at a size that reads, and
 * its height never shrinks it. Otherwise it fits both ways, centred. `reveal` is something
 * inside that must end up in view.
 */
function frame(
  bounds: Box,
  area: Box,
  fit: { min: number; fromTop?: boolean; reveal?: Box }
): Viewport {
  const across = area.width / bounds.width
  const zoom = Math.min(
    MAX_ZOOM,
    Math.max(
      fit.min,
      fit.fromTop ? across : Math.min(across, area.height / bounds.height)
    )
  )
  const fitsAcross = bounds.width * zoom <= area.width
  const fitsDown = !fit.fromTop && bounds.height * zoom <= area.height
  let x = fitsAcross
    ? area.x + (area.width - bounds.width * zoom) / 2 - bounds.x * zoom
    : area.x - bounds.x * zoom
  let y = fitsDown
    ? area.y + (area.height - bounds.height * zoom) / 2 - bounds.y * zoom
    : area.y - bounds.y * zoom
  const { reveal } = fit
  // Something lower down than the screen shows comes up to the middle of it.
  if (reveal && (reveal.y + reveal.height) * zoom + y > area.y + area.height)
    y =
      area.y +
      Math.max(0, (area.height - reveal.height * zoom) / 2) -
      reveal.y * zoom
  // A map wider than the screen at its least size pans across to it.
  if (reveal && !fitsAcross) {
    const margin = 24
    const right = area.x + area.width - margin
    if ((reveal.x + reveal.width) * zoom + x > right)
      x = right - (reveal.x + reveal.width) * zoom
    if (reveal.x * zoom + x < area.x + margin)
      x = area.x + margin - reveal.x * zoom
  }
  return { x, y, zoom }
}

/** The viewport that shows `shot`; nothing when what it names is not on the map. */
export function viewOf(shot: Shot, scene: Scene): Viewport | undefined {
  const { atlas, screen } = scene
  const area = readingArea(screen, scene.panel)
  const floor = screen.narrow ? NARROW_FLOOR : READ_FLOOR
  const find = (id?: string) => {
    const node = id ? atlas.nodes.find((item) => item.id === id) : undefined
    return node && boxOf(node)
  }
  switch (shot.of) {
    case "place": {
      const bounds = find(scene.focused) ?? around(atlas.nodes.map(boxOf))
      return (
        bounds &&
        frame(bounds, area, {
          min: floor,
          fromTop: true,
          reveal: scene.panel ? find(scene.subject) : undefined,
        })
      )
    }
    case "flow": {
      const module = find(scene.focused)
      const bounds =
        around(
          atlas.nodes
            .filter((node) => flowIdOf(node) === shot.flowId)
            .map(boxOf)
        ) ?? module
      if (!bounds) return undefined
      const under = module ? bounds.y - module.y : Infinity
      return frame(
        // At the top of its module, the module's name comes along.
        module && under < NAME_REACH
          ? {
              x: module.x,
              y: module.y,
              width: bounds.width + bounds.x - module.x,
              height: bounds.height + under,
            }
          : bounds,
        area,
        { min: floor, fromTop: true }
      )
    }
    case "steps": {
      const ids = new Set(shot.ids)
      const bounds = around(
        atlas.nodes.filter((node) => ids.has(node.id)).map(boxOf)
      )
      return bounds && frame(bounds, area, { min: STEPS_FLOOR })
    }
    case "step": {
      const box = find(shot.id)
      if (!box) return undefined
      // Beside the panel the step sits in the middle; over a panel that came up from
      // below, high enough for its name to stay clear.
      const height = screen.narrow ? Math.min(area.height, 560) : area.height
      return {
        x:
          area.x +
          Math.max(0, (area.width - box.width * WALK_ZOOM) / 2) -
          box.x * WALK_ZOOM,
        y:
          area.y +
          Math.max(0, (height - box.height * WALK_ZOOM) / 2) -
          box.y * WALK_ZOOM,
        zoom: WALK_ZOOM,
      }
    }
  }
}

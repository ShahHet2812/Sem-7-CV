import { bboxToScreen, toScreen, type Rect } from '@/lib/geometry'
import { classColor } from '@/lib/utils'
import type { BBox, DetectionItem, Point, Zone } from '@/types/api'

export interface DraftPolygon {
  points: Point[]
  closed: boolean
  color: string
}

function withAlpha(hex: string, alpha: number): string {
  const a = Math.round(alpha * 255)
    .toString(16)
    .padStart(2, '0')
  return `${hex.slice(0, 7)}${a}`
}

export function drawZones(ctx: CanvasRenderingContext2D, zones: Zone[], rect: Rect, highlightId?: string | null) {
  for (const z of zones) {
    if (z.polygon.length < 3) continue
    const pts = z.polygon.map((p) => toScreen(p, rect))
    const highlight = z.id === highlightId
    ctx.beginPath()
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
    ctx.closePath()
    ctx.fillStyle = withAlpha(z.color, highlight ? 0.22 : z.enabled ? 0.12 : 0.05)
    ctx.fill()
    ctx.setLineDash(z.enabled ? [] : [6, 4])
    ctx.lineWidth = highlight ? 3 : 2
    ctx.strokeStyle = withAlpha(z.color, z.enabled ? 1 : 0.6)
    ctx.stroke()
    ctx.setLineDash([])
    const top = pts.reduce((a, b) => (b[1] < a[1] ? b : a))
    label(ctx, z.name + (z.enabled ? '' : ' (disabled)'), top[0], top[1] - 4, z.color, '#04131a')
  }
}

function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, bg: string, fg: string) {
  ctx.font = '600 11px Inter, system-ui, sans-serif'
  const w = ctx.measureText(text).width + 8
  const h = 16
  const lx = Math.max(0, Math.min(x, ctx.canvas.width / (window.devicePixelRatio || 1) - w))
  const ly = Math.max(0, y - h)
  ctx.fillStyle = bg
  ctx.fillRect(lx, ly, w, h)
  ctx.fillStyle = fg
  ctx.fillText(text, lx + 4, ly + 12)
}

export function drawDetections(
  ctx: CanvasRenderingContext2D,
  detections: DetectionItem[],
  rect: Rect,
  opts: { boxes: boolean; labels: boolean },
) {
  for (const d of detections) {
    const r = bboxToScreen(d.bbox, rect)
    const color = classColor(d.class_name)
    if (opts.boxes) {
      ctx.lineWidth = 2
      ctx.strokeStyle = color
      ctx.strokeRect(r.x, r.y, r.width, r.height)
      // Anchor point used for zone membership (bottom-center).
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(r.x + r.width / 2, r.y + r.height, 3, 0, Math.PI * 2)
      ctx.fill()
    }
    if (opts.labels) {
      const text = `${d.class_name}${d.track_id != null ? ` #${d.track_id}` : ''} ${(d.confidence * 100).toFixed(0)}%`
      label(ctx, text, r.x, r.y, color, '#04131a')
    }
  }
}

export function drawHighlightBox(ctx: CanvasRenderingContext2D, bbox: BBox, rect: Rect) {
  const r = bboxToScreen(bbox, rect)
  ctx.setLineDash([5, 4])
  ctx.lineWidth = 2.5
  ctx.strokeStyle = '#f87171'
  ctx.strokeRect(r.x - 3, r.y - 3, r.width + 6, r.height + 6)
  ctx.setLineDash([])
}

export function drawDraft(ctx: CanvasRenderingContext2D, draft: DraftPolygon, rect: Rect, cursor: Point | null, hoverIndex: number | null) {
  const pts = draft.points.map((p) => toScreen(p, rect))
  if (pts.length === 0) return
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
  if (draft.closed) {
    ctx.closePath()
    ctx.fillStyle = withAlpha(draft.color, 0.18)
    ctx.fill()
  } else if (cursor) {
    const c = toScreen(cursor, rect)
    ctx.lineTo(c[0], c[1])
  }
  ctx.lineWidth = 2
  ctx.strokeStyle = draft.color
  ctx.setLineDash(draft.closed ? [] : [6, 4])
  ctx.stroke()
  ctx.setLineDash([])
  pts.forEach(([x, y], i) => {
    const big = i === hoverIndex || (!draft.closed && i === 0 && pts.length >= 3)
    ctx.beginPath()
    ctx.arc(x, y, big ? 7 : 5, 0, Math.PI * 2)
    ctx.fillStyle = i === hoverIndex ? draft.color : '#ffffff'
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = draft.color
    ctx.stroke()
  })
}

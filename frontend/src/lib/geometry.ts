/**
 * Mapping between the normalized source-frame coordinate system used by the
 * backend ((0,0) = top-left of the video frame, (1,1) = bottom-right) and
 * CSS pixels inside the <video> element.
 *
 * A <video> with `object-fit: contain` letterboxes its content: the frame is
 * scaled uniformly to fit and centered, leaving bars on two sides. Overlays
 * therefore must use the *content rectangle*, not the element box.
 */
import type { BBox, FrameDetections, Point } from '@/types/api'

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export function contentRect(videoWidth: number, videoHeight: number, boxWidth: number, boxHeight: number): Rect {
  if (videoWidth <= 0 || videoHeight <= 0 || boxWidth <= 0 || boxHeight <= 0) {
    return { x: 0, y: 0, width: Math.max(0, boxWidth), height: Math.max(0, boxHeight) }
  }
  const scale = Math.min(boxWidth / videoWidth, boxHeight / videoHeight)
  const width = videoWidth * scale
  const height = videoHeight * scale
  return { x: (boxWidth - width) / 2, y: (boxHeight - height) / 2, width, height }
}

export function toScreen(p: Point, rect: Rect): Point {
  return [rect.x + p[0] * rect.width, rect.y + p[1] * rect.height]
}

/** Screen -> normalized; returns null when the point is in the letterbox bars. */
export function toNormalized(sx: number, sy: number, rect: Rect, clamp = false): Point | null {
  if (rect.width <= 0 || rect.height <= 0) return null
  let x = (sx - rect.x) / rect.width
  let y = (sy - rect.y) / rect.height
  if (clamp) {
    x = Math.min(1, Math.max(0, x))
    y = Math.min(1, Math.max(0, y))
  } else if (x < 0 || x > 1 || y < 0 || y > 1) {
    return null
  }
  return [round6(x), round6(y)]
}

export function snapToEdges(p: Point, threshold = 0.015): Point {
  const snap = (v: number) => (v <= threshold ? 0 : v >= 1 - threshold ? 1 : v)
  return [snap(p[0]), snap(p[1])]
}

export function bboxToScreen(b: BBox, rect: Rect): Rect {
  return {
    x: rect.x + b[0] * rect.width,
    y: rect.y + b[1] * rect.height,
    width: (b[2] - b[0]) * rect.width,
    height: (b[3] - b[1]) * rect.height,
  }
}

function round6(v: number): number {
  return Math.round(v * 1e6) / 1e6
}

/**
 * Pick the sampled frame to display at playback time `t`.
 *
 * Detections exist only on sampled frames. We show the latest sample at or
 * before `t`, but only while it is still "fresh" (within one sampling
 * interval plus a small tolerance). No interpolation is performed, so boxes
 * are never invented for unsampled frames.
 */
export function frameAt(frames: FrameDetections[], t: number, sampleInterval: number): FrameDetections | null {
  if (frames.length === 0) return null
  let lo = 0
  let hi = frames.length - 1
  let best = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (frames[mid].timestamp <= t + 1e-3) {
      best = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (best < 0) return null
  const f = frames[best]
  return t - f.timestamp <= sampleInterval * 1.05 + 0.02 ? f : null
}

// ---- polygon helpers for the editor (mirror backend validation) ----

function orient(a: Point, b: Point, c: Point): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}

function segmentsCross(p1: Point, p2: Point, p3: Point, p4: Point): boolean {
  const d1 = orient(p3, p4, p1)
  const d2 = orient(p3, p4, p2)
  const d3 = orient(p1, p2, p3)
  const d4 = orient(p1, p2, p4)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

export function polygonArea(pts: Point[]): number {
  let s = 0
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i]
    const [x2, y2] = pts[(i + 1) % pts.length]
    s += x1 * y2 - x2 * y1
  }
  return Math.abs(s) / 2
}

export function polygonProblem(pts: Point[]): string | null {
  if (pts.length < 3) return 'Add at least 3 points.'
  const n = pts.length
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue
      if (segmentsCross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n])) return 'Polygon edges must not cross.'
    }
  }
  if (polygonArea(pts) < 1e-4) return 'Polygon is too small.'
  return null
}

export function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

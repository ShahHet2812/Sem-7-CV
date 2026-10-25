import { describe, expect, it } from 'vitest'
import { bboxToScreen, contentRect, frameAt, pointInPolygon, polygonProblem, toNormalized, toScreen } from '@/lib/geometry'
import type { FrameDetections, Point } from '@/types/api'

describe('contentRect (object-fit: contain letterboxing)', () => {
  it('pillarboxes a 4:3 video in a 16:9 box', () => {
    expect(contentRect(640, 480, 1600, 900)).toEqual({ x: 200, y: 0, width: 1200, height: 900 })
  })
  it('letterboxes a 16:9 video in a square box', () => {
    expect(contentRect(1920, 1080, 800, 800)).toEqual({ x: 0, y: 175, width: 800, height: 450 })
  })
  it('fills exactly when aspect ratios match', () => {
    expect(contentRect(1280, 720, 640, 360)).toEqual({ x: 0, y: 0, width: 640, height: 360 })
  })
  it('handles unknown dimensions', () => {
    expect(contentRect(0, 0, 300, 200)).toEqual({ x: 0, y: 0, width: 300, height: 200 })
  })
})

describe('coordinate mapping', () => {
  const rect = contentRect(640, 480, 1600, 900)
  it('round-trips normalized <-> screen', () => {
    const p: Point = [0.25, 0.75]
    const [sx, sy] = toScreen(p, rect)
    expect(toNormalized(sx, sy, rect)).toEqual(p)
  })
  it('rejects clicks in the letterbox bars unless clamped', () => {
    expect(toNormalized(100, 450, rect)).toBeNull()
    expect(toNormalized(100, 450, rect, true)).toEqual([0, 0.5])
  })
  it('maps boxes into the content rect', () => {
    expect(bboxToScreen([0, 0, 0.5, 0.5], rect)).toEqual({ x: 200, y: 0, width: 600, height: 450 })
  })
})

describe('frameAt', () => {
  const frames: FrameDetections[] = [0, 0.2, 0.4, 0.6].map((t, i) => ({ frame_index: i * 2, timestamp: t, detections: [] }))
  it('selects the latest sample at or before the playhead', () => {
    expect(frameAt(frames, 0.45, 0.2)?.timestamp).toBe(0.4)
    expect(frameAt(frames, 0.2, 0.2)?.timestamp).toBe(0.2)
  })
  it('returns nothing before the first sample or when the sample is stale', () => {
    expect(frameAt([{ frame_index: 10, timestamp: 1, detections: [] }], 0.5, 0.2)).toBeNull()
    expect(frameAt(frames, 2.0, 0.2)).toBeNull()
  })
  it('handles empty input', () => {
    expect(frameAt([], 1, 0.2)).toBeNull()
  })
})

describe('polygon validation (mirrors backend rules)', () => {
  it('accepts a simple polygon', () => {
    expect(polygonProblem([[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]])).toBeNull()
  })
  it('requires 3 points', () => {
    expect(polygonProblem([[0, 0], [1, 1]])).toMatch(/3 points/)
  })
  it('rejects self-intersections', () => {
    expect(polygonProblem([[0, 0], [1, 1], [1, 0], [0, 1]])).toMatch(/cross/)
  })
  it('rejects degenerate polygons', () => {
    expect(polygonProblem([[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]])).toMatch(/small/)
  })
  it('point in polygon', () => {
    const sq: Point[] = [[0.2, 0.2], [0.6, 0.2], [0.6, 0.6], [0.2, 0.6]]
    expect(pointInPolygon([0.4, 0.4], sq)).toBe(true)
    expect(pointInPolygon([0.7, 0.4], sq)).toBe(false)
  })
})

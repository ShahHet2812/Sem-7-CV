import { AlertTriangle, ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, type PointerEvent } from 'react'
import { contentRect, frameAt, toNormalized, toScreen, type Rect } from '@/lib/geometry'
import { resourceUrl } from '@/lib/api'
import { cn, formatDuration } from '@/lib/utils'
import type { BBox, FrameDetections, Point, Video, Zone } from '@/types/api'
import { drawDetections, drawDraft, drawHighlightBox, drawZones, type DraftPolygon } from './drawing'

export interface TimelineMarker {
  id: string
  t: number
  color: string
  title: string
}

export interface VideoStageHandle {
  seek: (t: number, pause?: boolean) => void
  pause: () => void
}

interface Props {
  video: Video
  frames?: FrameDetections[]
  sampleInterval?: number | null
  showBoxes?: boolean
  showLabels?: boolean
  classFilter?: Set<string> | null
  zones?: Zone[]
  highlightZoneId?: string | null
  highlightBox?: BBox | null
  markers?: TimelineMarker[]
  draft?: DraftPolygon | null
  onDraftChange?: (d: DraftPolygon) => void
  onTimeChange?: (t: number) => void
  onVisibleCountChange?: (n: number) => void
  className?: string
}

const SPEEDS = [0.25, 0.5, 1, 1.5, 2]
const HIT_RADIUS = 10

/**
 * Video player with a canvas overlay that shares the video's box.
 *
 * Coordinates: everything drawn is stored normalized to the source frame
 * and mapped through `contentRect`, which accounts for object-fit: contain
 * letterboxing, so overlays stay aligned on resize, seek and playback.
 */
export const VideoStage = forwardRef<VideoStageHandle, Props>(function VideoStage(
  {
    video,
    frames = [],
    sampleInterval,
    showBoxes = true,
    showLabels = true,
    classFilter = null,
    zones = [],
    highlightZoneId,
    highlightBox,
    markers = [],
    draft,
    onDraftChange,
    onTimeChange,
    onVisibleCountChange,
    className,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(video.duration_seconds ?? 0)
  const [speed, setSpeed] = useState(1)
  const [playbackError, setPlaybackError] = useState(!video.browser_playable)
  const [cursor, setCursor] = useState<Point | null>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const dragIndex = useRef<number | null>(null)
  const lastCount = useRef(-1)

  // Latest props for the draw loop without re-subscribing listeners.
  const state = useRef({ frames, sampleInterval, showBoxes, showLabels, classFilter, zones, highlightZoneId, highlightBox, draft, cursor, hoverIndex })
  useLayoutEffect(() => {
    state.current = { frames, sampleInterval, showBoxes, showLabels, classFilter, zones, highlightZoneId, highlightBox, draft, cursor, hoverIndex }
  })

  const fallbackInterval = video.fps ? 1 / video.fps : 0.2

  const getRect = useCallback((): Rect => {
    const el = containerRef.current
    if (!el) return { x: 0, y: 0, width: 0, height: 0 }
    const v = videoRef.current
    const vw = v && v.videoWidth ? v.videoWidth : video.width
    const vh = v && v.videoHeight ? v.videoHeight : video.height
    return contentRect(vw, vh, el.clientWidth, el.clientHeight)
  }, [video.width, video.height])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const el = containerRef.current
    if (!canvas || !el) return
    const dpr = window.devicePixelRatio || 1
    const w = el.clientWidth
    const h = el.clientHeight
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)
    const s = state.current
    const rect = getRect()
    drawZones(ctx, s.zones, rect, s.highlightZoneId)
    const t = videoRef.current?.currentTime ?? 0
    const frame = frameAt(s.frames, t, s.sampleInterval ?? fallbackInterval)
    const dets = frame ? frame.detections.filter((d) => !s.classFilter || s.classFilter.has(d.class_name)) : []
    if (s.showBoxes || s.showLabels) drawDetections(ctx, dets, rect, { boxes: s.showBoxes, labels: s.showLabels })
    if (s.highlightBox) drawHighlightBox(ctx, s.highlightBox, rect)
    if (s.draft) drawDraft(ctx, s.draft, rect, s.cursor, s.hoverIndex)
    if (dets.length !== lastCount.current) {
      lastCount.current = dets.length
      onVisibleCountChange?.(dets.length)
    }
  }, [getRect, fallbackInterval, onVisibleCountChange])

  // Redraw whenever inputs change.
  useEffect(() => {
    draw()
  }, [draw, frames, showBoxes, showLabels, classFilter, zones, highlightZoneId, highlightBox, draft, cursor, hoverIndex])

  // Resize handling.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => draw())
    ro.observe(el)
    return () => ro.disconnect()
  }, [draw])

  // rAF loop only while playing.
  useEffect(() => {
    if (!playing) return
    let lastUi = -1
    let lastReport = -1
    const tick = () => {
      draw()
      const t = videoRef.current?.currentTime ?? 0
      // Canvas redraws every frame; React state updates are throttled.
      if (Math.abs(t - lastUi) >= 0.1) {
        lastUi = t
        setTime(t)
      }
      if (Math.abs(t - lastReport) >= 0.25) {
        lastReport = t
        onTimeChange?.(t)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [playing, draw, onTimeChange])

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = speed
  }, [speed])

  // Reset when switching videos.
  useEffect(() => {
    setPlaybackError(!video.browser_playable)
    setTime(0)
    setPlaying(false)
    setDuration(video.duration_seconds ?? 0)
  }, [video.id, video.browser_playable, video.duration_seconds])

  const seek = useCallback(
    (t: number, pause = true) => {
      const v = videoRef.current
      const clamped = Math.max(0, Math.min(t, duration || t))
      if (v && !playbackError) {
        if (pause) v.pause()
        v.currentTime = clamped
      }
      setTime(clamped)
      onTimeChange?.(clamped)
    },
    [duration, playbackError, onTimeChange],
  )

  useImperativeHandle(ref, () => ({ seek, pause: () => videoRef.current?.pause() }), [seek])

  const togglePlay = () => {
    const v = videoRef.current
    if (!v || playbackError) return
    if (v.paused) v.play().catch(() => setPlaybackError(true))
    else v.pause()
  }

  const step = (dir: 1 | -1) => seek(time + dir * (sampleInterval ?? fallbackInterval))

  // ---- polygon editor interaction ----
  const localPoint = (e: PointerEvent) => {
    const bounds = containerRef.current!.getBoundingClientRect()
    return [e.clientX - bounds.left, e.clientY - bounds.top] as const
  }

  const nearestVertex = (sx: number, sy: number): number | null => {
    if (!draft) return null
    const rect = getRect()
    let best: number | null = null
    let bestD = HIT_RADIUS
    draft.points.forEach((p, i) => {
      const [px, py] = toScreen(p, rect)
      const d = Math.hypot(px - sx, py - sy)
      if (d <= bestD) {
        best = i
        bestD = d
      }
    })
    return best
  }

  const onPointerDown = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!draft || !onDraftChange) {
      togglePlay()
      return
    }
    const [sx, sy] = localPoint(e)
    const idx = nearestVertex(sx, sy)
    if (idx !== null) {
      if (!draft.closed && idx === 0 && draft.points.length >= 3) {
        onDraftChange({ ...draft, closed: true })
        return
      }
      dragIndex.current = idx
      e.currentTarget.setPointerCapture(e.pointerId)
      return
    }
    if (draft.closed) return
    const p = toNormalized(sx, sy, getRect())
    if (p) onDraftChange({ ...draft, points: [...draft.points, p] })
  }

  const onPointerMove = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!draft) return
    const [sx, sy] = localPoint(e)
    if (dragIndex.current !== null && onDraftChange) {
      const p = toNormalized(sx, sy, getRect(), true)
      if (p) {
        const pts = draft.points.slice()
        pts[dragIndex.current] = p
        onDraftChange({ ...draft, points: pts })
      }
      return
    }
    setHoverIndex(nearestVertex(sx, sy))
    setCursor(draft.closed ? null : toNormalized(sx, sy, getRect(), true))
  }

  const onPointerUp = (e: PointerEvent<HTMLCanvasElement>) => {
    if (dragIndex.current !== null) {
      dragIndex.current = null
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const editing = !!draft && !!onDraftChange

  return (
    <div className={cn('overflow-hidden rounded-lg border border-border bg-black', className)}>
      <div ref={containerRef} className="relative aspect-video w-full select-none">
        {playbackError ? (
          video.thumbnail_url && (
            <img src={resourceUrl(video.thumbnail_url)} alt="" className="absolute inset-0 size-full object-contain" />
          )
        ) : (
          <video
            ref={videoRef}
            key={video.id}
            src={resourceUrl(video.stream_url)}
            className="absolute inset-0 size-full object-contain"
            preload="auto"
            playsInline
            muted
            onPlay={() => setPlaying(true)}
            onPause={() => {
              setPlaying(false)
              const t = videoRef.current?.currentTime ?? 0
              setTime(t)
              onTimeChange?.(t)
              draw()
            }}
            onEnded={() => setPlaying(false)}
            onSeeked={() => {
              const t = videoRef.current?.currentTime ?? 0
              setTime(t)
              onTimeChange?.(t)
              draw()
            }}
            onTimeUpdate={() => {
              if (!playing) setTime(videoRef.current?.currentTime ?? 0)
            }}
            onLoadedMetadata={() => {
              const v = videoRef.current
              if (v && Number.isFinite(v.duration)) setDuration(v.duration)
              draw()
            }}
            onLoadedData={draw}
            onError={() => setPlaybackError(true)}
          />
        )}
        <canvas
          ref={canvasRef}
          className={cn('absolute inset-0 size-full', editing ? (hoverIndex !== null ? 'cursor-grab' : 'cursor-crosshair') : 'cursor-pointer')}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => {
            setCursor(null)
            setHoverIndex(null)
          }}
          onDoubleClick={() => {
            if (draft && onDraftChange && !draft.closed && draft.points.length >= 3) onDraftChange({ ...draft, closed: true })
          }}
          aria-label={editing ? 'Zone drawing canvas: click to add points' : 'Video overlay'}
        />
        {playbackError && (
          <div className="absolute inset-x-3 top-3 flex items-start gap-2 rounded-md bg-black/75 px-3 py-2 text-xs text-warning">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Your browser cannot play this file ({video.container_format.toUpperCase()}
              {video.codec ? `/${video.codec}` : ''}). Processing still works; the first frame is shown for zone drawing. Convert to
              H.264 MP4 for in-browser playback with overlays.
            </span>
          </div>
        )}
      </div>

      <div className="space-y-1.5 border-t border-border bg-surface px-3 py-2">
        <div className="relative h-4">
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.01}
            value={Math.min(time, duration || 0)}
            onChange={(e) => seek(Number(e.target.value), false)}
            className="absolute inset-x-0 top-1/2 h-1 w-full -translate-y-1/2 cursor-pointer"
            aria-label="Seek"
            disabled={playbackError}
          />
          {duration > 0 &&
            markers.map((m) => (
              <button
                key={m.id}
                title={m.title}
                onClick={() => seek(m.t)}
                className="absolute -top-1 h-2.5 w-1 -translate-x-1/2 rounded-sm opacity-90 hover:scale-y-150"
                style={{ left: `${(m.t / duration) * 100}%`, background: m.color }}
                aria-label={m.title}
              />
            ))}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={togglePlay}
            disabled={playbackError}
            className="rounded p-1.5 hover:bg-surface-2 disabled:opacity-40"
            aria-label={playing ? 'Pause' : 'Play'}
          >
            {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
          </button>
          <button onClick={() => step(-1)} className="rounded p-1 hover:bg-surface-2" aria-label="Step back one sample" title="Previous sample">
            <ChevronLeft className="size-4" />
          </button>
          <button onClick={() => step(1)} className="rounded p-1 hover:bg-surface-2" aria-label="Step forward one sample" title="Next sample">
            <ChevronRight className="size-4" />
          </button>
          <span className="font-mono tabular text-muted">
            {formatDuration(time, true)} / {formatDuration(duration, true)}
          </span>
          <div className="ml-auto flex items-center gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={cn('rounded px-1.5 py-0.5 font-mono', s === speed ? 'bg-primary/15 text-primary' : 'text-muted hover:bg-surface-2')}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
})

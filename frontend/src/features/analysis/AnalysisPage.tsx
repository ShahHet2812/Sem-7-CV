import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Box, Download, Eye, EyeOff, Film, Hexagon, Loader2, Play, RotateCcw, ScanSearch, Square, Tag } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, EventTypeBadge, LoadingState, PageHeader, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Progress, Select, Switch } from '@/components/ui/primitives'
import { VideoStage, type TimelineMarker, type VideoStageHandle } from '@/components/video/VideoStage'
import { useJobAction, useProcessVideo, useVideo, useVideoEvents, useVideoOptions, useZones } from '@/hooks/queries'
import { useDetectionWindows } from '@/hooks/useDetections'
import { resourceUrl } from '@/lib/api'
import { classColor, cn, formatBytes, formatDateTime, formatDuration, formatNumber, ZONE_TYPE_LABELS } from '@/lib/utils'
import { analyticsApi } from '@/services/resources'
import type { MonitoringEvent, SampleMeta, Video } from '@/types/api'

const SEVERITY_COLOR = { info: '#60a5fa', warning: '#fbbf24', critical: '#f87171' }

function ProcessingCard({ video }: { video: Video }) {
  const job = video.latest_job
  const process = useProcessVideo()
  const action = useJobAction()
  const active = video.status === 'queued' || video.status === 'processing'
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Processing</CardTitle>
          <CardDescription>YOLO detection + multi-object tracking</CardDescription>
        </div>
        <StatusBadge status={video.status} />
      </CardHeader>
      <CardContent className="space-y-3">
        {job ? (
          <>
            {active && (
              <div className="space-y-1">
                <Progress value={job.progress} indeterminate={job.progress == null} />
                <p className="text-xs text-muted tabular">
                  {job.status === 'queued'
                    ? 'Waiting for the worker…'
                    : job.total_frames
                      ? `${formatNumber(job.frames_processed)} / ${formatNumber(job.total_frames)} frames (${Math.round((job.progress ?? 0) * 100)}%)`
                      : `${formatNumber(job.frames_processed)} frames decoded (total unknown)`}
                </p>
              </div>
            )}
            {job.error_message && <p className="rounded-md bg-danger/10 px-3 py-2 text-xs text-danger">{job.error_message}</p>}
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-muted">Model</dt>
              <dd className="text-right">{job.model_name ?? '—'}</dd>
              <dt className="text-muted">Device</dt>
              <dd className="text-right">{job.device ?? '—'}</dd>
              <dt className="text-muted">Sampling</dt>
              <dd className="text-right tabular">
                every {job.frame_stride} frame(s){video.fps ? ` (${(video.fps / job.frame_stride).toFixed(1)}/s)` : ''}
              </dd>
              <dt className="text-muted">Confidence ≥</dt>
              <dd className="text-right tabular">{job.config.confidence_threshold ?? '—'}</dd>
              <dt className="text-muted">Sampled frames</dt>
              <dd className="text-right tabular">{formatNumber(job.frames_sampled)}</dd>
              <dt className="text-muted">Detections / tracks</dt>
              <dd className="text-right tabular">
                {formatNumber(job.detection_count)} / {formatNumber(job.track_count)}
              </dd>
              <dt className="text-muted">Processing time</dt>
              <dd className="text-right tabular">
                {job.processing_seconds != null ? `${job.processing_seconds.toFixed(1)} s` : '—'}
                {job.sampled_fps ? ` · ${job.sampled_fps.toFixed(1)} fps` : ''}
              </dd>
              <dt className="text-muted">Attempt</dt>
              <dd className="text-right tabular">{job.attempt}</dd>
            </dl>
          </>
        ) : (
          <p className="text-sm text-muted">This video has not been processed yet.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {active ? (
            <Button size="sm" variant="outline" disabled={action.isPending || job?.cancel_requested} onClick={() => action.mutate({ id: job!.id, action: 'cancel' })}>
              <Square /> {job?.cancel_requested ? 'Cancelling…' : 'Cancel'}
            </Button>
          ) : (
            <>
              <Button size="sm" onClick={() => process.mutate(video.id)} disabled={process.isPending}>
                {process.isPending ? <Loader2 className="animate-spin" /> : <Play />}
                {video.current_job_id ? 'Reprocess' : 'Start processing'}
              </Button>
              {job && (job.status === 'failed' || job.status === 'cancelled') && (
                <Button size="sm" variant="outline" onClick={() => action.mutate({ id: job.id, action: 'retry' })} disabled={action.isPending}>
                  <RotateCcw /> Retry job
                </Button>
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function EventTimeline({
  events,
  selected,
  onSelect,
}: {
  events: MonitoringEvent[]
  selected: string | null
  onSelect: (e: MonitoringEvent) => void
}) {
  if (events.length === 0)
    return (
      <EmptyState
        className="py-8"
        title="No events for this video"
        description="Events appear when tracked objects cross enabled zone boundaries. Draw zones on the Monitoring Zones page."
      />
    )
  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-left text-xs">
        <tbody>
          {events.map((e) => (
            <tr
              key={e.id}
              onClick={() => onSelect(e)}
              className={cn('cursor-pointer border-b border-border last:border-0 hover:bg-surface-2', selected === e.id && 'bg-primary/10')}
            >
              <td className="py-2 pl-4 pr-2 font-mono tabular text-muted">{formatDuration(e.video_timestamp, true)}</td>
              <td className="px-2">
                <EventTypeBadge type={e.event_type} severity={e.severity} />
              </td>
              <td className="px-2">
                {e.zone_name && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2 rounded-sm" style={{ background: e.zone_color ?? undefined }} />
                    {e.zone_name}
                  </span>
                )}
              </td>
              <td className="px-2 text-muted">
                {e.class_name ?? (e.occupancy != null ? `occupancy ${e.occupancy}` : '')}
                {e.track_id != null && ` #${e.track_id}`}
              </td>
              <td className="py-2 pl-2 pr-4 text-right">
                <StatusBadge status={e.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Workspace({ video }: { video: Video }) {
  const qc = useQueryClient()
  const stageRef = useRef<VideoStageHandle>(null)
  const [params] = useSearchParams()
  const [time, setTime] = useState(0)
  const [showBoxes, setShowBoxes] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [showZones, setShowZones] = useState(true)
  const [hiddenClasses, setHiddenClasses] = useState<Set<string>>(new Set())
  const [selectedEvent, setSelectedEvent] = useState<MonitoringEvent | null>(null)
  const [visibleCount, setVisibleCount] = useState(0)

  const det = useDetectionWindows(video.id, video.current_job_id, time)
  const zones = useZones(video.id)
  const events = useVideoEvents(video.id)
  const classStats = useQuery({
    queryKey: ['analytics', 'detections', { video_id: video.id }],
    queryFn: () => analyticsApi.detections({ video_id: video.id }),
    enabled: !!video.current_job_id,
  })

  // When a job finishes, reload everything derived from it.
  const prevStatus = useRef(video.status)
  useEffect(() => {
    if (prevStatus.current !== video.status && video.status === 'completed') {
      ;['detections', 'video-events', 'zones', 'analytics'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
    }
    prevStatus.current = video.status
  }, [video.status, qc])

  // Deep link: /analysis/:id?t=12.5&event=<id>
  const initialSeek = useRef(false)
  useEffect(() => {
    if (initialSeek.current) return
    const t = Number(params.get('t'))
    if (params.get('t') && Number.isFinite(t)) {
      initialSeek.current = true
      setTimeout(() => stageRef.current?.seek(t), 300)
    }
  }, [params])
  useEffect(() => {
    const id = params.get('event')
    const ev = events.data?.items.find((e) => e.id === id)
    if (ev) setSelectedEvent(ev)
  }, [params, events.data])

  const classes = useMemo(() => (classStats.data ?? []).map((c) => c.class_name), [classStats.data])
  const classFilter = useMemo(
    () => (hiddenClasses.size ? new Set(classes.filter((c) => !hiddenClasses.has(c))) : null),
    [classes, hiddenClasses],
  )
  const eventList = useMemo(() => events.data?.items ?? [], [events.data])
  const markers = useMemo<TimelineMarker[]>(
    () =>
      eventList
        .filter((e) => e.video_timestamp != null)
        .map((e) => ({ id: e.id, t: e.video_timestamp!, color: SEVERITY_COLOR[e.severity], title: `${e.event_type} @ ${formatDuration(e.video_timestamp, true)}` })),
    [eventList],
  )
  const onTime = useCallback((t: number) => setTime(t), [])

  const selectEvent = (e: MonitoringEvent) => {
    setSelectedEvent(e)
    if (e.video_timestamp != null) stageRef.current?.seek(e.video_timestamp)
  }

  const processed = !!video.current_job_id

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <div className="space-y-4 xl:col-span-8">
        <VideoStage
          ref={stageRef}
          video={video}
          frames={det.frames}
          sampleInterval={det.sampleInterval}
          showBoxes={showBoxes}
          showLabels={showLabels}
          classFilter={classFilter}
          zones={showZones ? (zones.data ?? []) : []}
          highlightZoneId={selectedEvent?.zone_id}
          highlightBox={selectedEvent?.bbox ?? null}
          markers={markers}
          onTimeChange={onTime}
          onVisibleCountChange={setVisibleCount}
        />

        <Card className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-xs">
          <label className="flex items-center gap-2">
            <Switch checked={showBoxes} onCheckedChange={setShowBoxes} aria-label="Toggle bounding boxes" />
            <Box className="size-3.5 text-muted" /> Boxes
          </label>
          <label className="flex items-center gap-2">
            <Switch checked={showLabels} onCheckedChange={setShowLabels} aria-label="Toggle labels" />
            <Tag className="size-3.5 text-muted" /> Labels
          </label>
          <label className="flex items-center gap-2">
            <Switch checked={showZones} onCheckedChange={setShowZones} aria-label="Toggle zones" />
            <Hexagon className="size-3.5 text-muted" /> Zones
          </label>
          {classes.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted">Classes:</span>
              {classes.map((c) => {
                const hidden = hiddenClasses.has(c)
                return (
                  <button
                    key={c}
                    onClick={() =>
                      setHiddenClasses((s) => {
                        const n = new Set(s)
                        if (hidden) n.delete(c)
                        else n.add(c)
                        return n
                      })
                    }
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
                      hidden ? 'border-border text-subtle line-through' : 'border-border-strong',
                    )}
                  >
                    <span className="size-2 rounded-full" style={{ background: classColor(c) }} />
                    {c}
                  </button>
                )
              })}
            </div>
          )}
          <span className="ml-auto text-muted tabular">
            {processed ? (
              <>
                {det.loading && <Loader2 className="mr-1 inline size-3 animate-spin" />}
                {visibleCount} object(s) on current sample
                {det.sampleInterval ? ` · samples every ${det.sampleInterval.toFixed(2)} s` : ''}
              </>
            ) : (
              'Process the video to see detections'
            )}
          </span>
        </Card>
        {det.truncated && <p className="text-xs text-warning">Very dense window: only the first 20,000 detections are displayed.</p>}

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Event timeline</CardTitle>
              <CardDescription>Click an event to jump to it; the triggering object is outlined in red.</CardDescription>
            </div>
            <Button size="xs" variant="outline" asChild>
              <Link to={`/events?video_id=${video.id}`}>Open in Events</Link>
            </Button>
          </CardHeader>
          {events.isLoading ? <LoadingState /> : events.isError ? <ErrorState error={events.error} /> : (
            <EventTimeline events={eventList} selected={selectedEvent?.id ?? null} onSelect={selectEvent} />
          )}
        </Card>
      </div>

      <div className="space-y-4 xl:col-span-4">
        <ProcessingCard video={video} />

        <Card>
          <CardHeader>
            <CardTitle>Detection statistics</CardTitle>
          </CardHeader>
          <CardContent>
            {!processed ? (
              <p className="text-sm text-muted">No results yet.</p>
            ) : classStats.isLoading ? (
              <LoadingState className="py-4" />
            ) : (classStats.data ?? []).length === 0 ? (
              <p className="text-sm text-muted">No objects of the selected classes were detected.</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="text-subtle">
                  <tr>
                    <th className="pb-1.5 text-left font-medium">Class</th>
                    <th className="pb-1.5 text-right font-medium">Detections</th>
                    <th className="pb-1.5 text-right font-medium" title="Distinct tracker IDs (upper bound on distinct objects)">
                      Track IDs
                    </th>
                    <th className="pb-1.5 text-right font-medium">Avg conf.</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {classStats.data!.map((c) => (
                    <tr key={c.class_name} className="border-t border-border">
                      <td className="py-1.5">
                        <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: classColor(c.class_name) }} />
                        {c.class_name}
                      </td>
                      <td className="text-right">{formatNumber(c.detections)}</td>
                      <td className="text-right">{formatNumber(c.tracks)}</td>
                      <td className="text-right">{c.avg_confidence != null ? `${(c.avg_confidence * 100).toFixed(0)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Zones</CardTitle>
              <CardDescription>Entries/exits computed from tracked anchor points</CardDescription>
            </div>
            <Button size="xs" variant="outline" asChild>
              <Link to={`/zones?video=${video.id}`}>
                <Hexagon /> Edit zones
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {(zones.data ?? []).length === 0 ? (
              <p className="text-sm text-muted">No zones defined for this video.</p>
            ) : (
              zones.data!.map((z) => (
                <div key={z.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs">
                  <span className="size-3 rounded-sm" style={{ background: z.color }} />
                  <div className="min-w-0 flex-1">
                    <p className={cn('truncate font-medium', !z.enabled && 'text-muted line-through')}>{z.name}</p>
                    <p className="text-subtle">{ZONE_TYPE_LABELS[z.zone_type]}</p>
                  </div>
                  <span className="text-muted tabular" title="entries / exits / peak occupancy">
                    ↓{z.stats.entries} ↑{z.stats.exits}
                    {z.stats.peak_occupancy != null && ` · peak ${z.stats.peak_occupancy}`}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Video information</CardTitle>
            <Button size="icon" variant="ghost" asChild title="Download original">
              <a href={resourceUrl(video.download_url)} download>
                <Download />
              </a>
            </Button>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-muted">Resolution</dt>
              <dd className="text-right tabular">
                {video.width}×{video.height}
              </dd>
              <dt className="text-muted">Frame rate</dt>
              <dd className="text-right tabular">{video.fps ? `${video.fps.toFixed(2)} fps` : '—'}</dd>
              <dt className="text-muted">Duration</dt>
              <dd className="text-right tabular">{formatDuration(video.duration_seconds)}</dd>
              <dt className="text-muted">Frames</dt>
              <dd className="text-right tabular">{formatNumber(video.frame_count)}</dd>
              <dt className="text-muted">Format</dt>
              <dd className="text-right">
                {video.container_format.toUpperCase()} {video.codec && `(${video.codec})`}
              </dd>
              <dt className="text-muted">Size</dt>
              <dd className="text-right tabular">{formatBytes(video.file_size)}</dd>
              <dt className="text-muted">Uploaded</dt>
              <dd className="text-right">{formatDateTime(video.created_at)}</dd>
              {(() => {
                const meta = video.processing_metadata.sample as SampleMeta | undefined
                return meta ? (
                  <>
                    <dt className="text-muted">Source</dt>
                    <dd className="text-right">
                      <a href={meta.source_page} target="_blank" rel="noreferrer" className="hover:text-primary">
                        {meta.license} · {meta.attribution}
                      </a>
                    </dd>
                  </>
                ) : null
              })()}
              {video.recorded_at && (
                <>
                  <dt className="text-muted">Recorded</dt>
                  <dd className="text-right">{formatDateTime(video.recorded_at)}</dd>
                </>
              )}
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function VideoPicker({ value, onChange }: { value?: string; onChange: (id: string) => void }) {
  const options = useVideoOptions()
  return (
    <Select value={value ?? ''} onChange={(e) => onChange(e.target.value)} className="w-72" aria-label="Select video" disabled={options.isLoading}>
      <option value="" disabled>
        {options.isLoading ? 'Loading videos…' : 'Select a video…'}
      </option>
      {options.data?.items.map((v) => (
        <option key={v.id} value={v.id}>
          {v.original_filename} · {v.status}
        </option>
      ))}
    </Select>
  )
}

export default function AnalysisPage() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const options = useVideoOptions()
  const video = useVideo(videoId)

  // Without a selection, open the most recently uploaded video.
  useEffect(() => {
    if (!videoId && options.data?.items.length) navigate(`/analysis/${options.data.items[0].id}`, { replace: true })
  }, [videoId, options.data, navigate])

  return (
    <>
      <PageHeader
        title="Analysis Workspace"
        description="Play back footage with synchronized detections, track IDs and zones. Boxes are drawn from stored metadata for the sampled frame at the playhead."
        actions={<VideoPicker value={videoId} onChange={(id) => navigate(`/analysis/${id}`)} />}
      />
      {!videoId ? (
        options.isLoading ? (
          <LoadingState />
        ) : (
          <Card>
            <EmptyState
              icon={<Film />}
              title="No videos to analyze"
              description="Upload a video in the Video Library first."
              action={
                <Button asChild>
                  <Link to="/videos?upload=1">Upload video</Link>
                </Button>
              }
            />
          </Card>
        )
      ) : video.isLoading ? (
        <LoadingState />
      ) : video.isError ? (
        <Card>
          <ErrorState error={video.error} onRetry={() => video.refetch()} />
        </Card>
      ) : video.data ? (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <ScanSearch className="size-4 text-primary" />
            <span className="font-medium">{video.data.original_filename}</span>
            <StatusBadge status={video.data.status} />
            {!video.data.current_job_id && video.data.status !== 'processing' && video.data.status !== 'queued' && (
              <span className="text-xs text-muted">— not processed yet: start processing to generate detections.</span>
            )}
            <span className="ml-auto flex items-center gap-1 text-xs text-muted">
              {video.data.zone_count > 0 ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
              {video.data.zone_count} zone(s) · {video.data.event_count} event(s)
            </span>
          </div>
          <Workspace key={video.data.id} video={video.data} />
        </>
      ) : null}
    </>
  )
}

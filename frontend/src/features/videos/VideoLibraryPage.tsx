import { Download, Film, Loader2, Play, RotateCcw, ScanSearch, Search, Sparkles, Square, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConfirmDialog, EmptyState, ErrorState, LoadingState, PageHeader, Pagination, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, Input, Progress, Select } from '@/components/ui/primitives'
import { useDeleteVideo, useJobAction, useProcessVideo, useVideos } from '@/hooks/queries'
import { resourceUrl } from '@/lib/api'
import { formatBytes, formatDuration, formatRelative } from '@/lib/utils'
import type { Video } from '@/types/api'
import { SamplesDialog } from './SamplesDialog'
import { UploadDialog } from './UploadDialog'

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function VideoRow({ video }: { video: Video }) {
  const process = useProcessVideo()
  const del = useDeleteVideo()
  const jobAction = useJobAction()
  const job = video.latest_job
  const active = video.status === 'queued' || video.status === 'processing'
  const canRetry = job && (job.status === 'failed' || job.status === 'cancelled')

  return (
    <tr className="border-b border-border last:border-0 hover:bg-surface-2/50">
      <td className="py-2.5 pl-4 pr-3">
        <div className="flex items-center gap-3">
          <div className="relative h-12 w-20 shrink-0 overflow-hidden rounded bg-surface-3">
            {video.thumbnail_url ? (
              <img src={resourceUrl(video.thumbnail_url)} alt="" className="size-full object-cover" loading="lazy" />
            ) : (
              <Film className="m-auto mt-3.5 size-5 text-subtle" />
            )}
            {video.duration_seconds != null && (
              <span className="absolute bottom-0.5 right-0.5 rounded bg-black/70 px-1 text-[10px] tabular">
                {formatDuration(video.duration_seconds)}
              </span>
            )}
          </div>
          <div className="min-w-0">
            <Link to={`/analysis/${video.id}`} className="block max-w-[280px] truncate text-sm font-medium hover:text-primary">
              {video.original_filename}
            </Link>
            <p className="text-xs text-muted">
              {video.width}×{video.height} · {video.fps ? `${video.fps.toFixed(1)} fps` : 'fps unknown'} ·{' '}
              {video.container_format.toUpperCase()}
              {video.codec ? ` (${video.codec})` : ''}
              {video.is_sample && <span className="ml-1.5 rounded bg-info/15 px-1 text-[10px] text-info">sample</span>}
            </p>
          </div>
        </div>
      </td>
      <td className="px-3 text-sm tabular text-muted">{formatBytes(video.file_size)}</td>
      <td className="px-3 text-sm text-muted">{formatRelative(video.created_at)}</td>
      <td className="px-3">
        <div className="w-36 space-y-1">
          <StatusBadge status={video.status} />
          {active && job && (
            <Progress value={job.progress} indeterminate={job.progress == null} className="h-1" />
          )}
          {video.status === 'failed' && job?.error_message && (
            <p className="line-clamp-2 text-[11px] text-danger" title={job.error_message}>
              {job.error_message}
            </p>
          )}
        </div>
      </td>
      <td className="px-3 text-xs text-muted tabular">
        {video.current_job_id ? (
          <>
            {video.detection_count.toLocaleString()} det · {video.event_count} events
          </>
        ) : (
          '—'
        )}
        <div>{video.zone_count} zone(s)</div>
      </td>
      <td className="py-2.5 pl-3 pr-4">
        <div className="flex justify-end gap-1">
          {active ? (
            <Button
              size="xs"
              variant="outline"
              disabled={jobAction.isPending || job?.cancel_requested}
              onClick={() => job && jobAction.mutate({ id: job.id, action: 'cancel' })}
            >
              <Square /> {job?.cancel_requested ? 'Cancelling' : 'Cancel'}
            </Button>
          ) : canRetry ? (
            <Button size="xs" variant="outline" onClick={() => jobAction.mutate({ id: job!.id, action: 'retry' })} disabled={jobAction.isPending}>
              <RotateCcw /> Retry
            </Button>
          ) : (
            <Button size="xs" variant="outline" onClick={() => process.mutate(video.id)} disabled={process.isPending}>
              {process.isPending ? <Loader2 className="animate-spin" /> : <Play />}
              {video.current_job_id ? 'Reprocess' : 'Process'}
            </Button>
          )}
          <Button size="xs" variant="ghost" asChild title="Open in analysis workspace">
            <Link to={`/analysis/${video.id}`}>
              <ScanSearch /> View
            </Link>
          </Button>
          <Button size="icon" variant="ghost" asChild title="Download original">
            <a href={resourceUrl(video.download_url)} download>
              <Download />
            </a>
          </Button>
          <ConfirmDialog
            title="Delete video?"
            description={`“${video.original_filename}” and all of its detections, zones, events and snapshots will be permanently deleted.`}
            confirmLabel="Delete"
            destructive
            onConfirm={() => del.mutateAsync(video)}
            trigger={
              <Button size="icon" variant="ghost" title="Delete" disabled={video.status === 'processing'}>
                <Trash2 className="text-danger/80" />
              </Button>
            }
          />
        </div>
      </td>
    </tr>
  )
}

export default function VideoLibraryPage() {
  const [params, setParams] = useSearchParams()
  const [uploadOpen, setUploadOpen] = useState(params.get('upload') === '1')
  const [samplesOpen, setSamplesOpen] = useState(params.get('samples') === '1')
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('created_at:desc')
  const [page, setPage] = useState(1)
  const debouncedQ = useDebounced(q)
  const [sortField, order] = sort.split(':') as [string, 'asc' | 'desc']
  const videos = useVideos({ q: debouncedQ || undefined, status: status || undefined, sort: sortField, order, page, page_size: 10 })

  useEffect(() => setPage(1), [debouncedQ, status, sort])
  useEffect(() => {
    if (params.get('upload') === '1' || params.get('samples') === '1') {
      params.delete('upload')
      params.delete('samples')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  const filtered = !!(debouncedQ || status)
  const data = videos.data

  return (
    <>
      <PageHeader
        title="Video Library"
        description="Upload footage, start processing jobs, and manage stored videos. Files are validated on the server before they are accepted."
        actions={
          <>
            <Button variant="outline" onClick={() => setSamplesOpen(true)}>
              <Sparkles /> Sample videos
            </Button>
            <Button onClick={() => setUploadOpen(true)}>
              <Upload /> Upload video
            </Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="relative min-w-56 flex-1">
            <Search className="absolute left-2.5 top-2.5 size-4 text-subtle" />
            <Input placeholder="Search by filename…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" aria-label="Search videos" />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Filter by status">
            <option value="">All statuses</option>
            {['uploaded', 'queued', 'processing', 'completed', 'failed', 'cancelled'].map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-48" aria-label="Sort">
            <option value="created_at:desc">Newest first</option>
            <option value="created_at:asc">Oldest first</option>
            <option value="original_filename:asc">Name A–Z</option>
            <option value="file_size:desc">Largest first</option>
            <option value="duration_seconds:desc">Longest first</option>
          </Select>
        </div>

        {videos.isLoading ? (
          <LoadingState />
        ) : videos.isError ? (
          <ErrorState error={videos.error} onRetry={() => videos.refetch()} />
        ) : !data || data.items.length === 0 ? (
          filtered ? (
            <EmptyState icon={<Search />} title="No videos match your filters" />
          ) : (
            <EmptyState
              icon={<Film />}
              title="No videos yet"
              description="Upload an MP4, MOV, AVI, MKV or WEBM file, or import the public sample clip to try the full workflow."
              action={
                <>
                  <Button onClick={() => setUploadOpen(true)}>
                    <Upload /> Upload video
                  </Button>
                  <Button variant="outline" onClick={() => setSamplesOpen(true)}>
                    <Sparkles /> Browse sample videos
                  </Button>
                </>
              }
            />
          )
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-subtle">
                    <th className="py-2 pl-4 pr-3 font-medium">Video</th>
                    <th className="px-3 font-medium">Size</th>
                    <th className="px-3 font-medium">Uploaded</th>
                    <th className="px-3 font-medium">Status</th>
                    <th className="px-3 font-medium">Results</th>
                    <th className="pl-3 pr-4 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((v) => (
                    <VideoRow key={v.id} video={v} />
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={data.page} pages={data.pages} total={data.total} onChange={setPage} />
          </>
        )}
      </Card>

      <p className="mt-3 text-xs text-subtle">
        Decoding uses the FFmpeg build bundled with OpenCV. Browser playback depends on the codec: H.264/VP9/AV1 in MP4/WebM play everywhere;
        AVI/MKV files can still be processed but may not play in the browser.
      </p>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <SamplesDialog open={samplesOpen} onOpenChange={setSamplesOpen} />
    </>
  )
}

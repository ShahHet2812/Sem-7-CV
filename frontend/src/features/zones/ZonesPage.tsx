import { Check, Hexagon, Loader2, Pencil, Plus, RefreshCcw, Trash2, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConfirmDialog, EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Kbd, Switch } from '@/components/ui/primitives'
import type { DraftPolygon } from '@/components/video/drawing'
import { VideoStage } from '@/components/video/VideoStage'
import { VideoPicker } from '@/features/analysis/AnalysisPage'
import { useSettings, useVideo, useVideoOptions, useZoneMutations, useZones } from '@/hooks/queries'
import { polygonProblem } from '@/lib/geometry'
import { cn, ZONE_COLORS, ZONE_TYPE_LABELS } from '@/lib/utils'
import type { Point, Video, Zone, ZoneInput } from '@/types/api'
import { TYPE_DEFAULTS, ZoneForm, type ZoneFormInput, type ZoneFormValues } from './ZoneForm'

const TEMPLATES: { label: string; points: Point[] }[] = [
  { label: 'Left half', points: [[0, 0], [0.5, 0], [0.5, 1], [0, 1]] },
  { label: 'Right half', points: [[0.5, 0], [1, 0], [1, 1], [0.5, 1]] },
  { label: 'Bottom band', points: [[0, 0.66], [1, 0.66], [1, 1], [0, 1]] },
  { label: 'Center box', points: [[0.3, 0.3], [0.7, 0.3], [0.7, 0.85], [0.3, 0.85]] },
  { label: 'Full frame', points: [[0, 0], [1, 0], [1, 1], [0, 1]] },
]

type Mode = { kind: 'idle' } | { kind: 'create' } | { kind: 'edit'; zone: Zone }

function Editor({ video }: { video: Video }) {
  const zones = useZones(video.id)
  const settings = useSettings()
  const m = useZoneMutations(video.id)
  const [mode, setMode] = useState<Mode>({ kind: 'idle' })
  const [draft, setDraft] = useState<DraftPolygon | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const classes = settings.data?.processing.classes.length ? settings.data.processing.classes : (settings.data?.supported_classes ?? [])

  const list = useMemo(() => zones.data ?? [], [zones.data])
  const nextColor = ZONE_COLORS[list.length % ZONE_COLORS.length]

  const startCreate = (points: Point[] = []) => {
    setMode({ kind: 'create' })
    setDraft({ points, closed: points.length >= 3, color: nextColor })
    setSelectedId(null)
    setError(null)
  }

  const startEdit = (z: Zone) => {
    setMode({ kind: 'edit', zone: z })
    setDraft({ points: z.polygon, closed: true, color: z.color })
    setSelectedId(z.id)
    setError(null)
  }

  const cancel = useCallback(() => {
    setMode({ kind: 'idle' })
    setDraft(null)
    setError(null)
  }, [])

  const undo = useCallback(() => {
    setDraft((d) => (d ? (d.closed && mode.kind === 'create' ? { ...d, closed: false } : { ...d, closed: false, points: d.points.slice(0, -1) }) : d))
  }, [mode.kind])

  useEffect(() => {
    if (!draft) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select')) return
      if (e.key === 'Escape') cancel()
      else if (e.key === 'Backspace' || (e.key === 'z' && (e.ctrlKey || e.metaKey))) {
        e.preventDefault()
        undo()
      } else if (e.key === 'Enter' && !draft.closed && draft.points.length >= 3) setDraft({ ...draft, closed: true })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [draft, cancel, undo])

  const onColorChange = useCallback((c: string) => {
    if (/^#[0-9a-fA-F]{6}$/.test(c)) setDraft((d) => (d && d.color !== c ? { ...d, color: c } : d))
  }, [])

  const save = async (v: ZoneFormValues) => {
    if (!draft) return
    const problem = draft.closed ? polygonProblem(draft.points) : 'Close the polygon first (click the first point, double-click, or press Enter).'
    if (problem) {
      setError(problem)
      return
    }
    const body: ZoneInput = { ...v, polygon: draft.points, class_filter: v.class_filter.length ? v.class_filter : null }
    try {
      if (mode.kind === 'edit') {
        await m.update.mutateAsync({ id: mode.zone.id, body })
      } else {
        const z = await m.create.mutateAsync(body)
        setSelectedId(z.id)
      }
      cancel()
    } catch {
      // toast already shown by the mutation
    }
  }

  const defaults: ZoneFormInput =
    mode.kind === 'edit'
      ? {
          name: mode.zone.name,
          zone_type: mode.zone.zone_type,
          color: mode.zone.color,
          enabled: mode.zone.enabled,
          emit_entries: mode.zone.emit_entries,
          emit_exits: mode.zone.emit_exits,
          occupancy_threshold: mode.zone.occupancy_threshold ?? '',
          class_filter: mode.zone.class_filter ?? [],
        }
      : {
          name: `Zone ${list.length + 1}`,
          zone_type: 'general',
          color: nextColor,
          enabled: true,
          ...TYPE_DEFAULTS.general,
          occupancy_threshold: '',
          class_filter: [],
        }

  const visibleZones = useMemo(() => list.filter((z) => !(mode.kind === 'edit' && z.id === mode.zone.id)), [list, mode])
  const saving = m.create.isPending || m.update.isPending

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <div className="space-y-3 xl:col-span-8">
        <VideoStage
          video={video}
          zones={visibleZones}
          highlightZoneId={selectedId}
          draft={draft}
          onDraftChange={(d) => {
            setDraft(d)
            setError(null)
          }}
          showBoxes={false}
          showLabels={false}
        />
        {draft ? (
          <Card className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-xs">
            <span className="text-muted">
              {draft.closed ? (
                <>Polygon closed · drag vertices to adjust</>
              ) : (
                <>
                  Click to add points ({draft.points.length}) · close with first point, double-click or <Kbd>Enter</Kbd>
                </>
              )}
              {' · '}
              <Kbd>Backspace</Kbd> undo · <Kbd>Esc</Kbd> cancel
            </span>
            <div className="ml-auto flex gap-2">
              <Button size="xs" variant="outline" onClick={undo} disabled={draft.points.length === 0}>
                <Undo2 /> Undo
              </Button>
              {!draft.closed && (
                <Button size="xs" variant="outline" disabled={draft.points.length < 3} onClick={() => setDraft({ ...draft, closed: true })}>
                  <Check /> Close polygon
                </Button>
              )}
            </div>
          </Card>
        ) : (
          <p className="text-xs text-muted">
            Zones are stored in normalized frame coordinates (0–1), so they stay aligned at any player size. Pause on a representative frame
            before drawing. Membership is tested with each object's bottom-center point.
          </p>
        )}
      </div>

      <div className="space-y-4 xl:col-span-4">
        {mode.kind !== 'idle' ? (
          <Card>
            <CardHeader>
              <div>
                <CardTitle>{mode.kind === 'edit' ? `Edit “${mode.zone.name}”` : 'New zone'}</CardTitle>
                <CardDescription>
                  {video.current_job_id
                    ? 'Events are recomputed from stored detections when you save.'
                    : 'Events will be generated when the video is processed.'}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {mode.kind === 'create' && draft && draft.points.length === 0 && (
                <div>
                  <p className="mb-1.5 text-xs text-muted">Start from a template (optional):</p>
                  <div className="flex flex-wrap gap-1.5">
                    {TEMPLATES.map((t) => (
                      <Button key={t.label} size="xs" variant="outline" onClick={() => setDraft({ ...draft, points: t.points, closed: true })}>
                        {t.label}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              <ZoneForm
                key={mode.kind === 'edit' ? mode.zone.id : 'new'}
                id="zone-form"
                defaultValues={defaults}
                classes={classes}
                onSubmit={save}
                onColorChange={onColorChange}
              />
              {error && <p className="rounded-md bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={cancel}>
                  <X /> Cancel
                </Button>
                <Button size="sm" type="submit" form="zone-form" disabled={saving || !draft?.closed}>
                  {saving ? <Loader2 className="animate-spin" /> : <Check />} Save zone
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Button className="w-full" onClick={() => startCreate()}>
            <Plus /> Draw new zone
          </Button>
        )}

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Zones for this video</CardTitle>
              <CardDescription>{list.length} defined</CardDescription>
            </div>
            {video.current_job_id && list.length > 0 && (
              <Button size="xs" variant="outline" onClick={() => m.recompute.mutate()} disabled={m.recompute.isPending} title="Rebuild events with the current zone settings">
                {m.recompute.isPending ? <Loader2 className="animate-spin" /> : <RefreshCcw />} Recompute
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {zones.isLoading ? (
              <LoadingState className="py-4" />
            ) : zones.isError ? (
              <ErrorState error={zones.error} />
            ) : list.length === 0 ? (
              <p className="text-sm text-muted">No zones yet. Draw a polygon on the video to create one.</p>
            ) : (
              list.map((z) => (
                <div
                  key={z.id}
                  className={cn('rounded-md border px-3 py-2', selectedId === z.id ? 'border-primary/60 bg-primary/5' : 'border-border')}
                  onMouseEnter={() => mode.kind === 'idle' && setSelectedId(z.id)}
                >
                  <div className="flex items-center gap-2">
                    <span className="size-3 shrink-0 rounded-sm" style={{ background: z.color }} />
                    <div className="min-w-0 flex-1">
                      <p className={cn('truncate text-sm font-medium', !z.enabled && 'text-muted')}>{z.name}</p>
                      <p className="text-[11px] text-subtle">
                        {ZONE_TYPE_LABELS[z.zone_type]} · {z.polygon.length} pts
                        {z.occupancy_threshold != null && ` · max ${z.occupancy_threshold}`}
                        {z.class_filter?.length ? ` · ${z.class_filter.join(', ')}` : ''}
                      </p>
                    </div>
                    <Switch
                      checked={z.enabled}
                      onCheckedChange={(enabled) => m.update.mutate({ id: z.id, body: { enabled } })}
                      aria-label={`${z.enabled ? 'Disable' : 'Enable'} ${z.name}`}
                      disabled={mode.kind !== 'idle'}
                    />
                    <Button size="icon" variant="ghost" onClick={() => startEdit(z)} disabled={mode.kind !== 'idle'} aria-label={`Edit ${z.name}`}>
                      <Pencil />
                    </Button>
                    <ConfirmDialog
                      title="Delete zone?"
                      description={`“${z.name}” and all of its events will be deleted.`}
                      confirmLabel="Delete"
                      destructive
                      onConfirm={() => m.remove.mutateAsync(z.id)}
                      trigger={
                        <Button size="icon" variant="ghost" aria-label={`Delete ${z.name}`} disabled={mode.kind !== 'idle'}>
                          <Trash2 className="text-danger/80" />
                        </Button>
                      }
                    />
                  </div>
                  <div className="mt-1.5 grid grid-cols-4 gap-1 text-center text-[11px] tabular">
                    {[
                      ['Entries', z.stats.entries],
                      ['Exits', z.stats.exits],
                      ['Alerts', z.stats.occupancy_alerts + z.stats.restricted_entries],
                      ['Peak', z.stats.peak_occupancy ?? '—'],
                    ].map(([l, v]) => (
                      <div key={l} className="rounded bg-surface-2 py-1">
                        <div className="font-semibold">{v}</div>
                        <div className="text-subtle">{l}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function AllZonesTable() {
  const zones = useZones(undefined)
  const videos = useVideoOptions()
  const names = new Map(videos.data?.items.map((v) => [v.id, v.original_filename]))
  if (!zones.data?.length) return null
  return (
    <Card className="mt-6">
      <CardHeader>
        <div>
          <CardTitle>All monitoring zones</CardTitle>
          <CardDescription>Across every video</CardDescription>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="border-y border-border text-[11px] uppercase tracking-wider text-subtle">
            <tr>
              <th className="py-2 pl-4 font-medium">Zone</th>
              <th className="font-medium">Video</th>
              <th className="font-medium">Type</th>
              <th className="text-right font-medium">Entries</th>
              <th className="text-right font-medium">Exits</th>
              <th className="text-right font-medium">Alerts</th>
              <th className="pr-4 text-right font-medium">Peak occupancy</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {zones.data.map((z) => (
              <tr key={z.id} className="border-b border-border last:border-0 hover:bg-surface-2/50">
                <td className="py-2 pl-4">
                  <Link to={`/zones?video=${z.video_id}`} className="inline-flex items-center gap-2 hover:text-primary">
                    <span className="size-2.5 rounded-sm" style={{ background: z.color }} />
                    {z.name}
                    {!z.enabled && <span className="text-subtle">(disabled)</span>}
                  </Link>
                </td>
                <td className="max-w-56 truncate text-muted">{names.get(z.video_id) ?? '—'}</td>
                <td className="text-muted">{ZONE_TYPE_LABELS[z.zone_type]}</td>
                <td className="text-right">{z.stats.entries}</td>
                <td className="text-right">{z.stats.exits}</td>
                <td className="text-right">{z.stats.occupancy_alerts + z.stats.restricted_entries}</td>
                <td className="pr-4 text-right">{z.stats.peak_occupancy ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function ZonesPage() {
  const [params, setParams] = useSearchParams()
  const options = useVideoOptions()
  const videoId = params.get('video') ?? undefined
  const video = useVideo(videoId)

  useEffect(() => {
    if (!videoId && options.data?.items.length) setParams({ video: options.data.items[0].id }, { replace: true })
  }, [videoId, options.data, setParams])

  return (
    <>
      <PageHeader
        title="Monitoring Zones"
        description="Draw polygon zones on a video frame. Entry, exit, restricted-area and occupancy events are derived from tracked objects crossing these boundaries."
        actions={<VideoPicker value={videoId} onChange={(id) => setParams({ video: id })} />}
      />
      {options.isLoading || (videoId && video.isLoading) ? (
        <LoadingState />
      ) : !videoId ? (
        <Card>
          <EmptyState
            icon={<Hexagon />}
            title="No videos available"
            description="Zones are defined on a video's frame. Upload a video first."
            action={
              <Button asChild>
                <Link to="/videos?upload=1">Upload video</Link>
              </Button>
            }
          />
        </Card>
      ) : video.isError ? (
        <Card>
          <ErrorState error={video.error} onRetry={() => video.refetch()} />
        </Card>
      ) : video.data ? (
        <Editor key={video.data.id} video={video.data} />
      ) : null}
      <AllZonesTable />
    </>
  )
}

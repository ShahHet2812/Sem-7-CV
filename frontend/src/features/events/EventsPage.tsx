import { ArrowDown, ArrowUp, Check, Download, FilterX, Search, Siren, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, EventTypeBadge, LoadingState, PageHeader, Pagination, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, Input, Select } from '@/components/ui/primitives'
import { useEvents, useEventStatus, useSettings, useVideoOptions, useZones } from '@/hooks/queries'
import { cn, EVENT_LABELS, formatDateTime, formatDuration, toIsoOrUndefined } from '@/lib/utils'
import { eventsApi } from '@/services/resources'
import type { EventFilters, EventType, MonitoringEvent } from '@/types/api'
import { EventDetails } from './EventDetails'

type SortKey = NonNullable<EventFilters['sort']>

export default function EventsPage() {
  const [params, setParams] = useSearchParams()
  const [qInput, setQInput] = useState(params.get('q') ?? '')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detail, setDetail] = useState<MonitoringEvent | null>(null)
  const videos = useVideoOptions()
  const settings = useSettings()
  const status = useEventStatus()

  const get = (k: string) => params.get(k) ?? ''
  const filters: EventFilters = {
    q: get('q') || undefined,
    video_id: get('video_id') || undefined,
    zone_id: get('zone_id') || undefined,
    event_type: params.get('alerts') ? 'alerts' : ((get('event_type') as EventType) || ''),
    class_name: get('class_name') || undefined,
    status: (get('status') as EventFilters['status']) || '',
    date_from: toIsoOrUndefined(get('from')),
    date_to: toIsoOrUndefined(get('to')),
    sort: (get('sort') as SortKey) || 'occurred_at',
    order: (get('order') as 'asc' | 'desc') || 'desc',
    page: Number(get('page')) || 1,
    page_size: 25,
  }
  const events = useEvents(filters)
  const zones = useZones(filters.video_id)

  const update = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (!('page' in patch)) next.delete('page')
    setParams(next, { replace: true })
    setSelected(new Set())
  }

  useEffect(() => {
    const t = setTimeout(() => {
      if (qInput !== get('q')) update({ q: qInput || undefined })
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput])

  const toggleSort = (key: SortKey) => {
    if (filters.sort === key) update({ order: filters.order === 'desc' ? 'asc' : 'desc' })
    else update({ sort: key, order: 'desc' })
  }

  const items = events.data?.items ?? []
  const allSelected = items.length > 0 && items.every((e) => selected.has(e.id))
  const hasFilters = [...params.keys()].some((k) => !['sort', 'order', 'page'].includes(k))
  const classes = settings.data?.processing.classes ?? []
  const typeValue = params.get('alerts') ? 'alerts' : get('event_type')

  const SortHead = ({ k, label, className }: { k: SortKey; label: string; className?: string }) => (
    <th className={cn('font-medium', className)}>
      <button onClick={() => toggleSort(k)} className="inline-flex items-center gap-1 uppercase hover:text-foreground">
        {label}
        {filters.sort === k && (filters.order === 'desc' ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </th>
  )

  const exportHref = useMemo(() => eventsApi.exportUrl({ ...filters }), [params]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader
        title="Events & Alerts"
        description="Zone transitions, restricted-area entries, occupancy alerts and processing failures — all derived from processed video."
        actions={
          <Button variant="outline" asChild>
            <a href={exportHref} download>
              <Download /> Export CSV
            </a>
          </Button>
        }
      />

      <Card>
        <div className="grid gap-2 border-b border-border p-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8">
          <div className="relative sm:col-span-2">
            <Search className="absolute left-2.5 top-2.5 size-4 text-subtle" />
            <Input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search video, zone, class, notes…" className="pl-8" aria-label="Search events" />
          </div>
          <Select value={get('video_id')} onChange={(e) => update({ video_id: e.target.value, zone_id: undefined })} aria-label="Video">
            <option value="">All videos</option>
            {videos.data?.items.map((v) => (
              <option key={v.id} value={v.id}>
                {v.original_filename}
              </option>
            ))}
          </Select>
          <Select value={get('zone_id')} onChange={(e) => update({ zone_id: e.target.value })} aria-label="Zone">
            <option value="">All zones</option>
            {zones.data?.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name}
              </option>
            ))}
          </Select>
          <Select
            value={typeValue}
            onChange={(e) =>
              e.target.value === 'alerts' ? update({ alerts: '1', event_type: undefined }) : update({ event_type: e.target.value, alerts: undefined })
            }
            aria-label="Event type"
          >
            <option value="">All event types</option>
            <option value="alerts">Alerts only</option>
            {(Object.keys(EVENT_LABELS) as EventType[]).map((t) => (
              <option key={t} value={t}>
                {EVENT_LABELS[t]}
              </option>
            ))}
          </Select>
          <Select value={get('class_name')} onChange={(e) => update({ class_name: e.target.value })} aria-label="Object class">
            <option value="">All classes</option>
            {classes.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <Select value={get('status')} onChange={(e) => update({ status: e.target.value })} aria-label="Review status">
            <option value="">Any status</option>
            <option value="new">New</option>
            <option value="reviewed">Reviewed</option>
            <option value="dismissed">Dismissed</option>
          </Select>
          <Input type="datetime-local" value={get('from')} onChange={(e) => update({ from: e.target.value })} aria-label="From date" title="From" />
          <Input type="datetime-local" value={get('to')} onChange={(e) => update({ to: e.target.value })} aria-label="To date" title="To" />
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={() => { setQInput(''); setParams({}, { replace: true }) }}>
              <FilterX /> Clear filters
            </Button>
          )}
        </div>

        {selected.size > 0 && (
          <div className="flex items-center gap-2 border-b border-border bg-primary/5 px-4 py-2 text-xs">
            <span>{selected.size} selected</span>
            <Button size="xs" onClick={() => status.mutate({ ids: [...selected], status: 'reviewed' }, { onSuccess: () => setSelected(new Set()) })}>
              <Check /> Mark reviewed
            </Button>
            <Button size="xs" variant="outline" onClick={() => status.mutate({ ids: [...selected], status: 'dismissed' }, { onSuccess: () => setSelected(new Set()) })}>
              <X /> Dismiss
            </Button>
            <Button size="xs" variant="ghost" onClick={() => setSelected(new Set())}>
              Clear selection
            </Button>
          </div>
        )}

        {events.isLoading ? (
          <LoadingState />
        ) : events.isError ? (
          <ErrorState error={events.error} onRetry={() => events.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Siren />}
            title={hasFilters ? 'No events match these filters' : 'No events yet'}
            description={
              hasFilters
                ? 'Try widening the date range or clearing filters.'
                : 'Process a video and define at least one zone. Events are generated when tracked objects cross zone boundaries.'
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1000px] text-left text-sm">
                <thead className="border-b border-border text-[11px] uppercase tracking-wider text-subtle">
                  <tr>
                    <th className="w-10 py-2 pl-4">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((e) => e.id)))}
                        aria-label="Select all on page"
                        className="accent-[var(--color-primary)]"
                      />
                    </th>
                    <SortHead k="occurred_at" label="Time" />
                    <SortHead k="event_type" label="Event" />
                    <th className="font-medium">Zone</th>
                    <th className="font-medium">Video</th>
                    <SortHead k="class_name" label="Object" />
                    <SortHead k="confidence" label="Conf." className="text-right" />
                    <th className="pr-4 text-right font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((e) => (
                    <tr key={e.id} className="cursor-pointer border-b border-border last:border-0 hover:bg-surface-2/60" onClick={() => setDetail(e)}>
                      <td className="py-2 pl-4" onClick={(ev) => ev.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected.has(e.id)}
                          onChange={() =>
                            setSelected((s) => {
                              const n = new Set(s)
                              if (n.has(e.id)) n.delete(e.id)
                              else n.add(e.id)
                              return n
                            })
                          }
                          aria-label="Select event"
                          className="accent-[var(--color-primary)]"
                        />
                      </td>
                      <td className="whitespace-nowrap text-xs">
                        <div>{formatDateTime(e.occurred_at)}</div>
                        {e.video_timestamp != null && <div className="font-mono text-subtle">video {formatDuration(e.video_timestamp, true)}</div>}
                      </td>
                      <td>
                        <EventTypeBadge type={e.event_type} severity={e.severity} />
                      </td>
                      <td className="text-xs">
                        {e.zone_name ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="size-2 rounded-sm" style={{ background: e.zone_color ?? undefined }} />
                            {e.zone_name}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="max-w-48 truncate text-xs text-muted">{e.video_name}</td>
                      <td className="text-xs">
                        {e.class_name ?? (e.occupancy != null ? `${e.occupancy} objects` : '—')}
                        {e.track_id != null && <span className="text-subtle"> #{e.track_id}</span>}
                      </td>
                      <td className="text-right text-xs tabular">{e.confidence != null ? `${(e.confidence * 100).toFixed(0)}%` : '—'}</td>
                      <td className="pr-4 text-right">
                        <StatusBadge status={e.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={events.data!.page} pages={events.data!.pages} total={events.data!.total} onChange={(p) => update({ page: String(p) })} />
          </>
        )}
      </Card>
      <p className="mt-3 text-xs text-subtle">
        Times use the video's recording start (if provided at upload) or its upload time plus the position in the video. Track IDs are short-term
        tracker identities and may change after occlusions.
      </p>
      <EventDetails event={detail} onClose={() => setDetail(null)} />
    </>
  )
}

import { useQuery } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AnalyticsFilterBar, useAnalyticsFilters } from '@/components/AnalyticsFilterBar'
import { CHART, ChartCard } from '@/components/charts'
import { PageHeader } from '@/components/common'
import { Card, CardContent, CardHeader, CardTitle, Select } from '@/components/ui/primitives'
import { useAnalytics, useOverview } from '@/hooks/queries'
import { classColor, EVENT_LABELS, formatDuration, formatNumber } from '@/lib/utils'
import { zonesApi } from '@/services/resources'
import type { EventType } from '@/types/api'

const TYPE_COLORS: Record<string, string> = {
  zone_entry: '#34d399',
  zone_exit: '#a78bfa',
  restricted_entry: '#f87171',
  occupancy_exceeded: '#fbbf24',
  processing_failure: '#fb7185',
}

function OccupancyChart({ zoneOptions }: { zoneOptions: { id: string; name: string; video: string }[] }) {
  const [zoneId, setZoneId] = useState<string>('')
  useEffect(() => {
    if (!zoneOptions.some((z) => z.id === zoneId)) setZoneId(zoneOptions[0]?.id ?? '')
  }, [zoneOptions, zoneId])
  const series = useQuery({ queryKey: ['analytics', 'occupancy', zoneId], queryFn: () => zonesApi.occupancy(zoneId), enabled: !!zoneId })
  return (
    <ChartCard
      title="Zone occupancy over time"
      description="Tracks confirmed inside the zone, on the video timeline (step function of change points)"
      loading={series.isLoading && !!zoneId}
      error={series.error}
      empty={!zoneId || !series.data?.length}
      emptyText={zoneOptions.length ? 'No occupancy samples for this zone yet.' : 'No zones defined.'}
      action={
        zoneOptions.length > 0 && (
          <Select value={zoneId} onChange={(e) => setZoneId(e.target.value)} className="h-8 w-52 text-xs" aria-label="Zone">
            {zoneOptions.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name} — {z.video}
              </option>
            ))}
          </Select>
        )
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series.data} margin={{ left: -10, right: 12 }}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(v) => formatDuration(v)} tick={CHART.tick} stroke={CHART.axis} />
          <YAxis allowDecimals={false} tick={CHART.tick} stroke={CHART.axis} />
          <Tooltip {...CHART.tooltip} labelFormatter={(v) => `t = ${formatDuration(Number(v), true)}`} />
          <Line type="stepAfter" dataKey="occupancy" name="Occupancy" stroke={CHART.colors.detections} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export default function AnalyticsPage() {
  const [filters] = useAnalyticsFilters()
  const a = useAnalytics(filters)
  const overview = useOverview(filters, false)

  const eventsByType = useMemo(
    () =>
      Object.entries(overview.data?.events_by_type ?? {}).map(([type, count]) => ({
        type,
        label: EVENT_LABELS[type as EventType] ?? type,
        count,
      })),
    [overview.data],
  )
  const zoneOptions = useMemo(
    () => (a.zones.data ?? []).map((z) => ({ id: z.zone_id, name: z.zone_name, video: z.video_name })),
    [a.zones.data],
  )
  const perf = useMemo(
    () => (a.performance.data ?? []).slice(0, 12).reverse().map((p, i) => ({ ...p, label: `${i + 1}. ${p.video_name.slice(0, 18)}` })),
    [a.performance.data],
  )

  return (
    <>
      <PageHeader title="Analytics" description="Charts computed on the server from persisted detections, tracks and zone events of each video's current processing job." />
      <AnalyticsFilterBar />

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Detections and track IDs by class" loading={a.classes.isLoading} error={a.classes.error} empty={!a.classes.data?.length}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a.classes.data} margin={{ left: -10, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="class_name" tick={CHART.tick} stroke={CHART.axis} />
              <YAxis yAxisId="d" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <YAxis yAxisId="t" orientation="right" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <Tooltip {...CHART.tooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="d" dataKey="detections" name="Detections" radius={[4, 4, 0, 0]}>
                {a.classes.data?.map((c) => <Cell key={c.class_name} fill={classColor(c.class_name)} />)}
              </Bar>
              <Bar yAxisId="t" dataKey="tracks" name="Track IDs" fill={CHART.colors.tracks} fillOpacity={0.55} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Entries and exits over time"
          description={a.activity.data?.mode === 'video_time' ? `Video timeline · ${a.activity.data.bucket_size} buckets` : `Wall clock · per ${a.activity.data?.bucket_size ?? 'hour'}`}
          loading={a.activity.isLoading}
          error={a.activity.error}
          empty={!a.activity.data?.points.some((p) => p.entries || p.exits || p.alerts)}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={a.activity.data?.points} margin={{ left: -10, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="label" tick={CHART.tick} stroke={CHART.axis} minTickGap={24} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <Tooltip {...CHART.tooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="entries" name="Entries" stroke={CHART.colors.entries} dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="exits" name="Exits" stroke={CHART.colors.exits} dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="alerts" name="Alerts" stroke={CHART.colors.alerts} dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <OccupancyChart zoneOptions={zoneOptions} />

        <ChartCard title="Entries and exits by zone" loading={a.zones.isLoading} error={a.zones.error} empty={!a.zones.data?.length} emptyText="No zones defined.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a.zones.data?.slice(0, 10)} margin={{ left: -10, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="zone_name" tick={CHART.tick} stroke={CHART.axis} interval={0} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <Tooltip {...CHART.tooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="entries" name="Entries" fill={CHART.colors.entries} radius={[4, 4, 0, 0]} />
              <Bar dataKey="exits" name="Exits" fill={CHART.colors.exits} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Events by type" loading={overview.isLoading} error={overview.error} empty={eventsByType.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={eventsByType} layout="vertical" margin={{ left: 30, right: 16 }}>
              <CartesianGrid stroke={CHART.grid} horizontal={false} />
              <XAxis type="number" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <YAxis type="category" dataKey="label" tick={CHART.tick} stroke={CHART.axis} width={120} />
              <Tooltip {...CHART.tooltip} />
              <Bar dataKey="count" name="Events" radius={[0, 4, 4, 0]}>
                {eventsByType.map((e) => <Cell key={e.type} fill={TYPE_COLORS[e.type] ?? '#60a5fa'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Video processing performance"
          description="Sampled frames processed per second (inference + tracking + persistence), last completed jobs"
          loading={a.performance.isLoading}
          error={a.performance.error}
          empty={!perf.length}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={perf} margin={{ left: -10, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="label" tick={CHART.tick} stroke={CHART.axis} interval={0} angle={-15} textAnchor="end" height={50} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} />
              <Tooltip
                {...CHART.tooltip}
                formatter={(v, n, item) =>
                  n === 'Sampled fps'
                    ? [`${v} fps (${item.payload.realtime_factor ?? '—'}× realtime, ${item.payload.device ?? '?'})`, n]
                    : [v, n]
                }
              />
              <Bar dataKey="sampled_fps" name="Sampled fps" fill={CHART.colors.detections} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Top monitored zones</CardTitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-xs">
              <thead className="border-y border-border text-[11px] uppercase tracking-wider text-subtle">
                <tr>
                  <th className="py-2 pl-4 font-medium">Zone</th>
                  <th className="font-medium">Video</th>
                  <th className="text-right font-medium">Entries</th>
                  <th className="text-right font-medium">Exits</th>
                  <th className="text-right font-medium">Restricted</th>
                  <th className="text-right font-medium">Occupancy alerts</th>
                  <th className="pr-4 text-right font-medium">Peak</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {(a.zones.data ?? []).slice(0, 10).map((z) => (
                  <tr key={z.zone_id} className="border-b border-border last:border-0">
                    <td className="py-2 pl-4">
                      <span className="mr-2 inline-block size-2.5 rounded-sm align-middle" style={{ background: z.color }} />
                      {z.zone_name}
                    </td>
                    <td className="max-w-48 truncate text-muted">{z.video_name}</td>
                    <td className="text-right">{formatNumber(z.entries)}</td>
                    <td className="text-right">{formatNumber(z.exits)}</td>
                    <td className="text-right">{formatNumber(z.restricted_entries)}</td>
                    <td className="text-right">{formatNumber(z.occupancy_alerts)}</td>
                    <td className="pr-4 text-right">{z.peak_occupancy ?? '—'}</td>
                  </tr>
                ))}
                {!a.zones.data?.length && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-muted">
                      No zones yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="size-4 text-primary" /> How metrics are calculated
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-muted">
            <p>
              <b className="text-foreground">Detections</b> count boxes on <i>sampled</i> frames. An object visible on 30 sampled frames counts 30 times.
            </p>
            <p>
              <b className="text-foreground">Track IDs</b> are distinct tracker identities. Occlusion or leaving the frame can give the same person a
              new ID, so this is an upper bound on distinct objects, not a people count.
            </p>
            <p>
              <b className="text-foreground">Entries / exits</b> are confirmed outside↔inside transitions of a track's bottom-center point. An object
              first seen inside a zone does not count as an entry.
            </p>
            <p>
              <b className="text-foreground">Occupancy</b> is the number of live tracks confirmed inside a zone. Missed detections, occlusion and
              sampling can under- or over-estimate it.
            </p>
            <p>Only each video's current (latest successful) job is counted, so reprocessing never double counts.</p>
          </CardContent>
        </Card>
      </div>
    </>
  )
}

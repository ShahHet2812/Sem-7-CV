import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Boxes, DoorClosed, DoorOpen, Film, Fingerprint, Hexagon, Play, ScanSearch, ShieldAlert, Sparkles, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AnalyticsFilterBar, useAnalyticsFilters } from '@/components/AnalyticsFilterBar'
import { CHART, ChartCard } from '@/components/charts'
import { EmptyState, ErrorState, EventTypeBadge, LoadingState, PageHeader, StatCard, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, Progress } from '@/components/ui/primitives'
import { useImportSample, useOverview } from '@/hooks/queries'
import { classColor, formatDuration, formatNumber, formatRelative } from '@/lib/utils'
import { analyticsApi } from '@/services/resources'

const STATUS_COLORS: Record<string, string> = {
  uploaded: '#5d6779',
  queued: '#60a5fa',
  processing: '#22d3ee',
  completed: '#34d399',
  failed: '#f87171',
  cancelled: '#fbbf24',
}

function Onboarding() {
  const sample = useImportSample()
  const steps = [
    { icon: Upload, title: 'Add footage', text: 'Upload an MP4/MOV/AVI/MKV/WEBM file, or import the public sample clip.' },
    { icon: Play, title: 'Process it', text: 'YOLO detects objects on sampled frames and ByteTrack links them into tracks.' },
    { icon: Hexagon, title: 'Draw zones', text: 'Click polygon zones on a frame. Entry/exit events are derived from tracked anchor points.' },
    { icon: ScanSearch, title: 'Review', text: 'Play back with overlays, review alerts, explore analytics and export CSV.' },
  ]
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-gradient-to-br from-primary/10 to-transparent px-6 py-6">
        <h2 className="text-lg font-semibold">Welcome to ZoneVision</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Vision-based object detection and zone monitoring. Nothing here is simulated: every number on this dashboard is computed from
          videos you process. Start by adding a video.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild>
            <Link to="/videos?upload=1">
              <Upload /> Upload a video
            </Link>
          </Button>
          <Button variant="outline" onClick={() => sample.mutate()} disabled={sample.isPending}>
            <Sparkles /> {sample.isPending ? 'Downloading sample…' : 'Quick sample'}
          </Button>
          <Button variant="outline" asChild>
            <Link to="/videos?samples=1">Browse sample library</Link>
          </Button>
        </div>
        <p className="mt-2 text-xs text-subtle">
          Samples are CC BY 4.0 (Intel sample-videos) or public domain (Wikimedia Commons), downloaded only on request. The library includes
          a restricted-zone demo with preset zones.
        </p>
      </div>
      <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((s, i) => (
          <div key={s.title} className="bg-surface p-5">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">{i + 1}</span>
              <s.icon className="size-4 text-muted" />
            </div>
            <p className="text-sm font-medium">{s.title}</p>
            <p className="mt-1 text-xs text-muted">{s.text}</p>
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function DashboardPage() {
  const [filters] = useAnalyticsFilters()
  const overview = useOverview(filters)
  const classes = useQuery({ queryKey: ['analytics', 'detections', filters], queryFn: () => analyticsApi.detections(filters) })
  const activity = useQuery({ queryKey: ['analytics', 'activity', filters], queryFn: () => analyticsApi.activity(filters) })
  const zones = useQuery({ queryKey: ['analytics', 'zones', filters], queryFn: () => analyticsApi.zones(filters) })
  const o = overview.data

  if (overview.isLoading) return <LoadingState />
  if (overview.isError) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
  if (o && o.total_videos === 0 && !filters.video_id)
    return (
      <>
        <PageHeader title="Overview" />
        <Onboarding />
      </>
    )

  const statusData = Object.entries(o?.video_status ?? {}).map(([name, value]) => ({ name, value }))
  const activityEmpty = !activity.data?.points.some((p) => p.detections || p.entries || p.exits)

  return (
    <>
      <PageHeader
        title="Overview"
        description="Live summary of processed footage, tracked objects and zone activity."
        actions={
          <Button variant="outline" asChild>
            <Link to="/videos">
              <Film /> Video library
            </Link>
          </Button>
        }
      />
      <AnalyticsFilterBar />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Videos" value={formatNumber(o?.total_videos)} hint={`${o?.processed_videos ?? 0} processed`} icon={<Film />} />
        <StatCard label="Detections" value={formatNumber(o?.total_detections)} hint="boxes on sampled frames" icon={<Boxes />} tone="primary" />
        <StatCard
          label="Track IDs"
          value={formatNumber(o?.unique_tracks)}
          hint="tracker IDs, not unique people"
          icon={<Fingerprint />}
          tone="primary"
        />
        <StatCard label="Zone entries" value={formatNumber(o?.zone_entries)} hint={`${o?.restricted_entries ?? 0} restricted`} icon={<DoorOpen />} tone="success" />
        <StatCard label="Zone exits" value={formatNumber(o?.zone_exits)} hint={`${o?.total_zones ?? 0} zone(s) defined`} icon={<DoorClosed />} />
        <StatCard
          label="Unreviewed alerts"
          value={formatNumber(o?.unreviewed_alerts)}
          hint={`${o?.occupancy_alerts ?? 0} occupancy · ${o?.processing_failures ?? 0} failures`}
          icon={<ShieldAlert />}
          tone={o?.unreviewed_alerts ? 'danger' : 'default'}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <ChartCard
            title="Activity over time"
            description={
              activity.data?.mode === 'video_time'
                ? `Video timeline, ${activity.data.bucket_size} buckets`
                : `Wall-clock time (recording start + video offset), per ${activity.data?.bucket_size ?? 'hour'}`
            }
            loading={activity.isLoading}
            error={activity.error}
            empty={activityEmpty}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={activity.data?.points} margin={{ left: -10, right: 8, top: 4 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                <XAxis dataKey="label" tick={CHART.tick} stroke={CHART.axis} minTickGap={24} />
                <YAxis yAxisId="d" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
                <YAxis yAxisId="e" orientation="right" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
                <Tooltip {...CHART.tooltip} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area yAxisId="d" type="monotone" dataKey="detections" name="Detections" stroke={CHART.colors.detections} fill={CHART.colors.detections} fillOpacity={0.15} />
                <Area yAxisId="e" type="stepAfter" dataKey="entries" name="Entries" stroke={CHART.colors.entries} fill={CHART.colors.entries} fillOpacity={0.2} />
                <Area yAxisId="e" type="stepAfter" dataKey="exits" name="Exits" stroke={CHART.colors.exits} fill={CHART.colors.exits} fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
        <ChartCard title="Processing status" description="Videos by current status" empty={statusData.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2} stroke="none">
                {statusData.map((d) => (
                  <Cell key={d.name} fill={STATUS_COLORS[d.name] ?? '#5d6779'} />
                ))}
              </Pie>
              <Tooltip {...CHART.tooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => <span className="capitalize text-muted">{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <ChartCard title="Detections by class" loading={classes.isLoading} error={classes.error} empty={!classes.data?.length}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={classes.data} layout="vertical" margin={{ left: 10, right: 16 }}>
              <CartesianGrid stroke={CHART.grid} horizontal={false} />
              <XAxis type="number" tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <YAxis type="category" dataKey="class_name" tick={CHART.tick} stroke={CHART.axis} width={80} />
              <Tooltip {...CHART.tooltip} />
              <Bar dataKey="detections" name="Detections" radius={[0, 4, 4, 0]}>
                {classes.data?.map((c) => <Cell key={c.class_name} fill={classColor(c.class_name)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Events by zone"
          loading={zones.isLoading}
          error={zones.error}
          empty={!zones.data?.some((z) => z.total_events)}
          emptyText="No zone events yet. Draw zones on processed videos."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={zones.data?.slice(0, 8)} margin={{ left: -10, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="zone_name" tick={CHART.tick} stroke={CHART.axis} interval={0} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} allowDecimals={false} />
              <Tooltip {...CHART.tooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="entries" name="Entries" fill={CHART.colors.entries} radius={[4, 4, 0, 0]} />
              <Bar dataKey="exits" name="Exits" fill={CHART.colors.exits} radius={[4, 4, 0, 0]} />
              <Bar dataKey="occupancy_alerts" name="Occupancy alerts" fill={CHART.colors.alerts} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent processing jobs</CardTitle>
            <Button size="xs" variant="ghost" asChild>
              <Link to="/videos">
                All videos <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {!o?.recent_jobs.length ? (
              <EmptyState className="py-6" title="No jobs yet" description="Start processing from the Video Library." />
            ) : (
              <ul className="divide-y divide-border">
                {o.recent_jobs.map((j) => (
                  <li key={j.id} className="flex items-center gap-3 py-2.5 text-sm">
                    <div className="min-w-0 flex-1">
                      <Link to={`/analysis/${j.video_id}`} className="block truncate hover:text-primary">
                        {j.video_name}
                      </Link>
                      <p className="text-xs text-muted">
                        {formatRelative(j.created_at)}
                        {j.status === 'completed' && ` · ${formatNumber(j.detection_count)} detections · ${j.event_count} events`}
                        {j.status === 'failed' && j.error_message && ` · ${j.error_message}`}
                      </p>
                      {(j.status === 'processing' || j.status === 'queued') && (
                        <Progress value={j.progress} indeterminate={j.progress == null} className="mt-1.5 h-1" />
                      )}
                    </div>
                    <StatusBadge status={j.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent monitoring events</CardTitle>
            <Button size="xs" variant="ghost" asChild>
              <Link to="/events">
                All events <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {!o?.recent_events.length ? (
              <EmptyState className="py-6" title="No events yet" description="Events are generated when tracked objects cross zone boundaries." />
            ) : (
              <ul className="divide-y divide-border">
                {o.recent_events.map((e) => (
                  <li key={e.id} className="flex items-center gap-3 py-2.5 text-sm">
                    <EventTypeBadge type={e.event_type} severity={e.severity} />
                    <span className="min-w-0 flex-1 truncate text-xs text-muted">
                      {e.zone_name && `${e.zone_name} · `}
                      {e.class_name && `${e.class_name}${e.track_id != null ? ` #${e.track_id}` : ''} · `}
                      {e.video_name}
                    </span>
                    {e.video_timestamp != null ? (
                      <Link to={`/analysis/${e.video_id}?t=${e.video_timestamp}&event=${e.id}`} className="font-mono text-xs text-primary hover:underline">
                        {formatDuration(e.video_timestamp, true)}
                      </Link>
                    ) : (
                      <span className="text-xs text-muted">{formatRelative(e.occurred_at)}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  )
}

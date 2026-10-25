import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/api'
import { analyticsApi, eventsApi, jobsApi, settingsApi, zonesApi } from '@/services/resources'
import { videosApi, type VideoListParams } from '@/services/videos'
import type { AnalyticsFilters, EventFilters, EventStatus, Page, Video, ZoneInput } from '@/types/api'

export const qk = {
  videos: (p?: VideoListParams) => ['videos', p ?? {}] as const,
  video: (id: string) => ['video', id] as const,
  jobs: (p?: object) => ['jobs', p ?? {}] as const,
  zones: (videoId?: string) => ['zones', videoId ?? 'all'] as const,
  events: (f?: EventFilters) => ['events', f ?? {}] as const,
  analytics: (kind: string, f?: AnalyticsFilters) => ['analytics', kind, f ?? {}] as const,
  settings: ['settings'] as const,
  health: ['health'] as const,
}

const ACTIVE = new Set(['queued', 'processing'])

export function useVideos(params: VideoListParams) {
  return useQuery({
    queryKey: qk.videos(params),
    queryFn: () => videosApi.list(params),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((v) => ACTIVE.has(v.status)) ? 2000 : false),
  })
}

/** Small list for selectors (most recent first). */
export function useVideoOptions() {
  return useQuery({
    queryKey: qk.videos({ page_size: 200 }),
    queryFn: () => videosApi.list({ page_size: 200 }),
    staleTime: 10_000,
  })
}

export function useVideo(id: string | undefined) {
  return useQuery({
    queryKey: qk.video(id ?? ''),
    queryFn: () => videosApi.get(id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.status) ? 1500 : false),
  })
}

export function useInvalidateAll() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['videos', 'video', 'jobs', 'zones', 'events', 'analytics', 'video-events', 'detections'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    )
}

export function useProcessVideo() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (id: string) => videosApi.process(id),
    onSuccess: (job) => {
      toast.success('Processing queued', { description: job.video_name ?? undefined })
      invalidate()
    },
    onError: (e) => toast.error('Could not start processing', { description: errorMessage(e) }),
  })
}

export function useDeleteVideo() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (v: Video) => videosApi.remove(v.id),
    onSuccess: (_, v) => {
      toast.success('Video deleted', { description: v.original_filename })
      invalidate()
    },
    onError: (e) => toast.error('Delete failed', { description: errorMessage(e) }),
  })
}

export function useImportSample() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: () => videosApi.importSample(),
    onSuccess: () => {
      toast.success('Sample video imported')
      invalidate()
    },
    onError: (e) => toast.error('Sample import failed', { description: errorMessage(e) }),
  })
}

export function useJobs(params: { video_id?: string; status?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: qk.jobs(params),
    queryFn: () => jobsApi.list(params),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((j) => ACTIVE.has(j.status)) ? 2000 : 10_000),
  })
}

export function useJobAction() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'retry' | 'cancel' }) =>
      action === 'retry' ? jobsApi.retry(id) : jobsApi.cancel(id),
    onSuccess: (job, { action }) => {
      toast.success(action === 'retry' ? 'Job re-queued' : job.status === 'cancelled' ? 'Job cancelled' : 'Cancellation requested')
      invalidate()
    },
    onError: (e) => toast.error('Action failed', { description: errorMessage(e) }),
  })
}

export function useZones(videoId: string | undefined) {
  return useQuery({
    queryKey: qk.zones(videoId),
    queryFn: () => (videoId ? zonesApi.forVideo(videoId) : zonesApi.all()),
  })
}

export function useZoneMutations(videoId: string | undefined) {
  const invalidate = useInvalidateAll()
  const onError = (e: unknown) => toast.error('Zone not saved', { description: errorMessage(e) })
  return {
    create: useMutation({
      mutationFn: (body: ZoneInput) => zonesApi.create(videoId!, body),
      onSuccess: (z) => {
        toast.success(`Zone “${z.name}” created`)
        invalidate()
      },
      onError,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Partial<ZoneInput> }) => zonesApi.update(id, body),
      onSuccess: () => invalidate(),
      onError,
    }),
    remove: useMutation({
      mutationFn: (id: string) => zonesApi.remove(id),
      onSuccess: () => {
        toast.success('Zone deleted')
        invalidate()
      },
      onError: (e) => toast.error('Delete failed', { description: errorMessage(e) }),
    }),
    recompute: useMutation({
      mutationFn: () => zonesApi.recompute(videoId!),
      onSuccess: (r) => {
        toast.success(`Recomputed ${r.events} event(s) for ${r.zones} zone(s)`)
        invalidate()
      },
      onError,
    }),
  }
}

export function useEvents(filters: EventFilters) {
  return useQuery({
    queryKey: qk.events(filters),
    queryFn: () => eventsApi.list(filters),
    placeholderData: keepPreviousData,
  })
}

export function useVideoEvents(videoId: string | undefined) {
  return useQuery({
    queryKey: ['video-events', videoId],
    queryFn: () => videosApi.events(videoId!),
    enabled: !!videoId,
  })
}

export function useEventStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, status }: { ids: string[]; status: EventStatus }) =>
      ids.length === 1 ? eventsApi.update(ids[0], { status }).then(() => ({ updated: 1 })) : eventsApi.bulkStatus(ids, status),
    onSuccess: (r, { status }) => {
      toast.success(`${r.updated} event(s) marked ${status}`)
      ;['events', 'analytics', 'video-events'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
    },
    onError: (e) => toast.error('Update failed', { description: errorMessage(e) }),
  })
}

export function useOverview(f: AnalyticsFilters = {}, refetchMs: number | false = 10_000) {
  return useQuery({
    queryKey: qk.analytics('overview', f),
    queryFn: () => analyticsApi.overview(f),
    refetchInterval: refetchMs,
    placeholderData: keepPreviousData,
  })
}

export function useAnalytics(f: AnalyticsFilters) {
  const opts = { placeholderData: keepPreviousData }
  return {
    classes: useQuery({ queryKey: qk.analytics('detections', f), queryFn: () => analyticsApi.detections(f), ...opts }),
    activity: useQuery({ queryKey: qk.analytics('activity', f), queryFn: () => analyticsApi.activity(f), ...opts }),
    zones: useQuery({ queryKey: qk.analytics('zones', f), queryFn: () => analyticsApi.zones(f), ...opts }),
    performance: useQuery({ queryKey: qk.analytics('performance', f), queryFn: () => analyticsApi.performance(f), ...opts }),
  }
}

export function useSettings() {
  return useQuery({ queryKey: qk.settings, queryFn: settingsApi.get })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: settingsApi.health, refetchInterval: 30_000, retry: false })
}

export type { Page }

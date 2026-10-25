import { api, apiUrl } from '@/lib/api'
import type {
  ActivitySeries,
  AnalyticsFilters,
  ClassCount,
  EventFilters,
  EventStatus,
  HealthResponse,
  Job,
  MonitoringEvent,
  OccupancyPoint,
  Overview,
  Page,
  PerformancePoint,
  ProcessingConfig,
  SettingsResponse,
  Zone,
  ZoneInput,
  ZoneSummary,
} from '@/types/api'

export const jobsApi = {
  list: (params: { video_id?: string; status?: string; page?: number; page_size?: number } = {}) =>
    api.get<Page<Job>>('/api/v1/jobs', { ...params }),
  get: (id: string) => api.get<Job>(`/api/v1/jobs/${id}`),
  retry: (id: string) => api.post<Job>(`/api/v1/jobs/${id}/retry`),
  cancel: (id: string) => api.post<Job>(`/api/v1/jobs/${id}/cancel`),
}

export const zonesApi = {
  forVideo: (videoId: string) => api.get<Zone[]>(`/api/v1/videos/${videoId}/zones`),
  all: () => api.get<Zone[]>('/api/v1/zones'),
  create: (videoId: string, body: ZoneInput) => api.post<Zone>(`/api/v1/videos/${videoId}/zones`, body),
  update: (id: string, body: Partial<ZoneInput>) => api.patch<Zone>(`/api/v1/zones/${id}`, body),
  remove: (id: string) => api.delete(`/api/v1/zones/${id}`),
  occupancy: (id: string) => api.get<OccupancyPoint[]>(`/api/v1/zones/${id}/occupancy`),
  recompute: (videoId: string) =>
    api.post<{ zones: number; events: number; job_id: string | null }>(`/api/v1/videos/${videoId}/zones/recompute`),
}

function eventQuery(f: EventFilters) {
  return {
    q: f.q,
    video_id: f.video_id,
    zone_id: f.zone_id,
    class_name: f.class_name,
    event_type:
      f.event_type === 'alerts' ? ['restricted_entry', 'occupancy_exceeded', 'processing_failure'] : f.event_type || undefined,
    status: f.status || undefined,
    date_from: f.date_from,
    date_to: f.date_to,
    sort: f.sort,
    order: f.order,
    page: f.page,
    page_size: f.page_size,
  }
}

export const eventsApi = {
  list: (f: EventFilters) => api.get<Page<MonitoringEvent>>('/api/v1/events', eventQuery(f)),
  get: (id: string) => api.get<MonitoringEvent>(`/api/v1/events/${id}`),
  update: (id: string, body: { status?: EventStatus; notes?: string | null }) =>
    api.patch<MonitoringEvent>(`/api/v1/events/${id}`, body),
  bulkStatus: (ids: string[], status: EventStatus) =>
    api.post<{ updated: number }>('/api/v1/events/bulk-status', { ids, status }),
  exportUrl: (f: EventFilters) => {
    const { page: _p, page_size: _s, ...rest } = eventQuery(f)
    return apiUrl('/api/v1/events/export', rest)
  },
}

export const analyticsApi = {
  overview: (f: AnalyticsFilters = {}) => api.get<Overview>('/api/v1/analytics/overview', { ...f }),
  detections: (f: AnalyticsFilters = {}) => api.get<ClassCount[]>('/api/v1/analytics/detections', { ...f }),
  activity: (f: AnalyticsFilters = {}) => api.get<ActivitySeries>('/api/v1/analytics/activity', { ...f }),
  zones: (f: AnalyticsFilters = {}) => api.get<ZoneSummary[]>('/api/v1/analytics/zones', { ...f }),
  performance: (f: AnalyticsFilters = {}) => api.get<PerformancePoint[]>('/api/v1/analytics/performance', { ...f }),
}

export const settingsApi = {
  get: () => api.get<SettingsResponse>('/api/v1/settings'),
  update: (processing: Partial<ProcessingConfig>) => api.patch<SettingsResponse>('/api/v1/settings', { processing }),
  loadModel: () => api.post<SettingsResponse>('/api/v1/settings/model/load'),
  health: () => api.get<HealthResponse>('/api/v1/health'),
}

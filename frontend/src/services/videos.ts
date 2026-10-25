import { api, uploadWithProgress } from '@/lib/api'
import type { DetectionWindow, Job, MonitoringEvent, Page, Video } from '@/types/api'

export interface VideoListParams {
  q?: string
  status?: string
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export const videosApi = {
  list: (params: VideoListParams = {}) => api.get<Page<Video>>('/api/v1/videos', { ...params }),
  get: (id: string) => api.get<Video>(`/api/v1/videos/${id}`),
  update: (id: string, body: { original_filename?: string; recorded_at?: string | null }) =>
    api.patch<Video>(`/api/v1/videos/${id}`, body),
  remove: (id: string) => api.delete(`/api/v1/videos/${id}`),
  process: (id: string) => api.post<Job>(`/api/v1/videos/${id}/process`),
  importSample: () => api.post<Video>('/api/v1/videos/sample'),
  upload: (file: File, recordedAt: string | undefined, onProgress: (f: number) => void, signal?: AbortSignal) => {
    const form = new FormData()
    form.append('file', file)
    if (recordedAt) form.append('recorded_at', recordedAt)
    return uploadWithProgress<Video>('/api/v1/videos', form, onProgress, signal)
  },
  detections: (id: string, start: number, end: number, signal?: AbortSignal) =>
    api.get<DetectionWindow>(`/api/v1/videos/${id}/detections`, { start, end }, signal),
  events: (id: string, pageSize = 200) =>
    api.get<Page<MonitoringEvent>>(`/api/v1/videos/${id}/events`, { page_size: pageSize }),
}

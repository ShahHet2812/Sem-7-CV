// Types mirroring the backend Pydantic schemas (backend/app/schemas).

export type UUID = string

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export type VideoStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
export type ZoneType = 'general' | 'entry' | 'exit' | 'restricted'
export type EventType =
  | 'zone_entry'
  | 'zone_exit'
  | 'restricted_entry'
  | 'occupancy_exceeded'
  | 'processing_failure'
export type EventStatus = 'new' | 'reviewed' | 'dismissed'
export type Severity = 'info' | 'warning' | 'critical'

export interface ProcessingConfig {
  confidence_threshold: number
  image_size: number
  target_sample_fps: number
  classes: string[]
  tracker: 'bytetrack' | 'botsort'
  zone_confirm_samples: number
  track_lost_timeout: number
  occupancy_alert_cooldown: number
  anchor_mode: 'bottom_center' | 'center'
  edge_entries: boolean
  generate_snapshots: boolean
}

export interface Job {
  id: UUID
  video_id: UUID
  video_name: string | null
  status: JobStatus
  is_current: boolean
  attempt: number
  progress: number | null
  frames_processed: number
  frames_sampled: number
  total_frames: number | null
  frame_stride: number
  config: Partial<ProcessingConfig>
  device: string | null
  model_name: string | null
  error_message: string | null
  cancel_requested: boolean
  detection_count: number
  track_count: number
  event_count: number
  processing_seconds: number | null
  sampled_fps: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Video {
  id: UUID
  original_filename: string
  file_size: number
  content_type: string
  container_format: string
  codec: string | null
  duration_seconds: number | null
  fps: number | null
  frame_count: number | null
  width: number
  height: number
  status: VideoStatus
  is_sample: boolean
  recorded_at: string | null
  created_at: string
  updated_at: string
  processing_metadata: Record<string, unknown>
  thumbnail_url: string | null
  stream_url: string
  download_url: string
  browser_playable: boolean
  latest_job: Job | null
  current_job_id: UUID | null
  zone_count: number
  event_count: number
  detection_count: number
}

export interface SampleInfo {
  key: string
  title: string
  category: string
  description: string
  objects: string[]
  license: string
  attribution: string
  source_page: string
  approx_mb: number
  duration_s: number | null
  fixed_camera: boolean
  scenario: string | null
  zones: { name: string; zone_type: string; polygon: Point[]; color: string; occupancy_threshold: number | null }[]
  imported_video_id: string | null
}

export interface SampleMeta {
  key: string
  title: string
  license: string
  attribution: string
  source_page: string
}

export type Point = [number, number]

export interface ZoneStats {
  entries: number
  exits: number
  restricted_entries: number
  occupancy_alerts: number
  peak_occupancy: number | null
}

export interface Zone {
  id: UUID
  video_id: UUID
  name: string
  zone_type: ZoneType
  color: string
  polygon: Point[]
  enabled: boolean
  emit_entries: boolean
  emit_exits: boolean
  occupancy_threshold: number | null
  class_filter: string[] | null
  created_at: string
  updated_at: string
  stats: ZoneStats
}

export interface ZoneInput {
  name: string
  zone_type: ZoneType
  color: string
  polygon: Point[]
  enabled?: boolean
  emit_entries?: boolean
  emit_exits?: boolean
  occupancy_threshold?: number | null
  class_filter?: string[] | null
}

/** Normalized source-frame box: [x1, y1, x2, y2] in 0..1 */
export type BBox = [number, number, number, number]

export interface DetectionItem {
  bbox: BBox
  class_id: number
  class_name: string
  confidence: number
  track_id: number | null
}

export interface FrameDetections {
  frame_index: number
  timestamp: number
  detections: DetectionItem[]
}

export interface DetectionWindow {
  video_id: UUID
  job_id: UUID | null
  start: number
  end: number
  fps: number | null
  frame_stride: number
  sample_interval: number | null
  truncated: boolean
  frames: FrameDetections[]
}

export interface MonitoringEvent {
  id: UUID
  video_id: UUID
  video_name: string | null
  zone_id: UUID | null
  zone_name: string | null
  zone_color: string | null
  job_id: UUID | null
  event_type: EventType
  severity: Severity
  video_timestamp: number | null
  frame_index: number | null
  occurred_at: string
  class_name: string | null
  track_id: number | null
  confidence: number | null
  occupancy: number | null
  bbox: BBox | null
  status: EventStatus
  notes: string | null
  snapshot_url: string | null
  details: Record<string, unknown>
  created_at: string
  reviewed_at: string | null
}

export interface Overview {
  total_videos: number
  processed_videos: number
  total_detections: number
  unique_tracks: number
  zone_entries: number
  zone_exits: number
  restricted_entries: number
  occupancy_alerts: number
  processing_failures: number
  unreviewed_alerts: number
  total_zones: number
  video_status: Record<string, number>
  job_status: Record<string, number>
  events_by_type: Record<string, number>
  recent_jobs: Job[]
  recent_events: MonitoringEvent[]
}

export interface ClassCount {
  class_name: string
  detections: number
  tracks: number
  avg_confidence: number | null
}

export interface ActivityPoint {
  bucket: string
  label: string
  detections: number
  entries: number
  exits: number
  alerts: number
}

export interface ActivitySeries {
  mode: 'video_time' | 'wall_clock'
  bucket_size: string
  points: ActivityPoint[]
}

export interface ZoneSummary {
  zone_id: UUID
  zone_name: string
  zone_type: ZoneType
  color: string
  video_id: UUID
  video_name: string
  enabled: boolean
  entries: number
  exits: number
  restricted_entries: number
  occupancy_alerts: number
  total_events: number
  peak_occupancy: number | null
}

export interface PerformancePoint {
  job_id: UUID
  video_name: string
  finished_at: string | null
  processing_seconds: number | null
  frames_sampled: number
  sampled_fps: number | null
  realtime_factor: number | null
  device: string | null
  model_name: string | null
}

export interface OccupancyPoint {
  t: number
  occupancy: number
}

export interface SettingsResponse {
  processing: ProcessingConfig
  model: {
    name: string
    weights_present: boolean
    loaded: boolean
    error: string | null
    device: string
    auto_download: boolean
    source: string
    class_count: number | null
    trackers: string[]
  }
  supported_classes: string[]
  upload: { max_upload_mb: number; allowed_extensions: string[]; configured_via: string }
  storage: {
    uploads_bytes: number
    processed_bytes: number
    snapshots_bytes: number
    disk_free_bytes: number | null
    disk_total_bytes: number | null
  }
  system: Record<string, string | number | boolean | null>
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'unavailable'
  version: string
  environment: string
  checks: Record<string, { ok: boolean; [key: string]: unknown }>
}

export interface AnalyticsFilters {
  video_id?: string
  zone_id?: string
  class_name?: string
  date_from?: string
  date_to?: string
}

export interface EventFilters extends AnalyticsFilters {
  q?: string
  /** 'alerts' = restricted entries, occupancy alerts and processing failures */
  event_type?: EventType | 'alerts' | ''
  status?: EventStatus | ''
  sort?: 'occurred_at' | 'video_timestamp' | 'event_type' | 'class_name' | 'confidence'
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

# ZoneVision architecture

## Request and processing flow

```
Browser ──upload──► POST /api/v1/videos ──► VideoStorage.save_upload
                                              (stream to tmp, size limit, magic bytes,
                                               OpenCV decode of frame 0, thumbnail)
        ──process─► POST /videos/{id}/process ─► processing_jobs row (status=queued, config snapshot)
                                                        │  JobQueue.enqueue() wakes the worker
JobWorker thread ── claim (FOR UPDATE SKIP LOCKED) ◄─────┘
   └─ VideoProcessor.run(job)
        VideoReader.iter_sampled(stride) ──► TrackingSession.update(frame) (YOLO + ByteTrack)
        └─ bulk insert detections every 20 sampled frames, progress commit, cancel check
        └─ track_summaries
        └─ zone_analysis.recompute_zone_events (ZoneMonitor over stored detections)
        └─ promote job to current, purge previous current job's results
        └─ snapshots.generate_missing_snapshots
Browser ◄─poll── GET /videos/{id} (status/progress) ── GET /videos/{id}/detections?start&end (20 s windows)
```

## Backend layers

| Layer | Package | Responsibility |
|---|---|---|
| HTTP | `app/api/v1/routers` | Validation, status codes, dependency injection |
| Services | `app/services` | Use cases (upload, queue, retry, zone edit + recompute, CSV, analytics) |
| Repositories | `app/repositories` | Reusable SQLAlchemy queries and filters |
| Models | `app/models` | Tables, indexes, cascades |
| Schemas | `app/schemas` | Pydantic request/response contracts (mirrored in `frontend/src/types/api.ts`) |
| CV | `app/cv` | `video_reader`, `detector` (model loading/device), `tracker`, `geometry`, `zone_monitor`, `processor` |
| Workers | `app/workers` | DB-backed queue and worker threads |

## Data model

```
videos 1─* processing_jobs 1─* detections
   │            │           1─* track_summaries
   │            │           1─* monitoring_events (zone events + processing failures)
   │            │           1─* zone_occupancy_samples
   └─1─* monitoring_zones 1─* monitoring_events / zone_occupancy_samples
application_settings (key/value JSON)
```

* All foreign keys use `ON DELETE CASCADE`. Deleting a video removes everything derived from it, and the
  service then removes its files.
* `processing_jobs.is_current` marks the job whose results are shown. A newly completed job purges the old
  current job's detections and zone events in the same transaction, so analytics never double count and
  in-progress jobs never leak partial data into the UI.
* Indexes: `detections(job_id, timestamp)`, `(job_id, class_name)`, `(job_id, track_id)`;
  `monitoring_events(video_id, occurred_at)`, `(zone_id, event_type)`, plus `event_type`, `status`,
  `occurred_at`, `class_name`; `zone_occupancy_samples(zone_id, timestamp)`; `videos(status)`,
  `videos(created_at)`; `processing_jobs(status)`, `(video_id, is_current)`.
* Video binaries are never stored in the database; only server-generated filenames relative to the storage
  roots are.

## Why zone events are derived from stored detections

Detection and tracking are expensive; zone logic is cheap and deterministic. Persisting tracked detections first
and running `ZoneMonitor` over them:

* lets users add or edit zones after processing and get correct events in seconds,
* keeps a single implementation for the pipeline and for zone edits,
* makes zone behaviour testable with synthetic tracks (`tests/test_zone_monitor.py`).

`ZoneMonitor.update(timestamp, frame_index, observations)` is a streaming interface, so a future live
(RTSP) pipeline can call it per frame without changes.

## Frontend

* `lib/api.ts`: one fetch client with a configurable base URL, error envelope parsing, and XHR uploads with
  progress.
* `hooks/queries.ts`: all TanStack Query hooks. They poll while jobs are active and invalidate dependent data
  after mutations.
* `components/video/VideoStage.tsx`: `<video>` plus a `<canvas>` in the same box. The `contentRect()` helper
  computes the letterboxed content area, and a ResizeObserver plus a requestAnimationFrame loop (only while
  playing) redraw zones, detections and the polygon editor. `frameAt()` picks the latest sampled frame within
  one sampling interval of the playhead.
* `hooks/useDetections.ts`: loads detections in 20 s chunks around the playhead (previous, current and next)
  and caches them.

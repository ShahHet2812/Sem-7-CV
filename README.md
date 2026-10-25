# ZoneVision

**Academic project title:** *Vision-Based Object Detection and Zone Monitoring Platform*

ZoneVision is a web application for analyzing recorded video. It detects and tracks objects with a pretrained
YOLO model and ByteTrack, lets you draw polygon monitoring zones on a frame, derives zone **entry / exit /
restricted-entry / occupancy** events from the tracked objects, and presents everything in a dashboard with
synchronized video overlays, an event inbox, analytics and CSV export.

Everything runs locally: no paid APIs, no cloud credentials, no proprietary datasets. Every number in the UI is
computed from videos you actually process. The app does not seed demonstration records.

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick start with Docker](#quick-start-with-docker)
4. [Local development](#local-development)
5. [Configuration](#configuration)
6. [Model weights](#model-weights)
7. [Using the application](#using-the-application)
8. [How the computer vision pipeline works](#how-the-computer-vision-pipeline-works)
9. [Metric definitions](#metric-definitions)
10. [API](#api)
11. [Testing](#testing)
12. [Data management and reset](#data-management-and-reset)
13. [Troubleshooting](#troubleshooting)
14. [Limitations](#limitations)
15. [Security notes](#security-notes)
16. [Demonstrating the project](#demonstrating-the-project)
17. [Extending ZoneVision](#extending-zonevision)

---

## Features

| Area | What it does |
|---|---|
| Video library | Drag-and-drop upload with progress, server-side validation (size, container signature, decodability), thumbnails, search, filter, sort, pagination, process / retry / cancel / delete with confirmation, download |
| CV pipeline | OpenCV decoding, configurable frame sampling, Ultralytics YOLO (`yolo11n.pt` by default), ByteTrack or BoT-SORT tracking, batched persistence, progress reporting, cancellation, retry |
| Analysis workspace | HTML5 player with a canvas overlay that accounts for letterboxing, boxes/labels/track IDs/confidence, class filter, speed control, sample stepping, event markers on the seek bar, an event timeline that jumps to and outlines the triggering object, and job status |
| Zones | Draw polygons by clicking, drag vertices, undo/cancel, templates, rename/recolor/enable/disable/delete, four zone types, optional occupancy threshold, per-zone class filter. Events are recomputed from stored detections on save, so no re-inference is needed |
| Events & alerts | Search, filters (video, zone, type, class, status, date range), sorting, pagination, bulk review/dismiss, detail view with JPEG snapshot and notes, deep link to the video timestamp, CSV export of the filtered set, in-app alert badge |
| Analytics | Detections and track IDs by class, entries/exits over time, zone occupancy over time, entries/exits by zone, events by type, processing performance, top zones. All filterable by video, zone, class and date range |
| Settings | Confidence, inference size, sampling rate, classes, tracker, zone-logic parameters, snapshots, model status and download, health checks, storage use, versions |

## Architecture

```
┌────────────┐  /api, /health  ┌───────────────────────────────┐        ┌────────────┐
│  React SPA │ ──────────────► │ FastAPI (uvicorn)             │ ─────► │ PostgreSQL │
│  (nginx)   │ ◄────────────── │  routers → services → repos   │ ◄───── │            │
└────────────┘   JSON / video  │  in-process JobWorker thread  │        └────────────┘
                               │   └─ VideoProcessor           │
                               │       OpenCV → YOLO+ByteTrack │──► storage/ (uploads,
                               │       → bulk insert → zones   │     thumbnails, snapshots,
                               └───────────────────────────────┘     model weights)
```

* **Backend** (`backend/app`): `api/v1/routers` (HTTP), `services` (business logic), `repositories` (queries),
  `models` (SQLAlchemy 2), `schemas` (Pydantic), `cv` (detector, tracker, geometry, zone monitor, video reader,
  processor), `workers` (DB-backed job queue), `core` (config, logging, errors). Alembic manages migrations.
* **Job queue**: the `processing_jobs` table is the queue. A worker thread inside the API process claims
  queued jobs with `SELECT … FOR UPDATE SKIP LOCKED` (PostgreSQL). Because of this, several worker
  processes can share one database, and a Redis/Celery worker can later replace the thread behind the
  `JobQueue` interface.
* **Frontend** (`frontend/src`): React 19 + TypeScript + Vite, Tailwind CSS v4, shadcn-style components on Radix
  primitives, TanStack Query, React Router, Recharts, React Hook Form + Zod, Lucide icons.

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
├── backend/
│   ├── app/{api,core,cv,db,models,repositories,schemas,services,workers}/, main.py, cli.py
│   ├── alembic/ (migrations)   tests/ (pytest)   Dockerfile   requirements*.txt
├── frontend/
│   ├── src/{app,components,features/*,hooks,lib,services,types}/   tests/ (vitest)
│   ├── Dockerfile   nginx.conf
├── docs/ARCHITECTURE.md
├── docker-compose.yml   .env.example
└── storage/  (created at runtime: uploads/, processed/, snapshots/, models/)
```

## Quick start with Docker

Requirements: Docker with Compose v2, about 6 GB of free disk, and internet access the first time (to pull images
and CPU PyTorch and to download the 5.4 MB model weights).

```bash
cp .env.example .env              # then set POSTGRES_PASSWORD (and DATABASE_URL for local runs)
docker compose up -d --build      # db → backend (runs migrations) → frontend
open http://localhost:8080        # UI
#   API docs:  http://localhost:8000/docs     Health: http://localhost:8000/health
```

* The backend container runs `alembic upgrade head` before starting, and it starts only after PostgreSQL
  reports healthy. The frontend starts after the backend health check passes.
* Data persists in the named volumes `zonevision_pgdata` (database) and `zonevision_storage` (uploads,
  thumbnails, snapshots, weights).
* The browser talks only to nginx (same origin), which proxies `/api` and `/health` to `backend:8000`. No
  `localhost` URL is baked into the frontend bundle.

```bash
docker compose logs -f backend    # follow logs (JSON lines)
docker compose stop               # stop, keep data
docker compose down               # remove containers, keep volumes
docker compose down -v            # ⚠ also deletes the database and all uploaded videos
```

## Local development

Prerequisites: Python 3.11+ (tested on 3.12), Node.js 20+ (tested on 24), and a PostgreSQL instance.
The simplest way to get PostgreSQL is `docker compose up -d db`, which publishes it on `127.0.0.1:5432`.

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu   # CPU build
pip install -r requirements-dev.txt
python -m app.cli init-db                 # alembic upgrade head (uses DATABASE_URL from ../.env)
uvicorn app.main:app --reload --reload-dir app --port 8000
```

For an NVIDIA GPU, install the CUDA build of PyTorch instead
(`--index-url https://download.pytorch.org/whl/cu126`). With `INFERENCE_DEVICE=auto`, the GPU is detected
automatically.

**SQLite fallback (development only):** set `DATABASE_URL=sqlite:///./storage/zonevision.db` and run
`python -m app.cli init-db`. PostgreSQL remains the supported primary database.

### Frontend

```bash
cd frontend
npm ci
npm run dev            # http://localhost:5173, proxies /api → http://127.0.0.1:8000
```

Set `VITE_PROXY_TARGET` to point the dev proxy elsewhere. To call a backend on another origin directly, set
`VITE_API_BASE_URL=https://api.example.com` at build time and add the UI origin to `CORS_ORIGINS`.

## Configuration

All backend settings come from environment variables or `.env` in the project root (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://zonevision:…@localhost:5432/zonevision` | SQLAlchemy URL (PostgreSQL primary; `sqlite:///…` fallback) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `zonevision` / **required** / `zonevision` | Used by Docker Compose |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated browser origins allowed to call the API |
| `STORAGE_DIR` | `./storage` | Root for `uploads/`, `processed/`, `snapshots/`, `models/` |
| `MAX_UPLOAD_MB` | `500` | Upload size limit (enforced while streaming) |
| `MODEL_WEIGHTS` | `yolo11n.pt` | Official Ultralytics model name or path to a `.pt` file |
| `MODEL_DIR` | `<STORAGE_DIR>/models` | Where weights are stored and downloaded |
| `MODEL_AUTO_DOWNLOAD` | `true` | Download official weights on first use |
| `INFERENCE_DEVICE` | `auto` | `auto`, `cpu`, `cuda:0`, `mps` |
| `DEFAULT_CONFIDENCE` / `DEFAULT_IMAGE_SIZE` / `DEFAULT_TARGET_FPS` | `0.35` / `640` / `6` | Defaults for the editable processing settings |
| `WORKER_ENABLED` | `true` | Run the in-process job worker |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Logging |
| `ENVIRONMENT` | `development` | `development`, `production` or `test` |
| `VITE_API_BASE_URL` | empty | Frontend build-time API origin (empty means same origin) |

Runtime-editable settings, changed on the Settings page and stored in `application_settings`:
confidence threshold, inference image size, target sampling rate, classes, tracker, zone confirmation samples,
lost-track timeout, occupancy alert cooldown, zone anchor point, and snapshot generation. Detection settings are
copied into each job when it is queued, so a job is reproducible and retries use the same configuration.

## Model weights

* Default model: **YOLO11n** (`yolo11n.pt`, about 5.4 MB), pretrained on COCO (80 classes), published by
  Ultralytics at `https://github.com/ultralytics/assets/releases`. Ultralytics models are licensed under
  **AGPL-3.0**; check that license before any commercial or closed-source use.
* With `MODEL_AUTO_DOWNLOAD=true`, the weights are downloaded into `MODEL_DIR` the first time a job runs, when
  you click **Settings → Download & load**, or when you run `python -m app.cli download-model`.
* **Offline machines:** download `yolo11n.pt` (or `yolov8n.pt`, `yolo26n.pt`, …) elsewhere, copy it to
  `storage/models/` (in Docker: `docker compose cp yolo11n.pt backend:/data/storage/models/`), and set
  `MODEL_AUTO_DOWNLOAD=false`. You can also point `MODEL_WEIGHTS` at any compatible Ultralytics detection
  `.pt` file, including a custom-trained one.
* If the weights are missing and cannot be downloaded, jobs **fail with a clear message**, a
  `processing_failure` event is recorded, and the health endpoint reports the model as not ready. Detections are
  never fabricated.

## Using the application

1. **Video Library → Upload video** (or **Import sample video**). Supported formats are MP4, MOV, M4V, AVI,
   MKV and WEBM, up to `MAX_UPLOAD_MB`.
2. Click **Process**. The job is queued, and you can watch progress (frames decoded / total) live.
3. **Monitoring Zones → Draw new zone**: pause on a representative frame, click the polygon vertices, then
   close the shape by clicking the first point, double-clicking, or pressing Enter. Choose a type and an
   optional maximum occupancy, then save. On a processed video, events for the zone are computed immediately.
4. **Analysis Workspace**: play the video with overlays. Click an event in the timeline (or a marker on the
   seek bar) to jump to it; the triggering object is outlined in red.
5. **Events**: filter, review or dismiss, open details with the snapshot, and export CSV.
6. **Overview / Analytics**: inspect the aggregates.

**Sample video:** *Import sample video* downloads `people-detection.mp4` from
[intel-iot-devkit/sample-videos](https://github.com/intel-iot-devkit/sample-videos), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (© Intel Corporation). The clip is not redistributed
in this repository; it is fetched only when you click the button.

**Codecs:** decoding uses the FFmpeg build bundled in the OpenCV wheel, which handles H.264, H.265, MPEG-4,
MJPEG, VP8/VP9 and more. Browser playback is narrower: H.264/VP9/AV1 in MP4 or WebM play everywhere, while
AVI/MKV or HEVC often do not. Such files can still be processed and zoned (the UI falls back to the first frame),
but overlay playback needs a browser-playable file. Convert with
`ffmpeg -i in.avi -c:v libx264 -pix_fmt yuv420p -movflags +faststart out.mp4`.

## How the computer vision pipeline works

**Coordinate system.** Every box and polygon is stored *normalized to the source frame*: `(0,0)` is the top-left
corner and `(1,1)` the bottom-right. Boxes are `[x1, y1, x2, y2]`. The frontend maps this space onto the
*content rectangle* of the `<video>` element (`object-fit: contain`, so letterbox bars are excluded). As a
result, overlays and zones stay aligned at any player size.

**Processing a job** (`backend/app/cv/processor.py`):

1. Purge any partial results from an earlier attempt of this job, which makes retries idempotent.
2. Decode the video once, sequentially. Every `stride`-th frame is sampled, where
   `stride = round(fps / target_sample_fps)`; skipped frames use `grab()` and are never re-decoded.
   Timestamps are `frame_index / fps`, which matches the HTML5 timeline for constant-frame-rate video.
3. Run `model.track(frame, persist=True, tracker=bytetrack.yaml, conf, imgsz, classes)` on each sampled frame.
   Boxes are clipped and normalized. Ultralytics only assigns IDs to confirmed tracks, so a box without a track
   ID is stored with `track_id = NULL`.
4. Bulk-insert detection rows every 20 sampled frames (or 2,000 rows), commit progress, and check whether
   cancellation was requested.
5. Store per-track summaries, then run **zone analysis** on the stored detections.
6. Atomically make this job the video's *current* job and purge the previous current job's results.
7. Render JPEG snapshots for the events (best effort).

Any exception rolls back the partial work, marks the job `failed` with a user-safe message (the stack trace goes
only to the server log), and records a `processing_failure` event. **Retry** re-queues the same job with its
original configuration. Jobs left `processing` by a crash are marked failed on startup and can be retried.

**Zone monitoring** (`backend/app/cv/zone_monitor.py`) runs per (zone, track):

* **Anchor point:** the bottom-center of the box (where a person or vehicle touches the ground), or optionally
  the box center.
* **Point-in-polygon:** `cv2.pointPolygonTest`. **Boundary rule:** a point exactly on an edge or vertex counts
  as *inside*.
* **Initial state:** the first observation of a track only records which side it is on. Objects that appear
  already inside a zone do not produce an "entry", because no crossing was observed.
* **Hysteresis:** a side change must persist for `zone_confirm_samples` consecutive observations (default 2)
  before it is confirmed. This suppresses enter/exit flicker for boxes jittering on the boundary.
* **Events:** exactly one event per confirmed transition. Outside→inside emits `zone_entry`
  (`restricted_entry` for restricted zones); inside→outside emits `zone_exit`. Nothing is emitted while the
  state is unchanged. Each event is timestamped at the first sample of the crossing on the source-video timeline.
* **Track loss:** if a track is unseen for `track_lost_timeout` seconds of video time (default 2 s), its state
  is dropped silently. No exit is invented, because the object may only be occluded. A track that reappears
  within the timeout keeps its state, so brief occlusions do not create duplicate entries.
* **Occupancy:** the number of live tracks whose confirmed state is inside. Change-points are stored for
  charts. With a threshold set, `occupancy_exceeded` fires when occupancy rises *above* it, then disarms until
  occupancy is back at or below the threshold. A cooldown (default 10 s) additionally rate-limits repeats.
* **Zone types:** *general* emits entries and exits, *entry* emits entries only, *exit* emits exits only,
  *restricted* emits restricted-entry alerts and exits. Each zone's entry/exit emission can be toggled.

Because zone logic is a pure function of the stored tracks, adding or editing a zone, or pressing **Recompute**
after changing zone settings, rebuilds that zone's events in seconds without re-running YOLO. Review status and
notes are preserved for events that are reproduced identically.

## Metric definitions

* **Detections**: boxes on *sampled* frames. An object visible on 30 sampled frames counts 30 times.
* **Track IDs / unique tracks**: distinct `(job, track_id)` pairs. This is **not** a count of real people or
  vehicles: occlusion, leaving the frame or missed detections can give the same object several IDs (and,
  rarely, swap IDs).
* **Entries**: `zone_entry` + `restricted_entry`. **Exits**: `zone_exit`.
* **Occupancy / peak occupancy**: see above. It is an estimate that depends on detection quality and sampling.
* **Activity over time**: with a video selected, buckets follow the video timeline. Otherwise they use wall-clock
  time, computed as `recorded_at` (optional at upload, defaulting to upload time) plus the video offset.
* **Processing performance**: sampled frames per second of wall time (decode + inference + tracking +
  persistence), plus a real-time factor (video seconds processed per wall second).
* Only each video's **current** job is counted, so reprocessing never double counts.

## API

Interactive OpenAPI docs are served at `/docs` (Swagger) and `/redoc`. All endpoints live under `/api/v1`, and
every error has the form `{"error": {"code", "message", "details?"}}`.

| Method | Path | Description |
|---|---|---|
| GET | `/health`, `/api/v1/health` | Database, storage, worker and model checks (503 if DB/storage are down) |
| POST | `/videos` | Multipart upload (`file`, optional `recorded_at`) |
| POST | `/videos/sample` | Import the CC BY sample clip |
| GET | `/videos` | List (`q`, `status`, `sort`, `order`, `page`, `page_size`) |
| GET/PATCH/DELETE | `/videos/{id}` | Read, rename or set `recorded_at`, delete (files included) |
| POST | `/videos/{id}/process` | Queue a job (optional per-job overrides); 409 if one is active |
| GET | `/videos/{id}/detections?start&end` | Current-job detections grouped by sampled frame (≤120 s window) |
| GET | `/videos/{id}/events` | Events of a video |
| GET | `/videos/{id}/preview` · `/stream` · `/download` | Thumbnail, range-enabled stream, attachment |
| GET/POST | `/videos/{id}/zones` | List or create zones |
| POST | `/videos/{id}/zones/recompute` | Rebuild zone events from stored detections |
| GET | `/zones`, `/zones/{id}`, `/zones/{id}/occupancy` | Zones and occupancy series |
| PATCH/DELETE | `/zones/{id}` | Update (recomputes events when geometry or behaviour changes) or delete |
| GET | `/jobs`, `/jobs/{id}` | Job list and detail |
| POST | `/jobs/{id}/retry`, `/jobs/{id}/cancel` | Retry failed/cancelled jobs; cancel queued/running jobs |
| GET | `/events` | Filter (`q`, `video_id`, `zone_id`, `event_type[]`, `class_name`, `status`, `date_from`, `date_to`, `track_id`), sort, paginate |
| GET | `/events/export` | Same filters, streamed CSV (spreadsheet formula injection is neutralized) |
| GET/PATCH | `/events/{id}` | Detail; update `status` (`new`/`reviewed`/`dismissed`) and `notes` |
| POST | `/events/bulk-status` | Review or dismiss up to 500 events |
| GET | `/events/{id}/snapshot` | JPEG evidence |
| GET | `/analytics/overview` · `/detections` · `/activity` · `/zones` · `/performance` | Aggregates (`video_id`, `zone_id`, `class_name`, `date_from`, `date_to`) |
| GET/PATCH | `/settings` | Read or update the processing settings |
| POST | `/settings/model/load` | Download (if needed) and load the model |

## Testing

```bash
# Backend: 98 tests (API, geometry, zone state machine, video reader, job lifecycle, migrations)
cd backend && source .venv/bin/activate
pytest                    # uses a temporary SQLite DB via the real Alembic migrations, no weights needed
ruff check app tests

# Frontend: type check, lint, unit/component tests, production build
cd frontend
npm run typecheck && npm run lint && npm test && npm run build      # or: npm run check

# Docker configuration
docker compose config --quiet
```

The API tests replace YOLO with a scripted tracker, so they run offline and without a GPU. The CV tests use small
synthetic tracks and videos generated with OpenCV. The real model was verified end to end by processing the
sample clip; see the [Demonstrating the project](#demonstrating-the-project) section.

## Data management and reset

```bash
python -m app.cli reset-results     # delete jobs, detections, events, snapshots; KEEP videos and zones
python -m app.cli delete-samples    # delete only videos imported via "Import sample video"
python -m app.cli download-model    # fetch/verify weights
python -m app.cli init-db           # apply migrations
# in Docker: docker compose exec backend python -m app.cli reset-results --yes
```

None of these commands touch user-uploaded files except `delete-samples`, which removes only sample imports.
Deleting a video in the UI removes its rows (through cascades), file, thumbnail and snapshots.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header shows "API or database unavailable" | Is the backend running? Is `DATABASE_URL` correct? Run `docker compose ps` and `curl localhost:8000/health` |
| Job fails with "Model weights … not found" | Enable `MODEL_AUTO_DOWNLOAD` or copy the `.pt` file into `storage/models/` |
| Upload rejected "does not match a supported video container" | The file's bytes do not match its extension; re-encode or rename correctly |
| Upload rejected "could not be decoded" | Corrupt file or unsupported codec; transcode to H.264 MP4 |
| Video processes but will not play | The browser lacks the codec; see *Codecs* above |
| Few or no detections | Lower the confidence threshold, raise the image size, check the class selection |
| Many entries/exits for one person | Increase *zone confirmation samples*; draw zones on the floor where the bottom-center anchor lands |
| Port already in use | Change `BACKEND_PORT`, `FRONTEND_PORT` or `POSTGRES_PORT` in `.env` |

## Limitations

* Track IDs are short-term identities, and counts are upper bounds on distinct objects (no re-identification).
* Occlusion, crowding, small or distant objects, motion blur and low light reduce recall. The tracker cannot
  recover objects the detector misses.
* Frame sampling trades accuracy for speed: very fast crossings between samples can be missed, and event times
  are quantized to the sampling interval.
* Timestamps assume a constant frame rate. Variable-frame-rate files may drift slightly from the browser
  timeline.
* Overlays show the most recent sampled frame within one sampling interval of the playhead. There is no
  interpolation, so boxes may lag fast motion slightly.
* Processing speed depends on CPU/GPU, resolution, codec and settings; no fixed FPS is promised. The sample clip
  (768×432, 50 s) processed at about 35 sampled frames/s on a 16-thread CPU.
* The in-process worker runs one job at a time per API process. Very long videos produce many detection rows;
  increase the sampling interval for long footage.
* There is no authentication; see below.

## Security notes

* This is a **development and demo configuration without authentication**: anyone who can reach the API can
  upload, delete and read data. Do not expose it to untrusted networks. Docker publishes ports on `127.0.0.1`
  only.
* Uploads are stored under server-generated UUID names in a directory that is not served statically. Client
  filenames are metadata only. Every served or deleted path is re-resolved and checked to be inside its storage
  root, and absolute paths are never returned.
* Validation covers the extension allow-list, a streaming size limit, a magic-byte container signature
  consistent with the extension, and successful decoding of the first frame.
* All SQL goes through SQLAlchemy with bound parameters, and LIKE wildcards in search terms are escaped.
* CORS origins come from configuration. Errors never include stack traces, and secrets live only in `.env`
  (git-ignored).

## Demonstrating the project

A walkthrough of about 10 minutes for an evaluation:

1. `docker compose up -d --build`, then open <http://localhost:8080>. The empty dashboard shows the onboarding
   steps (there is no fake data).
2. Click **Import sample video**, then **Process** in the Video Library and watch the progress bar.
3. Open **Monitoring Zones**, pause around 0:15 and draw a zone over the corridor floor. Set *Max occupancy*
   to 1 and save. Point out that events appear immediately because they are recomputed from stored tracks.
4. In the **Analysis Workspace**, play the video. Show the boxes, track IDs and the bottom-center anchor dots,
   and how a box crossing the zone edge produces an entry on the timeline. Click a timeline event to jump to it.
5. Under **Events**, filter to *Alerts only*, open an occupancy alert to see its snapshot, mark it reviewed,
   and export CSV.
6. Use **Analytics** to show occupancy over time and the metric definitions card.
7. Under **Settings**, change *zone confirmation samples* or the anchor point, then press **Recompute** on the
   zones page to show how the parameters affect the events.
8. Optionally, run `pytest` to show the geometry and state-machine tests.

## Extending ZoneVision

* **Redis / separate workers:** implement `JobQueue.enqueue` to publish job IDs and run `VideoProcessor.run` in a
  worker process. Database claiming already supports multiple workers.
* **RTSP / live cameras:** `ZoneMonitor.update()` is a streaming API. Feed it frames from a live
  `TrackingSession` and push events over WebSockets.
* **Custom models:** point `MODEL_WEIGHTS` at any Ultralytics detection `.pt` file. Class lists come from the
  model.
* **Notifications:** subscribe to newly created `MonitoringEvent` rows (for example, an outbox table) to send
  email or webhooks.
* **Multi-site / RBAC, retention policies, storage quotas, line-crossing counters, model comparisons.**

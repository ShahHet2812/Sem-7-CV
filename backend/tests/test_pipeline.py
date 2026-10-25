"""End-to-end job lifecycle with a scripted tracker (no YOLO weights needed)."""

import csv
import io

import pytest
from sqlalchemy import func, select

from app.cv.detector import ModelUnavailableError
from app.models import Detection, MonitoringEvent, TrackSummary
from tests.conftest import fake_factory, upload

RIGHT_HALF = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
LEFT_STRIP = [[0.0, 0.0], [0.2, 0.0], [0.2, 1.0], [0.0, 1.0]]


@pytest.fixture
def video(client, video_file):
    return upload(client, video_file).json()


def add_zone(client, vid, name="Right", polygon=RIGHT_HALF, **kw):
    r = client.post(f"/api/v1/videos/{vid}/zones", json={"name": name, "polygon": polygon, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def process(client, vid, **body):
    r = client.post(f"/api/v1/videos/{vid}/process", json=body or None)
    assert r.status_code == 202, r.text
    return r.json()


def test_full_pipeline(client, db, video, run_worker):
    vid = video["id"]
    zone = add_zone(client, vid, occupancy_threshold=0)
    job = process(client, vid, target_sample_fps=5)
    assert job["status"] == "queued"
    assert client.post(f"/api/v1/videos/{vid}/process").status_code == 409  # duplicate request

    run_worker()
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "completed", job["error_message"]
    assert job["is_current"] and job["progress"] == 1.0
    assert job["frame_stride"] == 2 and job["frames_processed"] == 40 and job["frames_sampled"] == 20
    assert job["detection_count"] == 20 and job["track_count"] == 1

    # Detections are stored with source timestamps and normalized boxes
    dets = db.scalars(select(Detection).order_by(Detection.frame_index)).all()
    assert [d.frame_index for d in dets] == list(range(0, 40, 2))
    assert dets[3].timestamp == pytest.approx(0.6)
    assert all(0 <= d.x1 < d.x2 <= 1 and 0 <= d.y1 < d.y2 <= 1 for d in dets)
    assert db.scalar(select(func.count()).select_from(TrackSummary)) == 1

    window = client.get(f"/api/v1/videos/{vid}/detections", params={"start": 0, "end": 1}).json()
    assert [f["frame_index"] for f in window["frames"]] == [0, 2, 4, 6, 8]
    assert window["sample_interval"] == pytest.approx(0.2)
    assert window["frames"][0]["detections"][0]["track_id"] == 1

    # Exactly one entry (left -> right), plus one occupancy alert (threshold 0)
    events = client.get("/api/v1/events", params={"video_id": vid, "sort": "video_timestamp", "order": "asc"}).json()
    assert [e["event_type"] for e in events["items"]] == ["zone_entry", "occupancy_exceeded"]
    entry = events["items"][0]
    assert entry["zone_id"] == zone["id"] and entry["track_id"] == 1 and entry["class_name"] == "person"
    assert entry["snapshot_url"] is not None
    assert client.get(entry["snapshot_url"]).headers["content-type"] == "image/jpeg"

    zones = client.get(f"/api/v1/videos/{vid}/zones").json()
    assert zones[0]["stats"]["entries"] == 1 and zones[0]["stats"]["peak_occupancy"] == 1
    occ = client.get(f"/api/v1/zones/{zone['id']}/occupancy").json()
    assert [p["occupancy"] for p in occ] == [0, 1]

    ov = client.get("/api/v1/analytics/overview").json()
    assert ov["total_videos"] == 1 and ov["processed_videos"] == 1
    assert ov["total_detections"] == 20 and ov["unique_tracks"] == 1
    assert ov["zone_entries"] == 1 and ov["zone_exits"] == 0 and ov["occupancy_alerts"] == 1
    assert ov["unreviewed_alerts"] == 1

    by_class = client.get("/api/v1/analytics/detections").json()
    assert by_class == [{"class_name": "person", "detections": 20, "tracks": 1, "avg_confidence": 0.9}]
    act = client.get("/api/v1/analytics/activity", params={"video_id": vid}).json()
    assert act["mode"] == "video_time"
    assert sum(p["detections"] for p in act["points"]) == 20
    assert sum(p["entries"] for p in act["points"]) == 1
    wall = client.get("/api/v1/analytics/activity").json()
    assert wall["mode"] == "wall_clock" and sum(p["detections"] for p in wall["points"]) == 20
    zsum = client.get("/api/v1/analytics/zones").json()
    assert zsum[0]["entries"] == 1 and zsum[0]["total_events"] == 2
    perf = client.get("/api/v1/analytics/performance").json()
    assert perf[0]["frames_sampled"] == 20

    vout = client.get(f"/api/v1/videos/{vid}").json()
    assert vout["status"] == "completed" and vout["detection_count"] == 20


def test_zone_added_after_processing_recomputes_events(client, video, run_worker):
    vid = video["id"]
    process(client, vid)
    run_worker()
    assert client.get("/api/v1/events").json()["total"] == 0
    zone = add_zone(client, vid)
    assert client.get("/api/v1/events").json()["total"] == 1

    # Moving the polygon away removes the event; disabling removes it as well.
    r = client.patch(f"/api/v1/zones/{zone['id']}", json={"polygon": LEFT_STRIP})
    assert r.status_code == 200
    # The object starts inside the left strip (x=0.05) and leaves it -> exit only.
    assert [e["event_type"] for e in client.get("/api/v1/events").json()["items"]] == ["zone_exit"]
    client.patch(f"/api/v1/zones/{zone['id']}", json={"enabled": False})
    assert client.get("/api/v1/events").json()["total"] == 0


def test_review_status_survives_recompute(client, video, run_worker):
    vid = video["id"]
    zone = add_zone(client, vid)
    process(client, vid)
    run_worker()
    ev = client.get("/api/v1/events").json()["items"][0]
    r = client.patch(f"/api/v1/events/{ev['id']}", json={"status": "reviewed", "notes": "checked"})
    assert r.json()["status"] == "reviewed" and r.json()["reviewed_at"]
    client.patch(f"/api/v1/zones/{zone['id']}", json={"occupancy_threshold": 5})
    again = client.get("/api/v1/events").json()["items"][0]
    assert again["status"] == "reviewed" and again["notes"] == "checked"
    assert client.post(f"/api/v1/videos/{vid}/zones/recompute").json()["events"] == 1


def test_reprocessing_replaces_previous_results(client, db, video, run_worker):
    vid = video["id"]
    add_zone(client, vid)
    process(client, vid)
    run_worker()
    process(client, vid)
    run_worker()
    assert db.scalar(select(func.count()).select_from(Detection)) == 20
    assert db.scalar(select(func.count()).select_from(MonitoringEvent)) == 1
    jobs = client.get("/api/v1/jobs", params={"video_id": vid}).json()["items"]
    assert [j["is_current"] for j in jobs] == [True, False]


def failing_factory(config):
    raise ModelUnavailableError("Model weights are missing (test).")


def test_failure_then_retry(client, db, video, run_worker):
    vid = video["id"]
    add_zone(client, vid)
    job = process(client, vid)
    run_worker(failing_factory)
    failed = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error_message"] == "Model weights are missing (test)."
    assert client.get(f"/api/v1/videos/{vid}").json()["status"] == "failed"
    failures = client.get("/api/v1/events", params={"event_type": "processing_failure"}).json()
    assert failures["total"] == 1 and failures["items"][0]["severity"] == "critical"

    assert client.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 409
    r = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert r.status_code == 202 and r.json()["attempt"] == 2
    assert client.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 409  # already queued
    run_worker(fake_factory)
    done = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert done["status"] == "completed" and done["error_message"] is None
    assert db.scalar(select(func.count()).select_from(Detection)) == 20
    zone_events = client.get("/api/v1/events", params={"event_type": "zone_entry"}).json()
    assert zone_events["total"] == 1
    # Completed jobs cannot be retried
    assert client.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 409


def test_crash_mid_processing_marks_failed_without_partial_rows(client, db, video, run_worker):
    class Exploding:
        calls = 0

        def update(self, frame):
            self.calls += 1
            if self.calls > 25:
                raise RuntimeError("boom")
            return fake_factory({}).tracker.update(frame)

    from app.cv.processor import TrackerHandle

    job = process(client, video["id"], target_sample_fps=60)
    run_worker(lambda cfg: TrackerHandle(Exploding(), "x", "cpu"))
    failed = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert "RuntimeError" in failed["error_message"] and "boom" not in failed["error_message"]
    assert db.scalar(select(func.count()).select_from(Detection)) == 0


def test_cancel_queued_job(client, video, run_worker):
    job = process(client, video["id"])
    r = client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert r.status_code == 202 and r.json()["status"] == "cancelled"
    assert run_worker() == []
    assert client.get(f"/api/v1/videos/{video['id']}").json()["status"] == "cancelled"


def test_cancel_running_job(client, db, video, run_worker):
    from app.cv.processor import TrackerHandle
    from app.models import ProcessingJob

    job = process(client, video["id"], target_sample_fps=60)

    class CancelDuringRun:
        calls = 0

        def update(self, frame):
            self.calls += 1
            if self.calls == 5:
                with db.begin():
                    db.get(ProcessingJob, __import__("uuid").UUID(job["id"])).cancel_requested = True
            return []

    run_worker(lambda cfg: TrackerHandle(CancelDuringRun(), "x", "cpu"))
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "cancelled"


def test_event_filters_and_csv_export(client, video, run_worker):
    vid = video["id"]
    add_zone(client, vid, name="Danger", zone_type="restricted")
    process(client, vid)
    run_worker()
    assert client.get("/api/v1/events", params={"event_type": "restricted_entry"}).json()["total"] == 1
    assert client.get("/api/v1/events", params={"event_type": "zone_exit"}).json()["total"] == 0
    assert client.get("/api/v1/events", params={"q": "danger"}).json()["total"] == 1
    assert client.get("/api/v1/events", params={"class_name": "car"}).json()["total"] == 0
    assert client.get("/api/v1/events", params={"date_from": "2100-01-01T00:00:00Z"}).json()["total"] == 0
    assert client.get("/api/v1/events", params={"event_type": "bogus"}).status_code == 422

    ids = [e["id"] for e in client.get("/api/v1/events").json()["items"]]
    assert client.post("/api/v1/events/bulk-status", json={"ids": ids, "status": "reviewed"}).json()["updated"] == 1
    assert client.get("/api/v1/events", params={"status": "new"}).json()["total"] == 0

    r = client.get("/api/v1/events/export", params={"video_id": vid})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1
    assert rows[0]["event_type"] == "restricted_entry" and rows[0]["zone"] == "Danger"
    assert rows[0]["status"] == "reviewed"


def test_csv_neutralizes_formulas(client, video, run_worker):
    vid = video["id"]
    add_zone(client, vid, name="=HYPERLINK(1)")
    process(client, vid)
    run_worker()
    rows = list(csv.DictReader(io.StringIO(client.get("/api/v1/events/export").text)))
    assert rows[0]["zone"] == "'=HYPERLINK(1)"


def test_delete_video_during_processing_is_rejected(client, db, video):
    from app.models import ProcessingJob

    job = process(client, video["id"])
    with db.begin():
        db.get(ProcessingJob, __import__("uuid").UUID(job["id"])).status = "processing"
    r = client.delete(f"/api/v1/videos/{video['id']}")
    assert r.status_code == 409

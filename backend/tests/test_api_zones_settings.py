import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import engine
from tests.conftest import upload

SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


@pytest.fixture
def vid(client, video_file):
    return upload(client, video_file).json()["id"]


def test_zone_crud(client, vid):
    r = client.post(f"/api/v1/videos/{vid}/zones", json={"name": " Door ", "zone_type": "entry", "polygon": SQUARE})
    assert r.status_code == 201
    z = r.json()
    assert z["name"] == "Door" and z["emit_entries"] and not z["emit_exits"]  # entry-type defaults
    assert z["stats"]["entries"] == 0

    r = client.patch(f"/api/v1/zones/{z['id']}", json={"name": "Main door", "color": "#FF0000", "occupancy_threshold": 3})
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["color"], r.json()["occupancy_threshold"]) == ("Main door", "#ff0000", 3)
    r = client.patch(f"/api/v1/zones/{z['id']}", json={"occupancy_threshold": None})
    assert r.json()["occupancy_threshold"] is None
    r = client.patch(f"/api/v1/zones/{z['id']}", json={"zone_type": "exit"})
    assert (r.json()["emit_entries"], r.json()["emit_exits"]) == (False, True)

    assert len(client.get(f"/api/v1/videos/{vid}/zones").json()) == 1
    assert len(client.get("/api/v1/zones").json()) == 1
    assert client.delete(f"/api/v1/zones/{z['id']}").status_code == 204
    assert client.get(f"/api/v1/zones/{z['id']}").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "polygon": [[0, 0], [1, 1]]},
        {"name": "x", "polygon": [[0, 0], [1.5, 0], [0, 1]]},
        {"name": "x", "polygon": [[0, 0], [1, 1], [1, 0], [0, 1]]},
        {"name": "", "polygon": SQUARE},
        {"name": "x", "polygon": SQUARE, "color": "red"},
        {"name": "x", "polygon": SQUARE, "zone_type": "secret"},
        {"name": "x", "polygon": SQUARE, "occupancy_threshold": -1},
        {"name": "x", "polygon": "not a list"},
    ],
)
def test_zone_validation(client, vid, body):
    r = client.post(f"/api/v1/videos/{vid}/zones", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_zone_name_unique_per_video(client, vid):
    client.post(f"/api/v1/videos/{vid}/zones", json={"name": "A", "polygon": SQUARE})
    r = client.post(f"/api/v1/videos/{vid}/zones", json={"name": "a", "polygon": SQUARE})
    assert r.status_code == 409


def test_zone_for_missing_video(client):
    r = client.post(f"/api/v1/videos/{uuid.uuid4()}/zones", json={"name": "A", "polygon": SQUARE})
    assert r.status_code == 404
    assert client.patch(f"/api/v1/zones/{uuid.uuid4()}", json={"name": "B"}).status_code == 404


def test_settings_get_and_update(client):
    s = client.get("/api/v1/settings").json()
    assert s["processing"]["confidence_threshold"] == 0.35
    assert s["upload"]["max_upload_mb"] == 20
    assert s["model"]["weights_present"] is False
    r = client.patch("/api/v1/settings", json={"processing": {"confidence_threshold": 0.5, "image_size": 480}})
    assert r.status_code == 200
    assert r.json()["processing"]["confidence_threshold"] == 0.5
    assert client.get("/api/v1/settings").json()["processing"]["image_size"] == 480


@pytest.mark.parametrize(
    "processing",
    [
        {"confidence_threshold": 1.5},
        {"confidence_threshold": 0},
        {"image_size": 500},
        {"target_sample_fps": 0},
        {"tracker": "deepsort"},
        {"zone_confirm_samples": 0},
    ],
)
def test_settings_validation(client, processing):
    assert client.patch("/api/v1/settings", json={"processing": processing}).status_code == 422


def test_process_request_validation(client, vid):
    r = client.post(f"/api/v1/videos/{vid}/process", json={"confidence_threshold": 2})
    assert r.status_code == 422


def test_detections_window_validation(client, vid):
    assert client.get(f"/api/v1/videos/{vid}/detections", params={"start": 5, "end": 2}).status_code == 422
    assert client.get(f"/api/v1/videos/{vid}/detections", params={"start": 0, "end": 500}).status_code == 422
    empty = client.get(f"/api/v1/videos/{vid}/detections").json()
    assert empty["job_id"] is None and empty["frames"] == []


def test_migrations_match_models():
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        tables = set(inspect(conn).get_table_names())
    assert diff == []
    assert {
        "videos", "processing_jobs", "monitoring_zones", "detections", "track_summaries",
        "monitoring_events", "zone_occupancy_samples", "application_settings", "alembic_version",
    } <= tables


def test_sample_catalog(client):
    items = client.get("/api/v1/videos/samples").json()
    keys = {s["key"] for s in items}
    assert {"restricted-area-worker", "people-corridor", "military-air-base-1968"} <= keys
    restricted = next(s for s in items if s["key"] == "restricted-area-worker")
    assert restricted["zones"][0]["zone_type"] == "restricted"
    assert all(s["license"] and s["attribution"] and s["imported_video_id"] is None for s in items)
    # Every preset polygon must pass the same validation as user zones.
    from app.cv.geometry import validate_polygon

    for s in items:
        for z in s["zones"]:
            validate_polygon(z["polygon"])
    assert client.post("/api/v1/videos/samples/does-not-exist").status_code == 404

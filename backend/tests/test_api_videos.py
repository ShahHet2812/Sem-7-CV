import uuid

from app.core.config import get_settings
from tests.conftest import upload, write_video


def test_health_checks_dependencies(client):
    for path in ("/health", "/api/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert body["checks"]["database"]["ok"] is True
        assert body["checks"]["storage"]["ok"] is True
        # Weights are absent and auto-download is disabled in tests -> degraded, not ok.
        assert body["checks"]["model"]["ok"] is False
        assert body["status"] == "degraded"


def test_upload_and_retrieve(client, video_file):
    r = upload(client, video_file, "My Clip.mp4")
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["original_filename"] == "My Clip.mp4"
    assert (v["width"], v["height"], v["frame_count"]) == (160, 120, 40)
    assert v["status"] == "uploaded"
    assert "storage" not in str(v) and "/tmp" not in str(v)  # no filesystem paths leak
    assert client.get(f"/api/v1/videos/{v['id']}").json()["id"] == v["id"]
    assert client.get(v["thumbnail_url"]).headers["content-type"] == "image/jpeg"
    stream = client.get(v["stream_url"], headers={"Range": "bytes=0-99"})
    assert stream.status_code == 206 and len(stream.content) == 100
    dl = client.get(v["download_url"])
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]


def test_upload_rejects_bad_extension(client, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    r = upload(client, p)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_spoofed_content(client, tmp_path):
    p = tmp_path / "fake.mp4"
    p.write_bytes(b"This is not a video at all" * 100)
    r = upload(client, p)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_video_content"
    assert list(get_settings().uploads_dir.iterdir()) == []  # nothing left behind


def test_upload_rejects_undecodable_video(client, tmp_path):
    p = tmp_path / "corrupt.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 4000)
    r = upload(client, p)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "undecodable_video"


def test_upload_rejects_extension_container_mismatch(client, video_file, tmp_path):
    p = tmp_path / "clip.avi"
    p.write_bytes(video_file.read_bytes())  # MP4 bytes with .avi name
    r = upload(client, p)
    assert r.status_code == 422


def test_upload_too_large(client, video_file, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    r = upload(client, video_file)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_list_search_and_pagination(client, tmp_path):
    for i in range(3):
        upload(client, write_video(tmp_path / f"v{i}.mp4", frames=5), f"camera-{i}.mp4")
    upload(client, write_video(tmp_path / "x.mp4", frames=5), "lobby.mp4")
    page = client.get("/api/v1/videos", params={"page_size": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2 and page["pages"] == 2
    found = client.get("/api/v1/videos", params={"q": "camera"}).json()
    assert found["total"] == 3
    # LIKE wildcards in the query are treated literally
    assert client.get("/api/v1/videos", params={"q": "%"}).json()["total"] == 0
    by_name = client.get("/api/v1/videos", params={"sort": "original_filename", "order": "asc"}).json()
    assert by_name["items"][0]["original_filename"] == "camera-0.mp4"


def test_invalid_pagination_and_ids(client):
    assert client.get("/api/v1/videos", params={"page": 0}).status_code == 422
    assert client.get("/api/v1/videos", params={"page_size": 1000}).status_code == 422
    assert client.get("/api/v1/videos/not-a-uuid").status_code == 422
    r = client.get(f"/api/v1/videos/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_delete_removes_files(client, video_file):
    v = upload(client, video_file).json()
    settings = get_settings()
    assert len(list(settings.uploads_dir.iterdir())) == 1
    assert client.delete(f"/api/v1/videos/{v['id']}").status_code == 204
    assert client.get(f"/api/v1/videos/{v['id']}").status_code == 404
    assert list(settings.uploads_dir.iterdir()) == []
    assert list(settings.thumbnails_dir.iterdir()) == []


def test_update_video_metadata(client, video_file):
    v = upload(client, video_file).json()
    r = client.patch(
        f"/api/v1/videos/{v['id']}",
        json={"original_filename": "renamed.mp4", "recorded_at": "2026-01-02T03:04:05Z"},
    )
    assert r.status_code == 200
    assert r.json()["original_filename"] == "renamed.mp4"
    assert r.json()["recorded_at"].startswith("2026-01-02T03:04:05")

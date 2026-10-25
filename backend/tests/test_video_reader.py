import pytest

from app.cv.video_reader import VideoDecodeError, VideoReader, compute_stride, probe_video
from tests.conftest import write_video


def test_probe_synthetic_video(tmp_path):
    path = write_video(tmp_path / "v.mp4", frames=30, fps=10, size=(160, 120))
    meta, frame = probe_video(path)
    assert (meta.width, meta.height) == (160, 120)
    assert meta.fps == pytest.approx(10.0)
    assert meta.frame_count == 30
    assert meta.duration_seconds == pytest.approx(3.0)
    assert frame.shape == (120, 160, 3)


def test_probe_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 500)
    with pytest.raises(VideoDecodeError):
        probe_video(bad)


def test_sampled_frames_have_source_timestamps(tmp_path):
    path = write_video(tmp_path / "v.mp4", frames=30, fps=10)
    with VideoReader(path, fps=10.0) as reader:
        frames = list(reader.iter_sampled(stride=3))
        assert reader.frames_read == 30
    assert [f.index for f in frames] == list(range(0, 30, 3))
    assert [f.timestamp for f in frames] == pytest.approx([i / 10 for i in range(0, 30, 3)])


@pytest.mark.parametrize(
    "fps, target, stride", [(30, 6, 5), (25, 6, 4), (12, 6, 2), (10, 20, 1), (30, 0, 1), (29.97, 5, 6)]
)
def test_compute_stride(fps, target, stride):
    assert compute_stride(fps, target) == stride

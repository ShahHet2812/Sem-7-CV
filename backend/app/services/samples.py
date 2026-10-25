"""Catalog of legally reusable sample videos (downloaded only on request).

Every entry is either CC BY 4.0 (Intel IoT DevKit sample-videos, attribution
shown in the UI) or public domain (Wikimedia Commons / U.S. federal works).
Some entries carry a *demo scenario*: preset zones and per-job processing
overrides, so a monitoring use case can be set up with one click. Presets are
ordinary zones afterwards and can be edited like any other zone.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import PayloadTooLarge, ServiceUnavailable
from app.services.storage import CHUNK, StoredVideo, VideoStorage

logger = logging.getLogger(__name__)

INTEL = "https://github.com/intel-iot-devkit/sample-videos/raw/master"
INTEL_PAGE = "https://github.com/intel-iot-devkit/sample-videos"
INTEL_LICENSE = "CC BY 4.0"
INTEL_ATTR = "© Intel Corporation, intel-iot-devkit/sample-videos"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
PEOPLE_AND_BAGS = ["person", "backpack", "handbag", "suitcase"]
TRAFFIC = ["person", "bicycle", "car", "motorcycle", "bus", "truck"]


@dataclass(frozen=True)
class SampleZone:
    name: str
    zone_type: str
    polygon: list[list[float]]
    color: str
    occupancy_threshold: int | None = None
    class_filter: list[str] | None = None


@dataclass(frozen=True)
class SampleVideo:
    key: str
    title: str
    filename: str
    url: str
    category: str
    description: str
    objects: list[str]
    license: str
    attribution: str
    source_page: str
    approx_mb: float
    duration_s: float | None
    fixed_camera: bool = True
    # (start_s, duration_s): trim with ffmpeg, re-encoding to browser-friendly H.264 MP4.
    trim: tuple[float, float] | None = None
    zones: tuple[SampleZone, ...] = ()
    process: dict[str, Any] = field(default_factory=dict)
    scenario: str | None = None


def _commons(path: str) -> str:
    return f"{COMMONS}/{path}"


CATALOG: tuple[SampleVideo, ...] = (
    SampleVideo(
        key="restricted-area-worker",
        title="Restricted area — hazard boundary (DMZ-style demo)",
        filename="restricted-area-worker-zone.mp4",
        url=f"{INTEL}/worker-zone-detection.mp4",
        category="Restricted zone",
        description=(
            "Fixed overhead camera on a warehouse floor. A yellow/black hazard line marks a restricted "
            "area; workers repeatedly cross it. Demonstrates restricted-entry alerts the same way a "
            "perimeter/DMZ camera would."
        ),
        objects=["person"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=12.6,
        duration_s=75.9,
        scenario="Restricted zone beyond the hazard line; every confirmed entry raises a critical alert, "
        "more than one person inside raises an occupancy alert.",
        zones=(
            SampleZone(
                "Restricted area (beyond hazard line)",
                "restricted",
                [[0.50, 0.42], [0.96, 0.42], [1.0, 1.0], [0.27, 1.0]],
                "#f87171",
                occupancy_threshold=1,
                class_filter=["person"],
            ),
        ),
        process={"classes": ["person"], "target_sample_fps": 8},
    ),
    SampleVideo(
        key="night-intrusion",
        title="Night-time intrusion near a vehicle (IR camera)",
        filename="night-intrusion-ir-camera.webm",
        url=_commons(
            "transcoded/c/c2/8MP_4K_Dahua_CCTV_System_Sample_Video_-_Night_Time.webm/"
            "8MP_4K_Dahua_CCTV_System_Sample_Video_-_Night_Time.webm.1080p.vp9.webm"
        ),
        category="Restricted zone",
        description="Infrared night footage: a person walks up to a parked car. Tests low-light detection.",
        objects=["person", "car"],
        license="Public domain",
        attribution="Serious Security (via Wikimedia Commons)",
        source_page="https://commons.wikimedia.org/wiki/File:8MP_4K_Dahua_CCTV_System_Sample_Video_-_Night_Time.webm",
        approx_mb=1.8,
        duration_s=11.9,
        scenario="Restricted garden path: the intruder walks into it after inspecting the car.",
        zones=(
            SampleZone(
                "Garden path (restricted)",
                "restricted",
                [[0.15, 0.62], [0.47, 0.62], [0.47, 1.0], [0.15, 1.0]],
                "#fb923c",
                class_filter=["person"],
            ),
        ),
        process={"classes": ["person", "car"], "target_sample_fps": 15},
    ),
    SampleVideo(
        key="perimeter-wall",
        title="Property perimeter — people approaching (alarm camera)",
        filename="perimeter-wall-alarm-camera.webm",
        url=_commons(
            "transcoded/d/df/Ezviz-H8C-4MP_Alarm_Siren_Warning.webm/"
            "Ezviz-H8C-4MP_Alarm_Siren_Warning.webm.1080p.vp9.webm"
        ),
        category="Restricted zone",
        description=(
            "Outdoor camera above a perimeter wall and driveway; people approach the property. "
            "The camera pans near the end (tests track resets)."
        ),
        objects=["person"],
        license="Public domain",
        attribution="Crb Panther (via Wikimedia Commons)",
        source_page="https://commons.wikimedia.org/wiki/File:Ezviz-H8C-4MP_Alarm_Siren_Warning.webm",
        approx_mb=13.1,
        duration_s=32.2,
        scenario="Restricted road section at the gate; alerts on entries and when more than one person "
        "is inside.",
        zones=(
            SampleZone(
                "Gate approach (restricted)",
                "restricted",
                [[0.5, 0.3], [1.0, 0.3], [1.0, 0.75], [0.5, 0.75]],
                "#f87171",
                occupancy_threshold=1,
                class_filter=["person"],
            ),
        ),
        process={"classes": ["person", "car", "dog"], "target_sample_fps": 8},
    ),
    SampleVideo(
        key="parking-lot-long",
        title="Parking lot surveillance — long fixed shot (2 min 25 s)",
        filename="parking-lot-surveillance-long.mp4",
        url=_commons("1/14/BLK-HDPTZ12_Security_Camera_Parking_Lot_Surveillance_Video.webm"),
        category="Vehicles",
        description=(
            "Long fixed-camera shot of a large parking lot: dozens of parked cars, trucks and occasional "
            "pedestrians. Trimmed to the static part of the original PTZ recording."
        ),
        objects=["car", "truck", "person"],
        license="Public domain",
        attribution="Supercircuits (via Wikimedia Commons)",
        source_page="https://commons.wikimedia.org/wiki/File:BLK-HDPTZ12_Security_Camera_Parking_Lot_Surveillance_Video.webm",
        approx_mb=67.7,
        duration_s=145,
        trim=(0, 145),
        scenario="Restricted driving lane in the foreground; pedestrians entering it raise alerts.",
        zones=(
            SampleZone(
                "Foreground lane (restricted)",
                "restricted",
                [[0.0, 0.62], [1.0, 0.62], [1.0, 1.0], [0.0, 1.0]],
                "#f87171",
                class_filter=["person"],
            ),
        ),
        process={"classes": TRAFFIC, "image_size": 960, "target_sample_fps": 4},
    ),
    SampleVideo(
        key="military-air-base-1968",
        title="Military air-base security (1968 USAF film, 6 min)",
        filename="usaf-safe-side-air-base-security-1968.webm",
        url=_commons(
            "transcoded/6/69/US_Air_Force_Safe_Side-1968.ogv/US_Air_Force_Safe_Side-1968.ogv.360p.vp9.webm"
        ),
        category="Military (archival)",
        description=(
            "U.S. Air Force film on air-base security: soldiers, weapons training, aircraft, vehicles. "
            "Edited film with camera cuts — use it to test detection on military footage, not zone counting."
        ),
        objects=["person", "airplane", "truck", "car"],
        license="Public domain (U.S. federal work)",
        attribution="U.S. Air Force (via Wikimedia Commons)",
        source_page="https://commons.wikimedia.org/wiki/File:US_Air_Force_Safe_Side-1968.ogv",
        approx_mb=29.4,
        duration_s=363,
        fixed_camera=False,
        process={"classes": ["person", "airplane", "truck", "car", "bus", "boat"], "target_sample_fps": 4},
    ),
    SampleVideo(
        key="people-corridor",
        title="People walking in a room (overhead)",
        filename="people-detection.mp4",
        url=f"{INTEL}/people-detection.mp4",
        category="People",
        description="Overhead camera; several people enter, cross the room and leave.",
        objects=["person"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=5.5,
        duration_s=49.7,
        scenario="Center aisle zone with occupancy limit 1.",
        zones=(
            SampleZone("Center aisle", "general", [[0.3, 0.45], [0.7, 0.45], [0.75, 1.0], [0.25, 1.0]], "#22d3ee", 1),
        ),
        process={"classes": ["person"]},
    ),
    SampleVideo(
        key="one-by-one",
        title="People entering one by one",
        filename="one-by-one-person-detection.mp4",
        url=f"{INTEL}/one-by-one-person-detection.mp4",
        category="People",
        description="People walk into view one at a time — good for counting entries.",
        objects=["person"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=3.3,
        duration_s=None,
        process={"classes": ["person"]},
    ),
    SampleVideo(
        key="pedestrians-walking",
        title="Pedestrians walking toward the camera",
        filename="face-demographics-walking-and-pause.mp4",
        url=f"{INTEL}/face-demographics-walking-and-pause.mp4",
        category="People",
        description="People walk toward the camera and pause — tests tracking through stops.",
        objects=["person", "handbag", "backpack"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=9.4,
        duration_s=None,
        process={"classes": PEOPLE_AND_BAGS},
    ),
    SampleVideo(
        key="classroom",
        title="Classroom (indoor crowd, furniture)",
        filename="classroom.mp4",
        url=f"{INTEL}/classroom.mp4",
        category="Indoor objects",
        description="Classroom scene: many seated people, chairs, laptops, books.",
        objects=["person", "chair", "laptop", "book", "dining table"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=13.5,
        duration_s=None,
        process={"classes": ["person", "chair", "laptop", "book", "dining table", "cell phone", "backpack"]},
    ),
    SampleVideo(
        key="store-aisle",
        title="Store aisle (retail)",
        filename="store-aisle-detection.mp4",
        url=f"{INTEL}/store-aisle-detection.mp4",
        category="Retail",
        description="Shoppers in a supermarket aisle.",
        objects=["person", "handbag", "bottle"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=9.2,
        duration_s=None,
        process={"classes": ["person", "handbag", "backpack", "bottle"]},
    ),
    SampleVideo(
        key="person-bicycle-car",
        title="Street: person, bicycle and car",
        filename="person-bicycle-car-detection.mp4",
        url=f"{INTEL}/person-bicycle-car-detection.mp4",
        category="Vehicles",
        description="Street scene with pedestrians, cyclists and cars.",
        objects=["person", "bicycle", "car"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=6.0,
        duration_s=None,
        process={"classes": TRAFFIC},
    ),
    SampleVideo(
        key="bottles",
        title="Bottles on a conveyor (small objects)",
        filename="bottle-detection.mp4",
        url=f"{INTEL}/bottle-detection.mp4",
        category="Objects",
        description="Bottles — tests a non-person COCO class.",
        objects=["bottle"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=0.5,
        duration_s=None,
        process={"classes": ["bottle", "cup", "vase"], "target_sample_fps": 10},
    ),
    SampleVideo(
        key="fruit-vegetables",
        title="Fruit and vegetables",
        filename="fruit-and-vegetable-detection.mp4",
        url=f"{INTEL}/fruit-and-vegetable-detection.mp4",
        category="Objects",
        description="Produce on a table — apples, bananas, oranges, carrots, broccoli.",
        objects=["apple", "banana", "orange", "carrot", "broccoli"],
        license=INTEL_LICENSE,
        attribution=INTEL_ATTR,
        source_page=INTEL_PAGE,
        approx_mb=17.8,
        duration_s=None,
        process={"classes": ["apple", "banana", "orange", "carrot", "broccoli", "bowl", "person"]},
    ),
)

BY_KEY = {s.key: s for s in CATALOG}
DEFAULT_SAMPLE = "people-corridor"


def ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def _download(url: str, dest: Path, max_bytes: int, attempts: int = 3) -> int:
    for attempt in range(1, attempts + 1):
        try:
            return _download_once(url, dest, max_bytes)
        except PayloadTooLarge:
            raise
        except Exception as exc:  # noqa: BLE001 - transient network/HTTP 429 errors are retried
            logger.warning("Sample download attempt %d failed: %s", attempt, exc)
            if attempt == attempts:
                raise
            time.sleep(3 * attempt)
    raise AssertionError("unreachable")


def _download_once(url: str, dest: Path, max_bytes: int) -> int:
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": "ZoneVision/1.0 (academic project)"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:  # noqa: S310 - fixed catalog URL
        while chunk := resp.read(CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLarge("Sample video exceeds the maximum upload size.")
            out.write(chunk)
    return size


def _trim(src: Path, dest: Path, start: float, duration: float) -> None:
    exe = ffmpeg_exe()
    if exe is None:
        raise ServiceUnavailable(
            "This sample needs ffmpeg to trim it (pip install imageio-ffmpeg).", code="ffmpeg_missing"
        )
    cmd = [
        exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(src),
        "-t", str(duration), "-an", "-vf", "scale=1280:-2", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)  # noqa: S603 - fixed args
    if res.returncode != 0 or not dest.is_file():
        logger.error("ffmpeg trim failed: %s", res.stderr[-500:])
        raise ServiceUnavailable("Trimming the sample video failed.", code="ffmpeg_failed")


def import_sample(storage: VideoStorage, sample: SampleVideo) -> StoredVideo:
    settings = storage.settings
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    ext = storage.validate_extension(sample.filename)
    final = settings.uploads_dir / f"{uuid.uuid4().hex}{ext}"
    raw = final.with_name(f".{final.name}.download")
    try:
        size = _download(sample.url, raw, settings.max_upload_bytes * 4 if sample.trim else settings.max_upload_bytes)
        if sample.trim:
            _trim(raw, final, *sample.trim)
            raw.unlink(missing_ok=True)
            size = final.stat().st_size
        else:
            raw.replace(final)
        return storage._finalize(final, sample.filename, ext, size)
    except BaseException:
        raw.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise


def sample_metadata(sample: SampleVideo) -> dict[str, Any]:
    return {
        "key": sample.key,
        "title": sample.title,
        "license": sample.license,
        "attribution": sample.attribution,
        "source_page": sample.source_page,
    }

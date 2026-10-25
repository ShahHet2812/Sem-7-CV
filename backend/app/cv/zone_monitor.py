"""Streaming zone-transition and occupancy state machine.

``ZoneMonitor.update`` is called once per *sampled* frame, in timeline order,
with the tracked objects observed on that frame. It is used both by the batch
pipeline (fed from stored detections) and could be fed directly from a live
stream, because it only ever looks at the current frame plus its own state.

Per (zone, track) the monitor keeps a confirmed state (inside / outside):

1. The first observation of a track sets its initial state *without* emitting
   an event: we never saw it cross the boundary, so we do not invent a
   crossing for objects that are already inside when they appear.
   Exception (``edge_entries``): a track that first appears inside a zone
   while its box touches the image border, after the first processed frame,
   has just walked into view through a part of the border that lies inside
   the zone. It is treated as coming from outside, so the normal confirmation
   below turns it into an entry.
2. When the observed side differs from the confirmed state, a candidate
   transition starts. It must persist for ``confirm_samples`` consecutive
   observations of that track before it is confirmed. This hysteresis keeps
   boxes jittering on the boundary from producing enter/exit/enter storms.
3. A confirmed outside->inside transition emits an entry (or restricted
   entry) event; inside->outside emits an exit event. Exactly one event per
   confirmed transition, and nothing while the state stays the same.
   The event is timestamped at the *first* sample of the candidate run, i.e.
   when the crossing was first observed on the source timeline.
4. If a track is not observed for ``lost_timeout`` seconds of video time its
   state is dropped silently (no exit event, since we cannot know whether it
   left or was occluded). A track ID that reappears within the timeout keeps
   its state, so brief occlusions do not cause duplicate entries.

Occupancy of a zone = number of live (not timed out) tracks whose confirmed
state is inside. Threshold alerts fire when occupancy rises above the
threshold, then disarm until occupancy falls back to <= threshold; a cooldown
additionally limits how often alerts can repeat.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.cv.geometry import AnchorMode, BBox, Polygon, bbox_anchor
from app.models.enums import EventType, ZoneType


@dataclass(frozen=True)
class Observation:
    track_id: int | None
    class_name: str
    confidence: float
    bbox: BBox  # normalized xyxy


@dataclass(frozen=True)
class ZoneSpec:
    id: Any
    name: str
    polygon: Sequence[Sequence[float]]
    zone_type: str = ZoneType.GENERAL
    emit_entries: bool = True
    emit_exits: bool = True
    occupancy_threshold: int | None = None
    class_filter: tuple[str, ...] | None = None


@dataclass
class ZoneEventRecord:
    zone_id: Any
    event_type: str
    timestamp: float
    frame_index: int
    track_id: int | None = None
    class_name: str | None = None
    confidence: float | None = None
    bbox: BBox | None = None
    occupancy: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OccupancyChange:
    zone_id: Any
    timestamp: float
    occupancy: int


@dataclass
class _TrackState:
    inside: bool
    last_seen: float
    class_name: str
    candidate: bool | None = None
    candidate_count: int = 0
    candidate_ts: float = 0.0
    candidate_frame: int = 0
    candidate_obs: Observation | None = None


@dataclass
class _ZoneRuntime:
    spec: ZoneSpec
    polygon: Polygon
    tracks: dict[int, _TrackState] = field(default_factory=dict)
    occupancy: int = 0
    series_started: bool = False
    peak_occupancy: int = 0
    alert_armed: bool = True
    last_alert_ts: float | None = None


class ZoneMonitor:
    def __init__(
        self,
        zones: Iterable[ZoneSpec],
        *,
        confirm_samples: int = 2,
        lost_timeout: float = 2.0,
        occupancy_cooldown: float = 10.0,
        anchor_mode: AnchorMode | str = AnchorMode.BOTTOM_CENTER,
        edge_entries: bool = True,
        edge_margin: float = 0.03,
    ):
        if confirm_samples < 1:
            raise ValueError("confirm_samples must be >= 1")
        if lost_timeout <= 0:
            raise ValueError("lost_timeout must be > 0")
        self.confirm_samples = confirm_samples
        self.lost_timeout = lost_timeout
        self.occupancy_cooldown = max(0.0, occupancy_cooldown)
        self.anchor_mode = AnchorMode(anchor_mode)
        self.edge_entries = edge_entries
        self.edge_margin = edge_margin
        self._zones = [_ZoneRuntime(spec=z, polygon=Polygon(z.polygon)) for z in zones]
        self.occupancy_changes: list[OccupancyChange] = []
        self._last_ts: float | None = None

    @property
    def peak_occupancy(self) -> dict[Any, int]:
        return {z.spec.id: z.peak_occupancy for z in self._zones}

    def current_occupancy(self) -> dict[Any, int]:
        return {z.spec.id: z.occupancy for z in self._zones}

    def update(
        self, timestamp: float, frame_index: int, observations: Sequence[Observation]
    ) -> list[ZoneEventRecord]:
        if self._last_ts is not None and timestamp < self._last_ts:
            raise ValueError("ZoneMonitor.update must be called in timeline order")
        first_frame = self._last_ts is None
        self._last_ts = timestamp
        events: list[ZoneEventRecord] = []
        for zone in self._zones:
            events.extend(self._update_zone(zone, timestamp, frame_index, observations, first_frame))
        return events

    def _touches_border(self, bbox: tuple[float, float, float, float]) -> bool:
        m = self.edge_margin
        x1, y1, x2, y2 = bbox
        return x1 <= m or y1 <= m or x2 >= 1 - m or y2 >= 1 - m

    def _update_zone(
        self,
        zone: _ZoneRuntime,
        ts: float,
        frame_index: int,
        observations: Sequence[Observation],
        first_frame: bool = False,
    ) -> list[ZoneEventRecord]:
        spec = zone.spec
        events: list[ZoneEventRecord] = []
        for obs in observations:
            # Without a track ID we cannot relate this box to earlier frames,
            # so it cannot participate in transition logic.
            if obs.track_id is None:
                continue
            if spec.class_filter and obs.class_name not in spec.class_filter:
                continue
            inside = zone.polygon.contains(bbox_anchor(obs.bbox, self.anchor_mode))
            state = zone.tracks.get(obs.track_id)
            if state is None:
                entered_from_edge = (
                    inside
                    and self.edge_entries
                    and not first_frame
                    and self._touches_border(obs.bbox)
                )
                state = zone.tracks[obs.track_id] = _TrackState(
                    inside=inside and not entered_from_edge,
                    last_seen=ts,
                    class_name=obs.class_name,
                )
                if not entered_from_edge:
                    continue
            state.last_seen = ts
            if inside == state.inside:
                state.candidate, state.candidate_count, state.candidate_obs = None, 0, None
                continue
            if state.candidate is inside:
                state.candidate_count += 1
            else:
                state.candidate = inside
                state.candidate_count = 1
                state.candidate_ts = ts
                state.candidate_frame = frame_index
                state.candidate_obs = obs
            if state.candidate_count >= self.confirm_samples:
                state.inside = inside
                first = state.candidate_obs or obs
                event_ts, event_frame = state.candidate_ts, state.candidate_frame
                state.candidate, state.candidate_count, state.candidate_obs = None, 0, None
                event_type = self._transition_event_type(spec, inside)
                if event_type:
                    events.append(
                        ZoneEventRecord(
                            zone_id=spec.id,
                            event_type=event_type,
                            timestamp=event_ts,
                            frame_index=event_frame,
                            track_id=obs.track_id,
                            class_name=first.class_name,
                            confidence=round(float(first.confidence), 4),
                            bbox=first.bbox,
                            details={"confirmed_at": round(ts, 3)},
                        )
                    )

        # Forget tracks that have not been seen for too long (no event).
        for tid in [t for t, s in zone.tracks.items() if ts - s.last_seen > self.lost_timeout]:
            del zone.tracks[tid]

        occupancy = sum(1 for s in zone.tracks.values() if s.inside)
        if occupancy != zone.occupancy or not zone.series_started:
            zone.series_started = True
            zone.occupancy = occupancy
            self.occupancy_changes.append(OccupancyChange(spec.id, ts, occupancy))
        zone.peak_occupancy = max(zone.peak_occupancy, occupancy)

        threshold = spec.occupancy_threshold
        if threshold is not None:
            if occupancy <= threshold:
                zone.alert_armed = True
            elif zone.alert_armed and (
                zone.last_alert_ts is None or ts - zone.last_alert_ts >= self.occupancy_cooldown
            ):
                zone.alert_armed = False
                zone.last_alert_ts = ts
                events.append(
                    ZoneEventRecord(
                        zone_id=spec.id,
                        event_type=EventType.OCCUPANCY_EXCEEDED.value,
                        timestamp=ts,
                        frame_index=frame_index,
                        occupancy=occupancy,
                        details={"threshold": threshold},
                    )
                )
        return events

    @staticmethod
    def _transition_event_type(spec: ZoneSpec, inside: bool) -> str | None:
        if inside:
            if not spec.emit_entries:
                return None
            if spec.zone_type == ZoneType.RESTRICTED:
                return EventType.RESTRICTED_ENTRY.value
            return EventType.ZONE_ENTRY.value
        return EventType.ZONE_EXIT.value if spec.emit_exits else None

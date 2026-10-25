"""Zone transition state machine on small synthetic tracks.

Zone: right half of the frame (x >= 0.5). Anchor: bottom-center of the box.
"""

import pytest

from app.cv.zone_monitor import Observation, ZoneMonitor, ZoneSpec
from app.models.enums import EventType, ZoneType

RIGHT_HALF = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]


def obs(x: float, track_id: int | None = 1, cls: str = "person", conf: float = 0.9) -> Observation:
    # Box whose bottom-center anchor is at (x, 0.9)
    return Observation(track_id, cls, conf, (x - 0.02, 0.5, x + 0.02, 0.9))


def run(monitor: ZoneMonitor, xs, dt: float = 0.2, track_id: int | None = 1):
    events = []
    for i, x in enumerate(xs):
        frame = [] if x is None else [obs(x, track_id)]
        events += monitor.update(i * dt, i, frame)
    return events


def make(confirm: int = 1, **kw) -> ZoneMonitor:
    spec_kw = {k: kw.pop(k) for k in list(kw) if k in ZoneSpec.__dataclass_fields__}
    return ZoneMonitor([ZoneSpec(id="z", name="Z", polygon=RIGHT_HALF, **spec_kw)], confirm_samples=confirm, **kw)


def types(events):
    return [e.event_type for e in events]


def test_outside_to_inside_emits_single_entry():
    events = run(make(), [0.1, 0.3, 0.6, 0.7, 0.8])
    assert types(events) == [EventType.ZONE_ENTRY]
    assert events[0].track_id == 1 and events[0].frame_index == 2
    assert events[0].timestamp == pytest.approx(0.4)


def test_inside_to_outside_emits_exit():
    events = run(make(), [0.1, 0.7, 0.8, 0.3])
    assert types(events) == [EventType.ZONE_ENTRY, EventType.ZONE_EXIT]


def test_no_repeated_events_while_inside():
    events = run(make(), [0.1] + [0.6 + 0.01 * i for i in range(20)])
    assert types(events) == [EventType.ZONE_ENTRY]


def test_first_observation_inside_sets_state_without_event():
    events = run(make(), [0.7, 0.8, 0.9])
    assert events == []


def test_hysteresis_suppresses_boundary_jitter():
    # One-sample excursions do not count with confirm_samples=2.
    jitter = [0.4, 0.55, 0.45, 0.52, 0.48, 0.49]
    assert run(make(confirm=2), jitter) == []
    assert len(run(make(confirm=1), jitter)) == 4


def test_confirmed_event_uses_first_crossing_timestamp():
    events = run(make(confirm=3), [0.1, 0.6, 0.7, 0.8])
    assert len(events) == 1
    assert events[0].frame_index == 1
    assert events[0].timestamp == pytest.approx(0.2)
    assert events[0].details["confirmed_at"] == pytest.approx(0.6)


def test_point_on_boundary_counts_as_inside():
    events = run(make(), [0.3, 0.5])
    assert types(events) == [EventType.ZONE_ENTRY]


def test_brief_track_loss_keeps_state():
    # Inside, missing for 0.4s (< 2s timeout), seen inside again: no duplicate entry.
    events = run(make(lost_timeout=2.0), [0.1, 0.7, None, None, 0.75, 0.8])
    assert types(events) == [EventType.ZONE_ENTRY]


def test_track_loss_beyond_timeout_resets_state_without_exit():
    xs = [0.1, 0.7] + [None] * 15 + [0.8, 0.1]
    events = run(make(lost_timeout=1.0), xs)
    # Entry, then state forgotten (no exit emitted for the gap); on reappearance
    # inside the state is re-initialized, and the later exit is a real transition.
    assert types(events) == [EventType.ZONE_ENTRY, EventType.ZONE_EXIT]


def test_reentry_after_exit_counts_again():
    events = run(make(), [0.1, 0.7, 0.2, 0.8])
    assert types(events) == [EventType.ZONE_ENTRY, EventType.ZONE_EXIT, EventType.ZONE_ENTRY]


def test_detections_without_track_id_are_ignored():
    assert run(make(), [0.1, 0.7, 0.2], track_id=None) == []


def test_restricted_zone_emits_restricted_entry():
    events = run(make(zone_type=ZoneType.RESTRICTED), [0.1, 0.7])
    assert types(events) == [EventType.RESTRICTED_ENTRY]


def test_emit_flags():
    assert types(run(make(emit_entries=False), [0.1, 0.7, 0.2])) == [EventType.ZONE_EXIT]
    assert types(run(make(emit_exits=False), [0.1, 0.7, 0.2])) == [EventType.ZONE_ENTRY]


def test_class_filter():
    m = make(class_filter=("car",))
    assert run(m, [0.1, 0.7]) == []


def test_multiple_tracks_are_independent():
    m = make()
    e = []
    e += m.update(0.0, 0, [obs(0.1, 1), obs(0.9, 2)])
    e += m.update(0.2, 1, [obs(0.7, 1), obs(0.2, 2)])
    assert sorted((x.track_id, x.event_type) for x in e) == [(1, "zone_entry"), (2, "zone_exit")]


def test_occupancy_threshold_fires_once_and_rearms():
    m = make(occupancy_threshold=1, occupancy_cooldown=0.0)
    events = []
    t = 0.0

    def step(*frame):
        nonlocal t
        events.extend(m.update(t, int(t * 10), list(frame)))
        t += 0.1

    step(obs(0.1, 1), obs(0.1, 2))
    step(obs(0.7, 1), obs(0.1, 2))  # occupancy 1
    step(obs(0.7, 1), obs(0.7, 2))  # occupancy 2 > 1 -> alert
    step(obs(0.7, 1), obs(0.8, 2))  # still exceeded -> no repeat
    step(obs(0.7, 1), obs(0.2, 2))  # back to 1 -> re-armed
    step(obs(0.7, 1), obs(0.7, 2))  # exceeded again -> second alert
    alerts = [e for e in events if e.event_type == EventType.OCCUPANCY_EXCEEDED]
    assert len(alerts) == 2
    assert alerts[0].occupancy == 2 and alerts[0].details == {"threshold": 1}
    assert m.peak_occupancy["z"] == 2


def test_occupancy_cooldown_delays_repeat_alerts():
    m = make(occupancy_threshold=0, occupancy_cooldown=5.0)
    events = []
    # Re-armed at t=2 and t=4, but the 5s cooldown since t=1 blocks alerts
    # until t=6, when the zone is still over the threshold.
    xs = [0.1, 0.7, 0.2, 0.7, 0.2, 0.7, 0.8]
    for i, x in enumerate(xs):
        events += m.update(i * 1.0, i, [obs(x)])
    alerts = [e for e in events if e.event_type == EventType.OCCUPANCY_EXCEEDED]
    assert [a.timestamp for a in alerts] == [1.0, 6.0]


def test_occupancy_changes_are_recorded_as_change_points():
    m = make()
    run(m, [0.1, 0.7, 0.8, 0.2])
    assert [(c.timestamp, c.occupancy) for c in m.occupancy_changes] == [
        (0.0, 0), (pytest.approx(0.2), 1), (pytest.approx(0.6), 0)
    ]


def test_timeline_order_enforced():
    m = make()
    m.update(1.0, 10, [])
    with pytest.raises(ValueError):
        m.update(0.5, 5, [])


def test_invalid_parameters():
    with pytest.raises(ValueError):
        make(confirm=0)
    with pytest.raises(ValueError):
        make(lost_timeout=0)

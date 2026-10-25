"""Geometry helpers in the *normalized source-frame* coordinate system.

Coordinate system used everywhere in ZoneVision (DB, API, frontend):

* origin (0, 0) is the top-left corner of the source video frame,
* x grows to the right and y grows downwards,
* (1, 1) is the bottom-right corner, independent of resolution.

Because both bounding boxes and zone polygons live in this space, zone tests
are resolution independent and the frontend only has to map [0,1]^2 onto the
rectangle where the video content is actually rendered.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

import cv2
import numpy as np

Point = tuple[float, float]
BBox = tuple[float, float, float, float]  # x1, y1, x2, y2

MIN_POLYGON_AREA = 1e-4  # 0.01% of the frame
MAX_POLYGON_POINTS = 64


class PolygonError(ValueError):
    pass


class AnchorMode(StrEnum):
    BOTTOM_CENTER = "bottom_center"
    CENTER = "center"


def _clip01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def normalize_bbox(xyxy: Sequence[float], width: int, height: int) -> BBox:
    """Convert pixel xyxy to normalized xyxy, clipped to the frame."""
    if width <= 0 or height <= 0:
        raise ValueError("Frame dimensions must be positive")
    x1, y1, x2, y2 = (float(v) for v in xyxy)
    return (
        _clip01(min(x1, x2) / width),
        _clip01(min(y1, y2) / height),
        _clip01(max(x1, x2) / width),
        _clip01(max(y1, y2) / height),
    )


def denormalize_bbox(bbox: BBox, width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    return (round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height))


def bbox_anchor(bbox: BBox, mode: AnchorMode | str = AnchorMode.BOTTOM_CENTER) -> Point:
    """Representative point of a box used for zone membership.

    Bottom-center approximates where a person or vehicle touches the ground,
    which matches how floor-plane zones are usually drawn on CCTV footage and
    avoids counting a tall person as "inside" just because their head overlaps
    the polygon.
    """
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    if AnchorMode(mode) is AnchorMode.CENTER:
        return (cx, (y1 + y2) / 2.0)
    return (cx, y2)


def polygon_area(points: Sequence[Point]) -> float:
    """Absolute shoelace area."""
    n = len(points)
    s = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True

    def on_seg(a: Point, b: Point, c: Point) -> bool:
        return (
            min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
        )

    return (
        (d1 == 0 and on_seg(p3, p4, p1))
        or (d2 == 0 and on_seg(p3, p4, p2))
        or (d3 == 0 and on_seg(p1, p2, p3))
        or (d4 == 0 and on_seg(p1, p2, p4))
    )


def is_self_intersecting(points: Sequence[Point]) -> bool:
    n = len(points)
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            # Adjacent edges share a vertex by construction; skip them.
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segments_intersect(*edges[i], *edges[j]):
                return True
    return False


def validate_polygon(raw: Sequence[Sequence[float]]) -> list[list[float]]:
    """Validate and canonicalize a normalized polygon.

    Rules: 3..64 vertices, each coordinate finite and within [0, 1], no
    duplicate consecutive vertices, non-zero area, no self-intersection.
    """
    if not isinstance(raw, Sequence) or len(raw) < 3:
        raise PolygonError("A polygon needs at least 3 points.")
    if len(raw) > MAX_POLYGON_POINTS:
        raise PolygonError(f"A polygon can have at most {MAX_POLYGON_POINTS} points.")
    pts: list[Point] = []
    for p in raw:
        if not isinstance(p, Sequence) or len(p) != 2:
            raise PolygonError("Each point must be an [x, y] pair.")
        x, y = float(p[0]), float(p[1])
        if not (np.isfinite(x) and np.isfinite(y)):
            raise PolygonError("Point coordinates must be finite numbers.")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise PolygonError("Point coordinates must be normalized to the range [0, 1].")
        pts.append((round(x, 6), round(y, 6)))
    # Drop an explicit closing vertex if the client repeated the first point.
    if len(pts) > 3 and pts[0] == pts[-1]:
        pts.pop()
    for i in range(len(pts)):
        if pts[i] == pts[(i + 1) % len(pts)]:
            raise PolygonError("Polygon contains duplicate consecutive points.")
    if is_self_intersecting(pts):
        raise PolygonError("Polygon edges must not cross each other.")
    if polygon_area(pts) < MIN_POLYGON_AREA:
        raise PolygonError("Polygon area is too small or its points are collinear.")
    return [[x, y] for x, y in pts]


class Polygon:
    """Pre-built contour for repeated point-in-polygon tests.

    Boundary rule: a point exactly on an edge or vertex counts as INSIDE
    (cv2.pointPolygonTest returns 0 for on-edge points, +1 inside, -1 outside).
    """

    def __init__(self, points: Sequence[Sequence[float]]):
        self.points = [(float(x), float(y)) for x, y in points]
        self._contour = np.asarray(self.points, dtype=np.float32).reshape(-1, 1, 2)

    def contains(self, point: Point) -> bool:
        res = cv2.pointPolygonTest(self._contour, (float(point[0]), float(point[1])), False)
        return res >= 0

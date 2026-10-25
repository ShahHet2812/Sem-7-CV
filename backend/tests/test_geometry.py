import pytest

from app.cv.geometry import (
    AnchorMode,
    Polygon,
    PolygonError,
    bbox_anchor,
    denormalize_bbox,
    is_self_intersecting,
    normalize_bbox,
    polygon_area,
    validate_polygon,
)

SQUARE = [[0.2, 0.2], [0.6, 0.2], [0.6, 0.6], [0.2, 0.6]]


class TestPointInPolygon:
    def test_inside_and_outside(self):
        poly = Polygon(SQUARE)
        assert poly.contains((0.4, 0.4))
        assert not poly.contains((0.1, 0.4))
        assert not poly.contains((0.7, 0.7))

    @pytest.mark.parametrize("point", [(0.2, 0.4), (0.6, 0.3), (0.4, 0.2), (0.4, 0.6)])
    def test_point_on_edge_counts_as_inside(self, point):
        assert Polygon(SQUARE).contains(point)

    @pytest.mark.parametrize("point", [(0.2, 0.2), (0.6, 0.6)])
    def test_vertex_counts_as_inside(self, point):
        assert Polygon(SQUARE).contains(point)

    def test_concave_polygon(self):
        # "U" shape: the notch (0.5, 0.2) is outside.
        u = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.5], [0.7, 0.5], [0.7, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        poly = Polygon(validate_polygon(u))
        assert not poly.contains((0.5, 0.2))
        assert poly.contains((0.5, 0.7))
        assert poly.contains((0.2, 0.2))


class TestValidatePolygon:
    def test_valid_polygon_is_canonicalized(self):
        assert validate_polygon(SQUARE) == SQUARE

    def test_closing_vertex_is_dropped(self):
        assert validate_polygon([*SQUARE, SQUARE[0]]) == SQUARE

    @pytest.mark.parametrize(
        "pts, msg",
        [
            ([[0.1, 0.1], [0.2, 0.2]], "at least 3"),
            ([[0.1, 0.1], [1.2, 0.2], [0.3, 0.5]], "range"),
            ([[0.1, 0.1], [-0.1, 0.2], [0.3, 0.5]], "range"),
            ([[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]], "collinear"),
            ([[0.1, 0.1], [0.1, 0.1], [0.3, 0.5]], "duplicate"),
            ([[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]], "cross"),
            ([[0.1, 0.1], [0.1002, 0.1], [0.1, 0.1002]], "too small"),
            ([[0.1, 0.1, 0.3], [0.2, 0.2], [0.3, 0.5]], "pair"),
        ],
    )
    def test_invalid_polygons(self, pts, msg):
        with pytest.raises(PolygonError, match=msg):
            validate_polygon(pts)

    def test_nan_rejected(self):
        with pytest.raises(PolygonError):
            validate_polygon([[float("nan"), 0.1], [0.5, 0.1], [0.5, 0.5]])

    def test_too_many_points(self):
        import math

        pts = [[0.5 + 0.4 * math.cos(i / 70 * 6.283), 0.5 + 0.4 * math.sin(i / 70 * 6.283)] for i in range(70)]
        with pytest.raises(PolygonError, match="at most"):
            validate_polygon(pts)

    def test_area_and_self_intersection_helpers(self):
        assert polygon_area([(0, 0), (1, 0), (1, 1), (0, 1)]) == pytest.approx(1.0)
        assert is_self_intersecting([(0, 0), (1, 1), (1, 0), (0, 1)])
        assert not is_self_intersecting([(0, 0), (1, 0), (1, 1), (0, 1)])


class TestBoxes:
    def test_normalize_and_clip(self):
        assert normalize_bbox((-10, 20, 330, 220), 320, 240) == pytest.approx((0.0, 20 / 240, 1.0, 220 / 240))

    def test_normalize_orders_corners(self):
        assert normalize_bbox((100, 100, 50, 60), 200, 200) == pytest.approx((0.25, 0.3, 0.5, 0.5))

    def test_normalize_requires_positive_dims(self):
        with pytest.raises(ValueError):
            normalize_bbox((0, 0, 1, 1), 0, 10)

    def test_roundtrip(self):
        box = normalize_bbox((64, 48, 128, 96), 640, 480)
        assert denormalize_bbox(box, 640, 480) == (64, 48, 128, 96)

    def test_anchor_modes(self):
        box = (0.2, 0.2, 0.4, 0.8)
        assert bbox_anchor(box) == pytest.approx((0.3, 0.8))
        assert bbox_anchor(box, AnchorMode.CENTER) == pytest.approx((0.3, 0.5))

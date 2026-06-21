"""Court geometry for filtering and normalising person detections.

A :class:`CourtModel` is built from the four labelled court corners (in the
coordinate space of the *extracted* frames) and provides two operations the
motion pipeline needs:

* :meth:`CourtModel.on_court` — reject detections (spectators, players on
  adjacent courts) whose foot-point falls outside a slightly dilated court
  polygon.  This is what makes the motion signal immune to neighbouring-court
  activity.
* :meth:`CourtModel.to_court_plane` — project foot-points onto a normalised
  ``[0, 1] x [0, 1]`` top-down court plane so motion features are consistent
  across videos with different camera positions and resolutions.

Corner ordering follows the project convention (see
``src/ui/widgets/court_calibrator.py`` and ``ml/video_features.py``): the four
points trace the court perimeter starting at Team 1's baseline, so passing them
straight to :func:`ml.video_features.compute_homography` maps Team 1's baseline
to the canonical top edge.  The net therefore runs across the canonical
mid-line, i.e. normalised ``y = 0.5`` — the split used by the cross-net feature.
"""

from __future__ import annotations

import cv2
import numpy as np

from ml.video_features import CANONICAL_SIZE, compute_homography

__all__ = ["CourtModel", "foot_point"]


def foot_point(box: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return the foot-point (bottom-centre) of an ``(x1, y1, x2, y2)`` box.

    The bottom-centre approximates where a standing person contacts the floor,
    which is the point that should lie inside the court polygon — far more
    discriminative than the box centroid, which sits at torso height.
    """
    x1, y1, x2, y2 = box
    return ((x1 + x2) * 0.5, y2)


class CourtModel:
    """Perspective model of one court built from four labelled corners."""

    def __init__(
        self,
        corners: list[tuple[float, float]] | np.ndarray,
        canonical_size: tuple[int, int] = CANONICAL_SIZE,
        dilation: float = 0.12,
    ) -> None:
        """Build the model.

        Args:
            corners: Four ``(x, y)`` court corners in the *extracted-frame*
                pixel space (scale them with
                :func:`ml.video_features.resolve_extract_geometry` first if the
                frames were downscaled for detection).
            canonical_size: Canonical court-plane size ``(width, height)``; only
                its aspect/scale matters since outputs are normalised.
            dilation: Fraction by which the court polygon is expanded about its
                centroid before the membership test, to keep players who step
                just off-court during a rally (~10-15% per the design doc).

        Raises:
            ValueError: If ``corners`` does not contain exactly four points.
        """
        pts = np.asarray(corners, dtype=np.float64)
        if pts.shape != (4, 2):
            raise ValueError(
                f"CourtModel needs exactly 4 (x, y) corners, got shape {pts.shape}"
            )

        self.corners = pts
        self.canonical_size = canonical_size
        # Team-order corners are already in perimeter order, so they map directly
        # to compute_homography's expected TL, TR, BR, BL convention.
        self.homography = compute_homography(
            [(float(x), float(y)) for x, y in pts], canonical_size
        )

        # Dilate the (convex-hull-ordered) quad about its centroid for the
        # membership test.  Convex hull guarantees a non-self-intersecting
        # polygon regardless of the stored winding.
        hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2)
        centroid = hull.mean(axis=0)
        self._poly = (centroid + (hull - centroid) * (1.0 + dilation)).astype(
            np.float32
        )

    def on_court(self, x: float, y: float) -> bool:
        """True if pixel ``(x, y)`` lies inside the dilated court polygon."""
        return cv2.pointPolygonTest(self._poly, (float(x), float(y)), False) >= 0

    def filter_on_court(
        self, foot_points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Return only the foot-points that fall inside the court polygon."""
        return [(x, y) for (x, y) in foot_points if self.on_court(x, y)]

    def to_court_plane(
        self, points: list[tuple[float, float]] | np.ndarray
    ) -> np.ndarray:
        """Project pixel points onto the normalised ``[0, 1]^2`` court plane.

        Args:
            points: ``(N, 2)`` pixel coordinates in the extracted-frame space.

        Returns:
            ``(N, 2)`` float32 array of normalised court coordinates.  ``y < 0.5``
            is Team 1's half, ``y > 0.5`` Team 2's half (net at ``y = 0.5``).
            Empty input yields a ``(0, 2)`` array.
        """
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        if pts.shape[0] == 0:
            return np.empty((0, 2), dtype=np.float32)
        warped = cv2.perspectiveTransform(pts, self.homography).reshape(-1, 2)
        w, h = self.canonical_size
        return warped / np.array([w, h], dtype=np.float32)

    @property
    def polygon(self) -> np.ndarray:
        """The dilated court polygon as an ``(k, 2)`` float32 array (for drawing)."""
        return self._poly

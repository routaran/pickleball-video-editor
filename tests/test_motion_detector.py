"""Tests for ml.motion.detector parsing + tracker plumbing (no GPU/ultralytics).

These exercise the ultralytics-free seams of the detector: the tracking-result
parser and the per-video tracker reset.  The full YOLO+ByteTrack path is only
runnable in ``.venv-motion`` and is out of scope for the cheap test suite.
"""

from __future__ import annotations

import numpy as np

from ml.motion.detector import MotionDetector


class _FakeTensor:
    """Mimics the ``.cpu().numpy()`` chain ultralytics tensors expose."""

    def __init__(self, arr):
        self._arr = np.asarray(arr)

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class _FakeBoxes:
    def __init__(self, xyxy, ids):
        self.xyxy = _FakeTensor(xyxy) if xyxy is not None else None
        self.id = _FakeTensor(ids) if ids is not None else None
        self._n = 0 if xyxy is None else len(xyxy)

    def __len__(self):
        return self._n


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


def test_parse_result_with_track_ids():
    res = _FakeResult(_FakeBoxes([[0, 0, 10, 20], [5, 5, 15, 25]], [3.0, 7.0]))
    boxes, ids = MotionDetector._boxes_ids_from_result(res)
    assert boxes == [(0.0, 0.0, 10.0, 20.0), (5.0, 5.0, 15.0, 25.0)]
    np.testing.assert_array_equal(ids, [3, 7])
    assert ids.dtype == np.int64


def test_parse_result_no_ids_falls_back_to_minus_one():
    res = _FakeResult(_FakeBoxes([[0, 0, 10, 20]], ids=None))
    boxes, ids = MotionDetector._boxes_ids_from_result(res)
    assert len(boxes) == 1
    np.testing.assert_array_equal(ids, [-1])


def test_parse_result_id_count_mismatch_falls_back():
    # Defensive: misaligned id count -> all -1 rather than a wrong mapping.
    res = _FakeResult(_FakeBoxes([[0, 0, 10, 20], [5, 5, 15, 25]], [3.0]))
    boxes, ids = MotionDetector._boxes_ids_from_result(res)
    assert len(boxes) == 2
    np.testing.assert_array_equal(ids, [-1, -1])


def test_parse_empty_result():
    boxes, ids = MotionDetector._boxes_ids_from_result(_FakeResult(_FakeBoxes(None, None)))
    assert boxes == []
    assert ids.shape == (0,)


def test_reset_trackers_is_safe_without_model():
    # Before any track() call there is no predictor/trackers; reset is a no-op.
    det = MotionDetector()
    det._model = object()  # no .predictor attribute
    det._reset_trackers()  # must not raise


def test_reset_trackers_calls_reset_on_each():
    class _Tracker:
        def __init__(self):
            self.reset_calls = 0

        def reset(self):
            self.reset_calls += 1

    class _Predictor:
        def __init__(self, trackers):
            self.trackers = trackers

    class _Model:
        def __init__(self, predictor):
            self.predictor = predictor

    trackers = [_Tracker(), _Tracker()]
    det = MotionDetector()
    det._model = _Model(_Predictor(trackers))
    det._reset_trackers()
    assert all(t.reset_calls == 1 for t in trackers)

"""Evaluation utilities for the ML winner prediction pipeline."""

from ml.evaluation.event_metrics import (
    aggregate_video_metrics,
    interval_detection_metrics,
    match_intervals,
)
from ml.evaluation.game_metrics import (
    aggregate_game_metrics,
    game_score_sequence_metrics,
)
from ml.evaluation.split_manifest import (
    SplitLeakageError,
    SplitManifest,
    SplitManifestEntry,
    SplitManifestError,
    detect_split_leakage,
    load_split_manifest,
    load_split_manifests,
)

__all__ = [
    # event_metrics
    "match_intervals",
    "interval_detection_metrics",
    "aggregate_video_metrics",
    # game_metrics
    "game_score_sequence_metrics",
    "aggregate_game_metrics",
    # split_manifest
    "SplitManifest",
    "SplitManifestEntry",
    "SplitManifestError",
    "SplitLeakageError",
    "load_split_manifest",
    "detect_split_leakage",
    "load_split_manifests",
]

"""Motion-fusion rally segmentation (Stage-1 corrective signal).

This package adds an independent **on-court motion signal** that fuses, late,
with the existing audio rally detector (``ml/model.py`` -> ``ml/predict.py``).
The audio detector's measured weak point is low precision (false rally segments
triggered by neighbouring-court audio in a multi-court facility).  Person
detection filtered to the court via the labelled corners is immune to that audio
bleed, so the two signals fail in non-overlapping ways.

Pipeline:

1. ``detector.MotionDetector`` — YOLOv8n (ultralytics, pre-trained COCO,
   "person" only) over frames streamed from the system ffmpeg CLI, filtered to
   the court polygon and projected onto the canonical court plane.
2. ``features`` — collapse per-frame on-court detections into a small scalar
   feature series, then resample onto the audio model's window centre-times.
3. ``fusion`` — veto/sustain rules with hysteresis applied to the audio binary
   stream.
4. ``predict_fused`` — end-to-end: audio window probabilities + cached motion
   features -> corrected rally intervals matching ``predict_video``'s contract.

Detection runs only as an *offline batch* step that decodes via an ffmpeg
subprocess (ultralytics' own cv2 reader is never used here), keeping the
no-in-process-video-libs invariant the GUI relies on.  Nothing in this package
is imported by the GUI.
"""

__all__ = ["court_filter", "features", "fusion"]

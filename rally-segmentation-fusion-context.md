# Rally Segmentation Fusion Pipeline — Knowledge Transfer

## Context

This document transfers design context from a conversation about improving an existing audio-based rally segmentation system for pickleball video editing. The goal is to add YOLO-based motion detection as a second signal, fused with the existing audio classifier to reduce errors. This is not a ground-up model — it is a composed pipeline of existing tools with corrective fusion logic.

## Problem Statement

Given a mobile phone recording of a pickleball doubles game, automatically segment the video into rallies and dead time so that dead time can be cut from the final edit.

An audio-based classifier already exists and works reasonably well. Its errors stem from a specific environmental condition: the videos are recorded in a multi-court facility where neighboring court sounds bleed into the audio. This causes two failure modes:

1. **False positives:** Audio from a neighboring court triggers rally detection when the target court is idle.
2. **Premature truncation:** Ambient noise from neighboring courts drowns out quiet play (dink exchanges, brief pauses), causing the classifier to end a rally too early.

## Why Motion Fixes This

Audio from neighboring courts produces zero movement signal on the target court. YOLO-based player detection filtered to the target court's boundaries is completely immune to neighboring court audio. The two signals fail in non-overlapping ways, making fusion effective.

## Existing Labeled Data

- ~60-70 video recordings of pickleball games
- Each video has: rally start/end timestamps, score after each rally, game winners
- Each video has: 4 court corner points labeled (bottom-left, bottom-right, top-right, top-left)
- First server always starts but their near/far position is **not** labeled
- Videos are from a multi-court indoor facility with variable camera positions across recordings

## Architecture Decision: Late Fusion with Veto/Sustain

**Rejected alternative:** Feature-level fusion (concatenating audio + motion features into a single vector and training a new classifier). Rejected because it requires more training data, loses interpretability, and doesn't exploit the known asymmetry of the failure modes.

**Chosen approach:** Both classifiers run independently. The motion signal has two specific override powers:

- **Veto power over audio false positives:** When audio says "rally" but on-court motion features show no active play pattern (low detection count, low displacement, no two-and-two spatial distribution), the audio detection is vetoed.
- **Sustain power over audio false negatives:** When audio says "rally ended" but on-court detections still show 4 players in active, distributed positions, the rally state is sustained.

Audio remains the primary trigger because it has better temporal precision for detecting rally start (the serve sound is acoustically sharp and distinctive; player positioning shifts are gradual).

## Implementation Steps

### Step 1 — Validate YOLO Detections

Run YOLOv8n (nano variant, "person" class only) on a single video at 5 fps. Overlay raw bounding boxes on frames and visually verify:

- Detection quality under facility lighting and camera angle
- Whether spectators or people on adjacent courts are detected (they will be — court filtering handles this in step 2)
- Whether players are reliably detected during fast movement, when clustered at the net, or when partially occluded

YOLOv8n is sufficient for this task. Larger YOLO variants add latency without meaningful accuracy gains for detecting "person" at this scale. Pre-trained on COCO, no fine-tuning needed.

**Licensing note:** Ultralytics YOLOv8 is AGPL-3.0. No constraints for personal use on local hardware with no distribution. If AGPL becomes a concern, RT-DETR (Apache 2.0) is a drop-in alternative.

### Step 2 — Court Filtering via Homography

Use the labeled court corners (4 points per video) to compute a perspective transform:

```python
import cv2
import numpy as np

# Real-world pickleball court dimensions: 20ft x 44ft
court_real = np.float32([[0, 0], [20, 0], [20, 44], [0, 44]])
court_pixels = np.float32([...])  # 4 labeled corner points in pixel coords (BL, BR, TR, TL)

H, _ = cv2.findHomography(court_pixels, court_real)
# H maps pixel coords -> court coords
# inv(H) maps court coords -> pixel coords (for drawing court polygon)
```

Define the court polygon in pixel space with ~10-15% dilation to allow for players stepping just off-court during play. Discard any YOLO detection whose foot-point (bottom-center of bounding box) falls outside this polygon.

The homography also enables projecting player positions onto a normalized court plane, which makes motion features consistent across videos with different camera positions.

### Step 3 — Extract Motion Features Per Time Window

Align windows to the audio classifier's temporal resolution. Per window, compute:

| Feature | Description | Rally Signal | Dead Time Signal |
|---------|-------------|-------------|-----------------|
| `mean_detections` | Average on-court person detections per frame in the window | ~4 (all players on court) | Variable (0-6, players wandering) |
| `aggregate_displacement` | Sum of frame-to-frame bounding box centroid movement across all on-court detections | High, sustained | Low or sporadic |
| `spatial_variance` | Variance of detection positions projected onto court plane | High (players distributed) | Low (players clustered near net/bench) |
| `cross_net_symmetry` | Whether detections are roughly balanced across the net line (2 per side) | Strong two-and-two pattern | Weak or absent |

### Step 4 — Build Veto/Sustain Logic

Start with threshold-based rules:

```
# Veto: audio says rally, motion says no
if audio_rally AND mean_detections < 3 AND aggregate_displacement < THRESHOLD_LOW:
    → override to dead_time

# Sustain: audio says dead time, motion says still playing
if audio_dead_time AND mean_detections >= 4 AND cross_net_symmetry > THRESHOLD_SYM:
    → override to rally
```

Apply hysteresis to prevent single-window glitches: a state transition requires the override condition to hold for N consecutive windows (e.g., 2-3 seconds).

Tune all thresholds against the labeled ground truth across the full 60-70 video dataset.

### Step 5 — Measure Improvement

Compare fused system vs audio-only baseline on the labeled set:

- **Precision:** Of all segments labeled as rally, what fraction actually are?
- **Recall:** Of all actual rallies, what fraction were detected?
- **Boundary accuracy:** Mean absolute error of predicted rally start/end vs labeled start/end, in seconds.

## Technical Stack

- **Detection:** YOLOv8n (ultralytics), pre-trained COCO weights, no fine-tuning
- **Compute:** RTX A6000 (YOLOv8n at 640px runs at hundreds of fps on this hardware; processing all 60-70 videos at 5 fps sampling is a few-hours batch job)
- **Homography:** OpenCV (`cv2.findHomography`, `cv2.perspectiveTransform`)
- **Container runtime:** Podman (no Docker)
- **Language:** Python
- **Database:** MariaDB (for storing labeled data, detection results, feature vectors)
- **No budget / no cloud dependency:** Everything runs locally, all tools are open source

## What This Pipeline Does NOT Address (Shelved)

These are acknowledged future work, not current scope:

- **Score tracking:** Requires a state machine driven by rally winner detection, which requires ball tracking. Shelved — will use pre-trained tools in a separate pipeline later.
- **Ball/shuttlecock tracking:** Pickleball is 5-15 pixels in phone footage with motion blur. TrackNet is the closest existing architecture but requires per-frame ball position labels which don't exist yet. Not needed for rally segmentation.
- **Per-player analytics** (kitchen arrival ratio, shot counting, unforced errors): All depend on ball tracking and player identity tracking (ByteTrack/BoT-SORT). Not needed for rally segmentation — tracking adds complexity and identity-swap failure modes that are irrelevant to the current task.
- **Automated court corner detection:** Currently hand-labeled per video. Could be automated later with line detection (Hough transform) + geometric constraints, or a fine-tuned keypoint detector trained on the 60-70 labeled samples.

## Design Principles

- Each component (audio classifier, YOLO detector, court filter, fusion logic) is a self-contained unit with a single responsibility.
- Motion detection was chosen specifically to compensate for the known failure modes of the audio classifier, not as a redundant signal.
- Late fusion with explicit rules was chosen over feature-level fusion for interpretability and independent tunability.
- Full multi-object tracking (ByteTrack/BoT-SORT) was explicitly rejected for this task — per-frame detections are sufficient for aggregate motion features. Tracking is only needed for per-player identity, which is out of scope.
- No custom model training is needed for detection — pre-trained YOLO on COCO handles "person" detection out of the box.

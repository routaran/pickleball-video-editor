# Round 1 analysis

Your diagnosis is sound: the failed ResNet setup is not primarily a bug; it is trying to infer a tiny, sparse, physically decisive signal through a global whole-frame representation with weak rally labels. More resolution inside the same paradigm was unlikely to fix it.

Your proposed replacement — **ball tracking + court geometry + fault rules + abstain** — is directionally right. But I would not make it the only Stage 2 strategy. The best practical plan is a **selective hybrid evidence system**:

1. **Primary high-precision path:** terminal ball tracking + rule decoding.
2. **Supplemental cues:** post-rally behavior, player motion, ball resting/retrieval location, and audio hit timing.
3. **Fusion/abstain layer:** only emit a winner when independent evidence agrees or one cue is very high margin.

Pure ball tracking can work on a valuable subset, but expecting it to solve all rallies from 4 px far-side balls and no ball labels is too optimistic.

---

## 1. Is your approach sound?

Yes, with qualifications.

The key insight is correct: the winner is determined by a **localized physical event**, not by global visual appearance. The model must recover some combination of:

- last hitter side,
- whether the ball crossed the net,
- first bounce location after the last hit,
- whether the receiving side failed to return,
- terminal ball/resting location.

A full-frame classifier trained only on rally-level outcomes has no strong reason to learn that. It will find court/player/video priors first.

So the replacement should be **event-centric**, not clip-classification-centric.

However, I would modify your proposal in two important ways:

### A. Do not rely on exact bounce detection everywhere

Single-view bounce inference is hard. The homography is only valid on the ground plane. For airborne balls, projected position can be substantially biased. At bounce, the bias is near zero, but identifying the exact bounce frame/location from a 4–21 px compressed ball is nontrivial.

For many rallies, you can decide the winner without a perfect semantic reconstruction:

- If the last hit comes from side A and the ball never crosses the net before terminal failure: A loses.
- If the ball crosses to side B and first reliable ground contact/resting point is clearly outside: A loses.
- If the ball crosses to side B, lands clearly in, and side B never returns it: B loses.
- If the evidence is near a line, occluded, far-side, or ambiguous: abstain.

So I would frame the goal as:

> Recover enough terminal-event evidence to make a high-confidence winner decision, not necessarily a complete referee-grade event explanation.

### B. Add post-rally/player behavior early, not later

Because abstention is allowed, post-rally cues are likely to provide real coverage. They will not be deterministic, but they may be strong on many clips:

- loser retrieves ball,
- winner turns away / resets,
- failed returner remains near the terminal ball,
- players relax or walk to serving positions,
- ball rolls/stops on the faulting side,
- obvious celebration/frustration gestures.

These cues are less elegant than ball physics, but they may be more robust than far-side 4 px bounce calls.

I would not replace ball tracking with behavior cues, but I would build both as independent evidence sources.

---

## 2. Hardest failure modes, ranked

### 1. Far-side terminal events

Far ball diameter is about 4 px. Even with ideal detection, centroid error of 1–3 px plus compression blur, lens distortion, and homography error can move the inferred ground point enough to make line calls unreliable.

Approximate scale at far baseline:

- far baseline width ≈ 353 px,
- court width ≈ 6.10 m,
- scale ≈ 58 px/m,
- 2 px error ≈ 3.4 cm laterally before homography/corner/lens error,
- practical error likely closer to 10–25 cm for difficult cases.

That is too large for close line calls.

**Mitigation:**

- Do not call close in/out.
- Use distance-to-line margins:
  - near side: require maybe >10–15 cm from relevant line,
  - far side: require maybe >20–30 cm.
- Report selective accuracy by terminal location: near / mid / far.
- Expect lower far-side coverage.

---

### 2. Occlusion by players, paddles, legs, and bodies

The most important frames are often exactly when the ball is near a player or paddle. That is where occlusion and motion clutter are worst.

**Mitigation:**

- Use multi-hypothesis tracking, not greedy Kalman.
- Allow frame gaps of at least 3–8 frames.
- Keep top-K trajectories, not only the best path.
- Use player boxes/masks as context:
  - candidate near a player after a hit is plausible,
  - long motion attached to a limb is suspicious,
  - sudden direction change near a player is likely a paddle hit.

---

### 3. Plausible false tracks from yellow/static distractors and limb motion

You already observed this. Color and motion each fail alone. Worse, some distractors can form smooth-ish paths over short windows.

**Mitigation:**

- Build a per-video static yellow-object mask.
- Penalize candidates persistent at the same location across many frames.
- Penalize candidates moving with a player/limb for long durations.
- Require physically plausible speed/acceleration over at least 0.5–1.0 seconds.
- Use top-K audit: measure whether the real ball is present among top-K tracks even when top-1 fails.

---

### 4. Bounce detection from a single camera

A bounce is a 3D event. In image coordinates, it may not appear as a clean local minimum. The ground-plane homography is only accurate at contact, but contact is what you are trying to infer.

**Mitigation:**

- Treat bounce as a change-point in a piecewise trajectory, not merely an image-space extremum.
- Use multiple signs:
  - velocity/angle discontinuity,
  - speed loss,
  - proximity to court plane inferred by trajectory shape,
  - absence of nearby player contact,
  - audio if bounce/hit separation is available.
- Abstain on weak bounce evidence.
- Prefer coarse decisions: “clearly outside,” “clearly inside and unreturned,” “uncertain.”

---

### 5. Ambiguous terminal semantics

Some sequences are hard even if the ball is tracked:

- ball clips the net and drops,
- player touches but fails to return,
- ball lands near line and rolls,
- double bounce vs late attempt,
- audio rally-end timestamp may lag the actual fault.

**Mitigation:**

- Search a window around the audio end, not only before it.
- Include 1–3 seconds post-rally.
- Detect “no return” by absence of a subsequent high-speed outgoing segment.
- Keep rule outputs as hypotheses with confidence, not hard labels.

---

### 6. Homography/court calibration error

Four clicked corners are useful, but line calls need more precision than winner overlays. Lens distortion and imperfect clicks matter.

**Mitigation:**

- Use homography for coarse side/net/inside/outside reasoning.
- Avoid close calls.
- Optionally refine court lines per video using detected painted lines, but only if needed.
- Store calibration quality metrics and lower confidence on poor calibrations.

---

## 3. Alternatives you may be undervaluing

### A. Weakly supervised learning from 1,847 rally labels

I would not bet on an end-to-end MIL/attention model as the main solution.

The supervision is too weak:

- one binary label per rally,
- no localization,
- many nuisance correlations,
- only ~51 videos / ~40 courts,
- decisive visual event may occupy <1% of frames and <0.01% of pixels.

A weakly supervised model will likely learn:

- court-specific priors,
- player tendencies,
- side imbalance,
- reaction/body-position shortcuts,
- post-rally behavior if included.

That may produce some useful signal, but it is unlikely to learn robust terminal ball physics from scratch.

Where weak supervision **is** useful:

1. **Fusion/calibration layer** over engineered evidence.
2. **Trajectory reranking** among top-K candidate tracks.
3. **Self-training** a ball detector from high-confidence classical tracks.
4. **Post-rally behavior classifier** trained video-wise.

So: weak supervision should support the system, not replace physics.

---

### B. Player-centric cues

Worth adding, but not as the primary determinant.

Likely useful cues:

- which player lunges/reaches/misses near rally end,
- which side stops moving first,
- who retrieves the ball,
- ball resting near one side,
- who walks back to serve/receive positions,
- celebration/frustration gestures.

Weaknesses:

- casual players react inconsistently,
- doubles creates four-agent ambiguity,
- pose estimators may fail on far-side small players,
- body language is culturally/player dependent,
- retrieval does not always imply loser.

Best use:

- train a video-wise cross-validated classifier on post-rally/player features,
- only use high-confidence predictions,
- fuse with ball evidence.

This may give meaningful extra coverage, especially where ball tracking abstains.

---

### C. Post-rally seconds

This is probably the most undervalued alternative.

The product needs rally winner, not referee-grade terminal event reconstruction. Post-rally behavior may often reveal the winner more clearly than the last 300 ms of ball flight.

I would include:

- 0–6 seconds after audio rally end,
- player trajectories by court side,
- ball/resting object if visible,
- who walks toward ball,
- who resets to serve/receive,
- whether one side remains stationary after failing to return,
- gross optical-flow/person-box changes.

This could be a separate “behavioral winner” module.

Expected behavior-module ceiling:

- maybe 60–70% overall accuracy if forced on all rallies,
- potentially 75–85% accuracy on a high-confidence 20–40% subset.

Not enough alone, but valuable with abstain.

---

### D. Audio beyond boundaries

Useful, but probably secondary.

Potentially useful:

- last paddle hit timestamp,
- number/timing of hits near rally end,
- net-cord sound,
- bounce vs paddle sound,
- whether a final paddle hit happened after a bounce.

Limitations:

- single camera mic likely has weak spatial localization,
- court acoustics vary,
- overlapping player/court noise,
- net/bounce sounds may be quiet.

Best use:

- align visual trajectory with hit events,
- identify the last hit time,
- distinguish “ball bounced twice” from “player returned it,”
- increase confidence for net faults.

I would not expect audio alone to identify the winning side unless there is stereo/spatial information.

---

### E. Off-the-shelf detectors

#### Ball detectors

Generic YOLO-style detectors are unlikely to reliably detect a 4 px far pickleball without domain adaptation. Tennis-ball detectors may help, but the domain gap is real:

- different ball size/texture,
- compression,
- pickleball court colors,
- far-side 4 px target,
- heavy clutter.

Useful role:

- candidate generator,
- self-training initialization,
- comparison baseline.

Not sufficient as a direct winner detector.

#### Person detectors / pose

Person boxes are likely useful. Full pose may be less reliable, especially far-side.

Use person detection for:

- masking/penalizing player-attached false positives,
- locating likely paddle-hit zones,
- detecting player motion/reaction,
- post-rally behavior features.

Pose is optional. I would start with boxes/tracks before adding pose complexity.

---

## 4. Concrete robust tracking algorithm

I would use a **candidate-generation + multi-hypothesis graph tracking + rule decoder** architecture.

### Step 1: Decode full-resolution frames

Use the original 1920×1080 frames at 60 fps for the last 3–4 seconds before rally end, plus maybe 1–3 seconds after.

Do not detect on the warped 256×128 view. Use the homography only for geometry and court masking.

---

### Step 2: Define ROI

Use the court polygon plus an out-of-bounds margin.

The margin matters because terminal out balls may land outside the court.

Suggested ROI:

- full court polygon,
- extend laterally and beyond baselines by perhaps 1–2 court meters when projected into image,
- include net area and near surrounding court.

---

### Step 3: Generate high-recall ball candidates

Per frame, produce candidates from several detectors:

#### Color candidates

- HSV/yellow threshold, but adaptive per video.
- Keep small yellow blobs.
- Reject elongated line-like components.
- Reject static yellow objects using a persistence/background mask.

#### Motion candidates

- 3-frame temporal differencing.
- Background subtraction against a per-video median/percentile background.
- Keep small moving blobs.

#### Blob candidates

- Difference-of-Gaussians or Laplacian-of-Gaussian over perspective-aware scales.
- Expected diameter:
  - near: ~21 px,
  - far: ~4 px,
  - interpolate by image/court position.
- Allow wider range because airborne height breaks ground-plane scale.

#### Candidate features

For each candidate store:

- frame index,
- pixel center,
- apparent radius/area,
- color score,
- motion score,
- circularity,
- local contrast,
- persistence penalty,
- proximity to players,
- proximity to court/net/lines,
- detector-source flags.

The candidate generator should favor **recall over precision**. It is okay to keep 20–100 candidates per frame if the tracker can disambiguate.

Critical validation metric:

> In manually audited frames where the ball is visible, is the true ball present among candidates?

If candidate recall is poor, tracking cannot recover.

---

### Step 4: Use multi-hypothesis graph tracking, not simple Kalman

A plain Kalman filter will be too brittle because:

- false positives are frequent,
- the ball disappears,
- hits/bounces cause abrupt changes,
- speed varies sharply by perspective,
- the best local candidate may be wrong.

Use a graph/beam/Viterbi approach.

#### Graph structure

- Node = candidate detection in frame `t`.
- Add virtual miss nodes for short gaps.
- Edges connect candidates across frame gaps of 1–8 frames.
- Edge cost includes:
  - displacement plausibility,
  - perspective-adjusted max speed,
  - acceleration/smoothness,
  - detector confidence,
  - color/motion consistency,
  - persistence penalty,
  - court/ROI plausibility.

#### Second-order motion

Use a second-order dynamic program or beam search where the transition cost depends on the previous two nodes, not just the previous node.

This allows penalizing implausible acceleration while permitting discrete change-points.

#### Change-point modes

Allow special events with lower smoothness penalty:

- paddle hit near player,
- bounce away from player,
- net contact near net plane,
- short occlusion/miss.

Do not force a single globally smooth trajectory. Pickleball trajectories are piecewise smooth.

#### Output

Keep top-K tracks, e.g. K=10–50, with scores.

Do not immediately trust top-1. Many decisions should ask:

- Do the top hypotheses agree on the winner?
- Is the best path much better than the next-best conflicting path?
- Is the terminal event far from a line/net ambiguity?

---

### Step 5: Segment trajectory into events

For each candidate track:

1. Fit piecewise smooth trajectory.
2. Detect high-residual change-points.
3. Classify change-points using context.

Event types:

#### Paddle hit

Likely if:

- abrupt velocity/direction change,
- near a player box/body/paddle region,
- coincides with audio hit,
- outgoing speed increases.

#### Bounce

Likely if:

- change in vertical/image trajectory consistent with contact,
- no nearby player contact,
- speed decreases,
- point lies on/near court surface projection,
- maybe weak bounce audio.

Do not use “image local minimum” alone. That is too brittle.

#### Net fault

Likely if:

- trajectory approaches net line,
- fails to cross or sharply drops/reverses,
- terminal point remains on hitter side or near net,
- optional net sound/visual cue.

---

### Step 6: Decode winner conservatively

For a terminal segment:

#### Determine last hitter side

Use:

- direction of ball immediately after last hit,
- side of court containing last hit/player,
- audio hit timestamp if available,
- player proximity.

If ball travels from near side to far side, near side was last hitter; vice versa.

#### Determine terminal outcome

Cases:

1. **Did not cross net after last hit**
   - hitter loses.

2. **First clear bounce after last hit is outside opponent court**
   - hitter loses.
   - require strong line margin.

3. **First clear bounce is inside opponent court and no return occurs before rally end**
   - opponent side loses.

4. **Ball reaches opponent side, slows/stops/rolls after playable bounce**
   - opponent side likely loses.

5. **Close line, occluded bounce, conflicting tracks, weak last-hitter inference**
   - abstain.

---

## 5. Confidence and abstention

Confidence should not be a neural softmax over the clip. It should be an evidence score.

Useful confidence inputs:

- track duration near terminal event,
- detection density along track,
- top-1 vs top-2 trajectory margin,
- whether top-K hypotheses agree on winner,
- terminal event distance from court lines,
- terminal event distance from net ambiguity,
- near/mid/far court location,
- candidate clutter density,
- occlusion count/gap length,
- last-hitter certainty,
- audio/visual agreement,
- post-rally cue agreement.

Output should be calibrated on video-wise folds.

Report:

- accuracy at coverage thresholds,
- coverage at accuracy thresholds,
- selective risk curve,
- near/mid/far slices,
- event-type slices: net, out, double bounce/unreturned.

A good first milestone would be something like:

- **≥90% accuracy on 25–40% coverage**, or
- **≥85% accuracy on 40–60% coverage**.

If the system only reaches 65–70% accuracy at high coverage, it may still beat the prior but may not be operationally useful unless the UI clearly surfaces uncertainty.

---

## 6. Realistic ceiling

My expectation:

### Classical ball-tracking only, no ball labels

Likely:

- high-confidence near/mid events: 85–95% accuracy,
- coverage: 25–50%,
- all-rally forced accuracy: probably 65–75%, maybe lower depending video quality.

Far-side close line calls and occluded terminal events will dominate failures.

### Ball tracking + post-rally/player/audio fusion

Likely:

- 85–92% accuracy at 40–65% coverage if cues are well-calibrated,
- possibly higher on good camera angles/courts,
- still not reliable enough to auto-label every rally without review.

### With modest manual ball/event labels

If you label even a small set — say 100–300 terminal events with ball positions/bounce/outcome — the ceiling improves substantially.

Likely:

- better candidate scoring,
- better TrackNet-style heatmap detector,
- better event classifier,
- better confidence calibration.

This may push toward:

- 85–95% accuracy at 60–80% coverage,
- depending heavily on far-side visibility.

I would strongly recommend a small annotated terminal-event validation set, even if not used for training. Rally-level labels alone are too coarse to debug tracking.

---

## 7. What is likely to work

Likely worth doing:

1. Full-resolution candidate generation in original image coordinates.
2. Static distractor suppression per video.
3. Multi-hypothesis graph tracking.
4. Conservative rule decoder with abstain.
5. Post-rally behavior features.
6. Audio hit timing alignment.
7. Video-wise cross-validation with selective accuracy/coverage.
8. Small manually audited terminal-event set for debugging.

---

## 8. What is likely to disappoint

Likely poor ROI:

1. Another whole-frame classifier, even higher resolution.
2. End-to-end MIL from only 1,847 rally labels.
3. Generic YOLO ball detection without domain adaptation.
4. Exact far-side in/out calls near lines.
5. Pose-heavy systems before simpler person-box/player-motion features.
6. Treating homography-mapped airborne ball coordinates as true ground coordinates.
7. Greedy Kalman tracking with one best candidate per frame.

---

## Recommended plan

I would build this in phases.

### Phase 1: Feasibility audit

Before full implementation, manually inspect/annotate a small stratified sample:

- 100–200 rallies,
- near/mid/far terminal events,
- net/out/double-bounce cases,
- mark terminal ball path/bounce roughly.

Measure:

- candidate recall,
- top-K track oracle coverage,
- line-margin ambiguity,
- winner recoverability from ball alone.

This tells you whether classical tracking can carry the system.

### Phase 2: Ball evidence module

Implement:

- high-recall candidates,
- graph/beam tracking,
- top-K trajectories,
- conservative terminal rule decoder,
- confidence/abstain.

Target:

- high precision first,
- do not chase full coverage.

### Phase 3: Behavioral/audio evidence module

Add:

- post-rally player tracks,
- ball/resting/retrieval cues,
- audio last-hit timing,
- simple video-wise trained classifier.

### Phase 4: Fusion

Use a simple calibrated model or rule-based fusion:

- if ball module high confidence: use it,
- if ball and behavior agree: boost confidence,
- if they disagree: abstain,
- if behavior alone is high confidence and ball absent: maybe emit with lower tier confidence.

### Phase 5: Optional learned ball detector

Only after collecting high-confidence pseudo-labels and some human corrections:

- train a small heatmap detector,
- use it to improve candidate scoring,
- keep graph tracking and abstention.

Do not jump directly to TrackNet without labels unless classical coverage is clearly blocked by detection recall.

---

## Round-1 position summary

Your proposed ball-tracking/rules approach is the right core replacement for the failed classifier, but I would not make it a pure ball-only system. The stronger practical plan is a **selective hybrid**: full-resolution multi-hypothesis ball tracking for high-confidence terminal events, plus post-rally/player/audio cues, fused with conservative abstention. The largest risks are far-side 4 px balls, occlusion, false smooth tracks, and single-view bounce ambiguity. Realistically, no-label classical tracking may deliver high accuracy on a useful subset, not full automation; with modest terminal-event labels and hybrid cues, substantially higher coverage becomes plausible.

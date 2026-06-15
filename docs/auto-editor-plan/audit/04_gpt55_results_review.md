## 1. Read of the result

Yes: this is **Outcome 2 — tracker-not-good-enough / ambiguous**, not a valid no-go and not a build signal.

The model’s apparent signal is too contaminated to interpret:

- **Geometric leave-date accuracy = 0.558**, exactly at the **95th percentile permutation null**. That is borderline at best.
- **Nuisance-only = 0.543**, very close to the geometric model. That means some of the “signal” may be video/date/quality artifact, not ball geometry.
- **Per-video oracle baseline = 0.685** is a warning: there is substantial video-specific label structure, so any weak model can look better than chance if it leaks recording conditions indirectly.
- The strongest selective accuracies are not compelling:
  - 60% coverage: 0.619 vs prior 0.517 — maybe real.
  - 20% coverage: 0.641 vs prior 0.692 — actually worse than subset prior.

The decisive fact is your overlay finding: **track[0] often follows players/paddles/limbs, not the ball**. Therefore the audit has not yet tested whether terminal ball geometry predicts rally winner. It has mostly tested whether a clutter-tracker’s terminal object geometry weakly correlates with winner labels.

So I agree with your framing: **neither full build nor no-go is justified.**

---

## 2. Single highest-ROI next move

The highest-ROI next move is **not immediately building player-suppression + parabola-RANSAC**.

It is:

> **Create a small ball-ground-truth set and measure candidate recall + oracle trackability before changing the tracker.**

Reason: your current uncertainty is upstream of tracking. You do not yet know whether the true ball is reliably present in the candidate set. If candidate recall is poor, player suppression and RANSAC are polishing the wrong layer. If candidate recall is high but tracker selection is bad, then player suppression/RANSAC is exactly the right next investment.

This is the key decision tree:

```text
Ball candidate recall low
→ improve detection / resolution / background subtraction / learned detector.

Ball candidate recall high, but tracker misses
→ improve association: player suppression, RANSAC, top-K trajectory model.

Ball candidate recall high and oracle geometry predicts winner
→ continue building.

Ball candidate recall high and oracle geometry does not predict winner
→ likely weak-signal/no-go for geometry-only approach.
```

Right now you are missing the measurement that decides which branch you are on.

So the best order is:

1. **Annotate a small set of visible ball positions.**
2. **Measure detector candidate recall.**
3. **Measure whether an oracle can recover a plausible ball track from the candidates.**
4. Then implement **player suppression + trajectory fitting** only if candidate recall is good enough.

---

## 3. Ranked alternatives

### 1. Small ball-GT candidate-recall audit — best next move

This gives you the highest information gain per hour. It tells you whether the ball is even recoverable from the current representation.

### 2. Player-region suppression — likely useful, but should be guided by GT

I agree player-locking is a major failure. But hard exclusion inside person boxes is risky because the ball is often:

- near the hitter,
- near paddle contact,
- partially overlapping the body,
- passing in front of foreground players,
- inside a coarse YOLO person box despite being visible.

Use player boxes as a **soft penalty**, not a hard exclusion, unless GT shows the ball is rarely inside boxes during the terminal frames you care about.

### 3. Parabola/RANSAC trajectory fitting — promising, but depends on candidate recall

RANSAC helps if the true ball appears in the candidate set often enough. If the ball is absent in many frames, it will instead fit clean-looking trajectories through structured clutter.

Also, “gravity parabola” in image/court coordinates is not always clean after camera perspective, spin, bounce, occlusion, and contact events. It can still help, but do not assume constant acceleration alone separates ball from paddle/limb motion.

### 4. Prove feasibility on good-geometry videos only

Useful, but secondary. I would not restrict the whole audit yet. First use the GT sample to stratify by camera quality. If good-camera candidate recall is high and bad-camera recall is terrible, then yes: split the problem into feasibility tier and generalization tier.

### 5. Learned tiny-ball detector / TrackNet-style model

Potentially the long-term answer, but not the next move unless the GT audit shows classical detection recall is poor. You need labels anyway before training or validating a learned detector.

---

## 4. Concrete specifics for the recommended move

Build a small annotation/evaluation set. Do not overbuild it.

### Sample

Use roughly:

- **30–50 rallies**
- stratified across:
  - good / medium / bad camera geometry,
  - near/far baseline visibility,
  - foreground-player occlusion,
  - several dates/videos,
  - both winner classes.
- For each rally, annotate only terminal-relevant frames:
  - e.g. **10–20 frames per rally**, not all 210 frames.
  - Include frames around:
    - last visible flight,
    - bounce/contact if visible,
    - terminal landing/out/dead-ball moment.

That gives you about **300–1000 labeled frames**, enough for a decisive first audit.

### Labels

For each labeled frame:

```text
frame_index
ball_visible: yes/no/uncertain
ball_center_x, ball_center_y if visible
visibility_quality: clear / small / motion-blurred / occluded / uncertain
camera_quality_bucket
notes optional
```

If the human can annotate ~30 rallies, prefer that over autonomous self-marking. Self-marking is acceptable only as a quick triage set, but do not treat it as final evidence.

### Metrics to compute

For each visible ball label:

1. **Candidate recall**
   - Is there any candidate within radius R of the labeled ball?
   - Use multiple radii:
     - 4 px,
     - 8 px,
     - 12 px,
     - maybe scaled by estimated ball size.

2. **Candidate rank**
   - If matched, where does the ball candidate rank among top 40?
   - If the ball is usually rank 35–40, tracking will be fragile.
   - If it is usually rank 1–10, association is the main problem.

3. **Source attribution**
   - Was the matched candidate from:
     - HSV,
     - motion,
     - both?
   - This tells you whether optic-yellow thresholding or motion differencing is carrying recall.

4. **Player-overlap diagnostic**
   - Run your intended person detector on annotated frames.
   - Measure:
     - fraction of true ball labels inside person boxes,
     - fraction near box edges,
     - fraction outside all boxes.
   - This tells you whether hard suppression would delete true positives.

5. **Oracle trackability**
   - Given labeled frames, ask:
     - Is there a candidate near the ball in enough consecutive frames to form a trajectory?
     - Could a top-K tracker recover it if it had the right association objective?
   - This separates detection failure from tracking failure.

6. **Oracle winner signal**
   - For frames/rallies where the true ball is annotated near terminal state, compute the same geometric features from GT positions.
   - Even a crude version helps answer: “If the ball were tracked correctly, is the terminal geometry predictive?”

### Decision thresholds

I would use rough gates like:

```text
Candidate recall ≥ 80–90% on visible clear/small frames
→ detection is probably adequate; invest in tracking/player suppression.

Candidate recall 50–80%
→ improve detector and tracker together; RANSAC may help but detection is fragile.

Candidate recall < 50%
→ do not spend much effort on tracking yet; detection is the bottleneck.
```

For player suppression:

```text
True ball inside person box > 20–30% of visible terminal frames
→ hard suppression is dangerous; use soft penalties/masks.

True ball rarely inside boxes
→ suppression likely high ROI.
```

For feasibility split:

```text
Good-camera recall high, bad-camera recall low
→ prove full pipeline on good-camera subset first.

Recall poor even on good-camera subset
→ classical detector likely insufficient.
```

---

## 5. Anything you are missing

A few issues to watch:

### Top-K should be evaluated, not just track[0]

Since you already have a beam tracker, measure whether the true ball appears in **any of top K tracks**, not only the best track. If top-K contains the ball but rank 1 is wrong, reranking is the problem. If top-K rarely contains it, detection/association is deeper broken.

### Do not let player suppression become label leakage

If person detector quality varies by video/camera/date, its failure modes can become another nuisance channel. Keep the nuisance-only control after adding it.

### Date-grouped CV remains the right primary split

Given the per-video oracle baseline of 0.685, video-grouped and date-grouped splits are both informative. I would keep **date-grouped as primary** and report video-grouped as secondary. Do not tune on all videos and then declare feasibility.

### “Good geometry” subset is useful, but call it what it is

If you evaluate only good videos, label the result as **conditional feasibility**, not general performance. It is still valuable: if the method cannot work on favorable views, it will not work generally.

### Learned detector may become necessary

For a 4–21 px ball under clutter, HSV+motion may hit a ceiling. But you should not jump to TrackNet-style training until the small GT audit tells you whether the current detector has adequate recall.

---

## Bottom line

Your result is ambiguous because the tracker is visibly tracking the wrong object; the current numbers cannot validate or reject the rally-winner geometry idea. The single best next move is a small ball-ground-truth audit measuring candidate recall, candidate rank, player-box overlap, and oracle trackability. If recall is high, proceed with soft player suppression plus trajectory/RANSAC reranking; if recall is low, fix detection before touching the tracker. Do not call no-go until you have tested the model on true ball geometry rather than clutter geometry.

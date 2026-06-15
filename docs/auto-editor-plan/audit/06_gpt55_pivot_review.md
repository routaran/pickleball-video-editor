## 1. My read of the A/B result

Your interpretation is correct, and I would be harsher:

The ball-tracking-geometry path has **failed its first serious falsification test**.

The key result is not just “player suppression made it worse.” It is that:

- **No suppression:** date-grouped accuracy = `0.558`, exactly equal to the per-date prior.
- **With suppression:** date-grouped accuracy = `0.457`, worse than chance-like behavior.
- **Nuisance-only:** `0.543–0.538`, almost as good as the supposed signal model.
- **Permutation:** no convincing evidence of real signal.

That strongly suggests the pre-suppression “signal” was not ball geometry. It was probably some mixture of:

- accidental player-following,
- camera/date/video bias,
- weak court-side prior,
- detector/tracker artifacts,
- highlight/editing correlations.

The player suppression A/B did what a good control should do: it exposed that the tracker was not reliably tracking the thing you care about.

So no: I would not keep tuning this tracker blindly. That is now a low-EV path.

---

## 2. Decision: pivot to behavior now

My recommendation:

**Pivot primary effort to post-rally behavior features immediately. Do not push classical ball tracking further without ball GT.**

Reasoning:

### Ball tracking is currently blocked by missing observability

You cannot tune a tracker if you cannot tell whether it is tracking the ball. The current end-to-end winner metric is too indirect. It lets you optimize accidental correlates and then discover later that they were not ball signal.

That is exactly what happened.

### Behavior uses the labels you already have

You have 1,847 rally-winner labels. Post-rally behavior plausibly depends on the winner/loser outcome and can be measured from person boxes without ball labels.

That makes it a better near-term delivery path.

### Behavior is more aligned with the deployed goal

The user wants a **winner detector**, not a physics reconstruction system. If behavior predicts winner robustly, it is a legitimate solution, especially because human review/abstention already exists.

### Classical ball geometry has high upside but poor current tractability

A visible ball trajectory would be the cleanest semantic cue. But with a 4–21 px ball, heterogeneous cameras, occlusion, partial player detection, and no ball GT, this is not a near-term production path.

So the decision is:

> **Primary path: behavior + possibly audio. Secondary diagnostic path: small human ball GT only if you want to preserve the ball option. Stop blind tracker tuning.**

---

## 3. Behavior-feature design and how to avoid the same traps

The behavior audit should be designed to answer one question:

> “Can post-rally human movement predict winning side above date/video priors under grouped validation?”

Keep it simple. Do not build a deep tracker-reID system first. Start with side-level aggregate behavior.

### Windowing

Use several post-rally windows, because highlights may be truncated:

- `0.0–1.0s`
- `0.0–2.0s`
- `0.5–3.0s`
- `0.0–5.0s` if available
- maybe `-0.5–2.0s` as a robustness check, but be careful not to leak pre-end dynamics if rally_end is label-dependent.

For each rally, record actual usable post-end duration. Use duration mainly for coverage/abstention/control, not as a primary predictive feature unless tested against nuisance baselines.

### Representation

Map detected person footpoints into canonical court coordinates using the homography.

Then aggregate by court side, not by persistent identity:

- near-side team/persons
- far-side team/persons
- optionally left/right within each side if stable enough

Do **side-differenced features** wherever possible:

```text
feature = behavior_side_A - behavior_side_B
```

This reduces camera/date bias and forces the model to learn relative behavior rather than detector confidence.

### Core behavior features

#### A. Movement magnitude after rally end

For each court side:

- total person displacement
- median displacement
- max displacement
- displacement toward own baseline
- displacement toward opponent baseline
- displacement toward net
- displacement away from net
- speed in first 1s / 2s / 5s
- acceleration or movement onset time

Useful derived features:

```text
side_A_total_motion - side_B_total_motion
side_A_max_motion - side_B_max_motion
side_A_motion_onset_time - side_B_motion_onset_time
```

Hypothesis: losing side may move more to retrieve the ball; winning side may disengage/reset.

#### B. “Ball retrieval” proxy

For each side, measure whether any detected player moves toward likely dead-ball regions:

- toward baseline corners
- toward sideline/out-of-bounds areas
- toward net dead zones
- toward where the ball likely ended if you have even weak terminal ball candidates

Even without ball GT, use generic retrieval proxies:

```text
max distance moved away from ready-position area
max movement toward court boundary
player exits central court region
player approaches baseline/sideline
```

Then compare sides.

#### C. Reset-to-serve behavior

After a point, one side prepares to serve/receive. In doubles this may be noisy, but still valuable.

Features:

- count of players near baseline per side after 2–5s
- side whose players become more stationary near baseline
- side with one player moving to serve-like position
- side with two players reforming a ready formation
- change in team spread
- distance between teammates
- whether one side transitions from active movement to stable formation faster

Be careful: serving side after point depends on scoring/side-out rules, not always winner in a trivial way unless you model pickleball serve rules. So treat this as empirical behavior signal, not rule-based truth.

#### D. Disengagement / celebration / pause

For each side:

- reduction in speed after rally end
- players stop moving first
- players turn/walk casually away from ready position
- one side clusters or separates
- one side remains in ready posture longer

From boxes only, you cannot measure pose reliably, but speed/stationarity is enough for an audit.

#### E. Detection-quality features for abstention, not prediction

Track:

- number of detected persons per frame
- fraction of frames with ≥2 detections
- fraction with ≥3/4 detections
- far-side detection count
- post-window duration
- homography in-bounds fraction
- track continuity

Use these to define coverage tiers:

```text
all rallies
usable post-window >= 1s
usable post-window >= 2s
usable post-window >= 3s
good detection quality
```

Do not let the model win purely from “this camera detects far players badly and this date has a winner prior.” Always compare against nuisance-only controls.

---

### Model/evaluation

Use exactly the same discipline as the ball audit:

- simple model first: logistic regression, small tree/GBM only after linear baseline
- date-grouped CV as decisive
- leave-video-out as secondary
- permutation test
- nuisance-only baseline
- date prior baseline
- video/date metadata controls
- coverage-aware reporting
- no random frame leakage across same rally/video/date

Report:

```text
accuracy at all coverage
accuracy at high-quality coverage
coverage
date-prior comparison
nuisance-only comparison
permutation p
confusion by date/video
```

The target is not just “beats 0.558 once.” You want:

- materially above date prior,
- stable across folds,
- beats nuisance-only by a meaningful margin,
- survives permutation,
- does not collapse when post-window length or detection quality is controlled.

---

### Main failure modes and mitigations

#### Failure mode 1: highlight cut leakage

If winners/losers are edited differently, post-rally duration itself may predict label.

Mitigation:

- evaluate fixed-length windows where available;
- include post-window duration in nuisance-only baseline;
- report performance with duration removed;
- stratify by available post-rally length.

#### Failure mode 2: camera/date leakage

Person detector quality differs by camera/date. If labels are imbalanced per date, missingness can look predictive.

Mitigation:

- date-grouped CV remains decisive;
- use side-differenced features;
- compare to nuisance-only;
- avoid raw detector counts as primary features unless controlled.

#### Failure mode 3: far-side under-detection

Far players may be missing, causing asymmetry unrelated to behavior.

Mitigation:

- build features that tolerate missing detections;
- use per-side confidence masks;
- test high-quality subset separately;
- do not overinterpret features requiring all four players.

#### Failure mode 4: rally_end timestamp leakage

If rally_end was generated using label-aware logic or includes post-point editing behavior, features may leak.

Mitigation:

- audit how rally_end is defined;
- test windows starting slightly after rally_end;
- test fixed offsets;
- test pre-end negative controls.

#### Failure mode 5: behavior signal is real but not causal enough

Sometimes the winner retrieves the ball, sometimes the loser does, depending on convenience, serve rotation, and etiquette.

Mitigation:

- do not hand-code winner rules;
- let simple models learn statistical patterns;
- use abstention;
- combine behavior with audio/editing features later.

---

## 4. What to do about ball tracking

Do **not** continue blind classical tuning.

Keep the current tracker as:

1. a diagnostic artifact,
2. possible weak feature source,
3. future path if GT becomes available.

But stop treating it as the primary path.

If you can get even a small human-labeled ball GT set, it is worth doing — but only as a bounded diagnostic, not as the main effort.

Recommended GT scope:

- 20–40 rallies,
- sampled across hard videos/cameras/dates,
- label ball center every 5–10 frames near terminal phase,
- include visibility/occlusion flag,
- include “not visible” labels.

Use it to answer:

- Is the detector finding the ball at all?
- Is top-K beam retaining the ball candidate?
- Where does tracking fail: detection, association, occlusion, player confusion, scale?
- Is the ball signal even extractable from these videos?

If the GT says recall is terrible or association collapses in clutter, stop. If it says candidates are present but association is bad, maybe revisit tracker design later.

But the immediate delivery path should not depend on this.

---

## 5. Anything you are missing

Yes: **audio may be a better companion to behavior than ball tracking.**

Without ball GT, audio can still expose:

- paddle/ball contact cadence,
- final hit timing,
- crowd/player reactions,
- referee/player calls,
- silence/reset behavior,
- highlight cut patterns.

A simple audio audit could be valuable:

- post-rally audio energy,
- speech onset,
- applause/cheer proxy,
- final-impact timing if detectable,
- side-independent audio features combined with behavior.

But be careful: audio is also vulnerable to video/date leakage. Use the same grouped CV and nuisance controls.

The highest-EV next sequence is probably:

1. behavior-only audit;
2. audio-only audit;
3. behavior + audio simple fusion;
4. optional small ball-GT diagnostic.

Do not jump to an end-to-end video model yet. With 1,847 labels and heterogeneous cameras, it may learn camera/date/editing priors unless the split discipline is extremely strict.

---

## Bottom line

The A/B result is a strong stop sign for blind classical ball tracking, not a reason to tune harder. Pivot to post-rally behavior as the primary delivery path because it uses available labels, avoids ball GT, and plausibly captures the actual winner signal. Keep ball tracking parked unless you can obtain a small, focused human GT set to diagnose whether the path is salvageable. The next serious audit should be behavior-only, then audio-only, then behavior+audio under the same grouped controls.

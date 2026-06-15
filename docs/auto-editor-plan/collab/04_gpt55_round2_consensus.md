# Final consensus plan

## 1. Agreed approach

Build a **selective hybrid winner-resolution system**: full-resolution image-space ball/event recovery, audio-assisted last-hitter inference, lightweight player/post-rally behavior cues, and a conservative fusion layer that either emits a calibrated winner or abstains. The system is not trying to referee every rally; it should confidently resolve easy/medium terminal events and route ambiguous cases to the existing review UI. Every result is measured as **accuracy-on-covered** plus **coverage**, with explicit abstain behavior.

---

## 2. Phased plan and go/no-go gates

### Phase 0 — Instrument the existing review UI immediately

Do this before or alongside the audit because it creates the labeling flywheel.

Minimum additions:

1. Existing: reviewer confirms/flips predicted winner.
2. Add one optional terminal-event tag:
   - `net / did not cross`
   - `out`
   - `in / no return`
   - `unknown / other`
3. Add one optional terminal-location/fault-side tag:
   - `near side`
   - `far side`
   - `left/right/deep out`
   - `unknown`
4. On flips or low-confidence cases, ask for one extra click only if tolerable:
   - accept/adjust terminal time, or
   - click/select final visible ball candidate.

This turns normal use into training data for calibration, terminal-event classification, last-hitter inference, and detector self-training.

---

### Phase 1 — Feasibility audit

Use **150–200 stratified rallies**, not fewer than 100. Stratify by:

- near-side vs far-side terminal event
- net fault / out / in-no-return / unknown
- singles vs doubles
- good vs poor lighting/compression
- clean vs occluded terminal sequence
- highlight cut with ≥6 s post-rally vs truncated post-rally
- existing cascade confidence high/medium/low

Each rally gets two human reviewers plus adjudication for:

- true winner
- terminal event type
- last-hitter side
- approximate terminal time
- whether the decisive evidence is visible
- post-rally availability duration

#### Ball-path audit metrics

Measure:

1. **Candidate recall**
   - Top-K candidate contains true ball in visible terminal frames.
   - Use K=10 initially.
   - Count separately for near, mid, and far-side events.
   - Report frame-level recall and event-level recall.

2. **Trajectory recoverability**
   - Whether a plausible top-K trajectory can recover:
     - last hit direction,
     - crossed / did not cross net,
     - terminal bounce/contact zone,
     - clear in/out with margin.

3. **Human ball-only recoverability**
   - Human sees only terminal ball evidence, not post-rally reactions.
   - They may abstain.
   - Measure accuracy-on-covered and coverage.

4. **Line-margin safety**
   - Near-side line calls only trusted if margin >10–15 cm.
   - Far-side line calls only trusted if margin >20–30 cm.
   - Anything inside margin becomes abstain.

#### Post-rally behavior audit metrics

Measure on the same rallies:

1. **Post-rally availability**
   - Percent with ≥2 s, ≥4 s, and ≥6 s after terminal event before cut.
   - Usable behavior window requires at least ≥2 s visible; ≥4 s preferred.

2. **Person-box trackability**
   - Percent of active players tracked for ≥80% of the post-rally window.

3. **Behavior-only human separability**
   - Reviewers see post-rally behavior but not the terminal ball path.
   - They choose winner side or abstain.
   - Measure accuracy-on-covered, coverage, and reviewer agreement.

4. **Automatable behavior cues**
   Measure whether simple box-based features separate outcomes:
   - first player/team moving toward dead ball
   - side where ball is retrieved
   - players disengaging vs preparing to continue
   - movement asymmetry after terminal event
   - whether all players stop immediately
   - whether one team turns away / walks to serve/reset

Behavior becomes **co-primary** only if it shows real separability, not because it is conceptually attractive.

---

### Phase 1 gates

#### Gate 1A — Ball as primary module

Proceed with ball as a primary module if:

- top-10 visible-ball candidate recall is:
  - ≥85% on near/mid terminal frames, and
  - ≥75% overall including far-side cases;
- event-level terminal trajectory recoverability is ≥70%;
- human ball-only recoverability is ≥60% coverage at ≥90% accuracy-on-covered.

If human ball-only recoverability is <50% coverage, ball should not be treated as the primary path except for obvious cases like net faults and clear near-side outs.

#### Gate 1B — Behavior as co-primary module

Treat behavior as co-primary if:

- ≥60% of rallies have ≥2 s usable post-rally footage;
- behavior-only human recoverability is ≥50% coverage at ≥80% accuracy-on-covered;
- simple automatable behavior features reach AUC ≥0.70 or ≥75% accuracy at meaningful coverage.

If behavior-only coverage is <30% or post-rally footage is often truncated, behavior remains a backup abstain-filler.

#### Gate 1C — Last-hitter feasibility

Because every rule depends on last hitter, require:

- last-hitter side inference ≥85% accuracy-on-covered at ≥70% coverage, or
- ≥90% accuracy-on-covered at ≥50% coverage.

If this fails, do not ship winner automation except for cases where last hitter is irrelevant or obvious, such as clear dead-ball net faults with unambiguous side.

---

### Phase 2 — Build ball/event module

Inputs:

- full-resolution frames around audio rally end
- static distractor mask
- person-box suppression
- homography only for court geometry/masking
- multi-hypothesis graph/beam tracking

Process:

- search around audio end, not only before it:
  - terminal ball window: roughly `audio_end - 2.5 s` to `audio_end + 1.5 s`
  - post-rally context: up to `audio_end + 6 s`
- run 60 fps only in the terminal window;
- lower fps is acceptable outside it.

Outputs:

- no-cross probability
- crossed-net probability
- clear-in / clear-out / unknown
- terminal location estimate
- trajectory confidence
- quality flags: occlusion, far-side uncertainty, near-line margin, homography instability

#### Gate 2 — Ball module release threshold

I would sharpen your proposed threshold.

- For **assisted review / prefill**, ≥85% accuracy at ≥40% coverage is acceptable.
- For **auto-accept / eliminate review click**, 85% is too low.

Production auto-decision gate:

- ≥90% accuracy-on-covered at ≥35–40% coverage;
- no major stratum below 85%;
- calibration ECE ≤0.05–0.08.

---

### Phase 3 — Add audio last-hitter + behavior modules

#### Last-hitter module

Use audio-hit timing as the primary temporal cue, but not as the sole side cue.

Fusion inputs:

- audio pock/transient time
- temporal proximity to rally end
- player-box proximity to expected paddle/contact zone
- side of nearest plausible player
- ball acceleration/direction change after hit
- whether ball then moves away from that side
- occlusion/visibility quality

High confidence if:

- side posterior ≥0.85;
- top-side margin ≥0.20;
- audio timing and ball direction do not conflict.

Abstain if:

- multiple plausible pocks near terminal event;
- nearest players from both sides are plausible;
- ball direction contradicts audio/player association;
- final contact is occluded and posterior <0.80.

#### Behavior module

Use only cheap cues first:

- person boxes
- team-side motion
- dead-ball retrieval side
- post-rally stop/disengagement
- movement toward ball
- reset/serve preparation if visible

Do not start with pose. Pose is optional later if the audit proves box-level behavior is insufficient but promising.

---

### Phase 4 — Fusion and calibration

Train a conservative fusion layer over module outputs.

Inputs:

- ball terminal outcome posterior
- last-hitter side posterior
- behavior posterior
- existing score/cascade prediction
- audio end confidence
- quality flags
- line-margin flags
- post-rally truncation flag
- game type: singles/doubles
- near/far terminal zone

Fusion policy:

1. Apply hard rule filters first:
   - did not cross net → hitter loses;
   - crossed + clearly out → hitter loses;
   - crossed + clearly in + no return → other side loses;
   - near-line/far-line uncertain → abstain unless other evidence is overwhelming.

2. Use calibrated probabilistic fusion second.

3. Abstain on disagreement:
   - last-hitter confidence <0.80;
   - ball outcome uncertain;
   - ball and behavior disagree strongly;
   - calibrated winner probability <0.90 for auto-decision;
   - quality flags indicate occlusion/truncation.

Confidence tiers:

- **Tier A — auto-accept**
  - winner probability ≥0.90;
  - no hard conflict;
  - required module confidence present.
- **Tier B — prefill review**
  - probability 0.75–0.90;
  - useful suggestion, but reviewer confirms.
- **Tier C — abstain**
  - probability <0.75 or conflicting evidence.

#### Gate 3 — Fusion release threshold

Corrected target:

- minimum V1 production target: **≥90% accuracy-on-covered at ≥50% coverage**;
- strong target: **≥90% at ≥60% coverage**;
- ≥88% at ≥60% is acceptable for assisted review, but I would not call it low-error auto-accept.

---

## 3. Singles vs doubles recommendation

Do **not** scope V1 to singles only if the corpus is mostly doubles. That would optimize for the wrong distribution.

Recommendation:

- V1 should target the common fixed-camera doubles setting, but abstain aggressively on ambiguous doubles contacts.
- Report metrics separately for singles and doubles.
- Use game type as a fusion feature.
- If singles performs much better, allow a higher-coverage singles tier, but do not make singles the main product scope unless product usage is actually singles-heavy.

Camera geometry helps both, but doubles is materially harder because of occlusion, last-hitter ambiguity, and noisier post-rally behavior. It is not irrelevant.

---

## 4. Labeling flywheel strategy

Yes: the existing review loop should be the primary labeling path.

Minimum useful reviewer signal:

1. confirm / flip winner;
2. terminal event type;
3. terminal side/location bucket;
4. optional terminal-time correction;
5. optional ball click/candidate selection only on flips, abstains, or sampled audits.

For detector self-training, the most valuable low-burden signal is:

- accepted terminal time;
- selected/confirmed terminal ball candidate or final ball location when visible.

For calibration, the most valuable signal is:

- every model score at decision time;
- final reviewer-confirmed winner;
- whether reviewer flipped;
- whether case was abstained or auto-accepted.

Also sample **5–10% of high-confidence auto decisions** for human audit to avoid calibration drift and selection bias.

---

## 5. Compute budget

Cheapest viable configuration:

- one consumer GPU, e.g. RTX 3060/4060/4070 class;
- 8–12 GB VRAM;
- normal CPU decode/preprocess;
- no need for multi-GPU.

Expected per video with 30–50 rallies:

- process only windows around audio rally ends;
- 60 fps for terminal `~4 s` window;
- 10–15 fps for longer post-rally behavior;
- person boxes can run sparsely, e.g. 5–10 fps with interpolation.

Rough budget:

- optimized/cropped GPU path: **3–10 min/video**;
- heavier full-res detector on all terminal frames: **10–30 min/video**;
- CPU-only: likely **30–90 min/video**, acceptable for offline experiments but not ideal.

Do not run full-resolution 60 fps over the entire video unless profiling proves it is cheap enough. The decisive signal is concentrated near the terminal window.

---

## 6. Realistic targets

Initial V1:

- **90% accuracy-on-covered**
- **50–60% coverage**
- conservative abstain on far-side lines, occlusions, ambiguous last hitter, and truncated post-rally footage.

Stretch after flywheel labels:

- **90–92% accuracy**
- **65–75% coverage**

I would not plan around full automation. Some rallies are visually underdetermined from this camera/view/cut structure.

---

## 7. Remaining disagreements / open risks

1. **Shipping threshold:** I disagree with using 85% accuracy as a true auto-skip-review threshold. It is fine for assisted review, not for low-error automation.

2. **Behavior cue value is unresolved:** It may be highly useful, but only if the audit shows separability and enough post-rally footage. It should gate build order.

3. **Audio-hit timing should be primary for timing, not side alone:** Audio can locate the hit time well, but side assignment still needs player proximity and ball-direction confirmation.

4. **Far-side line calls remain structurally weak:** Treat far-side near-line decisions as abstain unless margins are large.

5. **Doubles ambiguity is real:** V1 should include doubles because that is the corpus, but coverage may be meaningfully lower than singles.

6. **Flywheel labels can be biased:** Review-derived labels need random audits of high-confidence cases, otherwise the model learns mostly from hard/flipped examples.

7. **Highlight cuts may cap behavior coverage:** If many clips end immediately after the rally, behavior cannot be co-primary regardless of model quality.

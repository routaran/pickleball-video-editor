# Rally-Winner Detection — Consensus Plan of Record

**Status:** Agreed design (no implementation yet).
**Date:** 2026-06-14
**Produced by:** a two-round collaboration between **Claude (Opus 4.8)** and **GPT-5.5 (high reasoning)**, driven by the human engineer. Raw transcripts: `docs/auto-editor-plan/collab/01–04`. Prior solo analysis + diagnosis: [`winner-ball-tracking-plan.md`](winner-ball-tracking-plan.md).

> **Why this exists.** The audio rally-*boundary* model works (<10% error). The rally-*winner* model (ResNet-18 over homography-warped 256×128 court clips) does **not**: it collapses to a constant classifier on unseen courts (val = base rate 54.6%). Root cause is a representation/generalization wall — the decisive cue (a tiny, late, physical ball event) is averaged away by a whole-frame classifier and does not transfer across ~40 courts. More resolution does not fix it (proven). This plan replaces that approach.

---

## 1. Agreed approach (one paragraph)

Build a **selective hybrid winner-resolution system**: full-resolution, image-space ball/event recovery; audio-assisted last-hitter inference; lightweight player/post-rally **behavior** cues; and a **conservative fusion layer** that either emits a calibrated winner or **abstains** to the existing 1-click human review. The system does not try to referee every rally — it confidently resolves easy/medium terminal events and routes ambiguous ones to review. Every result is reported as **two numbers: accuracy-on-covered and coverage.** Geometry comes from the 4 court corners we already collect (homography); the deterministic `ScoreState` engine still composes per-rally winners into the score. Abstaining is a first-class, acceptable outcome because human review already ships — the realistic V1 win is **eliminating ~half the review clicks at low error**, not full automation.

### Both models converged on this; the key shifts from the solo plan
- **Not ball-only.** Ball tracking is the primary high-precision path, but **post-rally behavior, audio hit-timing, and player motion are independent evidence sources** fused with abstain. (GPT-5.5's biggest contribution.)
- **The decisive event is often *after* the rally,** not in the last 300 ms of ball flight: who retrieves the dead ball, who resets to serve, who stays stationary after failing to return. Search a window that includes **up to ~6 s after** the audio rally-end.
- **Coarse > referee-grade.** Decide from "didn't cross net / crossed-and-clearly-out / crossed-clearly-in-and-no-return," not exact bounce reconstruction. Require generous line margins; abstain inside them.
- **The human-review loop is the labeling engine** (a flywheel), not just a fallback.
- **Candidate recall is the gating early metric;** a small hand-audited terminal-event set is required because rally-level labels are too coarse to debug tracking.

---

## 2. Phased plan with go/no-go gates

### Phase 0 — Instrument the review UI now (creates the labeling flywheel)
Do this first/alongside the audit. Minimum additions to the existing confirm/flip review:
1. Existing: confirm or flip predicted winner.
2. Optional **terminal-event type** tag: `net/did-not-cross` · `out` · `in/no-return` · `unknown`.
3. Optional **terminal side/location** tag: `near` · `far` · `left/right/deep out` · `unknown`.
4. On flips / low-confidence only: optional accept-or-adjust terminal time, or one click on the final visible ball.
Also **log every module score at decision time** + the reviewer's final winner + flip/abstain/auto-accept status (for calibration), and **randomly audit 5–10% of high-confidence auto-decisions** to prevent the flywheel from learning only from hard/flipped cases.

### Phase 1 — Feasibility audit (the deciding experiment, cheap)
**150–200 stratified rallies** (≥100 floor), stratified by: near/far terminal; net/out/in-no-return/unknown; singles/doubles; good/poor lighting+compression; clean/occluded terminal; post-rally ≥6 s vs truncated; existing cascade confidence high/med/low. Two reviewers + adjudication establish: true winner, terminal event type, last-hitter side, approximate terminal time, decisive-evidence-visible?, post-rally available duration.

**Ball-path metrics:** (1) top-K candidate recall (K=10) of the true ball in visible terminal frames, reported near/mid/far, frame- and event-level; (2) trajectory recoverability of last-hit direction / crossed-net / terminal zone / clear in-out-with-margin; (3) **human ball-only recoverability** (human sees only terminal ball evidence, may abstain → accuracy-on-covered + coverage); (4) line-margin safety (near >10–15 cm, far >20–30 cm; inside margin → abstain).

**Post-rally behavior metrics (same rallies):** (1) availability — % with ≥2 s / ≥4 s / ≥6 s before cut; (2) person-box trackability over the window; (3) **behavior-only human separability** (reviewers see only post-rally behavior → accuracy-on-covered, coverage, agreement); (4) whether simple box features separate outcomes (first mover to dead ball, retrieval side, disengage vs prepare, movement asymmetry, who turns to serve). **Behavior becomes co-primary only if the data shows separability — not because it's attractive.**

#### Phase 1 gates
- **Gate 1A — ball as primary:** top-10 visible-ball recall **≥85% near/mid, ≥75% overall**; event-level trajectory recoverability **≥70%**; human ball-only **≥60% coverage @ ≥90% accuracy**. If human ball-only coverage **<50%**, ball is primary only for obvious cases (net faults, clear near-side outs).
- **Gate 1B — behavior as co-primary:** **≥60%** of rallies have ≥2 s usable post-rally footage; behavior-only human **≥50% coverage @ ≥80% accuracy**; simple features **AUC ≥0.70** (or ≥75% acc at meaningful coverage). If behavior coverage **<30%** or footage often truncated → behavior is a backup abstain-filler only.
- **Gate 1C — last-hitter feasibility (linchpin):** last-hitter side **≥85% acc @ ≥70% coverage** OR **≥90% @ ≥50%**. If it fails, don't ship winner automation except where last-hitter is irrelevant/obvious (clear dead-ball net faults with unambiguous side).

### Phase 2 — Ball / event module
Inputs: full-res frames around audio end; per-video static distractor mask; person-box suppression; homography for geometry/masking only; **multi-hypothesis graph/beam tracking** (second-order motion, change-point modes for hit/bounce/net, gaps 1–8 frames, keep top-K). Windows: terminal `audio_end − 2.5 s … audio_end + 1.5 s` at **60 fps**; post-rally context to `audio_end + 6 s` at lower fps. Outputs: no-cross / crossed-net / clear-in / clear-out / unknown probabilities, terminal-location estimate, trajectory confidence, quality flags (occlusion, far-side, near-line, homography instability).
- **Gate 2 (sharpened):** **assisted prefill** OK at ≥85% acc @ ≥40% coverage; **auto-accept (skip review)** requires **≥90% acc @ ≥35–40% coverage, no stratum <85%, calibration ECE ≤0.05–0.08.** (This corrected my original "85%@40% ship" threshold — 85% is fine to *suggest*, not to *auto-skip* review.)

### Phase 3 — Audio last-hitter + behavior modules
**Last-hitter:** audio pock timing is the **primary temporal** cue, **not** the side cue alone. Fuse: pock time + proximity to rally end + player-box proximity to contact zone + nearest-player side + post-hit ball direction/acceleration + occlusion quality. High-confidence if side posterior ≥0.85, margin ≥0.20, audio/ball don't conflict; abstain on multiple plausible pocks, both-side-plausible players, audio/ball contradiction, or occluded contact with posterior <0.80.
**Behavior:** cheap box-level cues first (team-side motion, retrieval side, stop/disengage, movement to ball, reset-to-serve). **No pose initially** — only if the audit proves box-level is insufficient-but-promising.

### Phase 4 — Fusion + calibration
Hard rule filters first (didn't-cross → hitter loses; crossed+clear-out → hitter loses; crossed+clear-in+no-return → other side loses; uncertain margins → abstain). Then calibrated probabilistic fusion over: ball outcome posterior, last-hitter posterior, behavior posterior, existing cascade prediction, audio-end confidence, quality/line-margin/truncation flags, game type, near/far zone. **Abstain on disagreement** (last-hitter <0.80; ball uncertain; ball vs behavior strong conflict; fused winner prob <0.90 for auto; occlusion/truncation flags).
**Confidence tiers:** **A auto-accept** (prob ≥0.90, no hard conflict) · **B prefill review** (0.75–0.90) · **C abstain** (<0.75 or conflict).
- **Gate 3:** V1 min **≥90% acc @ ≥50% coverage**; strong **≥90% @ ≥60%**; ≥88%@60% acceptable for *assisted* review but not low-error auto-accept.

---

## 3. Singles vs doubles
Include **doubles** in V1 (it's the corpus) but abstain aggressively on ambiguous doubles contacts; report singles/doubles **separately**; use game-type as a fusion feature. Allow a higher-coverage singles tier if it clearly outperforms, but don't scope the product to singles. Doubles is materially harder (occlusion, last-hitter ambiguity, noisier post-rally) — not irrelevant.

## 4. Labeling flywheel (primary labeling path)
Routine review *is* the annotation pipeline. Minimum reviewer signal: confirm/flip + terminal-event type + terminal side bucket + optional terminal-time correction + optional ball click (on flips/abstains/sampled audits). Most valuable for **detector self-training:** accepted terminal time + confirmed final ball location. Most valuable for **calibration:** all module scores at decision time + confirmed winner + flip/abstain/auto status. Mandatory **5–10% random audit of high-confidence auto-decisions** to avoid selection-biased labels.

## 5. Compute budget
Process **only windows around audio rally-ends**, not the whole video. 60 fps in the terminal ~4 s; 10–15 fps for the post-rally behavior window; person boxes sparse (5–10 fps + interpolation). One consumer GPU (8–12 GB). Rough: optimized cropped GPU path **3–10 min/video**; heavier full-res detector on all terminal frames **10–30 min**; CPU-only **30–90 min** (offline experiments only). Do **not** run full-res 60 fps over entire videos.

## 6. Realistic targets
- **V1:** ~**90% accuracy-on-covered at 50–60% coverage**, abstaining on far-side line calls, occlusions, ambiguous last-hitter, truncated post-rally.
- **Stretch (after flywheel labels):** **90–92% accuracy at 65–75% coverage.**
- **Do not plan around full automation** — some rallies are visually underdetermined from this single camera + cut structure.

## 7. Remaining disagreements / open risks (not smoothed over)
1. **Auto-skip threshold:** 85% accuracy is fine to *prefill* a suggestion, **not** to auto-skip review. Auto-accept needs ≥90% + good calibration. (Resolved in favor of GPT-5.5's stricter line.)
2. **Behavior-cue value is unresolved** — genuinely pending the Phase-1 audit; it gates build order by design.
3. **Audio gives timing, not side** — side still needs player-proximity + ball-direction confirmation.
4. **Far-side near-line calls are structurally weak** (~4 px ball, 58 px/m) → abstain unless margins are large.
5. **Doubles ambiguity is real** → lower coverage than singles expected.
6. **Flywheel labels can be biased** toward hard/flipped cases → mandatory random audits.
7. **Highlight cuts may cap behavior coverage** — if clips end immediately after the rally, behavior can't be co-primary regardless of model quality.

---

## 8. Immediate next actions (when implementation is greenlit)
1. **Phase 0:** add the optional terminal-event / side tags + decision-score logging to the review UI.
2. **Phase 1:** run the 150–200-rally stratified audit; compute the ball-path + behavior + last-hitter metrics; evaluate Gates 1A/1B/1C. **This audit decides whether — and in what order — to build the modules.** It is cheap and must precede any heavy build.
3. Only after the audit clears the gates, build Phase 2 → 3 → 4, validating each against the gate numbers on **video-wise** folds against the existing 1,847 labeled rallies.

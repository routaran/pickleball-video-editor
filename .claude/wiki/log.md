---
type: log
---
# Pickleball Video Editor Wiki Log

Append-only record of every wiki operation — `init`, `ingest`, `update`, `lint` — performed against this project's `./.claude/wiki/`. Readers should scan from the top to see the most recent activity.

**Entry format:** `## [YYYY-MM-DD] <operation> | <subject>` followed by a short bulleted body noting what changed, which source files drove the change, and which pages were touched.

**Rules:**
- Newest entries go at the TOP (reverse-chronological).
- Never edit or delete past entries — corrections go in a new entry that supersedes the old one.
- Operations vocabulary: `init`, `ingest`, `update`, `lint`, `split`, `delete`.

---

## [2026-06-21] ingest | staleness-driven (tech-stack source edit)

- Pages checked: 11
- Pages stale (genuine): 1 — `architecture/tech-stack.md`. Source `docs/TECH_STACK.md` changed @ `bb14454` (2026-06-21 21:29, "docs(tech-stack): add offline motion-fusion detector stack"), strictly newer than the page's prior same-day compile (which was driven by `README.md` @ `a336a82`). Only source change since the previous 2026-06-21 ingest.
- Recompiled (DAG: single architecture page; no domain/gotcha pages stale):
  - `architecture/tech-stack.md` — folded in `TECH_STACK.md` §2.3's offline motion detector. Core Stack row now notes the AGPL ultralytics dep + own `.venv-motion` (`ml/requirements-motion.txt`); expanded the motion-fusion note with the **isolation rationale** (ultralytics hard-deps the full Qt/GL `opencv-python`, which would interpose on the GUI's mpv, so the GUI venv stays `opencv-python-headless`) and the **out-of-process flow** (`extract_motion_features` via `extract_runner` → `ml/cache/motion/*.npz`; cheap `predict_fused`/`evaluate_fused` reads `.npz` and needs only `ml/requirements.txt`). 124 → 131 lines (≤ hard_max 200). Cross-refs verified resolving. `last_compiled` stays 2026-06-21 (same-day recompile).
- Skipped (up-to-date): 10 — `domains/{core,ui,video,output,ml,tests}`, `architecture/{auto-edit-pipeline,session-lifecycle}`, `gotchas/{pickleball-scoring,auto-edit-pitfalls}`. No domain sources changed since the prior ingest; `README.md` (`a336a82`) was already absorbed by that ingest.
- Note: wiki content pages are gitignored (disk-only); only `log.md` is tracked. No commit performed (wiki-build flow does not commit); `tech-stack.md` + `log.md` left modified on disk. `index.md`/`source-map.md` unchanged (dates already 2026-06-21; `tech-stack` `compiled_via` already `ingest`).
- Status: complete

## [2026-06-21] ingest | staleness-driven (1 stale architecture page)

- Pages checked: 11
- Pages stale (git-log detected, genuine): 1 — `architecture/tech-stack.md`. Source `README.md` changed @ `a336a82` (2026-06-21, "PICKLEBALL_MOTION_VENV override / installed-binary motion fusion"), strictly newer than the page's 2026-06-14 `last_compiled`. This is the only source change since the prior 2026-06-21 ingest.
- Recompiled (DAG: single architecture page; no domain/gotcha pages stale):
  - `architecture/tech-stack.md` — incorporated the two README sections `a336a82` added: (1) "Motion fusion from the installed binary" → new Core Stack row "Motion fusion (optional): YOLOv8n + ByteTrack (ultralytics), out-of-process in a separate `.venv-motion`" + a deployment note (set `PICKLEBALL_MOTION_VENV` to the venv dir or its `bin/python` for the frozen binary; `make run` finds it automatically; audio-only fallback + one-time notice when absent/no GPU); (2) "Rebuild & reinstall to ~/.local/bin" → added `make install-ml` (rally-trainer binary) to Build & Test and the same-`PREFIX` reinstall guidance. `last_compiled` 2026-06-14 → 2026-06-21. 124 lines (≤ hard_max 200; at target 125). Cross-refs verified resolving.
- Skipped (up-to-date): 10 — `domains/{core,ui,video,output,ml,tests}`, `architecture/{auto-edit-pipeline,session-lifecycle}`, `gotchas/{pickleball-scoring,auto-edit-pitfalls}`.
- Same-day-boundary false positives ruled out: a `--since` sweep using bare `last_compiled` dates initially flagged `output` / `auto-edit-pipeline` / `auto-edit-pitfalls`, but every flagged commit is dated exactly on their 2026-06-14 compile day (OUTPUT_* aligns 1a1700c/13e337d/14849e8/03d39be; auto-editor-plan docs 19387d0); a strict `--since=2026-06-15` check returned empty for all three, and the prior 2026-06-21 ingest already cleared them. Not recompiled. `ml`/`tests`/`ui`/`core` were recompiled by the prior 2026-06-21 ingest for the exact same commits and have no newer source changes.
- Note: wiki content pages are gitignored (disk-only); only `log.md` is tracked. No commit performed (wiki-build flow does not commit); `tech-stack.md` + `log.md` left modified on disk. `index.md`/`source-map.md` dates already 2026-06-21 (unchanged); `tech-stack` `compiled_via` already `ingest`.
- Status: complete

## [2026-06-21] source-update | align (scope: all docs)

- Trigger: new commit `a336a82` ("motion: PICKLEBALL_MOTION_VENV override so installed binary finds .venv-motion") — the only code commit since the prior 2026-06-21 align (fd0a37c/02a26d1/fb6b801). Touches `ml/motion/extract_runner.py`, `README.md`, `tests/test_motion_extract_runner.py`; adds NO new files.
- Drift items: 4 (factual: 0, structural: 0, editorial: 3, candidate-new: 1) — all surfaced; none auto-applicable.
- Applied: 0  Skipped: 4  Edited inline: 0
- Source docs touched: [] (no edits, no per-doc commits)
- Key assessment — `a336a82` / PICKLEBALL_MOTION_VENV / installed-binary fusion:
  - `README.md` is CLEAN: `a336a82` itself added the "Motion fusion from the installed binary" section (set `PICKLEBALL_MOTION_VENV` to the `.venv-motion` dir or its `bin/python`; out-of-process detector; audio-only fallback + one-time notice) plus the earlier "Rebuild & reinstall to `~/.local/bin`" build note. The doc's own commit reset its anchor, so these are not drift. README is the canonical home for this install/deployment concern; the env var is documented there, so no other doc needs a candidate-new entry for it.
  - `docs/auto-editor-plan/current-state.md` (anchor fd0a37c): motion section (L124-128, "runs in a separate `.venv-motion`") remains factually accurate; the env-var override is an installed-binary deployment detail covered by README → not-drift.
  - `docs/TECH_STACK.md`: still no motion/venv mention — the offline motion dependency stack (ultralytics/YOLOv8n in `.venv-motion`, `ml/requirements-motion.txt`) remains uncovered. RECURRING candidate-new (also surfaced 2026-06-14 + 2026-06-21, deliberately deferred). Not written (candidate-new never auto-applies; README covers the env var; consistent with prior runs).
  - tests docs (`TESTING.md`/`TEST_SUITE_SUMMARY.md`): CLEAN — `test_motion_extract_runner.py` first landed in da26a74 (already counted in the 2026-06-21 align); test-file count 63 unchanged.
- Re-surfaced editorial (from prior align, still deferred — author's call): stale "14 games" planning figure (current-state.md/training-data.md/architecture.md/decisions.md/README.md); Stage-1-now-fuses-motion narrative vs audio-only framing (architecture.md/README.md); decisions.md "NOT building player tracking/pose" partially contradicted by ByteTrack identity tracking.
- Followed by: ingest WITHHELD (no source edits to ingest; wiki-build invocation also withheld per orchestrator instruction — the separate `/wiki-build ingest` step handles staleness).
- Status: complete (no source-doc edits required; a336a82 already self-documents via README).

## [2026-06-21] ingest | staleness-driven (4 stale domain pages)

- Pages checked: 11
- Pages stale (git-log detected): 4 — `domains/ml`, `domains/tests`, `domains/ui`, `domains/core`. Picked up the 2026-06-21 align (current-state.md, TESTING.md, TEST_SUITE_SUMMARY.md) PLUS three 2026-06-16 source-updates that were never ingested (REVIEW_MODE_USAGE.md @231fc32, REVIEW_MODE_IMPLEMENTATION.md @ee80572, DETAILED_DESIGN.md @97a61aa).
- Recompiled (DAG: all four are domains; no architecture/gotcha pages stale):
  - `domains/ml.md` — added the `ml/motion/` offline layer (YOLOv8n+ByteTrack feature extraction in `.venv-motion` → `ml/cache/motion/*.npz`; `predict_fused` court-dilation fusion augments Stage-1 audio boundaries, `auto_edit.py` uses fusion when a motion cache exists else falls back to tuned audio-only). Updated Purpose (Stage 1) + current-state.md Sources line. Source: `current-state.md` @fd0a37c. 101 lines.
  - `domains/tests.md` — test-file count 49 → 63 (Purpose + Sources). Sources: `TESTING.md` @02a26d1/da7918b, `TEST_SUITE_SUMMARY.md` @fb6b801/16a1bf9. 73 lines.
  - `domains/ui.md` — review-mode rewrite: `ScoreEditWidget`+"Flip Winner" replaced by `WinnerControlWidget` (winner_selected "server"/"receiver") + `StateAnchorWidget` (serving-team toggle + score; ALWAYS cascades, cascade checkbox gone); `TimingControlWidget` gained a configurable step combo (0.1/0.25/0.5/1.0s) + direct start/end/duration entry (`timing_set`) alongside nudge (`timing_adjusted`); full `ReviewModeWidget` signal set (timing_set/winner_set/state_anchor_set, delete/insert, generate/export_ffmpeg, game_completed_toggled); runtime FPS via `set_rallies`; tall/wide frozen splitter + mpv-never-in-QScrollArea contract; Kdenlive GENERATE + FFmpeg EXPORT MP4 + Mark Game Completed. Updated Patterns wiring, ml Coordinates, gotcha ref, Sources. Sources: `REVIEW_MODE_IMPLEMENTATION.md` @ee80572, `REVIEW_MODE_USAGE.md` @231fc32. 105 lines.
  - `domains/core.md` — added `ScoreState.set_serving_team(int)` (review-mode state anchor) and `RallyManager.set_rally_timing(index, start, end) -> Rally` (absolute raw-time set vs delta-based `update_rally_timing`). Source: `DETAILED_DESIGN.md` @97a61aa (methods landed in 5113ab7). 91 lines.
- Skipped (up-to-date by git log): 7 — `domains/video`, `domains/output`, `architecture/{tech-stack,auto-edit-pipeline,session-lifecycle}`, `gotchas/{pickleball-scoring,auto-edit-pitfalls}`.
- Out of scope: commit 0bdd345 (2026-06-14) added many new `docs/auto-editor-plan/` files (WINNER_DETECTION_*, audit/*, collab/*, winner-ball-tracking-plan.md, winner-detection-consensus-plan.md) but none are in any page's `source_paths` per source-map, so they triggered no recompilation (candidate-new for `wiki-source-update`, not ingest).
- `compiled_via` for `domains/ml` set `update` → `ingest`; `index.md` / `source-map.md` dates bumped to 2026-06-21.
- All four pages ≤ hard_max 200 (max 105). Cross-references verified resolving.
- Note: wiki content pages are gitignored (disk-only); only `log.md` is tracked. No commit performed (wiki-build flow does not commit); `log.md` left modified.
- Status: complete

## [2026-06-21] source-update | align (scope: all docs)

- Drift items: 8 (factual: 0, structural: 3, editorial: 3, candidate-new: 2)
- Applied: 3  Skipped: 5  Edited inline: 0  (autonomous run: applied factual/structural only; editorial + candidate-new surfaced for human review, not written)
- Source docs touched (committed, one commit each):
  - `docs/auto-editor-plan/current-state.md` (anchor 19387d0) — structural: added `ml/motion/` (offline YOLOv8n+ByteTrack feature extraction + `predict_fused` court-dilation fusion, wired into `auto_edit.py` Stage 1) to the ml-module inventory. Commit fd0a37c. Prompted by 57d2754, 2909754, da26a74, 100f86c, fad7fae.
  - `docs/TESTING.md` (anchor da7918b) — structural: test-file count 50 → 63. Commit 02a26d1. Prompted by cf4a7e3, 57d2754, 74ef636, 2909754, da26a74, 4a50349.
  - `docs/TEST_SUITE_SUMMARY.md` (anchor 16a1bf9) — structural: overall-suite test-file count 50 → 63 (~116 core-suite figure unchanged). Commit fb6b801. Same prompting commits.
- Surfaced, NOT edited (need human decision):
  - editorial — "14 games" planning figure is stale in current-state.md, training-data.md, architecture.md, README.md, decisions.md; TRAINING_GUIDE.md already says ~20 games and the pinned split `ml/splits/audio_clean_2026_06_17/` holds 72 `.training.json`. Correct value is ambiguous and the figure lives inside design rationale, so left for the author.
  - editorial — Stage 1 now fuses motion (predict_fused) when a cache exists (2909754, da26a74); architecture.md data-flow diagram and README.md "two-stage pipeline" framing describe audio-only Stage 1. Narrative extension, not a single-line contradiction.
  - editorial — decisions.md "What we're NOT building: player tracking / pose" is partially contradicted by the ByteTrack identity tracking in the motion-perception layer (100f86c, fad7fae); design evolved — author's call.
  - candidate-new — new offline motion-detection dependency stack (ultralytics/YOLOv8n in a separate `.venv-motion`, `ml/requirements-motion.txt`, 57d2754) is uncovered by tech-stack docs (README.md / docs/TECH_STACK.md).
  - candidate-new — src/main.py one-time "fusion unavailable → audio-only" session notice + auto_edit progress motion-extraction phase (da26a74) is uncovered by ui docs (low significance).
- Followed by: ingest DEFERRED — wiki-build invocation withheld per orchestrator instruction; run `/wiki-build ingest` separately to refresh `domains/ml` (from current-state.md) and `domains/tests` (from TESTING.md + TEST_SUITE_SUMMARY.md).
- Status: complete

## [2026-06-14] ingest | staleness-driven (1 stale gotcha page)

- Pages checked: 11
- Pages stale: 1 — `gotchas/auto-edit-pitfalls`
- Recompiled: `gotchas/auto-edit-pitfalls.md` — triggered because its source `docs/auto-editor-plan/review-fixes.md` was newly git-tracked in `19387d0` (prior compile predated tracking). Re-merged `review-fixes.md` + memory sections "Key decisions" / "Fixes applied 2026-04-19 (post-review)"; content already accurate and complete (all six issues A–F + test-collection + 2 key-decision gotchas), so only `last_compiled` advanced to 2026-06-14. Page = 83 lines (gotcha target 60–120, hard_max 200). Cross-references verified.
- Skipped (up-to-date): 10 — 6 domains, 3 architecture, `gotchas/pickleball-scoring`. (`18d902b` touched only `.gitignore`, so no source content changed for the 2026-05-26 pages.)
- source-map: `auto-edit-pitfalls` compiled_via `init` → `ingest`
- Status: complete

## [2026-06-14] ingest | staleness-driven (4 stale domain pages)

- Pages checked: 11
- Pages stale (git-log detected): 4 — `domains/core`, `domains/ui`, `domains/output`, `domains/tests`. NOTE: staleness detection worked normally this time because the source docs were just tracked (extended `.gitignore` allowlist in the source-update above) — previously these pages' sources were gitignored, so prior runs needed FORCED updates.
- Recompiled (targeted updates reflecting the source-update edits):
  - `domains/tests.md` — test-file count 41 → 49 (`tests/test_winner_estimator.py` added; 2b6344f).
  - `domains/core.md` — RallyManager score cascade is now implemented (`cascade_scores_from -> list[int]`, `delete_rally -> tuple[Rally, list[int]]`, `insert_rally -> list[int]`); replaced the stale "cascade is a TODO stub" claim (db8178b).
  - `domains/ui.md` — toast width now dynamic (one-third of parent, clamped 320–480px); `GameConfig` gained `session_state`/`court_corners`/`auto_mode`; added `J`/`E` + `Shift+J`/`Shift+E` touch-counter shortcuts (cfdc578, 6faa718, 63a752a).
  - `domains/output.md` — NO content change: the page already stated `{basename}.kdenlive` (it was ahead of the source docs' stale `_rallies` suffix); only `last_compiled` bumped.
- Skipped (up-to-date by git log): 7 — `domains/video`, `domains/ml`, `architecture/{tech-stack,auto-edit-pipeline,session-lifecycle}`, `gotchas/{pickleball-scoring,auto-edit-pitfalls}`.
- `compiled_via` set to `ingest` for the 4 pages; `index.md`/`source-map.md` dates bumped to 2026-06-14.
- Note: wiki content pages are gitignored (disk-only); only `log.md` is tracked, so the recompiled pages are written to disk but not committed.
- Status: complete

---

## [2026-06-14] source-update | align (all docs)

- Drift items: 17 (factual: 12, structural: 4, editorial: 0, candidate-new: 1)
- Applied: 16  Skipped: 1  Edited inline: 0
- Scope caveat: `wiki.config.md` sets no `code_scope`, so per-domain code scope was INFERRED from the dir layout (core→`src/core`, ui→`src/ui`, video→`src/video`, output→`src/output`, ml→`ml`, tests→`tests`; cross-cutting arch/gotcha scopes unioned).
- Trigger commits: `db8178b` (RallyManager cascade/delete/insert return types), `cfdc578` (toast width now dynamic), `6faa718`+`9e4d6bf` (GameConfig gained court_corners/auto_mode/session_state), `63a752a` (J/E/Shift+J/Shift+E touch-counter shortcuts), `f27d67c` (export basename via generate_export_basename — dropped the `_rallies` suffix), `2b6344f` (added tests/test_winner_estimator.py → 48→49 test files).
- Source docs touched (committed, one commit each): `docs/DETAILED_DESIGN.md` (37da661), `docs/TOAST_IMPLEMENTATION.md` (8387fdd), `docs/SETUP_DIALOG_GUIDE.md` (6a9ad6b), `docs/UI_SPEC.md` (90256ca), `docs/OUTPUT_MODULE_COMPLETE.md` (1a1700c), `docs/OUTPUT_GENERATION_USAGE.md` (13e337d), `docs/OUTPUT_GENERATION_INTEGRATION.md` (14849e8), `docs/OUTPUT_QUICK_REFERENCE.md` (03d39be), `docs/TESTING.md` (3a0de01), `docs/TEST_SUITE_SUMMARY.md` (f6149dd).
- Infra: extended `.gitignore` wiki-source allowlist so these 10 docs are now tracked (commit 18d902b) — they were gitignored despite being `wiki.config.md` source_paths, which had left them invisible to git-log staleness detection. NOTE: the other ~12 clean source docs under `docs/` (SCORE_STATE_EXAMPLES, SESSION_MANAGER_*, REVIEW_MODE_*, DIALOGS_*, STATUS_OVERLAY, TYPOGRAPHY, SYSTEM_DIALOGS, PLAYBACK_CONTROLS, OUTPUT_GENERATION_*, SESSION_INTEGRATION_USAGE, PHASE_7.2) remain gitignored — extend the allowlist when they next need tracking.
- Surfaced, not applied (per user choice): `docs/auto-editor-plan/current-state.md` candidate-new DRAFT for the new `ml/winner_tracking/` package (commit 2b6344f) — skipped this run.
- False positives avoided: all decord/opencv doc mentions verified CORRECT (decord still declared in `ml/requirements.txt` and used by `ml/tools/frame_picker_dialog.py`); README.md/TECH_STACK.md clean (0 in-scope commits); the `ml/winner_tracking/` audit CONFIRMS rather than contradicts the "not building ball tracking" decisions in decisions.md/architecture.md.
- Followed by: ingest of `domains/core`, `domains/ui`, `domains/output`, `domains/tests` (now git-visible since the docs are tracked).
- Status: source edits complete; wiki ingest follows.

---

## [2026-06-14] update | domains/ml.md (forced)

- Forced recompile of a git-blind page (its sources are gitignored, so the staleness ingest above could not detect them). Source `docs/auto-editor-plan/implementation.md` changed (decord→ffmpeg) in the 2026-06-14 source-update.
- Changes: the frame-extractor bullet now describes the system `ffmpeg` CLI (out-of-process), noting decord/torchvision are no longer used (decord remains a declared-but-unused dep). `last_compiled` → 2026-06-14; 100 lines (140/200).
- Status: complete

---

## [2026-06-14] update | architecture/auto-edit-pipeline.md (forced)

- Forced recompile of a git-blind page. Sources `docs/auto-editor-plan/architecture.md` + `docs/auto-editor-plan/implementation.md` changed (decord→ffmpeg).
- Changes: Stage 2 now notes frames are extracted via the system FFmpeg CLI (out-of-process). The 0.75 confidence-flag wording is left unchanged — the flag-all behavior was deliberately not written into the source docs, and the wiki mirrors sources. `last_compiled` → 2026-06-14; 61 lines (125/200).
- Status: complete

---

## [2026-06-14] ingest | staleness-driven (all pages)

- Pages checked: 11
- Pages stale (git-log detected): 1
- Recompiled: `architecture/tech-stack.md` — README.md + docs/TECH_STACK.md changed (decord → system FFmpeg CLI for frame extraction; commits 9368573, ebc0428, 6e86d27). Updated Overview, Core Stack (split the ML row; decord noted as declared-but-unused), and Layers; `last_compiled` → 2026-06-14; 110 lines (budget 125/200).
- Skipped (up-to-date by git log): 10
- CAVEAT — git-blind pages: `domains/ml.md` and `architecture/auto-edit-pipeline.md` have on-disk edits in their GITIGNORED sources (`docs/auto-editor-plan/implementation.md`, `docs/auto-editor-plan/architecture.md`, from the 2026-06-14 source-update). `git log` cannot see gitignored files, so staleness detection missed them. Run `wiki-build update domains/ml.md` and `wiki-build update architecture/auto-edit-pipeline.md` (forced) to refresh.
- Note: wiki content pages are gitignored (disk-only); only `log.md` is tracked, so the recompiled `tech-stack.md` is written to disk but not committed.
- Status: complete (forced updates pending for 2 git-blind pages)

---

## [2026-06-14] source-update | align (all docs)

- Drift items: 8 (factual: 4, structural: 0, editorial: 3, candidate-new: 1)
- Applied: 4  Skipped: 4  Edited inline: 0
- Trigger: the decord→ffmpeg frame-extraction swap (327318a) — the in-process decord/torchvision decoders were replaced with the system ffmpeg CLI, so every "decord is used for frame extraction" claim went stale.
- Source docs touched: `README.md`, `docs/TECH_STACK.md`, `docs/auto-editor-plan/implementation.md`, `docs/auto-editor-plan/architecture.md`
- Committed: `README.md` (ebc0428), `docs/TECH_STACK.md` (6e86d27). `implementation.md` + `architecture.md` are gitignored, so they were edited on disk only (no commit).
- Surfaced, not applied (per edit discipline): decord is still declared-but-UNUSED in `ml/requirements.txt:6` and `configure:281` (a code cleanup, outside doc scope); winner flag-all vs low-confidence in `decisions.md`/`architecture.md`/`implementation.md` (decision/plan rationale, left untouched); the decord dependency-mirror doc lines (`TECH_STACK.md:79`, `implementation.md:22/35/41`, `TRAINING_GUIDE.md:27`) remain accurate to the manifest, so left as-is.
- Ingest needed for: `architecture/tech-stack` (README.md + TECH_STACK.md), `domains/ml` + `architecture/auto-edit-pipeline` (implementation.md, architecture.md). CAVEAT: ingest staleness uses `git log`, which will NOT detect the gitignored `implementation.md`/`architecture.md` edits — use `wiki-build update <page>` (forced) for those two pages.
- Status: source edits complete; wiki ingest pending (forced/manual)

---

## [2026-06-13] source-update | align (all docs)

- Drift items: 40 (factual: 13, structural: 17, editorial: 6, candidate-new: 4)
- Applied: 28 — 24 factual/structural + 4 candidate-new DRAFTs (DRAFT-tagged)
- Skipped: 6 factual/structural in gitignored docs the user chose to skip (`docs/TRAINING_GUIDE.md`, `docs/ffmpeg_integration_plan.md`, `docs/auto-editor-plan/training-data.md`, `docs/auto-editor-plan/decisions.md`)
- Surfaced only (no edit, editorial): `auto-editor-plan/decisions.md`, `TRAINING_GUIDE.md`, `auto-editor-plan/review-fixes.md`, `OUTPUT_MODULE_COMPLETE.md`, `OUTPUT_GENERATION_INTEGRATION.md`, `ffmpeg_integration_plan.md`
- Source docs touched: `README.md`, `docs/UI_SPEC.md`, `docs/REVIEW_MODE_IMPLEMENTATION.md`, `docs/REVIEW_MODE_USAGE.md`, `docs/STATUS_OVERLAY_USAGE.md`, `docs/TOAST_IMPLEMENTATION.md`, `docs/DIALOGS_IMPLEMENTATION.md`, `docs/DETAILED_DESIGN.md`, `docs/SCORE_STATE_EXAMPLES.md`, `docs/OUTPUT_GENERATION_USAGE.md`, `docs/SESSION_INTEGRATION_USAGE.md`, `docs/TESTING.md`, `docs/TEST_SUITE_SUMMARY.md`
- Committed: `README.md` only (9368573). `docs/` + `.claude/` are gitignored, so the other 12 docs were edited on disk only (user choice: "commit README only").
- Ingest needed for: `domains/ui`, `domains/core`, `domains/output`, `domains/tests`, `architecture/tech-stack`, `architecture/session-lifecycle`, `gotchas/pickleball-scoring`. CAVEAT: `ingest` uses `git log` for staleness, which will NOT detect the gitignored `docs/` edits — use `wiki-build update <page>` (forced) to recompile the docs/-derived pages.
- Status: source edits complete; wiki ingest pending (forced/manual)

---

## [2026-06-10] ingest | stale pages

- Pages checked: 11
- Pages stale: 2
- Recompiled: [`domains/video.md`, `architecture/tech-stack.md`]
- Skipped (up-to-date): 9
- Sources triggering staleness: `docs/TESTING_PLAYER.md` (commit `5d5b105`), `docs/TECH_STACK.md` (commit `b0c35e9`)
- Status: complete

---

## [2026-05-31] lint | full wiki

- Checks run: 6
- Checks passed: 6
- Failures: 0
- Details: none — sources resolve (check 1), index ↔ disk match 11/11 (check 2), all internal links resolve (check 3), all pages ≤ hard_max 200 (check 4; largest video.md 127), cross-ref rules satisfied (check 5: every domain→gotcha, every gotcha→domain, index lists every page), no orphans (check 6).
- Status: pass

---

## [2026-05-31] ingest | partial (driven by source-update)

- Trigger: the `wiki-source-update align` below edited 4 source docs. Because `docs/` is `.gitignore`d, git-log staleness cannot see working-tree edits, so the 2 affected pages were recompiled directly (targeted, equivalent to `ingest --page`).
- Pages checked: 11. Stale (by changed sources): 2 — `domains/ml.md`, `domains/tests.md`.
- Recompiled:
  - `domains/ml.md` — checkpoint-config caveat flipped to RESOLVED (config now embedded + mismatch warning, `d9ba004`); new "data/eval tooling layer" Rules bullet (`examples`/`features`/`evaluation`/`review_priority`/`from_rally_examples`/CLIs); per-video validation noted; source descriptions reworded.
  - `domains/tests.md` — test-file count 25 → 41 (Purpose + Sources); 2026-05 data/eval tooling tests added to the ml Coordinates row.
- `last_compiled` bumped to 2026-05-31 on both. Line counts within hard_max 200 (ml 100, tests 73).
- Skipped (sources unchanged): 9.
- Status: complete (partial).

---

## [2026-05-31] source-update | ml + tests docs (auto-mechanical)

- Baseline: 8 ML-scope commits `e09da78..7eef4c9` (landed after the 2026-05-28 align).
- Drift items: 6 (factual: 1, structural: 3, editorial: 0, candidate-new: 2)
- Applied: 5  Skipped: 1  Edited inline: 0
- Source docs touched (working tree only — see commit note):
  - `docs/TRAINING_GUIDE.md` — [factual] caveat #1 "Checkpoint stores no model config" marked RESOLVED (`d9ba004`: config embedded under `"config"` + `load_winner_classifier` mismatch warning); [candidate-new, user-approved] new "## Auxiliary tools" section documenting `python -m ml.tools.{audit_training_corpus,collect_features,evaluate_winner}` (`7eef4c9`).
  - `docs/auto-editor-plan/current-state.md` — [candidate-new, user-approved] new "## Data & evaluation tooling (landed since)" subsection (`6ac5b59,f700643,f71d626,b7d8305,9087838,d9ba004,e09da78`); appended at end of doc to avoid clashing with the stale "What's missing from ml/" block.
  - `docs/TESTING.md`, `docs/TEST_SUITE_SUMMARY.md` — [structural] test-file count `25 → 41`.
- Skipped: [structural, low-confidence] `current-state.md:105` config.py class list — folded into the candidate-new subsection instead of editing a row already missing `WinnerModelConfig`.
- Candidate-new drafts left `<!-- DRAFT -->`-tagged for the user to detag.
- **Commits: NONE** — all four docs are `.gitignore`d, so Rule 5 per-doc commits are impossible (revert = file restore, not `git revert`). `README.md` (the only tracked source) was clean: its ML-tooling gap is dev-facing CLI, not app features, and its long-standing no-ML-mention is pre-window.
- Followed by: ingest of [`domains/ml.md`, `domains/tests.md`] (entry above).
- Status: complete (working tree only).

---

## [2026-05-28] source-update | all docs
- Drift items: 2 (factual: 2, structural: 0, editorial: 0, candidate-new: 0)
- Applied: 2  Skipped: 0  Edited inline: 0
- Source docs touched: [docs/TESTING_PLAYER.md, docs/TECH_STACK.md]
- Followed by: ingest of [full wiki]
- Status: complete

---

## [2026-05-28] ingest | full wiki

- Pages checked: 11
- Pages stale: 0
- Recompiled: []
- Skipped (up-to-date): 11
- Status: complete

---

## [2026-05-26] ingest --all | full wiki

- Trigger: explicit `/wiki-build ingest --all` after the same-day `wiki-source-update align`. Because `docs/` is `.gitignore`d, staleness detection via `git log` would not have caught the working-tree edits — `--all` recompiles every page regardless.
- Pages checked: 11 (6 domain + 3 architecture + 2 gotcha).
- Pages recompiled: 11 (all). DAG order honoured: domains → architecture → gotchas.
- Final line counts (all under the 200-line hard_max; pages well-compressed):
  - `domains/core.md` — 90
  - `domains/ui.md` — 101
  - `domains/video.md` — 127
  - `domains/output.md` — 81
  - `domains/ml.md` — 99
  - `domains/tests.md` — 73
  - `architecture/tech-stack.md` — 79
  - `architecture/auto-edit-pipeline.md` — 61
  - `architecture/session-lifecycle.md` — 58
  - `gotchas/pickleball-scoring.md` — 71
  - `gotchas/auto-edit-pitfalls.md` — 82
- Highlights of corrections that landed this run (the things the prior compile got wrong or didn't cover):
  - **core**: padding constants now class constants `START_PADDING=-0.5`/`END_PADDING=+1.0` applied inline; `ScoreState.set_player_names`/`has_player_names`/`reset`, `RallyManager.update_rally_winner`/`clear_all`/`get_last_rally_end_position`, `ScoreSnapshot.first_server_player_index`, `Rally.raw_*` + `is_post_game`, `SessionState.court_corners`/`game_completion`.
  - **ui**: player names are optional (commit 5a29662); ReviewModeWidget composition + `winner_flipped` signal; Flip Winner orange/amber palette via `_low_confidence_indices`; new dialogs (PlayerNames, NewGameConfirm, FrameSelector, Config, ExportProgress/Complete, AutoEditProgress).
  - **video**: skip durations configurable via `PlaybackControls.small_skip_duration` / `.large_skip_duration` and the unified `skip_requested(float)` signal; `frame_extract.py` + `_subprocess_env.py` documented.
  - **output**: schema 1.1 current; output basenames now via `generate_export_basename()` (YYYY-MM-DD prefix when video stem starts with 8 digits); FFmpeg direct-export promoted from "planned" to shipped; encoder-profile config; `LD_LIBRARY_PATH` sanitisation.
  - **ml**: 4-stage orchestrator + Stage 5 review pass landed; Flip Winner + `winner_flipped` signal close the correction loop; schema 1.1 generators current.
  - **tests**: suite has grown from 3 modules / 54 tests to 25 files; `run_tests.sh` deleted, `make test` is canonical.
  - **tech-stack**: ML add-ons + decord + OpenCV + PyTorch enumerated; `ExportManager` lifetime + `_subprocess_env.py` LD_LIBRARY_PATH note.
  - **auto-edit-pipeline**: Stage 2 corrected to T=20 frames / threshold 0.75; Stage 5 promoted to first-class section.
  - **session-lifecycle**: Auto path hydration is in-memory (no JSON round-trip); resume-at-last-cut (commit e1d47e8) noted; SessionState field inventory updated.
  - **gotchas**: pickleball-scoring expanded to 6 canonical rule gotchas + 2 derived; auto-edit-pitfalls restructured around the 6 review-fix tasks plus 2 Key-decisions architectural gotchas.
- Method: 11 pages compiled in 2 parallel waves of subagent workers (wave 1 = 6 domains, wave 2 = 3 architecture + 2 gotchas), each agent given the per-page source list, budget, structure, and key-facts brief. All output verified against hard_max before write.
- Cross-references validated: every domain links to at least one gotcha; every gotcha links to at least one domain; index lists every page (per `cross_ref_rules`).
- Recompiled: all 11 pages.
- Skipped (up-to-date): 0 (forced `--all`).
- Status: complete.

---

## [2026-05-26] ingest | partial (driven by source-update)

- Trigger: `wiki-source-update align --auto-mechanical` (entry above) edited many source docs in the working tree. Because `docs/` is `.gitignore`d, the default staleness check (`git log --since=<last_compiled> -- <source>`) finds no commits and cannot detect the changes. A full `--all` recompile would be ideal but is deferred; this run is a targeted patch over the most affected wiki pages.
- Pages updated (surgical patches, `last_compiled` bumped to 2026-05-26):
  - `domains/core.md` — padding constants corrected to inline `-0.5s` / `+1.0s` on `RallyManager`; SessionState/Rally/ScoreSnapshot new fields documented.
  - `domains/ui.md` — player names marked optional; Flip Winner button and `winner_flipped` signal added to ReviewModeWidget inventory; low-confidence styling noted.
  - `domains/video.md` — skip durations marked configurable; new `frame_extract.py` + `_subprocess_env.py` documented.
  - `domains/output.md` — output naming rewritten around `generate_export_basename()`; ffmpeg direct-export promoted from "planned" to "shipped"; encoder-profile config noted; `LD_LIBRARY_PATH` sanitisation noted.
  - `domains/ml.md` — current-state source line updated to reflect landed pipeline.
  - `domains/tests.md`, `architecture/tech-stack.md` — `last_compiled` bumped; source-doc text now aligns with these pages' existing claims.
- Pages not touched this run: `architecture/auto-edit-pipeline.md`, `architecture/session-lifecycle.md`, `gotchas/pickleball-scoring.md`, `gotchas/auto-edit-pitfalls.md`.
- Recommended follow-up: `wiki-build ingest --all` once the user is ready for a canonical, template-driven recompile.
- Status: complete (partial).

---

## [2026-05-26] source-update | all docs (auto-mechanical)

- Scope: every source doc in `wiki.config.md` (domains + architecture + gotchas).
- Anchor: most tracked source docs ended up anchored at `58ef78b` (2026-01-16,
  "Clean up repository for public release") because `docs/` is **gitignored** —
  `git log -- docs/<file>` returns only the deletion commit. Untracked docs
  (auto-editor-plan/*, TRAINING_GUIDE.md, DETAILED_DESIGN.md and others
  re-touched today) were treated with mtime-based anchors and the latest
  edits-since-mtime were processed.
- Mode: `--auto-mechanical` (factual + structural items applied without prompt;
  editorial and candidate-new items surfaced rather than written).
- Source docs touched (working tree edits, not commits — see note below):
  - `docs/DETAILED_DESIGN.md` — padding constants (-1.0→-0.5), inline padding
    note, ScoreState new methods (`set_player_names`/`has_player_names`/`reset`),
    ScoreSnapshot.first_server_player_index, RallyManager class constants and
    new methods (`get_last_rally_end_position`, `update_rally_winner`,
    `clear_all`), Rally raw_* timing fields and `is_post_game`, SessionState
    `first_server_player_index`/`court_corners`/`game_completion`.
  - `docs/SCORE_STATE_EXAMPLES.md` — RallyManager integration example updated
    for the current `start_rally(timestamp, score_snapshot)` /
    `end_rally(timestamp, winner, score_at_start, score_snapshot)` API.
  - `docs/SESSION_MANAGER_USAGE.md` — Example session JSON now includes
    `first_server_player_index`, `court_corners`, `game_completion`, and per-rally
    `is_post_game`/`raw_*` fields.
  - `docs/UI_SPEC.md` — toolbar inventory adds Names, New Game,
    Mark Court Corners buttons.
  - `docs/SETUP_DIALOG_GUIDE.md` — player names marked optional; auto-process
    mode court-corner calibration requirement added.
  - `docs/REVIEW_MODE_USAGE.md` — Flip Winner feature section added.
  - `docs/REVIEW_MODE_IMPLEMENTATION.md` — Flip Winner Button component
    inserted into the components inventory.
  - `docs/PLAYBACK_CONTROLS.md` — added `skip_requested` signal and
    `small_skip_duration`/`large_skip_duration` properties.
  - `docs/TESTING_PLAYER.md` — corrected `test_player.py` path
    (`src/video/test_player.py` → `tests/test_player.py`) per commit 597e75e.
  - `docs/OUTPUT_MODULE_COMPLETE.md` — file manifest adds `ffmpeg_exporter.py`,
    `hardware_detect.py`, `training_data_generator.py`.
  - `docs/OUTPUT_QUICK_REFERENCE.md` — imports include `FFmpegExporter` and
    `TrainingDataGenerator`; file-naming section rewritten to describe
    `generate_export_basename()` behaviour.
  - `docs/auto-editor-plan/current-state.md` — `TrainingDataGenerator` schema
    1.1 + `winning_team`; review-mode `winner_flipped` signal now landed.
  - `docs/auto-editor-plan/README.md` — Stage 4 phrased as landed; Project
    status updated to reflect rally-trainer pipeline + tools + Flip Winner.
  - `docs/auto-editor-plan/training-data.md` — schema migration marked as
    landed; "current" relabelled to "1.1".
  - `docs/TEST_SUITE_SUMMARY.md` — overview notes the suite has grown to 25
    test files; padding constants corrected.
  - `docs/TESTING.md` — removed references to deleted `run_tests.sh`; padding
    constants corrected; added note about the larger current suite.
  - `docs/TECH_STACK.md` — added decord/OpenCV/PyTorch/torchaudio/numpy/sklearn
    rows; ML add-on requirements block appended.
- **Critical note for the reader**: `docs/` is in `.gitignore`. Per-doc commits
  required by Rule 5 are not possible — `git add docs/…` is rejected. Revert
  is via file restoration (e.g., from backups or an mtime-based comparison)
  rather than `git revert`. The user accepted this trade-off when gitignoring
  `docs/`; this run respects the gitignore and writes only the working tree.
- Items surfaced as editorial (not auto-applied):
  - `README.md` has no mention of the ML auto-process pipeline (post-anchor
    feature, candidate-new — needs a one-paragraph "Auto-Process Mode" entry
    under "Features" with traceable commits `8b46df0`, `6faa718`).
  - `docs/UI_SPEC.md` Window Hierarchy table groups dialogs by category;
    several new dialogs (PlayerNames, NewGameConfirm, FrameSelector, Config,
    ExportProgress, ExportComplete, AutoEditProgress) fit existing categories
    so were not enumerated as rows. Author may want to either keep category
    grouping or expand inventory.
  - `docs/SESSION_MANAGER_IMPLEMENTATION.md` is pre-existing inaccurate (lists
    `_get_video_hash` only; public `get_video_hash` and the
    `list_all_sessions`/`load_from_session_file`/`delete_session_file` methods
    pre-date the doc's anchor). Not edited under Rule 1 (no triggering diff in
    the time window).
  - `docs/ffmpeg_integration_plan.md` is a planning artefact whose plan has
    landed; consider archiving rather than editing.
- Followed by: `wiki-build ingest` (next entry).
- Status: complete (working tree only; no commits because `docs/` is gitignored).

---

## [2026-05-01] ingest | full wiki

- Pages checked: 11 (6 domain + 3 architecture + 2 gotcha).
- Pages stale: 0. `git log --since=2026-04-24` empty for every source listed in `source-map.md`; `git status` shows no working-tree modifications to any wiki source (`docs/`, `README.md`, `.claude/agents/`).
- Recompiled: none.
- Skipped (up-to-date): all 11.
- Out-of-band drift flagged for the user (not actionable by ingest): a substantial body of uncommitted/untracked work has accumulated under `ml/` (winner classifier dataset/model/trainer, `ml/tools/calibrate_video.py`, `ml/tools/calibrate_existing.py` `--force` flag), `src/ui/widgets/court_calibrator.py`, `src/ui/dialogs/auto_edit_progress.py`, plus several modified `src/` files. None of the wiki source docs (`docs/auto-editor-plan/*.md`, `docs/TRAINING_GUIDE.md`, etc.) have been updated to describe this work, so the wiki is faithful to its sources but the sources have drifted from the code. Fixing this requires editing the source docs first; `ingest` cannot synthesize coverage that is not in any tracked source.
- Status: complete (no-op).

---

## [2026-04-24] update | domains/ml.md (canonical recompile)

- Trigger: `/wiki-build update domains/ml.md` to canonically re-derive the page after the prior surgical edit. Caught a routing-table inconsistency: `docs/TRAINING_GUIDE.md` was in the page's `compiled_from` and `## Sources` but missing from `wiki.config.md::domains.ml.source_paths` and `source-map.md`. Fixed both routing tables before the recompile so the canonical update has all 7 sources.
- Recompiled from 7 sources: 4 auto-editor-plan docs + `docs/TRAINING_GUIDE.md` + 2 shared skills (python-coder, code-reviewer scoped to ml).
- Substantive content changes vs prior surgical edit:
  - Confidence threshold corrected `0.7 → 0.75`. Caught internal source drift: `architecture.md` says 0.7, `implementation.md §3.1` shipped default is 0.75, `TRAINING_GUIDE.md` confirms 0.75. Later-source-wins merge rule resolved to 0.75 (the as-shipped default).
  - `train-winner` CLI bullet expanded: now also flags absence of `--patience`; notes checkpoint overwrites without versioning.
  - Schema rule tightened: `schema 1.1` → `schema >= 1.1`; `generated_by` filter admits absent OR `"manual"`.
  - New rule: checkpoint-no-config caveat — do NOT retune `clip_duration_s / fps_out / canonical_*` without retraining (silent preprocessing mismatch on load).
  - Coordinates With → video: added explicit link.
- Page size: 98 lines (target 140, hard_max 200). Rules: 20 bullets at the cap.
- Status: complete.

---

## [2026-04-24] update | domains/ml.md

- Trigger: documented gap (no `train-winner` CLI flags in the digest) was confirmed valid by an audit + code review of `ml/cli.py`, `ml/train_winner.py`, `ml/winner_dataset.py`, `ml/winner_model.py`, and the two `ml/tools/` retrofit utilities.
- Added 2 bullets to `## Rules` (kept total at 20 by merging the two backfill bullets): exact `train-winner` CLI surface (`--root --epochs --batch-size --device`; no `--lr/--resume/--checkpoint`) + training preconditions referencing `calibrate_existing` and `backfill_winner_labels`.
- Added cross-link to new `docs/TRAINING_GUIDE.md` in `## Patterns` and as a `## Sources` entry.
- Page size: 93 → 98 lines (still well under 200 hard_max).
- Companion artifact: `docs/TRAINING_GUIDE.md` (283 lines) — consolidated step-by-step training how-to. Surfaces current `~/Videos/pickleball/` data state (0/20 files training-ready; need calibrate_existing + backfill_winner_labels first), exact CLI invocations, expected runtime, verification roundtrip, and 3 known caveats from code review (checkpoint missing config metadata; silent rally attrition; no `--resume`).
- Status: complete.

---

## [2026-04-24] init | Pickleball Video Editor

- Config: `./.claude/wiki/wiki.config.md`
- Rendered infrastructure: `schema.md` (218 lines), `index.md` (37), `source-map.md` (53), `log.md`.
- Created 6 domain pages: core (83), ui (95), video (120), output (78), ml (93), tests (50).
- Created 3 architecture pages: tech-stack (58), auto-edit-pipeline (71), session-lifecycle (50).
- Created 2 gotcha pages: pickleball-scoring (83), auto-edit-pitfalls (79).
- All 11 content pages within hard_max 200 lines. All internal cross-refs resolve.
- Source doc gaps flagged during compilation (for future fixup, not init failures):
  - `docs/SESSION_INTEGRATION_USAGE.md` / `PHASE_7.2_SESSION_INTEGRATION_SUMMARY.md` predate the auto-edit path; `court_corners`, `AutoEditResult`, `AutoEditProgressDialog` came from context, not sources.
  - `confidence_threshold` default disagrees across `architecture.md` (0.7) and `implementation.md` (0.75). Used 0.7.
  - `python-coder.md` line 69 claims 0.5s pre-rally padding; `rally_manager.py` defines `START_PADDING = -1.0s`. Code is authoritative; flagged for agent-file cleanup.
  - `Rally.winning_team` discussion reflects the post-review fix (field was removed; re-derived at export).
- Status: complete.

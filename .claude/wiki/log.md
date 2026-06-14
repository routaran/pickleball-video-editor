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

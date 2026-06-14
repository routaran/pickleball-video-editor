# Review-driven fixes — orchestrator plan

Two independent reviews (user + GPT-5.4) of the auto-editor implementation
surfaced six material issues. All were verified against the actual code.
This document is a self-contained work plan for the orchestrator to execute
after a context clear.

## Orchestrator role

You are the **orchestrator**. Your job:

1. **Create the task list first.** Use `TaskCreate` to add every task listed
   in §Tasks below, in order. Then use `TaskUpdate` with `addBlockedBy` to wire
   dependencies (nearly everything is independent here).
2. **Delegate to specialist agents.** Tasks are code changes — use the
   `python-coder` agent for all implementation tasks. Never do the coding
   yourself; your job is coordination, review, and verification.
3. **Run independent tasks in parallel.** Launch multiple agents in a single
   message when they don't touch the same files. Almost all tasks here are
   independent — expect one big parallel wave.
4. **Monitor and verify.** After each agent returns, check the actual file
   changes (not just the agent's self-report). Mark the task complete via
   `TaskUpdate`. If the agent's work is incomplete or wrong, re-dispatch with
   corrective instructions rather than accepting the broken state.
5. **Run tests at the end.** After all tasks complete, run `make test` and
   confirm the full suite passes.

## Background (what you need to know)

The auto-edit pipeline was implemented in this same branch (see commits on
master). The implementation is structurally sound but has correctness bugs
and cruft. The fixes below target the bugs, not the architecture.

### The six issues

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 1 | `winning_team` derivation wrong for receiver-wins-with-side-out (~25% of labels flipped) | `src/output/training_data_generator.py:79-84`; `src/core/rally_manager.py:152`; `src/ui/main_window.py:1003-1014, 1049-1064` | correctness |
| 2 | Auto-review session hydration leaves `ScoreState` with default/empty score | `src/main.py:53-117, 232-238`; `src/ui/main_window.py:306-325` | correctness |
| 3 | Export drops `court_corners`, breaking the training feedback loop | `src/ui/main_window.py:2304-2317`; `ml/winner_dataset.py:68-95` | correctness |
| 4 | Debug cruft: writes `DEBUG_LOCALE.txt` on every startup + scattered `print()` calls | `src/main.py:37-38, 139-317` | cleanup |
| 5 | Auto-mode allowed for Highlights → crashes because `ScoreState` only supports singles/doubles | `src/ui/setup_dialog.py`; `ml/auto_edit.py:167-171` | correctness (edge) |
| 6 | `ml/auto_edit.py` imports `GameConfig` from the Qt layer → `python -m ml auto-edit` drags in PyQt6 | `ml/auto_edit.py:28` | coupling |

Plus: `make test` currently fails during collection at
`tests/test_video_features.py:86` — `CANONICAL_SIZE` unpacks as empty due to
a cv2-stub interaction.

### Why the root-cause fix for #1 is the right shape

`Rally.serving_team_at_start` (added at `src/core/models.py:104`) was supposed
to capture the serving team during a rally. But the snapshot is saved
**after** `server_wins()` / `receiver_wins()` mutates state. For
receiver-wins-with-side-out the serving team flips between rally and snapshot,
so `serving_team_at_start` is actually `serving_team_at_end`. The field is
misnamed AND redundant — `backfill_winner_labels.py:81-127` already derives
`winning_team` correctly from `score_at_start` + `winner` by re-syncing
`ScoreState`. Unify on that pattern, delete the field.

## Tasks

Create these as tasks via `TaskCreate`. Keep the wording. The subjects are
short and imperative; the descriptions give the agent everything it needs.

### Task A — Unify winning_team derivation; remove Rally.serving_team_at_start

**Subject**: `Fix #1: Remove Rally.serving_team_at_start; derive winning_team from score_at_start`

**Description**:
The current derivation at `src/output/training_data_generator.py:79-84`
uses `rally.serving_team_at_start`, but that field (`src/core/models.py:104`)
captures the post-action serving team because the snapshot is saved *after*
`server_wins()`/`receiver_wins()` in `src/ui/main_window.py:1003-1014` and
:1049-1064. For receiver wins that cause a side-out (~25% of rallies), the
serving team flips before capture, so labels are wrong.

Root-cause fix:
1. **Delete the `serving_team_at_start` field** from `Rally` in
   `src/core/models.py`. Remove it from `to_dict` / `from_dict`.
2. **Delete the `serving_team_at_start=score_snapshot.serving_team` argument**
   from `RallyManager.end_rally()` in `src/core/rally_manager.py:152`.
3. **Rewrite the derivation in `src/output/training_data_generator.py`** to
   match the re-sync pattern from `ml/tools/backfill_winner_labels.py:81-127`:
   init a fresh `ScoreState`, then for each rally call
   `score_state.set_score(rally.score_at_start)`, read `serving_team`,
   determine `winning_team = serving_team if winner=="server" else 1 - serving_team`,
   then advance state with `server_wins()` / `receiver_wins()`. Skip post-game
   rallies and highlights (set `winning_team = None`).
4. **Update any tests** that reference `serving_team_at_start`.
5. **Do not run the backfill tool** — existing `.training.json` files are
   already correct because the backfill tool used the right algorithm.

Verification: run `make test` and confirm the winning_team-related tests in
`tests/test_backfill_winner_labels.py` and any `tests/test_output*.py`
still pass. Spot-check one real training file in `~/Videos/pickleball/` —
the `winning_team` values should be unchanged.

---

### Task B — Pass court_corners when exporting from review mode

**Subject**: `Fix #3: Pass court_corners on export so feedback loop works`

**Description**:
`src/ui/main_window.py:2304-2317` calls `TrainingDataGenerator.write(...)`
without `court_corners=`. `ml/winner_dataset.py:68-95` filters out training
files without corners, so every user-corrected export is excluded from
future training. This silently breaks the feedback loop.

Fix:
1. **Pass `court_corners=self.config.court_corners`** to the
   `TrainingDataGenerator.write()` call at `src/ui/main_window.py:2305-2317`.
2. **Ensure `GameConfig.court_corners` is propagated to `SessionState.court_corners`**
   when `MainWindow` constructs session state. Grep for where SessionState is
   built from GameConfig — verify corners pass through.
3. Remove the bare `except Exception: pass` around the training JSON write at
   :2318-2319 if it's there. Let errors bubble up so silent drops stop.

Verification: run `make test`. Manually inspect the `TrainingDataGenerator.write`
call site and confirm `court_corners=` is now present.

---

### Task C — Fix auto-review session hydration; decouple ml.auto_edit from UI

**Subject**: `Fix #2 + #6: auto_edit returns full SessionState; introduce AutoEditSetup`

**Description**:
Two coupled fixes — cleaner to do together because they both reshape the
`auto_edit() → main.py` interface.

**Problem #2**: `session_from_training_json` in `src/main.py:53-117`
round-trips through the training JSON but doesn't populate `current_score`,
`serving_team`, `server_number`, or `first_server_player_index` on
`SessionState`. `MainWindow._init_core_components` at :306-325 then restores
a ScoreSnapshot from these defaults, producing a 0-0 score state that
doesn't match the actual game end. Review mode reads
`score_state.score[0]/[1]` and shows wrong values.

**Problem #6**: `ml/auto_edit.py:28` imports `GameConfig` from
`src.ui.setup_dialog`. This pulls PyQt6 into every invocation of
`python -m ml auto-edit` — a headless ML workflow that shouldn't need Qt.

Fix:
1. **Define `AutoEditSetup` dataclass** in `ml/auto_edit.py` (or a new
   `ml/types.py` if that feels cleaner) with the fields `auto_edit()`
   actually uses: `game_type`, `victory_rule`, `team1_players`,
   `team2_players`. No PyQt6 dependency.
2. **Change `auto_edit()` signature** to accept `AutoEditSetup` instead of
   `GameConfig`. Remove the `from src.ui.setup_dialog import GameConfig`
   import.
3. **Extend `AutoEditResult`** with a `session_state: SessionState` field.
   Populate it from the `ScoreState` / `RallyManager` / player_names you
   already have at the end of `auto_edit()` — all the fields
   (`current_score`, `serving_team`, `server_number`,
   `first_server_player_index`) are accessible from the final
   `ScoreState`. Do not round-trip through JSON.
4. **Remove `session_from_training_json()`** from `src/main.py`. Use
   `auto_result.session_state` directly. Delete the helper function.
5. **Update callers**:
   - `src/main.py`: construct `AutoEditSetup` from `GameConfig` before
     calling the progress dialog; consume `auto_result.session_state`.
   - `src/ui/dialogs/auto_edit_progress.py`: accept `AutoEditSetup`
     (not `GameConfig`) if the dialog forwards it. Check the dialog's
     constructor signature.
   - `ml/cli.py`: the `_cmd_auto_edit` handler constructs `AutoEditSetup`
     directly rather than `GameConfig`.
   - `tests/test_auto_edit.py`: update the test fixture to pass
     `AutoEditSetup`.

Verification: `python -c "import ml.auto_edit"` must succeed without PyQt6
available (you can verify conceptually by ensuring the module has no
`src.ui.*` import). `make test` passes. Manual: launch app, run auto mode
on a real video, confirm review mode shows the correct final score at the
top.

---

### Task D — Disable auto-mode for Highlights game type

**Subject**: `Fix #5: Disable auto-mode toggle for Highlights game type`

**Description**:
Setup dialog allows `game_type == "highlights"` with `auto_mode = True`.
`auto_edit.py:167-171` unconditionally constructs `ScoreState`, which only
supports singles/doubles. This path crashes at runtime.

Fix:
1. **UI guard in `src/ui/setup_dialog.py`**: when the game type combo
   changes to Highlights (index 2 per `src/ui/setup_dialog.py:1195`),
   disable the "Auto-process" radio button and force it back to "Manual
   editing". When switching away from Highlights, re-enable it.
2. **Backend guard in `ml/auto_edit.py`**: at the top of `auto_edit()`,
   raise `ValueError("auto_edit does not support highlights mode")` if
   `setup.game_type not in ("singles", "doubles")`. Belt-and-suspenders.

Verification: manual — set game type to Highlights in setup dialog, confirm
the auto radio is disabled and mode stays Manual. Switch back to Doubles,
confirm auto re-enables.

---

### Task E — Remove debug cruft from src/main.py

**Subject**: `Fix #4: Delete DEBUG_LOCALE.txt write and cleanup debug prints`

**Description**:
`src/main.py:37-38` writes `DEBUG_LOCALE.txt` into the repo root on every
launch. Plus there are scattered `print()` statements (lines ~139-317)
that were left over from development.

Fix:
1. **Delete the DEBUG_LOCALE.txt write** at `src/main.py:37-38`.
2. **Delete the file** from the repo if it exists: `DEBUG_LOCALE.txt` at
   repo root.
3. **Remove or downgrade debug prints** in `src/main.py`:
   - Delete the `">>> CODE VERSION: ..."` print at :139.
   - Keep a single `"Pickleball Video Editor vX.Y"` startup line if desired.
   - Convert informational `print()` calls in the auto path (lines 210,
     215, 218-221, 226-228, 247, 272-275) to `logger.info()` or delete them.
   - Keep error prints (e.g., "Error: Invalid configuration") — those are
     user-facing.
   - Leave the locale setup code (lines 20-34) alone; it's load-bearing
     for MPV.

Verification: grep `DEBUG_LOCALE.txt` across the repo and `src/main.py`
— no matches. `make test` passes. Launch the app manually, confirm no
`DEBUG_LOCALE.txt` appears.

---

### Task F — Fix test_video_features.py collection error

**Subject**: `Fix test collection: CANONICAL_SIZE unpacks empty in test_video_features`

**Description**:
`make test` currently fails during collection:
```
tests/test_video_features.py:86: in <module>
    W, H = CANONICAL_SIZE  # 256, 128
ValueError: not enough values to unpack (expected 2, got 0)
```

Root cause: at import time, `from ml.video_features import CANONICAL_SIZE`
picks up an empty tuple instead of `(256, 128)`. Direct import from the
shell returns `(256, 128)` correctly — so the issue is specific to how the
test's `cv2` stub at lines 42-52 interacts with pytest collection.

Fix:
1. Investigate why CANONICAL_SIZE is empty at test-collection time.
   Likely culprit: `MagicMock(name="cv2")` being placed into `sys.modules`
   before `ml.video_features` imports cleanly. MagicMock attribute access
   returns MagicMock instances, and something in the import chain may be
   evaluating `CANONICAL_SIZE` as a mock attribute.
2. Fix approach: either (a) make the cv2 stub more surgical so it only
   intercepts specific calls, not the module object; or (b) restructure
   the test so CANONICAL_SIZE is accessed inside functions, not at module
   top level; or (c) patch cv2 via `monkeypatch` inside a fixture rather
   than sys.modules injection.
3. Confirm `make test` collects all tests and runs to completion.

Verification: `make test` should show "N passed" with no collection errors.

---

## Task dependencies

All six tasks are independent — they touch mostly disjoint files:

| Task | Files touched |
|------|--------------|
| A | `src/core/models.py`, `src/core/rally_manager.py`, `src/output/training_data_generator.py`, tests |
| B | `src/ui/main_window.py` |
| C | `ml/auto_edit.py`, `src/main.py`, `src/ui/dialogs/auto_edit_progress.py`, `ml/cli.py`, `tests/test_auto_edit.py` |
| D | `src/ui/setup_dialog.py`, `ml/auto_edit.py` |
| E | `src/main.py`, `DEBUG_LOCALE.txt` (deletion) |
| F | `tests/test_video_features.py` |

**Note on C↔D↔E conflicts**: C, D, and E all touch `src/main.py` and/or
`ml/auto_edit.py`. Run them sequentially to avoid merge conflicts, OR
accept that you'll need to resolve conflicts manually. Suggested order:

- **Wave 1 (parallel)**: A, B, F — fully disjoint.
- **Wave 2 (sequential)**: C → D → E — shared files.

Or if you want maximum parallelism: run all six in parallel but tell C, D,
E agents to read each other's file regions carefully. Wave approach is
safer.

Set up the `addBlockedBy` graph accordingly:
- D blockedBy C (shared `src/ui/setup_dialog.py` touch? actually no — D
  only touches setup_dialog; C touches main.py and auto_edit. **D is
  actually independent of C in practice.** Keep it parallel.)
- E blockedBy C (both touch `src/main.py` heavily).

Revised safer graph:
- Wave 1 (parallel): A, B, D, F
- Wave 2: C (touches main.py extensively)
- Wave 3: E (cleans up main.py after C has stabilized it)

## Agent delegation template

For each task, spawn one `python-coder` agent with this template prompt
shape:

```
You are implementing [Task X] for the Pickleball Video Editor auto-editor fixes.

## Context
Project root: /home/rkalluri/Documents/source/pickleball_editing/
The background is in docs/auto-editor-plan/review-fixes.md — issue #[N].

## Required reading
- [list of specific files + line ranges]

## Task
[copy the "Fix:" section from the task description in review-fixes.md]

## Verification
[copy the "Verification:" section]

After implementing, mark Task #[ID] complete via TaskUpdate (only if the
TaskUpdate tool is available — if not, just report done and the orchestrator
will mark it).
```

## After all tasks complete

1. Run `make test` — ensure all tests pass.
2. Run `make lint` if available — ensure no new lint errors.
3. Manual smoke: `python -m ml auto-edit --help` should succeed without
   PyQt6 installed (conceptually — verify via import-only check).
4. Update the memory file
   `~/.claude/projects/-home-rkalluri-Documents-source-pickleball-editing/memory/project_auto_editor_plan.md`
   with a "Fixes applied YYYY-MM-DD" section listing what changed.
5. Report back to the user with a summary: what was fixed, what tests pass,
   any follow-ups worth flagging.

## Non-goals (don't do these)

- Don't restructure the pipeline beyond what the six fixes require.
- Don't add new features.
- Don't "improve" the existing logic while you're in the file — keep diffs
  tight to the fix.
- Don't rename files or reorganize modules.
- Don't add backwards-compat shims for the removed `serving_team_at_start`
  field. It was never shipped outside this branch; just delete it.

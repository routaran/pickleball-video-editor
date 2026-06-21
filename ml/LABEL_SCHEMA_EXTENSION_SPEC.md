# Label Schema Extension Spec — Forward-Compatible Optional Fields

**Status:** Scaffolding only. No classifiers, no training loops — just a specification of optional JSON fields and load-path behavior to keep the door open for future labeling.

---

## 1. What Exists Today

### Top-level keys in `.training.json` (schema 1.1)

| Key | Description |
|---|---|
| `schema_version` | `"1.1"` |
| `generated_by` | `"manual"` or `"auto_edit"` |
| `rallies` | List of rally dicts (see below) |
| `rally_count` | Integer count of rallies |
| `video` | `{path, fps, duration_seconds, width, height, court_corners}` |
| `game` | `{type, victory_rules, team1_players, team2_players, completion}` |

### Per-rally dict keys (schema 1.1)

| Key | Description |
|---|---|
| `index` | Zero-based rally index |
| `score_at_start` | Score string: `"T1-T2-ServerNum"` (doubles) or `"T1-T2"` (singles) |
| `winner` | `"server"` or `"receiver"` (perspective-relative) |
| `winning_team` | `0` or `1` (absolute team index) |
| `is_post_game` | Boolean |
| `comment` | Free-text or null |
| `raw` | `{start_frame, end_frame, start_seconds, end_seconds}` |
| `padded` | `{start_frame, end_frame, start_seconds, end_seconds}` |
| `score_snapshot_at_start` | **Optional, schema-ready but absent in current files.** `{serving_team, server_number, first_server_player_index}`. Already parsed by `RallyExample.from_rally_dict`. |

### What is already covered by existing winner/side work

- **Who won the point** — `winner` + `winning_team` — fully labeled; primary target for the winner classifier.
- **Serving team (absolute index)** — `score_snapshot_at_start.serving_team` — schema-ready in `RallyExample.serving_team`; not yet populated in any file, but `from_rally_dict` already reads it.
- **Camera near/far side** — live in *separate* annotation JSON files (`side_metrics.py`): terminal-event-side annotations and segment-level camera-near-team side map. Not in the `.training.json` schema.
- **Player names** — `game.team1_players` / `game.team2_players` — team rosters are already present at file level.

---

## 2. Proposed Optional-Field Schema

All fields are optional. Omitting them is valid forever; existing consumers silently ignore unknown keys (see §3). Loaders MUST use `.get()` with a `None` / `[]` default and MUST NOT fail if a key is absent.

### 2a. Per-rally optional fields

```json
{
  "index": 0,
  "winner": "receiver",
  "winning_team": 1,

  "end_reason": "winner",
  "serving_side": "near",
  "shots": [
    {
      "t_seconds": 25.1,
      "player_id": "Ravi",
      "shot_type": "serve"
    }
  ]
}
```

| Field | Type | Allowed values | Description |
|---|---|---|---|
| `end_reason` | `str \| null` | `"winner"`, `"out"`, `"net"`, `"error"`, `"unknown"` | How the point ended — the terminal event type. |
| `serving_side` | `str \| null` | `"near"`, `"far"`, `"unknown"` | Which court side the serving team occupies at this rally's start, relative to the recording camera. Mirrors the `terminal_event_side` convention in `side_metrics.py`. |
| `shots` | `list \| null` | see below | Ordered list of shot events within the rally. `null` or absent = not yet labeled. Empty list `[]` = labeled but no shots detected (unusual). |

**Shot event object:**

| Field | Type | Allowed values | Notes |
|---|---|---|---|
| `t_seconds` | `float` | ≥ 0.0 | Absolute timestamp of the shot within the video. |
| `player_id` | `str \| null` | Any name from `game.team1_players` / `team2_players`, or `null` | References the player roster. |
| `shot_type` | `str \| null` | `"serve"`, `"drive"`, `"dink"`, `"drop"`, `"lob"`, `"volley"`, `"smash"`, `"unknown"` | Shot classification. |

### 2b. Top-level optional field: `players`

```json
{
  "schema_version": "1.1",
  "players": {
    "Ravi":   {"team": 0, "dominant_hand": "right"},
    "Hussein": {"team": 0},
    "Chris":  {"team": 1},
    "Anish":  {"team": 1}
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `players` | `dict[str, object] \| null` | Key = player name (must match entries in `game.team1_players` / `team2_players`). Value = open object; `team` (0/1) is the only expected field. Any extra keys are ignored. |

**Why a top-level `players` block?** The `game.team1_players` / `team2_players` arrays already list names. This block adds per-player metadata (hand dominance, player ID for cross-video identity) without mutating the existing game block or breaking the teams array shape.

---

## 3. Loader Forward-Compat Audit

### `ml/dataset.py`

- **`load_training_json()`** — checks only for `"video"` and `"rallies"` keys; returns the raw dict as-is. Extra top-level keys (`players`, etc.) are silently present in the returned dict and ignored by callers.
- **`build_labels_from_rallies()`** — reads only `is_post_game`, `raw`, and `padded` from each rally dict. Unknown keys (`end_reason`, `serving_side`, `shots`) are **already silently ignored**. ✅ No change needed.
- **`_label_cache_key()`** — hashes the *entire* `rallies` list. Adding optional fields to rally dicts will cause an **audio-label cache miss** (recomputation) but **NOT a crash or incorrect output**. The recomputed label array is byte-identical to the previous one because the timing fields are unchanged. This is acceptable behavior; the cache miss is a one-time cost. ℹ️ Documented here; no code change warranted.

### `ml/winner_dataset.py`

- `_is_usable_training_file()` reads `schema_version`, `generated_by`, `video.court_corners` — unaffected.
- `WinnerDataset.__init__()` rally loop reads only `is_post_game`, `winning_team`, `raw`. Unknown keys ignored. ✅

### `ml/examples.py`

- `RallyExample.from_rally_dict()` reads `raw`, `score_at_start`, `winner`, `winning_team`, `is_post_game`, `index`, `score_snapshot_at_start`. Unknown keys in rally dicts are **already silently ignored** by `dict.get()`. ✅

**Verdict: No code change needed. All loaders are already forward-compatible with unknown optional keys.**

---

## 4. How Each Vector Would Be Consumed

### 4a. `end_reason` (per-rally)

- **Where labeled:** In the GUI label editor, a dropdown on each rally card: `winner / out / net / error / unknown`.
- **How loader would consume it:** `rally.get("end_reason")` — already safe; can be surfaced in `RallyExample` as a new optional field (defaulting to `None`).
- **What it trains:** A per-rally end-reason classifier taking the last N audio frames + motion end-burst features as input.
- **Reuses:** Terminal-event-side annotations in `side_metrics.py` already distinguish near/far for the terminal event. `end_reason` would replace the separate annotation file for event *type* (winner vs error), consolidating into the rally dict itself.
- **Fidelity wall:** ⚠️ **BLOCKED.** Reliably distinguishing `out` from `winner` (ball landing in vs out) requires ball tracking. Audio-only: net errors have a distinctive thud but `winner` vs `out` are indistinguishable from audio. Motion alone can detect crowd reaction but not ball path. **Label manually until ball tracking is available.**

### 4b. `serving_side` (per-rally)

- **Where labeled:** In the GUI label editor, a per-rally toggle (`near` / `far` / `unknown`), or auto-derived from `score_snapshot_at_start.serving_team` + the segment-level camera-near-team side map.
- **How loader would consume it:** `rally.get("serving_side")` — maps directly to the `camera_near_team` / `terminal_event_side` convention already used in `side_metrics.py`.
- **What it trains:** A serving-side feature that can augment the winner classifier (serve from far side is a known accuracy degradation source). Also enables the `compute_terminal_event_side_metrics` path to run without a separate annotation file.
- **Reuses:** The existing `side_metrics.load_side_map` / segment map infrastructure could be replaced or supplemented by inline rally-level `serving_side` labels. `RallyExample.serving_team` (from `score_snapshot_at_start`) already provides the absolute team; `serving_side` adds the camera-relative perspective needed for far-side analysis.
- **Fidelity wall:** ✅ **TRACTABLE.** Serving side can be derived from: (a) `score_snapshot_at_start.serving_team` + a single per-game or per-segment camera-near-team annotation, or (b) motion tracking — the server starts at the baseline and the ByteTrack foot-point clusters distinguish near vs far side. Does NOT require ball tracking.

### 4c. `shots` (per-rally, per-shot hit events)

- **Where labeled:** Manual annotation tool (click-to-mark hit timestamps on waveform + assign player + shot type), or semi-automated from audio hit-detection peaks with human correction.
- **How loader would consume it:** `rally.get("shots", [])` — a list of dicts; each dict has `t_seconds`, `player_id`, `shot_type`. Loaders iterate and extract hit timestamps for audio hit-detection training; `player_id` enables per-player feature attribution.
- **What it trains:**
  - Hit-timing classifier (shot boundary detector) — `t_seconds` alone is sufficient; tractable from audio+motion.
  - Per-player hit attribution — links `player_id` to ByteTrack IDs via court position at `t_seconds`.
  - Shot-type classifier — `shot_type` labels a fine-grained classifier; ball-tracking dependent.
- **Reuses:** ByteTrack foot-point tracks (`ml/motion/`) already provide per-frame player positions. `player_id` can be matched to track IDs by court-side heuristics (team → near/far side → track cluster). Hit timing aligns with audio transient spikes already used implicitly for rally boundary detection.
- **Fidelity wall (mixed):**
  - `t_seconds` (hit timing): ✅ **TRACTABLE** — audio transient detection + motion velocity peaks.
  - `player_id` (who hit): ✅ **TRACTABLE** — court position at `t_seconds` + team side assignment.
  - `shot_type` (fine-grained): ⚠️ **BLOCKED** for dink/drive/drop/lob distinction — requires ball speed/height/trajectory. Serve vs non-serve is tractable (position at rally start = baseline).

### 4d. `players` (top-level roster with metadata)

- **Where labeled:** Once per game in the GUI.
- **How loader would consume it:** `data.get("players", {})` at file level; entries cross-referenced with `game.team1_players` / `team2_players` for team assignment. No `schema_version` bump needed.
- **What it trains:** Cross-video player identity (same player name across different game files = same identity). Enables per-player performance metrics and player-identity-aware model features.
- **Reuses:** `game.team1_players` / `team2_players` are already the name ground truth. This block only adds metadata rows to an already-known name list.
- **Fidelity wall:** ✅ **TRACTABLE** — player identity is a labeling problem (names → court side → motion tracks), not a ball-tracking problem.

---

## 5. Fidelity-Wall Summary

| Vector | Field | Tractable without ball tracking? | Notes |
|---|---|---|---|
| Serving-team location | `serving_side` | ✅ Yes | Derivable from motion + single side annotation |
| Player identity | `players`, `shots[].player_id` | ✅ Yes | Court-position heuristics from ByteTrack |
| Hit timing | `shots[].t_seconds` | ✅ Yes | Audio transient + motion velocity |
| Serve detection | `shots[].shot_type == "serve"` | ✅ Yes | Server starts at baseline |
| Point-end reason | `end_reason` | ⚠️ BLOCKED | Needs ball in/out tracking |
| Fine shot type | `shots[].shot_type` (non-serve) | ⚠️ BLOCKED | Needs ball speed/trajectory |

---

## 6. Schema Versioning Note

These additions do NOT require a `schema_version` bump. Optional keys with `.get()` / `None`-default access are inherently backward-compatible. A bump to `"1.2"` is recommended *only* if a field becomes required or if a loader starts enforcing a minimum schema for the new fields. Document the bump in this file at that time.

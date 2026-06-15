"""Top-K trajectory association over ball candidates (per-candidate beam DP).

Links per-frame candidates into smooth, fast, near-ballistic tracks.  A second-order
(velocity-aware) cost penalizes acceleration and gaps, rewards candidate quality, and
discourages stationary chains — so player limbs / static distractors don't form long
tracks while the ball does.  Returns the top-K tracks per rally; the single best path
feeds the (label-blind) feature model, the rest support false-negative diagnostics.
"""

from dataclasses import dataclass, field

import numpy as np

from ml.winner_tracking.detect import Candidate

__all__ = ["Track", "TrackerConfig", "track_candidates"]


@dataclass(slots=True)
class Track:
    frames: list[int]
    xs: list[float]
    ys: list[float]
    total_reward: float
    mean_score: float
    span: int            # last_frame - first_frame
    length: int          # number of nodes

    def points(self) -> list[tuple[int, float, float]]:
        return list(zip(self.frames, self.xs, self.ys))


@dataclass(slots=True)
class TrackerConfig:
    """Tracks are scored by *motion + smoothness*, not length, so that fast smooth
    ballistic arcs (the ball) beat long persistent jittery chains (player limbs)."""

    max_gap: int = 5                 # frames a track may skip (occlusion)
    max_disp_per_frame: float = 150.0  # px/frame speed gate (near-side fast ball)
    accel_gate: float = 18.0         # px/frame: max |Δvelocity| between steps (kills jitter)
    beam: int = 6                    # incoming states kept per candidate
    top_per_frame: int = 15          # candidates considered per frame
    w_speed: float = 1.0             # reward per step for ball-like speed
    speed_ref: float = 8.0           # px/frame giving full speed reward
    speed_cap: float = 1.5           # max speed-reward multiple per step
    w_quality: float = 0.30          # reward for candidate quality (color/motion/shape)
    lambda_gap: float = 0.20
    lambda_acc: float = 0.020        # per px/frame^2 — penalize non-ballistic jitter
    lambda_static: float = 0.40      # penalty for ~stationary steps
    lambda_player: float = 0.60      # penalty per step landing inside a player body
    min_move_px: float = 2.0
    min_length: int = 5              # nodes required to count as a track
    min_span: int = 8                # frame span required to count as a track
    min_net_disp: float = 45.0       # px: straight-line distance a real ball covers
    min_straightness: float = 0.40   # net_disp / path_len (coherent vs jitter)
    top_k: int = 12


@dataclass(slots=True)
class _State:
    cost: float
    vx: float
    vy: float
    back_cand: int       # index into flat candidate array, or -1 for a start
    back_state: int      # index into predecessor's state list, or -1


def track_candidates(
    per_frame: list[list[Candidate]], cfg: TrackerConfig | None = None
) -> list[Track]:
    """Return up to ``cfg.top_k`` non-overlapping tracks, best first."""
    if cfg is None:
        cfg = TrackerConfig()

    # Flatten candidates (kept per-frame top-N) into one indexed array.
    flat: list[Candidate] = []
    by_frame: dict[int, list[int]] = {}
    for cands in per_frame:
        for c in sorted(cands, key=lambda c: -c.score)[: cfg.top_per_frame]:
            by_frame.setdefault(c.frame, []).append(len(flat))
            flat.append(c)
    if not flat:
        return []

    frames_sorted = sorted(by_frame.keys())
    states: list[list[_State]] = [[] for _ in flat]

    for f in frames_sorted:
        for ci in by_frame[f]:
            c = flat[ci]
            # A start state has cost 0: length is NOT intrinsically rewarded; only
            # ball-like motion (fast, smooth) accrues negative cost (= reward).
            cand_states: list[_State] = [_State(0.0, 0.0, 0.0, -1, -1)]
            for pf in range(max(0, f - cfg.max_gap), f):
                if pf not in by_frame:
                    continue
                gap = f - pf
                for pi in by_frame[pf]:
                    p = flat[pi]
                    dx, dy = c.x - p.x, c.y - p.y
                    disp = float(np.hypot(dx, dy))
                    if disp > cfg.max_disp_per_frame * gap:
                        continue
                    vx, vy = dx / gap, dy / gap
                    step_speed = disp / gap
                    speed_rew = cfg.w_speed * min(step_speed / cfg.speed_ref, cfg.speed_cap)
                    move_pen = cfg.lambda_static if step_speed < cfg.min_move_px else 0.0
                    gap_pen = cfg.lambda_gap * (gap - 1)
                    player_pen = cfg.lambda_player * c.in_player
                    pstates = states[pi]
                    if not pstates:
                        continue
                    for si, ps in enumerate(pstates):
                        is_start = ps.back_cand == -1 and ps.vx == 0.0 and ps.vy == 0.0
                        if is_start:
                            acc = 0.0  # predecessor was a start (no velocity yet)
                        else:
                            acc = float(np.hypot(vx - ps.vx, vy - ps.vy))
                            # Acceleration gate: a ball changes velocity slowly except
                            # at discrete bounce/hit events (which start a NEW track).
                            if acc > cfg.accel_gate:
                                continue
                        # cost = -(rewards) + penalties; DP minimizes cost.
                        cost = (
                            ps.cost
                            - speed_rew
                            - cfg.w_quality * c.score
                            + gap_pen
                            + cfg.lambda_acc * acc
                            + move_pen
                            + player_pen
                        )
                        cand_states.append(_State(cost, vx, vy, pi, si))
            cand_states.sort(key=lambda s: s.cost)
            states[ci] = cand_states[: cfg.beam]

    # Collect best end-states across all candidates, then greedily extract
    # non-overlapping top-K tracks by backtracking.
    ends: list[tuple[float, int, int]] = []
    for ci, ss in enumerate(states):
        for si, s in enumerate(ss):
            ends.append((s.cost, ci, si))
    ends.sort(key=lambda e: e[0])

    used: set[int] = set()
    tracks: list[Track] = []
    for cost, ci, si in ends:
        if len(tracks) >= cfg.top_k:
            break
        # Backtrack this path.
        path: list[int] = []
        cur_c, cur_s = ci, si
        ok = True
        while cur_c != -1:
            if cur_c in used:
                ok = False
                break
            path.append(cur_c)
            st = states[cur_c][cur_s]
            cur_c, cur_s = st.back_cand, st.back_state
        if not ok or len(path) < cfg.min_length:
            continue
        path.reverse()
        cands = [flat[i] for i in path]
        span = cands[-1].frame - cands[0].frame
        if span < cfg.min_span:
            continue
        xs = [c.x for c in cands]
        ys = [c.y for c in cands]
        net_disp = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]))
        path_len = float(
            sum(np.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]) for i in range(1, len(xs)))
        )
        straightness = net_disp / (path_len + 1e-6)
        # Reject jitter (low coherence) and stationary blobs (tiny net travel).
        if net_disp < cfg.min_net_disp or straightness < cfg.min_straightness:
            continue
        for i in path:
            used.add(i)
        tracks.append(
            Track(
                frames=[c.frame for c in cands],
                xs=xs,
                ys=ys,
                total_reward=float(-cost),
                mean_score=float(np.mean([c.score for c in cands])),
                span=int(span),
                length=len(path),
            )
        )
    # Re-rank by a ballistic score: motion+smoothness reward weighted by coherence.
    def _ballistic(t: Track) -> float:
        nd = float(np.hypot(t.xs[-1] - t.xs[0], t.ys[-1] - t.ys[0]))
        pl = float(sum(np.hypot(t.xs[i] - t.xs[i - 1], t.ys[i] - t.ys[i - 1])
                       for i in range(1, len(t.xs)))) + 1e-6
        return t.total_reward * (0.5 + nd / pl)

    tracks.sort(key=_ballistic, reverse=True)
    return tracks

"""Tests for ml/tools/backfill_winner_labels.py.

Tests the _backfill_game function directly on in-memory dicts, covering:
- Correct winning_team derivation for a simple game
- Intervention re-sync (score_at_start override absorbs mid-game edits)
- Post-game rallies receive winning_team=None
- Malformed score_at_start causes the game to be skipped without raising
- Idempotency across two successive backfill runs
"""

import copy

import pytest

from ml.tools.backfill_winner_labels import _already_labeled, _backfill_game


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_game_section(
    game_type: str = "doubles",
    victory_rules: str = "11",
    team1: list[str] | None = None,
    team2: list[str] | None = None,
) -> dict:
    """Return a minimal game section dict matching the training JSON schema."""
    return {
        "type": game_type,
        "victory_rules": victory_rules,
        "team1_players": team1 or ["Alice", "Bob"],
        "team2_players": team2 or ["Carol", "Dave"],
    }


def _make_rally(
    index: int,
    score_at_start: str,
    winner: str,
    *,
    is_post_game: bool = False,
) -> dict:
    """Return a minimal rally dict matching the training JSON schema."""
    rally = {
        "index": index,
        "score_at_start": score_at_start,
        "winner": winner,
    }
    if is_post_game:
        rally["is_post_game"] = True
    return rally


# ---------------------------------------------------------------------------
# Test 1: Correct winning_team for a simple 5-rally doubles game
# ---------------------------------------------------------------------------


class TestSimpleDoublesGame:
    """winning_team is derived correctly when there are no interventions.

    Game trace (doubles, starting 0-0-2, team0 serves first):

    Rally  score_at_start  serving_team  winner    winning_team
    -----  --------------  ------------  --------  ------------
    0      0-0-2           0             server    0
    1      1-0-2           0             server    0
    2      2-0-2           0             receiver  1
    3      0-2-1           1             server    1
    4      1-2-1           1             receiver  0

    Trace verified by running ScoreState forward in the test-setup script.
    """

    @pytest.fixture()
    def game_section(self) -> dict:
        return _make_game_section()

    @pytest.fixture()
    def rallies(self) -> list[dict]:
        return [
            _make_rally(0, "0-0-2", "server"),
            _make_rally(1, "1-0-2", "server"),
            _make_rally(2, "2-0-2", "receiver"),
            _make_rally(3, "0-2-1", "server"),
            _make_rally(4, "1-2-1", "receiver"),
        ]

    def test_no_error_returned(self, game_section, rallies):
        """_backfill_game returns None (success) for a well-formed game."""
        error = _backfill_game(game_section, rallies)
        assert error is None

    def test_winning_team_rally_0(self, game_section, rallies):
        """Rally 0: team0 serving, server wins -> winning_team=0."""
        _backfill_game(game_section, rallies)
        assert rallies[0]["winning_team"] == 0

    def test_winning_team_rally_1(self, game_section, rallies):
        """Rally 1: team0 serving, server wins -> winning_team=0."""
        _backfill_game(game_section, rallies)
        assert rallies[1]["winning_team"] == 0

    def test_winning_team_rally_2(self, game_section, rallies):
        """Rally 2: team0 serving, receiver wins -> winning_team=1."""
        _backfill_game(game_section, rallies)
        assert rallies[2]["winning_team"] == 1

    def test_winning_team_rally_3(self, game_section, rallies):
        """Rally 3: team1 serving (after side-out), server wins -> winning_team=1."""
        _backfill_game(game_section, rallies)
        assert rallies[3]["winning_team"] == 1

    def test_winning_team_rally_4(self, game_section, rallies):
        """Rally 4: team1 serving, receiver wins -> winning_team=0."""
        _backfill_game(game_section, rallies)
        assert rallies[4]["winning_team"] == 0

    def test_all_rallies_have_winning_team_key(self, game_section, rallies):
        """Every rally dict must carry the winning_team key after backfill."""
        _backfill_game(game_section, rallies)
        for i, rally in enumerate(rallies):
            assert "winning_team" in rally, f"Rally {i} is missing winning_team"

    def test_schema_version_not_set_by_backfill_game(self, game_section, rallies):
        """_backfill_game only mutates rallies; schema_version lives outside it."""
        # _backfill_game receives only the game section and rallies slice.
        # Schema bumping is the caller's responsibility (_process_file).
        # This test confirms _backfill_game does not touch the game_section dict.
        game_section_before = copy.deepcopy(game_section)
        _backfill_game(game_section, rallies)
        assert game_section == game_section_before


# ---------------------------------------------------------------------------
# Test 2: Intervention handling — re-sync works
# ---------------------------------------------------------------------------


class TestInterventionReSync:
    """Injected score_at_start values re-sync state and affect downstream rallies.

    Game layout (5 rallies):
    - Rallies 0–2: normal sequence (receiver wins at 0, then team1 server_wins x2)
    - Rally 3: INTERVENED — score_at_start set to '3-0-2' instead of the naive '2-0-1'
      (simulates an Edit Score intervention that changed server number 1->2)
    - Rally 4: winner=server

    Naive replay (without re-sync):
      Rally 3 would read '2-0-1' (server1), receiver wins -> server2, same team
      Rally 4: team1 still serving, server wins -> winning_team=1

    Corrected replay (with re-sync to '3-0-2'):
      Rally 3: server2, receiver wins -> SIDE-OUT -> team0 serves
      Rally 4: team0 serving, server wins -> winning_team=0

    The two paths produce different winning_team for rally 4, so this test
    exercises that _backfill_game uses score_at_start for re-sync rather than
    trusting naive forward-play.
    """

    @pytest.fixture()
    def game_section(self) -> dict:
        return _make_game_section()

    @pytest.fixture()
    def rallies(self) -> list[dict]:
        # Scores for rallies 0-2 match what the app actually records.
        # Rally 0: starting score, receiver wins (immediate side-out from 0-0-2)
        # Rally 1: team1 serving after side-out, score '0-0-1', server wins
        # Rally 2: team1 server1, score '1-0-1', server wins
        # Rally 3: INTERVENTION — naive would be '2-0-1', injected '3-0-2'
        # Rally 4: score_at_start after the intervention rally resolves ('0-3-1')
        return [
            _make_rally(0, "0-0-2", "receiver"),
            _make_rally(1, "0-0-1", "server"),
            _make_rally(2, "1-0-1", "server"),
            _make_rally(3, "3-0-2", "receiver"),   # <-- injected intervention score
            _make_rally(4, "0-3-1", "server"),
        ]

    def test_no_error_returned(self, game_section, rallies):
        error = _backfill_game(game_section, rallies)
        assert error is None

    def test_rally_4_winning_team_uses_corrected_serving_team(self, game_section, rallies):
        """Rally 4: after intervention side-out, team0 serves -> server wins -> winning_team=0.

        If backfill had used naive replay it would see team1 serving and assign winning_team=1.
        The correct re-synced answer is winning_team=0 (team0 serves after side-out).
        """
        _backfill_game(game_section, rallies)
        assert rallies[4]["winning_team"] == 0

    def test_rally_3_winning_team_from_intervention_score(self, game_section, rallies):
        """Rally 3: re-synced to '3-0-2' (server2, team1 serving), receiver wins -> winning_team=0."""
        _backfill_game(game_section, rallies)
        # team1 (index=1) is serving, receiver wins -> winning_team = 1 - 1 = 0
        assert rallies[3]["winning_team"] == 0


# ---------------------------------------------------------------------------
# Test 3: Post-game rallies get winning_team=None
# ---------------------------------------------------------------------------


class TestPostGameRallies:
    """Rallies with is_post_game=True must receive winning_team=None."""

    @pytest.fixture()
    def game_section(self) -> dict:
        return _make_game_section()

    @pytest.fixture()
    def rallies(self) -> list[dict]:
        return [
            _make_rally(0, "0-0-2", "server"),
            _make_rally(1, "1-0-2", "server"),
            # Post-game rallies have no meaningful winner for scoring purposes
            _make_rally(2, "", "server", is_post_game=True),
            _make_rally(3, "", "receiver", is_post_game=True),
        ]

    def test_no_error_returned(self, game_section, rallies):
        error = _backfill_game(game_section, rallies)
        assert error is None

    def test_post_game_rally_winning_team_is_none(self, game_section, rallies):
        """Each post-game rally must have winning_team explicitly set to None."""
        _backfill_game(game_section, rallies)
        assert rallies[2]["winning_team"] is None
        assert rallies[3]["winning_team"] is None

    def test_post_game_rally_has_winning_team_key(self, game_section, rallies):
        """The winning_team key must be present (with value None), not absent."""
        _backfill_game(game_section, rallies)
        assert "winning_team" in rallies[2]
        assert "winning_team" in rallies[3]

    def test_scored_rallies_before_post_game_are_labeled(self, game_section, rallies):
        """Scored rallies that precede post-game rallies still get labeled."""
        _backfill_game(game_section, rallies)
        assert rallies[0]["winning_team"] == 0
        assert rallies[1]["winning_team"] == 0


# ---------------------------------------------------------------------------
# Test 4: Malformed score_at_start — skip the game
# ---------------------------------------------------------------------------


class TestMalformedScore:
    """A rally with an unparseable score_at_start causes _backfill_game to abort.

    The function must return a non-None error string instead of raising, so
    that the caller (_process_file) can log a warning and skip the file without
    crashing the entire batch run.
    """

    @pytest.fixture()
    def game_section(self) -> dict:
        return _make_game_section()

    @pytest.fixture()
    def rallies_with_bad_score(self) -> list[dict]:
        return [
            _make_rally(0, "0-0-2", "server"),
            _make_rally(1, "invalid", "server"),   # <-- malformed
            _make_rally(2, "2-0-2", "receiver"),
        ]

    def test_returns_error_string_not_raises(self, game_section, rallies_with_bad_score):
        """_backfill_game must not raise; it returns a non-None error string."""
        error = _backfill_game(game_section, rallies_with_bad_score)
        assert error is not None
        assert isinstance(error, str)

    def test_error_message_references_bad_rally(self, game_section, rallies_with_bad_score):
        """The error message should identify the problematic rally index."""
        error = _backfill_game(game_section, rallies_with_bad_score)
        # Rally index 1 is the malformed one
        assert "1" in error

    def test_no_exception_propagates(self, game_section, rallies_with_bad_score):
        """Calling _backfill_game on malformed data must never raise an exception."""
        try:
            _backfill_game(game_section, rallies_with_bad_score)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"_backfill_game raised unexpectedly: {exc!r}")

    def test_already_labeled_check_respects_missing_schema_version(self):
        """_already_labeled returns False when schema_version is not '1.1'."""
        data = {
            "schema_version": "1.0",
            "game": _make_game_section(),
            "rallies": [
                _make_rally(0, "0-0-2", "server"),
            ],
        }
        assert _already_labeled(data) is False

    def test_file_level_skipping_via_already_labeled(self):
        """After _process_file logic: schema_version stays '1.0' on malformed input.

        We simulate the caller's behavior: if _backfill_game returns an error,
        schema_version must not be bumped to '1.1'.
        """
        data: dict = {
            "schema_version": "1.0",
            "game": _make_game_section(),
            "rallies": [
                _make_rally(0, "0-0-2", "server"),
                _make_rally(1, "bad-score", "server"),
            ],
        }
        rallies_copy = copy.deepcopy(data["rallies"])
        error = _backfill_game(data["game"], rallies_copy)

        # Simulate caller logic: only commit + bump if no error
        if error is None:
            data["rallies"] = rallies_copy
            data["schema_version"] = "1.1"

        # Must stay at "1.0" — the file is skipped, not partially updated
        assert data["schema_version"] == "1.0"
        # winning_team must NOT have been written back into the original data
        assert "winning_team" not in data["rallies"][0]


# ---------------------------------------------------------------------------
# Test 5: Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Running backfill twice on the same data produces identical results.

    The second run must produce the exact same winning_team values as the first.
    This guards against any stateful mutation that could alter the outcome when
    winning_team is already present on the input rallies.
    """

    @pytest.fixture()
    def game_section(self) -> dict:
        return _make_game_section()

    @pytest.fixture()
    def rallies(self) -> list[dict]:
        return [
            _make_rally(0, "0-0-2", "server"),
            _make_rally(1, "1-0-2", "server"),
            _make_rally(2, "2-0-2", "receiver"),
            _make_rally(3, "0-2-1", "server"),
            _make_rally(4, "1-2-1", "receiver"),
        ]

    def test_second_run_produces_identical_winning_team(self, game_section, rallies):
        """First and second backfill runs assign the same winning_team to every rally."""
        # First run
        error1 = _backfill_game(game_section, rallies)
        after_first = [r.get("winning_team") for r in rallies]

        # Second run (winning_team keys now pre-exist on each rally)
        error2 = _backfill_game(game_section, rallies)
        after_second = [r.get("winning_team") for r in rallies]

        assert error1 is None
        assert error2 is None
        assert after_first == after_second

    def test_second_run_no_extra_keys_added(self, game_section, rallies):
        """Second run must not add any new unexpected keys to rally dicts."""
        _backfill_game(game_section, rallies)
        keys_after_first = {frozenset(r.keys()) for r in rallies}

        _backfill_game(game_section, rallies)
        keys_after_second = {frozenset(r.keys()) for r in rallies}

        assert keys_after_first == keys_after_second

    def test_already_labeled_returns_true_after_bump(self):
        """_already_labeled returns True when schema_version is '1.1' and all rallies are labeled."""
        data = {
            "schema_version": "1.1",
            "game": _make_game_section(),
            "rallies": [
                {**_make_rally(0, "0-0-2", "server"), "winning_team": 0},
                {**_make_rally(1, "1-0-2", "server"), "winning_team": 0},
            ],
        }
        assert _already_labeled(data) is True

    def test_already_labeled_returns_false_if_any_rally_missing_key(self):
        """_already_labeled returns False when at least one scored rally lacks winning_team."""
        data = {
            "schema_version": "1.1",
            "game": _make_game_section(),
            "rallies": [
                {**_make_rally(0, "0-0-2", "server"), "winning_team": 0},
                _make_rally(1, "1-0-2", "server"),  # missing winning_team
            ],
        }
        assert _already_labeled(data) is False

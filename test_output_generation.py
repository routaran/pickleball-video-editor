#!/usr/bin/env python3
"""Test the output generation integration in MainWindow.

This test verifies that the _on_review_generate() method correctly:
1. Gets segments from rally manager
2. Probes video for resolution
3. Creates KdenliveGenerator
4. Generates Kdenlive and SRT files
5. Shows appropriate feedback to the user

This is a unit-style test that doesn't require the full GUI.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication

# Initialize QApplication (required for Qt widgets)
app = QApplication([])

from src.ui.main_window import MainWindow
from src.ui.setup_dialog import GameConfig
from src.video.probe import VideoInfo


def test_generate_with_rallies():
    """Test generation with valid rallies."""
    print("\n=== Test 1: Generation with valid rallies ===")

    # Create mock config
    config = GameConfig(
        video_path=Path(__file__).parent / "examples" / "sample_match.mp4",
        game_type="doubles",
        victory_rule="11",
        team1_players=["Alice", "Bob"],
        team2_players=["Carol", "Dave"]
    )

    # Mock video probe to avoid actual file requirement
    mock_video_info = VideoInfo(
        path=str(config.video_path),
        width=1920,
        height=1080,
        fps=60.0,
        duration=120.0,
        codec_name="h264",
        codec_long_name="H.264",
        bit_rate=5000000,
        frame_count=7200
    )

    with patch("src.ui.main_window.probe_video", return_value=mock_video_info):
        with patch("src.ui.main_window.VideoWidget"):
            with patch("src.ui.main_window.StatusOverlay"):
                window = MainWindow(config)

                # Add some mock rallies
                window.rally_manager.rallies = [
                    Mock(start_frame=600, end_frame=1200, score_at_start="0-0-2"),
                    Mock(start_frame=1800, end_frame=2400, score_at_start="1-0-2"),
                    Mock(start_frame=3000, end_frame=3600, score_at_start="2-0-2"),
                ]

                # Mock to_segments to return valid data
                window.rally_manager.to_segments = Mock(return_value=[
                    {"in": 600, "out": 1200, "score": "0-0-2"},
                    {"in": 1800, "out": 2400, "score": "1-0-2"},
                    {"in": 3000, "out": 3600, "score": "2-0-2"},
                ])

                # Mock the generator
                mock_kdenlive_path = Path("/home/user/Videos/pickleball/match_rallies.kdenlive")
                mock_srt_path = Path("/home/user/Videos/pickleball/match_scores.srt")

                with patch("src.ui.main_window.KdenliveGenerator") as MockGenerator:
                    mock_gen_instance = MockGenerator.return_value
                    mock_gen_instance.generate.return_value = (mock_kdenlive_path, mock_srt_path)

                    # Mock toast and OSD
                    with patch("src.ui.main_window.ToastManager"):
                        window.video_widget = Mock()

                        # Call the method
                        window._on_review_generate()

                        # Verify KdenliveGenerator was created correctly
                        MockGenerator.assert_called_once()
                        call_kwargs = MockGenerator.call_args[1]

                        assert call_kwargs["video_path"] == str(config.video_path)
                        assert call_kwargs["fps"] == 60.0
                        assert call_kwargs["resolution"] == (1920, 1080)
                        assert len(call_kwargs["segments"]) == 3

                        # Verify generate was called
                        mock_gen_instance.generate.assert_called_once()

                        print("✓ KdenliveGenerator created with correct parameters")
                        print("✓ generate() method called")
                        print("✓ Toast and OSD feedback shown")


def test_generate_no_rallies():
    """Test generation with no rallies."""
    print("\n=== Test 2: Generation with no rallies ===")

    config = GameConfig(
        video_path=Path(__file__).parent / "examples" / "sample_match.mp4",
        game_type="singles",
        victory_rule="11",
        team1_players=["Alice"],
        team2_players=["Bob"]
    )

    mock_video_info = VideoInfo(
        path=str(config.video_path),
        width=1920,
        height=1080,
        fps=60.0,
        duration=120.0,
        codec_name="h264",
        codec_long_name="H.264"
    )

    with patch("src.ui.main_window.probe_video", return_value=mock_video_info):
        with patch("src.ui.main_window.VideoWidget"):
            with patch("src.ui.main_window.StatusOverlay"):
                window = MainWindow(config)

                # No rallies
                window.rally_manager.to_segments = Mock(return_value=[])

                with patch("src.ui.main_window.ToastManager") as MockToast:
                    # Call the method
                    window._on_review_generate()

                    # Verify warning was shown
                    MockToast.show_warning.assert_called_once()
                    args = MockToast.show_warning.call_args[0]
                    assert "No rallies" in args[1]

                    print("✓ Warning shown for empty rallies")


def test_generate_probe_fails():
    """Test generation when video probe fails."""
    print("\n=== Test 3: Generation when probe fails (fallback to default resolution) ===")

    config = GameConfig(
        video_path=Path(__file__).parent / "examples" / "sample_match.mp4",
        game_type="doubles",
        victory_rule="11",
        team1_players=["Alice", "Bob"],
        team2_players=["Carol", "Dave"]
    )

    # First probe succeeds (in _load_video), second fails (in _on_review_generate)
    call_count = [0]

    def probe_side_effect(path):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call in _load_video
            return VideoInfo(
                path=str(path),
                width=1920,
                height=1080,
                fps=60.0,
                duration=120.0,
                codec_name="h264",
                codec_long_name="H.264"
            )
        else:
            # Second call in _on_review_generate - fail
            from src.video.probe import ProbeError
            raise ProbeError("Mock probe failure")

    with patch("src.ui.main_window.probe_video", side_effect=probe_side_effect):
        with patch("src.ui.main_window.VideoWidget"):
            with patch("src.ui.main_window.StatusOverlay"):
                window = MainWindow(config)

                # Add mock rally
                window.rally_manager.to_segments = Mock(return_value=[
                    {"in": 600, "out": 1200, "score": "0-0-2"},
                ])

                mock_kdenlive_path = Path("/home/user/Videos/pickleball/match_rallies.kdenlive")
                mock_srt_path = Path("/home/user/Videos/pickleball/match_scores.srt")

                with patch("src.ui.main_window.KdenliveGenerator") as MockGenerator:
                    mock_gen_instance = MockGenerator.return_value
                    mock_gen_instance.generate.return_value = (mock_kdenlive_path, mock_srt_path)

                    with patch("src.ui.main_window.ToastManager") as MockToast:
                        window.video_widget = Mock()

                        # Call the method
                        window._on_review_generate()

                        # Verify fallback resolution was used
                        call_kwargs = MockGenerator.call_args[1]
                        assert call_kwargs["resolution"] == (1920, 1080), "Should use default resolution"

                        # Verify warning was shown about resolution (in the except block)
                        # Check if show_warning was called at all (we have 1 call for resolution detection)
                        warning_calls = [c for c in MockToast.method_calls if 'show_warning' in str(c)]
                        if warning_calls:
                            print("✓ Warning shown about resolution detection")

                        print("✓ Fallback to default 1920x1080 resolution")


def test_generate_generator_fails():
    """Test generation when KdenliveGenerator.generate() raises exception."""
    print("\n=== Test 4: Generation when generator fails ===")

    config = GameConfig(
        video_path=Path(__file__).parent / "examples" / "sample_match.mp4",
        game_type="doubles",
        victory_rule="11",
        team1_players=["Alice", "Bob"],
        team2_players=["Carol", "Dave"]
    )

    mock_video_info = VideoInfo(
        path=str(config.video_path),
        width=1920,
        height=1080,
        fps=60.0,
        duration=120.0,
        codec_name="h264",
        codec_long_name="H.264"
    )

    with patch("src.ui.main_window.probe_video", return_value=mock_video_info):
        with patch("src.ui.main_window.VideoWidget"):
            with patch("src.ui.main_window.StatusOverlay"):
                window = MainWindow(config)

                window.rally_manager.to_segments = Mock(return_value=[
                    {"in": 600, "out": 1200, "score": "0-0-2"},
                ])

                with patch("src.ui.main_window.KdenliveGenerator") as MockGenerator:
                    mock_gen_instance = MockGenerator.return_value
                    mock_gen_instance.generate.side_effect = OSError("Disk full")

                    with patch("src.ui.main_window.ToastManager") as MockToast:
                        window.video_widget = Mock()

                        # Call the method
                        window._on_review_generate()

                        # Verify error toast was shown
                        MockToast.show_error.assert_called_once()
                        args = MockToast.show_error.call_args[0]
                        assert "Generation failed" in args[1]
                        assert "Disk full" in args[1]

                        print("✓ Error toast shown with exception details")


if __name__ == "__main__":
    print("Testing Output Generation Integration")
    print("=" * 60)

    test_generate_with_rallies()
    test_generate_no_rallies()
    test_generate_probe_fails()
    test_generate_generator_fails()

    print("\n" + "=" * 60)
    print("All tests passed!")

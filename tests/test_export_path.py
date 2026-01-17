"""Tests for export path selection feature in KdenliveGenerator.

Tests:
- Default output directory uses Path.home() / "Videos"
- Default filename is {stem}.kdenlive (not {stem}_rallies.kdenlive)
- Custom output_path parameter works correctly
- Output directory creation
- Automatic .kdenlive extension addition
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.output.kdenlive_generator import KdenliveGenerator
from src.video.probe import VideoInfo


@pytest.fixture
def mock_video_info():
    """Create a mock VideoInfo object for testing."""
    return VideoInfo(
        path="/fake/video.mp4",
        width=1920,
        height=1080,
        fps=60.0,
        duration=120.0,
        codec_name="h264",
        codec_long_name="H.264 / AVC",
        bit_rate=5000000,
        frame_count=7200,
    )


@pytest.fixture
def sample_segments():
    """Create sample rally segments for testing."""
    return [
        {"in": 0, "out": 300, "score": "0-0-2"},
        {"in": 600, "out": 900, "score": "1-0-2"},
    ]


class TestKdenliveGeneratorDefaultPaths:
    """Test default path behavior in KdenliveGenerator."""

    def test_default_output_dir_uses_home(self, tmp_path, sample_segments):
        """Verify default output_dir is Path.home() / 'Videos' not a hardcoded path."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Create generator without specifying output_dir
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
        )

        # Verify output_dir is set to home Videos directory
        expected_output_dir = Path.home() / "Videos"
        assert generator.output_dir == expected_output_dir

    def test_output_filename_no_rallies_suffix(self, tmp_path, sample_segments, mock_video_info):
        """Default filename should be {stem}.kdenlive not {stem}_rallies.kdenlive."""
        # Create a fake video file
        video_path = tmp_path / "my_game.mp4"
        video_path.write_bytes(b"fake video content")

        # Create generator and mock the dependencies
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
            output_dir=tmp_path,
        )

        # Mock probe_video and internal methods to avoid full generation
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate()

        # Verify filename is my_game.kdenlive, not my_game_rallies.kdenlive
        assert kdenlive_path.name == "my_game.kdenlive"
        assert kdenlive_path == tmp_path / "my_game.kdenlive"

        # Verify ASS file matches
        assert ass_path.name == "my_game.kdenlive.ass"


class TestKdenliveGeneratorCustomPath:
    """Test custom output path functionality."""

    def test_generate_with_custom_path(self, tmp_path, sample_segments, mock_video_info):
        """When output_path is provided to generate(), it should use that path."""
        # Create a fake video file
        video_path = tmp_path / "source_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Create custom output path
        custom_output_dir = tmp_path / "custom_output"
        custom_output_dir.mkdir(parents=True, exist_ok=True)
        custom_path = custom_output_dir / "my_custom_name.kdenlive"

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
            output_dir=tmp_path,  # Different from custom path
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate(output_path=custom_path)

        # Verify it used the custom path, not the default
        assert kdenlive_path == custom_path
        assert kdenlive_path.name == "my_custom_name.kdenlive"
        assert kdenlive_path.parent == custom_output_dir

        # Verify ASS file is alongside the kdenlive file
        assert ass_path == custom_path.with_suffix(".kdenlive.ass")
        assert ass_path.parent == custom_output_dir

    def test_generate_creates_output_directory(self, tmp_path, sample_segments, mock_video_info):
        """If output directory doesn't exist, it should be created."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Create custom path with non-existent parent directories
        nested_path = tmp_path / "deeply" / "nested" / "path" / "output.kdenlive"
        # Verify parent doesn't exist yet
        assert not nested_path.parent.exists()

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate(output_path=nested_path)

        # Verify directory was created
        assert nested_path.parent.exists()
        assert kdenlive_path == nested_path
        assert kdenlive_path.exists()

    def test_generate_adds_kdenlive_extension_if_missing(self, tmp_path, sample_segments, mock_video_info):
        """If user provides path without .kdenlive extension, it should be added."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Create custom path WITHOUT .kdenlive extension
        custom_path_no_ext = tmp_path / "my_project"

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate(output_path=custom_path_no_ext)

        # Verify .kdenlive extension was added
        assert kdenlive_path.suffix == ".kdenlive"
        assert kdenlive_path == tmp_path / "my_project.kdenlive"

        # Verify ASS file has correct extension
        assert ass_path == tmp_path / "my_project.kdenlive.ass"


class TestKdenliveGeneratorPathEdgeCases:
    """Test edge cases for path handling."""

    def test_custom_path_with_wrong_extension(self, tmp_path, sample_segments, mock_video_info):
        """If custom path has wrong extension, it should be replaced with .kdenlive."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Create custom path with .xml extension
        custom_path_wrong_ext = tmp_path / "my_project.xml"

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate(output_path=custom_path_wrong_ext)

        # Verify .kdenlive extension was used
        assert kdenlive_path.suffix == ".kdenlive"
        assert kdenlive_path == tmp_path / "my_project.kdenlive"

    def test_default_path_creates_output_dir_if_missing(self, tmp_path, sample_segments, mock_video_info):
        """Default path should create output_dir if it doesn't exist."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Set output_dir to non-existent directory
        non_existent_dir = tmp_path / "new_output_dir"
        assert not non_existent_dir.exists()

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
            output_dir=non_existent_dir,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate()

        # Verify output_dir was created
        assert non_existent_dir.exists()
        assert kdenlive_path.parent == non_existent_dir

    def test_custom_path_absolute_vs_relative(self, tmp_path, sample_segments, mock_video_info):
        """Test that both absolute and relative paths work for custom output_path."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Test with absolute path
        absolute_path = tmp_path / "absolute" / "output.kdenlive"
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
        )

        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path_abs, _ = generator.generate(output_path=absolute_path)

        assert kdenlive_path_abs == absolute_path
        assert kdenlive_path_abs.exists()

        # Test with relative path (pathlib automatically handles it)
        relative_path = Path("relative_output.kdenlive")
        expected_absolute = Path.cwd() / "relative_output.kdenlive"

        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path_rel, _ = generator.generate(output_path=relative_path)

        # Note: The actual path used will be relative unless resolved
        assert kdenlive_path_rel.name == "relative_output.kdenlive"


class TestKdenliveGeneratorOutputDirParameter:
    """Test output_dir parameter in constructor."""

    def test_custom_output_dir_in_constructor(self, tmp_path, sample_segments, mock_video_info):
        """Test that output_dir parameter in constructor is respected."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Set custom output directory
        custom_output_dir = tmp_path / "my_custom_output"
        custom_output_dir.mkdir(parents=True, exist_ok=True)

        # Create generator with custom output_dir
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
            output_dir=custom_output_dir,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate()

        # Verify files are in custom output directory
        assert kdenlive_path.parent == custom_output_dir
        assert ass_path.parent == custom_output_dir

    def test_output_path_overrides_output_dir(self, tmp_path, sample_segments, mock_video_info):
        """Test that output_path parameter to generate() overrides output_dir."""
        # Create a fake video file
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")

        # Set output_dir in constructor
        output_dir_constructor = tmp_path / "constructor_dir"
        output_dir_constructor.mkdir(parents=True, exist_ok=True)

        # Set different output_path in generate()
        output_path_generate = tmp_path / "generate_dir" / "custom.kdenlive"
        output_path_generate.parent.mkdir(parents=True, exist_ok=True)

        # Create generator
        generator = KdenliveGenerator(
            video_path=video_path,
            segments=sample_segments,
            fps=60.0,
            output_dir=output_dir_constructor,
        )

        # Mock probe_video and internal methods
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            with patch.object(generator, "_write_ass_file"):
                with patch.object(generator, "_build_mlt_xml", return_value="<mlt/>"):
                    kdenlive_path, ass_path = generator.generate(output_path=output_path_generate)

        # Verify output_path parameter was used, not output_dir
        assert kdenlive_path == output_path_generate
        assert kdenlive_path.parent == output_path_generate.parent
        assert kdenlive_path.parent != output_dir_constructor

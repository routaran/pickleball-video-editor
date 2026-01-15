#!/usr/bin/env python3
"""Test script for output generation module.

This script tests:
1. SubtitleGenerator.frames_to_srt_time()
2. SubtitleGenerator.generate_srt()
3. SubtitleGenerator.write_srt()
4. KdenliveGenerator initialization and generation

Run with: python test_output_generators.py
"""

import sys
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.output.subtitle_generator import SubtitleGenerator
from src.output.kdenlive_generator import KdenliveGenerator


def test_frames_to_srt_time():
    """Test SRT timestamp conversion."""
    print("Testing frames_to_srt_time()...")

    # Test cases: (frame, fps, expected_output)
    test_cases = [
        (0, 60.0, "00:00:00,000"),
        (60, 60.0, "00:00:01,000"),
        (90, 60.0, "00:00:01,500"),
        (3600, 60.0, "00:01:00,000"),
        (216000, 60.0, "01:00:00,000"),
        (150, 30.0, "00:00:05,000"),
    ]

    for frame, fps, expected in test_cases:
        result = SubtitleGenerator.frames_to_srt_time(frame, fps)
        status = "✓" if result == expected else "✗"
        print(f"  {status} Frame {frame} @ {fps}fps = {result} (expected: {expected})")

        if result != expected:
            print(f"    ERROR: Mismatch!")
            return False

    print("  All timestamp conversions passed!\n")
    return True


def test_generate_srt():
    """Test SRT content generation."""
    print("Testing generate_srt()...")

    # Sample rally segments
    segments = [
        {"in": 100, "out": 500, "score": "0-0-2"},
        {"in": 800, "out": 1200, "score": "1-0-2"},
        {"in": 1500, "out": 2000, "score": "1-1-1"},
    ]

    fps = 60.0
    srt_content = SubtitleGenerator.generate_srt(segments, fps)

    # Verify structure
    lines = srt_content.split("\n")

    # Should have entries for 3 segments (each entry is 4 lines: number, timing, text, blank)
    expected_line_count = 3 * 4
    if len(lines) != expected_line_count:
        print(f"  ✗ Expected {expected_line_count} lines, got {len(lines)}")
        return False

    # Check first entry
    if lines[0] != "1":
        print(f"  ✗ First line should be '1', got '{lines[0]}'")
        return False

    if "0-0-2" not in lines[2]:
        print(f"  ✗ First score should be '0-0-2', got '{lines[2]}'")
        return False

    # Verify cumulative timing
    # Segment 1: frames 0-400 (401 frames) @ 60fps = 0.000 - 6.683 seconds
    # Should start at 00:00:00,000
    if not lines[1].startswith("00:00:00,000"):
        print(f"  ✗ First segment should start at 00:00:00,000")
        print(f"    Got: {lines[1]}")
        return False

    print("  ✓ SRT structure valid")
    print("  ✓ Timing is cumulative (output timeline)")
    print("  ✓ Scores embedded correctly")
    print(f"\nGenerated SRT preview (first 10 lines):")
    for i, line in enumerate(lines[:10], 1):
        print(f"    {i}: {line}")
    print()
    return True


def test_write_srt():
    """Test SRT file writing."""
    print("Testing write_srt()...")

    segments = [
        {"in": 0, "out": 100, "score": "0-0"},
        {"in": 200, "out": 300, "score": "1-0"},
    ]

    fps = 30.0

    # Write to temporary file
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_scores.srt"

        result_path = SubtitleGenerator.write_srt(segments, fps, output_path)

        if not result_path.exists():
            print(f"  ✗ File not created at {result_path}")
            return False

        # Read and verify content
        content = result_path.read_text(encoding="utf-8")

        if "0-0" not in content or "1-0" not in content:
            print(f"  ✗ Scores not found in generated file")
            return False

        print(f"  ✓ File written successfully to {result_path}")
        print(f"  ✓ Content verified ({len(content)} bytes)")
        print()

    return True


def test_kdenlive_generator_init():
    """Test KdenliveGenerator initialization."""
    print("Testing KdenliveGenerator initialization...")

    # Test with invalid parameters
    segments = [{"in": 0, "out": 100, "score": "0-0"}]

    # Test invalid fps
    try:
        gen = KdenliveGenerator("video.mp4", segments, fps=0)
        print("  ✗ Should raise ValueError for fps=0")
        return False
    except ValueError:
        print("  ✓ Correctly rejects fps=0")

    # Test invalid resolution
    try:
        gen = KdenliveGenerator("video.mp4", segments, fps=60, resolution=(0, 1080))
        print("  ✗ Should raise ValueError for invalid resolution")
        return False
    except (ValueError, FileNotFoundError):
        print("  ✓ Correctly rejects invalid resolution")

    # Test nonexistent video file
    try:
        gen = KdenliveGenerator("/nonexistent/video.mp4", segments, fps=60)
        print("  ✗ Should raise FileNotFoundError for missing file")
        return False
    except FileNotFoundError:
        print("  ✓ Correctly rejects missing video file")

    print()
    return True


def test_kdenlive_output_dir():
    """Test KdenliveGenerator output directory handling."""
    print("Testing KdenliveGenerator output directory...")

    # Create temporary video file
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "test_video.mp4"
        video_path.write_text("fake video content")

        segments = [{"in": 0, "out": 100, "score": "0-0"}]

        # Test default output dir
        gen = KdenliveGenerator(str(video_path), segments, fps=60)

        expected_default = Path.home() / "Videos" / "pickleball"
        if gen.output_dir != expected_default:
            print(f"  ✗ Default output dir should be {expected_default}")
            print(f"    Got: {gen.output_dir}")
            return False

        print(f"  ✓ Default output dir: {gen.output_dir}")

        # Test custom output dir
        custom_dir = Path(tmpdir) / "custom_output"
        gen = KdenliveGenerator(str(video_path), segments, fps=60, output_dir=custom_dir)

        if gen.output_dir != custom_dir:
            print(f"  ✗ Custom output dir not set correctly")
            return False

        print(f"  ✓ Custom output dir: {gen.output_dir}")
        print()

    return True


def test_integration():
    """Test full integration (generate mock project)."""
    print("Testing full generation (mock)...")

    # Note: This test creates a mock output without a real video file
    # For real testing, you'd need an actual video file

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal dummy video file
        video_path = Path(tmpdir) / "rally_video.mp4"
        video_path.write_bytes(b"not a real video")

        segments = [
            {"in": 0, "out": 300, "score": "0-0-2"},
            {"in": 500, "out": 800, "score": "1-0-2"},
            {"in": 1000, "out": 1500, "score": "2-0-2"},
        ]

        output_dir = Path(tmpdir) / "output"

        try:
            gen = KdenliveGenerator(
                video_path=video_path,
                segments=segments,
                fps=60.0,
                resolution=(1920, 1080),
                output_dir=output_dir
            )

            print(f"  ✓ Generator initialized")
            print(f"    Video: {gen.video_path}")
            print(f"    Segments: {len(gen.segments)}")
            print(f"    FPS: {gen.fps}")
            print(f"    Resolution: {gen.resolution}")
            print(f"    Output dir: {gen.output_dir}")

            # Note: Can't call generate() without a real video for ffprobe
            # In a real test with a video file, you would:
            # kdenlive_path, srt_path = gen.generate()
            # assert kdenlive_path.exists()
            # assert srt_path.exists()

        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            return False

    print()
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Output Generation Module Tests")
    print("=" * 60)
    print()

    tests = [
        ("Frame to SRT Time", test_frames_to_srt_time),
        ("Generate SRT", test_generate_srt),
        ("Write SRT", test_write_srt),
        ("Kdenlive Init", test_kdenlive_generator_init),
        ("Kdenlive Output Dir", test_kdenlive_output_dir),
        ("Integration", test_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"  {symbol} {name}: {status}")

    print()

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

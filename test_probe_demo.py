#!/usr/bin/env python3
"""Demo script to test video probe functionality.

This script demonstrates how to use the probe_video function to extract
metadata from a video file. It's intended for manual testing.

Usage:
    python test_probe_demo.py [path/to/video.mp4]
"""

import sys
from pathlib import Path
from src.video import probe_video, ProbeError, frames_to_timecode, timecode_to_frames


def demo_probe(video_path: str) -> None:
    """Demonstrate video probing functionality.

    Args:
        video_path: Path to video file to probe
    """
    print(f"Probing video: {video_path}")
    print("-" * 60)

    try:
        info = probe_video(video_path)

        print(f"Path:          {info.path}")
        print(f"Resolution:    {info.resolution} ({info.width}x{info.height})")
        print(f"Aspect Ratio:  {info.aspect_ratio:.2f}")
        print(f"FPS:           {info.fps:.2f}")
        print(f"Duration:      {info.duration:.2f}s")
        print(f"Codec:         {info.codec_name}")
        print(f"Codec (long):  {info.codec_long_name}")

        if info.bit_rate:
            # Convert to Mbps for readability
            mbps = info.bit_rate / 1_000_000
            print(f"Bitrate:       {mbps:.2f} Mbps ({info.bit_rate} bps)")

        if info.frame_count:
            print(f"Frame Count:   {info.frame_count:,}")

        print("\n" + "=" * 60)
        print("Timecode Conversion Examples:")
        print("=" * 60)

        # Example: Convert first frame
        tc = frames_to_timecode(0, info.fps)
        print(f"Frame 0        -> {tc}")

        # Example: Convert 1 second worth of frames
        one_sec = int(info.fps)
        tc = frames_to_timecode(one_sec, info.fps)
        print(f"Frame {one_sec:<7} -> {tc}")

        # Example: Convert 1 minute worth of frames
        one_min = int(info.fps * 60)
        tc = frames_to_timecode(one_min, info.fps)
        print(f"Frame {one_min:<7} -> {tc}")

        # Example: Reverse conversion
        print(f"\nReverse: 00:01:30.000 -> Frame {timecode_to_frames('00:01:30.000', info.fps)}")

        print("\n" + "=" * 60)
        print("Serialization Test:")
        print("=" * 60)

        # Test serialization
        data = info.to_dict()
        print("to_dict() keys:", list(data.keys()))

        # Test deserialization
        from src.video import VideoInfo
        restored = VideoInfo.from_dict(data)
        print(f"Restored resolution: {restored.resolution}")
        print(f"Serialization: PASSED" if restored.width == info.width else "FAILED")

    except ProbeError as e:
        print(f"Error probing video: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_probe_demo.py <video_file>")
        print("\nNote: This is a demo script. No video file provided.")
        print("To test with a real video:")
        print("  python test_probe_demo.py /path/to/your/video.mp4")
        sys.exit(0)

    video_path = sys.argv[1]

    if not Path(video_path).exists():
        print(f"Error: File not found: {video_path}")
        sys.exit(1)

    demo_probe(video_path)


if __name__ == "__main__":
    main()

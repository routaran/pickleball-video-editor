#!/usr/bin/env python3
"""
Test script for typography constants module.

Verifies that font constants are defined correctly and the Fonts helper
class can create QFont instances. Also checks which design system fonts
are available on the current system.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PyQt6.QtWidgets import QApplication
from ui.styles.fonts import (
    FONT_DISPLAY,
    FONT_BODY,
    FONT_DISPLAY_FALLBACK,
    FONT_BODY_FALLBACK,
    SIZE_SCORE_DISPLAY,
    SIZE_BUTTON_RALLY,
    SIZE_TIMESTAMPS,
    WEIGHT_BOLD,
    WEIGHT_SEMIBOLD,
    WEIGHT_MEDIUM,
    SPACE_MD,
    SPACE_LG,
    RADIUS_MD,
    Fonts,
)


def test_constants() -> None:
    """Test that all constants are defined correctly."""
    print("Typography Constants Test")
    print("=" * 60)

    print("\n1. Font Families:")
    print(f"   Display Font:     {FONT_DISPLAY}")
    print(f"   Body Font:        {FONT_BODY}")
    print(f"   Display Fallback: {', '.join(FONT_DISPLAY_FALLBACK)}")
    print(f"   Body Fallback:    {', '.join(FONT_BODY_FALLBACK)}")

    print("\n2. Font Sizes:")
    print(f"   Score Display:    {SIZE_SCORE_DISPLAY}px")
    print(f"   Rally Button:     {SIZE_BUTTON_RALLY}px")
    print(f"   Timestamp:        {SIZE_TIMESTAMPS}px")

    print("\n3. Font Weights:")
    print(f"   Bold:             {WEIGHT_BOLD}")
    print(f"   Semibold:         {WEIGHT_SEMIBOLD}")
    print(f"   Medium:           {WEIGHT_MEDIUM}")

    print("\n4. Spacing (8px base):")
    print(f"   Medium:           {SPACE_MD}px")
    print(f"   Large:            {SPACE_LG}px")

    print("\n5. Border Radius:")
    print(f"   Medium:           {RADIUS_MD}px")


def test_font_creation() -> None:
    """Test creating QFont instances using Fonts helper class."""
    print("\nFont Creation Test")
    print("=" * 60)

    # Create various fonts
    score_font = Fonts.score_display()
    rally_button = Fonts.button_rally()
    timestamp_font = Fonts.timestamp()
    label_font = Fonts.label()

    print("\n1. Score Display Font:")
    print(f"   Family:  {score_font.family()}")
    print(f"   Size:    {score_font.pointSize()}pt")
    print(f"   Weight:  {score_font.weight()}")

    print("\n2. Rally Button Font:")
    print(f"   Family:  {rally_button.family()}")
    print(f"   Size:    {rally_button.pointSize()}pt")
    print(f"   Weight:  {rally_button.weight()}")

    print("\n3. Timestamp Font:")
    print(f"   Family:  {timestamp_font.family()}")
    print(f"   Size:    {timestamp_font.pointSize()}pt")
    print(f"   Weight:  {timestamp_font.weight()}")

    print("\n4. Label Font:")
    print(f"   Family:  {label_font.family()}")
    print(f"   Size:    {label_font.pointSize()}pt")
    print(f"   Weight:  {label_font.weight()}")


def test_font_availability() -> None:
    """Check which design system fonts are available on this system."""
    print("\nFont Availability Test")
    print("=" * 60)

    available = Fonts.get_available_fonts()

    print("\nInstalled Fonts:")
    for font_name, is_available in sorted(available.items()):
        status = "✓ Available" if is_available else "✗ Not Found"
        print(f"   {font_name:<20} {status}")

    # Check primary fonts
    primary_available = available.get(FONT_DISPLAY, False) and available.get(
        FONT_BODY, False
    )

    print("\nStatus:")
    if primary_available:
        print("   ✓ All primary fonts are available")
    else:
        print("   ⚠ Some primary fonts missing, will use fallbacks")
        if not available.get(FONT_DISPLAY, False):
            print(f"     Missing: {FONT_DISPLAY}")
        if not available.get(FONT_BODY, False):
            print(f"     Missing: {FONT_BODY}")


def main() -> None:
    """Run all typography tests."""
    # Create QApplication (required for QFont operations)
    app = QApplication(sys.argv)

    try:
        test_constants()
        test_font_creation()
        test_font_availability()

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

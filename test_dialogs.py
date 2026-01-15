#!/usr/bin/env python3
"""Quick test script to verify intervention dialogs can be instantiated.

This script tests that:
1. All dialogs can be imported
2. All dialogs can be instantiated with typical parameters
3. Result dataclasses are properly structured

Does NOT test interactive functionality - this is just a smoke test.
"""

import sys
from PyQt6.QtWidgets import QApplication

from src.ui.dialogs import (
    EditScoreDialog,
    EditScoreResult,
    ForceSideOutDialog,
    ForceSideOutResult,
    AddCommentDialog,
    AddCommentResult,
)


def test_edit_score_dialog():
    """Test EditScoreDialog instantiation."""
    print("Testing EditScoreDialog...")

    dialog = EditScoreDialog(
        current_score="7-5-2",
        is_doubles=True
    )

    assert dialog.current_score == "7-5-2"
    assert dialog.is_doubles is True
    assert dialog.result is None

    print("  ✓ EditScoreDialog instantiated successfully")
    print(f"  ✓ Current score: {dialog.current_score}")


def test_force_sideout_dialog():
    """Test ForceSideOutDialog instantiation."""
    print("\nTesting ForceSideOutDialog...")

    dialog = ForceSideOutDialog(
        current_server_info="Team 1 - Server 2",
        next_server_info="Team 2 - Server 1",
        current_score="7-5-2",
        is_doubles=True
    )

    assert dialog.current_server_info == "Team 1 - Server 2"
    assert dialog.next_server_info == "Team 2 - Server 1"
    assert dialog.current_score == "7-5-2"
    assert dialog.result is None

    print("  ✓ ForceSideOutDialog instantiated successfully")
    print(f"  ✓ Current server: {dialog.current_server_info}")
    print(f"  ✓ Next server: {dialog.next_server_info}")


def test_add_comment_dialog():
    """Test AddCommentDialog instantiation."""
    print("\nTesting AddCommentDialog...")

    dialog = AddCommentDialog(
        timestamp=123.45
    )

    assert dialog.timestamp == 123.45
    assert dialog.result is None

    print("  ✓ AddCommentDialog instantiated successfully")
    print(f"  ✓ Timestamp: {dialog.timestamp}")


def test_result_dataclasses():
    """Test result dataclass construction."""
    print("\nTesting result dataclasses...")

    # EditScoreResult
    edit_result = EditScoreResult(
        new_score="8-5-2",
        comment="Corrected missed point"
    )
    assert edit_result.new_score == "8-5-2"
    assert edit_result.comment == "Corrected missed point"
    print("  ✓ EditScoreResult constructed successfully")

    # ForceSideOutResult
    sideout_result = ForceSideOutResult(
        new_score="7-6-1",
        comment="Missed side-out during fast play"
    )
    assert sideout_result.new_score == "7-6-1"
    assert sideout_result.comment == "Missed side-out during fast play"
    print("  ✓ ForceSideOutResult constructed successfully")

    # AddCommentResult
    comment_result = AddCommentResult(
        timestamp=123.45,
        comment="Amazing rally!",
        duration=5.0
    )
    assert comment_result.timestamp == 123.45
    assert comment_result.comment == "Amazing rally!"
    assert comment_result.duration == 5.0
    print("  ✓ AddCommentResult constructed successfully")


def main():
    """Run all dialog tests."""
    print("=" * 60)
    print("Intervention Dialogs Smoke Test")
    print("=" * 60)

    # QApplication is required for any PyQt6 widget instantiation
    app = QApplication(sys.argv)

    try:
        test_edit_score_dialog()
        test_force_sideout_dialog()
        test_add_comment_dialog()
        test_result_dataclasses()

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

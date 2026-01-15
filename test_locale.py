#!/usr/bin/env python3
"""Minimal test to debug MPV locale issue."""

import sys
print("=== LOCALE DEBUG TEST ===", file=sys.stderr)

# Step 1: Check initial locale
import ctypes
libc = ctypes.CDLL("libc.so.6")
libc.setlocale.restype = ctypes.c_char_p

current = libc.setlocale(1, None)  # LC_NUMERIC = 1
print(f"1. Initial LC_NUMERIC: {current}", file=sys.stderr)

# Step 2: Set locale via ctypes
result = libc.setlocale(1, b"C")
print(f"2. After ctypes setlocale(1, 'C'): {result}", file=sys.stderr)

# Step 3: Verify it stuck
current = libc.setlocale(1, None)
print(f"3. Verify LC_NUMERIC: {current}", file=sys.stderr)

# Step 4: Try LC_ALL = 0
result_all = libc.setlocale(0, b"C")
print(f"4. After setlocale(LC_ALL=0, 'C'): {result_all}", file=sys.stderr)

current = libc.setlocale(1, None)
print(f"5. LC_NUMERIC after LC_ALL: {current}", file=sys.stderr)

# Step 5: Now import mpv
print("6. About to import mpv...", file=sys.stderr)
try:
    import mpv
    print("7. mpv imported successfully!", file=sys.stderr)
except Exception as e:
    print(f"7. mpv import failed: {e}", file=sys.stderr)
    sys.exit(1)

# Step 6: Check locale after import
current = libc.setlocale(1, None)
print(f"8. LC_NUMERIC after mpv import: {current}", file=sys.stderr)

# Step 7: Try creating MPV instance
print("9. About to create mpv.MPV()...", file=sys.stderr)

# Set locale one more time right before
libc.setlocale(0, b"C")
libc.setlocale(1, b"C")
current = libc.setlocale(1, None)
print(f"10. LC_NUMERIC right before MPV(): {current}", file=sys.stderr)

try:
    player = mpv.MPV()
    print("11. mpv.MPV() created successfully!", file=sys.stderr)
    player.terminate()
except Exception as e:
    print(f"11. mpv.MPV() failed: {e}", file=sys.stderr)

print("=== TEST COMPLETE ===", file=sys.stderr)

"""Ball-tracking-based rally-winner detection (Phase 1 feasibility audit).

This package implements the autonomous Phase-1 audit agreed in
``docs/auto-editor-plan/winner-detection-consensus-plan.md`` and hardened by the
GPT-5.5 review in ``docs/auto-editor-plan/audit/``:

- ``corpus``   — enumerate training-ready labeled rallies + date/court grouping + dev sample
- ``detect``   — full-resolution ball candidate detection (color ∪ motion ∪ blob)
- ``track``    — top-K beam/DAG trajectory association over the terminal window
- ``features`` — strictly-geometric features from a recovered track + court homography
- ``audit``    — orchestrate extract→detect→track→feature with per-rally disk caching
- ``evaluate`` — date/video-grouped CV + false-positive controls + accuracy/coverage report

It is Qt-free and decodes video only via the system ffmpeg CLI (see
``ml.video_features``), per the project's in-process-decoder ban.
"""

"""Build a sanitized environment for ffmpeg/ffprobe subprocesses.

Wheels like opencv-python-headless bundle their own copies of
libavformat/libavcodec inside ``site-packages/<pkg>.libs/`` and prepend
that directory to ``LD_LIBRARY_PATH`` at import time (see
``cv2/__init__.py``).  When we then ``subprocess.run(["ffprobe", ...])``
the child inherits that ``LD_LIBRARY_PATH`` and the system ffprobe (built
against a newer libavformat) loads the older bundled copy, producing
``undefined symbol: av_mime_codec_str`` and similar ABI errors.

This helper returns an ``os.environ`` copy with site-packages entries
filtered out of ``LD_LIBRARY_PATH`` so subprocess children resolve to the
system shared libraries.
"""
import os


def clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    ld = env.get("LD_LIBRARY_PATH", "")
    if not ld:
        return env
    cleaned = [p for p in ld.split(":") if p and "site-packages" not in p]
    if cleaned:
        env["LD_LIBRARY_PATH"] = ":".join(cleaned)
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env

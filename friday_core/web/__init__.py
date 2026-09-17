"""
F.R.I.D.A.Y. 2.0 - Safe Web Package
SSRF-protected fetching, sanitization, rate limiting, and prompt injection defense.
"""

from friday_core.web.fetcher import (
    web_fetch,
    is_safe_url,
    clean_html_to_text,
    QUARANTINE_DIR,
    PROMPT_DELIMITER_START,
    PROMPT_DELIMITER_END
)
from friday_core.web.youtube import (
    resolve_youtube_video,
    resolve_youtube_video_async
)

__all__ = [
    "web_fetch",
    "is_safe_url",
    "clean_html_to_text",
    "QUARANTINE_DIR",
    "PROMPT_DELIMITER_START",
    "PROMPT_DELIMITER_END",
    "resolve_youtube_video",
    "resolve_youtube_video_async"
]

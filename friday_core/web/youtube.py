"""
F.R.I.D.A.Y. 2.0 - Direct YouTube Video Resolution Service
Resolves direct video URLs for instant YouTube playback without requiring API keys.
"""

import re
import urllib.parse
import urllib.request
import asyncio
import logging
from typing import Tuple, Optional

logger = logging.getLogger("FRIDAY.YouTube")

YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query={}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def resolve_youtube_video(query: str, timeout: float = 3.5) -> Tuple[str, str]:
    """
    Searches YouTube for a query and resolves the top matching video playback URL.
    Returns (url, display_title).
    If resolution fails, gracefully falls back to the YouTube search results URL.
    """
    clean_q = query.strip()
    fallback_url = YOUTUBE_SEARCH_URL.format(urllib.parse.quote(clean_q))

    try:
        req = urllib.request.Request(
            fallback_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

            # Look for video IDs in watch?v= format or "videoId":"..."
            matches = re.findall(r"(?:watch\?v=|/shorts/|\"videoId\":\"|/embed/)([a-zA-Z0-9_-]{11})", html)
            if matches:
                # Deduplicate preserving order
                unique_ids = []
                for vid in matches:
                    if vid not in unique_ids:
                        unique_ids.append(vid)

                if unique_ids:
                    top_id = unique_ids[0]
                    video_url = f"https://www.youtube.com/watch?v={top_id}&autoplay=1"

                    # Try to extract the video title
                    title_match = re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', html)
                    video_title = title_match.group(1) if title_match else clean_q

                    logger.info(f"Resolved top YouTube video for '{clean_q}': {video_url} ({video_title})")
                    return video_url, video_title

    except Exception as ex:
        logger.debug(f"Direct YouTube video extraction note for '{clean_q}': {ex}")

    return fallback_url, clean_q


async def resolve_youtube_video_async(query: str, timeout: float = 3.5) -> Tuple[str, str]:
    """Asynchronously resolves the top YouTube video URL."""
    return await asyncio.to_thread(resolve_youtube_video, query, timeout)

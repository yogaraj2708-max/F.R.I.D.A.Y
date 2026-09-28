"""
F.R.I.D.A.Y. 3.0 — Browser Session Driver
Executes HTTP/DOM-level web navigation, parsing, form interaction, and file downloads.
Extracts structured InteractiveElement nodes via lxml.html.
"""

import os
import re
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
import httpx
import lxml.html

from friday_core.browser.models import BrowserState, InteractiveElement

logger = logging.getLogger("FRIDAY.BrowserSession")


class BrowserSession:
    """
    Session-level browser driver with robust HTML parsing and element extraction.
    """
    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 F.R.I.D.A.Y./3.0"
        )
        self.headers = {"User-Agent": self.user_agent}
        self.client = httpx.Client(headers=self.headers, follow_redirects=True, timeout=15.0)
        self.current_state: Optional[BrowserState] = None
        self._raw_html: str = ""

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass

    def navigate(self, url: str) -> BrowserState:
        """Navigates to a URL and parses the response into BrowserState."""
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme: {url}. Must be http or https.")

        resp = self.client.get(url)
        resp.raise_for_status()
        self._raw_html = resp.text
        self.current_state = self._parse_html(resp.text, str(resp.url), resp.status_code)
        return self.current_state

    def load_html(self, html_content: str, base_url: str = "http://localhost") -> BrowserState:
        """Loads static HTML string directly for testing and offline inspection."""
        self._raw_html = html_content
        self.current_state = self._parse_html(html_content, base_url, 200)
        return self.current_state

    def _parse_html(self, html: str, current_url: str, status_code: int) -> BrowserState:
        try:
            doc = lxml.html.fromstring(html)
        except Exception as e:
            logger.warning(f"HTML parsing fallback: {e}")
            doc = lxml.html.document_fromstring(html)

        # 1. Extract Title
        title_elems = doc.xpath("//title/text()")
        title = title_elems[0].strip() if title_elems else ""

        # 2. Extract Visible Text
        # Strip script and style tags
        for bad in doc.xpath("//script | //style | //noscript"):
            bad.getparent().remove(bad)
        text_content = doc.text_content().strip()
        # Collapse multiple whitespace
        text_content = re.sub(r"\s+", " ", text_content)

        # 3. Extract Interactive Elements (Links, Buttons, Inputs)
        interactive: List[InteractiveElement] = []

        # Links
        for a in doc.xpath("//a[@href]"):
            href = a.get("href")
            full_href = urljoin(current_url, href)
            link_text = a.text_content().strip()
            elem_id = a.get("id")
            selector = f"#{elem_id}" if elem_id else f"a[href='{href}']"
            interactive.append(InteractiveElement(
                tag="a",
                text=link_text,
                href=full_href,
                element_id=elem_id,
                name=a.get("name"),
                selector=selector
            ))

        # Buttons
        for b in doc.xpath("//button | //input[@type='button' or @type='submit']"):
            btn_text = b.text_content().strip() or b.get("value", "")
            elem_id = b.get("id")
            name = b.get("name")
            selector = f"#{elem_id}" if elem_id else (f"button[name='{name}']" if name else "button")
            interactive.append(InteractiveElement(
                tag=b.tag,
                text=btn_text,
                element_id=elem_id,
                name=name,
                selector=selector
            ))

        # Inputs
        for inp in doc.xpath("//input[not(@type='hidden') and not(@type='button') and not(@type='submit')] | //textarea"):
            elem_id = inp.get("id")
            name = inp.get("name")
            placeholder = inp.get("placeholder", "")
            selector = f"#{elem_id}" if elem_id else (f"input[name='{name}']" if name else inp.tag)
            interactive.append(InteractiveElement(
                tag=inp.tag,
                text=placeholder,
                element_id=elem_id,
                name=name,
                selector=selector
            ))

        return BrowserState(
            url=current_url,
            title=title,
            status_code=status_code,
            text_content=text_content,
            interactive_elements=interactive
        )

    def download_file(self, url: str, dest_path: str) -> Tuple[bool, int, str]:
        """
        Downloads a remote file with streaming verification.
        Returns (success, bytes_downloaded, error_message).
        """
        try:
            dest_dir = os.path.dirname(os.path.abspath(dest_path))
            os.makedirs(dest_dir, exist_ok=True)

            bytes_written = 0
            with self.client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)

            # Verification: postcondition check on disk
            if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
                return False, bytes_written, "Downloaded file is empty or missing from disk."

            return True, bytes_written, ""
        except Exception as e:
            logger.error(f"Download failed for '{url}': {e}")
            return False, 0, str(e)

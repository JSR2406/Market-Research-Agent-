"""
backend/core/web_research.py — real-time web search + scraping.

No API keys required. Two search backends are tried in order so a single
provider blocking us never takes the feature down:
  1. googlesearch-python (free scraper)
  2. DuckDuckGo HTML endpoint (free, scraped with httpx + BeautifulSoup)

Extracted page text is truncated to a fixed budget so it stays within LLM token
limits. All requests are time-boxed, send a browser User-Agent, and never follow
more than a handful of results — safe enough for advisory snippets.
"""
import asyncio
import logging
import re
from typing import List

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_HTML_TAG_CLEANER = re.compile(r"<[^>]+>")

# Hard caps so scraped content stays small and cheap.
_MAX_RESULTS = 4
_MAX_PAGE_CHARS = 1200
_TIMEOUT_SEC = 10.0


def _clean_text(html: str) -> str:
    """Strip scripts/styles/tags and collapse whitespace from a raw HTML page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True) if soup.get_text() else ""
    text = _HTML_TAG_CLEANER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _search_duckduckgo(query: str, max_results: int) -> List[str]:
    """Fallback search via DuckDuckGo HTML endpoint."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC, headers=_HEADERS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"[Web/DDG] search returned status {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            for a in soup.select("a.result__a")[:max_results]:
                href = a.get("href", "")
                # DDG wraps redirects in uddg=; strip it.
                match = re.search(r"uddg=([^&]+)", href)
                if match:
                    from urllib.parse import unquote
                    href = unquote(match.group(1))
                if href.startswith("http"):
                    results.append(href)
            return results
    except Exception as e:
        logger.warning(f"[Web/DDG] search failed: {e}")
        return []


async def search(query: str, max_results: int | None = None) -> List[str]:
    """Return a list of result URLs for the query using the first working backend."""
    max_results = max_results or _MAX_RESULTS

    # Backend 1: googlesearch-python (sync; run in an executor to stay async-safe).
    try:
        import googlesearch  # type: ignore

        loop = asyncio.get_event_loop()
        urls = await loop.run_in_executor(
            None, lambda: list(googlesearch.search(query, num_results=max_results))
        )
        urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        if urls:
            logger.info(f"[Web] google backend returned {len(urls)} result(s)")
            return urls[:max_results]
    except Exception as e:
        logger.warning(f"[Web] google backend failed: {e}")

    # Backend 2: DuckDuckGo HTML.
    urls = await _search_duckduckgo(query, max_results)
    if urls:
        logger.info(f"[Web] DuckDuckGo backend returned {len(urls)} result(s)")
        return urls[:max_results]

    logger.warning("[Web] both search backends returned nothing.")
    return []


async def fetch_text(url: str, max_chars: int = _MAX_PAGE_CHARS) -> str:
    """Fetch a page and return cleaned plain text (empty string on failure)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            text = _clean_text(resp.text)
            return " ".join(text.split())[:max_chars]
    except Exception as e:
        logger.info(f"[Web] fetch {url} failed: {e}")
        return ""


async def web_context(topic: str, max_results: int | None = None) -> str:
    """
    High-value snippet context for a research topic:
      • <URL>
      Common text snippet (truncated)

    Returns "" when nothing could be gathered — callers treat that as a no-op.
    """
    max_results = max_results or _MAX_RESULTS
    query = f"Indian MSME loan scheme {topic}"
    urls = await search(query, max_results)
    if not urls:
        return ""

    snippets: List[str] = []
    # Fetch up to 3 pages (frugal — scraping is slow, 2 is plenty for context).
    for url in urls[:2]:
        text = await fetch_text(url)
        if text:
            snippets.append(f"• {url}\n  {text}")
        else:
            snippets.append(f"• {url}\n  (page could not be read)")

    if not snippets:
        return ""
    header = f"Live web research for '{topic}' (auto-scraped, may be noisy):\n"
    return header + "\n\n".join(snippets)
"""
web_search.py — Token-Efficient Live Smartphone Search Module
Fetches concise, accurate launch dates, specs, and pricing via DuckDuckGo (`ddgs`)
with caching and strict snippet length budgets so Groq TPM limits are never strained.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests


@dataclass
class SearchSource:
    title: str
    url: str
    snippet: str


@dataclass
class SearchBundle:
    used_search: bool = False
    queries: List[str] = field(default_factory=list)
    sources: List[SearchSource] = field(default_factory=list)
    context_text: str = ""
    error: Optional[str] = None


# In-memory query cache to avoid redundant network hits in continuous chats
_QUERY_CACHE: Dict[str, List[SearchSource]] = {}

FOLLOW_UP_PRONOUNS = {
    "it", "its", "this", "that", "they", "them", "same", "phone", "device", "both",
}

SIMPLE_NO_SEARCH_PHRASES = (
    "summarize", "shorter", "explain", "which one should i", "thanks", "thank you",
    "in short", "pros and cons", "tldr",
)


def _trim(text: str, max_len: int = 175) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rsplit(" ", 1)[0] + "…"


def should_skip_web_search(user_message: str, has_active_phone: bool) -> bool:
    """Skip web search on pure conversational follow-ups when specs are already loaded."""
    if not has_active_phone:
        return False
    low = user_message.strip().lower()
    if any(p in low for p in SIMPLE_NO_SEARCH_PHRASES) and len(low.split()) <= 10:
        return True
    return False


def build_phone_queries(
    user_message: str,
    active_phone: Optional[str] = None,
    compare_phone: Optional[str] = None,
) -> List[str]:
    """Build 1–2 lean search queries tailored to single lookup, follow-up, or comparison."""
    msg = " ".join(user_message.strip().split())
    if not msg:
        return []

    low = msg.lower()

    # Explicit A vs B comparison pattern ("X vs Y" or "compare X and/with Y")
    vs_match = re.split(r"\b(?:vs\.?|versus|compared?\s+(?:with|to))\b", msg, maxsplit=1, flags=re.I)
    if len(vs_match) == 2:
        left_part = re.sub(r"^(?:compare|between)\s+", "", vs_match[0], flags=re.I).strip(" ?.,")
        right_part = vs_match[1].strip(" ?.,")
        # If left side is empty or a pronoun ("compare it with OnePlus 13"), substitute active_phone
        if (not left_part or left_part.lower() in FOLLOW_UP_PRONOUNS) and active_phone:
            left_part = active_phone
        if left_part and right_part:
            return [
                f"{left_part} specifications launch date price gsmarena",
                f"{right_part} specifications launch date price gsmarena",
            ]

    tokens = set(re.findall(r"[a-z0-9\+]+", low))
    is_followup = bool(
        active_phone
        and active_phone.lower() not in low
        and ((tokens & FOLLOW_UP_PRONOUNS) or len(tokens) <= 7)
    )

    if is_followup and active_phone:
        if compare_phone and ("both" in tokens or "better" in tokens or "winner" in tokens):
            return [f"{active_phone} vs {compare_phone} review comparison"]
        return [f"{active_phone} {msg} review specs"]

    # Discovery / budget query
    if any(k in low for k in ("best ", "suggest", "recommend", "under ", "budget")):
        return [f"{msg} smartphone 2025 2026 specs price"]

    # Standard single-phone lookup (single concise query + optional review query)
    return [
        f"{msg} full specifications launch date price gsmarena",
    ]


def _ddgs_text_search(query: str, max_results: int = 4) -> List[SearchSource]:
    if query in _QUERY_CACHE:
        return _QUERY_CACHE[query][:max_results]

    ddgs_cls = None
    try:
        from ddgs import DDGS as _DDGS
        ddgs_cls = _DDGS
    except ImportError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from duckduckgo_search import DDGS as _DDGS  # type: ignore
            ddgs_cls = _DDGS

    raw_items = list(ddgs_cls().text(query, max_results=max_results) or [])
    sources: List[SearchSource] = []
    for item in raw_items:
        title = _trim(item.get("title") or "", 90)
        url = (item.get("href") or item.get("url") or "").strip()
        snippet = _trim(item.get("body") or item.get("snippet") or "", 175)
        if title or snippet:
            sources.append(SearchSource(title=title, url=url, snippet=snippet))

    if sources:
        _QUERY_CACHE[query] = sources
    return sources


def _html_fallback_search(query: str, max_results: int = 4) -> List[SearchSource]:
    if query in _QUERY_CACHE:
        return _QUERY_CACHE[query][:max_results]

    resp = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        },
        timeout=7,
    )
    resp.raise_for_status()
    page = resp.text

    titles = re.findall(r'<a[^>]*class="result__a"[^>]* href="([^"]+)"[^>]*>(.*?)</a>', page, flags=re.S)
    snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', page, flags=re.S)

    results: List[SearchSource] = []
    for idx, (raw_href, raw_title) in enumerate(titles[:max_results]):
        clean_title = _trim(html.unescape(re.sub(r"<[^>]+>", "", raw_title)), 90)
        clean_snippet = ""
        if idx < len(snippets):
            clean_snippet = _trim(html.unescape(re.sub(r"<[^>]+>", "", snippets[idx])), 175)

        real_url = raw_href
        parsed = urllib.parse.urlparse(raw_href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            real_url = qs["uddg"][0]

        results.append(SearchSource(title=clean_title, url=real_url, snippet=clean_snippet))

    if results:
        _QUERY_CACHE[query] = results
    return results


def search_phone_facts(
    user_message: str,
    active_phone: Optional[str] = None,
    compare_phone: Optional[str] = None,
    max_total_results: int = 4,
) -> SearchBundle:
    """Fetch compact web facts (~180–240 tokens max) so API limits stay completely safe."""
    if should_skip_web_search(user_message, has_active_phone=bool(active_phone)):
        return SearchBundle(used_search=False)

    queries = build_phone_queries(user_message, active_phone, compare_phone)
    if not queries:
        return SearchBundle(used_search=False)

    collected: List[SearchSource] = []
    seen_urls: set[str] = set()
    last_error: Optional[str] = None
    per_q = 2 if len(queries) > 1 else max_total_results

    for q in queries:
        batch: List[SearchSource] = []
        try:
            batch = _ddgs_text_search(q, max_results=per_q)
        except Exception as exc:
            last_error = str(exc)
            try:
                batch = _html_fallback_search(q, max_results=per_q)
            except Exception as fb_exc:
                last_error = f"{last_error} | {fb_exc}"

        for src in batch:
            key = src.url or src.title
            if key and key not in seen_urls:
                seen_urls.add(key)
                collected.append(src)
                if len(collected) >= max_total_results:
                    break
        if len(collected) >= max_total_results:
            break

    if not collected:
        return SearchBundle(used_search=False, queries=queries, error=last_error)

    lines = ["WEB FACTS:"]
    for i, src in enumerate(collected, start=1):
        lines.append(f"[{i}] {src.title}: {src.snippet}")

    return SearchBundle(
        used_search=True,
        queries=queries,
        sources=collected,
        context_text="\n".join(lines),
    )

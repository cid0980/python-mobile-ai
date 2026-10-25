from __future__ import annotations

import html
import re
import urllib.parse
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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


_QUERY_CACHE: Dict[str, List[SearchSource]] = {}
_IMAGE_CACHE: Dict[str, Tuple[bytes, str]] = {}

GREETINGS_AND_CHITCHAT = {
    "hi", "hello", "hey", "yo", "hola", "namaste", "sup",
    "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "thx", "ok", "okay", "cool", "nice", "great",
    "help", "who are you", "what can you do", "how are you", "bye",
}

FOLLOW_UP_PRONOUNS = {
    "it", "its", "this", "that", "they", "them", "same", "phone", "device", "both",
}

PURE_CONVERSATIONAL_FOLLOWUPS = (
    "summarize", "shorter", "explain", "which one should i",
    "in short", "tldr", "for college", "for my mom", "for my dad",
)

BRAND_PREFIX_MAP = {
    "iphone": "apple",
    "galaxy": "samsung",
    "pixel": "google",
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "iqoo": "vivo",
    "xperia": "sony",
    "moto": "motorola",
    "razr": "motorola",
    "rog": "asus",
    "zenfone": "asus",
}

SAMSUNG_MODEL_SUFFIX = {
    "samsung-galaxy-s25-ultra": ["samsung-galaxy-s25-ultra-sm-s938", "samsung-galaxy-s25-ultra"],
    "samsung-galaxy-s25-plus": ["samsung-galaxy-s25-plus-sm-s936", "samsung-galaxy-s25+"],
    "samsung-galaxy-s25": ["samsung-galaxy-s25-sm-s931", "samsung-galaxy-s25"],
    "samsung-galaxy-s24-ultra": ["samsung-galaxy-s24-ultra-5g-sm-s928", "samsung-galaxy-s24-ultra"],
    "samsung-galaxy-s24-plus": ["samsung-galaxy-s24-plus-5g-sm-s926"],
    "samsung-galaxy-s24": ["samsung-galaxy-s24-5g-sm-s921"],
    "samsung-galaxy-s23-ultra": ["samsung-galaxy-s23-ultra-5g"],
}

FALLBACK_PHONE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="280" viewBox="0 0 220 280">'
    '<rect width="220" height="280" fill="#171717"/>'
    '<rect x="52" y="22" width="116" height="236" rx="18" fill="#06110c" stroke="#2d3a33" stroke-width="2"/>'
    '<circle cx="110" cy="36" r="3" fill="#2d3a33"/>'
    '<rect x="92" y="244" width="36" height="3" rx="1.5" fill="#a31c1b"/>'
    '</svg>'
).encode("utf-8")


def _trim(text: str, max_len: int = 230) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rsplit(" ", 1)[0] + "…"


def should_skip_web_search(user_message: str, has_active_phone: bool) -> bool:
    cleaned = re.sub(r"[!?.,:;]+", "", user_message.strip().lower())
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return True
    if cleaned in GREETINGS_AND_CHITCHAT:
        return True
    words = cleaned.split()
    if len(words) <= 3 and words[0] in {"hi", "hello", "hey", "thanks", "thank", "ok", "okay"}:
        return True
    if has_active_phone and any(p in cleaned for p in PURE_CONVERSATIONAL_FOLLOWUPS) and len(words) <= 10:
        return True
    return False


def build_phone_queries(
    user_message: str,
    active_phone: Optional[str] = None,
    compare_phone: Optional[str] = None,
) -> List[str]:
    msg = " ".join(user_message.strip().split())
    if not msg:
        return []

    low = msg.lower()

    vs_match = re.split(
        r"\b(?:vs\.?|versus|compared?\s+(?:with|to|and))\b", msg, maxsplit=1, flags=re.I
    )
    if len(vs_match) == 2:
        left_part = re.sub(r"^(?:compare|between)\s+", "", vs_match[0], flags=re.I).strip(" ?.,")
        right_part = vs_match[1].strip(" ?.,")
        if (not left_part or left_part.lower() in FOLLOW_UP_PRONOUNS) and active_phone:
            left_part = active_phone
        if left_part and right_part:
            return [
                f"{left_part} full phone specifications launch date price gsmarena",
                f"{right_part} full phone specifications launch date price gsmarena",
            ]

    tokens = set(re.findall(r"[a-z0-9\+]+", low))
    is_followup = bool(
        active_phone
        and active_phone.lower() not in low
        and ((tokens & FOLLOW_UP_PRONOUNS) or len(tokens) <= 5)
        and any(w in low for w in ("camera", "battery", "gaming", "display", "charge", "charging", "price", "worth", "buy", "update", "heating", "speaker"))
    )

    if is_followup and active_phone:
        if compare_phone and ("both" in tokens or "better" in tokens or "winner" in tokens):
            return [f"{active_phone} vs {compare_phone} comparison review"]
        return [f"{active_phone} {msg} smartphone review specs"]

    if any(k in low for k in ("best ", "suggest", "recommend", "under ", "budget")):
        return [f"{msg} smartphone 2025 2026 specs price"]

    return [f"{msg} full phone specifications launch date price gsmarena"]


def _get_ddgs_cls():
    try:
        from ddgs import DDGS as _DDGS
        return _DDGS
    except ImportError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from duckduckgo_search import DDGS as _DDGS
            return _DDGS


def _ddgs_text_search(query: str, max_results: int = 4) -> List[SearchSource]:
    if query in _QUERY_CACHE:
        return _QUERY_CACHE[query][:max_results]

    ddgs_cls = _get_ddgs_cls()
    raw_items = list(ddgs_cls().text(query, max_results=max_results) or [])
    sources: List[SearchSource] = []
    for item in raw_items:
        title = _trim(item.get("title") or "", 90)
        url = (item.get("href") or item.get("url") or "").strip()
        snippet = _trim(item.get("body") or item.get("snippet") or "", 230)
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
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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
            clean_snippet = _trim(html.unescape(re.sub(r"<[^>]+>", "", snippets[idx])), 230)

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

    lines = ["WEB SEARCH REFERENCE SNIPPETS:"]
    for i, src in enumerate(collected, start=1):
        lines.append(f"[{i}] {src.title}: {src.snippet}")

    return SearchBundle(
        used_search=True,
        queries=queries,
        sources=collected,
        context_text="\n".join(lines),
    )


def _build_gsmarena_slugs(phone_name: str, brand: str = "") -> List[str]:
    raw = phone_name.lower().strip()
    raw = raw.replace("+", " plus ")
    raw = re.sub(r"[()]", " ", raw)
    raw = " ".join(raw.split())

    b = brand.lower().strip()
    if not b:
        for kw, mapped in BRAND_PREFIX_MAP.items():
            if kw in raw:
                b = mapped
                break

    full = raw if (b and raw.startswith(b)) else f"{b} {raw}".strip()
    slug = re.sub(r"[^a-z0-9]+", "-", full).strip("-")
    slug_no_5g = re.sub(r"-5g$", "", slug)

    candidates: List[str] = []
    if slug in SAMSUNG_MODEL_SUFFIX:
        candidates.extend(SAMSUNG_MODEL_SUFFIX[slug])
    if slug_no_5g in SAMSUNG_MODEL_SUFFIX:
        candidates.extend(SAMSUNG_MODEL_SUFFIX[slug_no_5g])

    candidates.extend([
        slug,
        f"{slug}-",
        f"{slug}-5g",
        f"{slug}-5g-",
        slug_no_5g,
        f"{slug_no_5g}-",
    ])
    return list(dict.fromkeys(c for c in candidates if c))


def fetch_phone_image_bytes(phone_name: str, brand: str = "") -> Tuple[bytes, str]:
    cache_key = f"{brand.lower().strip()}::{phone_name.lower().strip()}"
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    })

    for slug in _build_gsmarena_slugs(phone_name, brand):
        url = f"https://fdn2.gsmarena.com/vv/bigpic/{slug}.jpg"
        try:
            resp = sess.get(url, timeout=3.5)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image/") and len(resp.content) > 2200:
                result = (resp.content, ctype.split(";")[0])
                _IMAGE_CACHE[cache_key] = result
                return result
        except Exception:
            continue

    try:
        ddgs_cls = _get_ddgs_cls()
        raw_imgs = list(ddgs_cls().images(f"{phone_name} gsmarena bigpic", max_results=10) or [])
        if not raw_imgs:
            raw_imgs = list(ddgs_cls().images(f"{phone_name} smartphone official", max_results=8) or [])

        def _img_priority(item: dict) -> int:
            u = item.get("image", "").lower()
            if "fdn2.gsmarena.com/vv/bigpic/" in u:
                return 0
            if "fdn2.gsmarena.com/vv/pics/" in u:
                return 1
            if "gsmarena.com" in u:
                return 2
            return 3

        raw_imgs.sort(key=_img_priority)
        for im in raw_imgs[:6]:
            img_url = (im.get("image") or "").strip()
            if not img_url.startswith("http"):
                continue
            try:
                resp = sess.get(img_url, timeout=4.0)
                ctype = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ctype.startswith("image/") and len(resp.content) > 2500:
                    result = (resp.content, ctype.split(";")[0])
                    _IMAGE_CACHE[cache_key] = result
                    return result
            except Exception:
                continue
    except Exception:
        pass

    return (FALLBACK_PHONE_SVG, "image/svg+xml")

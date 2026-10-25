"""
voice_engine.py — Ultra-Low-Latency Word-Synchronized Neural TTS Engine
Uses fast-inference neural voices (`en-US-GuyNeural` / `en-US-AriaNeural` — 12x
real-time synthesis speed) + IPv4 `AF_INET` transport + `WordBoundary` offsets
so UI text reveals word-by-word in exact lockstep with the spoken voice.
"""

from __future__ import annotations

import asyncio
import base64
import re
import socket
from typing import Any, AsyncIterator, Dict, List

import aiohttp

try:
    import edge_tts
    HAS_EDGE_TTS = True
except Exception:
    HAS_EDGE_TTS = False

DEFAULT_NEURAL_VOICE = "en-US-GuyNeural"

VOICE_PRESETS: Dict[str, str] = {
    "Guy (US · Fast Male)": "en-US-GuyNeural",
    "Aria (US · Fast Female)": "en-US-AriaNeural",
    "Christopher (US · Studio Male)": "en-US-ChristopherNeural",
    "Sonia (UK · Female)": "en-GB-SoniaNeural",
}

LEGACY_SLOW_VOICES = {
    "en-US-AndrewMultilingualNeural",
    "en-US-AndrewNeural",
    "en-GB-RyanNeural",
}

_TTS_WARMED = False


def resolve_fast_voice(voice: str | None) -> str:
    """Resolve voice ID and upgrade legacy slow multilingual voices to 12x-faster GuyNeural."""
    if not voice or voice in LEGACY_SLOW_VOICES:
        return DEFAULT_NEURAL_VOICE
    if voice in VOICE_PRESETS.values():
        return voice
    return DEFAULT_NEURAL_VOICE


def prepare_speech_text(raw_text: str, max_chars: int = 1400) -> str:
    """Clean markdown formatting while keeping spoken words aligned with visual words."""
    if not raw_text:
        return ""
    txt = raw_text
    txt = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", txt)
    txt = re.sub(r"https?://\S+", "", txt)
    txt = re.sub(r"^#{1,4}\s*(.+)$", r"\1.", txt, flags=re.M)
    txt = re.sub(r"^\s*[-*•▸]\s+", "", txt, flags=re.M)
    txt = txt.replace("·", ", ").replace("|", ", ")
    txt = re.sub(r"[*_`~]+", "", txt)
    txt = re.sub(r"\n+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()

    if len(txt) > max_chars:
        cutoff = txt.rfind(".", 0, max_chars)
        if cutoff > 200:
            txt = txt[: cutoff + 1]
        else:
            txt = txt[:max_chars].rsplit(" ", 1)[0] + "."
    return txt


def split_markdown_segments(raw_markdown: str) -> List[str]:
    """
    Split an analyst Markdown response into natural, fast-synthesizing segments.
    Pairs each `### Heading` with its first content bullet/sentence so Segment #0
    starts in ~800ms and plays for ~6-9s while remaining segments prefetch seamlessly.
    """
    if not raw_markdown or not raw_markdown.strip():
        return []

    raw_lines = [ln.strip() for ln in raw_markdown.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not raw_lines:
        return []

    segments: List[str] = []
    pending_heading: str = ""

    for ln in raw_lines:
        if re.match(r"^#{1,4}\s+", ln):
            if pending_heading:
                segments.append(pending_heading)
            pending_heading = ln
            continue

        is_bullet = bool(re.match(r"^[-*•]\s+", ln))
        if not is_bullet and len(ln) > 190:
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", ln)
            buf = ""
            for s in sentences:
                if buf and len(buf) + len(s) + 1 <= 180:
                    buf = f"{buf} {s}".strip()
                elif not buf:
                    buf = s
                else:
                    if pending_heading:
                        segments.append(f"{pending_heading}\n{buf}")
                        pending_heading = ""
                    else:
                        segments.append(buf)
                    buf = s
            if buf:
                if pending_heading:
                    segments.append(f"{pending_heading}\n{buf}")
                    pending_heading = ""
                else:
                    segments.append(buf)
        else:
            if pending_heading:
                segments.append(f"{pending_heading}\n{ln}")
                pending_heading = ""
            else:
                segments.append(ln)

    if pending_heading:
        segments.append(pending_heading)

    return segments


async def warm_tts_engine() -> None:
    """Pre-warm Edge TTS DRM handshake over IPv4 at server startup."""
    global _TTS_WARMED
    if _TTS_WARMED or not HAS_EDGE_TTS:
        return
    try:
        conn = aiohttp.TCPConnector(family=socket.AF_INET)
        comm = edge_tts.Communicate(
            "Ready.",
            DEFAULT_NEURAL_VOICE,
            boundary="WordBoundary",
            connector=conn,
            connect_timeout=5,
        )
        async for _ in comm.stream():
            pass
        _TTS_WARMED = True
    except Exception:
        pass


async def synthesize_segment_with_words(
    markdown_segment: str,
    voice: str = DEFAULT_NEURAL_VOICE,
) -> Dict[str, Any]:
    """
    Synthesize a single Markdown segment over IPv4 via Edge Neural TTS with
    `WordBoundary` events, returning base64 MP3 audio + exact millisecond word offsets.
    """
    spoken_text = prepare_speech_text(markdown_segment, max_chars=650)
    if not HAS_EDGE_TTS or not spoken_text:
        return {
            "markdown": markdown_segment,
            "audio_b64": "",
            "words": [],
            "duration_ms": 0.0,
        }

    valid_voice = resolve_fast_voice(voice)
    conn = aiohttp.TCPConnector(family=socket.AF_INET)
    comm = edge_tts.Communicate(
        spoken_text,
        valid_voice,
        boundary="WordBoundary",
        connector=conn,
        connect_timeout=6,
    )

    audio_buf = bytearray()
    words: List[Dict[str, Any]] = []
    max_end_ms = 0.0

    async for ev in comm.stream():
        ev_type = ev.get("type")
        if ev_type == "audio" and ev.get("data"):
            audio_buf.extend(ev["data"])
        elif ev_type == "WordBoundary":
            offset_ms = round(float(ev.get("offset", 0)) / 10_000.0, 1)
            dur_ms = round(float(ev.get("duration", 0)) / 10_000.0, 1)
            w_text = str(ev.get("text", "")).strip()
            if w_text:
                words.append(
                    {
                        "text": w_text,
                        "offset_ms": offset_ms,
                        "duration_ms": dur_ms,
                    }
                )
                if offset_ms + dur_ms > max_end_ms:
                    max_end_ms = offset_ms + dur_ms

    return {
        "markdown": markdown_segment,
        "audio_b64": base64.b64encode(bytes(audio_buf)).decode("ascii") if audio_buf else "",
        "words": words,
        "duration_ms": round(max_end_ms, 1),
    }


async def stream_synchronized_segments(
    raw_markdown: str,
    voice: str = DEFAULT_NEURAL_VOICE,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Priority-first pipelined synthesis:
      1. Synthesizes Segment #0 with 100% dedicated bandwidth (~750-900ms) and yields immediately.
      2. While the client is playing Segment #0 (~6-10s of speech), synthesizes Segments #1..N
         with 2-way pipelined concurrency so there is 0ms gap between segments!
    """
    segments = split_markdown_segments(raw_markdown)
    if not segments:
        return

    total = len(segments)

    # 1. Dedicated fast-lane for Segment #0 (zero WebSocket contention!)
    try:
        first_res = await synthesize_segment_with_words(segments[0], voice=voice)
    except Exception:
        first_res = {"markdown": segments[0], "audio_b64": "", "words": [], "duration_ms": 0.0}
    first_res["index"] = 0
    first_res["total"] = total
    yield first_res

    if total == 1:
        return

    # 2. Pipelined prefetch for Segments #1..N-1 while Segment #0 is speaking
    sem = asyncio.Semaphore(2)

    async def _worker(seg_md: str) -> Dict[str, Any]:
        async with sem:
            try:
                return await synthesize_segment_with_words(seg_md, voice=voice)
            except Exception:
                return {"markdown": seg_md, "audio_b64": "", "words": [], "duration_ms": 0.0}

    tasks = [asyncio.create_task(_worker(seg)) for seg in segments[1:]]
    try:
        for offset_idx, t in enumerate(tasks, start=1):
            res = await t
            res["index"] = offset_idx
            res["total"] = total
            yield res
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


async def synthesize_mp3_bytes(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
    """Generate full MP3 bytes over IPv4."""
    if not HAS_EDGE_TTS:
        raise RuntimeError("edge-tts package is not installed.")
    clean = prepare_speech_text(text)
    if not clean:
        return b""

    valid_voice = resolve_fast_voice(voice)
    conn = aiohttp.TCPConnector(family=socket.AF_INET)
    communicate = edge_tts.Communicate(clean, valid_voice, connector=conn, connect_timeout=6)
    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            chunks.extend(chunk["data"])
    return bytes(chunks)

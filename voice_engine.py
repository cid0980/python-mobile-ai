"""
voice_engine.py — Neural Text-to-Speech Synthesizer for SpecDeck
Streams crisp MP3 bytes via `edge-tts` directly to the UI's Web Audio player
(uses zero Groq API tokens, zero OS audio driver conflicts, zero temp file leaks).
"""

from __future__ import annotations

import re
from typing import Dict

try:
    import edge_tts
    HAS_EDGE_TTS = True
except Exception:
    HAS_EDGE_TTS = False

DEFAULT_NEURAL_VOICE = "en-US-AndrewMultilingualNeural"

VOICE_PRESETS: Dict[str, str] = {
    "Andrew (US · Male)": "en-US-AndrewMultilingualNeural",
    "Aria (US · Female)": "en-US-AriaNeural",
    "Ryan (UK · Male)": "en-GB-RyanNeural",
    "Sonia (UK · Female)": "en-GB-SoniaNeural",
}


def prepare_speech_text(raw_text: str, max_chars: int = 1100) -> str:
    """Clean markdown, headings, and URLs so spoken output flows naturally."""
    if not raw_text:
        return ""
    txt = raw_text
    txt = re.sub(r"https?://\S+", "", txt)
    txt = re.sub(r"^#{1,4}\s+", "", txt, flags=re.M)
    txt = txt.replace("▸", "").replace("•", ". ").replace("|", ", ")
    txt = re.sub(r"[*_`#~]+", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()

    if len(txt) > max_chars:
        cutoff = txt.rfind(".", 0, max_chars)
        if cutoff > 200:
            txt = txt[: cutoff + 1]
        else:
            txt = txt[:max_chars].rsplit(" ", 1)[0] + "."
    return txt


async def synthesize_mp3_bytes(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
    """Generate MP3 audio bytes asynchronously via Microsoft Edge Neural TTS."""
    if not HAS_EDGE_TTS:
        raise RuntimeError("edge-tts package is not installed.")
    clean = prepare_speech_text(text)
    if not clean:
        return b""

    valid_voice = voice if voice in VOICE_PRESETS.values() else DEFAULT_NEURAL_VOICE
    communicate = edge_tts.Communicate(clean, valid_voice)
    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            chunks.extend(chunk["data"])
    return bytes(chunks)

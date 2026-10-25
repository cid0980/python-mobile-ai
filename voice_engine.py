"""
voice_engine.py — Cross-Platform Neural Text-to-Speech Engine for SpecDeck AI
Uses free neural TTS (`edge-tts`) + `pygame.mixer` for smooth non-blocking playback
and instant stop controls on Windows & Linux (uses zero Groq API tokens).
Includes offline OS speech fallback if internet TTS is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

try:
    import pygame
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except Exception:
    HAS_EDGE_TTS = False

DEFAULT_NEURAL_VOICE = "en-US-AndrewMultilingualNeural"

VOICE_PRESETS = {
    "Andrew (US · Male)": "en-US-AndrewMultilingualNeural",
    "Aria (US · Female)": "en-US-AriaNeural",
    "Ryan (UK · Male)": "en-GB-RyanNeural",
    "Sonia (UK · Female)": "en-GB-SoniaNeural",
}


def prepare_speech_text(raw_text: str, max_chars: int = 1200) -> str:
    """Clean UI symbols, bullets, and URLs so spoken output sounds natural."""
    if not raw_text:
        return ""
    txt = raw_text
    # Remove URLs
    txt = re.sub(r"https?://\S+", "", txt)
    # Replace decorative bullets/arrows with natural sentence pauses
    txt = txt.replace("▸", "").replace("•", ". ").replace("|", ", ")
    txt = re.sub(r"[*_`#]+", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()

    if len(txt) > max_chars:
        cutoff = txt.rfind(".", 0, max_chars)
        if cutoff > 200:
            txt = txt[: cutoff + 1]
        else:
            txt = txt[:max_chars].rsplit(" ", 1)[0] + "."
    return txt


class VoiceOutputEngine:
    """Thread-safe background TTS synthesizer and audio player."""

    def __init__(self, voice: str = DEFAULT_NEURAL_VOICE) -> None:
        self.voice = voice
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._mixer_ready = False
        self._fallback_proc: Optional[subprocess.Popen] = None
        self._current_temp_mp3: Optional[Path] = None
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def _ensure_mixer(self) -> bool:
        if self._mixer_ready:
            return True
        if not HAS_PYGAME:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._mixer_ready = True
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Immediately halt any active speech synthesis or playback."""
        self._stop_event.set()
        try:
            if self._mixer_ready and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
        except Exception:
            pass

        with self._lock:
            if self._fallback_proc and self._fallback_proc.poll() is None:
                try:
                    self._fallback_proc.terminate()
                except Exception:
                    pass
            self._fallback_proc = None

        self._cleanup_temp_file()
        self._speaking = False

    def speak(
        self,
        text: str,
        on_state_change: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Synthesize and play `text` asynchronously on a background thread."""
        clean = prepare_speech_text(text)
        if not clean:
            return

        # Stop any currently playing speech first
        self.stop()
        self._stop_event.clear()

        def _worker() -> None:
            self._speaking = True
            if on_state_change:
                on_state_change(True, "Generating voice audio...")

            played_neural = False
            if HAS_EDGE_TTS and self._ensure_mixer():
                try:
                    played_neural = self._play_neural_tts(clean, on_state_change)
                except Exception:
                    played_neural = False

            if not played_neural and not self._stop_event.is_set():
                self._play_offline_fallback(clean, on_state_change)

            self._cleanup_temp_file()
            self._speaking = False
            if on_state_change:
                on_state_change(False, "")

        threading.Thread(target=_worker, daemon=True).start()

    def _play_neural_tts(
        self,
        clean_text: str,
        on_state_change: Optional[Callable[[bool, str], None]],
    ) -> bool:
        fd, tmp_name = tempfile.mkstemp(prefix="specdeck_tts_", suffix=".mp3")
        os.close(fd)
        tmp_path = Path(tmp_name)
        self._current_temp_mp3 = tmp_path

        async def _synthesize() -> None:
            comm = edge_tts.Communicate(clean_text, self.voice)
            await comm.save(str(tmp_path))

        asyncio.run(_synthesize())

        if self._stop_event.is_set() or not tmp_path.exists() or tmp_path.stat().st_size == 0:
            return False

        if on_state_change:
            on_state_change(True, "Speaking...")

        pygame.mixer.music.load(str(tmp_path))
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if self._stop_event.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.08)

        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        return True

    def _play_offline_fallback(
        self,
        clean_text: str,
        on_state_change: Optional[Callable[[bool, str], None]],
    ) -> None:
        """Offline native OS speech fallback for Windows SAPI and Linux espeak/spd-say."""
        if on_state_change:
            on_state_change(True, "Speaking (offline voice)...")

        cmd = None
        if os.name == "nt":
            safe_ps = clean_text.replace("'", "''")
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{safe_ps}')"
            )
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
        else:
            for bin_name, flag in (("espeak-ng", None), ("espeak", None), ("spd-say", "--wait")):
                if shutil.which(bin_name):
                    cmd = [bin_name, flag, clean_text] if flag else [bin_name, clean_text]
                    break

        if not cmd:
            return

        try:
            with self._lock:
                self._fallback_proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            while self._fallback_proc and self._fallback_proc.poll() is None:
                if self._stop_event.is_set():
                    self._fallback_proc.terminate()
                    break
                time.sleep(0.1)
        except Exception:
            pass

    def _cleanup_temp_file(self) -> None:
        if self._current_temp_mp3 and self._current_temp_mp3.exists():
            try:
                self._current_temp_mp3.unlink()
            except Exception:
                pass
        self._current_temp_mp3 = None

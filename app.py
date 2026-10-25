"""
app.py — SpecDeck Hardware Intelligence Studio
Backend API (FastAPI + Groq + Live Web Grounding + Neural Edge-TTS)
+ Standalone Native Desktop App Window Launcher (Windows & Linux).
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel

from ai_engine import (
    DEFAULT_MODELS,
    DEMO_COMPARE_CARD,
    DEMO_PHONE_CARD,
    PhoneCardData,
    SpecDeckAssistant,
    fetch_groq_models,
    get_saved_api_key,
    load_env_setting,
    save_api_key_to_env,
)
from autostart_manager import disable_autostart, enable_autostart, is_autostart_enabled
from voice_engine import DEFAULT_NEURAL_VOICE, VOICE_PRESETS, synthesize_mp3_bytes

APP_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = APP_DIR / "static" / "index.html"

app = FastAPI(title="SpecDeck Hardware Intelligence", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AppRuntimeState:
    def __init__(self) -> None:
        saved_key = get_saved_api_key()
        saved_model = load_env_setting("GROQ_MODEL", DEFAULT_MODELS[0]) or DEFAULT_MODELS[0]
        self.assistant = SpecDeckAssistant(api_key=saved_key, model=saved_model)
        self.voice_id: str = load_env_setting("VOICE_ID", DEFAULT_NEURAL_VOICE) or DEFAULT_NEURAL_VOICE
        self.live_web: bool = load_env_setting("LIVE_WEB_SEARCH", "1") != "0"
        self.auto_voice: bool = load_env_setting("AUTO_VOICE", "0") == "1"
        self.models: List[str] = list(DEFAULT_MODELS)
        if saved_model not in self.models:
            self.models.insert(0, saved_model)


STATE = AppRuntimeState()


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    use_web_search: bool = True


class VerifyKeyRequest(BaseModel):
    api_key: Optional[str] = ""


class SettingsUpdateRequest(BaseModel):
    api_key: Optional[str] = ""
    model: str = DEFAULT_MODELS[0]
    voice_id: str = DEFAULT_NEURAL_VOICE
    live_web: bool = True
    auto_voice: bool = False
    autostart: bool = False


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_ui() -> HTMLResponse:
    if not INDEX_HTML_PATH.exists():
        raise HTTPException(status_code=500, detail="static/index.html missing.")
    return HTMLResponse(INDEX_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/api/state")
def get_state() -> Dict[str, Any]:
    return {
        "has_api_key": bool(STATE.assistant.api_key.strip()),
        "model": STATE.assistant.model,
        "models": STATE.models,
        "voices": VOICE_PRESETS,
        "voice_id": STATE.voice_id,
        "live_web": STATE.live_web,
        "auto_voice": STATE.auto_voice,
        "autostart": is_autostart_enabled(),
        "demo_primary": (STATE.assistant.current_card or DEMO_PHONE_CARD).to_dict(),
        "demo_compare": (STATE.assistant.compare_card or DEMO_COMPARE_CARD).to_dict(),
    }


@app.post("/api/chat")
def chat_turn(req: ChatRequest) -> Dict[str, Any]:
    prompt = req.message.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Empty prompt.")
    try:
        res = STATE.assistant.send_message(prompt, use_web_search=req.use_web_search)
        return {
            "chat_reply": res.chat_reply,
            "updated_card": res.updated_card.to_dict() if res.updated_card else None,
            "updated_compare_card": (
                res.updated_compare_card.to_dict() if res.updated_compare_card else None
            ),
            "active_compare": (
                STATE.assistant.compare_card.to_dict() if STATE.assistant.compare_card else None
            ),
            "used_web_search": res.used_web_search,
            "search_sources": res.search_sources,
            "model_used": res.model_used,
            "tokens_used": res.tokens_used,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/verify-key")
def verify_key(req: VerifyKeyRequest) -> Dict[str, Any]:
    candidate = (req.api_key or "").strip() or STATE.assistant.api_key.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="Enter a Groq API key first.")
    try:
        models = fetch_groq_models(candidate)
        STATE.models = models
        return {"ok": True, "models": models}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest) -> Dict[str, Any]:
    final_key = (req.api_key or "").strip() or STATE.assistant.api_key.strip()
    STATE.assistant.api_key = final_key
    STATE.assistant.model = req.model.strip() or DEFAULT_MODELS[0]
    if STATE.assistant.model not in STATE.models:
        STATE.models.insert(0, STATE.assistant.model)

    STATE.voice_id = req.voice_id
    STATE.live_web = req.live_web
    STATE.auto_voice = req.auto_voice

    save_api_key_to_env(
        final_key,
        model=STATE.assistant.model,
        extra={
            "VOICE_ID": STATE.voice_id,
            "LIVE_WEB_SEARCH": "1" if STATE.live_web else "0",
            "AUTO_VOICE": "1" if STATE.auto_voice else "0",
        },
    )

    if req.autostart != is_autostart_enabled():
        if req.autostart:
            enable_autostart()
        else:
            disable_autostart()

    return {
        "ok": True,
        "has_api_key": bool(final_key),
        "model": STATE.assistant.model,
        "voice_id": STATE.voice_id,
        "live_web": STATE.live_web,
        "auto_voice": STATE.auto_voice,
        "autostart": is_autostart_enabled(),
    }


@app.post("/api/reset")
def reset_session() -> Dict[str, Any]:
    STATE.assistant.reset_session()
    return {"ok": True}


@app.post("/api/tts")
async def synthesize_speech(req: TTSRequest) -> Response:
    try:
        audio_bytes = await synthesize_mp3_bytes(req.text, voice=req.voice or STATE.voice_id)
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty speech text.")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/export", response_class=PlainTextResponse)
def export_markdown(mode: str = Query("single")) -> PlainTextResponse:
    primary: PhoneCardData = STATE.assistant.current_card or DEMO_PHONE_CARD
    compare: PhoneCardData = STATE.assistant.compare_card or DEMO_COMPARE_CARD
    if mode == "compare":
        md = (
            f"# Head-to-Head Comparison: {primary.name} vs {compare.name}\n\n"
            f"{primary.to_markdown()}\n\n---\n\n{compare.to_markdown()}\n"
        )
    else:
        md = primary.to_markdown()
    return PlainTextResponse(md)


# ---------------------------------------------------------------------------
# Standalone Native Desktop App Window Launcher (Linux + Windows)
# ---------------------------------------------------------------------------
def _find_free_port(preferred: int = 8765) -> int:
    for port in (preferred, 8766, 8767, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return int(s.getsockname()[1])
            except OSError:
                continue
    return 8765


def _wait_until_listening(host: str, port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def _detect_app_mode_browser() -> Optional[str]:
    system = platform.system().lower()
    if system == "windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        for cmd in ("msedge", "chrome", "brave"):
            found = shutil.which(cmd)
            if found:
                return found
    else:
        for cmd in (
            "google-chrome",
            "google-chrome-stable",
            "brave-browser",
            "chromium",
            "chromium-browser",
            "microsoft-edge",
            "microsoft-edge-stable",
        ):
            found = shutil.which(cmd)
            if found:
                return found
    return None


def launch_desktop_app() -> None:
    """Start local FastAPI engine and open SpecDeck in a chromeless native window."""
    port = _find_free_port(8765)
    url = f"http://127.0.0.1:{port}"

    server_cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_cfg)
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()

    if not _wait_until_listening("127.0.0.1", port):
        print(f"[SpecDeck] Server failed to bind on {url}", file=sys.stderr)
        sys.exit(1)

    browser_bin = _detect_app_mode_browser()
    profile_dir = Path.home() / ".cache" / "specdeck-window-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"[SpecDeck] Running Hardware Intelligence Studio at {url}")

    if browser_bin:
        cmd = [
            browser_bin,
            f"--app={url}",
            "--window-size=1380,860",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            proc.wait()
            server.should_exit = True
            return
        except Exception:
            pass

    # Fallback: open in default browser and keep local engine alive until Ctrl+C
    webbrowser.open(url)
    print("[SpecDeck] Opened in default browser. Press Ctrl+C to stop SpecDeck.")
    try:
        while srv_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecDeck — Smartphone Hardware Intelligence")
    parser.add_argument("--server", action="store_true", help="Run in headless HTTP server mode")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host in --server mode")
    parser.add_argument("--port", type=int, default=8000, help="Bind port in --server mode")
    args = parser.parse_args()

    # Pre-warm dynamic Groq model list in background if key exists
    if STATE.assistant.api_key:
        def _warm_models() -> None:
            try:
                STATE.models = fetch_groq_models(STATE.assistant.api_key)
            except Exception:
                pass
        threading.Thread(target=_warm_models, daemon=True).start()

    if args.server:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    else:
        launch_desktop_app()


if __name__ == "__main__":
    main()

# SpecDeck — Python Mobile Phone AI

A desktop smartphone research, side-by-side comparison, and buying advisor application built with Python and CustomTkinter. Powered by the Groq API with live web specification lookup and neural voice output.

---

## Features

- **Structured Hardware Datasheet** — Automatically extracts launch dates, retail pricing, full hardware specifications, category ratings (0–10), strengths, and trade-offs into a dedicated specification pane.
- **Side-by-Side Comparison** — Compare any two phones head-to-head across category scores, display, chipset, memory, camera hardware, battery/charging, and software support.
- **Contextual Advisor Thread** — Ask natural follow-up questions (*gaming thermals, night photography, charging times, budget alternatives*) with rolling conversation memory.
- **Dedicated Settings Window** — Click **Settings** (or press `Ctrl+,`) to paste your Groq API key with one click (`Paste` + `Verify`), choose your default model, pick a neural voice, and toggle OS startup.
- **Rate-Limit-Safe Token Budgeting** — Compact prompts, cached search snippets (~200 tokens), rolling history trimming, and automatic HTTP `429` model rotation keep usage around ~700–1,100 tokens per turn.
- **Neural Voice Output** — Listen to any response on demand (`Speak` / `Stop Audio`) or enable automatic `Voice Out` using `edge-tts` + `pygame` (uses zero Groq API tokens, with offline OS speech fallback).
- **Zero-Prerequisite Setup & Login Auto-Start** — Bootstrapper scripts for Windows and Linux automatically install Python 3 + Tkinter (if missing), create `.venv`, install dependencies, and optionally register system login auto-start.

---

## Quick Start

### Linux

```bash
git clone https://github.com/cid0980/python-mobile-ai.git
cd python-mobile-ai
chmod +x start_linux.sh autostart_linux.sh
./start_linux.sh
```

> If `python3`, `python3-venv`, or `python3-tk` is missing, `start_linux.sh` automatically detects your package manager (`apt-get`, `dnf`, `yum`, `pacman`, `zypper`, `apk`, `xbps-install`) and installs them before creating `.venv`.

### Windows (PowerShell or Command Prompt)

```bat
git clone https://github.com/cid0980/python-mobile-ai.git
cd python-mobile-ai
start_windows.bat
```

*(Or double-click `start_windows.bat` directly in File Explorer.)*

> If Python 3.9+ is not installed on Windows, `start_windows.bat` automatically installs Python 3.12 (including `pip` and `Tkinter`) via `winget` or the official silent installer from `python.org` without requiring Administrator privileges.

---

## Enable Auto-Start on System Login

Toggle **Launch on OS login** inside **Settings**, or run the setup utility from your terminal:

### Linux (XDG Autostart + Desktop Menu Entry)

```bash
# Interactive setup menu
./autostart_linux.sh

# Non-interactive CLI flags
./autostart_linux.sh --enable
./autostart_linux.sh --status
./autostart_linux.sh --disable
```

### Windows (Startup Folder + Desktop Shortcut)

```bat
:: Interactive setup menu
autostart_windows.bat

:: Non-interactive CLI flags
autostart_windows.bat --enable
autostart_windows.bat --status
autostart_windows.bat --disable
```

---

## API Key Setup

1. Create a free API key at **[console.groq.com/keys](https://console.groq.com/keys)**.
2. Open the app, click **Settings** in the top-right toolbar (or press `Ctrl+,`), click **Paste** next to **Groq API Key**, optionally click **Verify**, and click **Save Settings**.
   *(Your key is saved locally in `.env` and ignored by Git.)*

Alternatively, configure `.env` manually before launching:

```bash
cp .env.example .env
```

```env
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## Manual Setup (If You Already Have Python 3.9+)

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

```bat
:: Windows
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## Project Structure

```text
python-mobile-ai/
├── app.py                  # Split-pane CustomTkinter UI + dedicated Settings window
├── ai_engine.py            # Groq client, token-safe memory, JSON parser & 429 model fallback
├── web_search.py           # Cached DuckDuckGo (`ddgs`) live smartphone spec & review lookup
├── voice_engine.py         # Neural TTS (`edge-tts` + `pygame.mixer`) with offline OS fallback
├── autostart_manager.py    # Cross-platform Windows & Linux login auto-start and shortcut helper
├── start_windows.bat       # Windows auto-installer (Python + venv + packages) & launcher
├── autostart_windows.bat   # Windows login auto-start & Desktop shortcut setup script
├── start_linux.sh          # Linux auto-installer (Python3 + Tk + venv + packages) & launcher
├── autostart_linux.sh      # Linux XDG autostart & Application Menu setup script
├── specdeck_icon.svg       # Vector launcher icon
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules (.venv, .env, caches)
└── LICENSE                 # MIT License
```

---

## License

Released under the [MIT License](LICENSE).

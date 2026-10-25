# SpecDeck — Smartphone Hardware Intelligence Studio

**SpecDeck** is a desktop hardware intelligence terminal and contextual AI analyst for smartphones, built with **Python (FastAPI)**, **Groq Cloud LLMs**, **Live Web Grounding (`ddgs`)**, and **Neural Voice Synthesis (`edge-tts`)**.

Designed with modern interface engineering principles — precision dark surfaces, concentric geometry, `tabular-nums` hardware telemetry, progressive disclosure, and a live **5-Axis SVG Hardware Radar** — SpecDeck pairs a structured hardware datasheet on the left with a continuous AI analyst stream on the right.

---

## Core Capabilities

- **Split-Screen Hardware Telemetry + Continuous Analyst Stream**
  - **Left Pane (`Datasheet`):** Displays brand & availability signal, launch window, retail MSRP (`$ USD / ₹ INR`), a **5-axis SVG telemetry radar** (`Performance`, `Optics`, `Display`, `Power`, `Value`), an 8-cell bento hardware grid (Display, Silicon/SoC, Memory/UFS, Rear Optics, Front Camera, Battery/Charge, OS Policy, Chassis/IP), primary strengths, and honest trade-offs.
  - **Right Pane (`Analyst Session`):** Contextual follow-up conversation (`"Does it throttle in 120fps gaming?"`, `"How is 5x night zoom?"`) without losing the pinned datasheet.
- **Head-to-Head (`A/B`) Comparison Matrix & Dual Radar**
  - Type `"Compare OnePlus 13 vs iPhone 16 Pro Max"` (or use the `Head-to-Head` tab / `⌘K` omnibar) to overlay **dual translucent radar polygons** alongside category score deltas (`A +0.6`, `B +0.8`) and a row-aligned hardware comparison matrix.
- **Greeting-Aware Live Web Grounding (`ddgs`)**
  - Automatically queries live web specifications and pricing for smartphone lookups while skipping casual greetings (`"hello"`, `"thanks"`) to keep citations genuine and latency fast.
- **Groq Rate-Limit & Token Protection**
  - Budgets ~800–1,200 tokens per turn using rolling context compression and automatically rotates across active Groq models (`llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`) on `429` rate limits.
- **Zero-Token Neural Voice Output (`edge-tts`)**
  - Streams natural neural speech (`Andrew`, `Aria`, `Ryan`, `Sonia`) over `/api/tts` with hover-revealed per-response `Listen` controls and an animated top-bar audio equalizer.
- **Dedicated Settings & Credentials Sheet (`Ctrl+,` / `⌘,`)**
  - 1-click **`Paste`**, **`Show/Hide`**, and **`Verify`** for your Groq API key (`saved locally to .env`), model & neural voice selectors, live web search toggle, and OS login auto-start switch.

---

## Quick Start (Zero Prerequisites)

Both launchers automatically verify **Python 3.9+**, create/update `.venv`, install `requirements.txt`, and open SpecDeck in a **standalone chromeless desktop window** (`--app` mode).

### Linux (Ubuntu, Debian, Fedora, Arch, Mint, openSUSE)
```bash
git clone https://github.com/cid0980/python-mobile-ai.git
cd python-mobile-ai
chmod +x start_linux.sh autostart_linux.sh
./start_linux.sh
```
*(Updating an existing clone? Just run `git pull && ./start_linux.sh` — `.venv` packages upgrade automatically.)*

### Windows (10 / 11)
1. Clone or download this repository.
2. Double-click **`start_windows.bat`**.
   - Checks for Python 3.9+ (auto-installs Python 3.12 via `winget` or `python.org` if missing), sets up `.venv`, installs dependencies, and launches SpecDeck cleanly without keeping a console window open.

### Configuring Your Free Groq API Key
1. Generate a free API key at **[console.groq.com/keys](https://console.groq.com/keys)**.
2. Click the **Settings gear icon** (`⚙` top-right, or press `Ctrl+,`).
3. Click **`Paste`** → **`Verify`** → **`Save Changes`**.

---

## Auto-Start on OS Login

Enable or disable automatic launch on system login either from the in-app **Settings** switch (`Launch on System Login`) or via the included scripts:

- **Windows:** Double-click `autostart_windows.bat` (manages `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SpecDeckAI.vbs` + Desktop shortcut).
- **Linux:** Run `./autostart_linux.sh` (manages `~/.config/autostart/specdeck-ai.desktop` + application launcher entry).

---

## Project Architecture

```text
python-mobile-ai/
├── app.py                 # FastAPI backend + standalone chromeless desktop window launcher
├── static/
│   └── index.html         # Precision dark UI, 5-axis SVG radar, concentric layout & stream
├── ai_engine.py           # Groq JSON-mode analyst engine, spec sanitizer & 429 model fallback
├── web_search.py          # Greeting-aware DuckDuckGo smartphone spec & MSRP grounding
├── voice_engine.py        # Async Microsoft Edge Neural TTS MP3 byte streamer
├── autostart_manager.py   # Cross-platform Windows & Linux login auto-start manager
├── start_windows.bat      # 1-click Windows Python + .venv auto-installer & launcher
├── autostart_windows.bat  # Windows Startup toggle menu
├── start_linux.sh         # 1-click Linux multi-distro Python + .venv installer & launcher
├── autostart_linux.sh     # Linux XDG autostart toggle menu
├── specdeck_icon.svg      # Vector app icon
├── requirements.txt       # Python dependencies
└── .env.example           # Environment template
```

### Optional Browser / Projector Server Mode
For classroom projector demos or browser debugging:
```bash
./.venv/bin/python app.py --server --host 0.0.0.0 --port 8000
```

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+K` / `⌘K` | Focus top quick-jump & comparison omnibar |
| `Ctrl+,` / `⌘,` | Open Settings & API Key modal |
| `Esc` | Close modal |
| `Enter` | Submit query |

---

## License

Released under the [MIT License](LICENSE).

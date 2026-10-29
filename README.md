# SpecDeck — Smartphone Intelligence Studio

**SpecDeck** is a cross-platform Python desktop application (**Windows 10/11 & Linux**) combining a live **Split-Screen Hardware Datasheet**, **GSMArena Studio Device Imagery**, **Head-to-Head A/B Phone Comparison**, **Groq LLM Reasoning + Live Web Grounding**, and **Word-Synchronized Neural Voice Output** in a flat matte architectural UI (`#171717` Charcoal Black · `#06110c` Forest Green · `#a31c1b` Crimson Red).

---

## Key Capabilities

1. **Split-Screen Datasheet + Concise Contextual Advisor**
   - **Left Panel (Hardware Datasheet):** Automatically populates whenever you ask about any smartphone — displaying its official **GSMArena studio render**, launch date, USD/INR retail pricing, 5-axis SVG benchmark radar, and structured 8-block hardware specification grid.
   - **Right Panel (Contextual Advisor):** Delivers concise, high-signal buying context that directly answers what you asked without filler or raw JSON dumps.
2. **Official GSMArena Mobile Renders (`/api/phone-image`)**
   - Resolves high-resolution studio device imagery directly from GSMArena's CDN (`fdn2.gsmarena.com/vv/bigpic/...`) with live search fallback and in-memory caching for both Single Datasheet and Head-to-Head A/B views.
3. **Head-to-Head A/B Smartphone Comparison**
   - Compare any two smartphones side-by-side (`Compare OnePlus 13 vs iPhone 16 Pro Max`) with dual GSMArena studio renders, dual-polygon radar overlay, tabular score deltas (`A +0.4`, `B +0.6`), and category-by-category spec rows.
4. **Lockstep Word-by-Word Neural Voice Output + Voice Preview**
   - Powered by `edge-tts` (`WordBoundary` streaming over forced IPv4 `AF_INET` sockets for sub-second synthesis).
   - Words reveal in exact lockstep with the spoken voice, and Settings includes a one-click **Test Voice** preview button.
5. **Matte Architectural Palette**
   - Built strictly around **Charcoal Black (`#171717`)**, **Forest Green (`#06110c`)**, and **Crimson Red (`#a31c1b`)** — flat, crisp `1px` structural borders with zero drop-shadows, zero glow effects, zero gradients, and zero blinking animations.
6. **Zero-Friction Setup & Login Auto-Start (Windows & Linux)**
   - One-click `start_windows.bat` / `start_linux.sh` installers auto-detect or install Python 3, create `.venv`, install dependencies, and open SpecDeck in a chromeless native `--app` desktop window.

---

## Quick Start

### Windows (10 / 11)

```bat
git clone https://github.com/cid0980/python-mobile-ai.git
cd python-mobile-ai
start_windows.bat
```

Enable or disable automatic launch on Windows login:

```bat
autostart_windows.bat
autostart_windows.bat --disable
```

### Linux (Ubuntu / Debian / Mint / Fedora / Arch)

```bash
git clone https://github.com/cid0980/python-mobile-ai.git
cd python-mobile-ai
chmod +x start_linux.sh autostart_linux.sh
./start_linux.sh
```

Enable or disable automatic launch on Linux desktop login:

```bash
./autostart_linux.sh
./autostart_linux.sh --disable
```

---

## Groq API Key & Voice Configuration

1. Get a free API key at [console.groq.com/keys](https://console.groq.com/keys).
2. Click the **Settings (gear)** icon in the top-right corner of SpecDeck.
3. Click **Paste**, optionally **Verify**, test any neural voice using **Test Voice**, and click **Save Changes**.

---

## Project Structure

```text
python-mobile-ai/
├── app.py                  # FastAPI backend, GSMArena image endpoint & native --app window launcher
├── static/
│   └── index.html          # Matte #171717 / #06110c / #a31c1b UI + lockstep audio-word engine
├── ai_engine.py            # Groq JSON-enforced engine, <think> sanitizer & automatic model fallback
├── web_search.py           # Live DuckDuckGo grounding + GSMArena studio image resolver
├── voice_engine.py         # IPv4 neural Edge-TTS engine with WordBoundary streaming
├── autostart_manager.py    # Windows Startup & Linux XDG autostart + desktop shortcut manager
├── start_windows.bat       # Windows 1-click Python & venv installer + launcher
├── autostart_windows.bat   # Windows Startup & Desktop shortcut configurator
├── start_linux.sh          # Linux 1-click Python & venv installer + launcher
├── autostart_linux.sh      # Linux XDG autostart & .desktop configurator
├── specdeck_icon.svg       # Flat matte vector application icon
├── requirements.txt        # Python dependencies
└── .env.example            # Environment configuration template
```

---

## License

Released under the [MIT License](LICENSE).

## Windows setup troubleshooting (revised launcher)

1. Extract the whole ZIP into a writable folder, such as your user Documents folder.
   Do not run directly inside the ZIP or put it under `Program Files`.
2. Double-click **start_windows.bat**. It installs Python 3.12 when needed, repairs
   an unusable `.venv`, installs/verifies packages, then opens the application.
   Internet access is required for the first setup. Python 3.10–3.13 is accepted;
   the automatic installer uses Python 3.12.10.
3. Administrator rights are **not normally required**. If your environment requires
   elevation, use **start_windows_admin.bat** and approve the Windows UAC prompt.
   Do not use another user's administrator account for per-user installation or
   shortcuts: those would belong to that account. Elevation does not bypass company
   security policies, download restrictions, or antivirus rules.
4. To enable login launch and create a desktop shortcut, run
   **autostart_windows.bat** and choose **1**. This also launches the app immediately.
   Login launch is opt-in, not silently enabled during installation.
5. Setup failures remain visible. Logs are in **%LOCALAPPDATA%\SpecDeck\logs**:
   `setup.log` for installation, `app.log` for background application errors.
   For direct output run `start_windows.bat --console` from Command Prompt.
6. Re-run `start_windows.bat` after a failed download or dependency installation.
   Failed installs are not marked successful. Broken environments are preserved
   in `.venv.broken-*` folders; these may be deleted after successful repair.
7. Keep the extracted project in place. If you move it, recreate the shortcuts
   and enable login launch again. Native `.lnk` shortcuts replace the old VBScript
   launchers; re-enabling login launch removes the legacy Startup VBScript.

The application server intentionally stays running if Chromium hands the window
off to another browser process. Closing the app window may leave the launcher
running; close its console (or stop its Python process in Task Manager) to stop it.
This avoids the previous premature shutdown but is not full window-lifecycle tracking.

### Verification

`python -m unittest discover -s tests -v` runs the launcher regression tests.
The Windows installer, UAC, browser window and login launch must additionally be
smoke-tested on Windows 10/11; Linux checks cannot validate those OS integrations.

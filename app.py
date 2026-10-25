"""
app.py — SpecDeck Desktop Application (CustomTkinter)
Clean, native split-pane desktop UI with:
- Dedicated Settings window (1-click Paste API Key, Verify Key, Model, Voice & Startup)
- Single-device hardware datasheet & ratings
- Side-by-side 2-phone specification & score comparison
- Continuous rate-limit-safe Groq AI advisor chat
- Neural voice output (Speak / Stop + Auto-Voice mode)
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from ai_engine import (
    DEFAULT_MODELS,
    DEMO_COMPARE_CARD,
    DEMO_PHONE_CARD,
    PhoneCardData,
    SpecDeckAssistant,
    TurnResponse,
    fetch_groq_models,
    load_env_setting,
    save_api_key_to_env,
)
from autostart_manager import disable_autostart, enable_autostart, is_autostart_enabled
from voice_engine import DEFAULT_NEURAL_VOICE, VOICE_PRESETS, VoiceOutputEngine

# ---------------------------------------------------------------------------
# Neutral Monochrome Zinc Palette (Linear / Geist Desktop Aesthetic)
# ---------------------------------------------------------------------------
BG_CANVAS = "#131316"       # Right chat canvas
BG_SIDEBAR = "#18181B"      # Left spec sheet & top/bottom bars
BG_CONTROL = "#222226"      # Inputs, dropdowns, subtle buttons
BG_USER_MSG = "#1C1C20"     # Subtle user prompt block
BG_HOVER = "#2A2A2F"        # Quiet button hover

HAIRLINE = "#27272A"        # Primary 1px structural divider
HAIRLINE_SOFT = "#202024"   # Subtle row divider

TEXT_HIGH = "#FAFAFA"       # Headings & primary values
TEXT_MAIN = "#E4E4E7"       # Standard body copy
TEXT_DIM = "#A1A1AA"        # Secondary metadata
TEXT_MUTED = "#71717A"      # Micro labels & timestamps

BTN_PRIMARY_BG = "#F4F4F5"  # Crisp monochrome primary action
BTN_PRIMARY_FG = "#141416"
BTN_PRIMARY_HOVER = "#D4D4D8"

ACCENT_SUBTLE = "#3B82F6"   # Active switch progress fill


def tk_safe(text: str) -> str:
    """Keep characters within Tcl/Tk 8.6 BMP range across Windows, macOS & Linux."""
    if not text:
        return ""
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def attach_entry_context_menu(entry: ctk.CTkEntry, root: tk.Misc) -> None:
    """Attach standard right-click Paste / Copy / Clear menu to a CTkEntry."""
    menu = tk.Menu(
        root,
        tearoff=0,
        bg="#1F1F24",
        fg=TEXT_MAIN,
        activebackground="#2E2E36",
        activeforeground=TEXT_HIGH,
        bd=1,
        relief="flat",
    )

    def _paste() -> None:
        try:
            clip = root.clipboard_get().strip()
            if clip:
                entry.insert("insert", clip)
        except Exception:
            pass

    def _copy() -> None:
        try:
            val = entry.get()
            if val:
                root.clipboard_clear()
                root.clipboard_append(val)
        except Exception:
            pass

    def _clear() -> None:
        entry.delete(0, "end")

    menu.add_command(label="Paste", command=_paste)
    menu.add_command(label="Copy", command=_copy)
    menu.add_separator()
    menu.add_command(label="Clear", command=_clear)

    def _popup(event) -> None:
        entry.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    entry.bind("<Button-3>", _popup)


# ===========================================================================
# Dedicated Settings Dialog Window
# ===========================================================================
class SettingsDialog(ctk.CTkToplevel):
    """Modal Settings dialog for pasting Groq API key, model, voice & startup."""

    def __init__(
        self,
        parent: "SpecDeckApp",
        available_models: List[str],
        on_saved: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.on_saved = on_saved
        self.dialog_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()

        self.title("Settings — SpecDeck")
        self.configure(fg_color=BG_SIDEBAR)
        self.resizable(False, False)

        w, h = 560, 545
        px = parent.winfo_rootx() + max(20, (parent.winfo_width() - w) // 2)
        py = parent.winfo_rooty() + max(20, (parent.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")

        self.transient(parent)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_form(available_models)
        self._build_footer()

        self.after(60, self._poll_dialog_queue)
        self.after(100, self._grab_safely)

    def _grab_safely(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.key_entry.focus_set()
            self.grab_set()
        except Exception:
            pass

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=22, pady=(18, 12), sticky="ew")

        ctk.CTkLabel(
            hdr,
            text="Settings",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT_HIGH,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            hdr,
            text="Configure your Groq API key, preferred model, voice synthesis, and startup behavior.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        ctk.CTkFrame(self, fg_color=HAIRLINE, height=1, corner_radius=0).grid(
            row=1, column=0, sticky="ew"
        )

    def _build_form(self, available_models: List[str]) -> None:
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, padx=22, pady=14, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)

        r = 0
        # --- Section 1: Groq API Key ---
        key_hdr = ctk.CTkFrame(form, fg_color="transparent")
        key_hdr.grid(row=r, column=0, pady=(0, 6), sticky="ew")
        key_hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            key_hdr,
            text="GROQ API KEY",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            key_hdr,
            text="Get Free Key (console.groq.com)",
            height=22,
            width=0,
            corner_radius=4,
            fg_color="transparent",
            hover_color=BG_CONTROL,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=11),
            command=lambda: webbrowser.open("https://console.groq.com/keys"),
        ).grid(row=0, column=1, sticky="e")
        r += 1

        key_row = ctk.CTkFrame(form, fg_color="transparent")
        key_row.grid(row=r, column=0, sticky="ew")
        key_row.grid_columnconfigure(0, weight=1)

        self.key_masked = True
        self.key_entry = ctk.CTkEntry(
            key_row,
            placeholder_text="Paste gsk_... API key here",
            show="•",
            height=34,
            corner_radius=6,
            fg_color=BG_CANVAS,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=12),
        )
        if self.parent_app.assistant.api_key:
            self.key_entry.insert(0, self.parent_app.assistant.api_key)
        self.key_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        attach_entry_context_menu(self.key_entry, self)

        ctk.CTkButton(
            key_row,
            text="Paste",
            width=60,
            height=34,
            corner_radius=6,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._paste_from_clipboard,
        ).grid(row=0, column=1, padx=(0, 6))

        self.show_btn = ctk.CTkButton(
            key_row,
            text="Show",
            width=54,
            height=34,
            corner_radius=6,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=12),
            command=self._toggle_mask,
        )
        self.show_btn.grid(row=0, column=2, padx=(0, 6))

        self.verify_btn = ctk.CTkButton(
            key_row,
            text="Verify",
            width=62,
            height=34,
            corner_radius=6,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12),
            command=self._verify_key_clicked,
        )
        self.verify_btn.grid(row=0, column=3)
        r += 1

        ctk.CTkLabel(
            form,
            text="Stored locally in .env on your machine (never committed to Git).",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, pady=(4, 12), sticky="ew")
        r += 1

        ctk.CTkFrame(form, fg_color=HAIRLINE, height=1).grid(
            row=r, column=0, pady=(0, 12), sticky="ew"
        )
        r += 1

        # --- Section 2: Model & Search ---
        ctk.CTkLabel(
            form,
            text="MODEL & SEARCH",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, pady=(0, 6), sticky="ew")
        r += 1

        model_row = ctk.CTkFrame(form, fg_color="transparent")
        model_row.grid(row=r, column=0, pady=(0, 10), sticky="ew")
        model_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            model_row,
            text="Default Groq Model",
            width=160,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.dlg_model_var = ctk.StringVar(value=self.parent_app.model_var.get())
        self.dlg_model_menu = ctk.CTkOptionMenu(
            model_row,
            variable=self.dlg_model_var,
            values=available_models,
            height=30,
            corner_radius=5,
            fg_color=BG_CONTROL,
            button_color="#2C2C32",
            button_hover_color="#383840",
            dropdown_fg_color=BG_SIDEBAR,
            dropdown_hover_color=BG_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12),
        )
        self.dlg_model_menu.grid(row=0, column=1, sticky="ew")
        r += 1

        self.dlg_web_var = ctk.BooleanVar(value=self.parent_app.web_var.get())
        ctk.CTkSwitch(
            form,
            text="Enable Live Web Search for current phone specs & launch dates",
            variable=self.dlg_web_var,
            switch_width=34,
            switch_height=18,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            fg_color="#323238",
            progress_color=ACCENT_SUBTLE,
            button_color=TEXT_HIGH,
        ).grid(row=r, column=0, pady=(2, 12), sticky="w")
        r += 1

        ctk.CTkFrame(form, fg_color=HAIRLINE, height=1).grid(
            row=r, column=0, pady=(0, 12), sticky="ew"
        )
        r += 1

        # --- Section 3: Voice & System Startup ---
        ctk.CTkLabel(
            form,
            text="VOICE & SYSTEM",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, pady=(0, 6), sticky="ew")
        r += 1

        voice_row = ctk.CTkFrame(form, fg_color="transparent")
        voice_row.grid(row=r, column=0, pady=(0, 10), sticky="ew")
        voice_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            voice_row,
            text="Neural Voice",
            width=160,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        current_voice_id = self.parent_app.voice.voice
        current_label = next(
            (lbl for lbl, vid in VOICE_PRESETS.items() if vid == current_voice_id),
            list(VOICE_PRESETS.keys())[0],
        )
        self.dlg_voice_var = ctk.StringVar(value=current_label)
        ctk.CTkOptionMenu(
            voice_row,
            variable=self.dlg_voice_var,
            values=list(VOICE_PRESETS.keys()),
            height=30,
            corner_radius=5,
            fg_color=BG_CONTROL,
            button_color="#2C2C32",
            button_hover_color="#383840",
            dropdown_fg_color=BG_SIDEBAR,
            dropdown_hover_color=BG_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            voice_row,
            text="Test",
            width=58,
            height=30,
            corner_radius=5,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=12),
            command=self._test_voice_clicked,
        ).grid(row=0, column=2)
        r += 1

        switches_row = ctk.CTkFrame(form, fg_color="transparent")
        switches_row.grid(row=r, column=0, sticky="ew")

        self.dlg_autovoice_var = ctk.BooleanVar(
            value=self.parent_app.auto_voice_var.get()
        )
        ctk.CTkSwitch(
            switches_row,
            text="Auto-read AI responses",
            variable=self.dlg_autovoice_var,
            switch_width=34,
            switch_height=18,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            fg_color="#323238",
            progress_color=ACCENT_SUBTLE,
            button_color=TEXT_HIGH,
        ).pack(side="left", padx=(0, 24))

        self.dlg_autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        ctk.CTkSwitch(
            switches_row,
            text="Launch on OS login",
            variable=self.dlg_autostart_var,
            switch_width=34,
            switch_height=18,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            fg_color="#323238",
            progress_color=ACCENT_SUBTLE,
            button_color=TEXT_HIGH,
        ).pack(side="left")

    def _build_footer(self) -> None:
        ctk.CTkFrame(self, fg_color=HAIRLINE, height=1, corner_radius=0).grid(
            row=3, column=0, sticky="ew"
        )

        ftr = ctk.CTkFrame(self, fg_color=BG_CANVAS, corner_radius=0, height=54)
        ftr.grid(row=4, column=0, sticky="ew")
        ftr.grid_propagate(False)
        ftr.grid_columnconfigure(0, weight=1)

        self.dlg_status = ctk.CTkLabel(
            ftr,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
            anchor="w",
        )
        self.dlg_status.grid(row=0, column=0, padx=20, pady=14, sticky="ew")

        btns = ctk.CTkFrame(ftr, fg_color="transparent")
        btns.grid(row=0, column=1, padx=20, pady=11, sticky="e")

        ctk.CTkButton(
            btns,
            text="Cancel",
            width=76,
            height=32,
            corner_radius=6,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12),
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="Save Settings",
            width=112,
            height=32,
            corner_radius=6,
            fg_color=BTN_PRIMARY_BG,
            hover_color=BTN_PRIMARY_HOVER,
            text_color=BTN_PRIMARY_FG,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save_and_close,
        ).pack(side="left")

    def _paste_from_clipboard(self) -> None:
        try:
            clip = self.clipboard_get().strip()
            if not clip:
                self.dlg_status.configure(text="Clipboard is empty.")
                return
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, clip)
            self.dlg_status.configure(text="Pasted key from clipboard.")
        except Exception:
            self.dlg_status.configure(text="Nothing found in clipboard.")

    def _toggle_mask(self) -> None:
        self.key_masked = not self.key_masked
        self.key_entry.configure(show="•" if self.key_masked else "")
        self.show_btn.configure(text="Show" if self.key_masked else "Hide")

    def _verify_key_clicked(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            self.dlg_status.configure(text="Paste an API key first to verify.")
            return
        self.verify_btn.configure(state="disabled", text="...")
        self.dlg_status.configure(text="Verifying key with Groq...")

        def worker() -> None:
            try:
                models = fetch_groq_models(key)
                self.dialog_queue.put(("verify_ok", models))
            except Exception as exc:
                self.dialog_queue.put(("verify_err", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _test_voice_clicked(self) -> None:
        voice_id = VOICE_PRESETS.get(self.dlg_voice_var.get(), DEFAULT_NEURAL_VOICE)
        self.parent_app.voice.voice = voice_id
        self.parent_app._speak_text("SpecDeck voice output is ready.")
        self.dlg_status.configure(text="Playing voice sample...")

    def _poll_dialog_queue(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.dialog_queue.get_nowait()
                self.verify_btn.configure(state="normal", text="Verify")
                if kind == "verify_ok":
                    models: List[str] = payload  # type: ignore[assignment]
                    self.dlg_model_menu.configure(values=models)
                    if self.dlg_model_var.get() not in models and models:
                        self.dlg_model_var.set(models[0])
                    self.parent_app.model_menu.configure(values=models)
                    self.dlg_status.configure(
                        text=f"Key verified — {len(models)} models available."
                    )
                elif kind == "verify_err":
                    self.dlg_status.configure(text="Invalid key or network error.")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(60, self._poll_dialog_queue)

    def _save_and_close(self) -> None:
        key = self.key_entry.get().strip()
        selected_model = self.dlg_model_var.get().strip() or DEFAULT_MODELS[0]
        voice_id = VOICE_PRESETS.get(self.dlg_voice_var.get(), DEFAULT_NEURAL_VOICE)
        web_on = bool(self.dlg_web_var.get())
        autovoice_on = bool(self.dlg_autovoice_var.get())
        autostart_on = bool(self.dlg_autostart_var.get())

        self.parent_app.assistant.api_key = key
        self.parent_app.assistant.model = selected_model
        self.parent_app.model_var.set(selected_model)
        self.parent_app.web_var.set(web_on)
        self.parent_app.auto_voice_var.set(autovoice_on)
        self.parent_app.voice.voice = voice_id

        save_api_key_to_env(
            key,
            model=selected_model,
            extra={
                "VOICE_ID": voice_id,
                "LIVE_WEB": "1" if web_on else "0",
                "AUTO_VOICE": "1" if autovoice_on else "0",
            },
        )

        if autostart_on != is_autostart_enabled():
            if autostart_on:
                enable_autostart()
            else:
                disable_autostart()

        self.on_saved()
        self.destroy()


# ===========================================================================
# Main Application Window
# ===========================================================================
class SpecDeckApp(ctk.CTk):
    """Main Desktop Window for SpecDeck."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")

        self.title("SpecDeck")
        self.geometry("1280x800")
        self.minsize(1020, 640)
        self.configure(fg_color=BG_CANVAS)

        self.assistant = SpecDeckAssistant()
        saved_voice = load_env_setting("VOICE_ID", DEFAULT_NEURAL_VOICE)
        self.voice = VoiceOutputEngine(voice=saved_voice or DEFAULT_NEURAL_VOICE)
        self.ui_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()

        self.is_busy: bool = False
        self.left_mode: str = "Specifications"
        self.preview_mode: bool = True
        self._settings_win: Optional[SettingsDialog] = None
        self._available_models: List[str] = list(DEFAULT_MODELS)
        if self.assistant.model not in self._available_models:
            self._available_models.insert(0, self.assistant.model)

        self._shown_primary: PhoneCardData = DEMO_PHONE_CARD
        self._shown_compare: Optional[PhoneCardData] = DEMO_COMPARE_CARD

        # Root layout:
        # Row 0: Top toolbar (46px)
        # Row 1: 1px hairline
        # Row 2: Main split-pane body
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        ctk.CTkFrame(self, fg_color=HAIRLINE, height=1, corner_radius=0).grid(
            row=1, column=0, sticky="ew"
        )
        self._build_split_body()

        self._refresh_left_pane()
        self._render_empty_thread_hint()

        self._bind_scroll_routing()
        self.bind_all("<Control-comma>", lambda _e: self.open_settings())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._poll_queue)

    # -----------------------------------------------------------------------
    # Top Toolbar
    # -----------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        self.toolbar = ctk.CTkFrame(
            self, fg_color=BG_SIDEBAR, corner_radius=0, height=46
        )
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.toolbar.grid_propagate(False)
        self.toolbar.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=16, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="SpecDeck",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_HIGH,
        ).pack(side="left")

        ctk.CTkLabel(
            title_box,
            text="  Smartphone Specifications & Advisor",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).pack(side="left", pady=(1, 0))

        ctrl = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        ctrl.grid(row=0, column=2, padx=16, sticky="e")

        initial_web = load_env_setting("LIVE_WEB", "1") != "0"
        self.web_var = ctk.BooleanVar(value=initial_web)
        ctk.CTkSwitch(
            ctrl,
            text="Live Web",
            variable=self.web_var,
            switch_width=34,
            switch_height=18,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_DIM,
            fg_color="#323238",
            progress_color=ACCENT_SUBTLE,
            button_color=TEXT_HIGH,
            button_hover_color=TEXT_MAIN,
        ).pack(side="left", padx=(0, 14))

        initial_autovoice = load_env_setting("AUTO_VOICE", "0") == "1"
        self.auto_voice_var = ctk.BooleanVar(value=initial_autovoice)
        ctk.CTkSwitch(
            ctrl,
            text="Voice Out",
            variable=self.auto_voice_var,
            switch_width=34,
            switch_height=18,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_DIM,
            fg_color="#323238",
            progress_color=ACCENT_SUBTLE,
            button_color=TEXT_HIGH,
            button_hover_color=TEXT_MAIN,
        ).pack(side="left", padx=(0, 10))

        self.stop_voice_btn = ctk.CTkButton(
            ctrl,
            text="Stop Audio",
            width=76,
            height=28,
            corner_radius=5,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_MUTED,
            state="disabled",
            font=ctk.CTkFont(size=11),
            command=self._stop_speaking,
        )
        self.stop_voice_btn.pack(side="left", padx=(0, 10))

        self.model_var = ctk.StringVar(value=self.assistant.model)
        self.model_menu = ctk.CTkOptionMenu(
            ctrl,
            variable=self.model_var,
            values=self._available_models,
            command=self._on_model_select,
            width=184,
            height=28,
            corner_radius=5,
            fg_color=BG_CONTROL,
            button_color="#2C2C32",
            button_hover_color="#383840",
            dropdown_fg_color=BG_SIDEBAR,
            dropdown_hover_color=BG_HOVER,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12),
        )
        self.model_menu.pack(side="left", padx=(0, 10))

        self.settings_btn = ctk.CTkButton(
            ctrl,
            text=self._settings_btn_label(),
            width=116 if not self.assistant.api_key else 84,
            height=28,
            corner_radius=5,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH if not self.assistant.api_key else TEXT_MAIN,
            font=ctk.CTkFont(size=12),
            command=self.open_settings,
        )
        self.settings_btn.pack(side="left")

    def _settings_btn_label(self) -> str:
        return "Settings" if self.assistant.api_key else "Settings · Set Key"

    def open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        self._settings_win = SettingsDialog(
            self,
            available_models=self._available_models,
            on_saved=self._on_settings_saved,
        )

    def _on_settings_saved(self) -> None:
        has_key = bool(self.assistant.api_key)
        self.settings_btn.configure(
            text=self._settings_btn_label(),
            width=84 if has_key else 116,
            text_color=TEXT_MAIN if has_key else TEXT_HIGH,
        )
        self.status_label.configure(
            text="Settings saved." if has_key else "Settings updated (no API key set)."
        )
        if has_key:
            self._sync_models_background()

    # -----------------------------------------------------------------------
    # Edge-to-Edge Split Body (Left Datasheet/Compare | 1px Rule | Right Thread)
    # -----------------------------------------------------------------------
    def _build_split_body(self) -> None:
        self.body = ctk.CTkFrame(self, fg_color=BG_CANVAS, corner_radius=0)
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=0, minsize=500)
        self.body.grid_columnconfigure(1, weight=0, minsize=1)
        self.body.grid_columnconfigure(2, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        # ---------------- LEFT PANE ----------------
        self.left_pane = ctk.CTkFrame(
            self.body, width=500, fg_color=BG_SIDEBAR, corner_radius=0
        )
        self.left_pane.grid(row=0, column=0, sticky="nsew")
        self.left_pane.grid_propagate(False)
        self.left_pane.grid_columnconfigure(0, weight=1)
        self.left_pane.grid_rowconfigure(2, weight=1)

        left_bar = ctk.CTkFrame(
            self.left_pane, fg_color=BG_SIDEBAR, corner_radius=0, height=40
        )
        left_bar.grid(row=0, column=0, padx=14, pady=6, sticky="ew")
        left_bar.grid_columnconfigure(1, weight=1)

        self.mode_seg = ctk.CTkSegmentedButton(
            left_bar,
            values=["Specifications", "Compare"],
            height=28,
            corner_radius=6,
            fg_color="#121215",
            selected_color="#2C2C33",
            selected_hover_color="#35353D",
            unselected_color="#121215",
            unselected_hover_color="#1E1E24",
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_mode_switched,
        )
        self.mode_seg.set("Specifications")
        self.mode_seg.grid(row=0, column=0, sticky="w")

        left_actions = ctk.CTkFrame(left_bar, fg_color="transparent")
        left_actions.grid(row=0, column=2, sticky="e")

        self.copy_sheet_btn = ctk.CTkButton(
            left_actions,
            text="Copy",
            width=52,
            height=26,
            corner_radius=5,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=12),
            command=self._copy_datasheet,
        )
        self.copy_sheet_btn.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            left_actions,
            text="Export",
            width=56,
            height=26,
            corner_radius=5,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=12),
            command=self._export_report,
        ).pack(side="left")

        ctk.CTkFrame(
            self.left_pane, fg_color=HAIRLINE, height=1, corner_radius=0
        ).grid(row=1, column=0, sticky="ew")

        self.left_scroll = ctk.CTkScrollableFrame(
            self.left_pane,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            scrollbar_button_color="#27272A",
            scrollbar_button_hover_color="#3F3F46",
        )
        self.left_scroll.grid(row=2, column=0, sticky="nsew")
        self.left_scroll.grid_columnconfigure(0, weight=1)

        # ---------------- 1PX VERTICAL DIVIDER ----------------
        ctk.CTkFrame(
            self.body, fg_color=HAIRLINE, width=1, height=1, corner_radius=0
        ).grid(row=0, column=1, sticky="ns")

        # ---------------- RIGHT PANE ----------------
        self.right_pane = ctk.CTkFrame(
            self.body, fg_color=BG_CANVAS, corner_radius=0
        )
        self.right_pane.grid(row=0, column=2, sticky="nsew")
        self.right_pane.grid_columnconfigure(0, weight=1)
        self.right_pane.grid_rowconfigure(2, weight=1)

        right_bar = ctk.CTkFrame(
            self.right_pane, fg_color=BG_CANVAS, corner_radius=0, height=40
        )
        right_bar.grid(row=0, column=0, padx=18, pady=6, sticky="ew")
        right_bar.grid_columnconfigure(1, weight=1)

        ctx_wrap = ctk.CTkFrame(right_bar, fg_color="transparent")
        ctx_wrap.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            ctx_wrap,
            text="Advisor",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(side="left")

        self.context_label = ctk.CTkLabel(
            ctx_wrap,
            text="  ·  Ready",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        )
        self.context_label.pack(side="left")

        ctk.CTkButton(
            right_bar,
            text="New Thread",
            width=84,
            height=26,
            corner_radius=5,
            fg_color="transparent",
            hover_color=BG_CONTROL,
            text_color=TEXT_DIM,
            font=ctk.CTkFont(size=12),
            command=self._reset_thread,
        ).grid(row=0, column=2, sticky="e")

        ctk.CTkFrame(
            self.right_pane, fg_color=HAIRLINE, height=1, corner_radius=0
        ).grid(row=1, column=0, sticky="ew")

        self.chat_scroll = ctk.CTkScrollableFrame(
            self.right_pane,
            fg_color=BG_CANVAS,
            corner_radius=0,
            scrollbar_button_color="#27272A",
            scrollbar_button_hover_color="#3F3F46",
        )
        self.chat_scroll.grid(row=2, column=0, sticky="nsew")
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        # Bottom composer area
        ctk.CTkFrame(
            self.right_pane, fg_color=HAIRLINE, height=1, corner_radius=0
        ).grid(row=3, column=0, sticky="ew")

        composer = ctk.CTkFrame(
            self.right_pane, fg_color=BG_SIDEBAR, corner_radius=0
        )
        composer.grid(row=4, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)

        entry_row = ctk.CTkFrame(composer, fg_color="transparent")
        entry_row.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        entry_row.grid_columnconfigure(0, weight=1)

        self.chat_entry = ctk.CTkEntry(
            entry_row,
            placeholder_text="Ask about a phone, follow-up detail, or type 'Phone A vs Phone B'...",
            height=38,
            corner_radius=6,
            fg_color=BG_CANVAS,
            border_width=1,
            border_color="#2E2E34",
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=13),
        )
        self.chat_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.chat_entry.bind("<Return>", lambda _e: self._send_from_entry())
        attach_entry_context_menu(self.chat_entry, self)

        self.send_btn = ctk.CTkButton(
            entry_row,
            text="Send",
            width=76,
            height=38,
            corner_radius=6,
            fg_color=BTN_PRIMARY_BG,
            hover_color=BTN_PRIMARY_HOVER,
            text_color=BTN_PRIMARY_FG,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._send_from_entry,
        )
        self.send_btn.grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(
            composer,
            text="Ready  ·  Compact token mode active",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.status_label.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")

    # -----------------------------------------------------------------------
    # Left Pane Renderers: Single Datasheet & Side-by-Side Comparison
    # -----------------------------------------------------------------------
    def _on_mode_switched(self, value: str) -> None:
        self.left_mode = value
        self._refresh_left_pane()

    def _refresh_left_pane(self) -> None:
        for child in self.left_scroll.winfo_children():
            child.destroy()

        if self.left_mode == "Compare":
            self._render_compare_view()
        else:
            self._render_single_datasheet(self._shown_primary)

    def _render_single_datasheet(self, card: PhoneCardData) -> None:
        wrap = ctk.CTkFrame(self.left_scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        wrap.grid_columnconfigure(0, weight=1)

        r = 0
        if self.preview_mode:
            ctk.CTkLabel(
                wrap,
                text="Sample Datasheet  ·  Query any phone in Advisor to load live data",
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=r, column=0, pady=(0, 10), sticky="ew")
            r += 1

        meta_top = f"{(card.brand or 'Phone').upper()}  ·  {(card.status or 'Released').upper()}"
        ctk.CTkLabel(
            wrap,
            text=tk_safe(meta_top),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, sticky="ew")
        r += 1

        ctk.CTkLabel(
            wrap,
            text=tk_safe(card.name),
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT_HIGH,
            wraplength=440,
            justify="left",
            anchor="w",
        ).grid(row=r, column=0, pady=(2, 2), sticky="ew")
        r += 1

        if card.tagline:
            ctk.CTkLabel(
                wrap,
                text=tk_safe(card.tagline),
                font=ctk.CTkFont(size=12),
                text_color=TEXT_DIM,
                wraplength=440,
                justify="left",
                anchor="w",
            ).grid(row=r, column=0, pady=(0, 8), sticky="ew")
            r += 1

        ctk.CTkLabel(
            wrap,
            text=tk_safe(f"Launch: {card.launch_date}    ·    Price: {card.price_estimate}"),
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MAIN,
            wraplength=440,
            justify="left",
            anchor="w",
        ).grid(row=r, column=0, pady=(0, 12), sticky="ew")
        r += 1

        ctk.CTkFrame(wrap, fg_color=HAIRLINE, height=1).grid(
            row=r, column=0, pady=(0, 10), sticky="ew"
        )
        r += 1

        ctk.CTkLabel(
            wrap,
            text="SPECIFICATIONS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, pady=(0, 6), sticky="ew")
        r += 1

        spec_rows = [
            ("Display", card.specs.get("display", "—")),
            ("Processor", card.specs.get("processor", "—")),
            ("Memory", card.specs.get("ram_storage", "—")),
            ("Rear Camera", card.specs.get("rear_camera", "—")),
            ("Front Camera", card.specs.get("front_camera", "—")),
            ("Battery", card.specs.get("battery_charging", "—")),
            ("Software", card.specs.get("os_updates", "—")),
            ("Build", card.specs.get("build_extras", "—")),
        ]
        for idx, (s_label, s_val) in enumerate(spec_rows):
            row_f = ctk.CTkFrame(wrap, fg_color="transparent")
            row_f.grid(row=r, column=0, pady=4, sticky="ew")
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row_f,
                text=s_label,
                width=102,
                height=18,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=0, column=0, padx=(0, 8), sticky="nw", pady=(1, 0))

            ctk.CTkLabel(
                row_f,
                text=tk_safe(s_val),
                height=18,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MAIN,
                wraplength=330,
                justify="left",
                anchor="w",
            ).grid(row=0, column=1, sticky="ew")
            r += 1

            if idx < len(spec_rows) - 1:
                ctk.CTkFrame(wrap, fg_color=HAIRLINE_SOFT, height=1).grid(
                    row=r, column=0, sticky="ew"
                )
                r += 1

        ctk.CTkFrame(wrap, fg_color=HAIRLINE, height=1).grid(
            row=r, column=0, pady=(12, 10), sticky="ew"
        )
        r += 1

        ctk.CTkLabel(
            wrap,
            text="RATINGS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=r, column=0, pady=(0, 6), sticky="ew")
        r += 1

        ratings_f = ctk.CTkFrame(wrap, fg_color="transparent")
        ratings_f.grid(row=r, column=0, sticky="ew")
        ratings_f.grid_columnconfigure(1, weight=1)

        for idx, (k_label, k_key) in enumerate(
            [
                ("Performance", "performance"),
                ("Camera", "camera"),
                ("Display", "display"),
                ("Battery", "battery"),
                ("Value", "value"),
            ]
        ):
            val = card.scores.get(k_key, 8.0)
            ctk.CTkLabel(
                ratings_f,
                text=k_label,
                width=96,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_DIM,
                anchor="w",
            ).grid(row=idx, column=0, pady=4, sticky="w")

            bar = ctk.CTkProgressBar(
                ratings_f,
                height=5,
                corner_radius=3,
                fg_color="#26262B",
                progress_color=TEXT_MAIN,
            )
            bar.set(max(0.05, min(1.0, val / 10.0)))
            bar.grid(row=idx, column=1, padx=10, pady=4, sticky="ew")

            ctk.CTkLabel(
                ratings_f,
                text=f"{val:.1f}",
                width=32,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=TEXT_HIGH,
                anchor="e",
            ).grid(row=idx, column=2, pady=4, sticky="e")
        r += 1

        ctk.CTkFrame(wrap, fg_color=HAIRLINE, height=1).grid(
            row=r, column=0, pady=(12, 10), sticky="ew"
        )
        r += 1

        if card.good_for:
            ctk.CTkLabel(
                wrap,
                text="BEST FOR",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=r, column=0, pady=(0, 4), sticky="ew")
            r += 1
            for item in card.good_for:
                ctk.CTkLabel(
                    wrap,
                    text=f"•  {tk_safe(item)}",
                    font=ctk.CTkFont(size=12),
                    text_color=TEXT_MAIN,
                    wraplength=435,
                    justify="left",
                    anchor="w",
                ).grid(row=r, column=0, pady=1, sticky="ew")
                r += 1

        if card.skip_if:
            ctk.CTkLabel(
                wrap,
                text="TRADE-OFFS",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=r, column=0, pady=(10, 4), sticky="ew")
            r += 1
            for item in card.skip_if:
                ctk.CTkLabel(
                    wrap,
                    text=f"•  {tk_safe(item)}",
                    font=ctk.CTkFont(size=12),
                    text_color=TEXT_DIM,
                    wraplength=435,
                    justify="left",
                    anchor="w",
                ).grid(row=r, column=0, pady=1, sticky="ew")
                r += 1

        if card.verdict_one_liner:
            ctk.CTkLabel(
                wrap,
                text=tk_safe(card.verdict_one_liner),
                font=ctk.CTkFont(size=12),
                text_color=TEXT_DIM,
                wraplength=435,
                justify="left",
                anchor="w",
            ).grid(row=r, column=0, pady=(10, 6), sticky="ew")

    def _render_compare_view(self) -> None:
        wrap = ctk.CTkFrame(self.left_scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        wrap.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(2, weight=1)

        self.comp_a_entry = ctk.CTkEntry(
            bar,
            placeholder_text="Phone A",
            height=30,
            corner_radius=5,
            fg_color=BG_CANVAS,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=12),
        )
        if self._shown_primary:
            self.comp_a_entry.insert(0, self._shown_primary.name)
        self.comp_a_entry.grid(row=0, column=0, sticky="ew")
        attach_entry_context_menu(self.comp_a_entry, self)

        ctk.CTkLabel(
            bar, text="vs", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        ).grid(row=0, column=1, padx=6)

        self.comp_b_entry = ctk.CTkEntry(
            bar,
            placeholder_text="Phone B",
            height=30,
            corner_radius=5,
            fg_color=BG_CANVAS,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=12),
        )
        if self._shown_compare:
            self.comp_b_entry.insert(0, self._shown_compare.name)
        self.comp_b_entry.grid(row=0, column=2, padx=(0, 6), sticky="ew")
        self.comp_b_entry.bind("<Return>", lambda _e: self._run_compare_inputs())
        attach_entry_context_menu(self.comp_b_entry, self)

        ctk.CTkButton(
            bar,
            text="Compare",
            width=72,
            height=30,
            corner_radius=5,
            fg_color=BG_CONTROL,
            hover_color=BG_HOVER,
            border_width=1,
            border_color=HAIRLINE,
            text_color=TEXT_HIGH,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._run_compare_inputs,
        ).grid(row=0, column=3)

        ctk.CTkFrame(wrap, fg_color=HAIRLINE, height=1).grid(
            row=1, column=0, pady=(0, 10), sticky="ew"
        )

        card_a = self._shown_primary
        card_b = self._shown_compare

        if not card_b:
            ctk.CTkLabel(
                wrap,
                text="Enter a second phone above and click Compare (or type 'Compare with ...' in Advisor).",
                font=ctk.CTkFont(size=12),
                text_color=TEXT_DIM,
                wraplength=430,
                justify="left",
                anchor="w",
            ).grid(row=2, column=0, pady=12, sticky="ew")
            return

        grid = ctk.CTkFrame(wrap, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew")
        grid.grid_columnconfigure(0, weight=1, uniform="cmp")
        grid.grid_columnconfigure(1, weight=0, minsize=1)
        grid.grid_columnconfigure(2, weight=1, uniform="cmp")

        gr = 0
        ctk.CTkLabel(
            grid,
            text=tk_safe(card_a.name),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_HIGH,
            wraplength=205,
            justify="left",
            anchor="nw",
        ).grid(row=gr, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkFrame(grid, fg_color=HAIRLINE_SOFT, width=1, height=1).grid(
            row=gr, column=1, rowspan=2, sticky="ns"
        )

        ctk.CTkLabel(
            grid,
            text=tk_safe(card_b.name),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_HIGH,
            wraplength=205,
            justify="left",
            anchor="nw",
        ).grid(row=gr, column=2, padx=(10, 0), sticky="ew")
        gr += 1

        ctk.CTkLabel(
            grid,
            text=tk_safe(f"{card_a.launch_date}\n{card_a.price_estimate}"),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
            wraplength=205,
            justify="left",
            anchor="nw",
        ).grid(row=gr, column=0, padx=(0, 8), pady=(2, 8), sticky="ew")

        ctk.CTkLabel(
            grid,
            text=tk_safe(f"{card_b.launch_date}\n{card_b.price_estimate}"),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
            wraplength=205,
            justify="left",
            anchor="nw",
        ).grid(row=gr, column=2, padx=(10, 0), pady=(2, 8), sticky="ew")
        gr += 1

        ctk.CTkFrame(grid, fg_color=HAIRLINE, height=1).grid(
            row=gr, column=0, columnspan=3, pady=(2, 8), sticky="ew"
        )
        gr += 1

        ctk.CTkLabel(
            grid,
            text="CATEGORY SCORES",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=gr, column=0, columnspan=3, pady=(0, 4), sticky="ew")
        gr += 1

        for label, key in (
            ("Performance", "performance"),
            ("Camera", "camera"),
            ("Display", "display"),
            ("Battery", "battery"),
            ("Value", "value"),
        ):
            va = card_a.scores.get(key, 8.0)
            vb = card_b.scores.get(key, 8.0)
            ctk.CTkLabel(
                grid,
                text=f"{label}:  {va:.1f}",
                height=20,
                font=ctk.CTkFont(size=12, weight="bold" if va >= vb else "normal"),
                text_color=TEXT_HIGH if va >= vb else TEXT_DIM,
                anchor="w",
            ).grid(row=gr, column=0, padx=(0, 8), pady=2, sticky="ew")

            ctk.CTkFrame(grid, fg_color=HAIRLINE_SOFT, width=1, height=1).grid(
                row=gr, column=1, sticky="ns"
            )

            ctk.CTkLabel(
                grid,
                text=f"{label}:  {vb:.1f}",
                height=20,
                font=ctk.CTkFont(size=12, weight="bold" if vb >= va else "normal"),
                text_color=TEXT_HIGH if vb >= va else TEXT_DIM,
                anchor="w",
            ).grid(row=gr, column=2, padx=(10, 0), pady=2, sticky="ew")
            gr += 1

        ctk.CTkFrame(grid, fg_color=HAIRLINE, height=1).grid(
            row=gr, column=0, columnspan=3, pady=(8, 6), sticky="ew"
        )
        gr += 1

        compare_fields = [
            ("DISPLAY", card_a.specs.get("display", "—"), card_b.specs.get("display", "—")),
            ("PROCESSOR", card_a.specs.get("processor", "—"), card_b.specs.get("processor", "—")),
            ("MEMORY & STORAGE", card_a.specs.get("ram_storage", "—"), card_b.specs.get("ram_storage", "—")),
            ("REAR CAMERA", card_a.specs.get("rear_camera", "—"), card_b.specs.get("rear_camera", "—")),
            ("FRONT CAMERA", card_a.specs.get("front_camera", "—"), card_b.specs.get("front_camera", "—")),
            ("BATTERY & CHARGING", card_a.specs.get("battery_charging", "—"), card_b.specs.get("battery_charging", "—")),
            ("SOFTWARE", card_a.specs.get("os_updates", "—"), card_b.specs.get("os_updates", "—")),
            ("BUILD", card_a.specs.get("build_extras", "—"), card_b.specs.get("build_extras", "—")),
            ("BEST FOR", " · ".join(card_a.good_for) or "—", " · ".join(card_b.good_for) or "—"),
        ]

        for title, val_a, val_b in compare_fields:
            ctk.CTkLabel(
                grid,
                text=title,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=gr, column=0, columnspan=3, pady=(6, 2), sticky="ew")
            gr += 1

            ctk.CTkLabel(
                grid,
                text=tk_safe(val_a),
                height=18,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MAIN,
                wraplength=205,
                justify="left",
                anchor="nw",
            ).grid(row=gr, column=0, padx=(0, 8), pady=(0, 6), sticky="ew")

            ctk.CTkFrame(grid, fg_color=HAIRLINE_SOFT, width=1, height=1).grid(
                row=gr, column=1, sticky="ns"
            )

            ctk.CTkLabel(
                grid,
                text=tk_safe(val_b),
                height=18,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MAIN,
                wraplength=205,
                justify="left",
                anchor="nw",
            ).grid(row=gr, column=2, padx=(10, 0), pady=(0, 6), sticky="ew")
            gr += 1

            ctk.CTkFrame(grid, fg_color=HAIRLINE_SOFT, height=1).grid(
                row=gr, column=0, columnspan=3, sticky="ew"
            )
            gr += 1

    # -----------------------------------------------------------------------
    # Right Pane: Clean Editorial Thread Stream
    # -----------------------------------------------------------------------
    def _render_empty_thread_hint(self) -> None:
        self.empty_hint = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        self.empty_hint.pack(fill="x", padx=22, pady=(24, 12))

        ctk.CTkLabel(
            self.empty_hint,
            text="Ask about any mobile phone",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_HIGH,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            self.empty_hint,
            text=(
                "Enter a model name for launch dates, specifications, and real-world suitability, "
                "ask follow-up questions in context, or compare two devices side-by-side."
            ),
            font=ctk.CTkFont(size=13),
            text_color=TEXT_DIM,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 14))

        examples_row = ctk.CTkFrame(self.empty_hint, fg_color="transparent")
        examples_row.pack(fill="x")

        for sample in (
            "Samsung Galaxy S26 Ultra",
            "OnePlus 13 vs iPhone 16 Pro Max",
            "Google Pixel 9 Pro",
            "Best camera phone under $500",
        ):
            ctk.CTkButton(
                examples_row,
                text=sample,
                height=28,
                width=0,
                corner_radius=5,
                fg_color=BG_SIDEBAR,
                hover_color=BG_CONTROL,
                border_width=1,
                border_color=HAIRLINE,
                text_color=TEXT_DIM,
                font=ctk.CTkFont(size=12),
                command=lambda s=sample: self._submit_message(s),
            ).pack(side="left", padx=(0, 6), pady=2)

        ctk.CTkFrame(
            self.empty_hint, fg_color=HAIRLINE_SOFT, height=1
        ).pack(fill="x", pady=(18, 0))

    def _append_user_turn(self, text: str) -> None:
        if hasattr(self, "empty_hint") and self.empty_hint.winfo_exists():
            self.empty_hint.destroy()

        block = ctk.CTkFrame(
            self.chat_scroll,
            fg_color=BG_USER_MSG,
            corner_radius=6,
            border_width=1,
            border_color=HAIRLINE_SOFT,
        )
        block.pack(fill="x", padx=20, pady=(12, 6))

        ctk.CTkLabel(
            block,
            text="You",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            block,
            text=tk_safe(text),
            font=ctk.CTkFont(size=13),
            text_color=TEXT_HIGH,
            wraplength=660,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 10))

        self._scroll_thread_end()

    def _append_assistant_turn(
        self,
        text: str,
        used_web: bool = False,
        sources: Optional[List[Tuple[str, str]]] = None,
        is_error: bool = False,
    ) -> None:
        block = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        block.pack(fill="x", padx=22, pady=(6, 4))

        hdr = ctk.CTkFrame(block, fg_color="transparent")
        hdr.pack(fill="x", pady=(2, 4))

        ctk.CTkLabel(
            hdr,
            text="Notice" if is_error else "SpecDeck",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#F87171" if is_error else TEXT_HIGH,
        ).pack(side="left")

        meta_bits = []
        if used_web and not is_error:
            meta_bits.append("Web verified")
        meta_bits.append(datetime.now().strftime("%H:%M"))

        ctk.CTkLabel(
            hdr,
            text="  ·  " + "  ·  ".join(meta_bits),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        if not is_error:
            copy_btn = ctk.CTkButton(
                hdr,
                text="Copy",
                width=46,
                height=22,
                corner_radius=4,
                fg_color="transparent",
                hover_color=BG_CONTROL,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=11),
            )
            copy_btn.configure(command=lambda t=text, b=copy_btn: self._flash_copy(t, b))
            copy_btn.pack(side="right", padx=(4, 0))

            speak_btn = ctk.CTkButton(
                hdr,
                text="Speak",
                width=52,
                height=22,
                corner_radius=4,
                fg_color="transparent",
                hover_color=BG_CONTROL,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=11),
                command=lambda t=text: self._speak_text(t),
            )
            speak_btn.pack(side="right")

        ctk.CTkLabel(
            block,
            text=tk_safe(text),
            font=ctk.CTkFont(size=13),
            text_color="#FCA5A5" if is_error else TEXT_MAIN,
            wraplength=670,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        if sources and not is_error:
            names = [tk_safe(t[:40]) for t, _ in sources if t][:3]
            if names:
                ctk.CTkLabel(
                    block,
                    text="Sources: " + "  ·  ".join(names),
                    font=ctk.CTkFont(size=11),
                    text_color=TEXT_MUTED,
                    wraplength=670,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

        ctk.CTkFrame(block, fg_color=HAIRLINE_SOFT, height=1).pack(
            fill="x", pady=(4, 0)
        )
        self._scroll_thread_end()

    def _scroll_thread_end(self) -> None:
        self.update_idletasks()
        try:
            self.chat_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Messaging, Compare & Voice Actions
    # -----------------------------------------------------------------------
    def _send_from_entry(self) -> None:
        msg = self.chat_entry.get().strip()
        if not msg or self.is_busy:
            return
        self.chat_entry.delete(0, "end")
        self._submit_message(msg)

    def _run_compare_inputs(self) -> None:
        if self.is_busy:
            return
        phone_a = self.comp_a_entry.get().strip()
        phone_b = self.comp_b_entry.get().strip()
        if not phone_a or not phone_b:
            self.status_label.configure(
                text="Enter both Phone A and Phone B to run a side-by-side comparison."
            )
            return
        self._submit_message(f"Compare {phone_a} vs {phone_b}")

    def _submit_message(self, prompt: str) -> None:
        if self.is_busy:
            return

        if not self.assistant.api_key:
            self.open_settings()
            self._append_user_turn(prompt)
            self._append_assistant_turn(
                "Please paste your Groq API key in Settings (opened above) and click Save Settings.",
                is_error=True,
            )
            return

        self._append_user_turn(prompt)
        self._set_busy(True, "Researching...")
        use_web = bool(self.web_var.get())

        def worker() -> None:
            try:
                res = self.assistant.send_message(
                    user_message=prompt,
                    use_web_search=use_web,
                    status_callback=lambda s: self.ui_queue.put(("status", s)),
                )
                self.ui_queue.put(("ok", res))
            except Exception as exc:
                self.ui_queue.put(("err", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "status":
                    self.status_label.configure(text=tk_safe(str(payload)))
                elif kind == "ok":
                    res: TurnResponse = payload  # type: ignore[assignment]
                    self.preview_mode = False

                    if res.updated_card is not None:
                        self._shown_primary = res.updated_card
                    elif self.assistant.current_card is not None:
                        self._shown_primary = self.assistant.current_card

                    if res.updated_compare_card is not None:
                        self._shown_compare = res.updated_compare_card
                        self.left_mode = "Compare"
                        self.mode_seg.set("Compare")
                    elif res.updated_card is not None and res.updated_compare_card is None:
                        self._shown_compare = self.assistant.compare_card

                    self._refresh_left_pane()

                    if self.assistant.current_card:
                        ctx = self.assistant.current_card.name
                        if self.assistant.compare_card:
                            ctx += f"  vs  {self.assistant.compare_card.name}"
                        self.context_label.configure(text=f"  ·  {tk_safe(ctx)}")

                    if res.model_used and res.model_used != self.model_var.get():
                        self.model_var.set(res.model_used)

                    self._append_assistant_turn(
                        res.chat_reply,
                        used_web=res.used_web_search,
                        sources=res.search_sources,
                    )

                    tok_info = (
                        f"  ·  {res.tokens_used} tokens used" if res.tokens_used else ""
                    )
                    self._set_busy(False, f"Ready{tok_info}")

                    if self.auto_voice_var.get():
                        self._speak_text(res.chat_reply)

                elif kind == "err":
                    self._append_assistant_turn(str(payload), is_error=True)
                    self._set_busy(False, "Ready")
                elif kind == "models_ok":
                    models_list: List[str] = payload  # type: ignore[assignment]
                    self._available_models = models_list
                    self.model_menu.configure(values=models_list)
                    if self.assistant.model not in models_list and models_list:
                        self.assistant.model = models_list[0]
                        self.model_var.set(models_list[0])
                elif kind == "voice_state":
                    speaking, msg = payload  # type: ignore[misc]
                    if speaking:
                        self.stop_voice_btn.configure(
                            state="normal", text_color=TEXT_HIGH
                        )
                        if msg:
                            self.status_label.configure(text=msg)
                    else:
                        self.stop_voice_btn.configure(
                            state="disabled", text_color=TEXT_MUTED
                        )
                        if not self.is_busy:
                            self.status_label.configure(text="Ready")
        except queue.Empty:
            pass
        finally:
            self.after(60, self._poll_queue)

    def _speak_text(self, text: str) -> None:
        self.voice.speak(
            text,
            on_state_change=lambda active, msg: self.ui_queue.put(
                ("voice_state", (active, msg))
            ),
        )

    def _stop_speaking(self) -> None:
        self.voice.stop()
        self.stop_voice_btn.configure(state="disabled", text_color=TEXT_MUTED)
        if not self.is_busy:
            self.status_label.configure(text="Audio stopped.")

    def _set_busy(self, busy: bool, status_text: str) -> None:
        self.is_busy = busy
        self.send_btn.configure(
            state="disabled" if busy else "normal",
            text="..." if busy else "Send",
        )
        self.status_label.configure(text=tk_safe(status_text))

    def _on_model_select(self, model_name: str) -> None:
        self.assistant.model = model_name

    def _sync_models_background(self) -> None:
        key = self.assistant.api_key
        if not key:
            return

        def worker() -> None:
            try:
                self.ui_queue.put(("models_ok", fetch_groq_models(key)))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _reset_thread(self) -> None:
        if self.is_busy:
            return
        self.voice.stop()
        self.assistant.reset_session()
        self.preview_mode = True
        self._shown_primary = DEMO_PHONE_CARD
        self._shown_compare = DEMO_COMPARE_CARD
        for child in self.chat_scroll.winfo_children():
            child.destroy()
        self._render_empty_thread_hint()
        self._refresh_left_pane()
        self.context_label.configure(text="  ·  Ready")
        self.status_label.configure(text="Thread cleared.")

    def _flash_copy(self, text: str, btn: ctk.CTkButton) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        orig = btn.cget("text")
        btn.configure(text="Copied")
        self.after(1200, lambda: btn.configure(text=orig))

    def _copy_datasheet(self) -> None:
        if self.left_mode == "Compare" and self._shown_compare:
            md = (
                self._shown_primary.to_markdown()
                + "\n\n---\n\n"
                + self._shown_compare.to_markdown()
            )
        else:
            md = self._shown_primary.to_markdown()
        self._flash_copy(md, self.copy_sheet_btn)

    def _export_report(self) -> None:
        slug = "".join(
            ch if ch.isalnum() else "_" for ch in self._shown_primary.name.lower()
        ).strip("_")
        target = filedialog.asksaveasfilename(
            title="Export Markdown Report",
            defaultextension=".md",
            initialfile=f"{slug or 'specdeck'}_report.md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
        )
        if not target:
            return

        parts = [self._shown_primary.to_markdown()]
        if self._shown_compare and self.left_mode == "Compare":
            parts.append("\n---\n\n" + self._shown_compare.to_markdown())
        if self.assistant.chat_history:
            parts.append("\n---\n\n## Advisor Thread\n")
            for m in self.assistant.chat_history:
                role = "You" if m["role"] == "user" else "SpecDeck"
                parts.append(f"### {role}\n{m['content']}\n")

        Path(target).write_text("\n".join(parts), encoding="utf-8")
        self.status_label.configure(text=f"Exported to {Path(target).name}")

    def _bind_scroll_routing(self) -> None:
        def _canvas_under_pointer(x_root: int):
            lx = self.left_pane.winfo_rootx()
            lw = self.left_pane.winfo_width()
            if lx <= x_root <= lx + lw:
                return self.left_scroll._parent_canvas
            return self.chat_scroll._parent_canvas

        def _wheel(event) -> None:
            try:
                cv = _canvas_under_pointer(event.x_root)
                if getattr(event, "num", None) == 4:
                    cv.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    cv.yview_scroll(3, "units")
                elif getattr(event, "delta", 0):
                    step = (
                        -1 * int(event.delta / 120)
                        if abs(event.delta) >= 120
                        else (-1 if event.delta > 0 else 1)
                    )
                    cv.yview_scroll(step * 3, "units")
            except Exception:
                pass

        self.bind_all("<MouseWheel>", _wheel, add="+")
        self.bind_all("<Button-4>", _wheel, add="+")
        self.bind_all("<Button-5>", _wheel, add="+")

    def _on_close(self) -> None:
        self.voice.stop()
        self.destroy()


def main() -> None:
    app = SpecDeckApp()
    app.mainloop()


if __name__ == "__main__":
    main()

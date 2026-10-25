"""
ai_engine.py — Precision Smartphone Intelligence Engine (Groq + Web Grounding)
Combines live web search snippets with comprehensive hardware knowledge so every
spec cell is complete (zero 'details not listed'), while maintaining a strict
~800–1,200 token budget per turn and automatic 429 rate-limit model rotation.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq

from web_search import SearchBundle, search_phone_facts

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_MODELS: List[str] = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

EXCLUDED_MODEL_KEYWORDS = (
    "whisper", "guard", "safeguard", "tts", "orpheus", "embed", "vision-preview", "playai",
)


def _clean_spec_val(val: Any, fallback: str = "—") -> str:
    """Clean escaped quotes/backslashes from model strings (e.g. 6.82\\\" -> 6.82\")."""
    if val is None:
        return fallback
    s = str(val).strip()
    s = s.replace('\\"', '"').replace("\\'", "'").strip()
    return s if s else fallback


@dataclass
class PhoneCardData:
    name: str = ""
    brand: str = ""
    tagline: str = ""
    launch_date: str = "—"
    status: str = "Available"
    price_estimate: str = "—"
    specs: Dict[str, str] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)
    good_for: List[str] = field(default_factory=list)
    skip_if: List[str] = field(default_factory=list)
    verdict_one_liner: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.name}",
            f"*{self.tagline}*" if self.tagline else "",
            "",
            f"- **Brand:** {self.brand or '—'}",
            f"- **Status:** {self.status}",
            f"- **Launch Date:** {self.launch_date}",
            f"- **Price:** {self.price_estimate}",
            "",
            "## Hardware Specifications",
        ]
        spec_labels = [
            ("display", "Display"),
            ("processor", "Processor / SoC"),
            ("ram_storage", "Memory & Storage"),
            ("rear_camera", "Rear Camera System"),
            ("front_camera", "Front Camera"),
            ("battery_charging", "Battery & Charging"),
            ("os_updates", "OS & Update Policy"),
            ("build_extras", "Chassis & Protection"),
        ]
        for key, label in spec_labels:
            lines.append(f"- **{label}:** {self.specs.get(key, '—')}")

        if self.scores:
            lines.extend(["", "## Telemetry Ratings (0–10)"])
            for k, v in self.scores.items():
                lines.append(f"- **{k.capitalize()}:** {v:.1f} / 10")

        if self.good_for:
            lines.extend(["", "## Ideal Use Cases"])
            for item in self.good_for:
                lines.append(f"- {item}")

        if self.skip_if:
            lines.extend(["", "## Trade-offs"])
            for item in self.skip_if:
                lines.append(f"- {item}")

        if self.verdict_one_liner:
            lines.extend(["", f"**Analyst Verdict:** {self.verdict_one_liner}"])

        return "\n".join(line for line in lines if line is not None)


DEMO_PHONE_CARD = PhoneCardData(
    name="Samsung Galaxy S26 Ultra",
    brand="Samsung",
    tagline="6.9-inch Titanium Flagship · Built-in S-Pen & Quad Telephoto",
    launch_date="Feb 2026 (Released Mar 2026)",
    status="Available",
    price_estimate="$1,299 / ₹1,29,999",
    specs={
        "display": '6.9" Dynamic LTPO AMOLED 2X · QHD+ · 1–120Hz · 2600 nits',
        "processor": "Snapdragon 8 Elite Gen 5 (3nm)",
        "ram_storage": "12GB / 16GB LPDDR5X · 256GB / 512GB / 1TB UFS 4.0",
        "rear_camera": "200MP f/1.7 OIS + 50MP UW + 50MP 5x Periscope + 10MP 3x",
        "front_camera": "12MP f/2.2 Dual-Pixel AF (4K 60fps)",
        "battery_charging": "5000 mAh · 45W Wired / 15W Qi2 Wireless",
        "os_updates": "Android 16 (One UI 8) · 7 Years OS & Security",
        "build_extras": "Grade 5 Titanium · Gorilla Armor · IP68 · S-Pen · Wi-Fi 7",
    },
    scores={"performance": 9.8, "camera": 9.6, "display": 9.8, "battery": 8.9, "value": 8.2},
    good_for=[
        "Sustained 120fps gaming & heavy multitasking",
        "Long-range 5x–10x zoom & night video capture",
        "S-Pen precision notes & 7-year flagship longevity",
    ],
    skip_if=[
        "Prefer compact phones under 200g",
        "Want 80W–100W ultra-fast wired charging",
    ],
    verdict_one_liner="Benchmark Android flagship combining class-leading display optics, S-Pen utility, and 7-year support.",
)

DEMO_COMPARE_CARD = PhoneCardData(
    name="OnePlus 13",
    brand="OnePlus",
    tagline="6000mAh Silicon-Carbon Flagship with 100W SuperVOOC",
    launch_date="Oct 2024 (CN) · Jan 2025 (Global)",
    status="Available",
    price_estimate="$899 / ₹69,999",
    specs={
        "display": '6.82" LTPO 4.1 AMOLED · QHD+ · 1–120Hz · 4500 nits peak',
        "processor": "Snapdragon 8 Elite (3nm)",
        "ram_storage": "12GB / 16GB / 24GB LPDDR5X · 256GB / 512GB / 1TB UFS 4.0",
        "rear_camera": "50MP LYT-808 OIS + 50MP 3x Triprism + 50MP UW (Hasselblad)",
        "front_camera": "32MP Sony IMX615 (4K 60fps)",
        "battery_charging": "6000 mAh Si/C · 100W SuperVOOC / 50W AirVOOC Wireless",
        "os_updates": "Android 15 (OxygenOS 15) · 4 Years OS / 6 Years Security",
        "build_extras": "Aluminum Frame · Ceramic Guard · IP68 + IP69 · Alert Slider",
    },
    scores={"performance": 9.7, "camera": 9.0, "display": 9.5, "battery": 9.7, "value": 9.3},
    good_for=[
        "Two-day 6000mAh endurance + 36-min full 100W charge",
        "High-FPS gaming with large vapor chamber cooling",
        "Flagship silicon at $300–$400 below Ultra rivals",
    ],
    skip_if=[
        "Need 5x+ optical periscope zoom for distant subjects",
        "Want 7 years of guaranteed OS upgrades",
    ],
    verdict_one_liner="Best-value performance and battery flagship with class-leading 100W wired + 50W wireless charging.",
)


@dataclass
class TurnResponse:
    chat_reply: str
    updated_card: Optional[PhoneCardData]
    updated_compare_card: Optional[PhoneCardData]
    used_web_search: bool
    search_sources: List[Dict[str, str]] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0


SYSTEM_PROMPT = """You are SpecDeck, an authoritative smartphone hardware analyst (current year: 2026).
Combine WEB SEARCH REFERENCE SNIPPETS (for recent 2025/2026 releases & current pricing) WITH your complete smartphone engineering knowledge so EVERY spec field is detailed and accurate.
NEVER write "Not specified", "Check retail", or "(details not listed)" for released phones — always provide exact sensor MP, charging wattages, launch OS + update policy, and launch price ($ USD and ₹ INR).

Return ONLY valid JSON matching:
{
  "update_card": true/false,
  "phone_card": { ... } or null,
  "compare_card": { ... } or null,
  "chat_reply": "Markdown string"
}

Card schema (required when update_card=true or comparing):
{"name":"","brand":"","tagline":"","launch_date":"Mon YYYY","status":"Available|Upcoming","price_estimate":"$XXX / ₹XX,XXX","specs":{"display":"","processor":"","ram_storage":"","rear_camera":"","front_camera":"","battery_charging":"","os_updates":"","build_extras":""},"scores":{"performance":9.0,"camera":8.8,"display":9.0,"battery":9.0,"value":8.5},"good_for":["3 crisp strengths"],"skip_if":["2 honest trade-offs"],"verdict_one_liner":""}

Behavior rules:
1. Casual greeting ("hello", "hi"): set update_card=false, phone_card=null, compare_card=null, and reply warmly in 2 concise lines.
2. Phone lookup: set update_card=true, fill phone_card completely, set compare_card=null. In chat_reply, write a crisp structured breakdown using ### headings and newline bullet lists (- item): Launch & Pricing, Hardware Standouts, Best Suited For, and Trade-offs.
3. Follow-up question on current phone: set update_card=false, phone_card=null, compare_card=null; answer directly and concisely in chat_reply.
4. Comparing two phones ("X vs Y" or "compare with Y"): fill BOTH phone_card (Phone A) and compare_card (Phone B) completely, AND write a clear category-by-category winner summary + buying verdict in chat_reply (never leave chat_reply empty!)."""


def get_saved_api_key() -> str:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
    key = os.getenv("GROQ_API_KEY", "").strip()
    return "" if key == "your_groq_api_key_here" else key


def load_env_setting(name: str, default: str = "") -> str:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
    return os.getenv(name, default).strip()


def save_api_key_to_env(
    api_key: str,
    model: Optional[str] = None,
    extra: Optional[Dict[str, str]] = None,
) -> None:
    clean_key = api_key.strip()
    existing: Dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, v = stripped.split("=", 1)
                existing[k.strip()] = v.strip()

    existing["GROQ_API_KEY"] = clean_key
    if model:
        existing["GROQ_MODEL"] = model.strip()
    if extra:
        for ek, ev in extra.items():
            existing[ek] = str(ev).strip()

    out_lines = [
        "# SpecDeck Local Configuration",
        *[f"{k}={v}" for k, v in existing.items()],
        "",
    ]
    ENV_PATH.write_text("\n".join(out_lines), encoding="utf-8")
    os.environ["GROQ_API_KEY"] = clean_key
    if model:
        os.environ["GROQ_MODEL"] = model.strip()
    if extra:
        for ek, ev in extra.items():
            os.environ[ek] = str(ev).strip()


def fetch_groq_models(api_key: str) -> List[str]:
    if not api_key.strip():
        return list(DEFAULT_MODELS)

    client = Groq(api_key=api_key.strip())
    resp = client.models.list()
    available: List[str] = []
    for m in getattr(resp, "data", []):
        mid = getattr(m, "id", "")
        if mid and not any(bad in mid.lower() for bad in EXCLUDED_MODEL_KEYWORDS):
            available.append(mid)

    if not available:
        return list(DEFAULT_MODELS)

    priority = {name: i for i, name in enumerate(DEFAULT_MODELS)}
    available.sort(key=lambda x: (priority.get(x, 999), x.lower()))
    return available


def _clamp_score(val: Any, default: float = 8.2) -> float:
    try:
        return max(0.0, min(10.0, round(float(val), 1)))
    except (TypeError, ValueError):
        return default


def _parse_phone_card(raw_card: Any) -> Optional[PhoneCardData]:
    if not isinstance(raw_card, dict):
        return None
    name = _clean_spec_val(raw_card.get("name"), "")
    if not name:
        return None

    raw_specs = raw_card.get("specs") if isinstance(raw_card.get("specs"), dict) else {}
    specs = {
        "display": _clean_spec_val(raw_specs.get("display")),
        "processor": _clean_spec_val(raw_specs.get("processor")),
        "ram_storage": _clean_spec_val(raw_specs.get("ram_storage")),
        "rear_camera": _clean_spec_val(raw_specs.get("rear_camera")),
        "front_camera": _clean_spec_val(raw_specs.get("front_camera")),
        "battery_charging": _clean_spec_val(raw_specs.get("battery_charging")),
        "os_updates": _clean_spec_val(raw_specs.get("os_updates")),
        "build_extras": _clean_spec_val(raw_specs.get("build_extras")),
    }

    raw_scores = raw_card.get("scores") if isinstance(raw_card.get("scores"), dict) else {}
    scores = {
        "performance": _clamp_score(raw_scores.get("performance"), 8.4),
        "camera": _clamp_score(raw_scores.get("camera"), 8.2),
        "display": _clamp_score(raw_scores.get("display"), 8.5),
        "battery": _clamp_score(raw_scores.get("battery"), 8.4),
        "value": _clamp_score(raw_scores.get("value"), 8.2),
    }

    good_for = [
        _clean_spec_val(x, "")
        for x in (raw_card.get("good_for") or [])
        if _clean_spec_val(x, "")
    ][:4]
    skip_if = [
        _clean_spec_val(x, "")
        for x in (raw_card.get("skip_if") or [])
        if _clean_spec_val(x, "")
    ][:3]

    return PhoneCardData(
        name=name,
        brand=_clean_spec_val(raw_card.get("brand"), ""),
        tagline=_clean_spec_val(raw_card.get("tagline"), ""),
        launch_date=_clean_spec_val(raw_card.get("launch_date"), "—"),
        status=_clean_spec_val(raw_card.get("status"), "Available"),
        price_estimate=_clean_spec_val(raw_card.get("price_estimate"), "—"),
        specs=specs,
        scores=scores,
        good_for=good_for,
        skip_if=skip_if,
        verdict_one_liner=_clean_spec_val(raw_card.get("verdict_one_liner"), ""),
    )


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return {"update_card": False, "phone_card": None, "compare_card": None, "chat_reply": cleaned}


def _synthesize_fallback_summary(
    primary: Optional[PhoneCardData], compare: Optional[PhoneCardData]
) -> str:
    """Guarantee a rich analyst reply even if a model omits chat_reply."""
    if primary and compare:
        return (
            f"### {primary.name} vs {compare.name}\n"
            f"- **Launch & Pricing:** {primary.name} ({primary.launch_date}, {primary.price_estimate}) vs "
            f"{compare.name} ({compare.launch_date}, {compare.price_estimate})\n"
            f"- **Silicon:** {primary.specs.get('processor', '—')} vs {compare.specs.get('processor', '—')}\n"
            f"- **Battery & Charge:** {primary.specs.get('battery_charging', '—')} vs {compare.specs.get('battery_charging', '—')}\n"
            f"- **Verdict:** {primary.verdict_one_liner or ''} {compare.verdict_one_liner or ''}"
        ).strip()
    if primary:
        return (
            f"### {primary.name}\n"
            f"- **Launch & Price:** {primary.launch_date} · {primary.price_estimate}\n"
            f"- **Core Hardware:** {primary.specs.get('display', '—')} · {primary.specs.get('processor', '—')}\n"
            f"- **Verdict:** {primary.verdict_one_liner or 'Full datasheet loaded in the telemetry panel.'}"
        )
    return "Datasheet updated."


class SpecDeckAssistant:
    """Rate-limit-safe Smartphone AI Engine with single & comparison states."""

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODELS[0]) -> None:
        self.api_key: str = api_key or get_saved_api_key()
        self.model: str = os.getenv("GROQ_MODEL", model).strip() or DEFAULT_MODELS[0]
        self.current_card: Optional[PhoneCardData] = None
        self.compare_card: Optional[PhoneCardData] = None
        self.chat_history: List[Dict[str, str]] = []

    def reset_session(self) -> None:
        self.chat_history.clear()
        self.current_card = None
        self.compare_card = None

    def send_message(
        self,
        user_message: str,
        use_web_search: bool = True,
    ) -> TurnResponse:
        key = self.api_key.strip()
        if not key:
            raise ValueError(
                "No Groq API key configured. Open Settings (⌘, or top-right gear icon), "
                "paste your key from console.groq.com/keys, and click Save Settings."
            )

        active_name = self.current_card.name if self.current_card else None
        comp_name = self.compare_card.name if self.compare_card else None
        search_bundle = SearchBundle(used_search=False)

        if use_web_search:
            search_bundle = search_phone_facts(
                user_message,
                active_phone=active_name,
                compare_phone=comp_name,
                max_total_results=4,
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        if self.current_card:
            ctx = (
                f"Active device on datasheet: {self.current_card.name} "
                f"({self.current_card.launch_date}, {self.current_card.price_estimate}, "
                f"{self.current_card.specs.get('processor', '')})."
            )
            if self.compare_card:
                ctx += f" Currently compared against: {self.compare_card.name} ({self.compare_card.price_estimate})."
            messages.append({"role": "system", "content": ctx})

        for msg in self.chat_history[-6:]:
            content = msg["content"]
            if len(content) > 480:
                content = content[:480] + "…"
            messages.append({"role": msg["role"], "content": content})

        if search_bundle.used_search and search_bundle.context_text:
            user_payload = f"USER QUERY: {user_message}\n\n{search_bundle.context_text}"
        else:
            user_payload = user_message

        messages.append({"role": "user", "content": user_payload})

        is_compare_req = bool(
            re.search(r"\b(?:vs\.?|versus|compare|comparison)\b", user_message, flags=re.I)
        )
        token_cap = 1400 if is_compare_req else 1050

        client = Groq(api_key=key)
        raw_content, used_model, total_tokens = self._call_groq_safe(
            client, messages, max_tokens=token_cap
        )

        payload = _extract_json_payload(raw_content)

        should_update = bool(payload.get("update_card") or payload.get("update_spec_card"))
        parsed_primary = _parse_phone_card(payload.get("phone_card"))
        parsed_compare = _parse_phone_card(payload.get("compare_card"))

        updated_primary: Optional[PhoneCardData] = None
        updated_compare: Optional[PhoneCardData] = None

        if parsed_primary and (should_update or self.current_card is None or is_compare_req):
            self.current_card = parsed_primary
            updated_primary = parsed_primary

        if parsed_compare:
            self.compare_card = parsed_compare
            updated_compare = parsed_compare

        raw_reply = str(payload.get("chat_reply") or "").strip()
        raw_reply = raw_reply.replace('\\"', '"')
        # Fix inline bullet lists like "• Item A • Item B" into clean multi-line bullets
        raw_reply = re.sub(r"\s+•\s+", "\n- ", raw_reply)
        if not raw_reply:
            raw_reply = _synthesize_fallback_summary(
                updated_primary or self.current_card,
                updated_compare or (self.compare_card if is_compare_req else None),
            )

        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": raw_reply})

        sources = [
            {"title": s.title, "url": s.url}
            for s in search_bundle.sources[:3]
            if s.title
        ]
        return TurnResponse(
            chat_reply=raw_reply,
            updated_card=updated_primary,
            updated_compare_card=updated_compare,
            used_web_search=search_bundle.used_search,
            search_sources=sources,
            model_used=used_model,
            tokens_used=total_tokens,
        )

    def _call_groq_safe(
        self,
        client: Groq,
        messages: List[Dict[str, str]],
        max_tokens: int = 1050,
    ) -> Tuple[str, str, int]:
        candidates = [self.model] + [m for m in DEFAULT_MODELS if m != self.model]
        last_exc: Optional[Exception] = None

        for idx, candidate in enumerate(candidates):
            try:
                comp = client.chat.completions.create(
                    model=candidate,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=0.25,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                content = comp.choices[0].message.content or "{}"
                used_tok = getattr(getattr(comp, "usage", None), "total_tokens", 0) or 0
                self.model = candidate
                return content, candidate, int(used_tok)
            except Exception as exc:
                err_str = str(exc).lower()
                last_exc = exc

                if "response_format" in err_str or "json_validate_failed" in err_str:
                    try:
                        comp = client.chat.completions.create(
                            model=candidate,
                            messages=messages,  # type: ignore[arg-type]
                            temperature=0.25,
                            max_tokens=max_tokens,
                        )
                        content = comp.choices[0].message.content or "{}"
                        used_tok = getattr(getattr(comp, "usage", None), "total_tokens", 0) or 0
                        self.model = candidate
                        return content, candidate, int(used_tok)
                    except Exception as inner_exc:
                        last_exc = inner_exc
                        err_str = str(inner_exc).lower()

                if any(k in err_str for k in ("invalid_api_key", "401", "authentication")):
                    raise exc

                if "429" in err_str or "rate_limit" in err_str:
                    time.sleep(1.5)
                    continue

                if idx == 0 and any(k in err_str for k in ("decommissioned", "not found", "does not exist")):
                    try:
                        for lm in fetch_groq_models(self.api_key):
                            if lm not in candidates:
                                candidates.append(lm)
                    except Exception:
                        pass
                    continue

        if last_exc:
            raise last_exc
        raise RuntimeError("No response from Groq API.")

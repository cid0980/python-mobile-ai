"""
ai_engine.py — Token-Efficient Groq Engine, Memory & Side-by-Side Spec Parser
Engineered with strict prompt budgeting (~650–1,100 tokens/turn) and automatic
429 rate-limit rotation so continuous chatting never hits Groq API limits.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq

from web_search import SearchBundle, search_phone_facts

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Ordered with high-TPM production Groq models
DEFAULT_MODELS: List[str] = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

EXCLUDED_MODEL_KEYWORDS = (
    "whisper", "guard", "safeguard", "tts", "orpheus", "embed", "vision-preview", "playai",
)


@dataclass
class PhoneCardData:
    name: str = ""
    brand: str = ""
    tagline: str = ""
    launch_date: str = "Unknown"
    status: str = "Released"
    price_estimate: str = "Check retail"
    specs: Dict[str, str] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)
    good_for: List[str] = field(default_factory=list)
    skip_if: List[str] = field(default_factory=list)
    verdict_one_liner: str = ""

    def to_markdown(self) -> str:
        lines = [
            f"# {self.name}",
            f"*{self.tagline}*" if self.tagline else "",
            "",
            f"- **Brand:** {self.brand or 'N/A'}",
            f"- **Status:** {self.status}",
            f"- **Launch:** {self.launch_date}",
            f"- **Price:** {self.price_estimate}",
            "",
            "## Specifications",
        ]
        spec_labels = [
            ("display", "Display"),
            ("processor", "Processor"),
            ("ram_storage", "Memory & Storage"),
            ("rear_camera", "Rear Camera"),
            ("front_camera", "Front Camera"),
            ("battery_charging", "Battery & Charging"),
            ("os_updates", "Software"),
            ("build_extras", "Build & Connectivity"),
        ]
        for key, label in spec_labels:
            lines.append(f"- **{label}:** {self.specs.get(key, 'N/A')}")

        if self.scores:
            lines.extend(["", "## Ratings (0–10)"])
            for k, v in self.scores.items():
                lines.append(f"- **{k.capitalize()}:** {v:.1f} / 10")

        if self.good_for:
            lines.extend(["", "## Best For"])
            for item in self.good_for:
                lines.append(f"- {item}")

        if self.skip_if:
            lines.extend(["", "## Trade-offs"])
            for item in self.skip_if:
                lines.append(f"- {item}")

        if self.verdict_one_liner:
            lines.extend(["", f"**Summary:** {self.verdict_one_liner}"])

        return "\n".join(line for line in lines if line is not None)


DEMO_PHONE_CARD = PhoneCardData(
    name="Samsung Galaxy S26 Ultra",
    brand="Samsung",
    tagline="6.9-inch Titanium Android Flagship with S-Pen",
    launch_date="Feb 2026 (Released Mar 2026)",
    status="Available",
    price_estimate="$1,299 / ₹1,29,999",
    specs={
        "display": '6.9" LTPO AMOLED 2X, QHD+, 1–120Hz, Gorilla Armor',
        "processor": "Snapdragon 8 Elite Gen 5 (3nm)",
        "ram_storage": "12GB / 16GB RAM · 256GB / 512GB / 1TB UFS 4.0",
        "rear_camera": "200MP Main + 50MP UW + 50MP (5x) + 10MP (3x)",
        "front_camera": "12MP Dual-Pixel AF (4K 60fps)",
        "battery_charging": "5000 mAh · 45W Wired / 15W Qi2 Wireless",
        "os_updates": "Android 16 (One UI 8) · 7 Years Updates",
        "build_extras": "Titanium Frame, IP68, S-Pen, Wi-Fi 7, UWB",
    },
    scores={"performance": 9.8, "camera": 9.6, "display": 9.8, "battery": 8.9, "value": 8.1},
    good_for=[
        "Sustained 120fps gaming & heavy multitasking",
        "Long-range optical zoom & night photography",
        "S-Pen productivity & 7-year software support",
    ],
    skip_if=[
        "Prefer compact one-handed phones",
        "Want ultra-fast 80W–100W wired charging",
    ],
    verdict_one_liner="Complete flagship all-rounder built for power users, creators, and long-term ownership.",
)

DEMO_COMPARE_CARD = PhoneCardData(
    name="iPhone 16 Pro Max",
    brand="Apple",
    tagline="6.9-inch Titanium iOS Flagship for Video & Efficiency",
    launch_date="Sep 2024",
    status="Available",
    price_estimate="$1,199 / ₹1,44,900",
    specs={
        "display": '6.9" Super Retina XDR OLED, 1–120Hz ProMotion',
        "processor": "Apple A18 Pro (3nm)",
        "ram_storage": "8GB RAM · 256GB / 512GB / 1TB NVMe",
        "rear_camera": "48MP Main + 48MP UW + 12MP (5x Tetraprism)",
        "front_camera": "12MP TrueDepth OIS (4K 60fps Dolby Vision)",
        "battery_charging": "4685 mAh · ~30W Wired / 25W MagSafe",
        "os_updates": "iOS 18+ · 6+ Years Updates",
        "build_extras": "Grade 5 Titanium, IP68, Camera Control, Face ID",
    },
    scores={"performance": 9.6, "camera": 9.5, "display": 9.5, "battery": 9.4, "value": 8.0},
    good_for=[
        "Class-leading ProRes / 4K120 video recording",
        "Top-tier battery endurance & standby efficiency",
        "Seamless Apple ecosystem integration",
    ],
    skip_if=[
        "Slow wired charging compared to Android rivals",
        "Prefer universal sideloading or stylus support",
    ],
    verdict_one_liner="Unmatched video consistency and battery efficiency for iOS users.",
)


@dataclass
class TurnResponse:
    chat_reply: str
    updated_card: Optional[PhoneCardData]
    updated_compare_card: Optional[PhoneCardData]
    used_web_search: bool
    search_sources: List[Tuple[str, str]] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0


# Compact prompt (~220 tokens) to keep API usage ultra-low on every chat turn
SYSTEM_PROMPT = """You are SpecDeck, a precise smartphone hardware analyst (current year: 2026).
Trust WEB FACTS when provided for exact launch dates, chipsets, batteries, and prices.

Return ONLY valid JSON:
{
  "update_card": true/false,
  "phone_card": { ... } or null,
  "compare_card": { ... } or null,
  "chat_reply": "..."
}

Card object format (use when update_card=true or when comparing two phones):
{"name":"","brand":"","tagline":"","launch_date":"","status":"Available|Upcoming","price_estimate":"","specs":{"display":"","processor":"","ram_storage":"","rear_camera":"","front_camera":"","battery_charging":"","os_updates":"","build_extras":""},"scores":{"performance":8.5,"camera":8.5,"display":8.5,"battery":8.5,"value":8.5},"good_for":["..."],"skip_if":["..."],"verdict_one_liner":""}

Rules:
- First phone lookup or switching phones: set update_card=true and fill phone_card; set compare_card=null.
- Follow-up about current phone: set update_card=false, phone_card=null, compare_card=null; answer directly in chat_reply without repeating the whole spec sheet.
- Comparing two phones ("compare with Y" or "X vs Y"): fill compare_card with the second phone (and fill phone_card too if no active phone or if X is new).
- Keep chat_reply clean, concise, plain text with short bullet points (•). No markdown tables or ** asterisks."""


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


def _clean_chat_formatting(text: str) -> str:
    if not text:
        return ""
    cleaned_lines: List[str] = []
    for line in text.splitlines():
        heading_match = re.match(r"^\s*#{1,4}\s+(.*)$", line)
        if heading_match:
            cleaned_lines.append(heading_match.group(1).strip().strip("*").upper())
            continue
        bullet_match = re.match(r"^(\s*)[-\*]\s+(.*)$", line)
        if bullet_match:
            indent, rest = bullet_match.groups()
            line = f"{indent}• {rest}"
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"__(.*?)__", r"\1", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _clamp_score(val: Any, default: float = 8.0) -> float:
    try:
        return max(0.0, min(10.0, round(float(val), 1)))
    except (TypeError, ValueError):
        return default


def _parse_phone_card(raw_card: Any) -> Optional[PhoneCardData]:
    if not isinstance(raw_card, dict):
        return None
    name = str(raw_card.get("name") or "").strip()
    if not name:
        return None

    raw_specs = raw_card.get("specs") if isinstance(raw_card.get("specs"), dict) else {}
    specs = {
        "display": str(raw_specs.get("display") or "—"),
        "processor": str(raw_specs.get("processor") or "—"),
        "ram_storage": str(raw_specs.get("ram_storage") or "—"),
        "rear_camera": str(raw_specs.get("rear_camera") or "—"),
        "front_camera": str(raw_specs.get("front_camera") or "—"),
        "battery_charging": str(raw_specs.get("battery_charging") or "—"),
        "os_updates": str(raw_specs.get("os_updates") or "—"),
        "build_extras": str(raw_specs.get("build_extras") or "—"),
    }

    raw_scores = raw_card.get("scores") if isinstance(raw_card.get("scores"), dict) else {}
    scores = {
        "performance": _clamp_score(raw_scores.get("performance"), 8.0),
        "camera": _clamp_score(raw_scores.get("camera"), 8.0),
        "display": _clamp_score(raw_scores.get("display"), 8.0),
        "battery": _clamp_score(raw_scores.get("battery"), 8.0),
        "value": _clamp_score(raw_scores.get("value"), 8.0),
    }

    good_for = [str(x).strip() for x in (raw_card.get("good_for") or []) if str(x).strip()][:4]
    skip_if = [str(x).strip() for x in (raw_card.get("skip_if") or []) if str(x).strip()][:3]

    return PhoneCardData(
        name=name,
        brand=str(raw_card.get("brand") or "").strip(),
        tagline=str(raw_card.get("tagline") or "").strip(),
        launch_date=str(raw_card.get("launch_date") or "Unknown").strip(),
        status=str(raw_card.get("status") or "Released").strip(),
        price_estimate=str(raw_card.get("price_estimate") or "Check retail").strip(),
        specs=specs,
        scores=scores,
        good_for=good_for,
        skip_if=skip_if,
        verdict_one_liner=str(raw_card.get("verdict_one_liner") or "").strip(),
    )


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    for candidate in (cleaned,):
        try:
            data = json.loads(candidate)
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


class SpecDeckAssistant:
    """Rate-limit-conscious Smartphone AI Engine with single & comparison states."""

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

    def clear_comparison(self) -> None:
        self.compare_card = None

    def send_message(
        self,
        user_message: str,
        use_web_search: bool = True,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> TurnResponse:
        key = self.api_key.strip()
        if not key:
            raise ValueError(
                "No Groq API key configured. Click 'API Key' in the toolbar, paste your "
                "key from console.groq.com/keys, and click Save."
            )

        active_name = self.current_card.name if self.current_card else None
        comp_name = self.compare_card.name if self.compare_card else None
        search_bundle = SearchBundle(used_search=False)

        if use_web_search:
            if status_callback:
                status_callback("Searching live specifications...")
            search_bundle = search_phone_facts(
                user_message,
                active_phone=active_name,
                compare_phone=comp_name,
                max_total_results=4,
            )

        if status_callback:
            status_callback(f"Generating response ({self.model})...")

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Compact state summary (~40 tokens max)
        if self.current_card:
            ctx = (
                f"Active phone: {self.current_card.name} ({self.current_card.launch_date}, "
                f"{self.current_card.price_estimate}, {self.current_card.specs.get('processor', '')})."
            )
            if self.compare_card:
                ctx += f" Compared with: {self.compare_card.name} ({self.compare_card.price_estimate})."
            messages.append({"role": "system", "content": ctx})

        # Keep rolling window of last 6 messages (trimmed to save tokens)
        for msg in self.chat_history[-6:]:
            content = msg["content"]
            if len(content) > 450:
                content = content[:450] + "…"
            messages.append({"role": msg["role"], "content": content})

        if search_bundle.used_search and search_bundle.context_text:
            user_payload = f"{user_message}\n\n{search_bundle.context_text}"
        else:
            user_payload = user_message

        messages.append({"role": "user", "content": user_payload})

        is_compare_req = bool(
            re.search(r"\b(?:vs\.?|versus|compare|comparison)\b", user_message, flags=re.I)
        )
        token_cap = 1250 if is_compare_req else 900

        client = Groq(api_key=key)
        raw_content, used_model, total_tokens = self._call_groq_safe(
            client, messages, max_tokens=token_cap
        )

        payload = _extract_json_payload(raw_content)
        raw_reply = str(payload.get("chat_reply") or "").strip()
        if not raw_reply:
            raw_reply = "Specifications updated in the panel on the left."
        clean_reply = _clean_chat_formatting(raw_reply)

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

        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": clean_reply})

        source_pairs = [(s.title, s.url) for s in search_bundle.sources[:3]]
        return TurnResponse(
            chat_reply=clean_reply,
            updated_card=updated_primary,
            updated_compare_card=updated_compare,
            used_web_search=search_bundle.used_search,
            search_sources=source_pairs,
            model_used=used_model,
            tokens_used=total_tokens,
        )

    def _call_groq_safe(
        self,
        client: Groq,
        messages: List[Dict[str, str]],
        max_tokens: int = 900,
    ) -> Tuple[str, str, int]:
        """
        Execute Groq completion with automatic 429 rate-limit backoff & model rotation,
        plus fallback for deprecated models or non-JSON-mode models.
        """
        candidates = [self.model] + [m for m in DEFAULT_MODELS if m != self.model]
        last_exc: Optional[Exception] = None

        for idx, candidate in enumerate(candidates):
            try:
                comp = client.chat.completions.create(
                    model=candidate,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=0.3,
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

                # Retry without json_object if model rejected response_format
                if "response_format" in err_str or "json_validate_failed" in err_str:
                    try:
                        comp = client.chat.completions.create(
                            model=candidate,
                            messages=messages,  # type: ignore[arg-type]
                            temperature=0.3,
                            max_tokens=max_tokens,
                        )
                        content = comp.choices[0].message.content or "{}"
                        used_tok = getattr(getattr(comp, "usage", None), "total_tokens", 0) or 0
                        self.model = candidate
                        return content, candidate, int(used_tok)
                    except Exception as inner_exc:
                        last_exc = inner_exc
                        err_str = str(inner_exc).lower()

                # Auth errors should fail immediately with clear message
                if any(k in err_str for k in ("invalid_api_key", "401", "authentication")):
                    raise exc

                # On 429 rate-limit, wait briefly and rotate to next high-TPM model
                if "429" in err_str or "rate_limit" in err_str:
                    time.sleep(1.5)
                    continue

                # On decommissioned/missing model, pull live account models once
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

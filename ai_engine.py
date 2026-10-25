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
    name="OnePlus 13",
    brand="OnePlus",
    tagline="6000mAh Silicon-Carbon Flagship · Snapdragon 8 Elite & 100W SuperVOOC",
    launch_date="Jan 2025",
    status="Available",
    price_estimate="$899 / ₹69,999",
    specs={
        "display": '6.82" LTPO 4.1 AMOLED · QHD+ · 1–120Hz · 4500 nits',
        "processor": "Snapdragon 8 Elite (3nm)",
        "ram_storage": "12GB / 16GB / 24GB LPDDR5X · 256GB / 512GB / 1TB UFS 4.0",
        "rear_camera": "50MP LYT-808 OIS + 50MP 3x Triprism + 50MP UW (Hasselblad)",
        "front_camera": "32MP Sony IMX615 (4K 60fps)",
        "battery_charging": "6000 mAh Si/C · 100W Wired / 50W Wireless",
        "os_updates": "Android 15 (OxygenOS 15) · 4 Years OS / 6 Years Security",
        "build_extras": "Aluminum Frame · Ceramic Guard · IP68 + IP69 · Alert Slider",
    },
    scores={"performance": 9.7, "camera": 9.0, "display": 9.5, "battery": 9.7, "value": 9.3},
    good_for=[
        "Two-day 6000mAh endurance with 36-minute 100W full charge",
        "Sustained 120fps gaming with dual-cryo vapor chamber cooling",
        "Flagship silicon priced $300–$400 under Ultra competitors",
    ],
    skip_if=[
        "Need 5x–10x optical periscope zoom for distant subjects",
        "Require 7 years of major OS version upgrades",
    ],
    verdict_one_liner="High-value flagship pairing Snapdragon 8 Elite speed with class-leading 6000mAh battery life and 100W charging.",
)

DEMO_COMPARE_CARD = PhoneCardData(
    name="iPhone 16 Pro Max",
    brand="Apple",
    tagline="6.9-inch Grade 5 Titanium Flagship · A18 Pro & 4K120 Dolby Vision",
    launch_date="Sep 2024",
    status="Available",
    price_estimate="$1,199 / ₹1,44,900",
    specs={
        "display": '6.9" LTPO Super Retina XDR OLED · 1–120Hz · 2000 nits',
        "processor": "Apple A18 Pro (3nm)",
        "ram_storage": "8GB LPDDR5X · 256GB / 512GB / 1TB NVMe",
        "rear_camera": "48MP Fusion OIS + 48MP UW + 12MP 5x Tetraprism OIS",
        "front_camera": "12MP TrueDepth PDAF OIS (4K 60fps)",
        "battery_charging": "4685 mAh · 30W USB-C PD / 25W MagSafe Qi2",
        "os_updates": "iOS 18 · 6+ Years iOS Feature & Security Support",
        "build_extras": "Grade 5 Titanium · Ceramic Shield · IP68 (6m) · Camera Control",
    },
    scores={"performance": 9.8, "camera": 9.6, "display": 9.6, "battery": 9.3, "value": 8.3},
    good_for=[
        "Industry-reference 4K 120fps ProRes & Dolby Vision video",
        "Single-core speed, ecosystem longevity, and strong resale value",
        "Consistent 5x tetraprism telephoto and skin-tone rendering",
    ],
    skip_if=[
        "Want ultra-fast 80W–100W wired charging speeds",
        "Prefer high-RAM Android multitasking at a lower price",
    ],
    verdict_one_liner="Benchmark video and performance flagship with long-term iOS support and titanium build quality.",
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


SYSTEM_PROMPT = """You are SpecDeck, an authoritative smartphone hardware advisor (current year: 2026).
Combine WEB SEARCH REFERENCE SNIPPETS with your complete smartphone hardware knowledge so every specification field is accurate and complete. Never write "Not specified" or "(details not listed)" for released phones; provide exact chipset, sensor MP, battery mAh + charging watts, OS policy, and launch price ($ USD / ₹ INR).

Respond with ONLY one valid JSON object matching this exact structure:
{
  "update_card": true,
  "phone_card": {
    "name": "Full Official Phone Name",
    "brand": "Brand",
    "tagline": "Short hardware positioning line",
    "launch_date": "Mon YYYY",
    "status": "Available",
    "price_estimate": "$XXX / ₹XX,XXX",
    "specs": {
      "display": "",
      "processor": "",
      "ram_storage": "",
      "rear_camera": "",
      "front_camera": "",
      "battery_charging": "",
      "os_updates": "",
      "build_extras": ""
    },
    "scores": {"performance": 9.0, "camera": 8.8, "display": 9.0, "battery": 9.0, "value": 8.5},
    "good_for": ["Strength 1", "Strength 2", "Strength 3"],
    "skip_if": ["Trade-off 1", "Trade-off 2"],
    "verdict_one_liner": "One sentence summary."
  },
  "compare_card": null,
  "chat_reply": "Concise natural response for the right panel."
}

Rules:
1. Whenever the user mentions, asks about, or searches for ANY specific phone (or asks for a phone recommendation — pick the #1 best phone for phone_card), ALWAYS set "update_card": true and populate "phone_card" completely so the left panel updates immediately.
2. When comparing two phones ("X vs Y" or "compare with Y"), populate BOTH "phone_card" (Phone A) and "compare_card" (Phone B) completely.
3. Only set "update_card": false and "phone_card": null on casual greetings ("hello", "thanks") or follow-up questions about the exact phone ALREADY active on the left panel.
4. Keep "chat_reply" concise, natural, and directly informative (3 to 5 clear sentences or brief bullets): give a quick contextual overview of what the user asked, highlight key real-world strengths/trade-offs, and give a clear recommendation without repeating the raw spec table."""


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

    out_lines = [f"{k}={v}" for k, v in existing.items()] + [""]
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
    if not name or name == "—":
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


def _strip_reasoning_and_fences(raw_text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.S | re.I).strip()
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _try_parse_json_dict(raw_text: str) -> Optional[Dict[str, Any]]:
    cleaned = _strip_reasoning_and_fences(raw_text)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _looks_like_raw_json(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if s.startswith("{") or s.startswith('{"'):
        return True
    if '"update_card"' in s or '"phone_card"' in s or '"chat_reply"' in s:
        return True
    return False


def _synthesize_fallback_summary(
    primary: Optional[PhoneCardData], compare: Optional[PhoneCardData]
) -> str:
    if primary and compare:
        return (
            f"**{primary.name}** ({primary.price_estimate}) faces **{compare.name}** ({compare.price_estimate}) in this comparison.\n"
            f"- **Performance & Display:** {primary.name} runs {primary.specs.get('processor', 'flagship silicon')}, while {compare.name} uses {compare.specs.get('processor', 'competing silicon')}.\n"
            f"- **Battery & Camera:** {primary.name} offers {primary.specs.get('battery_charging', '—')}; {compare.name} counters with {compare.specs.get('rear_camera', '—')}.\n"
            f"- **Bottom Line:** {primary.verdict_one_liner or ''} {compare.verdict_one_liner or ''}"
        ).strip()
    if primary:
        strength = primary.good_for[0] if primary.good_for else primary.specs.get("processor", "")
        tradeoff = primary.skip_if[0] if primary.skip_if else ""
        extra = f" Keep in mind: {tradeoff.lower()}." if tradeoff else ""
        return (
            f"**{primary.name}** ({primary.launch_date} · {primary.price_estimate}) is loaded in the datasheet on the left.\n"
            f"- **Key Highlight:** {strength}.\n"
            f"- **Core Hardware:** {primary.specs.get('display', '—')} paired with {primary.specs.get('processor', '—')} and {primary.specs.get('battery_charging', '—')}.\n"
            f"- **Verdict:** {primary.verdict_one_liner}{extra}"
        ).strip()
    return "Ask about any smartphone model or head-to-head comparison to load its full specifications and image."


class SpecDeckAssistant:
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
                "No Groq API key configured. Open Settings (top-right gear icon), "
                "paste your key from console.groq.com/keys, and click Save Changes."
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
                f"Currently displayed on left panel: {self.current_card.name} "
                f"({self.current_card.launch_date}, {self.current_card.price_estimate}, "
                f"{self.current_card.specs.get('processor', '')}). "
                f"If the user is asking about a DIFFERENT phone, you MUST set update_card=true and populate phone_card for the new phone."
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

        client = Groq(api_key=key)
        payload, used_model, total_tokens = self._call_groq_structured(
            client, messages, max_tokens=4096
        )

        parsed_primary = _parse_phone_card(payload.get("phone_card"))
        parsed_compare = _parse_phone_card(payload.get("compare_card"))

        updated_primary: Optional[PhoneCardData] = None
        updated_compare: Optional[PhoneCardData] = None

        if parsed_primary is not None:
            self.current_card = parsed_primary
            updated_primary = parsed_primary

        if parsed_compare is not None:
            self.compare_card = parsed_compare
            updated_compare = parsed_compare
        elif updated_primary is not None and not is_compare_req:
            self.compare_card = None

        raw_reply = str(payload.get("chat_reply") or "").strip()
        raw_reply = raw_reply.replace('\\"', '"')
        raw_reply = re.sub(r"\s+•\s+", "\n- ", raw_reply)

        if not raw_reply or _looks_like_raw_json(raw_reply):
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

    def _call_groq_structured(
        self,
        client: Groq,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
    ) -> Tuple[Dict[str, Any], str, int]:
        candidates = [self.model] + [m for m in DEFAULT_MODELS if m != self.model]
        last_exc: Optional[Exception] = None

        for idx, candidate in enumerate(candidates):
            for use_json_mode in (True, False):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": candidate,
                        "messages": messages,
                        "temperature": 0.25,
                        "max_tokens": max_tokens,
                    }
                    if use_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    comp = client.chat.completions.create(**kwargs)
                    content = comp.choices[0].message.content or ""
                    used_tok = getattr(getattr(comp, "usage", None), "total_tokens", 0) or 0
                    parsed = _try_parse_json_dict(content)
                    if parsed is not None:
                        self.model = candidate
                        return parsed, candidate, int(used_tok)
                    if not use_json_mode and content.strip() and not _looks_like_raw_json(content):
                        self.model = candidate
                        return {
                            "update_card": False,
                            "phone_card": None,
                            "compare_card": None,
                            "chat_reply": _strip_reasoning_and_fences(content),
                        }, candidate, int(used_tok)
                except Exception as exc:
                    err_str = str(exc).lower()
                    last_exc = exc

                    if any(k in err_str for k in ("invalid_api_key", "401", "authentication")):
                        raise exc

                    if use_json_mode and ("response_format" in err_str or "json_validate_failed" in err_str):
                        continue

                    if "429" in err_str or "rate_limit" in err_str:
                        time.sleep(1.2)
                        break

                    if idx == 0 and any(k in err_str for k in ("decommissioned", "not found", "does not exist")):
                        try:
                            for lm in fetch_groq_models(self.api_key):
                                if lm not in candidates:
                                    candidates.append(lm)
                        except Exception:
                            pass
                        break
                    break

        if last_exc:
            raise last_exc
        raise RuntimeError("No valid structured response received from Groq API.")

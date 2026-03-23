import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path

import aiohttp

from app.core.config import settings
from app.core.state import GlobalState

_SD_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
_ICONS_DIR = settings.DATA_DIR / "icons"           # template lives here
_TEMPLATE_PATH = _ICONS_DIR / "templates" / "icon_sample.png"
_SESSIONS_DIR = settings.SESSIONS_DIR
_LOG_DIR = settings.BASE_DIR / "logs" / "artist"


def _write_log(
    prompt: str,
    negative_prompt: str,
    output_path: str | None,
    error: str | None = None,
    timing: dict | None = None,
    tokens: dict | None = None,
):
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]  # YYYYmmdd_HHMMSS_ms
    log_path = _LOG_DIR / f"{timestamp}.json"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "output_path": output_path,
        "error": error,
        "timing_secs": timing,
        "tokens": tokens,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)
    return log_path

_NEGATIVE_PROMPT = (
    "photorealistic, realistic, cartoon, lowres, text, error, cropped, worst quality, "
    "low quality, jpeg artifacts, signature, watermark, username, blurry, noise, "
    "anti-aliasing, human, people, person, character, animal, creature, bad anatomy, "
    "multiple products, multiple views, messy edges, rough texture"
)

_THEME_STYLE_MAP = {
    "fire":    "glowing ember, red-orange flame aura",
    "ice":     "frosty, icy blue crystal edges",
    "poison":  "sickly green, dripping venom",
    "shadow":  "dark purple aura, void energy",
    "thunder": "crackling lightning, electric sparks",
    "dark":    "ominous black energy, dark aura",
    "holy":    "golden radiance, divine glow",
    "wind":    "swirling air currents, cyan trails",
}


def _build_prompt(concept: dict) -> str:
    keywords = concept.get("keywords", [])
    codename = concept.get("codename", "weapon")
    visual   = concept.get("visual_manifest", "")

    # Map theme keywords to visual style descriptors
    style_parts = []
    for kw in keywords:
        kw_lower = kw.lower()
        for theme, style in _THEME_STYLE_MAP.items():
            if theme in kw_lower:
                style_parts.append(style)
                break

    style_str = ", ".join(style_parts) if style_parts else "magical glow"

    # Weapon shape hint from visual_manifest (first 60 chars, sanitised)
    shape_hint = re.sub(r"[^a-zA-Z0-9 ,'-]", "", visual)[:60].strip()

    return (
        f"<lora:pixel sprites:1>, "
        f"a clean 2D pixel art sprite of a weapon, specifically a {shape_hint}, "
        f"{style_str}, fantasy weapon design, game prop, "
        f"perfectly centered, vertical orientation, "
        f"pure solid white background, no shadows, flat lighting, "
        f"single item, game asset"
    )


def _load_template_b64() -> str | None:
    if not _TEMPLATE_PATH.exists():
        return None
    with open(_TEMPLATE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _save_icon(image_b64: str, weapon_id: str, session_id: str) -> Path:
    session_dir = _SESSIONS_DIR / session_id / "icons"
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"{weapon_id}.png"
    with open(path, "wb") as f:
        f.write(base64.b64decode(image_b64))
    return path


async def _call_sd(prompt: str, template_b64: str | None) -> str | None:
    """POST to SD txt2img, return base64 image string or None on failure."""
    payload: dict = {
        "prompt":          prompt,
        "negative_prompt": _NEGATIVE_PROMPT,
        "steps":           25,
        "width":           512,
        "height":          512,
        "cfg_scale":       8.5,
        "sampler_name":    "Euler a",
        "seed":            -1,
    }

    if template_b64:
        payload["alwayson_scripts"] = {
            "ControlNet": {
                "args": [{
                    "input_image":    template_b64,
                    "module":         "canny",
                    "model":          "control_v11p_sd15_canny",
                    "weight":         1.0,
                    "resize_mode":    "Just Resize",
                    "control_mode":   "ControlNet is more important",
                    "guidance_start": 0.0,
                    "guidance_end":   1.0,
                }]
            }
        }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            _SD_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"SD API returned {resp.status}: {text[:200]}")
            data = await resp.json()
            images = data.get("images")
            if not images:
                raise RuntimeError("SD API returned no images")
            return images[0]


class ArtistAgent:
    async def generate_icon_node(self, state: GlobalState) -> dict:
        concept   = state.get("design_concept") or {}
        codename  = concept.get("codename", "unknown")
        weapon_id = (state.get("final_output") or {}).get("id") or codename.lower().replace(" ", "_")
        session_id = state.get("session_id") or "default"

        print(f"[Artist] Generating icon for: {codename} (session={session_id})")

        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        prompt = _build_prompt(concept)
        t_prompt_build = time.perf_counter() - t0

        t0 = time.perf_counter()
        template_b64 = _load_template_b64()
        t_template_load = time.perf_counter() - t0

        if template_b64 is None:
            print("[Artist] ⚠️  Template not found — generating without ControlNet.")

        # Rough CLIP token estimate: SD tokenizes by word/subword (~1 word ≈ 1-1.5 tokens)
        tokens = {
            "prompt_words": len(prompt.split()),
            "negative_prompt_words": len(_NEGATIVE_PROMPT.split()),
            "prompt_chars": len(prompt),
        }

        try:
            t0 = time.perf_counter()
            image_b64 = await _call_sd(prompt, template_b64)
            t_sd_call = time.perf_counter() - t0

            t0 = time.perf_counter()
            icon_path = _save_icon(image_b64, weapon_id, session_id)
            t_save = time.perf_counter() - t0

            timing = {
                "prompt_build": round(t_prompt_build, 3),
                "template_load": round(t_template_load, 3),
                "sd_call": round(t_sd_call, 3),
                "save_icon": round(t_save, 3),
                "total": round(time.perf_counter() - t_total_start, 3),
            }
            log = _write_log(prompt, _NEGATIVE_PROMPT, str(icon_path), timing=timing, tokens=tokens)
            print(f"[Artist] ✅ Icon saved: {icon_path} | sd={t_sd_call:.1f}s total={timing['total']:.1f}s | log: {log.name}")
            return {
                "generated_icon":      str(icon_path),
                "generated_icon_b64":  image_b64,
            }
        except Exception as e:
            timing = {"total": round(time.perf_counter() - t_total_start, 3)}
            log = _write_log(prompt, _NEGATIVE_PROMPT, output_path=None, error=str(e), timing=timing, tokens=tokens)
            print(f"[Artist] ❌ Generation failed: {e} — log: {log.name} — falling back to default icon.")
            return {"generated_icon": "weapon_axe.png", "generated_icon_b64": None}


artist_agent = ArtistAgent()

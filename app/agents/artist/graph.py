import base64
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path

import aiohttp
import numpy as np
from PIL import Image
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.state import GlobalState
from app.services.llm_service import llm_service
from app.utils.callbacks import make_callbacks


class IconSelection(BaseModel):
    selected_filename: str = Field(description="Exact filename from the available list, e.g. 'sword_long.png'")
    reasoning: str = Field(description="One sentence: why this base image fits the weapon concept.")

_ICON_OUTPUT_SIZE = 128
_WHITE_THRESH     = 240   # pixels with all RGB channels >= this are treated as background


def _crop_and_resize(path: Path, size: int = _ICON_OUTPUT_SIZE, padding: int = 4) -> bytes:
    """
    Auto-crop transparent or white-background weapon sprite, then resize to size×size PNG.
    Returns raw PNG bytes.
    """
    img = Image.open(path).convert("RGBA")

    # Try alpha-channel crop first
    bbox = img.split()[3].getbbox()

    # Fallback: white-background crop via numpy
    if bbox is None:
        arr  = np.array(img.convert("RGB"))
        mask = np.any(arr < _WHITE_THRESH, axis=2)
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if rows.any():
            top    = int(np.argmax(rows))
            bottom = int(len(rows) - 1 - np.argmax(rows[::-1]))
            left   = int(np.argmax(cols))
            right  = int(len(cols) - 1 - np.argmax(cols[::-1]))
            bbox   = (left, top, right + 1, bottom + 1)

    if bbox:
        w, h = img.size
        l, t, r, b = bbox
        l, t = max(0, l - padding), max(0, t - padding)
        r, b = min(w, r + padding), min(h, b + padding)
        img = img.crop((l, t, r, b))
        print(f"[Artist] crop {w}x{h} → {r-l}x{b-t} → {size}x{size}")
    else:
        print(f"[Artist] no content bbox found, resizing original to {size}x{size}")

    crop_w, crop_h = img.size
    resample = Image.NEAREST if (crop_w >= size and crop_h >= size) else Image.LANCZOS
    img = img.resize((size, size), resample)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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


_ICON_SELECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a weapon art director. Select the single best-matching base sprite for the given weapon.\n"
     "You MUST choose a filename that exists EXACTLY in the available list — do not invent or modify names.\n\n"
     "SELECTION PRIORITY (apply in order):\n"
     "1. If any word in the weapon name appears in a filename (e.g. 'arrow' → 'arrow.png'), pick that file immediately.\n"
     "2. Otherwise match by weapon shape/type (sword, axe, spear, bow, staff…).\n"
     "3. Never let gameplay mechanics (pierce, burn, etc.) override the visual shape.\n\n"
     "Available base images:\n{filenames}"),
    ("human",
     "Weapon name: {name}\n"
     "Visual description: {visual_manifest}\n"
     "Theme keywords: {keywords}"),
])


class ArtistAgent:
    def __init__(self):
        self._icon_select_chain = (
            _ICON_SELECT_PROMPT
            | llm_service.get_structured_model("artist", IconSelection)
        )

    async def generate_icon_node(self, state: GlobalState, config: RunnableConfig | None = None) -> dict:
        if settings.ARTIST_MODE == "composite":
            return await self._composite_node(state, config)
        return await self._sd_node(state)

    async def _composite_node(self, state: GlobalState, config: RunnableConfig | None = None) -> dict:
        """
        Composite mode: LLM picks the best base sprite from app/data/baseimg/.
        Unity applies visual_stats.tint_color at runtime.
        """
        concept      = state.get("design_concept") or {}
        final_output = state.get("final_output") or {}

        # Collect available base images
        base_images = sorted(
            p.name for p in settings.BASEIMG_DIR.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ) if settings.BASEIMG_DIR.exists() else []

        if not base_images:
            print("[Artist/Composite] ⚠️  No base images in baseimg/ — using fallback.")
            return {"generated_icon": "weapon_axe.png", "generated_icon_b64": None}

        filenames_str = "\n".join(f"  - {name}" for name in base_images)

        try:
            selection: IconSelection = await self._icon_select_chain.ainvoke({
                "filenames":       filenames_str,
                "name":            final_output.get("name") or concept.get("codename", "weapon"),
                "visual_manifest": concept.get("visual_manifest", ""),
                "keywords":        ", ".join(concept.get("keywords", [])),
            }, config={"callbacks": make_callbacks("Artist", state.get("session_id", "default"), config)})
            icon_filename = selection.selected_filename
            print(f"[Artist/Composite] LLM selected: {icon_filename} | reason: {selection.reasoning}")
        except Exception as e:
            print(f"[Artist/Composite] LLM selection failed: {e} — using fallback.")
            icon_filename = base_images[0]

        # Validate the selected filename actually exists
        base_path = settings.BASEIMG_DIR / icon_filename
        if not base_path.exists():
            print(f"[Artist/Composite] ⚠️  '{icon_filename}' not found — using first available.")
            icon_filename = base_images[0]
            base_path = settings.BASEIMG_DIR / icon_filename

        tint = (final_output.get("visual_stats") or {}).get("tint_color") or {}
        print(
            f"[Artist/Composite] icon={icon_filename} | "
            f"tint=({tint.get('r',1):.2f},{tint.get('g',1):.2f},{tint.get('b',1):.2f},{tint.get('a',1):.2f})"
        )

        png_bytes = _crop_and_resize(base_path)
        icon_b64  = base64.b64encode(png_bytes).decode("utf-8")

        return {
            "generated_icon":     icon_filename,
            "generated_icon_b64": icon_b64,
        }

    async def _sd_node(self, state: GlobalState) -> dict:  # legacy Stable Diffusion path
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

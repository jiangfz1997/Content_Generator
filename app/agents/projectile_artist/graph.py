"""
Projectile Artist Agent
Selects a base sprite from projectile_base_img/ and assigns a shader RGB color
for each newly generated projectile.  Fully independent of the weapon ArtistAgent.
"""
import base64
import io

import numpy as np
from PIL import Image
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.llm_service import llm_service


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class ShaderColor(BaseModel):
    r: float = Field(description="Red channel 0.0–1.0")
    g: float = Field(description="Green channel 0.0–1.0")
    b: float = Field(description="Blue channel 0.0–1.0")
    a: float = Field(default=1.0, description="Alpha channel 0.0–1.0. Use 1.0 for fully opaque.")


class ProjectileIconSelection(BaseModel):
    reasoning: str = Field(description="One sentence explaining shape, color, and scale choice. MAX 20 words.")
    selected_category: str = Field(
        description="Subdirectory category name, e.g. 'arrow', 'magic', 'bullet'. "
                    "Must match a category in the available list exactly."
    )
    selected_filename: str = Field(
        description="Exact filename within that category, e.g. 'basic_arrow.png'. "
                    "Must exist verbatim in the list — do NOT invent or modify names."
    )
    shader_color: ShaderColor = Field(
        description="RGBA tint (0.0–1.0 per channel) that Unity applies at runtime. "
                    "Match the elemental theme: fire→orange/red, ice→cyan/white, "
                    "poison→green, lightning→yellow, shadow→purple, physical→white/grey."
    )
    scale: float = Field(
        default=1.0,
        description=(
            "Uniform sprite scale multiplier. 1.0 = default size. "
            "Tiny/fast projectile (bullet, needle): 0.5–0.8. "
            "Normal projectile (arrow, bolt): 1.0. "
            "Large/slow projectile (orb, missile, AoE cloud): 1.3–2.0."
        ),
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SELECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a projectile art director for a 2D roguelike game.\n"
     "Images are organised into categories (subdirectories). "
     "You MUST return both a category and a filename that exist EXACTLY in the available list.\n\n"
     "SELECTION RULES (apply in order):\n"
     "1. Match shape/category first — 'bullet'/'gun' → bullet category, 'orb'/'bolt'/'magic' → magic category, "
     "'arrow'/'bow' → arrow category, 'wave'/'shockwave' → wave/melee category, etc.\n"
     "2. If no category keyword matches, pick the shape that best fits travel behavior "
     "(fast+thin → bullet, slow+large → orb/magic, melee wave → wave).\n"
     "3. Within the category, pick the filename that best matches the shape.\n"
     "4. Choose shader_color to match the elemental theme of the on_hit effects.\n"
     "   Fire/burn → (1.0, 0.4, 0.1) | Ice/freeze → (0.5, 0.9, 1.0) | Poison → (0.3, 0.9, 0.2) "
     "| Lightning → (1.0, 0.95, 0.2) | Shadow/dark → (0.5, 0.1, 0.8) | Physical → (1.0, 1.0, 1.0)\n"
     "5. Choose scale based on the projectile's physical size.\n"
     "   Bullet/needle → 0.6 | Arrow/bolt → 1.0 | Orb/missile → 1.3 | AoE cloud/explosion → 1.8\n\n"
     "Available images by category:\n{filenames}"),
    ("human",
     "Projectile ID: {projectile_id}\n"
     "Name: {name}\n"
     "Description: {description}\n"
     "On-hit effects: {on_hit_payloads}\n"
     "Speed: {speed}  Lifetime: {lifetime}"),
])


# ---------------------------------------------------------------------------
# Projectile image registry — scanned once at startup (same pattern as artist)
# ---------------------------------------------------------------------------

_IMG_EXTS     = {".png", ".jpg", ".jpeg"}
_OUTPUT_SIZE  = 64   # projectile sprites are smaller than weapon icons
_WHITE_THRESH = 240


def _scan_projectile_registry(base_dir) -> dict[str, list[str]]:
    """
    Recursively scan base_dir for leaf directories containing image files.
    Keys are relative paths from base_dir, e.g. "arrow", "magic/orb".
    Files placed directly in base_dir (flat/legacy layout) are grouped under "default".
    Adding any new subdir to projectile_base_img/ extends the registry automatically.
    """
    from pathlib import Path
    base_dir = Path(base_dir)
    registry: dict[str, list[str]] = {}
    if not base_dir.exists():
        return registry

    def _recurse(directory: Path):
        files = sorted(p.name for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMG_EXTS)
        if files:
            rel = directory.relative_to(base_dir).as_posix()
            key = "default" if rel == "." else rel   # root-level files → "default" category
            registry[key] = files
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                _recurse(child)

    _recurse(base_dir)
    return registry


_PROJECTILE_REGISTRY: dict[str, list[str]] = _scan_projectile_registry(settings.PROJECTILE_BASEIMG_DIR)


# ---------------------------------------------------------------------------
# Image utility
# ---------------------------------------------------------------------------

def _crop_and_resize(path, size: int = _OUTPUT_SIZE, padding: int = 2) -> bytes:
    img = Image.open(path).convert("RGBA")
    bbox = img.split()[3].getbbox()

    if bbox is None:
        arr  = np.array(img.convert("RGB"))
        mask = np.any(arr < _WHITE_THRESH, axis=2)
        rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
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

    # Proportional scale + centre-pad to square (preserves aspect ratio)
    crop_w, crop_h = img.size
    scale   = size / max(crop_w, crop_h)
    new_w, new_h = round(crop_w * scale), round(crop_h * scale)
    resample = Image.NEAREST if scale >= 1.0 else Image.LANCZOS
    scaled  = img.resize((new_w, new_h), resample)
    canvas  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(scaled, ((size - new_w) // 2, (size - new_h) // 2))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ProjectileArtistAgent:
    def __init__(self):
        self._chain = (
            _SELECT_PROMPT
            | llm_service.get_structured_model("projectile_artist", ProjectileIconSelection)
        )

    async def select_icon(
        self,
        projectile_id: str,
        name: str,
        description: str,
        on_hit_payloads: list[str],
        speed: float = 14.0,
        lifetime: float = 3.0,
    ) -> dict:
        """
        Returns a dict with keys: icon, visual_stats, icon_b64.
        icon is stored as "<category>/<filename>" (e.g. "arrow/basic_arrow.png").
        Suitable for direct merging into the projectile JSON dict.
        """
        if not _PROJECTILE_REGISTRY:
            print(f"[ProjectileArtist] ⚠️  No projectile image categories found — using fallback.")
            return _fallback()

        # Build categorised listing for the prompt
        options_lines: list[str] = []
        for category, files in _PROJECTILE_REGISTRY.items():
            options_lines.append(f"[{category}]")
            options_lines.extend(f"  - {f}" for f in files)
        filenames_str = "\n".join(options_lines)

        fallback_cat  = next(iter(_PROJECTILE_REGISTRY))
        fallback_file = _PROJECTILE_REGISTRY[fallback_cat][0]

        print(f"[ProjectileArtist] Registry: { {k: len(v) for k, v in _PROJECTILE_REGISTRY.items()} }")

        try:
            result: ProjectileIconSelection = await self._chain.ainvoke({
                "filenames":        filenames_str,
                "projectile_id":    projectile_id,
                "name":             name,
                "description":      description,
                "on_hit_payloads":  ", ".join(on_hit_payloads) if on_hit_payloads else "none",
                "speed":            speed,
                "lifetime":         lifetime,
            })
            sel_cat  = result.selected_category
            sel_file = result.selected_filename

            if sel_cat not in _PROJECTILE_REGISTRY or sel_file not in _PROJECTILE_REGISTRY[sel_cat]:
                print(f"[ProjectileArtist] ⚠️  '{sel_cat}/{sel_file}' not in registry — using fallback.")
                sel_cat, sel_file = fallback_cat, fallback_file

            sc = result.shader_color
            print(
                f"[ProjectileArtist] {projectile_id} → {sel_cat}/{sel_file} | "
                f"tint=({sc.r:.2f},{sc.g:.2f},{sc.b:.2f},{sc.a:.2f}) | {result.reasoning}"
            )
        except Exception as e:
            print(f"[ProjectileArtist] LLM failed: {e} — using fallback.")
            return _fallback()

        if sel_cat == "default":
            icon_key  = sel_file                                          # legacy flat layout
            icon_path = settings.PROJECTILE_BASEIMG_DIR / sel_file
        else:
            icon_key  = f"{sel_cat}/{sel_file}"
            icon_path = settings.PROJECTILE_BASEIMG_DIR / sel_cat / sel_file

        try:
            png_bytes = _crop_and_resize(icon_path)
            icon_b64  = base64.b64encode(png_bytes).decode("utf-8")
        except Exception as e:
            print(f"[ProjectileArtist] Image processing failed: {e}")
            icon_b64 = None

        sc = result.shader_color
        return {
            "icon":         icon_key,
            "visual_stats": {
                "tint_color": {"r": sc.r, "g": sc.g, "b": sc.b, "a": sc.a},
                "scale":      result.scale,
            },
            "icon_b64":     icon_b64,
        }


def _fallback() -> dict:
    return {
        "icon":         "default_projectile.png",
        "visual_stats": {"tint_color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}, "scale": 1.0},
        "icon_b64":     None,
    }


projectile_artist_agent = ProjectileArtistAgent()

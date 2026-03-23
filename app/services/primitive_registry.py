import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings
from app.utils.formatter import format_registries_for_llm_yaml


class PrimitiveRegistry:
    def __init__(self):
        self.primitive_path = settings.PRIMITIVES_PATH
        self.payloads_dir = settings.PAYLOADS_PATH
        self.projectiles_dir = settings.PROJECTILES_PATH
        self.primitive_motion_path = settings.MOTION_PATH
        self.weapon_schema_path = settings.WEAPON_SCHEMA_PATH
        self.projectile_schema_path = settings.PROJECTILE_SCHEMA_PATH

        # In-memory caches — populated by initialize() at startup.
        # Fall back to disk scan if cache is empty (test / cold-start).
        self._payload_cache: Dict[str, Any] = {}
        self._projectile_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Async initializer — call once from main() after DB is connected
    # ------------------------------------------------------------------

    async def initialize(self, session_id: Optional[str] = None):
        """Load presets (+ optional session payloads/projectiles) from MongoDB into cache."""
        from app.services.mongo_service.payloads_services import payload_mongo_service
        from app.services.mongo_service.projectiles_services import projectile_mongo_service

        payloads = await payload_mongo_service.get_all_payloads(session_id)
        self._payload_cache = {p["id"]: p for p in payloads}

        projectiles = await projectile_mongo_service.get_all_projectiles(session_id)
        self._projectile_cache = {p["id"]: p for p in projectiles}

        print(f"✅ [Registry] 缓存已加载: {len(self._payload_cache)} payloads, "
              f"{len(self._projectile_cache)} projectiles")

    # ------------------------------------------------------------------
    # Cache update helpers — called by factories after generation
    # ------------------------------------------------------------------

    def add_payload(self, payload_id: str, payload_data: dict):
        self._payload_cache[payload_id] = payload_data

    def add_projectile(self, projectile_id: str, projectile_data: dict):
        self._projectile_cache[projectile_id] = projectile_data

    # ------------------------------------------------------------------
    # Synchronous getters (safe for Pydantic validators & workflow nodes)
    # ------------------------------------------------------------------

    def get_all_payloads(self) -> Dict[str, Any]:
        if self._payload_cache:
            return dict(self._payload_cache)
        # Fallback: scan preset dir then flat dir (for tests / pre-init)
        return self._scan_dir(settings.PAYLOADS_PRESET_PATH) or self._scan_dir(self.payloads_dir)

    def get_all_projectiles(self) -> Dict[str, Any]:
        if self._projectile_cache:
            return dict(self._projectile_cache)
        return self._scan_dir(settings.PROJECTILES_PRESET_PATH) or self._scan_dir(self.projectiles_dir)

    # ------------------------------------------------------------------
    # Schema readers (unchanged)
    # ------------------------------------------------------------------

    def get_primitives_schema(self) -> str:
        try:
            with open(Path(self.primitive_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Primitives Schema failed: {e}")
            return "No primitive schema found."

    def get_motions_schema(self) -> str:
        try:
            with open(Path(self.primitive_motion_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Motion Schema failed: {e}")
            return "No motion schema found."

    def get_weapon_schema(self) -> str:
        try:
            with open(Path(self.weapon_schema_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Weapon Schema failed: {e}")
            return "No weapon schema found."

    def get_projectile_schema(self) -> str:
        try:
            with open(Path(self.projectile_schema_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Projectile Schema failed: {e}")
            return "No projectile schema found."

    def get_all_motions(self) -> list:
        try:
            with open(self.primitive_motion_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Load Motions failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_dir(directory: Path) -> Dict[str, Any]:
        result = {}
        if not directory or not directory.exists() or not directory.is_dir():
            return result
        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    result[json_file.stem] = json.load(f)
            except Exception as e:
                print(f"❌ Failed to load {json_file.name}: {e}")
        return result


# Singleton
primitive_registry = PrimitiveRegistry()


def get_shared_engine_context():
    return format_registries_for_llm_yaml(
        available_payloads=primitive_registry.get_all_payloads(),
        available_primitives={},
        available_motions=primitive_registry.get_all_motions(),
    )

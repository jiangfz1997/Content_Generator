import json
import os
from datetime import datetime
from typing import List, Optional

from pymongo import UpdateOne

from app.core.config import settings
from app.db.mongodb import db


class ProjectilesMongoService:
    def __init__(self):
        self.collection_name = "projectiles"

    async def load_preset_projectiles(self):
        """Upsert all preset projectiles (PROJECTILES_PRESET_PATH) into MongoDB as session_id='SYSTEM'."""
        presets_dir = settings.PROJECTILES_PRESET_PATH
        if not presets_dir.exists():
            print(f"⚠️ [ProjectileSeeder] Preset dir not found: {presets_dir}")
            return

        collection = db.db[self.collection_name]
        ops = []
        for filename in os.listdir(presets_dir):
            if not filename.endswith(".json"):
                continue
            with open(presets_dir / filename, "r", encoding=settings.ENCODING) as f:
                raw_data = json.load(f)
            doc = {
                "id": raw_data["id"],
                "session_id": "SYSTEM",
                "is_preset": True,
                "content": raw_data,
                "last_synced": datetime.utcnow(),
            }
            ops.append(UpdateOne(
                {"id": raw_data["id"], "session_id": "SYSTEM"},
                {"$set": doc},
                upsert=True,
            ))

        if ops:
            await collection.bulk_write(ops, ordered=False)
            print(f"✅ [ProjectileSeeder] 已同步 {len(ops)} 个预设 Projectile。")

    async def save_generated_projectile(self, session_id: str, projectile_data: dict):
        """Persist a factory-generated projectile bound to a specific session."""
        doc = {
            "id": projectile_data["id"],
            "session_id": session_id,
            "is_preset": False,
            "content": projectile_data,
            "last_synced": datetime.utcnow(),
        }
        await db.db[self.collection_name].replace_one(
            {"id": projectile_data["id"], "session_id": session_id},
            doc,
            upsert=True,
        )
        print(f"✅ [ProjectileService] 已存档: {projectile_data['id']} (session={session_id})")

    async def get_all_projectiles(self, session_id: Optional[str] = None) -> List[dict]:
        """Return content dicts for SYSTEM presets + optional session-specific projectiles."""
        if session_id:
            query = {"$or": [{"session_id": "SYSTEM"}, {"session_id": session_id}]}
        else:
            query = {"session_id": "SYSTEM"}
        cursor = db.db[self.collection_name].find(query, {"_id": 0, "content": 1})
        docs = await cursor.to_list(length=500)
        return [d["content"] for d in docs]

    async def get_session_projectiles(self, session_id: str) -> List[dict]:
        """Return only the generated projectiles for a given session (for returning to Unity)."""
        cursor = db.db[self.collection_name].find(
            {"session_id": session_id},
            {"_id": 0, "content": 1},
        )
        docs = await cursor.to_list(length=200)
        return [d["content"] for d in docs]


projectile_mongo_service = ProjectilesMongoService()

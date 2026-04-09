import hashlib
import json
import os
from typing import List, Optional
from pymongo import UpdateOne

from app.core.config import settings
from app.db.mongodb import db
from app.models.mongo.weapon import WeaponDocument, WeaponContent  # 假设你定义了模型


class WeaponMongoService:
    def __init__(self, collection_name: Optional[str] = "weapons"):
        self.collection_name = collection_name


    async def load_preset_weapons(self):
        presets_dir = settings.WEAPON_PRESET_PATH
        collection = db.db[self.collection_name]
        operations = []

        for filename in os.listdir(presets_dir):
            if not filename.endswith(".json"): continue

            file_path = os.path.join(presets_dir, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

                try:

                    weapon_doc = WeaponDocument(
                        id=raw_data["id"],
                        session_id="SYSTEM",  # 预设武器统一标记为 SYSTEM
                        is_preset=True,
                        content=WeaponContent(**raw_data)  # 校验核心内容
                    )

                    op = UpdateOne(
                        {"id": weapon_doc.id, "session_id": "SYSTEM"},  # 复合唯一索引
                        {"$set": weapon_doc.to_mongo()},
                        upsert=True
                    )
                    operations.append(op)
                except Exception as e:
                    print(f"❌ [Seeder] validation failed for {filename}: {e}")

        if operations:
            await collection.bulk_write(operations, ordered=False)
            print(f"✅ [Seeder] synced {len(operations)} weapons")

    async def find_by_input_hash(self, input_hash: str, session_id: str) -> Optional[dict]:
        """Find a previously generated weapon by its input combination hash, scoped to session."""
        doc = await db.db[self.collection_name].find_one(
            {"input_hash": input_hash, "is_preset": False, "session_id": session_id},
            {"_id": 0, "content": 1},
        )
        return doc.get("content") if doc else None

    @staticmethod
    def _make_combination_hash(biome: str, payload_ids: List[str], projectile_id: Optional[str]) -> str:
        key = json.dumps({
            "biome": biome or "",
            "payloads": sorted(pid for pid in payload_ids if pid),
            "projectile_id": projectile_id or "",
        }, sort_keys=True)
        return hashlib.md5(key.encode()).hexdigest()

    async def save_generated_weapon(self, weapon_data: dict, session_id: str,
                                    biome: str = None, level: int = None,
                                    generation_time_secs: float = None,
                                    node_timings: dict = None,
                                    node_traces: dict = None,
                                    input_hash: str = None):
        """保存 AI 生成的武器，并绑定 session_id 及 RAG 元数据"""
        try:
            if not weapon_data:
                print("⚠️ [Service] weapon_data is None/empty, skipping save")
                return False
            abilities = weapon_data.get("abilities") or {}
            on_hit = abilities.get("on_hit") or []
            on_attack = abilities.get("on_attack") or []
            on_equip = abilities.get("on_equip") or []
            all_payload_ids = [p for p in on_hit + on_attack + on_equip if p]
            primary_payload = all_payload_ids[0] if all_payload_ids else None
            projectile_id = (weapon_data.get("stats") or {}).get("projectile_id")
            combination_hash = self._make_combination_hash(biome, all_payload_ids, projectile_id) if biome else None

            doc = WeaponDocument(
                id=weapon_data["id"],
                session_id=session_id,
                is_preset=False,
                content=WeaponContent(**weapon_data),
                biome=biome,
                level=level,
                primary_payload=primary_payload,
                summary=weapon_data.get("summary"),
                generation_time_secs=round(generation_time_secs, 2) if generation_time_secs else None,
                node_timings=node_timings or None,
                node_traces=node_traces or None,
                input_hash=input_hash or None,
                combination_hash=combination_hash,
            )
            await db.db[self.collection_name].replace_one(
                {"id": doc.id, "session_id": session_id},
                doc.to_mongo(),
                upsert=True
            )
            print(f"✅ [Service] weapon saved: {doc.id}")
            return True
        except Exception as e:
            print(f"❌ [Service] failed to save weapon: {e}")
            return False

    async def get_similar_weapons(self, biome: str, level: int, limit: int = 6) -> List[dict]:
        """
        按 biome 筛选，按 level 距离排序，返回最相近的武器。
        包含完整 abilities 信息，用于 designer 判断 payload 组合是否重复。
        """
        projection = {
            "_id": 0, "id": 1, "biome": 1, "level": 1, "summary": 1,
            "content.name": 1, "content.abilities": 1,
        }
        cursor = db.db[self.collection_name].find({"biome": biome}, projection)
        docs = await cursor.to_list(length=200)

        docs.sort(key=lambda d: abs((d.get("level") or 0) - level))

        result = []
        for d in docs[:limit]:
            content = d.pop("content", {})
            d["name"] = content.get("name", d.get("id"))
            d["abilities"] = content.get("abilities", {})
            result.append(d)
        return result

    async def find_by_combination(
        self,
        biome: str,
        payload_ids: List[str],
        projectile_id: Optional[str],
        session_id: str = None,
    ) -> Optional[dict]:
        """
        Find an existing weapon by combination_hash (sorted payload_ids + projectile_id + biome),
        scoped to session.  Returns the full content dict or None.
        """
        combo_hash = self._make_combination_hash(biome, payload_ids, projectile_id)
        query = {"combination_hash": combo_hash, "is_preset": False}
        if session_id:
            query["session_id"] = session_id
        doc = await db.db[self.collection_name].find_one(query, {"_id": 0, "content": 1})
        return doc.get("content") if doc else None

    async def get_all_summaries(self) -> List[dict]:
        """拉取所有武器的轻量摘要，用于 RAG 注入 designer prompt"""
        projection = {
            "_id": 0, "id": 1, "biome": 1, "level": 1,
            "primary_payload": 1, "summary": 1, "content.name": 1,
        }
        cursor = db.db[self.collection_name].find({}, projection)
        docs = await cursor.to_list(length=500)
        # 把 content.name 提升到顶层，方便格式化
        for d in docs:
            d["name"] = d.pop("content", {}).get("name", d.get("id"))
        return docs

    async def get_all_sessions(self) -> List[dict]:
        """返回所有非 SYSTEM session 的摘要（id + 武器数 + 最后生成时间）"""
        pipeline = [
            {"$match": {"session_id": {"$ne": "SYSTEM"}}},
            {"$group": {
                "_id":        "$session_id",
                "weapon_count": {"$sum": 1},
                "last_created": {"$max": "$last_synced"},
            }},
            {"$sort": {"last_created": -1}},
        ]
        docs = await db.db[self.collection_name].aggregate(pipeline).to_list(length=500)
        return [{"session_id": d["_id"], "weapon_count": d["weapon_count"],
                 "last_created": d["last_created"].isoformat() if d["last_created"] else None}
                for d in docs]

    async def get_weapons_by_session(self, session_id: str) -> List[dict]:
        """返回指定 session 下所有武器的完整文档（含 generation_time_secs）"""
        projection = {"_id": 0}
        cursor = db.db[self.collection_name].find({"session_id": session_id}, projection)
        return await cursor.to_list(length=500)

    async def get_weapons_for_game(self, session_id: str) -> List[dict]:
        """
        核心查询逻辑：拉取预设 + 本局生成的武器
        """
        query = {
            "$or": [
                {"session_id": "SYSTEM"},
                {"session_id": session_id}
            ]
        }
        cursor = db.db[self.collection_name].find(query)
        docs = await cursor.to_list(length=200)

        # 只返回 content 部分给 Unity，保持协议简洁
        return [d["content"] for d in docs]

weapon_mongo_service = WeaponMongoService()
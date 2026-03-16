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
                    print(f"❌ [Seeder] 数据校验失败 {filename}: {e}")

        if operations:
            await collection.bulk_write(operations, ordered=False)
            print(f"✅ [Seeder] 已同步 {len(operations)} 把武器。")

    async def save_generated_weapon(self, weapon_data: dict, session_id: str,
                                    biome: str = None, level: int = None):
        """保存 AI 生成的武器，并绑定 session_id 及 RAG 元数据"""
        try:
            if not weapon_data:
                print("⚠️ [Service] weapon_data is None/empty, skipping save")
                return False
            abilities = weapon_data.get("abilities") or {}
            on_hit = abilities.get("on_hit") or []
            on_attack = abilities.get("on_attack") or []
            on_equip = abilities.get("on_equip") or []
            primary_payload = (on_hit or on_attack or on_equip or [None])[0]

            doc = WeaponDocument(
                id=weapon_data["id"],
                session_id=session_id,
                is_preset=False,
                content=WeaponContent(**weapon_data),
                biome=biome,
                level=level,
                primary_payload=primary_payload,
                summary=weapon_data.get("summary"),
            )
            await db.db[self.collection_name].replace_one(
                {"id": doc.id, "session_id": session_id},
                doc.to_mongo(),
                upsert=True
            )
            print(f"✅ [Service] 武器已存档: {doc.id}")
            return True
        except Exception as e:
            print(f"❌ [Service] 保存 AI 武器失败: {e}")
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

        # Python 侧按 level 距离排序（DB 数量小，不值得 aggregation）
        docs.sort(key=lambda d: abs((d.get("level") or 0) - level))

        result = []
        for d in docs[:limit]:
            content = d.pop("content", {})
            d["name"] = content.get("name", d.get("id"))
            d["abilities"] = content.get("abilities", {})
            result.append(d)
        return result

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
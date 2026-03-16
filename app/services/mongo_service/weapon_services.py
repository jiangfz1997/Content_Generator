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

    async def save_generated_weapon(self, weapon_data: dict, session_id: str):
        """
        保存 AI 生成的武器，并绑定 session_id
        """
        try:
            doc = WeaponDocument(
                id=weapon_data["id"],
                session_id=session_id,
                is_preset=False,
                content=WeaponContent(**weapon_data)
            )
            await db.db[self.collection_name].replace_one(
                {"id": doc.id, "session_id": session_id},
                doc.to_mongo(),
                upsert=True
            )
            return True
        except Exception as e:
            print(f"❌ [Service] 保存 AI 武器失败: {e}")
            return False

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
import os
import json
import asyncio
from pymongo import UpdateOne  # 🌟 核心：导入批量操作类
from app.db.mongodb import db


async def seed_preset_weapons(presets_dir: str):
    """使用 bulk_write 批量同步本地 JSON 预设武器到 MongoDB"""
    if not os.path.exists(presets_dir):
        print(f"⚠️ [Seeder] 未找到目录: {presets_dir}")
        return

    collection = db.db["weapons"]
    operations = []  # 存储批量操作指令的列表
    current_time = asyncio.get_event_loop().time()

    for filename in os.listdir(presets_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(presets_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    weapon_data = json.load(f)
                    weapon_id = weapon_data.get("id")

                    if not weapon_id:
                        continue

                    # 🌟 构造批量更新指令 (Upsert 逻辑)
                    op = UpdateOne(
                        {"id": weapon_id},
                        {
                            "$set": {
                                "content": weapon_data,
                                "is_preset": True,
                                "last_synced": current_time
                            }
                        },
                        upsert=True
                    )
                    operations.append(op)

            except Exception as e:
                print(f"❌ [Seeder] 解析文件 {filename} 失败: {e}")

    if operations:
        try:
            result = await collection.bulk_write(operations, ordered=False)

            print(f"✅ [Seeder] 批量同步完成!")
            print(f"   - 匹配到: {result.matched_count}")
            print(f"   - 已修改: {result.modified_count}")
            print(f"   - 新插入: {result.upserted_count}")
        except Exception as e:
            print(f"❌ [Seeder] 批量写入数据库失败: {e}")
    else:
        print("ℹ️ [Seeder] 没有发现需要同步的武器数据。")
from motor.motor_asyncio import AsyncIOMotorClient
import os


class MongoDB:
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None

    async def connect(self):
        # 从 .env 读取配置
        mongo_uri = os.getenv("MONGO_URL", "mongodb://admin:password@localhost:27017")
        db_name = os.getenv("MONGO_DB_NAME", "project_roguelike")

        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        print(f"✅ [DB] 已连接至 MongoDB: {db_name}")

    async def close(self):
        if self.client:
            self.client.close()
            print("❌ [DB] MongoDB 连接已关闭")


#
db = MongoDB()
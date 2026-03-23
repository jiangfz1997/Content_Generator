import asyncio
import json
import websockets

from app.core.config import settings
from app.db.mongodb import db
from app.db.seeder import seed_preset_weapons
from app.services.engine_docs_manager import engine_docs_manager
from handlers import handle_generation_request
from dotenv import load_dotenv
import os
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.services.mongo_service.payloads_services import payload_mongo_service
from app.services.mongo_service.projectiles_services import projectile_mongo_service
from app.services.primitive_registry import primitive_registry

load_dotenv()
# 路由表：Action -> Handler Function
ROUTER = {
    "generate_weapon": handle_generation_request
}


async def connection_handler(websocket):
    client_addr = websocket.remote_address
    print(f"[Server] 新连接: {client_addr}")

    try:
        async for message in websocket:

            try:
                data = json.loads(message)
                payload = data.get("payload")
                action = payload.get("action")
            except json.JSONDecodeError:
                print(f"[Server] 收到非 JSON 消息: {message}")
                continue
            print(f"[Server] 收到消息: action={action} from {client_addr}")
            # 2. 路由分发
            if action in ROUTER:
                # 启动一个 Task 来处理，这样如果处理很慢，不会阻塞接收下一条消息
                asyncio.create_task(ROUTER[action](websocket, message))
            elif action == "ping":
                await websocket.send(json.dumps({"msgType": "Pong", "payload": {}}))
            else:
                print(f"[Server] 未知动作: {action}")

    except websockets.exceptions.ConnectionClosedOK:
        print(f"[Server] 连接正常关闭: {client_addr}")
    except websockets.exceptions.ConnectionClosedError:
        print(f"[Server] 连接异常断开: {client_addr}")
    except Exception as e:
        print(f"[Server] 全局错误: {e}")

def _log_init_result(task: asyncio.Task) -> None:
    exc = task.exception() if not task.cancelled() else None
    if exc:
        print(f"[Init] ⚠️ 引擎手册预加载失败，首次请求时将触发冷启动: {exc}")
    else:
        print("[Init] ✅ 引擎手册预加载完成")

async def main():
    await db.connect()
    port = 8080
    # Generate the engine manual into cache. Used for LLM agents to understand how to use the infos.
    init_task = asyncio.create_task(engine_docs_manager.get_markdown_manual())
    init_task.add_done_callback(_log_init_result)
    # Load all presets into MongoDB
    await weapon_mongo_service.load_preset_weapons()
    await payload_mongo_service.load_preset_payloads()
    await projectile_mongo_service.load_preset_projectiles()
    # Populate in-memory registry cache from MongoDB (presets only at startup)
    await primitive_registry.initialize()
    async with websockets.serve(connection_handler, "localhost", port):
        print(f"✅ WebSocket Server 运行在 ws://localhost:{port}")
        # 保持运行
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] 服务器已停止")
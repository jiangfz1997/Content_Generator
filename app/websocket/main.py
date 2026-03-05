import asyncio
import json
import websockets
from handlers import handle_generation_request
from dotenv import load_dotenv
import os

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

            # 1. 基础预处理
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


async def main():

    port = 8080
    async with websockets.serve(connection_handler, "localhost", port):
        print(f"✅ WebSocket Server 运行在 ws://localhost:{port}")
        # 保持运行
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] 服务器已停止")
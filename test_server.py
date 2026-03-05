import json
import asyncio
import websockets


async def handle_client(websocket):
    print("New client connected!")
    try:
        async for message in websocket:
            print(f"收到 Unity 消息: {message}")

            # --- 测试逻辑开始 ---
            # 如果收到字符串 "PING"，我们就回一个 TestEvent
            if message == "PING":
                print("触发测试回复...")

                # 1. 构造内层数据 (TestEvent 的内容)
                inner_data = {
                    "content": "Python 收到你的信号了！这是测试回复。",
                    "mood": "Excited"
                }
                # 必须转成 JSON 字符串！
                payload_str = json.dumps(inner_data)

                # 2. 构造外层信封 (NetPacket)
                # msgType 必须和 C# 类名 "TestEvent" 一模一样
                packet = {
                    "msgType": "TestEvent",
                    "payload": payload_str
                }

                # 3. 发送最终的 JSON
                await websocket.send(json.dumps(packet))
                print("回复已发送！")
            # --- 测试逻辑结束 ---

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")


async def main():
    async with websockets.serve(handle_client, "localhost", 8080):
        print("WebSocket Server started on ws://localhost:8080")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
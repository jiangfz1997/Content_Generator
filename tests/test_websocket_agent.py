# tests/integration/test_websocket_agent.py
import pytest
import json
import asyncio
import websockets


@pytest.mark.asyncio
async def test_websocket_llm_integration():
    """
    集成测试目标：
    1. 验证 WebSocket 握手是否成功。
    2. 发送 GenerationRequest 协议包。
    3. 验证逻辑是否穿透到 LangGraph/LLM 并成功返回 WeaponGenerateEvent。
    """
    # 你的服务器地址，确保 main.py 已经启动
    uri = "ws://localhost:8080"
    print("Trying to connect to WebSocket server at:", uri)
    # 1. 建立连接
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket server")
        # 2. 构造符合协议定义的业务数据
        # 这里的字段必须与你的 GenerationRequest 类对应
        request_payload = {
            "action": "generate_weapon",
            "biome": "Magma_Chamber",
            "player_level": 20,
            "prompt": "use the itmes listed in materials to generate a unique weapon suitable for a level 20 player in the Magma Chamber biome.",
            "materials": ["Fire Essence", "Lava Core", "Obsidian Shard"]
        }

        # 3. 封装进 NetPacket 信封
        # msgType 必须对应你在服务器端 ROUTER 里的 Key 或 C# 类名
        packet = {
            "msgType": "GenerationRequest",
            "payload": request_payload
        }

        print(f"\n[Test] 正在发送请求: {packet['msgType']}")
        await websocket.send(json.dumps(packet))

        # 4. 接收响应
        # 注意：由于 14B 模型本地推理需要时间，设置 30-60 秒的超时是合理的
        try:
            raw_response = await asyncio.wait_for(websocket.recv(), timeout=180.0)
            response_data = json.loads(raw_response)

            # --- 5. 验证环节 ---

            # 验证外层信封
            assert response_data["msgType"] == "WeaponGenerateEvent", "返回的消息类型不正确"

            # 验证内层 payload
            payload = response_data["payload"]
            assert "content" in payload, "响应中缺少 content 字段"

            # 验证 AI 生成的具体内容
            weapon = payload["content"]
            assert "name" in weapon, "AI 未生成武器名称"
            assert "damage" in weapon, "AI 未生成武器伤害"

            print(f"\n[Test] 集成测试成功！")
            print(f"生成的武器: {weapon['name']} (伤害: {weapon['damage']})")
            print(f"AI 描述: {weapon.get('description', '无')}")

        except asyncio.TimeoutError:
            pytest.fail("❌ 测试失败：LLM 响应超时，请检查 Ollama 是否卡死或显存已满。")
        except ConnectionRefusedError:
            pytest.fail("❌ 测试失败：无法连接服务器，请确保 main.py 正在运行。")
import time

from app.agents.weapon.graph import weapon_agent
from protocol import NetPacket, GenerationRequest, WeaponGenerateEvent
from app.services.llm_service import LLMService
from app.core.workflow import global_graph

llm_service = LLMService()

async def handle_generation_request(websocket, raw_message: str):
    """
    处理 generate_weapon 请求
    """
    try:
        # 1. 解析请求
        req = GenerationRequest.from_json(raw_message)
        print(f"[Handler] 收到生成请求: {req}")

        # 2. 调用业务逻辑 (耗时操作)
        # 注意：这里 await 是为了等待结果，但不会阻塞整个 Server (因为是 async)
        # weapon_data = await weapon_agent.run({
        #     "biome": req.biome,
        #     "level": req.player_level
        # })
        # print(f"[Handler] AI 生成的武器数据: {weapon_data}")
        final_state = await global_graph.ainvoke({
            "prompt": req.prompt,
            "materials": req.materials,
            "biome": req.biome,
            "level": req.player_level
        })
        routed_dept = final_state.get("next_agent")
        output_data = final_state.get("final_output")

        if routed_dept == "FINISH" or not output_data:
            print("[Handler] failed to generate weapon or supervisor decided no further generation needed.")
            return
        packet = None
        if routed_dept == "weapon_department":
            event = WeaponGenerateEvent(
                timestamp=int(time.time()),
                content=output_data  # 此时这里确信是 WeaponSchema 的字典
            )
            packet = NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__)
        if packet:
            print(f"[Handler] 发送生成结果给 Unity: {packet}")
        await websocket.send(packet.to_json())

    except Exception as e:
        print(f"[Error] 处理生成请求失败: {e}")
        # 这里可以发一个 ErrorEvent 给 Unity
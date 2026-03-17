import asyncio
import json
import time

from app.core.config import settings
from app.websocket.protocol import NetPacket, GenerationRequest, WeaponGenerateEvent
from app.core.workflow import global_graph


async def _send_error(websocket, error: str, details: str = "", code: int = 500):
    packet = NetPacket(msgType="ErrMsgEvent", payload={"error": error, "code": code, "details": details})
    await websocket.send(packet.to_json())


async def handle_generation_request(websocket, raw_message: str):
    """
    generate_weapon request handler:
      1. Parse the incoming message into a structured GenerationRequest.
      2. Invoke the global crafting graph with the request parameters.
      3. Await the final output, which includes the generated weapon and any new payloads.
      4. Send a WeaponGenerateEvent back to the client with the results.
    """
    try:
        req = GenerationRequest.from_json(raw_message)
        print(f"[Handler] 收到生成请求: {req}")

        final_state = await global_graph.ainvoke(
            {
                "prompt": req.prompt,
                "materials": req.materials,
                "biome": req.biome,
                "level": req.player_level,
                "weapons": req.weapons,
                "session_id": req.session_id or "unknown_session",
                "world_level": req.world_level,
                "retry_count": 0,
                "audit_attempts": 0,
                "generation_history": [],
            },
            timeout=settings.PIPELINE_TIMEOUT_SECS,
        )

        output_data = final_state.get("final_output")
        if not output_data:
            print("❌ [Handler] 武器生成失败：pipeline 返回空 output")
            await _send_error(websocket, "GenerationFailed", "Output is None!")
            return

        output_data.pop("manual_analysis", None)
        output_data.pop("stat_balance_reasoning", None)
        output_data["icon"] = final_state.get("generated_icon") or output_data.get("icon") or "weapon_axe.png"

        new_payload_ids = final_state.get("pending_payload_ids") or []
        new_payloads_list = []
        for pid in new_payload_ids:
            payload_path = settings.PAYLOADS_PATH / f"{pid}.json"
            if payload_path.exists():
                with open(payload_path, "r", encoding="utf-8") as f:
                    new_payloads_list.append(json.load(f))

        event = WeaponGenerateEvent(
            timestamp=int(time.time()),
            content=output_data,
            new_payloads=new_payloads_list or None,
        )
        await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
        print(f"[Handler] 发送生成结果给 Unity: {output_data.get('id')}")

    except asyncio.TimeoutError:
        print("❌ [Handler] 武器生成超时")
        await _send_error(websocket, "GenerationTimeout", "Pipeline timed out", code=504)
    except Exception as e:
        print(f"❌ [Handler] 处理生成请求失败: {e}")
        await _send_error(websocket, "ServerError", str(e))

import asyncio
import json
import time

from app.core.config import settings
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.services.weapon_evaluator import WeaponEvaluator
from app.websocket.protocol import NetPacket, GenerationRequest, WeaponGenerateEvent
from app.core.workflow import global_graph


async def _send_error(websocket, error: str, details: str = "", code: int = 500):
    packet = NetPacket(msgType="ErrMsgEvent", payload={"error": error, "code": code, "details": details})
    await websocket.send(packet.to_json())


def _make_fallback_weapon(weapons: list, world_level: int, player_level: int) -> dict | None:
    """
    Enhance the first available weapon from the request as a generation fallback.
    Fills in any missing stats and scales base_damage to the world_level power budget.
    Returns None if no usable weapon is provided.
    """
    if not weapons:
        return None

    src = weapons[0]
    if not isinstance(src, dict) or not src.get("id"):
        return None

    original_id = src["id"]
    stats = dict(src.get("stats") or {})

    # Fill defaults for any missing stats so WeaponEvaluator can work
    stats.setdefault("range",        1.5)
    stats.setdefault("duration",     0.5)
    stats.setdefault("cooldown",     0.5)
    stats.setdefault("hit_start",    0.2)
    stats.setdefault("hit_end",      0.8)
    stats.setdefault("design_level", max(1, player_level))
    stats.setdefault("base_damage",  WeaponEvaluator.get_target_budget(world_level))

    weapon = {
        **src,
        "id":    f"{original_id}_enhanced",
        "name":  f"{src.get('name', original_id)} (Enhanced)",
        "stats": stats,
        "icon":  src.get("icon", "weapon_axe.png"),
        "summary": "Fallback weapon — enhanced from existing inventory.",
    }
    weapon.setdefault("motions",   [])
    weapon.setdefault("abilities", {"on_hit": [], "on_attack": [], "on_equip": []})

    # Scale damage to fit world_level budget
    weapon, score, budget = WeaponEvaluator.auto_scale(weapon, world_level)
    print(f"[Handler] 保底武器生成: {weapon['id']}  budget={budget}  score={score}")
    return weapon


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
        req.prompt =f"[CRITICAL]YOU HAVE TO GENERATE A RANGE WEAPON WITH NEW PROJECTILE!. {req.prompt}"
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
            print("❌ [Handler] 武器生成失败：pipeline 返回空 output，尝试保底")
            output_data = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if not output_data:
                await _send_error(websocket, "GenerationFailed", "Output is None and no fallback weapon available.")
                return

        output_data.pop("manual_analysis", None)
        output_data.pop("stat_balance_reasoning", None)
        output_data["icon"] = final_state.get("generated_icon") or output_data.get("icon") or "weapon_axe.png"
        icon_b64 = final_state.get("generated_icon_b64") or None

        session_id = req.session_id or "unknown_session"
        new_payload_ids = final_state.get("pending_payload_ids") or []
        new_projectile_ids = final_state.get("pending_projectile_ids") or []

        new_payloads_list = []
        new_projectiles_list = []
        if new_payload_ids or new_projectile_ids:
            from app.services.mongo_service.payloads_services import payload_mongo_service
            from app.services.mongo_service.projectiles_services import projectile_mongo_service
            if new_payload_ids:
                session_payloads = await payload_mongo_service.get_session_payloads(session_id)
                pid_set = set(new_payload_ids)
                new_payloads_list = [p for p in session_payloads if p.get("id") in pid_set]
            if new_projectile_ids:
                session_projectiles = await projectile_mongo_service.get_session_projectiles(session_id)
                proj_set = set(new_projectile_ids)
                new_projectiles_list = [p for p in session_projectiles if p.get("id") in proj_set]

        await _save_weapon_data(session_id, output_data, biome=req.biome, level=req.player_level)

        event = WeaponGenerateEvent(
            timestamp=int(time.time()),
            content=output_data,
            new_payloads=new_payloads_list or None,
            new_projectiles=new_projectiles_list or None,
            icon_b64=icon_b64,
        )
        # print(f"[Handler] 生成成功，准备发送结果给 Unity: {str(event)}")
        await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
        print(f"[Handler] 发送生成结果给 Unity: {output_data.get('id')}")

    except asyncio.TimeoutError:
        print("❌ [Handler] 武器生成超时，尝试保底")
        try:
            req = GenerationRequest.from_json(raw_message)
            fallback = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if fallback:
                event = WeaponGenerateEvent(timestamp=int(time.time()), content=fallback)
                await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
                print(f"[Handler] 保底武器已发送: {fallback.get('id')}")
                return
        except Exception:
            pass
        await _send_error(websocket, "GenerationTimeout", "Pipeline timed out", code=504)
    except Exception as e:
        print(f"❌ [Handler] 处理生成请求失败: {e}，尝试保底")
        try:
            req = GenerationRequest.from_json(raw_message)
            fallback = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if fallback:
                event = WeaponGenerateEvent(timestamp=int(time.time()), content=fallback)
                await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
                print(f"[Handler] 保底武器已发送: {fallback.get('id')}")
                return
        except Exception:
            pass
        await _send_error(websocket, "ServerError", str(e))


async def _save_weapon_data(session_id: str, final_weapon_data: dict, biome: str = None, level: int = None):
    await weapon_mongo_service.save_generated_weapon(
        weapon_data=final_weapon_data,
        session_id=session_id,
        biome=biome,
        level=level,
    )
    try:
        backup_dir = settings.SESSIONS_DIR / session_id / "weapons"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{final_weapon_data.get('id', 'unknown')}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(final_weapon_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [Handler] 武器本地备份失败 (不影响流程): {e}")
import asyncio
import json
import time

from app.core.config import settings
from app.services.mongo_service.weapon_services import weapon_mongo_service
from app.services.mongo_service.payloads_services import payload_mongo_service
from app.services.mongo_service.projectiles_services import projectile_mongo_service
from app.services.weapon_evaluator import WeaponEvaluator
from app.utils.callbacks import TimingCallback, WebSocketProgressCallback
from app.websocket.protocol import NetPacket, GenerationRequest, WeaponGenerateEvent
from app.core.workflow import global_graph


# ── Connection registry ────────────────────────────────────────────────────────
# All active WebSocket connections. Used to broadcast pipeline progress events
# to every connected client (including the debug UI).
_connections: set = set()

def register_connection(ws) -> None:
    _connections.add(ws)

def unregister_connection(ws) -> None:
    _connections.discard(ws)

def _pipeline_config() -> dict:
    return {
        "skip_idea_audit":  settings.SKIP_IDEA_AUDIT,
        "skip_tech_audit":  settings.SKIP_TECH_AUDIT,
        "skip_input_cache": settings.SKIP_INPUT_CACHE,
        "workflow_mode":    settings.WORKFLOW_MODE,
    }


async def _broadcast_progress(payload: dict) -> None:
    """Send a PipelineProgressEvent to every connected client."""
    if not _connections:
        return
    msg = json.dumps({"msgType": "PipelineProgressEvent", "payload": payload}, default=str)
    for ws in list(_connections):   # snapshot — avoid mutation during iteration
        try:
            await ws.send(msg)
        except Exception:
            pass


async def _send_error(websocket, error: str, details: str = "", code: int = 500):
    try:
        packet = NetPacket(msgType="ErrMsgEvent", payload={"error": error, "code": code, "details": details})
        await websocket.send(packet.to_json())
    except Exception:
        pass  # client may have already disconnected


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
    print(f"[Handler] fallback weapon built: {weapon['id']}  budget={budget}  score={score}")
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
        session_id = req.session_id or "unknown_session"
        print(f"[Handler] received generation request: {req}")
        # req.prompt =f"[CRITICAL]YOU HAVE TO GENERATE A RANGE WEAPON WITH NEW FIREBALL PROJECTILE AND A NEW PAYLOAD!. {req.prompt}"
        _t_start = time.perf_counter()
        _timing_cb = TimingCallback()
        _progress_cb = WebSocketProgressCallback(_broadcast_progress, session_id)

        await _broadcast_progress({
            "type": "pipeline_start",
            "session_id": session_id,
            "config": _pipeline_config(),
        })

        final_state = await global_graph.ainvoke(
            {
                "prompt": req.prompt,
                "materials": req.materials,
                "biome": req.biome,
                "level": req.player_level,
                "weapons": req.weapons,
                "session_id": session_id,
                "world_level": req.world_level,
                "retry_count": 0,
                "audit_attempts": 0,
                "generation_history": [],
            },
            config={"callbacks": [_timing_cb, _progress_cb]},
            timeout=settings.PIPELINE_TIMEOUT_SECS,
        )

        await _broadcast_progress({"type": "pipeline_end", "session_id": session_id})

        output_data = final_state.get("final_output")
        if not output_data:
            print("❌ [Handler] generation failed: pipeline returned empty output, trying fallback")
            output_data = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if not output_data:
                await _send_error(websocket, "GenerationFailed", "Output is None and no fallback weapon available.")
                return

        output_data.pop("manual_analysis", None)
        output_data.pop("stat_balance_reasoning", None)
        output_data["icon"] = final_state.get("generated_icon") or output_data.get("icon") or "weapon_axe.png"
        icon_b64 = final_state.get("generated_icon_b64") or None
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

        generation_time = round(time.perf_counter() - _t_start, 2)
        node_timings = _timing_cb.get_timings()
        node_traces  = _progress_cb.get_trace()
        print(f"[Handler] generation time: {generation_time}s | nodes: {node_timings}")
        await _save_weapon_data(session_id, output_data, biome=req.biome, level=req.player_level,
                                generation_time_secs=generation_time, node_timings=node_timings,
                                node_traces=node_traces,
                                input_hash=final_state.get("input_hash"))

        event = WeaponGenerateEvent(
            timestamp=int(time.time()),
            content=output_data,
            new_payloads=new_payloads_list or None,
            new_projectiles=new_projectiles_list or None,
            icon_b64=icon_b64,
        )
        # print(f"[Handler] 生成成功，准备发送结果给 Unity: {str(event)}")
        await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
        print(f"[Handler] sending result to Unity: {output_data.get('id')}")

        # Broadcast the new weapon to all connected debug clients so their UI updates live
        await _broadcast_progress({
            "type": "new_weapon",
            "weapon": {
                "id": output_data.get("id"),
                "session_id": session_id,
                "is_preset": False,
                "content": output_data,
                "biome": req.biome,
                "level": req.player_level,
                "generation_time_secs": generation_time,
                "node_timings": node_timings,
                "node_traces": node_traces,
            },
        })

    except asyncio.TimeoutError:
        print("❌ [Handler] generation timed out, trying fallback")
        try:
            req = GenerationRequest.from_json(raw_message)
            fallback = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if fallback:
                event = WeaponGenerateEvent(timestamp=int(time.time()), content=fallback)
                await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
                print(f"[Handler] fallback sent: {fallback.get('id')}")
                return
        except Exception:
            pass
        await _send_error(websocket, "GenerationTimeout", "Pipeline timed out", code=504)
    except Exception as e:
        print(f"❌ [Handler] failed to handle request: {e}, trying fallback")
        try:
            req = GenerationRequest.from_json(raw_message)
            fallback = _make_fallback_weapon(req.weapons, req.world_level, req.player_level)
            if fallback:
                event = WeaponGenerateEvent(timestamp=int(time.time()), content=fallback)
                await websocket.send(NetPacket(msgType="WeaponGenerateEvent", payload=event.__dict__).to_json())
                print(f"[Handler] fallback sent: {fallback.get('id')}")
                return
        except Exception:
            pass
        await _send_error(websocket, "ServerError", str(e))


async def handle_debug_get_system_weapons(websocket, _raw: str):
    weapons = await weapon_mongo_service.get_weapons_by_session("SYSTEM")
    await websocket.send(json.dumps({"msgType": "DebugSystemWeaponList", "payload": {"weapons": weapons}}, default=str))


async def handle_debug_get_pipeline_config(websocket, _raw: str):
    await websocket.send(json.dumps({"msgType": "PipelineConfigEvent", "payload": _pipeline_config()}))


async def handle_debug_list_sessions(websocket, _raw_message: str):
    sessions = await weapon_mongo_service.get_all_sessions()
    await websocket.send(json.dumps({"msgType": "DebugSessionList", "payload": {"sessions": sessions}}))


async def handle_debug_get_weapons(websocket, raw_message: str):
    data = json.loads(raw_message)
    session_id = (data.get("payload") or {}).get("session_id", "")
    weapons = await weapon_mongo_service.get_weapons_by_session(session_id)
    await websocket.send(json.dumps({"msgType": "DebugWeaponList", "payload": {"weapons": weapons}}, default=str))


async def handle_debug_get_payloads(websocket, raw_message: str):
    data = json.loads(raw_message)
    session_id = (data.get("payload") or {}).get("session_id", "")
    payloads = await payload_mongo_service.get_session_payloads(session_id)
    await websocket.send(json.dumps({"msgType": "DebugPayloadList", "payload": {"payloads": payloads}}, default=str))


async def handle_debug_get_projectiles(websocket, raw_message: str):
    data = json.loads(raw_message)
    session_id = (data.get("payload") or {}).get("session_id", "")
    projectiles = await projectile_mongo_service.get_session_projectiles(session_id)
    await websocket.send(json.dumps({"msgType": "DebugProjectileList", "payload": {"projectiles": projectiles}}, default=str))


async def _save_weapon_data(session_id: str, final_weapon_data: dict, biome: str = None, level: int = None, generation_time_secs: float = None, node_timings: dict = None, node_traces: dict = None, input_hash: str = None):
    await weapon_mongo_service.save_generated_weapon(
        weapon_data=final_weapon_data,
        session_id=session_id,
        biome=biome,
        level=level,
        generation_time_secs=generation_time_secs,
        node_timings=node_timings,
        node_traces=node_traces,
        input_hash=input_hash,
    )
    try:
        backup_dir = settings.SESSIONS_DIR / session_id / "weapons"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{final_weapon_data.get('id', 'unknown')}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(final_weapon_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [Handler] local weapon backup failed (non-blocking): {e}")
"""
WebSocket integration test — requires the server to be running.

Start server first:
    python app/websocket/main.py

Then run:
    pytest tests/test_websocket_agent.py -v -s
"""
import json
import asyncio
import pytest
import websockets


SERVER_URI = "ws://localhost:8080"
LLM_TIMEOUT = 240.0   # local 14B model can be slow; raise if needed


# ---------------------------------------------------------------------------
# Shared packet builder
# ---------------------------------------------------------------------------

def _make_packet(biome: str = "Magma_Chamber", level: int = 5,
                 prompt: str = "Create a fire-themed weapon",
                 materials: list = None, weapons: list = None) -> str:
    if materials is None:
        materials = [
            {
                "id": "mat_fire_essence",
                "itemName": "Fire Essence",
                "itemType": 1,
                "description": "A crystallised stone that stores the power of fire.",
                "count_in_altar": 2,
            },
            {
                "id": "mat_obsidian_shard",
                "itemName": "Obsidian Shard",
                "itemType": 1,
                "description": "A razor-sharp volcanic glass fragment.",
                "count_in_altar": 1,
            },
        ]
    if weapons is None:
        weapons = [
            {
                "id": "weapon_starter_blade",
                "name": "Starter Blade",
                "abilities": {"on_hit": ["payload_strike"], "on_attack": [], "on_equip": []},
                "motions": [
                    {"primitive_id": "OP_ROTATE",
                     "params": {"start": 30, "end": -90, "curve": "EaseIn",
                                "time_start": 0.0, "time_end": 1.0}},
                ],
            }
        ]

    packet = {
        "msgType": "GenerationRequest",
        "payload": {
            "action": "generate_weapon",
            "biome": biome,
            "player_level": level,
            "prompt": prompt,
            "materials": materials,
            "weapons": weapons,
            "session_id": "test_session_ws_001",
        },
    }
    return json.dumps(packet, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_generate_weapon():
    """
    Full integration test:
      1. Connect to the WebSocket server.
      2. Send a GenerationRequest packet.
      3. Receive WeaponGenerateEvent and validate the weapon schema.
    """
    print(f"\n🔌 [Test] Connecting to {SERVER_URI}...")
    try:
        async with websockets.connect(SERVER_URI) as ws:
            print("✅ Connected")

            packet_str = _make_packet(
                biome="Magma_Chamber",
                level=5,
                prompt="A volcanic weapon that burns enemies over time",
            )
            print(f"📤 Sending GenerationRequest...")
            await ws.send(packet_str)

            print(f"⏳ Waiting for response (timeout={LLM_TIMEOUT}s)...")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=LLM_TIMEOUT)
            except asyncio.TimeoutError:
                pytest.fail(f"❌ LLM response timed out after {LLM_TIMEOUT}s")

            data = json.loads(raw)

            # --- Envelope ---
            assert data.get("msgType") == "WeaponGenerateEvent", \
                f"Unexpected msgType: {data.get('msgType')!r}. Full response: {data}"

            payload = data.get("payload", {})
            assert "content" in payload, f"Missing 'content' in payload: {payload}"

            weapon = payload["content"]

            # --- Required fields ---
            for field in ("id", "name", "stats", "motions", "abilities", "icon"):
                assert field in weapon, f"Missing field in weapon: '{field}'"

            stats = weapon["stats"]
            for stat in ("base_damage", "design_level", "cooldown", "range",
                         "duration", "hit_start", "hit_end"):
                assert stat in stats, f"Missing stat: '{stat}'"

            abilities = weapon["abilities"]
            assert isinstance(abilities.get("on_hit", []), list),    "on_hit must be list"
            assert isinstance(abilities.get("on_attack", []), list), "on_attack must be list"
            assert isinstance(abilities.get("on_equip", []), list),  "on_equip must be list"

            assert len(weapon["motions"]) >= 1, "Weapon must have at least one motion"

            # --- Print summary ---
            print(f"\n🎉 Weapon generated successfully!")
            print(f"   Name     : {weapon['name']}")
            print(f"   ID       : {weapon['id']}")
            print(f"   Biome    : Magma_Chamber  Level: {stats['design_level']}")
            print(f"   Damage   : {stats['base_damage']}  Cooldown: {stats['cooldown']}s")
            print(f"   on_hit   : {abilities.get('on_hit')}")
            print(f"   on_attack: {abilities.get('on_attack')}")
            print(f"   on_equip : {abilities.get('on_equip')}")
            print(f"   Icon     : {weapon['icon']}")
            if weapon.get("summary"):
                print(f"   Summary  : {weapon['summary']}")
            print(f"\n   Full JSON:\n{json.dumps(weapon, indent=2, ensure_ascii=False)}")

    except ConnectionRefusedError:
        pytest.fail(f"❌ Cannot connect to {SERVER_URI}. Is the server running?\n"
                    "   Start it with: python app/websocket/main.py")


@pytest.mark.asyncio
async def test_websocket_ping():
    """Minimal connectivity check — does not invoke the LLM."""
    print(f"\n🔌 [Test] Ping test to {SERVER_URI}...")
    try:
        async with websockets.connect(SERVER_URI) as ws:
            ping_packet = json.dumps({"msgType": "ping", "payload": {}})
            await ws.send(ping_packet)
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(raw)
            print(f"   Pong response: {data}")
            # Server should respond — exact msgType varies, just check it's valid JSON
            assert isinstance(data, dict), "Response is not a JSON object"
    except ConnectionRefusedError:
        pytest.fail(f"❌ Cannot connect to {SERVER_URI}. Is the server running?")
    except asyncio.TimeoutError:
        pytest.fail("❌ Ping timed out — server is not responding")

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

# === 对应 Unity 的 NetPacket (信封) ===
@dataclass
class NetPacket:
    msgType: str
    payload: Dict[str, Any]  # 对应 Unity 里的 JObject / payload

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

# === 对应 Unity 的 GenerationRequest (接收到的请求) ===
@dataclass
class GenerationRequest:
    action: str
    biome: str
    player_level: int
    prompt: Optional[str] = None
    materials: Optional[list] = None
    weapons: Optional[list] = None
    session_id: Optional[str] = None

    @staticmethod
    def from_json(json_str: str) -> 'GenerationRequest':
        data = json.loads(json_str).get("payload", {})
        return GenerationRequest(
            action=data.get("action", ""),
            biome=data.get("biome", "Unknown"),
            player_level=data.get("player_level", 1),
            prompt=data.get("prompt"),
            materials=data.get("materials", []),
            weapons=data.get("weapons", []),
            session_id=data.get("session_id"),
        )

# === 对应 Unity 的 WeaponGenerateEvent (发回的响应) ===
@dataclass
class WeaponGenerateEvent:
    timestamp: int
    content: Dict[str, Any]          # 武器数据 (JObject)
    new_payloads: Optional[List[Dict[str, Any]]] = None  # 本次新生成的 payload 定义列表，无则 null
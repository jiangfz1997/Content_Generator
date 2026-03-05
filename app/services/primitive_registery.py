import json
from pathlib import Path
from app.core.config import settings

class PrimitiveRegistry:
    def __init__(self):
        self.primitive_path = settings.PRIMITIVES_PATH
        self.payloads_path = settings.PAYLOADS_PATH
        self.primitive_motion_path = settings.MOTION_PATH
        self._cache = {}

    def get_all_primitives(self) -> dict:
        """从 JSON 加载所有可选的动作和效果"""
        try:
            with open(self.primitive_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            return self._cache
        except Exception as e:
            print(f"Load Primitives failed: {e}")
            return {
                "motion_primitives": ["OP_MOVE", "OP_ROTATE"],
                "ability_payloads": ["payload_fire_burn", "payload_ice_freeze"]
            }
    def get_all_payloads(self)-> dict:
        try:
            with open(self.payloads_path, "r", encoding="utf-8" ) as f:
                self._cache = json.load(f)
            return self._cache
        except Exception as e:
            print(f"load Payload Failed: {e}")
            return {
                "payload_fire_burn": {"description": "点燃目标，造成持续伤害"},

            }

    def get_all_motions(self) -> list:
        """获取所有动作原语"""
        try:
            with open(self.primitive_motion_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            return self._cache
        except Exception as e:
            print(f"Load Motions failed: {e}")
            return []


# 单例模式
primitive_registry = PrimitiveRegistry()
import json
from pathlib import Path
from typing import Dict, Any

from app.core.config import settings
from app.utils.formatter import format_registries_for_llm_yaml


class PrimitiveRegistry:
    def __init__(self):
        self.primitive_path = settings.PRIMITIVES_PATH
        self.payloads_dir = settings.PAYLOADS_PATH
        self.primitive_motion_path = settings.MOTION_PATH
        self._cache = {}

    # def get_all_primitives(self) -> dict:
    #     """从 JSON 加载所有可选的动作和效果"""
    #     try:
    #         with open(self.primitive_path, "r", encoding="utf-8") as f:
    #             self._cache = json.load(f)
    #         return self._cache
    #     except Exception as e:
    #         print(f"Load Primitives failed: {e}")
    #         return {
    #             "motion_primitives": ["OP_MOVE", "OP_ROTATE"],
    #             "ability_payloads": ["payload_fire_burn", "payload_ice_freeze"]
    #         }

    def get_primitives_schema(self) -> str:
        """读取 Primitives 的 Markdown 定义"""
        try:
            with open(Path(self.primitive_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Primitives Schema failed: {e}")
            return "No primitive schema found."

    def get_motions_schema(self) -> str:
        """读取 Motion Primitives 的 Markdown 定义"""
        try:
            with open(Path(self.primitive_motion_path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Load Motion Schema failed: {e}")
            return "No motion schema found."

    def get_all_payloads(self) -> Dict[str, Any]:
        """
        🌟 核心修改：扫描 payloads 文件夹下的所有 JSON 文件
        返回格式: { "payload_id": { ...json内容... }, ... }
        """
        payloads = {}

        if not self.payloads_dir.exists() or not self.payloads_dir.is_dir():
            print(f"⚠️ Warning: Payloads directory not found at {self.payloads_dir}")
            return {"payload_basic_attack": {"description": "基础攻击"}}

        # 扫描目录下所有 .json 后缀的文件
        for json_file in self.payloads_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    # 使用文件名（不带后缀）作为 Payload 的唯一 ID
                    payload_id = json_file.stem
                    payload_data = json.load(f)
                    payloads[payload_id] = payload_data
            except Exception as e:
                print(f"❌ Failed to load payload {json_file.name}: {e}")

        return payloads

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

def get_shared_engine_context():
    return format_registries_for_llm_yaml(
        available_payloads=primitive_registry.get_all_payloads(),
        available_primitives=primitive_registry.get_all_primitives(),
        available_motions=primitive_registry.get_all_motions(),
    )
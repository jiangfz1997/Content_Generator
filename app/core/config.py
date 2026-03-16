# app/core/config.py
import os
from pathlib import Path
import pyrootutils

# use .git as the indicator to find the project root
path = pyrootutils.setup_root(__file__, indicator=".git", pythonpath=True)

class Settings:

    BASE_DIR = path

    ENCODING = "utf-8"
    APP_DIR = BASE_DIR / "app"
    CORE_DIR = APP_DIR / "core"
    PROMPTS_DIR = CORE_DIR / "prompts"

    DATA_DIR = BASE_DIR /"app"/ "data"
    # PRIMITIVES_PATH = DATA_DIR / "primitives.json"
    PAYLOADS_PATH = DATA_DIR / "payloads"
    # MOTION_PATH = DATA_DIR / "primitive_motions.json"
    PRIMITIVES_PATH = DATA_DIR /"unity_schema"/ "PrimitivesSchema.md"
    MOTION_PATH = DATA_DIR /"unity_schema"/ "MotionPrimitivesSchema.md"
    WEAPON_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "WeaponSchema.md"
    PROJECTILE_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "ProjectileSchema.md"
    WEAPON_PRESET_PATH = DATA_DIR / "weapon_presets"


    MODEL_CONFIG_PATH = CORE_DIR / "model_config.yaml"

    OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = "qwen2.5-coder:14b"

    PIPELINE_TIMEOUT_SECS = 30.0
# 导出单例供全局使用
settings = Settings()
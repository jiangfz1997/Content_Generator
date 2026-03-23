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
    SESSIONS_DIR         = DATA_DIR / "sessions"
    PAYLOADS_PATH        = DATA_DIR / "sessions"   # kept for legacy fallback scan
    PROJECTILES_PATH     = DATA_DIR / "sessions"   # kept for legacy fallback scan
    PAYLOADS_PRESET_PATH    = DATA_DIR / "presets" / "payloads"
    PROJECTILES_PRESET_PATH = DATA_DIR / "presets" / "projectiles"
    WEAPON_PRESET_PATH      = DATA_DIR / "presets" / "weapons"
    # MOTION_PATH = DATA_DIR / "primitive_motions.json"
    PRIMITIVES_PATH = DATA_DIR /"unity_schema"/ "PrimitivesSchema.md"
    MOTION_PATH = DATA_DIR /"unity_schema"/ "MotionPrimitivesSchema.md"
    WEAPON_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "WeaponSchema.md"
    PROJECTILE_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "ProjectileSchema.md"


    MODEL_CONFIG_PATH = CORE_DIR / "model_config.yaml"

    OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = "qwen2.5-coder:14b"

    PIPELINE_TIMEOUT_SECS = 30.0

    # 设为 True 可跳过 concept_reviewer，designer 直接进入 forge_fork
    SKIP_IDEA_AUDIT: bool = os.getenv("SKIP_IDEA_AUDIT", "false").lower() == "true"
    # 设为 True 可跳过 tech_auditor，payload_validator 通过后直接进入 power_budget
    SKIP_TECH_AUDIT: bool = os.getenv("SKIP_TECH_AUDIT", "false").lower() == "true"
    # 设为 True 则裁剪注入 LLM 的 materials / weapons 字段，减少 token 消耗
    SLIM_CONTEXT: bool = os.getenv("SLIM_CONTEXT", "true").lower() == "true"
# 导出单例供全局使用
settings = Settings()
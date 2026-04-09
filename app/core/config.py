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
    PAYLOADS_PRESET_PATH    = DATA_DIR / "presets" / "payloads"    / "presets"
    PROJECTILES_PRESET_PATH = DATA_DIR / "presets" / "projectiles" / "presets"
    WEAPON_PRESET_PATH      = DATA_DIR / "presets" / "weapons"
    BASEIMG_DIR             = DATA_DIR / "baseimg_128"
    PROJECTILE_BASEIMG_DIR      = DATA_DIR / "projectile_base_img"
    PROJECTILE_ANIM_PRESETS_PATH = DATA_DIR / "presets" / "projectiles" / "animation_presets.yaml"
    # MOTION_PATH = DATA_DIR / "primitive_motions.json"
    PRIMITIVES_PATH = DATA_DIR /"unity_schema"/ "PrimitivesSchema.md"
    MOTION_PATH = DATA_DIR /"unity_schema"/ "MotionPrimitivesSchema.md"
    WEAPON_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "WeaponSchema.md"
    PROJECTILE_SCHEMA_PATH = DATA_DIR /"unity_schema"/ "ProjectileSchema.md"


    MODEL_CONFIG_PATH = CORE_DIR / "model_config.yaml"

    # local LLM config
    OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = "qwen2.5-coder:14b"

    # timeouts
    PIPELINE_TIMEOUT_SECS = 30.0

    # True for skipping concept_reviewer，designer -> forge_fork
    SKIP_IDEA_AUDIT: bool = os.getenv("SKIP_IDEA_AUDIT", "false").lower() == "true"
    # True for skipping tech_auditor，payload_validator -> power_budget
    SKIP_TECH_AUDIT: bool = os.getenv("SKIP_TECH_AUDIT", "false").lower() == "true"
    # True for using slim context (only weapon concept + feedback) for all ops, False for using full context (weapon + payload + projectile concepts + feedback) for all ops
    SLIM_CONTEXT: bool = os.getenv("SLIM_CONTEXT", "true").lower() == "true"
    # "sd" = Stable Diffusion (existing), "composite" = base image + tint (new)
    ARTIST_MODE: str = os.getenv("ARTIST_MODE", "composite")
    
    # Workflow topology:
    #   "serial"            — factories serial, artist after power_budget (safest, slowest)
    #   "factory_parallel"  — two factories parallel, weapon+artist parallel after factories
    #   "full_parallel"     — all four ops parallel from concept_fork (fastest)
    WORKFLOW_MODE: str = os.getenv("WORKFLOW_MODE", "full_parallel")
    # True = skip input-combination cache (materials+weapons+biome hash), always run designer
    SKIP_INPUT_CACHE: bool = os.getenv("SKIP_INPUT_CACHE", "false").lower() == "true"
    
settings = Settings()
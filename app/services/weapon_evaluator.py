# app/services/weapon_evaluator.py
from typing import Any, Dict, List

class WeaponEvaluator:
    RANGE_WEIGHT = 0.2
    HEAL_WEIGHT = 2.0
    # Tolerance for BOTH scaling up and down
    SCALE_TOLERANCE = 0.1 

    # TargetBudget curve: budget = BASE * world_level^EXPONENT
    BUDGET_BASE = 10.0
    BUDGET_EXPONENT = 1.5

    @classmethod
    def get_target_budget(cls, world_level: int) -> float:
        """Lv1→10, Lv5→111, Lv10→316"""
        return round(cls.BUDGET_BASE * (max(1, world_level) ** cls.BUDGET_EXPONENT), 2)

    @classmethod
    def _collect_ops(cls, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Recursively extract HP modifications and Projectile counts.
        Returns aggregated data.
        """
        data = {
            "dmg_mult": 0.0,
            "heal_mult": 0.0,
            "flat_dmg": 0.0,
            "flat_heal": 0.0,
            "projectile_count": 0
        }
        
        for step in sequence:
            if not isinstance(step, dict):
                continue
                
            pid = step.get("primitive_id", "")
            params = step.get("params") or {}
            
            if pid == "OP_MODIFY_HP":
                val = abs(float(params.get("value", 0)))
                category = params.get("category", "damage")
                source = params.get("source", "absolute")
                
                if category in ("damage", "self_damage"):
                    if source == "weapon_multiplier":
                        data["dmg_mult"] += val
                    else:
                        data["flat_dmg"] += val
                elif category == "heal":
                    if source == "weapon_multiplier":
                        data["heal_mult"] += val
                    else:
                        data["flat_heal"] += val
                        
            elif pid == "OP_SPAWN_PROJECTILE":
                data["projectile_count"] += int(params.get("count", 1))

            elif pid == "OP_TIMER":
                # Multiply nested damage by actual tick count (duration / interval)
                tick_count = params.get("duration", 1.0) / max(params.get("interval", 1.0), 0.01)
                nested_data = cls._collect_ops(params.get("actions") or [])
                for k, v in nested_data.items():
                    data[k] += v * tick_count
                    
        return data

    @classmethod
    def calculate_power_score(
        cls,
        weapon_stats: Dict[str, Any],
        payload_sequences: List[Dict[str, Any]],
    ) -> float:
        base_damage = float(weapon_stats.get("base_damage", 10))
        cooldown    = float(weapon_stats.get("cooldown", 1.0))
        duration    = float(weapon_stats.get("duration", 0.45))
        atk_range   = float(weapon_stats.get("range", 1.0))

        cycle_time = max(cooldown + duration, 0.1)
        ops_data = cls._collect_ops(payload_sequences)

        # 1. Base multiplier logic
        dmg_mult = ops_data["dmg_mult"]
        
        # 2. Projectile compensation
        # If it spawns projectiles, assume each projectile carries at least a 1.0 multiplier 
        # (Assuming the projectile DB uses 1.0 by default if we can't read it here)
        if ops_data["projectile_count"] > 0:
            dmg_mult += float(ops_data["projectile_count"])

        # 3. Fallback for pure vanilla weapons (no payloads)
        if dmg_mult == 0:
            dmg_mult = 1.0 

        # Calculate eDPS combining multipliers and flat damage
        e_dps_mult = (base_damage / cycle_time) * dmg_mult
        e_dps_flat = (ops_data["flat_dmg"] / cycle_time)
        total_e_dps = e_dps_mult + e_dps_flat

        aoe_factor = 1.0 + (atk_range * cls.RANGE_WEIGHT)
        
        # Calculate utility score combining multipliers and flat heals
        utility_mult = (ops_data["heal_mult"] * base_damage * cls.HEAL_WEIGHT) / cycle_time
        utility_flat = (ops_data["flat_heal"] * cls.HEAL_WEIGHT) / cycle_time
        total_utility = utility_mult + utility_flat

        return round((total_e_dps * aoe_factor) + total_utility, 2)

    @classmethod
    def auto_scale(cls, weapon_json: Dict[str, Any], world_level: int) -> tuple[Dict[str, Any], float, float]:
        from app.services.primitive_registry import primitive_registry

        abilities = weapon_json.get("abilities") or {}
        used_ids = (
            (abilities.get("on_hit")    or []) +
            (abilities.get("on_attack") or []) +
            (abilities.get("on_equip")  or [])
        )

        all_payloads = primitive_registry.get_all_payloads()
        combined_sequence: List[Dict[str, Any]] = []
        for pid in used_ids:
            payload = all_payloads.get(pid)
            if payload:
                combined_sequence.extend(payload.get("sequence") or [])

        stats  = weapon_json.get("stats") or {}
        score  = cls.calculate_power_score(stats, combined_sequence)
        budget = cls.get_target_budget(world_level)

        # Bi-directional scaling: Scale DOWN if too strong, scale UP if too weak
        lower_bound = budget * (1 - cls.SCALE_TOLERANCE)
        upper_bound = budget * (1 + cls.SCALE_TOLERANCE)

        if score < lower_bound or score > upper_bound:
            # Prevent division by zero if score is completely 0
            safe_score = max(score, 0.1) 
            ratio = budget / safe_score
            original = stats.get("base_damage", 10)
            
            # Apply scaling, ensure base damage never drops below 1.0
            scaled = max(1.0, round(original * ratio, 1))
            
            weapon_json = {**weapon_json, "stats": {**stats, "base_damage": scaled, "design_level": world_level}}
            print(f"[WeaponEvaluator] Score {score} off budget {budget} — scaled base_damage {original} → {scaled}")
        else:
            # Stamp the design level even if scaling wasn't needed
            weapon_json = {**weapon_json, "stats": {**stats, "design_level": world_level}}
            print(f"[WeaponEvaluator] Score {score} within budget {budget} — no scaling needed.")

        return weapon_json, score, budget
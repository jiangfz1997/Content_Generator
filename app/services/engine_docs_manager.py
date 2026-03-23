# app/services/engine_docs_manager.py
from app.core.config import settings
from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION
from app.services.primitive_registry import primitive_registry


# Section header markers — must match what refresh_manual() writes
_SEC_CONSTITUTION  = "# GLOBAL DESIGN CONSTITUTION (STRICT RULES)"
_SEC_TACTICAL      = "# Engine Tactical Manual"
_SEC_PAYLOAD_CAT   = "## Payload Catalog"
_SEC_WEAPON        = "# Weapon Implementation Reference"
_SEC_PROJECTILE    = "# Projectile Implementation Reference"


class EngineDocsManager:
    def __init__(self):
        self._cached_md = None
        self._sections: dict = {}          # keyed by section name
        self._is_ready = False
        self.cache_path = settings.DATA_DIR / "instruction_manual.md"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_sections(self, full_md: str) -> dict:
        """Split full manual into named sections for targeted injection."""
        secs = {}

        def _between(text: str, start_marker: str, *end_markers) -> str:
            s = text.find(start_marker)
            if s == -1:
                return ""
            end = len(text)
            for em in end_markers:
                e = text.find(em, s + len(start_marker))
                if e != -1:
                    end = min(end, e)
            return text[s:end].strip()

        secs["constitution"]   = _between(full_md, _SEC_CONSTITUTION, _SEC_TACTICAL)
        secs["tactical"]       = _between(full_md, _SEC_TACTICAL, _SEC_WEAPON)
        secs["payload_catalog"]= _between(full_md, _SEC_PAYLOAD_CAT, _SEC_WEAPON)
        secs["weapon_schema"]  = _between(full_md, _SEC_WEAPON, _SEC_PROJECTILE)
        secs["projectile"]     = _between(full_md, _SEC_PROJECTILE)
        return secs

    async def _ensure_loaded(self) -> str:
        if self._cached_md:
            return self._cached_md
        if self.cache_path.exists():
            print(f"📂 [EngineDocs] 发现本地手册，极速加载: {self.cache_path}")
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cached_md = f.read()
                self._sections = self._parse_sections(self._cached_md)
                return self._cached_md
            except Exception as e:
                print(f"⚠️ [EngineDocs] 读取本地 MD 失败: {e}，准备重新生成...")
        return await self.refresh_manual()

    # ------------------------------------------------------------------
    # Public getters — each agent calls only what it needs
    # ------------------------------------------------------------------

    async def get_markdown_manual(self) -> str:
        """Full manual — for designer and weapon_crafter."""
        return await self._ensure_loaded()

    async def get_factory_manual(self) -> str:
        """Payload Factory: Engine Tactical Manual only (primitive index + payload catalog).
        Excludes Constitution, Weapon Schema, Projectile Schema — ~60% token reduction."""
        await self._ensure_loaded()
        return self._sections.get("tactical", await self.get_markdown_manual())

    async def get_audit_manual(self) -> str:
        """Tech Auditor: Payload Catalog + Weapon Schema only.
        Excludes Constitution, primitive motion details, Projectile Schema."""
        await self._ensure_loaded()
        parts = [
            self._sections.get("payload_catalog", ""),
            self._sections.get("weapon_schema", ""),
        ]
        result = "\n\n---\n\n".join(p for p in parts if p)
        return result or await self.get_markdown_manual()

    async def get_reviewer_manual(self) -> str:
        """Concept Reviewer (idea audit): Payload Catalog only.
        The idea stage only needs to know what payloads exist."""
        await self._ensure_loaded()
        return self._sections.get("payload_catalog", await self.get_markdown_manual())

    async def get_crafter_manual(self) -> str:
        """Weapon Crafter: Weapon Schema + Projectile Schema only.
        Payload selection is handled upstream by the designer's chosen_payload_ids.
        Excludes Constitution, Tactical Manual, Payload Catalog — ~70% token reduction vs full manual."""
        await self._ensure_loaded()
        parts = [
            self._sections.get("weapon_schema", ""),
            self._sections.get("projectile", ""),
        ]
        result = "\n\n---\n\n".join(p for p in parts if p)
        return result or await self.get_markdown_manual()

    # ------------------------------------------------------------------
    # Refresh (AI summarize + write to disk)
    # ------------------------------------------------------------------

    async def refresh_manual(self) -> str:
        """Force AI summarization, assemble and overwrite local .md file."""
        from app.agents.summarizer.graph import summarizer_agent

        print("\033[94m[EngineDocs] 正在呼叫 AI 进行底层逻辑总结...\033[0m")
        manual_obj, primitive_str = await summarizer_agent.summarize_engine()

        md_lines = [
            "# GLOBAL DESIGN CONSTITUTION (STRICT RULES)",
            GLOBAL_DESIGN_CONSTITUTION,
            "\n---\n",
            "# Engine Tactical Manual",
            f"**Overview:** {manual_obj.primitive_summary}\n",
            primitive_str,
            "\n## Payload Catalog"
        ]

        for payload in manual_obj.payload_catalog:
            md_lines.append(f"### {payload.id}")
            md_lines.append(f"- Tactical Intent: {payload.tactical_intent}")
            md_lines.append(f"- Logic: {payload.combination_logic}\n")

        md_lines.append("\n---\n")
        md_lines.append("# Weapon Implementation Reference")
        md_lines.append(primitive_registry.get_weapon_schema())

        md_lines.append("\n---\n")
        md_lines.append("# Projectile Implementation Reference")
        md_lines.append(primitive_registry.get_projectile_schema())

        final_md_string = "\n".join(md_lines)

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                f.write(final_md_string)
            print(f"💾 [EngineDocs] 终极手册已持久化保存至: {self.cache_path}")
        except Exception as e:
            print(f"❌ [EngineDocs] 保存缓存失败: {e}")

        self._cached_md = final_md_string
        self._sections = self._parse_sections(final_md_string)
        return self._cached_md


# 单例实例化
engine_docs_manager = EngineDocsManager()

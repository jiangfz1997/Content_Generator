# app/services/engine_docs_manager.py
from app.core.config import settings
from app.core.global_prompts import GLOBAL_DESIGN_CONSTITUTION


class EngineDocsManager:
    def __init__(self):
        self._cached_md = None
        self._is_ready = False
        self.cache_path = settings.DATA_DIR  / "instruction_manual.md"

    def _load_from_file(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return f.read()

        except FileNotFoundError as e:
            print(f"[EngineDocs] Failed to load manual from {self.cache_path}")




    async def get_markdown_manual(self) -> str:
        if self._cached_md:
            return self._cached_md

        if self.cache_path.exists():
            print(f"📂 [EngineDocs] 发现本地手册，极速加载: {self.cache_path}")
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cached_md = f.read()
                    return self._cached_md
            except Exception as e:
                print(f"⚠️ [EngineDocs] 读取本地 MD 失败: {e}，准备重新生成...")

            # 3. 如果都没有，呼叫 AI 重新总结并生成
        return await self.refresh_manual()

        # from app.agents.summarizer.graph import FinalEngineManual
        #
        # manual: FinalEngineManual = self._cached_manual
        # if not manual:
        #     return ""
        #
        # md_lines = [
        #     "# GLOBAL DESIGN CONSTITUTION (STRICT RULES)",
        #     GLOBAL_DESIGN_CONSTITUTION,
        #     "\n---\n",
        #     "# Engine Tactical Manual",
        #     f"**Overview:** {self._cached_manual.primitive_summary}\n",
        #     "## Payload Catalog"
        # ]
        #
        # for payload in manual.payload_catalog:
        #     md_lines.append(f"###  {payload.id}")
        #     md_lines.append(f"- **Tactical Intent**: {payload.tactical_intent}")
        #     md_lines.append(f"- **Logic**: {payload.combination_logic}\n")
        #
        # return "\n".join(md_lines)

    async def refresh_manual(self) -> str:
        """强制呼叫 AI 总结，拼装并覆写本地 .md 文件"""
        from app.agents.summarizer.graph import summarizer_agent

        print("\033[94m[EngineDocs] 正在呼叫 AI 进行底层逻辑总结...\033[0m")
        # 让 AI 吐出 Pydantic 结构
        manual_obj, primitive_str = await summarizer_agent.summarize_engine()

        # 🌟 立刻在内存里将 Pydantic 拼装成 Markdown 字符串
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

        final_md_string = "\n".join(md_lines)

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                f.write(final_md_string)
            print(f"💾 [EngineDocs] 终极手册已持久化保存至: {self.cache_path}")
        except Exception as e:
            print(f"❌ [EngineDocs] 保存缓存失败: {e}")

        self._cached_md = final_md_string
        return self._cached_md




# 单例实例化
engine_docs_manager = EngineDocsManager()
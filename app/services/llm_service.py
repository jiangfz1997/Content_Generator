# app/services/llm_service.py
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
import os
from app.core.config import settings # 建议引入配置类管理 URL 和模型名

class LLMService:
    def __init__(self):
        # 1. 纯粹的模型初始化
        # 这里不绑定任何 Prompt，它就是一个通用的推理引擎
        self.model = ChatOllama(
            model="qwen2.5-coder:14b",
            temperature=0.7,
            format="json",
            base_url="http://localhost:11434"
        )

        self.mini_model = ChatOllama(
            model="qwen2.5-coder:14b",
            num_predict=500,
            temperature=0.7,
            format="json",
            base_url="http://localhost:11434",
        )

        api_key = os.getenv("OPENAI_API_KEY", "your-fallback-key-here")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.gpt_model = ChatOpenAI(
            model = os.getenv("ONLINE_NANO_MODEL"),
            api_key = api_key,
            base_url = base_url,
            temperature = 0.5,
            max_retries = 3,
            timeout=30
        )

    async def fast_invoke(self, prompt_value):
        """
        处理最基础的、非 Agent 编排的简单推理任务
        """
        return await self.model.ainvoke(prompt_value)

# 全局单例：作为整台机器的 GPU 调度入口
llm_service = LLMService()
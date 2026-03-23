# app/services/llm_service.py
import os
import yaml
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from openai import max_retries

from app.core.config import settings


class LLMService:
    def __init__(self):
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

        google_flash_model = os.getenv("GOOGLE_FLASH_MODEL")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        self.google_flash_model = ChatGoogleGenerativeAI(
            model=google_flash_model,
            api_key=google_api_key,
            temperature=0.7,
            max_retries=3,
            timeout=30,
        )

        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.gpt_model = ChatOpenAI(
            model=os.getenv("ONLINE_NANO_MODEL"),
            api_key=api_key,
            base_url=base_url,
            temperature=0.5,
            max_retries=3,
            timeout=60
        )

        self._models = {
            "model": self.model,
            "mini_model": self.mini_model,
            "gpt_model": self.gpt_model,
            "google_flash_model": self.google_flash_model,

        }

        # Load agent → model key mapping from model_config.yaml
        self._agent_model_map: dict = {}
        config_path = settings.MODEL_CONFIG_PATH
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._agent_model_map = yaml.safe_load(f) or {}

    def get_model(self, agent: str):
        """Return the configured model instance for a given agent name."""
        model_key = self._agent_model_map.get(agent, "model")
        return self._models.get(model_key, self.model)

    async def fast_invoke(self, prompt_value):
        return await self.model.ainvoke(prompt_value)


# 全局单例：作为整台机器的 GPU 调度入口
llm_service = LLMService()

# app/utils/callbacks.py
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

from app.core.config import settings

_PROMPT_LOG_BASE = settings.BASE_DIR / "logs" / "prompts"


class AgentConsoleCallback(BaseCallbackHandler):
    def __init__(self, agent_name: str = "Agent"):
        self.agent_name = agent_name

    def on_llm_start(self, serialized, prompts, **kwargs):
        print(f"\n🧠 [{self.agent_name}] 模型开始推理 (请耐心等待本地模型)...")
        print(f"[{self.agent_name}] 输出: ", end="", flush=True)

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs):
        print(f"\n🧠 [{self.agent_name}] 模型开始推理 (请耐心等待本地模型)...")
        print(f"[{self.agent_name}] 输出: ", end="", flush=True)

    def on_llm_new_token(self, token: str, **kwargs):
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_llm_end(self, response, **kwargs):
        print(f"\n✅ [{self.agent_name}] 推理完成！\n")

    def on_llm_error(self, error, **kwargs):
        print(f"\n❌ [{self.agent_name}] 发生严重错误: {error}\n")


class PromptLogCallback(BaseCallbackHandler):
    """Writes the exact prompt sent to the model to logs/prompts/{session_id}/{ts}_{agent}.txt"""

    def __init__(self, agent_name: str = "Agent", session_id: str = "default"):
        self.agent_name = agent_name
        self.session_id = session_id

    def _write(self, content: str):
        log_dir = _PROMPT_LOG_BASE / self.session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        path = log_dir / f"{ts}_{self.agent_name}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs):
        parts = []
        for msg_list in messages:
            for msg in msg_list:
                role = msg.type.upper()
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                parts.append(f"[{role}]\n{content}")
        self._write("\n\n" + ("=" * 60) + "\n\n".join(parts))

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._write("\n\n".join(prompts))


def make_callbacks(agent_name: str, session_id: str = "default") -> list:
    """Return [AgentConsoleCallback, PromptLogCallback] for a given agent + session."""
    return [
        AgentConsoleCallback(agent_name=agent_name),
        PromptLogCallback(agent_name=agent_name, session_id=session_id),
    ]
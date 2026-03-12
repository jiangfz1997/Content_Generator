# app/utils/callbacks.py
import sys
from langchain_core.callbacks import BaseCallbackHandler

class AgentConsoleCallback(BaseCallbackHandler):
    def __init__(self, agent_name: str = "Agent"):
        self.agent_name = agent_name

    def on_llm_start(self, serialized, prompts, **kwargs):
        print(f"\n🧠 [{self.agent_name}] 模型开始推理 (请耐心等待本地模型)...")
        print(f"[{self.agent_name}] 输出: ", end="", flush=True)

    def on_llm_new_token(self, token: str, **kwargs):
        """流式输出：每一个字蹦出来的时候都会触发"""
        # 直接写到控制台而不换行，实现打字机效果
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_llm_end(self, response, **kwargs):
        print(f"\n✅ [{self.agent_name}] 推理完成！\n")

    def on_llm_error(self, error, **kwargs):
        print(f"\n❌ [{self.agent_name}] 发生严重错误: {error}\n")
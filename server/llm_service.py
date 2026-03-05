from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, load_prompt
from langchain_ollama import ChatOllama


class  LLMService:
    def __init__(self):
        self.llm = ChatOllama(
            model = "qwen2.5-coder:14b",
            temperature = 0.7,
            format="json"
        )
        self.parser = JsonOutputParser()

        self.weapon_prompt = load_prompt("../app/core/prompts/weapon_crafter.yaml")
        self.weapon_chain = self.weapon_prompt | self.llm | self.parser

    async def generate_weapon(self, biome: str, level: int):
        """
        核心业务方法：调用 LangChain 生成武器
        """
        # 使用 ainvoke 确保不阻塞异步事件循环
        result = await self.weapon_chain.ainvoke({
            "biome": biome,
            "level": level
        })
        return result


# 全局单例，方便 Handler 调用
llm_service = LLMService()


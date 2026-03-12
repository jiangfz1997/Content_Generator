# app/utils/inject_prompts.py
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate


def inject_prompts(inject_content: str, prompt_template):
    """
    灵活注入全局宪法，兼容 ChatPromptTemplate 和 普通 PromptTemplate
    """
    # 🌟 情况 A: 如果是 ChatPromptTemplate (包含消息序列)
    if hasattr(prompt_template, 'messages'):
        # 通常修改第一条消息 (System Message)
        first_msg = prompt_template.messages[0]
        if hasattr(first_msg, 'prompt'):
            first_msg.prompt.template = inject_content + "\n\n" + first_msg.prompt.template
        else:
            # 兼容非模板类的消息
            print("[Warning] First message has no inner prompt template.")

    # 🌟 情况 B: 如果是普通的 PromptTemplate (单一段落)
    elif hasattr(prompt_template, 'template'):
        prompt_template.template = inject_content + "\n\n" + prompt_template.template

    else:
        raise TypeError(f"Unsupported prompt type: {type(prompt_template)}")
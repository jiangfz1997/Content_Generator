import pytest
import json
# 导入你的图和状态定义 (根据你的实际路径调整)
from app.core.workflow import global_graph
from app.core.state import GlobalState

mock_materials = [
    {
        'id': 'mat_fire_essence',
        'itemName': 'Fire Essence',
        'icon': {'instanceID': 49168},  # 注意：如果在纯后端跑，这种 Unity 内部 ID 对 AI 没用，但传过去也没事
        'maxStack': 99,
        'itemType': 1,
        'description': 'A stone stores the power of fire.',
        'count_in_altar': 2
    }
]

# 提取出来的武器字典
mock_weapons = [
    {
        'id': 'weapon_axe',
        'name': 'Mjolnir Prototype',
        'abilities': {'on_hit': 'payload_fire_burn'},
        'motions': [
            {'primitive_id': 'OP_ROTATE', 'params': {'start': 10, 'end': -110, 'curve': 'EaseIn'}},
            {'primitive_id': 'OP_MOVE',
             'params': {'start': {'x': 0.0, 'y': 0}, 'end': {'x': 1.5, 'y': 0}, 'curve': 'PingPong'}}
        ]
    },
{
  "id": "weapon_spear",
  "name": "Mjolnir Prototype",
  "abilities": {
    "on_hit": "payload_heavy_smash"
  },
  "motions": [
    {
      "primitive_id": "OP_MOVE",
      "params": {
        "start": { "x": 0, "y": 0 },
        "end":   { "x": 3.0, "y": 0 },
        "curve": "PingPong"
      }
    }
  ]
}
]
@pytest.mark.asyncio
async def test_weapon_generation_pipeline():
    # 1. 组装 Mock 的初始状态 (模拟 Handler 收到请求后转换成的 State)
    initial_state: GlobalState = {
        "materials": mock_materials,
        "weapons": mock_weapons,
        "biome": "Magma_Chamber",
        "level": 20,


        # 必须初始化这些防御性字段，防止报错
        "retry_count": 0,
        "design_concept": "",
        "final_weapon": None,
        "is_idea_passed": None,
        "idea_feedback": "",
        "is_final_passed": None,
        "tech_feedback": ""
    }

    print("\n🚀 [Test] 开始测试锻造流水线...")

    # 2. 执行流水线 (这里会真实调用 LLM，建议用 mini 模型测试)
    final_state = await global_graph.ainvoke(initial_state)

    # 3. 断言与结果打印
    # 检查流水线是否走完了，且最终生成了武器
    assert final_state.get("final_output") is not None, "流水线熔断，未能生成最终武器 JSON"

    # 打印各个环节的输出，方便你观察 AI 的“脑回路”
    print("\n--- 💡 策划草案 (Concept) ---")
    print(final_state.get("design_concept"))

    print("\n--- ⚖️ 创意审核结果 ---")
    print(f"Passed: {final_state.get('is_idea_passed')}")
    print(f"Feedback: {final_state.get('idea_feedback')}")

    print("\n--- 🛠️ 最终武器 JSON (Final Weapon) ---")
    print(json.dumps(final_state.get("final_output"), indent=2, ensure_ascii=False))
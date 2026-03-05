from typing import *

import yaml # pip install pyyaml

def format_registries_for_llm_yaml(**kwargs: List[Dict[str, Any]]) -> Dict[str, str]:
    result = {}
    for key, data_list in kwargs.items():
        # default_flow_style=False 保证输出是纯粹的缩进结构
        result[key] = yaml.dump(data_list, allow_unicode=True, default_flow_style=False)
    return result
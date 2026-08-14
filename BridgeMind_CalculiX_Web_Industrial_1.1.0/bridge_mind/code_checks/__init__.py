"""BridgeMind 可审计规范验算接口。"""  # 说明包用途。
from .engine import run_code_check_plan  # 导出规则包执行入口。
__all__ = ["run_code_check_plan"]  # 声明公共接口。

"""BridgeMind 工业扩展层。"""  # 说明包用途。
from .migration import upgrade_document  # 导出旧版文档升级函数。
from .capabilities import build_capability_matrix  # 导出能力矩阵构造函数。
__all__ = ["upgrade_document", "build_capability_matrix"]  # 声明公共接口。

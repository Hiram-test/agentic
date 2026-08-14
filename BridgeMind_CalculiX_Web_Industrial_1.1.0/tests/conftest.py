"""提供 BridgeMind 测试共享路径和文档夹具。"""  # 说明测试配置用途。
from pathlib import Path  # 提供项目路径处理。
import pytest  # 提供测试夹具装饰器。
from bridge_mind.utils import load_json  # 导入 BSDL JSON 读取工具。


ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


@pytest.fixture()  # 注册双主梁桥文档夹具。
def bridge_document() -> dict:  # 返回每次测试独立读取的示例文档。
    return load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取双主梁桥示例。


@pytest.fixture()  # 注册空间悬臂梁文档夹具。
def cantilever_document() -> dict:  # 返回每次测试独立读取的悬臂梁示例。
    return load_json(ROOT / "examples" / "cantilever_3d.bsdl.json")  # 读取空间悬臂梁示例。

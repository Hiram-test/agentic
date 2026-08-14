"""验证点云分割到初始 BSDL 文档的可运行路径。"""  # 说明测试文件用途。
from pathlib import Path  # 提供示例点云路径。
from bridge_mind.importers.point_cloud import build_bsdl_from_point_cloud  # 导入点云转换器。
from bridge_mind.validator import validate_document  # 导入 BSDL 验证器。


def test_point_cloud_generates_valid_bsdl() -> None:  # 检查示例点云可转换为可编辑结构对象。
    root = Path(__file__).resolve().parents[1]  # 获取项目根目录。
    document, report = build_bsdl_from_point_cloud(root / "examples" / "two_girder_bridge.xyz")  # 执行降采样、聚类和代理几何生成。
    assert report["inputPointCount"] > report["sampledPointCount"]  # 确认体素降采样减少点数。
    assert report["clusterCount"] >= 1  # 确认至少识别一个点簇。
    assert len(document["components"]) >= report["clusterCount"] + 1  # 确认每个点簇生成构件并保留根结构对象。
    assert validate_document(document)["valid"] is True  # 确认生成文档满足 BSDL 规则。

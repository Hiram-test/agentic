"""验证内置空间梁快速 FEA 的主要数值结果。"""  # 说明测试文件用途。
import math  # 提供有限数检查。
from bridge_mind.fea.frame3d import solve_document  # 导入确定性空间梁求解器。


def test_two_girder_bridge_solves_and_balances(bridge_document: dict) -> None:  # 检查双主梁桥求解与反力平衡。
    result = solve_document(bridge_document)  # 执行默认工况快速试算。
    metrics = result["globalMetrics"]  # 读取全局指标。
    assert result["status"] == "succeeded"  # 确认求解成功。
    assert result["mesh"]["stats"]["elementCount"] > 13  # 确认网格策略对原始构件进行了分段。
    assert math.isfinite(metrics["maxVerticalDisplacement"])  # 确认最大竖向位移为有限数。
    assert metrics["maxVerticalDisplacement"] > 0.0  # 确认荷载产生非零竖向响应。
    assert metrics["relativeForceBalanceResidual"] < 1.0e-9  # 确认全局反力平衡满足快速试算阈值。


def test_cantilever_response_is_nonzero(cantilever_document: dict) -> None:  # 检查空间悬臂梁具有合理非零响应。
    result = solve_document(cantilever_document)  # 执行悬臂梁求解。
    assert result["status"] == "succeeded"  # 确认求解成功。
    assert result["globalMetrics"]["maxTranslation"] > 0.0  # 确认平移响应非零。
    assert result["globalMetrics"]["maxMoment"] > 0.0  # 确认弯矩响应非零。

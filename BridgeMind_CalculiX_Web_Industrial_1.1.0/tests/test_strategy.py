"""验证多专家区域策略与认知地图生成。"""  # 说明测试文件用途。
from bridge_mind.cognition.orchestrator import propose_strategy  # 导入多专家策略编排器。
from bridge_mind.fea.frame3d import solve_document  # 导入快速 FEA 以形成热点反馈。
from bridge_mind.validator import validate_document  # 导入 BSDL 验证器。


def test_experts_generate_regions_and_cognitive_map(bridge_document: dict) -> None:  # 检查初始结构认知策略。
    updated, report = propose_strategy(bridge_document)  # 运行支承、节点、突变和平滑 experts。
    semantics = {region["semanticType"] for region in updated["regions"]}  # 收集生成区域语义类型。
    assert report["generatedRegionCount"] > 0  # 确认 expert 产生至少一个区域提案。
    assert {"support", "joint", "discontinuity", "smooth"}.issubset(semantics)  # 确认四类基础认知区域均出现。
    assert len(updated["cognitiveMap"]["landmarks"]) > 0  # 确认认知地图具有局部地标。
    assert len(updated["cognitiveMap"]["decisionEdges"]) > 0  # 确认地标具有可执行决策关系。
    assert validate_document(updated)["valid"] is True  # 确认自动策略仍满足语言规则。


def test_fea_feedback_creates_hotspot_regions(bridge_document: dict) -> None:  # 检查计算反馈能够追加热点认知区域。
    proposed, _ = propose_strategy(bridge_document)  # 先生成基础区域和网格策略。
    result = solve_document(proposed)  # 根据策略执行快速 FEA。
    updated, report = propose_strategy(proposed, result)  # 把 FEA 结果交给热点 expert。
    hotspots = [region for region in updated["regions"] if region["semanticType"] == "hotspot" and region["source"] == "fea"]  # 提取 FEA 热点区域。
    assert report["feaFeedbackUsed"] is True  # 确认编排器识别并使用 FEA 反馈。
    assert len(hotspots) > 0  # 确认至少生成一个计算热点区。
    assert validate_document(updated)["valid"] is True  # 确认反馈闭环文档合法。

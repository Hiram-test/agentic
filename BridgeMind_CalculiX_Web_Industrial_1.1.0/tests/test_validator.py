"""验证 BSDL 结构、引用、拓扑和求解前规则。"""  # 说明测试文件用途。
from bridge_mind.utils import deep_copy  # 导入文档深复制工具。
from bridge_mind.validator import validate_document  # 导入完整验证器。


def test_examples_are_valid(bridge_document: dict, cantilever_document: dict) -> None:  # 检查两个正式示例均达到 L4。
    bridge_report = validate_document(bridge_document)  # 验证双主梁桥示例。
    cantilever_report = validate_document(cantilever_document)  # 验证空间悬臂梁示例。
    assert bridge_report["valid"] is True  # 确认双主梁桥没有阻断问题。
    assert bridge_report["level"] == "L4-valid"  # 确认双主梁桥达到完整一致性等级。
    assert cantilever_report["valid"] is True  # 确认悬臂梁没有阻断问题。
    assert cantilever_report["stats"]["activeFrameComponents"] > 0  # 确认悬臂梁包含可求解构件。


def test_dangling_reference_is_blocked(bridge_document: dict) -> None:  # 检查悬空节点引用会阻止执行。
    invalid = deep_copy(bridge_document)  # 创建独立非法文档。
    invalid["components"][1]["nodeRefs"][0] = "node.missing"  # 注入不存在节点引用。
    report = validate_document(invalid)  # 验证非法文档。
    assert report["valid"] is False  # 确认非法引用导致验证失败。
    assert any(issue["ruleId"] == "BSDL-REF-001" for issue in report["errors"])  # 确认返回稳定引用规则 ID。


def test_zero_length_component_is_blocked(bridge_document: dict) -> None:  # 检查零长度线构件会阻止求解。
    invalid = deep_copy(bridge_document)  # 创建独立非法文档。
    invalid["components"][1]["nodeRefs"] = ["node.g1.0", "node.g1.0"]  # 把线构件两个端点设为同一节点。
    report = validate_document(invalid)  # 验证非法拓扑。
    assert report["valid"] is False  # 确认零长度构件导致验证失败。
    assert any(issue["ruleId"] == "BSDL-COMP-001" for issue in report["errors"])  # 确认返回线构件拓扑规则 ID。

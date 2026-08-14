"""验证工业 BSDL、混合单元、接触、阶段和预应力 CalculiX 导出。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供示例文档读取。
from pathlib import Path  # 提供临时路径类型。
from bridge_mind.adapters.calculix import export_calculix  # 导入 CalculiX Adapter。
from bridge_mind.calculix.linter import lint_deck  # 导入 deck 静态检查器。
from bridge_mind.validator import validate_document  # 导入完整验证器。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


def _load(path: Path) -> dict:  # 读取 JSON 测试文档。
    return json.loads(path.read_text(encoding="utf-8"))  # 返回文档对象。


def test_industrial_example_is_l4_valid() -> None:  # 检查主工业示例达到完整验证等级。
    document = _load(ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json")  # 读取工业示例。
    report = validate_document(document)  # 执行完整验证。
    assert report["valid"] is True  # 确认文档没有阻断问题。
    assert report["level"] == "L4-valid"  # 确认工业语义完整。
    assert report["stats"]["elementTypes"] == ["C3D8R", "S4R", "T3D2"]  # 确认壳、实体和预应力筋单元存在。
    assert report["stats"]["contacts"] == 1  # 确认接触对象存在。
    assert report["stats"]["constructionStages"] == 4  # 确认四个施工阶段存在。


def test_mixed_model_exports_executable_contract(tmp_path: Path) -> None:  # 检查工业模型实际进入 CalculiX deck。
    document = _load(ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json")  # 读取工业示例。
    deck = tmp_path / "industrial_bridge.inp"  # 构造临时 deck 路径。
    report = export_calculix(document, deck, solver_plan_id="solver.calculix.industrial", finite_element_model_id="fem.bridge_segment", strict=True)  # 执行严格导出。
    text = deck.read_text(encoding="utf-8")  # 读取导出文本。
    assert report["blocked"] is False  # 确认转换未被关键损失阻断。
    assert not any(item.get("sourceRef") == "load.service.anchor" for item in report.get("losses", []))  # 确认节点校核荷载通过显式 FE 节点映射进入 deck。
    assert "*ELEMENT, TYPE=S4R" in text  # 确认壳单元进入 deck。
    assert "*ELEMENT, TYPE=C3D8R" in text  # 确认实体单元进入 deck。
    assert "*ELEMENT, TYPE=T3D2" in text  # 确认预应力筋单元进入 deck。
    assert "*CONTACT PAIR" in text  # 确认非线性接触进入 deck。
    assert "*MODEL CHANGE" in text  # 确认施工阶段生死单元进入 deck。
    assert "*DSLOAD" in text  # 确认表面荷载进入 deck。
    lint = lint_deck(deck)  # 执行确定性静态检查。
    assert lint["valid"] is True  # 确认 deck 静态结构合法。
    assert lint["stats"]["steps"] == 5  # 确认初始化步和四个施工阶段均已生成。


def test_prestress_contract_fixtures_are_real_decks() -> None:  # 检查两种预应力扩展包含实际 CalculiX 关键字。
    initial_deck = ROOT / "runs" / "industrial_demo" / "prestress_initial_stress.inp"  # 指向初始应力夹具。
    native_deck = ROOT / "runs" / "industrial_demo" / "prestress_solver_native.inp"  # 指向原生预紧夹具。
    assert "*INITIAL CONDITIONS, TYPE=STRESS" in initial_deck.read_text(encoding="utf-8")  # 确认积分点初始应力已生成。
    assert "*PRE-TENSION SECTION" in native_deck.read_text(encoding="utf-8")  # 确认原生预紧截面已生成。
    assert lint_deck(initial_deck)["valid"] is True  # 确认初始应力 deck 静态合法。
    assert lint_deck(native_deck)["valid"] is True  # 确认原生预紧 deck 静态合法。

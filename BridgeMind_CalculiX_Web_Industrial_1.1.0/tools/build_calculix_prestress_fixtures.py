"""生成 CalculiX 初始应力与原生预紧截面契约夹具。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供示例文档序列化。
from pathlib import Path  # 提供路径处理。
from bridge_mind.adapters.calculix import export_calculix  # 导入 CalculiX 确定性 Adapter。
from bridge_mind.calculix.linter import lint_deck  # 导入输入文件静态检查器。
from bridge_mind.validator import validate_document  # 导入 BSDL 完整验证器。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。
SOURCE = ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json"  # 指定工业示例基线。
OUTPUT_DIRECTORY = ROOT / "examples" / "fixtures"  # 指定 BSDL 夹具输出目录。
RUN_DIRECTORY = ROOT / "runs" / "industrial_demo"  # 指定 CalculiX deck 输出目录。


def _load() -> dict:  # 读取基线工业示例。
    return json.loads(SOURCE.read_text(encoding="utf-8"))  # 返回独立 JSON 文档。


def _replace_stage_reference(document: dict, old_id: str, new_id: str) -> None:  # 更新施工阶段中的预应力系统引用。
    for stage in document.get("constructionStages", []):  # 遍历全部施工阶段。
        stage["prestressRefs"] = [new_id if value == old_id else value for value in stage.get("prestressRefs", [])]  # 替换旧系统 ID。


def _write_and_export(document: dict, name: str, required_keyword: str) -> dict:  # 保存、验证并导出一个预应力夹具。
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)  # 确保夹具目录存在。
    RUN_DIRECTORY.mkdir(parents=True, exist_ok=True)  # 确保 deck 目录存在。
    document_path = OUTPUT_DIRECTORY / f"{name}.bsdl.json"  # 构造 BSDL 输出路径。
    deck_path = RUN_DIRECTORY / f"{name}.inp"  # 构造 CalculiX 输入路径。
    document_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 保存完整 BSDL 夹具。
    validation = validate_document(document)  # 执行结构、引用、工程和工业验证。
    if not validation["valid"]:  # 检查 BSDL 夹具合法性。
        raise RuntimeError({"message": f"{name} 未通过 BSDL 验证。", "errors": validation["errors"]})  # 阻止生成非法示例。
    report = export_calculix(document, deck_path, solver_plan_id="solver.calculix.industrial", finite_element_model_id="fem.bridge_segment", strict=True)  # 导出 CalculiX deck。
    if report["blocked"]:  # 检查转换是否存在阻断损失。
        raise RuntimeError({"message": f"{name} CalculiX 导出被阻断。", "losses": report["losses"]})  # 阻止交付不可执行 deck。
    text = deck_path.read_text(encoding="utf-8")  # 读取导出 deck。
    if required_keyword not in text:  # 检查关键预应力语义是否实际进入 deck。
        raise RuntimeError(f"{name} 缺少关键字 {required_keyword}。")  # 阻止接口占位冒充实现。
    lint = lint_deck(deck_path)  # 执行 CalculiX 静态检查。
    if not lint["valid"]:  # 检查 deck 静态合法性。
        raise RuntimeError({"message": f"{name} 未通过 CalculiX 静态检查。", "lint": lint})  # 阻止交付静态错误输入。
    return {"document": str(document_path), "deck": str(deck_path), "validationLevel": validation["level"], "lint": lint["stats"], "requiredKeyword": required_keyword}  # 返回夹具生成摘要。


def build() -> list[dict]:  # 生成两种预应力表示夹具。
    initial = _load()  # 读取初始应力夹具基线。
    initial["documentId"] = "document.calculix_prestress_initial_stress"  # 设置独立文档 ID。
    initial["project"]["id"] = "project.calculix_prestress_initial_stress"  # 设置独立项目 ID。
    initial["project"]["name"] = "CalculiX 初始应力预应力契约夹具"  # 设置项目名称。
    old_id = initial["prestressingSystems"][0]["id"]  # 读取原等效荷载系统 ID。
    initial_system = initial["prestressingSystems"][0]  # 读取待修改预应力系统。
    initial_system["id"] = "prestress.tendon.initial"  # 设置初始应力系统 ID。
    initial_system["name"] = "T3D2 钢束初始应力"  # 设置系统名称。
    initial_system["representation"] = "initial_stress"  # 切换为积分点初始应力表示。
    initial_system["initialStress"] = 1200000000.0  # 设置示例初始应力。
    initial_system["jackingForce"] = None  # 清除等效荷载张拉力以测试直接应力路径。
    initial_system["attributes"] = {"fixturePurpose": "adapter_contract", "engineeringUse": "synthetic_only", "integrationPointCount": 1}  # 标记合成契约夹具。
    _replace_stage_reference(initial, old_id, initial_system["id"])  # 更新阶段中的系统引用。
    native = _load()  # 读取原生预紧截面夹具基线。
    native["documentId"] = "document.calculix_prestress_native"  # 设置独立文档 ID。
    native["project"]["id"] = "project.calculix_prestress_native"  # 设置独立项目 ID。
    native["project"]["name"] = "CalculiX 原生预紧截面契约夹具"  # 设置项目名称。
    old_native_id = native["prestressingSystems"][0]["id"]  # 读取原系统 ID。
    native_system = native["prestressingSystems"][0]  # 读取待修改原生系统。
    native_system["id"] = "prestress.tendon.native"  # 设置原生系统 ID。
    native_system["name"] = "CalculiX PRE-TENSION SECTION"  # 设置系统名称。
    native_system["representation"] = "solver_native"  # 切换为 CalculiX 原生预紧表示。
    native_system["initialStress"] = None  # 清除直接初始应力。
    native_system["attributes"] = {"pretensionSurfaceRef": "fem.bearing.surface.xmin", "controlMode": "force", "controlValue": 500000.0, "direction": [1.0, 0.0, 0.0], "referencePoint": [0.0, 0.0, 1.75], "fixturePurpose": "adapter_contract", "engineeringUse": "synthetic_only"}  # 配置可执行原生预紧截面契约。
    _replace_stage_reference(native, old_native_id, native_system["id"])  # 更新阶段中的系统引用。
    return [_write_and_export(initial, "prestress_initial_stress", "*INITIAL CONDITIONS, TYPE=STRESS"), _write_and_export(native, "prestress_solver_native", "*PRE-TENSION SECTION")]  # 生成并返回两个夹具摘要。


if __name__ == "__main__":  # 检查脚本直接执行入口。
    print(json.dumps(build(), ensure_ascii=False, indent=2))  # 输出夹具生成结果。

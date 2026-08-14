"""验证 IFC 4.3 项目 MVD 的 Schema、身份和交付约束检查。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
from pathlib import Path  # 提供配置路径类型。
from bridge_mind.industrial.mvd import load_profile, validate_ifc_model  # 导入项目 MVD 工具。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


class FakeEntity:  # 定义最小 IfcOpenShell 风格实体替身。
    def __init__(self, step_id: int, ifc_type: str, global_id: str = "GID", name: str = "对象") -> None:  # 初始化测试实体。
        self._step_id = step_id  # 保存 STEP 实例号。
        self._ifc_type = ifc_type  # 保存 IFC 类型。
        self.GlobalId = global_id  # 保存全局稳定身份。
        self.Name = name  # 保存用户可读名称。
        self.ObjectPlacement = object()  # 提供非空放置对象。
        self.Representation = object()  # 提供非空几何表示。

    def id(self) -> int:  # 模拟 IfcOpenShell 实例号接口。
        return self._step_id  # 返回 STEP 实例号。

    def is_a(self) -> str:  # 模拟 IfcOpenShell 类型接口。
        return self._ifc_type  # 返回 IFC 类型。


class FakeModel:  # 定义最小 IfcOpenShell 风格模型替身。
    schema_identifier = "IFC4X3_ADD2"  # 声明 IFC 4.3 Schema。

    def __init__(self) -> None:  # 初始化实体索引。
        self.entities = {"IfcProject": [FakeEntity(1, "IfcProject")], "IfcBridge": [FakeEntity(2, "IfcBridge")], "IfcBeam": [FakeEntity(3, "IfcBeam", "BEAM-GID", "主梁")], "IfcMapConversion": [object()]}  # 创建必需实体、物理构件和地理参考。

    def by_type(self, entity_name: str) -> list:  # 模拟按 IFC 类型查询。
        return self.entities.get(entity_name, [])  # 返回匹配实体或空列表。


def test_project_mvd_accepts_complete_ifc43_model() -> None:  # 检查完整 IFC 4.3 模型通过项目交付约束。
    profile = load_profile(ROOT / "mvd" / "bridge_analysis_delivery_view.json")  # 读取项目 MVD 配置。
    report = validate_ifc_model(FakeModel(), profile)  # 执行项目级符合性检查。
    assert report["valid"] is True  # 确认没有 critical 或 error 问题。
    assert report["schema"] == "IFC4X3_ADD2"  # 确认 Schema 版本被记录。
    assert report["physicalProductCount"] == 1  # 确认物理构件被检查。
    assert report["certificationClaim"] is False  # 确认报告没有冒充官方认证。


def test_project_mvd_blocks_wrong_schema() -> None:  # 检查错误 Schema 被明确阻断。
    profile = load_profile(ROOT / "mvd" / "bridge_analysis_delivery_view.json")  # 读取项目 MVD 配置。
    model = FakeModel()  # 创建完整模型。
    model.schema_identifier = "IFC2X3"  # 修改为不允许的旧 Schema。
    report = validate_ifc_model(model, profile)  # 执行项目级符合性检查。
    assert report["valid"] is False  # 确认错误 Schema 阻断交付。
    assert any(item["ruleId"] == "MVD-SCHEMA-001" for item in report["issues"])  # 确认返回稳定规则 ID。

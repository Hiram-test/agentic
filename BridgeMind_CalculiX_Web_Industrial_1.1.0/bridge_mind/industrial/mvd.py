"""验证 IFC 4.3 桥梁分析交付视图并生成可审计符合性报告。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供 MVD 配置读取。
from pathlib import Path  # 提供配置路径处理。
from typing import Any  # 提供通用对象类型注解。
from ..utils import utc_now  # 复用统一时间戳。


def load_profile(path: str | Path) -> dict[str, Any]:  # 读取项目级 IFC MVD 配置。
    profile_path = Path(path).resolve()  # 规范化配置路径。
    payload = json.loads(profile_path.read_text(encoding="utf-8"))  # 解析 JSON 配置。
    if not isinstance(payload, dict) or not payload.get("id"):  # 检查配置基本结构。
        raise ValueError("MVD 配置必须是包含 id 的 JSON object。")  # 阻止非法配置。
    return payload  # 返回 MVD 配置。


def _by_type(model: Any, entity_name: str) -> list[Any]:  # 安全调用 IfcOpenShell by_type 接口。
    try:  # 捕获模型或实体类型不兼容。
        values = model.by_type(entity_name)  # 查询指定 IFC 实体及其子类型。
    except Exception:  # 处理查询失败。
        return []  # 返回空集合并由报告继续处理。
    return list(values or [])  # 返回普通列表。


def validate_ifc_model(model: Any, profile: dict[str, Any]) -> dict[str, Any]:  # 验证已打开的 IFC 模型是否满足项目交付视图。
    schema_identifier = str(getattr(model, "schema_identifier", None) or getattr(model, "schema", ""))  # 读取 IFC Schema 标识。
    issues: list[dict[str, Any]] = []  # 初始化符合性问题列表。
    prefixes = [str(value).upper() for value in profile.get("schemaPrefixes", [])]  # 读取允许的 Schema 前缀。
    if prefixes and not any(schema_identifier.upper().startswith(prefix) for prefix in prefixes):  # 检查 IFC Schema 版本。
        issues.append({"ruleId": "MVD-SCHEMA-001", "severity": profile.get("severity", {}).get("schemaMismatch", "critical"), "path": "/schema", "message": f"IFC Schema {schema_identifier!r} 不满足配置前缀 {prefixes}。", "actual": schema_identifier, "expected": prefixes})  # 记录 Schema 不匹配。
    entity_counts: dict[str, int] = {}  # 初始化实体数量统计。
    for entity_name in profile.get("requiredEntities", []):  # 遍历必需实体类型。
        count = len(_by_type(model, str(entity_name)))  # 统计实体数量。
        entity_counts[str(entity_name)] = count  # 保存实体数量。
        if count == 0:  # 检查必需实体是否缺失。
            issues.append({"ruleId": "MVD-ENTITY-001", "severity": profile.get("severity", {}).get("missingRequiredEntity", "critical"), "path": f"/entities/{entity_name}", "message": f"缺少必需 IFC 实体 {entity_name}。", "actual": 0, "expected": ">= 1"})  # 记录必需实体缺失。
    for entity_name in profile.get("recommendedEntities", []):  # 遍历推荐实体类型。
        entity_counts[str(entity_name)] = len(_by_type(model, str(entity_name)))  # 保存推荐实体数量。
    physical_types = [str(value) for value in profile.get("acceptedPhysicalElements", [])]  # 读取可接受物理构件类型。
    physical_products: list[Any] = []  # 初始化物理构件集合。
    seen_step_ids: set[int] = set()  # 初始化已收集 IFC 实例 ID 集合。
    for entity_name in physical_types:  # 遍历物理构件类型。
        for entity in _by_type(model, entity_name):  # 遍历当前类型实例。
            step_id = int(entity.id()) if hasattr(entity, "id") else id(entity)  # 读取 STEP 实例号或 Python 标识。
            if step_id in seen_step_ids:  # 检查继承查询导致的重复实例。
                continue  # 跳过重复实例。
            seen_step_ids.add(step_id)  # 记录已收集实例。
            physical_products.append(entity)  # 保存物理构件实例。
    product_summary: list[dict[str, Any]] = []  # 初始化产品符合性摘要。
    for entity in physical_products:  # 遍历所有可接受物理构件。
        ifc_type = str(entity.is_a()) if hasattr(entity, "is_a") else type(entity).__name__  # 读取 IFC 实体类型。
        global_id = getattr(entity, "GlobalId", None)  # 读取 IFC GlobalId。
        name = getattr(entity, "Name", None)  # 读取 IFC Name。
        placement = getattr(entity, "ObjectPlacement", None)  # 读取产品放置。
        representation = getattr(entity, "Representation", None)  # 读取产品几何表示。
        step_id = int(entity.id()) if hasattr(entity, "id") else None  # 读取 STEP 实例号。
        if not global_id:  # 检查稳定身份。
            issues.append({"ruleId": "MVD-IDENTITY-001", "severity": profile.get("severity", {}).get("missingGlobalId", "critical"), "path": f"/entities/{step_id}/GlobalId", "message": f"{ifc_type} 缺少 GlobalId。", "actual": global_id, "expected": "IfcGloballyUniqueId"})  # 记录 GlobalId 缺失。
        if not name:  # 检查用户可读名称。
            issues.append({"ruleId": "MVD-IDENTITY-002", "severity": profile.get("severity", {}).get("missingName", "warning"), "path": f"/entities/{step_id}/Name", "message": f"{ifc_type} 缺少 Name。", "actual": name, "expected": "非空 IfcLabel"})  # 记录名称缺失。
        if placement is None:  # 检查产品放置。
            issues.append({"ruleId": "MVD-PLACEMENT-001", "severity": profile.get("severity", {}).get("missingPlacement", "error"), "path": f"/entities/{step_id}/ObjectPlacement", "message": f"{ifc_type} 缺少 ObjectPlacement。", "actual": None, "expected": "IfcObjectPlacement"})  # 记录放置缺失。
        if representation is None:  # 检查几何表示。
            issues.append({"ruleId": "MVD-GEOMETRY-001", "severity": profile.get("severity", {}).get("missingRepresentation", "warning"), "path": f"/entities/{step_id}/Representation", "message": f"{ifc_type} 缺少几何 Representation。", "actual": None, "expected": "IfcProductRepresentation"})  # 记录几何表示缺失。
        product_summary.append({"stepId": step_id, "ifcType": ifc_type, "globalId": global_id, "name": name, "hasPlacement": placement is not None, "hasRepresentation": representation is not None})  # 保存产品摘要。
    georeferencing_count = len(_by_type(model, "IfcMapConversion")) + len(_by_type(model, "IfcProjectedCRS"))  # 统计地理参考实体。
    if georeferencing_count == 0:  # 检查是否存在地理参考。
        issues.append({"ruleId": "MVD-GEOREF-001", "severity": profile.get("severity", {}).get("missingGeoreferencing", "warning"), "path": "/georeferencing", "message": "IFC 文件没有 IfcMapConversion 或 IfcProjectedCRS；跨模型坐标联邦需要人工确认。", "actual": 0, "expected": ">= 1"})  # 记录地理参考缺失。
    severity_rank = {"info": 0, "warning": 1, "error": 2, "critical": 3}  # 定义严重度等级。
    issues.sort(key=lambda item: (-severity_rank.get(str(item.get("severity")), 0), str(item.get("path"))))  # 稳定排序问题。
    blockers = [item for item in issues if item.get("severity") in {"critical", "error"}]  # 提取阻断问题。
    return {"profileId": profile.get("id"), "profileVersion": profile.get("version"), "schema": schema_identifier, "valid": not blockers, "certificationClaim": False, "checkedAt": utc_now(), "entityCounts": entity_counts, "physicalProductCount": len(physical_products), "products": product_summary, "issues": issues, "summary": {"critical": sum(1 for item in issues if item.get("severity") == "critical"), "error": sum(1 for item in issues if item.get("severity") == "error"), "warning": sum(1 for item in issues if item.get("severity") == "warning"), "info": sum(1 for item in issues if item.get("severity") == "info")}, "note": "本报告是项目级交付视图检查，不等同于 buildingSMART 官方软件认证。"}  # 返回完整 MVD 报告。

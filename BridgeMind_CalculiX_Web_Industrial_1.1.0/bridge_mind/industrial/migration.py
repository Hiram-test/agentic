"""把 BSDL 0.1 文档确定性升级到 CalculiX 主线工业扩展 1.0。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from ..utils import deep_copy  # 复用安全深复制。
from ..version import ADAPTER_VERSION, CALCULIX_TARGET_VERSION, LANGUAGE_VERSION  # 复用统一版本常量。

INDUSTRIAL_VERSION = LANGUAGE_VERSION  # 保留旧 Adapter 使用的工业语言版本别名。
INDUSTRIAL_ARRAY_FIELDS = ["shellSections", "solidSections", "finiteElementModels", "contacts", "prestressingSystems", "constructionStages", "codeCheckPlans", "codeCheckResults", "solverProfiles", "resultSets", "externalMappings", "conversionReports"]  # 定义工业扩展顶层数组。


def _calculix_profile() -> dict[str, Any]:  # 构造唯一受支持的工业求解器能力档案。
    return {"id": "solver.profile.calculix.2_23", "solver": "calculix", "version": CALCULIX_TARGET_VERSION, "adapter": "bridge_mind.adapters.calculix", "adapterVersion": ADAPTER_VERSION, "capabilities": {"elementTypes": ["T3D2", "B31", "B32", "S3", "S4", "S4R", "C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D20", "C3D20R", "MASS", "SPRINGA"], "analyses": ["linear_static", "nonlinear_static", "modal", "buckling"], "contacts": ["contact", "tie", "frictionless", "penalty_friction", "rough"], "prestress": ["equivalent_load", "truss_tendon", "initial_stress", "solver_native"], "constructionStages": True, "resultImport": ["displacement", "reaction", "stress", "strain", "contact", "energy"]}, "executable": "ccx", "licenseRequired": False, "executionMode": "local", "settings": {"environmentVariable": "CCX_EXECUTABLE", "inputFormat": "CalculiX keyword input", "resultFormats": ["FRD", "DAT"]}, "status": "unverified"}  # 返回 CalculiX 2.23 能力档案。


def default_solver_profiles() -> list[dict[str, Any]]:  # 返回对外可复用的默认求解器档案。
    return [_calculix_profile()]  # 仅返回本项目实际维护的 CalculiX 主线。


def _normalise_solver_plan(plan: dict[str, Any]) -> None:  # 把旧求解计划迁移到 CalculiX 主线。
    previous_solver = str(plan.get("solver", "calculix"))  # 读取迁移前求解器名称。
    plan["solver"] = "calculix"  # 固定工业执行求解器为 CalculiX。
    plan["solverProfileRef"] = "solver.profile.calculix.2_23"  # 绑定经过版本治理的能力档案。
    plan.setdefault("finiteElementModelRef", None)  # 补充 FE 模型引用。
    plan.setdefault("stageRefs", [])  # 补充施工阶段引用。
    settings = plan.setdefault("settings", {})  # 获取或创建求解设置。
    settings.setdefault("analysis", "linear_static")  # 补充默认分析类型。
    settings.setdefault("nlgeom", False)  # 补充默认几何非线性开关。
    settings.setdefault("strictConversion", True)  # 默认禁止关键语义静默丢失。
    settings.setdefault("output", {"nodeFile": ["U", "RF"], "elementFile": ["S", "E"], "contactFile": ["CSTRESS", "CDIS"]})  # 补充可回读结果请求。
    if previous_solver not in {"", "calculix", "builtin_frame3d"}:  # 检查是否从其他外部求解器迁移。
        notes = settings.setdefault("migrationNotes", [])  # 获取迁移说明列表。
        notes.append(f"原求解器 {previous_solver} 已迁移为 CalculiX；必须审查转换报告和能力差异。")  # 保存可审计迁移说明。
    if previous_solver == "builtin_frame3d":  # 检查是否从内置快速试算迁移。
        settings.setdefault("previewSolver", "builtin_frame3d")  # 保留内置梁系求解器作为快速预览信息。


def upgrade_document(document: dict[str, Any], include_solver_profiles: bool = True, calculix_only: bool = True) -> dict[str, Any]:  # 升级文档并保持原对象 ID 与业务内容。
    upgraded = deep_copy(document)  # 深复制输入避免原地修改。
    upgraded["language"] = "Bridge-Structural-Description-Language"  # 规范化语言名称。
    upgraded["languageVersion"] = INDUSTRIAL_VERSION  # 设置工业扩展版本。
    upgraded["$schema"] = "../schema/bsdl-industrial.schema.json"  # 指向工业扩展 Schema。
    for field in INDUSTRIAL_ARRAY_FIELDS:  # 遍历所有工业扩展数组。
        upgraded.setdefault(field, [])  # 为旧文档补充空数组。
    for material in upgraded.get("materials", []):  # 遍历材料对象。
        if isinstance(material, dict):  # 检查材料结构。
            material.setdefault("plasticity", None)  # 补充塑性参数槽位。
            material.setdefault("creep", None)  # 补充徐变参数槽位。
            material.setdefault("relaxation", None)  # 补充松弛参数槽位。
    for component in upgraded.get("components", []):  # 遍历结构构件。
        if isinstance(component, dict):  # 检查构件结构。
            analysis = component.setdefault("analysis", {})  # 获取或创建分析属性。
            analysis.setdefault("finiteElementModelRef", None)  # 补充 FE 模型引用。
            analysis.setdefault("shellSectionRef", None)  # 补充壳截面引用。
            analysis.setdefault("solidSectionRef", None)  # 补充实体截面引用。
    for plan in upgraded.get("solverPlans", []):  # 遍历求解计划。
        if isinstance(plan, dict):  # 检查计划结构。
            _normalise_solver_plan(plan)  # 迁移为 CalculiX 求解计划。
    if include_solver_profiles:  # 检查是否需要注入能力档案。
        if calculix_only:  # 检查是否要求仅保留 CalculiX。
            upgraded["solverProfiles"] = default_solver_profiles()  # 替换为唯一受维护档案。
        elif not upgraded.get("solverProfiles"):  # 兼容调用方保留既有档案的需求。
            upgraded["solverProfiles"] = default_solver_profiles()  # 在空档案时注入 CalculiX。
    upgraded.setdefault("extensions", {})  # 确保扩展容器存在。
    industrial_meta = upgraded["extensions"].setdefault("bridgemind:industrial", {})  # 获取工业扩展元数据。
    industrial_meta["solverMainline"] = "calculix"  # 声明工业求解主线。
    industrial_meta["calculixTargetVersion"] = CALCULIX_TARGET_VERSION  # 声明目标求解器版本。
    industrial_meta["adapterVersion"] = ADAPTER_VERSION  # 声明 Adapter 版本。
    industrial_meta["capabilityPolicy"] = "unsupported safety-critical semantics block export or execution"  # 声明显式阻断策略。
    return upgraded  # 返回升级后的工业文档。

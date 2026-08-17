"""把 BSDL Industrial 1.0 确定性转换为 CalculiX 2.23 输入并管理本地运行。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import hashlib  # 提供真实 SHA-256 内容哈希。
import json  # 提供运行清单序列化。
import math  # 提供向量范数和截面推导。
import os  # 提供环境变量读取。
import re  # 提供 CalculiX 安全名称处理。
import shutil  # 提供可执行文件探测和文件复制。
import subprocess  # 提供外部 ccx 进程执行。
from pathlib import Path  # 提供路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from ..fea.mesher import mesh_document  # 复用核心梁系网格器作为兼容输入。
from ..calculix.linter import lint_deck  # 导入 CalculiX 输入文件静态检查器。
from ..industrial.migration import INDUSTRIAL_VERSION  # 复用语言版本常量。
from ..version import ADAPTER_VERSION  # 复用统一 Adapter 版本常量。
from ..industrial.prestress import analyze_prestress, equivalent_nodal_loads  # 复用预应力损失与等效荷载计算。
from ..industrial.stages import compile_stage_plan  # 复用施工阶段编译器。
from ..utils import content_hash, deep_copy, utc_now  # 复用哈希、复制和时间工具。
from .calculix_results import build_result_set, parse_dat  # 复用 DAT 结果解析与 ResultSet 封装。

CALCULIX_VERSION = "2.23"  # 固定当前 Adapter 目标求解器版本。
SUPPORTED_ELEMENT_TYPES = {"T3D2", "B31", "B32", "S3", "S4", "S4R", "C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D20", "C3D20R", "MASS", "SPRINGA"}  # 声明当前可导出的单元类型。
BEAM_TYPES = {"B31", "B32"}  # 声明梁单元类型。
TRUSS_TYPES = {"T3D2"}  # 声明桁架单元类型。
SHELL_TYPES = {"S3", "S4", "S4R"}  # 声明壳单元类型。
SOLID_TYPES = {"C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D20", "C3D20R"}  # 声明实体单元类型。
SPECIAL_TYPES = {"MASS", "SPRINGA"}  # 声明特殊单元类型。
DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]  # 定义 CalculiX 结构自由度顺序。
ARTIFACT_SUFFIXES = [".inp", ".dat", ".frd", ".sta", ".cvg", ".12d", ".eig", ".out", ".log", ".idmap.json", ".conversion.json"]  # 定义运行产物扩展名。
INTEGRATION_POINT_COUNTS = {"T3D2": 1, "C3D4": 1, "C3D6": 2, "C3D8": 8, "C3D8R": 1, "C3D10": 4, "C3D20": 27, "C3D20R": 8}  # 定义受支持初始应力单元的默认积分点数量。
CONTACT_TYPES = {"NODE TO SURFACE", "SURFACE TO SURFACE", "MORTAR", "MASSLESS"}  # 定义 CalculiX 允许的接触算法类型。


def _loss(category: str, source_ref: str | None, target_ref: str | None, path: str, message: str, severity: str = "warning", action: str = "人工核验") -> dict[str, Any]:  # 构造工业 Schema 兼容的转换损失对象。
    return {"category": category, "sourceRef": source_ref, "targetRef": target_ref, "path": path, "message": message, "severity": severity, "action": action}  # 返回统一损失结构。


def _chunks(values: list[Any], size: int = 16) -> list[list[Any]]:  # 把长列表拆成 CalculiX 可读短行。
    return [values[index : index + size] for index in range(0, len(values), size)]  # 返回固定长度分块。


def _safe_label(value: str, prefix: str = "X", limit: int = 72) -> str:  # 把任意 BSDL ID 转换为短且稳定的 CalculiX 标签。
    text = re.sub(r"[^A-Za-z0-9_]", "_", str(value)).upper()  # 替换输入文件不安全字符。
    text = re.sub(r"_+", "_", text).strip("_")  # 压缩连续下划线并去除边界下划线。
    if not text or not text[0].isalpha():  # 检查标签首字符。
        text = f"{prefix}_{text}" if text else prefix  # 确保标签以字母开头。
    digest = content_hash(str(value))[:8].upper()  # 生成碰撞规避短哈希。
    if len(text) > limit - 9:  # 检查标签是否过长。
        text = f"{text[: limit - 9]}_{digest}"  # 截断并附加哈希。
    return text  # 返回安全标签。


def _norm(vector: list[float]) -> float:  # 计算三维向量欧氏范数。
    return math.sqrt(sum(float(value) * float(value) for value in vector))  # 返回范数。


def _unit(vector: list[float], fallback: list[float] | None = None) -> list[float]:  # 归一化向量并提供可审计后备方向。
    length = _norm(vector)  # 计算输入长度。
    if length <= 1e-14:  # 检查退化向量。
        return list(fallback or [0.0, 0.0, -1.0])  # 返回调用方指定的后备方向。
    return [float(value) / length for value in vector]  # 返回单位向量。


def _beam_dimensions(section: dict[str, Any]) -> tuple[str, list[float], list[float], bool]:  # 把 BSDL 梁截面转换为 CalculiX 标准截面参数。
    shape = str(section.get("shape", "generic"))  # 读取截面形状。
    dimensions = section.get("dimensions", {}) if isinstance(section.get("dimensions"), dict) else {}  # 读取几何尺寸。
    area = max(float(section.get("area", 1.0) or 1.0), 1e-12)  # 读取截面面积。
    default_side = math.sqrt(area)  # 根据面积推导等效正方形边长。
    direction = [float(value) for value in dimensions.get("localDirection1", [0.0, 0.0, 1.0])]  # 读取截面局部第一方向。
    if shape == "rectangular":  # 处理矩形截面。
        width = float(dimensions.get("width", default_side))  # 读取矩形宽度。
        depth = float(dimensions.get("depth", default_side))  # 读取矩形高度。
        return "RECT", [width, depth], direction, False  # 返回无降级矩形映射。
    if shape in {"circular", "circle"}:  # 处理圆形截面。
        diameter = float(dimensions.get("diameter", math.sqrt(4.0 * area / math.pi)))  # 根据面积推导直径。
        return "CIRC", [diameter, diameter], direction, False  # 返回椭圆关键字的圆形特例。
    if shape == "box":  # 处理薄壁箱形截面。
        width = float(dimensions.get("width", default_side))  # 读取外宽。
        depth = float(dimensions.get("depth", default_side))  # 读取外高。
        wall = float(dimensions.get("wallThickness", dimensions.get("thickness", min(width, depth) * 0.05)))  # 读取统一壁厚。
        return "BOX", [width, depth, wall, wall, wall, wall], direction, False  # 返回 CalculiX BOX 参数。
    width = float(dimensions.get("width", default_side))  # 为通用截面读取或推导等效宽度。
    depth = float(dimensions.get("depth", default_side))  # 为通用截面读取或推导等效高度。
    return "RECT", [width, depth], direction, True  # 返回显式降级的矩形等效截面。


def _copy_constraints(value: Any) -> dict[str, bool]:  # 规范化六自由度约束字典。
    source = value if isinstance(value, dict) else {}  # 读取有效约束对象。
    return {name: bool(source.get(name, False)) for name in DOF_NAMES}  # 返回完整六自由度约束。


def _beam_model_from_core(document: dict[str, Any], mesh_policy_id: str | None = None) -> dict[str, Any]:  # 把核心 BSDL 梁网格转换为工业 FE 模型。
    mesh = mesh_document(document, mesh_policy_id)  # 生成核心梁系网格。
    task_ref = str(document.get("analysisTasks", [{}])[0].get("id", "task.default"))  # 选择首个分析任务。
    coordinate_system_ref = str(document.get("coordinateSystems", [{}])[0].get("id", "cs.global"))  # 选择全局坐标系。
    nodes: list[dict[str, Any]] = []  # 初始化工业 FE 节点。
    for node in mesh.get("nodes", []):  # 遍历核心网格节点。
        nodes.append({"id": str(node["id"]), "position": [float(value) for value in node["position"]], "coordinateSystemRef": coordinate_system_ref, "constraints": _copy_constraints(node.get("constraints")), "sourceRef": node.get("originalNodeRef"), "attributes": {"roles": list(node.get("roles", [])), "generatedFromCoreMesh": True}})  # 转换为工业 FE 节点。
    elements: list[dict[str, Any]] = []  # 初始化工业 FE 单元。
    for element in mesh.get("elements", []):  # 遍历核心梁单元。
        elements.append({"id": str(element["id"]), "type": "B31", "nodeRefs": [str(value) for value in element["nodeRefs"]], "sectionRef": element.get("sectionRef"), "materialRef": element.get("materialRef"), "sourceRef": element.get("componentRef"), "orientationRef": None, "setRefs": ["fem.compatible_beam.set.all"], "active": True, "attributes": {"localUp": element.get("localUp", [0.0, 0.0, 1.0]), "generatedFromCoreMesh": True}})  # 转换为 B31 单元。
    element_refs = [str(element["id"]) for element in elements]  # 收集全部单元 ID。
    model = {"id": "fem.compatible_beam", "name": "核心 BSDL 兼容梁系 FE 模型", "taskRef": task_ref, "coordinateSystemRef": coordinate_system_ref, "nodes": nodes, "elements": elements, "sets": [{"id": "fem.compatible_beam.set.all", "name": "全部梁单元", "kind": "element", "refs": element_refs, "faces": [], "sourceRefs": [], "attributes": {}}], "source": "generated", "meshHash": content_hash({"nodes": nodes, "elements": elements}), "status": "validated", "statistics": mesh.get("stats", {}), "artifactRefs": []}  # 组装工业 FE 模型。
    return model  # 返回兼容 FE 模型。


def _select_solver_plan(document: dict[str, Any], solver_plan_id: str | None = None) -> dict[str, Any]:  # 选择 CalculiX 求解计划。
    plans = [item for item in document.get("solverPlans", []) if isinstance(item, dict)]  # 收集有效求解计划。
    if solver_plan_id is not None:  # 处理显式计划 ID。
        matches = [item for item in plans if item.get("id") == solver_plan_id]  # 查找匹配计划。
        if not matches:  # 检查计划存在性。
            raise ValueError(f"SolverPlan 不存在：{solver_plan_id}")  # 抛出明确错误。
        plan = deep_copy(matches[0])  # 深复制匹配计划。
    else:  # 处理未指定计划。
        calculix_plans = [item for item in plans if item.get("solver") == "calculix"]  # 优先查找 CalculiX 计划。
        plan = deep_copy(calculix_plans[0] if calculix_plans else {})  # 没有 CalculiX 计划时创建隐式计划，避免误用内置预览求解器。
    if not plan:  # 检查文档是否完全没有计划。
        task_ref = str(document.get("analysisTasks", [{}])[0].get("id", "task.default"))  # 读取默认任务。
        plan = {"id": "solver.implicit.calculix", "name": "隐式 CalculiX 求解计划", "taskRef": task_ref, "meshPolicyRef": None, "solver": "calculix", "settings": {"analysis": "linear_static", "nlgeom": False}, "status": "draft", "solverProfileRef": "solver.profile.calculix.2_23", "finiteElementModelRef": None, "stageRefs": []}  # 构造隐式计划。
    if plan.get("solver") not in {None, "calculix"}:  # 检查求解器类型。
        raise ValueError(f"当前工业 Adapter 只执行 CalculiX，计划 {plan.get('id')} 指定了 {plan.get('solver')}。")  # 阻止错误求解器路由。
    plan["solver"] = "calculix"  # 规范化求解器字段。
    plan.setdefault("settings", {})  # 确保设置对象存在。
    plan.setdefault("stageRefs", [])  # 确保阶段引用存在。
    return plan  # 返回选定计划。


def _select_model(document: dict[str, Any], plan: dict[str, Any], finite_element_model_id: str | None, mesh_policy_id: str | None) -> tuple[dict[str, Any], bool]:  # 选择显式工业 FE 模型或生成梁系兼容模型。
    models = [item for item in document.get("finiteElementModels", []) if isinstance(item, dict)]  # 收集显式 FE 模型。
    requested = finite_element_model_id or plan.get("finiteElementModelRef")  # 解析目标模型 ID。
    if requested is not None:  # 处理显式模型引用。
        matches = [item for item in models if item.get("id") == requested]  # 查找匹配模型。
        if not matches:  # 检查引用存在性。
            raise ValueError(f"FiniteElementModel 不存在：{requested}")  # 抛出明确错误。
        return deep_copy(matches[0]), False  # 返回显式模型并标记非兼容生成。
    if models:  # 处理存在模型但计划未指定的情况。
        return deep_copy(models[0]), False  # 返回首个显式模型。
    return _beam_model_from_core(document, mesh_policy_id or plan.get("meshPolicyRef")), True  # 生成核心梁系兼容模型。


def _collect_model_sets(model: dict[str, Any]) -> dict[str, dict[str, Any]]:  # 建立 FE 集合索引。
    return {str(item.get("id")): item for item in model.get("sets", []) if isinstance(item, dict) and item.get("id")}  # 返回集合 ID 到对象的映射。


def _resolve_stage_element_ids(reference: str, model: dict[str, Any], set_index: dict[str, dict[str, Any]]) -> list[str]:  # 把构件、单元或集合引用解析为 FE 单元 ID。
    element_ids = {str(item.get("id")) for item in model.get("elements", []) if isinstance(item, dict)}  # 收集单元 ID。
    if reference in element_ids:  # 检查直接单元引用。
        return [reference]  # 返回单个单元。
    if reference in set_index and set_index[reference].get("kind") == "element":  # 检查单元集合引用。
        return [str(item) for item in set_index[reference].get("refs", [])]  # 返回集合中的单元。
    return [str(item.get("id")) for item in model.get("elements", []) if isinstance(item, dict) and item.get("sourceRef") == reference]  # 按源构件引用查找单元。


def _material_for_element(element: dict[str, Any], shell_sections: dict[str, dict[str, Any]], solid_sections: dict[str, dict[str, Any]]) -> str | None:  # 解析单元最终材料引用。
    material_ref = element.get("materialRef")  # 优先读取单元材料引用。
    if material_ref:  # 检查单元是否直接给出材料。
        return str(material_ref)  # 返回直接材料引用。
    section_ref = str(element.get("sectionRef")) if element.get("sectionRef") is not None else None  # 读取截面引用。
    if section_ref in shell_sections:  # 检查壳截面。
        return str(shell_sections[section_ref].get("materialRef"))  # 返回壳截面材料。
    if section_ref in solid_sections:  # 检查实体截面。
        return str(solid_sections[section_ref].get("materialRef"))  # 返回实体截面材料。
    return None  # 无法解析材料时返回空。


def _build_numbering(model: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:  # 为 FE 节点和单元建立稳定连续整数编号。
    node_numbers = {str(node["id"]): index for index, node in enumerate(model.get("nodes", []), start=1) if isinstance(node, dict) and node.get("id")}  # 按文档顺序编号节点。
    element_numbers = {str(element["id"]): index for index, element in enumerate(model.get("elements", []), start=1) if isinstance(element, dict) and element.get("id")}  # 按文档顺序编号单元。
    return node_numbers, element_numbers  # 返回编号映射。


def _write_numeric_set(lines: list[str], keyword: str, label: str, numbers: list[int]) -> None:  # 写入节点集或单元集。
    lines.append(f"*{keyword}, {keyword}={label}")  # 写入集合关键字。
    for chunk in _chunks(numbers):  # 按短行遍历编号。
        lines.append(", ".join(str(value) for value in chunk))  # 写入当前编号分块。


def _append_materials(lines: list[str], materials: dict[str, dict[str, Any]], label_map: dict[str, str], losses: list[dict[str, Any]]) -> None:  # 写入材料定义。
    for material_id, material in materials.items():  # 遍历材料对象。
        label = label_map[material_id]  # 获取材料安全名称。
        lines.append(f"*MATERIAL, NAME={label}")  # 开始材料块。
        lines.append("*ELASTIC")  # 写入弹性参数关键字。
        lines.append(f"{float(material.get('elasticModulus', 0.0)):.12g}, {float(material.get('poissonRatio', 0.3)):.12g}")  # 写入弹性模量与泊松比。
        density = float(material.get("density", 0.0) or 0.0)  # 读取材料密度。
        if density > 0.0:  # 检查密度是否有效。
            lines.append("*DENSITY")  # 写入密度关键字。
            lines.append(f"{density:.12g}")  # 写入密度值。
        model = str(material.get("model", "linear_elastic"))  # 读取材料模型。
        plasticity = material.get("plasticity")  # 读取塑性数据。
        if model in {"bilinear_plastic", "multilinear_plastic"} and isinstance(plasticity, dict):  # 处理表格塑性材料。
            points = plasticity.get("points", [])  # 读取应力塑性应变点。
            if points:  # 检查塑性点是否存在。
                lines.append("*PLASTIC")  # 写入塑性关键字。
                for point in points:  # 遍历塑性点。
                    if isinstance(point, dict):  # 检查点结构。
                        lines.append(f"{float(point.get('stress', 0.0)):.12g}, {float(point.get('plasticStrain', 0.0)):.12g}")  # 写入屈服应力与塑性应变。
            else:  # 处理缺少点表的塑性材料。
                losses.append(_loss("degraded", material_id, label, "/materials", "材料声明为塑性但未提供 plasticity.points，已按线弹性导出。", "warning", "补充应力—塑性应变曲线后重新导出。"))  # 记录材料降级。
        elif model not in {"linear_elastic", "bilinear_plastic", "multilinear_plastic"}:  # 检查未实现材料模型。
            losses.append(_loss("degraded", material_id, label, "/materials", f"材料模型 {model} 当前降级为线弹性。", "warning", "扩展 CalculiX 材料卡或使用用户材料子程序。"))  # 记录材料降级。


def _append_sections(lines: list[str], model: dict[str, Any], document: dict[str, Any], element_numbers: dict[str, int], material_labels: dict[str, str], losses: list[dict[str, Any]]) -> dict[str, str]:  # 写入单元分组及梁壳实体截面。
    beam_sections = {str(item.get("id")): item for item in document.get("sections", []) if isinstance(item, dict) and item.get("id")}  # 建立梁截面索引。
    shell_sections = {str(item.get("id")): item for item in document.get("shellSections", []) if isinstance(item, dict) and item.get("id")}  # 建立壳截面索引。
    solid_sections = {str(item.get("id")): item for item in document.get("solidSections", []) if isinstance(item, dict) and item.get("id")}  # 建立实体截面索引。
    grouped: dict[tuple[str, str | None, str | None], list[str]] = {}  # 初始化单元类型、截面和材料组合分组。
    for element in model.get("elements", []):  # 遍历 FE 单元。
        if not isinstance(element, dict):  # 跳过非法项。
            continue  # 继续下一单元。
        element_type = str(element.get("type"))  # 读取单元类型。
        section_ref = str(element.get("sectionRef")) if element.get("sectionRef") is not None else None  # 读取截面引用。
        material_ref = _material_for_element(element, shell_sections, solid_sections)  # 解析材料引用。
        grouped.setdefault((element_type, section_ref, material_ref), []).append(str(element.get("id")))  # 加入组合分组。
    element_set_labels: dict[str, str] = {}  # 初始化单元 ID 到分组标签映射。
    for group_index, ((element_type, section_ref, material_ref), element_ids) in enumerate(grouped.items(), start=1):  # 遍历分组。
        label = _safe_label(f"SEC_{group_index}_{element_type}_{section_ref or 'NONE'}", "E")  # 构造分组标签。
        numbers = [element_numbers[element_id] for element_id in element_ids]  # 转换为 CalculiX 单元号。
        _write_numeric_set(lines, "ELSET", label, numbers)  # 写入分组单元集。
        for element_id in element_ids:  # 遍历分组单元。
            element_set_labels[element_id] = label  # 保存单元到分组映射。
        if element_type in BEAM_TYPES:  # 处理梁截面。
            section = beam_sections.get(str(section_ref), {})  # 查找梁截面。
            if not section or material_ref not in material_labels:  # 检查梁截面与材料。
                losses.append(_loss("blocked", section_ref, label, "/finiteElementModels/elements", "梁单元缺少有效梁截面或材料。", "critical", "补充 sectionRef 与 materialRef。"))  # 记录阻断问题。
                continue  # 跳过无法定义的梁截面。
            section_type, values, direction, degraded = _beam_dimensions(section)  # 转换梁截面参数。
            lines.append(f"*BEAM SECTION, ELSET={label}, MATERIAL={material_labels[material_ref]}, SECTION={section_type}")  # 写入梁截面关键字。
            lines.append(", ".join(f"{value:.12g}" for value in values))  # 写入截面尺寸。
            lines.append(", ".join(f"{value:.12g}" for value in _unit(direction, [0.0, 0.0, 1.0])))  # 写入局部第一方向。
            if degraded:  # 检查是否发生等效转换。
                losses.append(_loss("degraded", section_ref, label, "/sections", "通用或 I 形梁截面被等效为矩形，面积与惯性矩不能同时完全保持。", "warning", "提供适配的 RECT/CIRC/PIPE/BOX 参数或使用经验证的用户单元。"))  # 记录截面降级。
        elif element_type in TRUSS_TYPES:  # 处理桁架截面。
            section = beam_sections.get(str(section_ref), {})  # 查找面积来源截面。
            if not section or material_ref not in material_labels:  # 检查桁架截面与材料。
                losses.append(_loss("blocked", section_ref, label, "/finiteElementModels/elements", "桁架单元缺少有效截面或材料。", "critical", "补充截面面积和材料。"))  # 记录阻断问题。
                continue  # 跳过非法桁架截面。
            lines.append(f"*SOLID SECTION, ELSET={label}, MATERIAL={material_labels[material_ref]}")  # 使用 SOLID SECTION 定义桁架面积。
            lines.append(f"{float(section.get('area', 0.0)):.12g}")  # 写入桁架截面积。
        elif element_type in SHELL_TYPES:  # 处理壳截面。
            section = shell_sections.get(str(section_ref), {})  # 查找壳截面。
            if not section or material_ref not in material_labels:  # 检查壳截面与材料。
                losses.append(_loss("blocked", section_ref, label, "/shellSections", "壳单元缺少有效 shellSection 或材料。", "critical", "补充 shellSection.materialRef 和厚度。"))  # 记录阻断问题。
                continue  # 跳过非法壳截面。
            offset = float(section.get("offset", 0.0))  # 读取归一化截面偏置。
            lines.append(f"*SHELL SECTION, ELSET={label}, MATERIAL={material_labels[material_ref]}, OFFSET={offset:.12g}")  # 写入壳截面关键字。
            lines.append(f"{float(section.get('thickness', 0.0)):.12g}")  # 写入壳厚度。
            if section.get("formulation") == "composite" and section.get("layers"):  # 检查复合壳层。
                losses.append(_loss("degraded", section_ref, label, "/shellSections", "复合壳层当前按等效单层厚度导出。", "warning", "实现逐层材料和方向映射后再用于正式计算。"))  # 记录复合壳降级。
        elif element_type in SOLID_TYPES:  # 处理三维实体截面。
            section = solid_sections.get(str(section_ref), {})  # 查找实体截面。
            if not section or material_ref not in material_labels:  # 检查实体截面与材料。
                losses.append(_loss("blocked", section_ref, label, "/solidSections", "实体单元缺少有效 solidSection 或材料。", "critical", "补充 solidSection.materialRef。"))  # 记录阻断问题。
                continue  # 跳过非法实体截面。
            lines.append(f"*SOLID SECTION, ELSET={label}, MATERIAL={material_labels[material_ref]}")  # 写入三维实体截面。
        elif element_type == "MASS":  # 处理集中质量单元。
            mass_value = next((float(item.get("attributes", {}).get("mass", 0.0)) for item in model.get("elements", []) if isinstance(item, dict) and item.get("id") in element_ids), 0.0)  # 读取分组首个质量值。
            lines.append(f"*MASS, ELSET={label}")  # 写入集中质量关键字。
            lines.append(f"{mass_value:.12g}")  # 写入质量值。
        elif element_type == "SPRINGA":  # 处理轴向弹簧单元。
            stiffness = next((float(item.get("attributes", {}).get("stiffness", 0.0)) for item in model.get("elements", []) if isinstance(item, dict) and item.get("id") in element_ids), 0.0)  # 读取分组首个刚度值。
            lines.append(f"*SPRING, ELSET={label}")  # 写入弹簧关键字。
            lines.append(f"{stiffness:.12g}")  # 写入弹簧刚度。
    return element_set_labels  # 返回单元分组映射。


def _append_sets_and_surfaces(lines: list[str], model: dict[str, Any], node_numbers: dict[str, int], element_numbers: dict[str, int], losses: list[dict[str, Any]]) -> dict[str, str]:  # 写入显式 FE 集合和接触表面。
    labels: dict[str, str] = {}  # 初始化 BSDL 集合 ID 到 CalculiX 标签映射。
    for item_set in model.get("sets", []):  # 遍历 FE 集合。
        if not isinstance(item_set, dict) or not item_set.get("id"):  # 跳过非法集合。
            continue  # 继续下一集合。
        set_id = str(item_set["id"])  # 读取集合 ID。
        kind = str(item_set.get("kind"))  # 读取集合类型。
        prefix = "N" if kind == "node" else ("S" if kind == "surface" else "E")  # 根据类型选择标签前缀。
        label = _safe_label(set_id, prefix)  # 构造安全标签。
        labels[set_id] = label  # 保存标签映射。
        if kind == "node":  # 处理节点集。
            numbers = [node_numbers[str(reference)] for reference in item_set.get("refs", []) if str(reference) in node_numbers]  # 解析节点编号。
            _write_numeric_set(lines, "NSET", label, numbers)  # 写入节点集。
        elif kind == "element":  # 处理单元集。
            numbers = [element_numbers[str(reference)] for reference in item_set.get("refs", []) if str(reference) in element_numbers]  # 解析单元编号。
            _write_numeric_set(lines, "ELSET", label, numbers)  # 写入单元集。
        elif kind == "surface":  # 处理表面集合。
            faces = [item for item in item_set.get("faces", []) if isinstance(item, dict)]  # 读取元素面定义。
            refs = [str(value) for value in item_set.get("refs", [])]  # 读取节点表面引用。
            if faces:  # 处理基于元素面的表面。
                lines.append(f"*SURFACE, NAME={label}, TYPE=ELEMENT")  # 写入元素面表面关键字。
                for face in faces:  # 遍历元素面。
                    element_ref = str(face.get("elementRef"))  # 读取单元引用。
                    if element_ref in element_numbers:  # 检查单元存在。
                        lines.append(f"{element_numbers[element_ref]}, {str(face.get('face', 'S1')).upper()}")  # 写入单元号与面标签。
            elif refs:  # 处理基于节点的表面。
                node_set_label = _safe_label(f"{set_id}_NODES", "N")  # 构造内部节点集标签。
                numbers = [node_numbers[reference] for reference in refs if reference in node_numbers]  # 解析节点编号。
                _write_numeric_set(lines, "NSET", node_set_label, numbers)  # 写入内部节点集。
                lines.append(f"*SURFACE, NAME={label}, TYPE=NODE")  # 写入节点表面关键字。
                lines.append(node_set_label)  # 引用内部节点集。
            else:  # 处理空表面。
                losses.append(_loss("blocked", set_id, label, "/finiteElementModels/sets", "表面集合为空，无法用于接触或压力。", "critical", "补充 faces 或节点 refs。"))  # 记录空表面阻断。
    return labels  # 返回集合标签映射。


def _append_boundary_conditions(lines: list[str], model: dict[str, Any], node_numbers: dict[str, int]) -> int:  # 写入模型级约束边界条件。
    boundary_lines: list[str] = []  # 初始化边界数据行。
    for node in model.get("nodes", []):  # 遍历 FE 节点。
        if not isinstance(node, dict) or str(node.get("id")) not in node_numbers:  # 跳过非法节点。
            continue  # 继续下一节点。
        constraints = _copy_constraints(node.get("constraints"))  # 规范化约束字典。
        for dof, name in enumerate(DOF_NAMES, start=1):  # 遍历六自由度。
            if constraints[name]:  # 检查自由度是否固定。
                boundary_lines.append(f"{node_numbers[str(node['id'])]}, {dof}, {dof}, 0.")  # 生成零边界数据行。
    if boundary_lines:  # 检查是否存在约束。
        lines.append("*BOUNDARY")  # 写入边界关键字。
        lines.extend(boundary_lines)  # 写入所有边界数据行。
    return len(boundary_lines)  # 返回约束自由度数量。


def _append_contacts(lines: list[str], document: dict[str, Any], set_labels: dict[str, str], losses: list[dict[str, Any]]) -> dict[str, dict[str, str]]:  # 写入接触与绑定定义并强制全模型接触算法一致。
    mapping: dict[str, dict[str, str]] = {}  # 初始化接触 ID 到主从面映射。
    contacts = [item for item in document.get("contacts", []) if isinstance(item, dict) and item.get("status") not in {"inactive", "blocked"}]  # 收集有效接触对象。
    requested_types: list[str] = []  # 初始化非绑定接触算法请求。
    aliases = {"NODE_TO_SURFACE": "NODE TO SURFACE", "SURFACE_TO_SURFACE": "SURFACE TO SURFACE", "FACE_TO_FACE": "SURFACE TO SURFACE"}  # 定义常见算法名称别名。
    for contact in contacts:  # 遍历接触对象以确定全局算法。
        if str(contact.get("behavior", "contact")) == "tie":  # 跳过独立 TIE 关系。
            continue  # 继续下一对象。
        attributes = contact.get("attributes", {}) if isinstance(contact.get("attributes"), dict) else {}  # 读取扩展属性。
        raw_type = str(attributes.get("calculixContactType", attributes.get("contactAlgorithm", "SURFACE TO SURFACE"))).upper().replace("-", "_")  # 读取并规范化算法名称。
        contact_type = aliases.get(raw_type, raw_type.replace("_", " "))  # 应用名称别名。
        requested_types.append(contact_type)  # 保存算法请求。
    unique_types = sorted(set(requested_types))  # 统计唯一算法类型。
    global_type = unique_types[0] if unique_types else "SURFACE TO SURFACE"  # 选择全模型统一接触算法。
    if global_type not in CONTACT_TYPES:  # 检查算法是否为 CalculiX 已知类型。
        losses.append(_loss("blocked", None, None, "/contacts/attributes/calculixContactType", f"未知 CalculiX 接触算法 {global_type}。", "critical", f"使用 {sorted(CONTACT_TYPES)} 中的一种。"))  # 记录算法阻断。
        global_type = "SURFACE TO SURFACE"  # 使用可检查的保守输出继续生成审查 deck。
    if len(unique_types) > 1:  # 检查同一 deck 是否混用了算法。
        losses.append(_loss("blocked", None, None, "/contacts", f"同一 CalculiX deck 请求了多种接触算法：{unique_types}。", "critical", "把全部非绑定接触统一为同一种 TYPE。"))  # 记录全局一致性阻断。
    for index, contact in enumerate(contacts, start=1):  # 遍历接触对象。
        contact_id = str(contact.get("id"))  # 读取接触 ID。
        master = set_labels.get(str(contact.get("masterSurfaceRef")))  # 解析主表面标签。
        slave = set_labels.get(str(contact.get("slaveSurfaceRef")))  # 解析从表面标签。
        if not master or not slave:  # 检查主从面映射。
            losses.append(_loss("blocked", contact_id, None, "/contacts", "接触主面或从面没有导出为 CalculiX surface。", "critical", "修复 surface set 引用。"))  # 记录阻断问题。
            continue  # 跳过非法接触。
        behavior = str(contact.get("behavior", "contact"))  # 读取接触行为。
        if behavior == "tie":  # 处理绑定关系。
            tolerance = contact.get("attributes", {}).get("positionTolerance") if isinstance(contact.get("attributes"), dict) else None  # 读取可选位置容差。
            header = f"*TIE, NAME={_safe_label(contact_id, 'T')}"  # 构造 TIE 关键字。
            if tolerance is not None:  # 检查是否提供容差。
                header += f", POSITION TOLERANCE={float(tolerance):.12g}"  # 添加位置容差。
            lines.append(header)  # 写入绑定关键字。
            lines.append(f"{slave}, {master}")  # 按从面、主面顺序写入。
            mapping[contact_id] = {"master": master, "slave": slave, "kind": "tie", "type": "TIE"}  # 保存固定绑定映射。
            continue  # 完成当前绑定。
        mapping[contact_id] = {"master": master, "slave": slave, "kind": "contact", "type": global_type}  # 保存可阶段控制的接触映射。
        if behavior not in {"contact", "rough"}:  # 检查已验证的非线性行为。
            losses.append(_loss("blocked", contact_id, None, "/contacts/behavior", f"接触行为 {behavior} 没有经过当前 CalculiX 主线验证。", "critical", "使用 contact、rough 或 tie。"))  # 阻断未验证行为。
        interaction = _safe_label(f"INTERACTION_{index}_{contact_id}", "I")  # 构造表面相互作用名称。
        lines.append(f"*SURFACE INTERACTION, NAME={interaction}")  # 开始相互作用定义。
        normal_behavior = str(contact.get("normalBehavior", "hard"))  # 读取法向行为。
        penalty = contact.get("penaltyStiffness")  # 读取惩罚刚度。
        if normal_behavior in {"hard", "linear_penalty"}:  # 处理当前已验证的法向关系。
            if not (global_type == "MORTAR" and normal_behavior == "hard" and penalty is None):  # 对 Mortar 真硬接触允许省略罚刚度卡。
                effective_penalty = float(penalty) if penalty is not None else float((contact.get("attributes") or {}).get("defaultPenaltyStiffness", 1.0e12))  # 解析显式或项目默认惩罚刚度。
                lines.append("*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR")  # 写入线性压力—闭合关系。
                lines.append(f"{effective_penalty:.12g}")  # 写入惩罚刚度。
                if penalty is None:  # 检查是否采用默认值。
                    losses.append(_loss("defaulted", contact_id, interaction, "/contacts/penaltyStiffness", f"未指定罚刚度，已采用 {effective_penalty:.6g}。", "warning", "通过穿透、接触压力和收敛敏感性分析校准。"))  # 记录可审计默认值。
        else:  # 处理尚未验证的法向本构。
            losses.append(_loss("blocked", contact_id, interaction, "/contacts/normalBehavior", f"法向行为 {normal_behavior} 未在当前 Adapter 中验证。", "critical", "使用 hard 或 linear_penalty。"))  # 阻断未知法向本构。
        tangential = str(contact.get("tangentialBehavior", "frictionless"))  # 读取切向行为。
        coefficient = float(contact.get("frictionCoefficient", 0.0) or 0.0)  # 读取摩擦系数。
        if tangential in {"penalty_friction", "rough"} or coefficient > 0.0:  # 检查是否需要摩擦。
            if tangential == "rough" and coefficient <= 0.0:  # 为 rough 语义建立可审计近似。
                coefficient = float((contact.get("attributes") or {}).get("roughFrictionCoefficient", 10.0))  # 使用项目可覆盖的大摩擦系数。
                losses.append(_loss("degraded", contact_id, interaction, "/contacts/tangentialBehavior", f"rough 已用摩擦系数 {coefficient:.6g} 近似。", "warning", "核验切向滑移并按项目基准校准。"))  # 记录 rough 近似。
            lines.append("*FRICTION")  # 写入摩擦关键字。
            lines.append(f"{coefficient:.12g}")  # 写入库仑摩擦系数。
        header = f"*CONTACT PAIR, INTERACTION={interaction}, TYPE={global_type}"  # 构造接触对关键字。
        if global_type == "NODE TO SURFACE" and not bool(contact.get("finiteSliding", True)):  # 检查节点—面小滑移设置。
            header += ", SMALL SLIDING"  # 仅对节点—面算法写入小滑移参数。
        if global_type != "NODE TO SURFACE" and bool(contact.get("finiteSliding", True)):  # 检查面—面算法的大滑移请求。
            losses.append(_loss("degraded", contact_id, interaction, "/contacts/finiteSliding", f"{global_type} 在当前 CalculiX 映射中按小滑移处理。", "warning", "大滑移问题改用统一 NODE TO SURFACE 并执行基准验证。"))  # 记录滑移能力差异。
        adjust = contact.get("attributes", {}).get("adjust") if isinstance(contact.get("attributes"), dict) else None  # 读取可选几何调整量。
        if adjust is not None:  # 检查是否指定调整量。
            header += f", ADJUST={float(adjust):.12g}"  # 添加调整量。
        lines.append(header)  # 写入接触对关键字。
        lines.append(f"{slave}, {master}")  # 按从面、主面顺序写入。
    return mapping  # 返回接触映射。


def _prestress_initial_tensor(system: dict[str, Any], stress: float) -> list[float]:  # 根据束首段方向构造全局初始应力张量。
    path = [item for item in system.get("path", []) if isinstance(item, dict)]  # 读取路径点。
    if len(path) < 2:  # 检查路径完整性。
        return [stress, 0.0, 0.0, 0.0, 0.0, 0.0]  # 对非法路径使用全局 X 方向并交由验证器阻断。
    first = [float(value) for value in path[0].get("position", [0.0, 0.0, 0.0])]  # 读取起点。
    second = [float(value) for value in path[1].get("position", [1.0, 0.0, 0.0])]  # 读取第二点。
    direction = _unit([second[index] - first[index] for index in range(3)], [1.0, 0.0, 0.0])  # 计算束方向。
    x, y, z = direction  # 解包方向余弦。
    return [stress * x * x, stress * y * y, stress * z * z, stress * x * y, stress * x * z, stress * y * z]  # 返回对称张量分量 xx、yy、zz、xy、xz、yz。


def _integration_point_count(element: dict[str, Any], system: dict[str, Any]) -> int:  # 解析初始应力目标单元的积分点数量。
    attributes = element.get("attributes", {}) if isinstance(element.get("attributes"), dict) else {}  # 读取单元扩展属性。
    system_attributes = system.get("attributes", {}) if isinstance(system.get("attributes"), dict) else {}  # 读取预应力扩展属性。
    override = attributes.get("integrationPointCount", system_attributes.get("integrationPointCount"))  # 读取单元级或系统级显式覆盖。
    if override is not None:  # 检查是否提供覆盖值。
        return max(1, int(override))  # 返回正积分点数量。
    return int(INTEGRATION_POINT_COUNTS.get(str(element.get("type")), 0))  # 返回标准单元默认积分点数量。


def _effective_prestress(system: dict[str, Any]) -> float:  # 计算用于初始应力或原生预紧控制的有效应力。
    if system.get("initialStress") is not None:  # 优先使用直接给定初始应力。
        return float(system.get("initialStress")) * (1.0 - float(system.get("immediateLossFactor", 0.0) or 0.0))  # 应用即时损失系数。
    analysis = analyze_prestress(system)  # 计算预应力沿程与即时损失。
    stations = analysis.get("stations", [])  # 读取沿程计算站点。
    if not stations:  # 检查计算结果非空。
        raise ValueError("预应力损失计算没有生成有效站点。")  # 阻止空结果继续导出。
    return float(stations[0]["forceAfterImmediateLoss"]) / float(system.get("area"))  # 返回张拉端即时有效应力。


def _append_prestress_definitions(lines: list[str], document: dict[str, Any], model: dict[str, Any], set_index: dict[str, dict[str, Any]], set_labels: dict[str, str], node_numbers: dict[str, int], element_numbers: dict[str, int], losses: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:  # 写入初始应力、原生预紧截面并准备阶段荷载控制。
    equivalent: dict[str, list[dict[str, Any]]] = {}  # 初始化阶段或全局等效荷载映射。
    native: dict[str, list[dict[str, Any]]] = {}  # 初始化阶段或全局原生预紧控制映射。
    initial_rows: list[str] = []  # 初始化初始应力数据行。
    element_index = {str(item.get("id")): item for item in model.get("elements", []) if isinstance(item, dict) and item.get("id")}  # 建立 FE 单元索引。
    used_node_refs = {str(reference) for item in model.get("elements", []) if isinstance(item, dict) for reference in item.get("nodeRefs", [])}  # 收集已参加单元的节点。
    next_node_number = max(node_numbers.values(), default=0) + 1  # 计算原生预紧参考节点起始编号。
    for system in document.get("prestressingSystems", []):  # 遍历预应力系统。
        if not isinstance(system, dict) or system.get("status") in {"inactive", "released"}:  # 跳过非法或停用系统。
            continue  # 继续下一系统。
        system_id = str(system.get("id"))  # 读取系统 ID。
        representation = str(system.get("representation", "equivalent_load"))  # 读取预应力表示方式。
        stage_key = str(system.get("stageRef") or "__GLOBAL__")  # 使用施工阶段或全局键。
        if representation == "equivalent_load":  # 处理折线等效节点荷载。
            try:  # 捕获预应力几何或参数错误。
                loads = equivalent_nodal_loads(system)  # 计算等效节点荷载。
                equivalent.setdefault(stage_key, []).extend([{**item, "systemRef": system_id} for item in loads])  # 保存等效荷载。
            except ValueError as error:  # 处理预应力计算失败。
                losses.append(_loss("blocked", system_id, None, "/prestressingSystems", str(error), "critical", "修复预应力路径、面积和张拉参数。"))  # 记录阻断问题。
            continue  # 完成等效荷载系统。
        if representation in {"initial_stress", "truss_tendon"}:  # 处理初始应力或桁架钢束表示。
            try:  # 捕获预应力损失计算错误。
                stress = _effective_prestress(system)  # 计算有效初始应力。
                tensor = _prestress_initial_tensor(system, stress)  # 构造全局应力张量。
                target_elements: list[str] = []  # 初始化目标单元 ID。
                for target in system.get("targetRefs", []):  # 遍历目标引用。
                    target_elements.extend(_resolve_stage_element_ids(str(target), model, set_index))  # 解析目标单元。
                for element_id in sorted(set(target_elements)):  # 遍历去重目标单元。
                    element = element_index.get(element_id)  # 读取目标单元对象。
                    if element is None or element_id not in element_numbers:  # 检查目标单元存在。
                        continue  # 跳过非法目标。
                    integration_points = _integration_point_count(element, system)  # 获取单元积分点数量。
                    if integration_points <= 0:  # 检查单元类型是否有已验证积分点映射。
                        losses.append(_loss("blocked", system_id, element_id, "/prestressingSystems/targetRefs", f"单元类型 {element.get('type')} 没有已验证的初始应力积分点映射。", "critical", "把目标改为 T3D2 或受支持实体单元，或显式提供 integrationPointCount 并完成基准验证。"))  # 记录单元类型阻断。
                        continue  # 跳过未验证单元。
                    for integration_point in range(1, integration_points + 1):  # 遍历全部积分点。
                        initial_rows.append(f"{element_numbers[element_id]}, {integration_point}, " + ", ".join(f"{value:.12g}" for value in tensor))  # 写入单元号、积分点号和六个应力分量。
                if not target_elements:  # 检查是否解析到目标。
                    losses.append(_loss("blocked", system_id, None, "/prestressingSystems/targetRefs", f"{representation} 未解析到任何 FE 单元。", "critical", "把 targetRefs 指向预应力筋 FE 单元或单元集。"))  # 记录目标阻断。
            except ValueError as error:  # 处理损失计算失败。
                losses.append(_loss("blocked", system_id, None, "/prestressingSystems", str(error), "critical", "修复预应力参数。"))  # 记录阻断问题。
            continue  # 完成初始应力系统。
        if representation == "solver_native":  # 处理 CalculiX 原生预紧截面。
            attributes = system.get("attributes", {}) if isinstance(system.get("attributes"), dict) else {}  # 读取原生参数。
            surface_ref = str(attributes.get("pretensionSurfaceRef", ""))  # 读取预紧截面表面引用。
            surface_label = set_labels.get(surface_ref)  # 解析 CalculiX 表面标签。
            if not surface_label:  # 检查预紧表面映射。
                losses.append(_loss("blocked", system_id, None, "/prestressingSystems/attributes/pretensionSurfaceRef", "solver_native 预紧截面没有映射到 CalculiX surface。", "critical", "修复 pretensionSurfaceRef。"))  # 记录表面阻断。
                continue  # 跳过非法系统。
            requested_node_ref = attributes.get("referenceFeNodeRef")  # 读取可选已有参考节点。
            if requested_node_ref is not None and str(requested_node_ref) in node_numbers:  # 检查是否复用已有 FE 节点。
                reference_node_ref = str(requested_node_ref)  # 保存已有参考节点 ID。
                if reference_node_ref in used_node_refs:  # 检查参考节点是否参加任何单元。
                    losses.append(_loss("blocked", system_id, reference_node_ref, "/prestressingSystems/attributes/referenceFeNodeRef", "PRE-TENSION SECTION 参考节点不能属于任何有限元单元。", "critical", "删除 referenceFeNodeRef，让 Adapter 生成独立参考节点。"))  # 记录参考节点阻断。
                    continue  # 跳过非法系统。
                reference_number = node_numbers[reference_node_ref]  # 读取已有参考节点编号。
            else:  # 处理自动生成独立参考节点。
                reference_node_ref = f"pretension.ref.{_safe_label(system_id, 'P', 48).lower()}"  # 构造稳定内部参考节点 ID。
                while reference_node_ref in node_numbers:  # 检查生成 ID 是否碰撞。
                    reference_node_ref += "_x"  # 追加稳定碰撞后缀。
                reference_number = next_node_number  # 分配新数值编号。
                next_node_number += 1  # 更新下一可用编号。
                node_numbers[reference_node_ref] = reference_number  # 加入 ID 映射。
                reference_point = attributes.get("referencePoint")  # 读取可选参考点坐标。
                if not isinstance(reference_point, list) or len(reference_point) != 3:  # 检查参考点格式。
                    path_points = [item for item in system.get("path", []) if isinstance(item, dict)]  # 读取钢束路径点。
                    reference_point = list(path_points[0].get("position", [0.0, 0.0, 0.0])) if path_points else [0.0, 0.0, 0.0]  # 使用首个路径点作为可视化位置。
                lines.append(f"*NODE, NSET={_safe_label(reference_node_ref, 'N')}")  # 开始独立参考节点定义。
                lines.append(f"{reference_number}, {float(reference_point[0]):.12g}, {float(reference_point[1]):.12g}, {float(reference_point[2]):.12g}")  # 写入参考节点坐标。
            lines.append(f"*PRE-TENSION SECTION, SURFACE={surface_label}, NODE={reference_number}")  # 写入原生预紧截面关键字。
            direction = attributes.get("direction")  # 读取可选预紧方向。
            if isinstance(direction, list) and len(direction) == 3 and _norm([float(value) for value in direction]) > 1e-14:  # 检查方向向量有效。
                normalised = _unit([float(value) for value in direction], [1.0, 0.0, 0.0])  # 归一化方向向量。
                lines.append(", ".join(f"{value:.12g}" for value in normalised))  # 写入可选预紧方向。
            control_mode = str(attributes.get("controlMode", "force"))  # 读取控制方式。
            if control_mode == "force":  # 处理力控制。
                control_value = float(attributes.get("controlValue", system.get("jackingForce") or (_effective_prestress(system) * float(system.get("area")))))  # 解析预紧力。
            elif control_mode == "displacement":  # 处理位移控制。
                if attributes.get("controlValue") is None:  # 检查位移控制值存在。
                    losses.append(_loss("blocked", system_id, reference_node_ref, "/prestressingSystems/attributes/controlValue", "位移控制原生预紧缺少 controlValue。", "critical", "提供差分预紧位移。"))  # 记录控制值阻断。
                    continue  # 跳过非法系统。
                control_value = float(attributes.get("controlValue"))  # 读取位移控制值。
            else:  # 处理未知控制方式。
                losses.append(_loss("blocked", system_id, reference_node_ref, "/prestressingSystems/attributes/controlMode", f"未知预紧控制方式 {control_mode}。", "critical", "使用 force 或 displacement。"))  # 记录控制方式阻断。
                continue  # 跳过非法系统。
            native.setdefault(stage_key, []).append({"systemRef": system_id, "nodeRef": reference_node_ref, "nodeNumber": reference_number, "mode": control_mode, "value": control_value})  # 保存阶段原生控制。
            continue  # 完成原生预紧系统。
        losses.append(_loss("blocked", system_id, None, "/prestressingSystems/representation", f"预应力表示 {representation} 当前未自动导出。", "critical", "使用 equivalent_load、truss_tendon、initial_stress 或 solver_native。"))  # 记录未实现表示。
    if initial_rows:  # 检查是否存在初始应力。
        lines.append("*INITIAL CONDITIONS, TYPE=STRESS")  # 写入初始应力关键字。
        lines.extend(initial_rows)  # 写入全部初始应力数据行。
    return {"equivalent": equivalent, "native": native}  # 返回按阶段分组的预应力定义。


def _node_targets_for_structural_ref(target_ref: str, model: dict[str, Any]) -> list[str]:  # 把结构节点引用映射到 FE 节点 ID。
    direct_ids = {str(item.get("id")) for item in model.get("nodes", []) if isinstance(item, dict)}  # 收集 FE 节点 ID。
    if target_ref in direct_ids:  # 检查直接 FE 节点引用。
        return [target_ref]  # 返回直接节点。
    return [str(item.get("id")) for item in model.get("nodes", []) if isinstance(item, dict) and item.get("sourceRef") == target_ref]  # 按 sourceRef 查找映射节点。


def _append_load_case(lines: list[str], document: dict[str, Any], model: dict[str, Any], node_numbers: dict[str, int], set_labels: dict[str, str], selected_case_refs: list[str], equivalent_prestress: list[dict[str, Any]], native_prestress: list[dict[str, Any]], losses: list[dict[str, Any]]) -> dict[str, int]:  # 写入一个施工步中的荷载和原生预紧控制。
    case_index = {str(item.get("id")): item for item in document.get("loadCases", []) if isinstance(item, dict)}  # 建立工况索引。
    cload_rows: list[str] = []  # 初始化集中荷载数据行。
    dload_rows: list[str] = []  # 初始化体积或元素面荷载数据行。
    dsload_rows: list[str] = []  # 初始化表面压力数据行。
    boundary_rows: list[str] = []  # 初始化预紧位移控制行。
    for load in document.get("loads", []):  # 遍历 BSDL 荷载。
        if not isinstance(load, dict) or str(load.get("caseRef")) not in selected_case_refs:  # 跳过其他工况。
            continue  # 继续下一荷载。
        case_factor = float(case_index.get(str(load.get("caseRef")), {}).get("factor", 1.0))  # 读取工况系数。
        kind = str(load.get("kind", "other"))  # 读取荷载类别。
        if kind == "nodal":  # 处理节点力和节点矩。
            attributes = load.get("attributes", {}) if isinstance(load.get("attributes"), dict) else {}  # 读取节点荷载扩展映射属性。
            target_ref = str(attributes.get("finiteElementNodeRef") or load.get("targetNodeRef"))  # 优先读取显式 FE 节点引用并回退到结构节点映射。
            targets = _node_targets_for_structural_ref(target_ref, model)  # 解析 FE 节点。
            if not targets:  # 检查节点映射。
                losses.append(_loss("ignored", str(load.get("id")), None, "/loads", "节点荷载目标没有映射到当前 FE 模型。", "warning", "补充 FE node.sourceRef 或直接引用 FE 节点。"))  # 记录荷载忽略。
                continue  # 跳过当前荷载。
            values = [float(value) * case_factor for value in list(load.get("force", [0.0, 0.0, 0.0])) + list(load.get("moment", [0.0, 0.0, 0.0]))]  # 合并并缩放六分量。
            for target in targets:  # 遍历目标 FE 节点。
                if target not in node_numbers:  # 检查编号存在。
                    continue  # 跳过非法目标。
                for dof, value in enumerate(values, start=1):  # 遍历六分量。
                    if abs(value) > 0.0:  # 跳过零值。
                        cload_rows.append(f"{node_numbers[target]}, {dof}, {value:.12g}")  # 保存 CLOAD 数据行。
        elif kind == "self_weight":  # 处理重力荷载。
            vector = [float(value) for value in load.get("force", [0.0, 0.0, -9.81])]  # 读取加速度向量。
            magnitude = _norm(vector)  # 计算加速度大小。
            direction = _unit(vector, [0.0, 0.0, -1.0])  # 计算加速度方向。
            target_set = str(load.get("attributes", {}).get("elementSetRef", "EALL")) if isinstance(load.get("attributes"), dict) else "EALL"  # 读取可选目标单元集。
            label = set_labels.get(target_set, "EALL")  # 解析目标集合标签。
            dload_rows.append(f"{label}, GRAV, {magnitude * case_factor:.12g}, {direction[0]:.12g}, {direction[1]:.12g}, {direction[2]:.12g}")  # 保存重力数据行。
        else:  # 处理扩展荷载类型。
            attributes = load.get("attributes", {}) if isinstance(load.get("attributes"), dict) else {}  # 读取扩展属性。
            surface_ref = attributes.get("surfaceRef")  # 读取表面引用。
            pressure = attributes.get("pressure")  # 读取压力值。
            if surface_ref is not None and pressure is not None and str(surface_ref) in set_labels:  # 检查表面压力定义。
                dsload_rows.append(f"{set_labels[str(surface_ref)]}, P, {float(pressure) * case_factor:.12g}")  # 保存 DSLOAD 表面压力。
            else:  # 处理无法映射的扩展荷载。
                losses.append(_loss("ignored", str(load.get("id")), None, "/loads", "扩展荷载缺少可识别的 surfaceRef/pressure，未导出。", "warning", "按 BSDL 扩展约定补充表面和压力。"))  # 记录荷载忽略。
    for item in equivalent_prestress:  # 遍历预应力等效节点力。
        node_ref = item.get("nodeRef")  # 读取路径点 FE 或结构节点引用。
        if node_ref is None:  # 检查节点引用存在。
            losses.append(_loss("ignored", str(item.get("systemRef")), None, "/prestressingSystems/path", "等效预应力路径点没有 nodeRef，无法施加到 FE 节点。", "warning", "为每个控制点绑定 FE 节点。"))  # 记录预应力映射缺失。
            continue  # 跳过该控制点。
        targets = _node_targets_for_structural_ref(str(node_ref), model)  # 解析 FE 节点。
        for target in targets:  # 遍历目标节点。
            if target not in node_numbers:  # 检查目标编号。
                continue  # 跳过非法目标。
            for dof, value in enumerate(item.get("force", [0.0, 0.0, 0.0]), start=1):  # 遍历三向等效力。
                if abs(float(value)) > 0.0:  # 跳过零力。
                    cload_rows.append(f"{node_numbers[target]}, {dof}, {float(value):.12g}")  # 保存等效 CLOAD 数据行。
    for control in native_prestress:  # 遍历 CalculiX 原生预紧控制。
        node_number = int(control.get("nodeNumber"))  # 读取独立参考节点编号。
        value = float(control.get("value", 0.0))  # 读取控制值。
        if str(control.get("mode")) == "force":  # 处理预紧力控制。
            cload_rows.append(f"{node_number}, 1, {value:.12g}")  # 把预紧力施加到参考节点自由度 1。
        else:  # 处理差分位移控制。
            boundary_rows.append(f"{node_number}, 1, 1, {value:.12g}")  # 把预紧位移施加到参考节点自由度 1。
    if cload_rows:  # 检查集中荷载。
        lines.append("*CLOAD, OP=NEW")  # 写入显式替换语义的集中荷载关键字。
        lines.extend(cload_rows)  # 写入集中荷载数据。
    if dload_rows:  # 检查体积或元素面荷载。
        lines.append("*DLOAD, OP=NEW")  # 写入显式替换语义的体积荷载关键字。
        lines.extend(dload_rows)  # 写入 DLOAD 数据。
    if dsload_rows:  # 检查表面压力。
        lines.append("*DSLOAD, OP=NEW")  # 写入显式替换语义的表面压力关键字。
        lines.extend(dsload_rows)  # 写入表面压力数据。
    if boundary_rows:  # 检查预紧位移控制。
        lines.append("*BOUNDARY, OP=MOD")  # 修改预紧参考节点边界。
        lines.extend(boundary_rows)  # 写入全部位移控制行。
    return {"cloadRows": len(cload_rows), "dloadRows": len(dload_rows), "dsloadRows": len(dsload_rows), "pretensionBoundaryRows": len(boundary_rows)}  # 返回荷载统计。


def _append_step_header(lines: list[str], settings: dict[str, Any], name: str) -> None:  # 写入分析步标题与求解过程关键字。
    nlgeom = bool(settings.get("nlgeom", False))  # 读取几何非线性开关。
    lines.append(f"*STEP, NAME={_safe_label(name, 'STEP')}, NLGEOM={'YES' if nlgeom else 'NO'}")  # 写入分析步关键字。
    analysis = str(settings.get("analysis", "linear_static"))  # 读取分析类型。
    if analysis in {"linear_static", "nonlinear_static"}:  # 处理静力分析。
        lines.append("*STATIC")  # 写入静力过程关键字。
        increment = settings.get("initialIncrement")  # 读取初始增量。
        period = settings.get("timePeriod")  # 读取步时间。
        minimum = settings.get("minimumIncrement")  # 读取最小增量。
        maximum = settings.get("maximumIncrement")  # 读取最大增量。
        if any(value is not None for value in [increment, period, minimum, maximum]):  # 检查是否提供增量控制。
            lines.append(f"{float(increment or 0.1):.12g}, {float(period or 1.0):.12g}, {float(minimum or 1e-8):.12g}, {float(maximum or 0.1):.12g}")  # 写入增量控制。
    elif analysis == "modal":  # 处理模态分析。
        modes = int(settings.get("modes", 10))  # 读取模态阶数。
        lines.append("*FREQUENCY")  # 写入频率过程关键字。
        lines.append(str(modes))  # 写入模态数量。
    elif analysis == "buckling":  # 处理线性屈曲分析。
        modes = int(settings.get("modes", 10))  # 读取屈曲模态数。
        lines.append("*BUCKLE")  # 写入屈曲关键字。
        lines.append(str(modes))  # 写入特征值数量。
    else:  # 处理未实现分析类型。
        raise ValueError(f"CalculiX Adapter 尚未实现分析类型：{analysis}")  # 阻止错误过程卡。


def _append_output_requests(lines: list[str], settings: dict[str, Any]) -> None:  # 写入 FRD 与 DAT 结果请求。
    lines.append("*NODE FILE")  # 请求节点文件输出。
    lines.append("U, RF")  # 请求位移与反力。
    lines.append("*EL FILE")  # 请求单元文件输出。
    lines.append("S, E")  # 请求应力与应变。
    lines.append("*NODE PRINT, NSET=NALL")  # 请求 DAT 节点输出用于轻量解析。
    lines.append("U, RF")  # 写入节点打印变量。
    lines.append("*EL PRINT, ELSET=EALL")  # 请求 DAT 单元输出用于审计。
    lines.append("S, E")  # 写入单元打印变量。
    if bool(settings.get("contactOutput", True)):  # 检查是否请求接触输出。
        lines.append("*CONTACT FILE")  # 请求接触结果文件。
        lines.append("CDIS, CSTR")  # 请求接触位移和接触应力。


def _expanded_active_elements(compiled_stage: dict[str, Any], model: dict[str, Any], set_index: dict[str, dict[str, Any]]) -> set[str]:  # 把阶段累计活动引用展开为 FE 单元集合。
    active_elements: set[str] = set()  # 初始化活动 FE 单元集合。
    for reference in compiled_stage.get("activeRefs", []):  # 遍历阶段累计活动引用。
        active_elements.update(_resolve_stage_element_ids(str(reference), model, set_index))  # 展开单元、集合或源构件引用。
    return active_elements  # 返回活动单元 ID 集合。


def _append_stages(lines: list[str], document: dict[str, Any], model: dict[str, Any], plan: dict[str, Any], set_labels: dict[str, str], node_numbers: dict[str, int], contact_mapping: dict[str, dict[str, str]], prestress_definitions: dict[str, dict[str, list[dict[str, Any]]]], losses: list[dict[str, Any]]) -> list[dict[str, Any]]:  # 写入无阶段或多阶段求解步骤。
    set_index = _collect_model_sets(model)  # 建立 FE 集合索引。
    equivalent_prestress = prestress_definitions.get("equivalent", {})  # 读取等效预应力分组。
    native_prestress = prestress_definitions.get("native", {})  # 读取原生预紧控制分组。
    requested_stages = [str(value) for value in plan.get("stageRefs", [])]  # 读取计划限定阶段。
    stage_objects = [item for item in document.get("constructionStages", []) if isinstance(item, dict) and (not requested_stages or str(item.get("id")) in requested_stages)]  # 收集目标施工阶段。
    step_summaries: list[dict[str, Any]] = []  # 初始化分析步摘要。
    if not stage_objects:  # 处理单步求解。
        settings = dict(plan.get("settings", {}))  # 复制求解设置。
        _append_step_header(lines, settings, str(plan.get("id", "STEP_1")))  # 写入单步过程。
        selected_case = settings.get("loadCaseRef")  # 读取显式工况。
        if selected_case is None:  # 处理未指定工况。
            task_ref = str(plan.get("taskRef"))  # 读取任务引用。
            task = next((item for item in document.get("analysisTasks", []) if isinstance(item, dict) and str(item.get("id")) == task_ref), {})  # 查找任务对象。
            case_refs = [str(value) for value in task.get("loadCaseRefs", [])]  # 读取任务工况。
        else:  # 处理显式工况。
            case_refs = [str(selected_case)]  # 使用单个工况。
        load_stats = _append_load_case(lines, document, model, node_numbers, set_labels, case_refs, equivalent_prestress.get("__GLOBAL__", []), native_prestress.get("__GLOBAL__", []), losses)  # 写入单步荷载。
        _append_output_requests(lines, settings)  # 写入结果请求。
        lines.append("*END STEP")  # 结束单步。
        step_summaries.append({"step": str(plan.get("id", "STEP_1")), "loadCaseRefs": case_refs, **load_stats})  # 保存单步摘要。
        return step_summaries  # 返回单步摘要。
    compiled = compile_stage_plan(document)  # 编译阶段累计状态链。
    if not compiled.get("valid", False):  # 检查阶段编译结果。
        for issue in compiled.get("issues", []):  # 遍历编译问题。
            losses.append(_loss("blocked", issue.get("stageRef"), None, "/constructionStages", str(issue.get("message")), "critical", "修复阶段激活、停用和引用顺序。"))  # 转换为阻断损失。
        return step_summaries  # 阻止输出不一致阶段。
    compiled_by_id = {str(item.get("stageId")): item for item in compiled.get("stages", [])}  # 建立编译阶段索引。
    sorted_stages = sorted(stage_objects, key=lambda item: int(item.get("sequence", 0)))  # 按序号排序阶段。
    element_numbers = {str(item.get("id")): index for index, item in enumerate(model.get("elements", []), start=1) if isinstance(item, dict) and item.get("id")}  # 建立 FE 单元编号。
    element_types = {str(item.get("id")): str(item.get("type")) for item in model.get("elements", []) if isinstance(item, dict) and item.get("id")}  # 建立单元类型索引。
    all_elements = set(element_numbers)  # 收集输入文件初始存在的全部单元。
    variable_contacts = {key for key, value in contact_mapping.items() if value.get("kind") == "contact"}  # 收集可阶段停启接触对。
    previous_elements = set(all_elements)  # CalculiX 在首步前把已定义单元视为活动。
    previous_contacts = set(variable_contacts)  # CalculiX 在首步前把接触对视为活动。
    transition_plans: list[dict[str, Any]] = []  # 初始化阶段生死转换计划。
    for stage in sorted_stages:  # 预计算每阶段的单元和接触增量。
        stage_id = str(stage.get("id"))  # 读取阶段 ID。
        compiled_stage = compiled_by_id.get(stage_id, {})  # 读取累计阶段状态。
        desired_elements = _expanded_active_elements(compiled_stage, model, set_index)  # 展开本阶段目标活动单元。
        remove_elements = sorted(previous_elements - desired_elements)  # 计算本阶段需要移除的单元。
        add_elements = sorted(desired_elements - previous_elements)  # 计算本阶段需要恢复的单元。
        desired_contacts = set(str(value) for value in compiled_stage.get("activeContactRefs", [])) & variable_contacts  # 解析本阶段累计活动接触。
        remove_contacts = sorted(previous_contacts - desired_contacts)  # 计算本阶段需要移除的接触对。
        add_contacts = sorted(desired_contacts - previous_contacts)  # 计算本阶段需要恢复的接触对。
        remove_label = _safe_label(f"STAGE_{stage_id}_REMOVE", "E") if remove_elements else None  # 构造移除单元集标签。
        add_label = _safe_label(f"STAGE_{stage_id}_ADD", "E") if add_elements else None  # 构造恢复单元集标签。
        if remove_label is not None:  # 检查是否需要定义移除集合。
            _write_numeric_set(lines, "ELSET", remove_label, [element_numbers[value] for value in remove_elements])  # 在所有分析步前定义移除集合。
        if add_label is not None:  # 检查是否需要定义恢复集合。
            _write_numeric_set(lines, "ELSET", add_label, [element_numbers[value] for value in add_elements])  # 在所有分析步前定义恢复集合。
        transition_plans.append({"stage": stage, "compiled": compiled_stage, "removeLabel": remove_label, "addLabel": add_label, "removeElements": remove_elements, "addElements": add_elements, "removeContacts": remove_contacts, "addContacts": add_contacts, "desiredElements": desired_elements, "desiredContacts": desired_contacts})  # 保存阶段转换计划。
        previous_elements = desired_elements  # 更新下一阶段的前态单元集合。
        previous_contacts = desired_contacts  # 更新下一阶段的前态接触集合。
    if transition_plans:  # 检查是否至少存在一个阶段。
        first_removed_types = {element_types.get(value) for value in transition_plans[0]["removeElements"]}  # 收集首阶段要移除的单元类型。
        if first_removed_types & (BEAM_TYPES | TRUSS_TYPES | SHELL_TYPES):  # 检查首步是否移除一维或二维展开单元。
            dummy_settings = {**dict(plan.get("settings", {})), "analysis": "linear_static", "nlgeom": False}  # 构造零荷载初始化步设置。
            _append_step_header(lines, dummy_settings, "CCX_INITIALIZE_EXPANDED_ELEMENTS")  # 写入展开单元初始化虚拟步。
            _append_output_requests(lines, {**dummy_settings, "contactOutput": False})  # 写入最小结果请求。
            lines.append("*END STEP")  # 结束虚拟初始化步。
            step_summaries.append({"step": "CCX_INITIALIZE_EXPANDED_ELEMENTS", "synthetic": True, "reason": "首个施工阶段需要移除一维或二维展开单元。"})  # 保存虚拟步审计摘要。
    for transition in transition_plans:  # 按序输出每个施工阶段分析步。
        stage = transition["stage"]  # 读取阶段对象。
        compiled_stage = transition["compiled"]  # 读取累计状态。
        stage_id = str(stage.get("id"))  # 读取阶段 ID。
        settings = {**dict(plan.get("settings", {})), **dict(stage.get("solverSettings", {}))}  # 合并计划和阶段求解设置。
        settings.setdefault("analysis", "nonlinear_static" if document.get("contacts") else "linear_static")  # 根据接触设置默认分析类型。
        settings.setdefault("nlgeom", bool(document.get("contacts")))  # 根据接触设置几何非线性。
        _append_step_header(lines, settings, stage_id)  # 写入阶段过程。
        if transition["removeLabel"] is not None:  # 检查是否需要移除单元。
            lines.append("*MODEL CHANGE, TYPE=ELEMENT, REMOVE")  # 写入单元停用关键字。
            lines.append(str(transition["removeLabel"]))  # 写入待停用单元集。
        if transition["addLabel"] is not None:  # 检查是否需要恢复单元。
            lines.append("*MODEL CHANGE, TYPE=ELEMENT, ADD=STRAIN FREE")  # 写入无初始应变恢复单元关键字。
            lines.append(str(transition["addLabel"]))  # 写入待恢复单元集。
        for contact_id in transition["removeContacts"]:  # 遍历需要停用的接触对。
            pair = contact_mapping[contact_id]  # 读取主从面标签。
            lines.append("*MODEL CHANGE, TYPE=CONTACT PAIR, REMOVE")  # 写入接触对停用关键字。
            lines.append(f"{pair['slave']}, {pair['master']}")  # 按从面、主面顺序写入。
        for contact_id in transition["addContacts"]:  # 遍历需要恢复的接触对。
            pair = contact_mapping[contact_id]  # 读取主从面标签。
            lines.append("*MODEL CHANGE, TYPE=CONTACT PAIR, ADD")  # 写入接触对恢复关键字。
            lines.append(f"{pair['slave']}, {pair['master']}")  # 按从面、主面顺序写入。
        active_prestress_refs = set(str(value) for value in compiled_stage.get("appliedPrestressRefs", []))  # 读取累计已施加预应力系统。
        stage_equivalent = list(equivalent_prestress.get("__GLOBAL__", []))  # 先加入无阶段归属的等效预应力。
        stage_native = list(native_prestress.get("__GLOBAL__", []))  # 先加入无阶段归属的原生控制。
        for values in equivalent_prestress.values():  # 遍历全部阶段等效预应力组。
            for item in values:  # 遍历组内等效节点力。
                if str(item.get("systemRef")) in active_prestress_refs and item not in stage_equivalent:  # 检查对应系统是否已施加且尚未加入。
                    stage_equivalent.append(item)  # 加入当前阶段完整等效预应力。
        for values in native_prestress.values():  # 遍历全部原生预紧控制组。
            for item in values:  # 遍历组内控制。
                if str(item.get("systemRef")) in active_prestress_refs and item not in stage_native:  # 检查对应系统是否已施加且尚未加入。
                    stage_native.append(item)  # 加入当前阶段原生控制。
        case_refs = [str(value) for value in compiled_stage.get("activeLoadCaseRefs", [])]  # 读取累计活动荷载工况。
        load_stats = _append_load_case(lines, document, model, node_numbers, set_labels, case_refs, stage_equivalent, stage_native, losses)  # 以 OP=NEW 语义写入阶段完整活动荷载。
        _append_output_requests(lines, settings)  # 写入阶段结果请求。
        lines.append("*END STEP")  # 结束当前阶段。
        step_summaries.append({"step": stage_id, "sequence": stage.get("sequence"), "activeElementRefs": len(transition["desiredElements"]), "addedElements": len(transition["addElements"]), "removedElements": len(transition["removeElements"]), "activeContactRefs": sorted(transition["desiredContacts"]), "addedContacts": transition["addContacts"], "removedContacts": transition["removeContacts"], "prestressRefs": sorted(active_prestress_refs), "loadCaseRefs": case_refs, **load_stats})  # 保存阶段摘要。
    return step_summaries  # 返回阶段摘要。


def _native_deck_path(document: dict[str, Any]) -> Path | None:  # 读取原生 CalculiX deck 直通路径。
    extensions = document.get("extensions") if isinstance(document.get("extensions"), dict) else {}  # 读取扩展容器。
    native = extensions.get("nativeCalculiX") if isinstance(extensions.get("nativeCalculiX"), dict) else {}  # 读取原生 deck 扩展。
    if native.get("useNativeDeck"):  # 检查是否声明直通。
        deck_path = native.get("deckPath")  # 读取扩展中的 deck 路径。
        if isinstance(deck_path, str) and deck_path and Path(deck_path).is_file():  # 检查路径指向现存文件。
            return Path(deck_path)  # 返回扩展声明的原生 deck。
    for artifact in document.get("artifacts", []):  # 回退到 solver_input/.inp 产物。
        if not isinstance(artifact, dict):  # 跳过非法产物项。
            continue  # 继续下一产物。
        if artifact.get("kind") == "solver_input" and str(artifact.get("format", "")).lower() == "inp":  # 识别原生输入产物。
            uri = artifact.get("uri")  # 读取产物 URI。
            if isinstance(uri, str) and uri and Path(uri).is_file():  # 检查产物文件存在。
                return Path(uri)  # 返回产物指向的原生 deck。
    return None  # 没有可用原生 deck。


def export_calculix(document: dict[str, Any], output_path: str | Path, mesh_policy_id: str | None = None, load_case_id: str | None = None, solver_plan_id: str | None = None, finite_element_model_id: str | None = None, strict: bool | None = None) -> dict[str, Any]:  # 导出混合单元、接触、预应力和施工阶段 CalculiX 输入。
    path = Path(output_path).resolve()  # 规范化输出路径。
    path.parent.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在。
    native_path = _native_deck_path(document)  # 检查是否存在原生 deck 直通。
    if native_path is not None:  # 处理兼容导入后的直通导出。
        shutil.copy2(native_path, path)  # 复制原生 deck，不从 BSDL 重建。
        id_map_path = path.with_suffix(".idmap.json")  # 构造身份映射文件路径。
        id_map = {"documentId": document.get("documentId"), "passthrough": True, "sourceDeck": str(native_path), "generatedAt": utc_now()}  # 构造直通身份映射。
        id_map_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入身份映射文件。
        report_id = f"conversion.calculix.{content_hash({'document': document.get('documentId'), 'revision': document.get('revision', {}).get('number'), 'passthrough': True, 'path': str(path)})[:16]}"  # 构造稳定转换报告 ID。
        report = {"id": report_id, "adapter": "bridge_mind.adapters.calculix", "adapterVersion": ADAPTER_VERSION, "sourceVersion": str(document.get("languageVersion", INDUSTRIAL_VERSION)), "targetVersion": f"CalculiX {CALCULIX_VERSION}", "createdAt": utc_now(), "passthrough": True, "mapped": {"passthrough": True, "sourceDeck": str(native_path), "nodes": 0, "elements": 0}, "losses": [], "blocked": False, "artifactRefs": [str(path), str(id_map_path)], "roundTrip": {"supported": False, "reason": "原生 deck 直通不从 BSDL 重建 CalculiX 输入。"}, "output": str(path), "idMapOutput": str(id_map_path), "warnings": []}  # 构造直通转换报告。
        report_path = path.with_suffix(".conversion.json")  # 构造转换报告文件路径。
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入转换报告文件。
        report["conversionReportOutput"] = str(report_path)  # 把报告路径加入返回对象。
        return report  # 返回直通报告且不重建 deck。
    plan = _select_solver_plan(document, solver_plan_id)  # 选择 CalculiX 求解计划。
    if load_case_id is not None:  # 处理兼容 API 传入的工况。
        plan.setdefault("settings", {})["loadCaseRef"] = load_case_id  # 写入临时工况设置。
    model, compatibility_generated = _select_model(document, plan, finite_element_model_id, mesh_policy_id)  # 选择或生成 FE 模型。
    node_numbers, element_numbers = _build_numbering(model)  # 建立连续编号。
    losses: list[dict[str, Any]] = []  # 初始化转换损失。
    if not node_numbers or not element_numbers:  # 检查 FE 模型非空。
        losses.append(_loss("blocked", str(model.get("id")), None, "/finiteElementModels", "FE 模型没有节点或单元。", "critical", "生成有效网格后重新导出。"))  # 记录空模型阻断。
    unsupported = sorted({str(item.get("type")) for item in model.get("elements", []) if isinstance(item, dict)} - SUPPORTED_ELEMENT_TYPES)  # 查找未支持单元类型。
    for element_type in unsupported:  # 遍历未支持类型。
        losses.append(_loss("blocked", str(model.get("id")), None, "/finiteElementModels/elements/type", f"CalculiX Adapter 不支持单元类型 {element_type}。", "critical", "改用受支持单元或扩展 Adapter。"))  # 记录单元阻断。
    materials = {str(item.get("id")): item for item in document.get("materials", []) if isinstance(item, dict) and item.get("id")}  # 建立材料索引。
    shell_sections = {str(item.get("id")): item for item in document.get("shellSections", []) if isinstance(item, dict) and item.get("id")}  # 建立壳截面索引。
    solid_sections = {str(item.get("id")): item for item in document.get("solidSections", []) if isinstance(item, dict) and item.get("id")}  # 建立实体截面索引。
    used_material_refs = {_material_for_element(item, shell_sections, solid_sections) for item in model.get("elements", []) if isinstance(item, dict)}  # 收集模型使用材料。
    missing_materials = sorted(str(value) for value in used_material_refs if value and value not in materials)  # 查找缺失材料。
    for material_ref in missing_materials:  # 遍历缺失材料。
        losses.append(_loss("blocked", material_ref, None, "/finiteElementModels/elements/materialRef", "FE 单元引用的材料不存在。", "critical", "补充 materials 对象。"))  # 记录材料阻断。
    material_labels = {material_id: _safe_label(f"MAT_{material_id}", "M") for material_id in materials}  # 构造材料标签映射。
    lines: list[str] = []  # 初始化输入文件行。
    lines.append("*HEADING")  # 写入文件标题关键字。
    lines.append(f"BridgeMind BSDL Industrial {INDUSTRIAL_VERSION} -> CalculiX {CALCULIX_VERSION}")  # 写入标题文本。
    lines.append(f"** Generated at {utc_now()}")  # 写入生成时间。
    lines.append(f"** Document {document.get('documentId')} revision {document.get('revision', {}).get('number')}")  # 写入源修订信息。
    lines.append(f"** FE model {model.get('id')} mesh hash {model.get('meshHash')}")  # 写入 FE 模型和哈希。
    lines.append("*NODE, NSET=NALL")  # 开始节点定义并建立全节点集。
    for node in model.get("nodes", []):  # 遍历 FE 节点。
        if not isinstance(node, dict) or str(node.get("id")) not in node_numbers:  # 跳过非法节点。
            continue  # 继续下一节点。
        position = [float(value) for value in node.get("position", [0.0, 0.0, 0.0])]  # 读取节点坐标。
        lines.append(f"{node_numbers[str(node['id'])]}, {position[0]:.12g}, {position[1]:.12g}, {position[2]:.12g}")  # 写入节点号与坐标。
    element_groups: dict[str, list[dict[str, Any]]] = {}  # 初始化按单元类型分组。
    for element in model.get("elements", []):  # 遍历 FE 单元。
        if isinstance(element, dict):  # 检查单元结构。
            element_groups.setdefault(str(element.get("type")), []).append(element)  # 加入类型分组。
    for element_type, elements in element_groups.items():  # 遍历单元类型分组。
        if element_type not in SUPPORTED_ELEMENT_TYPES:  # 跳过未支持类型。
            continue  # 继续下一类型。
        lines.append(f"*ELEMENT, TYPE={element_type}, ELSET=ETYPE_{_safe_label(element_type, 'E')}")  # 写入单元类型关键字。
        for element in elements:  # 遍历当前类型单元。
            refs = [node_numbers[str(reference)] for reference in element.get("nodeRefs", []) if str(reference) in node_numbers]  # 解析节点编号。
            lines.append(f"{element_numbers[str(element['id'])]}, " + ", ".join(str(value) for value in refs))  # 写入单元号和连接关系。
    _write_numeric_set(lines, "ELSET", "EALL", list(element_numbers.values()))  # 写入全单元集。
    _append_materials(lines, materials, material_labels, losses)  # 写入材料定义。
    _append_sections(lines, model, document, element_numbers, material_labels, losses)  # 写入截面与分组。
    set_labels = _append_sets_and_surfaces(lines, model, node_numbers, element_numbers, losses)  # 写入集合和表面。
    constrained_dofs = _append_boundary_conditions(lines, model, node_numbers)  # 写入边界条件。
    contact_mapping = _append_contacts(lines, document, set_labels, losses)  # 写入接触与绑定关系。
    set_index = _collect_model_sets(model)  # 建立集合索引。
    prestress_definitions = _append_prestress_definitions(lines, document, model, set_index, set_labels, node_numbers, element_numbers, losses)  # 写入预应力初始场、原生截面并准备阶段控制。
    step_summaries = _append_stages(lines, document, model, plan, set_labels, node_numbers, contact_mapping, prestress_definitions, losses)  # 写入求解步骤。
    strict_mode = bool(plan.get("settings", {}).get("strictConversion", True) if strict is None else strict)  # 解析严格转换模式。
    blocking_losses = [item for item in losses if item.get("severity") in {"error", "critical"} or item.get("category") == "blocked"]  # 提取阻断损失。
    blocked = bool(blocking_losses and strict_mode)  # 根据严格模式计算阻断状态。
    if blocked:  # 处理阻断导出。
        lines.insert(0, "** BLOCKED: conversion report contains critical loss; this deck is for inspection only")  # 在输入文件首行写入阻断提示。
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # 写入 CalculiX 输入文件。
    id_map_path = path.with_suffix(".idmap.json")  # 构造身份映射文件路径。
    id_map = {"documentId": document.get("documentId"), "finiteElementModelRef": model.get("id"), "taskRef": model.get("taskRef"), "coordinateSystemRef": model.get("coordinateSystemRef"), "nodes": node_numbers, "elements": element_numbers, "sets": set_labels, "materials": material_labels, "generatedAt": utc_now()}  # 构造完整身份映射。
    id_map_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入身份映射文件。
    report_id = f"conversion.calculix.{content_hash({'document': document.get('documentId'), 'revision': document.get('revision', {}).get('number'), 'model': model.get('id'), 'path': str(path)})[:16]}"  # 构造稳定转换报告 ID。
    report = {"id": report_id, "adapter": "bridge_mind.adapters.calculix", "adapterVersion": ADAPTER_VERSION, "sourceVersion": str(document.get("languageVersion", INDUSTRIAL_VERSION)), "targetVersion": f"CalculiX {CALCULIX_VERSION}", "createdAt": utc_now(), "mapped": {"nodes": len(node_numbers), "elements": len(element_numbers), "elementTypes": {key: len(value) for key, value in element_groups.items()}, "materials": len(materials), "sets": len(set_labels), "contacts": len(contact_mapping), "prestressingSystems": len(document.get("prestressingSystems", [])), "constructionStages": len(step_summaries), "constrainedDofs": constrained_dofs, "compatibilityGenerated": compatibility_generated, "steps": step_summaries, "idMap": str(id_map_path)}, "losses": losses, "blocked": blocked, "artifactRefs": [str(path), str(id_map_path)], "roundTrip": {"supported": False, "reason": "CalculiX 输入文件不是 BSDL 的完整语义真相源；回读只恢复结果与数值 ID 映射。"}, "output": str(path), "idMapOutput": str(id_map_path), "warnings": [item["message"] for item in losses if item.get("severity") in {"info", "warning"}]}  # 构造工业 Schema 兼容转换报告。
    report_path = path.with_suffix(".conversion.json")  # 构造转换报告文件路径。
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入转换报告文件。
    report["conversionReportOutput"] = str(report_path)  # 把报告路径加入返回对象。
    return report  # 返回转换报告。


def detect_calculix(executable: str | None = None) -> dict[str, Any]:  # 探测 CalculiX 可执行文件和运行环境。
    requested = executable or os.getenv("CCX_EXECUTABLE") or "ccx"  # 解析显式参数、环境变量或默认名称。
    resolved = shutil.which(requested) if not Path(requested).is_file() else str(Path(requested).resolve())  # 查找可执行文件。
    return {"available": bool(resolved), "requested": requested, "executable": resolved, "expectedVersion": CALCULIX_VERSION, "message": "已找到 CalculiX 可执行文件。" if resolved else "未找到 ccx；可继续导出输入文件，但不能在本机执行数值求解。"}  # 返回探测结果。


def _artifact_manifest(directory: Path, stem: str) -> list[dict[str, Any]]:  # 收集 CalculiX 作业产物及内容哈希。
    artifacts: list[dict[str, Any]] = []  # 初始化产物清单。
    for suffix in ARTIFACT_SUFFIXES:  # 遍历已知扩展名。
        candidate = directory / f"{stem}{suffix}"  # 构造候选产物路径。
        if candidate.is_file():  # 检查文件存在。
            data = candidate.read_bytes()  # 读取文件内容。
            artifacts.append({"path": str(candidate), "name": candidate.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})  # 保存路径、大小和哈希。
    return artifacts  # 返回产物清单。


def run_calculix(input_path: str | Path, executable: str | None = None, timeout: float = 3600.0, threads: int | None = None) -> dict[str, Any]:  # 执行 CalculiX 作业、回读 DAT 并归档全部产物。
    path = Path(input_path).resolve()  # 规范化输入文件路径。
    if not path.is_file():  # 检查输入文件存在。
        raise FileNotFoundError(path)  # 抛出明确文件错误。
    conversion_path = path.with_suffix(".conversion.json")  # 构造转换报告路径。
    if conversion_path.is_file():  # 检查是否存在转换报告。
        conversion = json.loads(conversion_path.read_text(encoding="utf-8"))  # 读取转换报告。
        if bool(conversion.get("blocked")):  # 检查关键语义损失是否阻断执行。
            result = {"status": "blocked", "message": "CalculiX 转换报告包含关键损失，未启动求解器。", "input": str(path), "conversionReport": str(conversion_path), "artifacts": _artifact_manifest(path.parent, path.stem)}  # 构造显式阻断状态。
            manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
            manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 保存阻断运行清单。
            result["manifest"] = str(manifest_path)  # 返回清单路径。
            return result  # 不调用外部求解器。
    lint_report = lint_deck(path)  # 在启动外部求解器前执行确定性静态检查。
    if not lint_report["valid"]:  # 检查输入文件是否存在阻断问题。
        result = {"status": "blocked", "message": "CalculiX 输入文件未通过静态检查，未启动求解器。", "input": str(path), "lint": lint_report, "artifacts": _artifact_manifest(path.parent, path.stem)}  # 构造静态阻断状态。
        manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 保存静态阻断运行清单。
        result["manifest"] = str(manifest_path)  # 返回清单路径。
        return result  # 结束静态阻断运行。
    capability = detect_calculix(executable)  # 探测 ccx 可执行文件。
    if not capability["available"]:  # 处理求解器不可用。
        result = {"status": "unavailable", "message": capability["message"], "input": str(path), "solver": capability, "artifacts": _artifact_manifest(path.parent, path.stem)}  # 返回非伪造的不可用状态。
        manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 保存不可用运行清单。
        result["manifest"] = str(manifest_path)  # 返回清单路径。
        return result  # 结束不可用运行。
    program = str(capability["executable"])  # 获取可执行文件路径。
    environment = dict(os.environ)  # 复制当前进程环境。
    if threads is not None and threads > 0:  # 检查是否指定线程数。
        environment["OMP_NUM_THREADS"] = str(int(threads))  # 设置 OpenMP 线程数。
        environment["CCX_NPROC_RESULTS"] = str(int(threads))  # 设置 CalculiX 结果处理线程数。
    stdout_path = path.with_suffix(".out")  # 构造标准输出日志路径。
    stderr_path = path.with_suffix(".log")  # 构造标准错误日志路径。
    try:  # 捕获超时和进程错误。
        completed = subprocess.run([program, "-i", path.stem], cwd=path.parent, capture_output=True, text=True, timeout=float(timeout), check=False, env=environment)  # 执行 ccx -i job。
        stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")  # 保存标准输出。
        stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")  # 保存标准错误。
        artifacts = _artifact_manifest(path.parent, path.stem)  # 收集全部作业产物。
        dat_path = path.with_suffix(".dat")  # 构造 DAT 文件路径。
        dat_text = dat_path.read_text(encoding="utf-8", errors="replace") if dat_path.is_file() else ""  # 读取 DAT 文本。
        convergence_error = "*ERROR" in dat_text.upper() or "ERROR" in (completed.stderr or "").upper()  # 检查显式错误标志。
        status = "succeeded" if completed.returncode == 0 and not convergence_error else "failed"  # 计算运行状态。
        result = {"status": status, "returnCode": completed.returncode, "input": str(path), "job": path.stem, "directory": str(path.parent), "solver": capability, "stdout": str(stdout_path), "stderr": str(stderr_path), "artifacts": artifacts, "startedBy": program, "timeoutSeconds": float(timeout)}  # 构造运行结果。
        if dat_path.is_file():  # 检查是否生成可解析 DAT。
            try:  # 捕获结果格式差异并保留原始产物。
                id_map_path = path.with_suffix(".idmap.json")  # 构造 ID 映射路径。
                parsed = parse_dat(dat_path, id_map_path if id_map_path.is_file() else None)  # 解析 DAT 结果摘要。
                id_map = json.loads(id_map_path.read_text(encoding="utf-8")) if id_map_path.is_file() else {}  # 读取结果上下文元数据。
                run_ref = f"run.calculix.{content_hash({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})[:16]}"  # 构造稳定运行引用。
                result_set = build_result_set(parsed, run_ref, str(id_map.get("taskRef") or "task.unknown"), id_map.get("coordinateSystemRef"), None, None, None)  # 构造 BSDL ResultSet 摘要。
                result["parsedResults"] = parsed  # 保存解析结果。
                result["resultSet"] = result_set  # 保存 BSDL 结果集。
            except (ValueError, TypeError, json.JSONDecodeError) as error:  # 处理结果解析失败。
                result["resultImport"] = {"status": "partial", "message": str(error), "dat": str(dat_path)}  # 明示回读不完整而不伪造结果。
    except subprocess.TimeoutExpired as error:  # 处理求解超时。
        stdout_path.write_text((error.stdout or "") if isinstance(error.stdout, str) else "", encoding="utf-8", errors="replace")  # 保存超时前标准输出。
        stderr_path.write_text((error.stderr or "") if isinstance(error.stderr, str) else "", encoding="utf-8", errors="replace")  # 保存超时前标准错误。
        result = {"status": "timeout", "message": f"CalculiX 超过 {timeout} 秒运行上限。", "input": str(path), "job": path.stem, "directory": str(path.parent), "solver": capability, "stdout": str(stdout_path), "stderr": str(stderr_path), "artifacts": _artifact_manifest(path.parent, path.stem), "timeoutSeconds": float(timeout)}  # 构造超时结果。
    manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入运行清单。
    result["manifest"] = str(manifest_path)  # 把清单路径加入返回对象。
    return result  # 返回运行结果。

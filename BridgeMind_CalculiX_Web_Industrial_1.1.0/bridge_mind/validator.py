"""BSDL 的结构与工程语义验证器。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供向量和有限数检查。
from pathlib import Path  # 提供 Schema 路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
import jsonschema  # 提供 JSON Schema Draft 2020-12 验证。
from jsonschema import FormatChecker  # 提供 date-time 等格式检查。
from .utils import finite_number, load_json  # 复用有限数判断与 JSON 读取。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。
DEFAULT_SCHEMA = ROOT / "schema" / "bsdl.schema.json"  # 指定核心 BSDL Schema。
INDUSTRIAL_SCHEMA = ROOT / "schema" / "bsdl-industrial.schema.json"  # 指定工业扩展 BSDL Schema。


def _issue(rule_id: str, severity: str, path: str, message: str, target_id: str | None = None, expected: Any = None, actual: Any = None) -> dict[str, Any]:  # 构造统一验证问题对象。
    return {"ruleId": rule_id, "severity": severity, "path": path, "targetId": target_id, "message": message, "expected": expected, "actual": actual}  # 返回稳定字段结构。


def _vector_norm(vector: list[float]) -> float:  # 计算三维向量范数。
    return math.sqrt(sum(float(value) * float(value) for value in vector))  # 使用欧氏范数。


def _dot(left: list[float], right: list[float]) -> float:  # 计算三维向量点积。
    return sum(float(a) * float(b) for a, b in zip(left, right))  # 返回逐分量乘积和。


def _cross(left: list[float], right: list[float]) -> list[float]:  # 计算三维向量叉积。
    return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0]]  # 返回右手叉积结果。


def _distance(left: list[float], right: list[float]) -> float:  # 计算两个三维点距离。
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))  # 返回欧氏距离。


def _collect_entities(document: dict[str, Any]) -> tuple[dict[str, tuple[str, dict[str, Any]]], list[dict[str, Any]]]:  # 建立全局实体索引并检测重复 ID。
    index: dict[str, tuple[str, dict[str, Any]]] = {}  # 初始化 ID 到路径和对象的索引。
    issues: list[dict[str, Any]] = []  # 初始化重复 ID 问题列表。
    root_entities: list[tuple[str, dict[str, Any]]] = []  # 初始化根级一等对象列表。
    if isinstance(document.get("project"), dict):  # 检查项目对象存在。
        root_entities.append(("/project", document["project"]))  # 把项目对象加入索引候选。
    collections = ["coordinateSystems", "agents", "materials", "sections", "shellSections", "solidSections", "nodes", "components", "connections", "loadCases", "loads", "analysisTasks", "regions", "meshPolicies", "solverPlans", "feedback", "artifacts", "contacts", "prestressingSystems", "constructionStages", "codeCheckPlans", "codeCheckResults", "solverProfiles", "resultSets", "externalMappings", "conversionReports"]  # 声明核心和工业一等实体集合。
    for collection in collections:  # 遍历每个实体数组。
        values = document.get(collection, [])  # 读取集合内容。
        if not isinstance(values, list):  # 跳过结构层已经会报告的非法集合。
            continue  # 继续检查下一集合。
        for position, entity in enumerate(values):  # 遍历数组实体。
            if isinstance(entity, dict):  # 只索引对象项。
                root_entities.append((f"/{collection}/{position}", entity))  # 保存实体路径与对象。
    cognitive_map = document.get("cognitiveMap", {})  # 读取认知地图对象。
    if isinstance(cognitive_map, dict):  # 检查认知地图为对象。
        for collection in ["landmarks", "decisionEdges"]:  # 遍历认知地图实体集合。
            values = cognitive_map.get(collection, [])  # 读取认知实体数组。
            if not isinstance(values, list):  # 跳过非法集合。
                continue  # 继续检查下一集合。
            for position, entity in enumerate(values):  # 遍历认知实体。
                if isinstance(entity, dict):  # 只索引对象项。
                    root_entities.append((f"/cognitiveMap/{collection}/{position}", entity))  # 保存认知实体路径。
    for path, entity in root_entities:  # 遍历所有候选实体。
        entity_id = entity.get("id")  # 读取实体 ID。
        if not isinstance(entity_id, str):  # 缺失 ID 由 Schema 负责报告。
            continue  # 跳过无法索引的对象。
        if entity_id in index:  # 检查 ID 是否已经出现。
            previous_path = index[entity_id][0]  # 读取首次出现路径。
            issues.append(_issue("BSDL-ID-001", "critical", path + "/id", f"ID {entity_id!r} 与 {previous_path} 重复。", entity_id, "全局唯一 ID", entity_id))  # 记录重复 ID。
        else:  # 处理首次出现 ID。
            index[entity_id] = (path, entity)  # 把实体加入索引。
    return index, issues  # 返回索引和重复问题。


def _check_reference(issues: list[dict[str, Any]], index: dict[str, tuple[str, dict[str, Any]]], value: Any, path: str, target_id: str | None, allowed_prefixes: tuple[str, ...] | None = None, nullable: bool = False) -> None:  # 检查单个引用存在性和可选类型。
    if value is None and nullable:  # 接受显式允许的空引用。
        return  # 无需进一步检查。
    if not isinstance(value, str):  # 非字符串引用由 Schema 通常也会报告。
        issues.append(_issue("BSDL-REF-001", "critical", path, "引用必须为字符串 ID。", target_id, "存在实体 ID", value))  # 记录引用类型错误。
        return  # 结束当前引用检查。
    if value not in index:  # 检查引用目标是否存在。
        issues.append(_issue("BSDL-REF-001", "critical", path, f"引用 {value!r} 不存在。", target_id, "存在实体 ID", value))  # 记录悬空引用。
        return  # 目标不存在时无法继续检查类型。
    if allowed_prefixes is not None:  # 仅在指定类型约束时检查路径前缀。
        target_path = index[value][0]  # 读取引用目标路径。
        if not any(target_path.startswith(prefix) for prefix in allowed_prefixes):  # 检查目标所属集合。
            issues.append(_issue("BSDL-REF-002", "error", path, f"引用 {value!r} 指向不允许的对象类型 {target_path}。", target_id, allowed_prefixes, target_path))  # 记录引用类型不匹配。


def _schema_issues(document: dict[str, Any], schema_path: str | Path) -> list[dict[str, Any]]:  # 执行 JSON Schema 验证并转换错误格式。
    schema = load_json(schema_path)  # 读取 Schema 文档。
    validator = jsonschema.Draft202012Validator(schema, format_checker=FormatChecker())  # 构造 Draft 2020-12 验证器。
    issues: list[dict[str, Any]] = []  # 初始化结构问题列表。
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):  # 按路径稳定排序所有错误。
        pointer = "/" + "/".join(str(part) for part in error.absolute_path) if error.absolute_path else "/"  # 构造 JSON Pointer 风格路径。
        issues.append(_issue("BSDL-SCHEMA-001", "critical", pointer, error.message, None, error.validator_value, error.instance))  # 记录结构错误。
    return issues  # 返回结构问题列表。


def _semantic_issues(document: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # 执行跨对象和工程语义检查。
    issues: list[dict[str, Any]] = []  # 初始化语义问题列表。
    index, id_issues = _collect_entities(document)  # 建立实体索引并收集重复 ID。
    issues.extend(id_issues)  # 合并重复 ID 问题。
    nodes = {item.get("id"): item for item in document.get("nodes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立节点索引。
    components = {item.get("id"): item for item in document.get("components", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立构件索引。
    materials = {item.get("id"): item for item in document.get("materials", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立材料索引。
    sections = {item.get("id"): item for item in document.get("sections", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立截面索引。
    load_cases = {item.get("id"): item for item in document.get("loadCases", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立工况索引。
    regions = {item.get("id"): item for item in document.get("regions", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立区域索引。
    coordinate_systems = {item.get("id"): item for item in document.get("coordinateSystems", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 建立坐标系索引。
    for position, coordinate_system in enumerate(document.get("coordinateSystems", [])):  # 遍历坐标系。
        if not isinstance(coordinate_system, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        coordinate_id = coordinate_system.get("id")  # 读取坐标系 ID。
        path = f"/coordinateSystems/{position}"  # 构造坐标系路径。
        axes = [coordinate_system.get("xAxis"), coordinate_system.get("yAxis"), coordinate_system.get("zAxis")]  # 读取三个坐标轴。
        if not all(isinstance(axis, list) and len(axis) == 3 and all(finite_number(value) for value in axis) for axis in axes):  # 检查坐标轴为有限三维向量。
            issues.append(_issue("BSDL-CS-001", "critical", path, "坐标系轴必须是有限三维向量。", coordinate_id))  # 记录坐标轴结构问题。
            continue  # 无法继续正交性检查。
        norms = [_vector_norm(axis) for axis in axes]  # 计算轴范数。
        if any(norm <= 1e-12 for norm in norms):  # 检查零向量轴。
            issues.append(_issue("BSDL-CS-001", "critical", path, "坐标系轴不得为零向量。", coordinate_id, "非零轴", norms))  # 记录零轴错误。
            continue  # 零轴无法归一化。
        normalized = [[value / norm for value in axis] for axis, norm in zip(axes, norms)]  # 归一化三个轴。
        orthogonal = abs(_dot(normalized[0], normalized[1])) < 1e-6 and abs(_dot(normalized[0], normalized[2])) < 1e-6 and abs(_dot(normalized[1], normalized[2])) < 1e-6  # 检查两两正交。
        handed = _dot(_cross(normalized[0], normalized[1]), normalized[2]) > 0.999999  # 检查右手关系。
        if not orthogonal or not handed:  # 检测坐标系不合法。
            issues.append(_issue("BSDL-CS-001", "critical", path, "坐标系轴必须正交并满足右手规则。", coordinate_id, "正交右手坐标系", {"orthogonal": orthogonal, "rightHanded": handed}))  # 记录坐标系错误。
        _check_reference(issues, index, coordinate_system.get("parentRef"), path + "/parentRef", coordinate_id, ("/coordinateSystems/",), True)  # 检查父坐标系引用。
    for position, node in enumerate(document.get("nodes", [])):  # 遍历节点。
        if not isinstance(node, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        node_id = node.get("id")  # 读取节点 ID。
        path = f"/nodes/{position}"  # 构造节点路径。
        coordinates = node.get("position")  # 读取节点坐标。
        if not isinstance(coordinates, list) or len(coordinates) != 3 or not all(finite_number(value) for value in coordinates):  # 检查坐标有限性。
            issues.append(_issue("BSDL-NODE-001", "error", path + "/position", "节点坐标必须包含三个有限数。", node_id, "有限三维坐标", coordinates))  # 记录非法节点坐标。
        _check_reference(issues, index, node.get("coordinateSystemRef"), path + "/coordinateSystemRef", node_id, ("/coordinateSystems/",))  # 检查节点坐标系引用。
    component_lengths: dict[str, float] = {}  # 初始化构件长度统计。
    active_frame_count = 0  # 初始化活跃梁单元构件计数。
    for position, component in enumerate(document.get("components", [])):  # 遍历构件。
        if not isinstance(component, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        component_id = component.get("id")  # 读取构件 ID。
        path = f"/components/{position}"  # 构造构件路径。
        _check_reference(issues, index, component.get("parentRef"), path + "/parentRef", component_id, ("/components/",), True)  # 检查主层级父对象。
        for node_position, node_ref in enumerate(component.get("nodeRefs", []) if isinstance(component.get("nodeRefs"), list) else []):  # 遍历构件节点引用。
            _check_reference(issues, index, node_ref, f"{path}/nodeRefs/{node_position}", component_id, ("/nodes/",))  # 检查节点引用存在且类型正确。
        topology = component.get("topology")  # 读取构件拓扑类型。
        node_refs = component.get("nodeRefs", [])  # 读取构件节点引用列表。
        if topology == "line":  # 处理线构件特殊规则。
            if not isinstance(node_refs, list) or len(node_refs) != 2 or node_refs[0] == node_refs[1]:  # 检查线构件恰有两个不同节点。
                issues.append(_issue("BSDL-COMP-001", "critical", path + "/nodeRefs", "线构件必须恰有两个不同节点。", component_id, "两个不同节点 ID", node_refs))  # 记录拓扑错误。
            elif node_refs[0] in nodes and node_refs[1] in nodes:  # 仅在节点存在时计算长度。
                length = _distance(nodes[node_refs[0]]["position"], nodes[node_refs[1]]["position"])  # 计算构件长度。
                component_lengths[str(component_id)] = length  # 保存长度统计。
                if length <= 1e-9:  # 检查零长度构件。
                    issues.append(_issue("BSDL-COMP-003", "critical", path + "/nodeRefs", "构件长度必须大于数值容差。", component_id, "> 1e-9 m", length))  # 记录零长度错误。
        analysis = component.get("analysis", {})  # 读取分析属性。
        if isinstance(analysis, dict) and analysis.get("active") is True and analysis.get("elementType") == "frame3d":  # 检查活跃空间梁构件。
            active_frame_count += 1  # 增加活跃梁构件计数。
            material_ref = component.get("materialRef")  # 读取材料引用。
            section_ref = component.get("sectionRef")  # 读取截面引用。
            if material_ref not in materials:  # 检查材料引用有效性。
                issues.append(_issue("BSDL-COMP-002", "critical", path + "/materialRef", "活跃 frame3d 构件必须引用有效材料。", component_id, "Material ID", material_ref))  # 记录材料缺失。
            if section_ref not in sections:  # 检查截面引用有效性。
                issues.append(_issue("BSDL-COMP-002", "critical", path + "/sectionRef", "活跃 frame3d 构件必须引用有效截面。", component_id, "Section ID", section_ref))  # 记录截面缺失。
    for position, connection in enumerate(document.get("connections", [])):  # 遍历连接对象。
        if not isinstance(connection, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        connection_id = connection.get("id")  # 读取连接 ID。
        path = f"/connections/{position}"  # 构造连接路径。
        participants = connection.get("participantRefs", [])  # 读取参与对象。
        if not isinstance(participants, list) or not participants:  # 检查连接至少有一个参与对象。
            issues.append(_issue("BSDL-CONN-001", "error", path + "/participantRefs", "连接至少需要一个参与对象。", connection_id, "至少一个构件或节点", participants))  # 记录空连接。
        for participant_position, participant_ref in enumerate(participants if isinstance(participants, list) else []):  # 遍历参与引用。
            _check_reference(issues, index, participant_ref, f"{path}/participantRefs/{participant_position}", connection_id, ("/components/", "/nodes/"))  # 检查参与对象引用。
        _check_reference(issues, index, connection.get("nodeRef"), path + "/nodeRef", connection_id, ("/nodes/",), True)  # 检查连接节点引用。
        _check_reference(issues, index, connection.get("coordinateSystemRef"), path + "/coordinateSystemRef", connection_id, ("/coordinateSystems/",))  # 检查连接坐标系引用。
    valid_load_count = 0  # 初始化有效荷载计数。
    for position, load in enumerate(document.get("loads", [])):  # 遍历荷载。
        if not isinstance(load, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        load_id = load.get("id")  # 读取荷载 ID。
        path = f"/loads/{position}"  # 构造荷载路径。
        if load.get("caseRef") not in load_cases:  # 检查工况引用。
            issues.append(_issue("BSDL-LOAD-001", "critical", path + "/caseRef", "荷载必须引用有效荷载工况。", load_id, "LoadCase ID", load.get("caseRef")))  # 记录工况缺失。
        if load.get("kind") == "nodal":  # 检查节点荷载目标。
            if load.get("targetNodeRef") not in nodes:  # 检查节点引用有效性。
                issues.append(_issue("BSDL-LOAD-001", "critical", path + "/targetNodeRef", "节点荷载必须引用有效节点。", load_id, "Node ID", load.get("targetNodeRef")))  # 记录目标节点缺失。
            else:  # 节点目标有效。
                force = load.get("force", [])  # 读取力向量。
                moment = load.get("moment", [])  # 读取矩向量。
                if any(abs(float(value)) > 0.0 for value in (force + moment) if finite_number(value)):  # 检查荷载不全为零。
                    valid_load_count += 1  # 增加有效荷载计数。
        _check_reference(issues, index, load.get("coordinateSystemRef"), path + "/coordinateSystemRef", load_id, ("/coordinateSystems/",))  # 检查荷载坐标系引用。
    for position, task in enumerate(document.get("analysisTasks", [])):  # 遍历分析任务。
        if not isinstance(task, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        task_id = task.get("id")  # 读取任务 ID。
        path = f"/analysisTasks/{position}"  # 构造任务路径。
        for case_position, case_ref in enumerate(task.get("loadCaseRefs", []) if isinstance(task.get("loadCaseRefs"), list) else []):  # 遍历任务工况引用。
            if case_ref not in load_cases:  # 检查工况存在。
                issues.append(_issue("BSDL-TASK-001", "error", f"{path}/loadCaseRefs/{case_position}", f"分析任务引用的工况 {case_ref!r} 不存在。", task_id, "LoadCase ID", case_ref))  # 记录任务工况错误。
    for position, region in enumerate(document.get("regions", [])):  # 遍历三维区域。
        if not isinstance(region, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        region_id = region.get("id")  # 读取区域 ID。
        path = f"/regions/{position}"  # 构造区域路径。
        geometry = region.get("geometry", {})  # 读取区域几何。
        if region.get("active") is True:  # 仅对活跃区域执行网格参数检查。
            if not finite_number(region.get("targetSize")) or float(region.get("targetSize", 0.0)) <= 0.0:  # 检查目标尺寸为正。
                issues.append(_issue("BSDL-REG-001", "error", path + "/targetSize", "活跃区域必须具有正 targetSize。", region_id, "> 0", region.get("targetSize")))  # 记录无效目标尺寸。
            if isinstance(geometry, dict) and geometry.get("kind") == "box":  # 检查包围盒尺寸。
                size = geometry.get("size", [])  # 读取包围盒尺寸。
                if not isinstance(size, list) or len(size) != 3 or any(not finite_number(value) or float(value) <= 0.0 for value in size):  # 检查三个尺寸为正。
                    issues.append(_issue("BSDL-REG-001", "error", path + "/geometry/size", "活跃包围盒区域的三个尺寸必须为正。", region_id, "三个正数", size))  # 记录无效包围盒尺寸。
        for target_position, target_ref in enumerate(region.get("targetRefs", []) if isinstance(region.get("targetRefs"), list) else []):  # 遍历区域目标引用。
            _check_reference(issues, index, target_ref, f"{path}/targetRefs/{target_position}", region_id, ("/components/", "/nodes/", "/connections/"))  # 检查区域目标对象。
    for position, policy in enumerate(document.get("meshPolicies", [])):  # 遍历网格策略。
        if not isinstance(policy, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        policy_id = policy.get("id")  # 读取策略 ID。
        path = f"/meshPolicies/{position}"  # 构造策略路径。
        _check_reference(issues, index, policy.get("taskRef"), path + "/taskRef", policy_id, ("/analysisTasks/",))  # 检查任务引用。
        for rule_position, rule in enumerate(policy.get("regionRules", []) if isinstance(policy.get("regionRules"), list) else []):  # 遍历区域规则。
            if isinstance(rule, dict) and rule.get("regionRef") not in regions:  # 检查区域规则引用存在。
                issues.append(_issue("BSDL-MESH-001", "error", f"{path}/regionRules/{rule_position}/regionRef", f"MeshPolicy 引用的区域 {rule.get('regionRef')!r} 不存在。", policy_id, "Region ID", rule.get("regionRef")))  # 记录区域引用错误。
    for position, plan in enumerate(document.get("solverPlans", [])):  # 遍历求解计划。
        if not isinstance(plan, dict):  # 跳过非法项。
            continue  # 继续检查下一项。
        plan_id = plan.get("id")  # 读取求解计划 ID。
        path = f"/solverPlans/{position}"  # 构造求解计划路径。
        _check_reference(issues, index, plan.get("taskRef"), path + "/taskRef", plan_id, ("/analysisTasks/",))  # 检查求解任务引用。
        _check_reference(issues, index, plan.get("meshPolicyRef"), path + "/meshPolicyRef", plan_id, ("/meshPolicies/",), True)  # 检查网格策略引用。
    constrained_dof_count = 0  # 初始化约束自由度计数。
    for node in nodes.values():  # 遍历节点约束。
        constraints = node.get("constraints", {})  # 读取六自由度约束。
        if isinstance(constraints, dict):  # 检查约束结构。
            constrained_dof_count += sum(1 for value in constraints.values() if value is True)  # 统计被约束自由度。
    if active_frame_count > 0 and constrained_dof_count == 0:  # 检查梁系模型是否完全无约束。
        issues.append(_issue("BSDL-SOLVE-001", "critical", "/nodes", "求解前模型必须至少有一个约束自由度。", None, "> 0 个约束自由度", constrained_dof_count))  # 记录无约束模型。
    if active_frame_count > 0 and valid_load_count == 0:  # 检查梁系模型是否没有有效荷载。
        issues.append(_issue("BSDL-SOLVE-001", "critical", "/loads", "求解前模型必须至少有一个非零荷载。", None, "> 0 个非零荷载", valid_load_count))  # 记录无荷载模型。
    stats = {"entities": len(index), "nodes": len(nodes), "components": len(components), "activeFrameComponents": active_frame_count, "regions": len(regions), "loads": len(document.get("loads", [])), "constrainedDofs": constrained_dof_count, "validLoads": valid_load_count, "coordinateSystems": len(coordinate_systems), "componentLengthMin": min(component_lengths.values()) if component_lengths else None, "componentLengthMax": max(component_lengths.values()) if component_lengths else None}  # 汇总验证统计。
    return issues, stats  # 返回语义问题与统计。


def _uses_industrial_schema(document: dict[str, Any]) -> bool:  # 判断文档是否启用工业扩展。
    version = str(document.get("languageVersion", "0.1.0"))  # 读取语言版本。
    return version.split(".", 1)[0].isdigit() and int(version.split(".", 1)[0]) >= 1  # 以主版本判断工业扩展。


def validate_document(document: dict[str, Any], schema_path: str | Path | None = None) -> dict[str, Any]:  # 对 BSDL 文档执行完整验证。
    selected_schema = Path(schema_path) if schema_path is not None else (INDUSTRIAL_SCHEMA if _uses_industrial_schema(document) else DEFAULT_SCHEMA)  # 根据语言版本选择 Schema。
    structure = _schema_issues(document, selected_schema)  # 执行结构验证。
    semantic, stats = _semantic_issues(document)  # 执行核心语义验证。
    industrial: list[dict[str, Any]] = []  # 初始化工业扩展问题。
    industrial_stats: dict[str, Any] = {}  # 初始化工业扩展统计。
    if _uses_industrial_schema(document):  # 检查是否需要工业验证。
        from .industrial.validation import validate_industrial  # 延迟导入避免核心模块循环依赖。
        industrial, industrial_stats = validate_industrial(document)  # 执行 FE、接触、预应力、阶段和 Adapter 语义验证。
    stats.update(industrial_stats)  # 合并工业统计。
    issues = structure + semantic + industrial  # 合并全部问题。
    severity_order = {"info": 0, "warning": 1, "error": 2, "critical": 3}  # 定义严重度排序。
    issues.sort(key=lambda item: (-severity_order.get(item["severity"], 0), item["path"], item["ruleId"]))  # 以严重度和路径稳定排序。
    blockers = [item for item in issues if item["severity"] in {"critical", "error"}]  # 提取阻断问题。
    warnings = [item for item in issues if item["severity"] == "warning"]  # 提取警告问题。
    level = "L0-invalid" if structure else ("L1-L4-invalid" if blockers else "L4-valid")  # 计算当前最低一致性状态。
    return {"valid": not blockers, "level": level, "schema": str(selected_schema), "errors": blockers, "warnings": warnings, "issues": issues, "stats": stats}  # 返回完整验证报告。

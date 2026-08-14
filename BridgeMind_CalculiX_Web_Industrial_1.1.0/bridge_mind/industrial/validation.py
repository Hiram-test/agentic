"""执行 BSDL Industrial 与 CalculiX 主线的跨对象工程验证。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from .mesh import expected_node_count  # 复用单元标准节点数表。

ROOT_COLLECTIONS = ["coordinateSystems", "agents", "materials", "sections", "shellSections", "solidSections", "nodes", "components", "connections", "loadCases", "loads", "analysisTasks", "regions", "meshPolicies", "solverPlans", "feedback", "artifacts", "contacts", "prestressingSystems", "constructionStages", "codeCheckPlans", "codeCheckResults", "solverProfiles", "resultSets", "externalMappings", "conversionReports"]  # 声明工业文档一等对象集合。
BEAM_TYPES = {"B31", "B32", "T3D2"}  # 声明需要一维截面的单元类型。
SHELL_TYPES = {"S3", "S4", "S4R"}  # 声明壳单元类型。
SOLID_TYPES = {"C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D20", "C3D20R"}  # 声明实体单元类型。
CALCULIX_CONTACT_BEHAVIORS = {"contact", "tie", "rough"}  # 声明当前 Adapter 已实现的接触行为。
CALCULIX_NORMAL_BEHAVIORS = {"hard", "linear_penalty"}  # 声明当前 Adapter 已验证的法向行为。
CALCULIX_TANGENTIAL_BEHAVIORS = {"frictionless", "penalty_friction", "rough"}  # 声明当前 Adapter 已实现的切向行为。
CALCULIX_PRESTRESS_REPRESENTATIONS = {"equivalent_load", "truss_tendon", "initial_stress", "solver_native"}  # 声明当前 Adapter 已实现的预应力表示。
CALCULIX_CONTACT_TYPES = {"NODE TO SURFACE", "SURFACE TO SURFACE", "MORTAR", "MASSLESS"}  # 声明 CalculiX 允许的接触算法类型。


def _issue(rule_id: str, severity: str, path: str, message: str, target_id: str | None = None, expected: Any = None, actual: Any = None) -> dict[str, Any]:  # 构造与核心验证器一致的问题对象。
    return {"ruleId": rule_id, "severity": severity, "path": path, "targetId": target_id, "message": message, "expected": expected, "actual": actual}  # 返回稳定字段结构。


def _root_index(document: dict[str, Any]) -> tuple[dict[str, tuple[str, dict[str, Any]]], list[dict[str, Any]]]:  # 建立根级对象索引并检查重复 ID。
    index: dict[str, tuple[str, dict[str, Any]]] = {}  # 初始化根对象索引。
    issues: list[dict[str, Any]] = []  # 初始化重复 ID 问题。
    candidates: list[tuple[str, dict[str, Any]]] = []  # 初始化候选对象列表。
    project = document.get("project")  # 读取项目对象。
    if isinstance(project, dict):  # 检查项目对象结构。
        candidates.append(("/project", project))  # 把项目加入候选列表。
    for collection in ROOT_COLLECTIONS:  # 遍历工业根对象集合。
        values = document.get(collection, [])  # 读取集合内容。
        if not isinstance(values, list):  # 跳过由 Schema 报告的非法集合。
            continue  # 继续下一集合。
        for position, item in enumerate(values):  # 遍历集合对象。
            if isinstance(item, dict):  # 只处理对象项。
                candidates.append((f"/{collection}/{position}", item))  # 保存对象路径。
    cognitive_map = document.get("cognitiveMap", {})  # 读取认知地图。
    if isinstance(cognitive_map, dict):  # 检查认知地图结构。
        for collection in ["landmarks", "decisionEdges"]:  # 遍历认知图对象集合。
            for position, item in enumerate(cognitive_map.get(collection, []) if isinstance(cognitive_map.get(collection), list) else []):  # 遍历认知图对象。
                if isinstance(item, dict):  # 只处理对象项。
                    candidates.append((f"/cognitiveMap/{collection}/{position}", item))  # 保存认知对象路径。
    for path, item in candidates:  # 遍历所有候选对象。
        object_id = item.get("id")  # 读取对象 ID。
        if not isinstance(object_id, str):  # 缺失 ID 由 Schema 负责报告。
            continue  # 跳过无法索引对象。
        if object_id in index:  # 检查 ID 重复。
            issues.append(_issue("BSDL-IND-ID-001", "critical", f"{path}/id", f"工业对象 ID {object_id!r} 与 {index[object_id][0]} 重复。", object_id, "全局唯一根对象 ID", object_id))  # 记录重复 ID。
        else:  # 处理首次出现 ID。
            index[object_id] = (path, item)  # 保存对象索引。
    return index, issues  # 返回根对象索引和问题。


def _add_nested_id(index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]], object_id: Any, path: str, item: dict[str, Any]) -> None:  # 把 FE 嵌套对象加入统一索引。
    if not isinstance(object_id, str):  # 缺失 ID 由 Schema 负责报告。
        return  # 跳过无法索引对象。
    if object_id in index:  # 检查与根对象或其他嵌套对象重复。
        issues.append(_issue("BSDL-IND-ID-002", "critical", f"{path}/id", f"FE 对象 ID {object_id!r} 与 {index[object_id][0]} 重复。", object_id, "文档级唯一 ID", object_id))  # 记录重复 ID。
    else:  # 处理首次出现 ID。
        index[object_id] = (path, item)  # 保存嵌套对象索引。


def _check_root_ref(issues: list[dict[str, Any]], index: dict[str, tuple[str, dict[str, Any]]], value: Any, path: str, target_id: str | None, prefixes: tuple[str, ...], nullable: bool = False) -> None:  # 检查根级引用存在性和集合类型。
    if value is None and nullable:  # 接受显式可空引用。
        return  # 无需继续检查。
    if not isinstance(value, str) or value not in index:  # 检查引用为已存在字符串 ID。
        issues.append(_issue("BSDL-IND-REF-001", "critical", path, f"引用 {value!r} 不存在。", target_id, "存在对象 ID", value))  # 记录悬空引用。
        return  # 结束当前引用检查。
    target_path = index[value][0]  # 读取引用目标路径。
    if not any(target_path.startswith(prefix) for prefix in prefixes):  # 检查目标集合类型。
        issues.append(_issue("BSDL-IND-REF-002", "error", path, f"引用 {value!r} 指向不允许的对象类型 {target_path}。", target_id, prefixes, target_path))  # 记录引用类型不匹配。


def _model_indices(model: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:  # 建立单个 FE 模型节点、单元与集合索引。
    nodes = {str(item.get("id")): item for item in model.get("nodes", []) if isinstance(item, dict) and item.get("id")}  # 建立 FE 节点索引。
    elements = {str(item.get("id")): item for item in model.get("elements", []) if isinstance(item, dict) and item.get("id")}  # 建立 FE 单元索引。
    sets = {str(item.get("id")): item for item in model.get("sets", []) if isinstance(item, dict) and item.get("id")}  # 建立 FE 集合索引。
    return nodes, elements, sets  # 返回三类局部索引。


def _validate_model(document: dict[str, Any], model: dict[str, Any], model_position: int, index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]]) -> dict[str, Any]:  # 验证一个工业 FE 模型。
    model_id = str(model.get("id")) if model.get("id") is not None else None  # 读取模型 ID。
    model_path = f"/finiteElementModels/{model_position}"  # 构造模型路径。
    _check_root_ref(issues, index, model.get("taskRef"), f"{model_path}/taskRef", model_id, ("/analysisTasks/",))  # 检查分析任务引用。
    _check_root_ref(issues, index, model.get("coordinateSystemRef"), f"{model_path}/coordinateSystemRef", model_id, ("/coordinateSystems/",))  # 检查模型坐标系引用。
    nodes, elements, sets = _model_indices(model)  # 建立模型局部索引。
    for node_position, node in enumerate(model.get("nodes", [])):  # 遍历 FE 节点。
        if not isinstance(node, dict):  # 跳过由 Schema 报告的非法节点。
            continue  # 继续下一节点。
        node_path = f"{model_path}/nodes/{node_position}"  # 构造节点路径。
        _add_nested_id(index, issues, node.get("id"), node_path, node)  # 把节点加入文档级索引。
        _check_root_ref(issues, index, node.get("coordinateSystemRef"), f"{node_path}/coordinateSystemRef", node.get("id"), ("/coordinateSystems/",))  # 检查节点坐标系引用。
    for element_position, element in enumerate(model.get("elements", [])):  # 遍历 FE 单元。
        if not isinstance(element, dict):  # 跳过非法单元。
            continue  # 继续下一单元。
        element_id = str(element.get("id")) if element.get("id") is not None else None  # 读取单元 ID。
        element_path = f"{model_path}/elements/{element_position}"  # 构造单元路径。
        _add_nested_id(index, issues, element.get("id"), element_path, element)  # 把单元加入文档级索引。
        element_type = str(element.get("type"))  # 读取单元类型。
        node_refs = [str(value) for value in element.get("nodeRefs", [])] if isinstance(element.get("nodeRefs"), list) else []  # 读取单元节点引用。
        required_count = expected_node_count(element_type)  # 查询标准节点数量。
        if required_count is not None and len(node_refs) != required_count:  # 检查节点数量匹配单元拓扑。
            issues.append(_issue("BSDL-FEM-001", "critical", f"{element_path}/nodeRefs", f"{element_type} 需要 {required_count} 个节点，当前为 {len(node_refs)} 个。", element_id, required_count, len(node_refs)))  # 记录拓扑节点数错误。
        for reference_position, node_ref in enumerate(node_refs):  # 遍历单元节点引用。
            if node_ref not in nodes:  # 检查节点位于同一 FE 模型。
                issues.append(_issue("BSDL-FEM-002", "critical", f"{element_path}/nodeRefs/{reference_position}", f"FE 节点引用 {node_ref!r} 不在模型 {model_id} 中。", element_id, "同模型 FE Node ID", node_ref))  # 记录悬空 FE 节点引用。
        section_ref = element.get("sectionRef")  # 读取单元截面引用。
        if element_type in BEAM_TYPES:  # 检查一维单元截面。
            _check_root_ref(issues, index, section_ref, f"{element_path}/sectionRef", element_id, ("/sections/",))  # 检查梁或桁架截面引用。
        if element_type in SHELL_TYPES:  # 检查壳单元截面。
            _check_root_ref(issues, index, section_ref, f"{element_path}/sectionRef", element_id, ("/shellSections/",))  # 检查壳截面引用。
        if element_type in SOLID_TYPES:  # 检查实体单元截面。
            _check_root_ref(issues, index, section_ref, f"{element_path}/sectionRef", element_id, ("/solidSections/",))  # 检查实体截面引用。
        material_ref = element.get("materialRef")  # 读取单元直接材料引用。
        if material_ref is not None:  # 检查是否提供直接材料覆盖。
            _check_root_ref(issues, index, material_ref, f"{element_path}/materialRef", element_id, ("/materials/",))  # 检查材料引用。
        for set_position, set_ref in enumerate(element.get("setRefs", []) if isinstance(element.get("setRefs"), list) else []):  # 遍历单元所属集合引用。
            if str(set_ref) not in sets:  # 检查集合位于同一模型。
                issues.append(_issue("BSDL-FEM-003", "error", f"{element_path}/setRefs/{set_position}", f"单元集合引用 {set_ref!r} 不在模型 {model_id} 中。", element_id, "同模型 FE Set ID", set_ref))  # 记录集合引用错误。
    for set_position, fe_set in enumerate(model.get("sets", [])):  # 遍历 FE 集合。
        if not isinstance(fe_set, dict):  # 跳过非法集合。
            continue  # 继续下一集合。
        set_id = str(fe_set.get("id")) if fe_set.get("id") is not None else None  # 读取集合 ID。
        set_path = f"{model_path}/sets/{set_position}"  # 构造集合路径。
        _add_nested_id(index, issues, fe_set.get("id"), set_path, fe_set)  # 把集合加入文档级索引。
        kind = str(fe_set.get("kind"))  # 读取集合类型。
        valid_refs = nodes if kind == "node" else elements  # 选择普通引用目标集合。
        for reference_position, reference in enumerate(fe_set.get("refs", []) if isinstance(fe_set.get("refs"), list) else []):  # 遍历集合引用。
            if str(reference) not in valid_refs:  # 检查引用属于模型对象。
                issues.append(_issue("BSDL-FEM-004", "critical", f"{set_path}/refs/{reference_position}", f"{kind} 集合引用 {reference!r} 不在模型 {model_id} 中。", set_id, "同模型对象 ID", reference))  # 记录集合成员错误。
        if kind == "surface" and not fe_set.get("faces") and not fe_set.get("refs"):  # 检查表面集合至少有节点或单元面。
            issues.append(_issue("BSDL-FEM-005", "critical", set_path, "表面集合必须包含 faces 或节点 refs。", set_id, "非空表面定义", fe_set))  # 记录空表面。
        for face_position, face in enumerate(fe_set.get("faces", []) if isinstance(fe_set.get("faces"), list) else []):  # 遍历单元面定义。
            if not isinstance(face, dict):  # 跳过非法面定义。
                continue  # 继续下一面。
            element_ref = str(face.get("elementRef"))  # 读取面所属单元。
            if element_ref not in elements:  # 检查面引用单元存在。
                issues.append(_issue("BSDL-FEM-006", "critical", f"{set_path}/faces/{face_position}/elementRef", f"表面面片引用单元 {element_ref!r} 不在模型 {model_id} 中。", set_id, "同模型 FE Element ID", element_ref))  # 记录悬空面引用。
    active_elements = sum(1 for item in elements.values() if item.get("active") is True)  # 统计初始活动单元。
    return {"id": model_id, "nodes": len(nodes), "elements": len(elements), "sets": len(sets), "activeElements": active_elements, "elementTypes": sorted({str(item.get("type")) for item in elements.values()})}  # 返回模型统计。


def _validate_contacts(document: dict[str, Any], index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]]) -> None:  # 验证 CalculiX 非线性接触契约。
    stages = {str(item.get("id")) for item in document.get("constructionStages", []) if isinstance(item, dict) and item.get("id")}  # 收集施工阶段 ID。
    aliases = {"NODE_TO_SURFACE": "NODE TO SURFACE", "SURFACE_TO_SURFACE": "SURFACE TO SURFACE", "FACE_TO_FACE": "SURFACE TO SURFACE"}  # 定义接触算法名称别名。
    requested_types: list[str] = []  # 初始化非绑定接触算法列表。
    for position, contact in enumerate(document.get("contacts", [])):  # 遍历接触对象。
        if not isinstance(contact, dict):  # 跳过非法接触项。
            continue  # 继续下一接触。
        contact_id = str(contact.get("id")) if contact.get("id") is not None else None  # 读取接触 ID。
        path = f"/contacts/{position}"  # 构造接触路径。
        for role in ["masterSurfaceRef", "slaveSurfaceRef"]:  # 遍历主从表面引用。
            reference = contact.get(role)  # 读取表面引用。
            if not isinstance(reference, str) or reference not in index or "/sets/" not in index[reference][0] or index[reference][1].get("kind") != "surface":  # 检查引用为 FE 表面集合。
                issues.append(_issue("BSDL-CONTACT-001", "critical", f"{path}/{role}", f"{role} 必须引用工业 FE 模型中的 surface 集合。", contact_id, "FE surface set ID", reference))  # 记录表面引用错误。
        master_ref = contact.get("masterSurfaceRef")  # 读取主表面引用。
        if isinstance(master_ref, str) and master_ref in index:  # 检查主表面存在。
            master = index[master_ref][1]  # 读取主表面对象。
            if master.get("kind") == "surface" and not master.get("faces"):  # 检查主表面采用单元面定义。
                issues.append(_issue("BSDL-CONTACT-002", "critical", f"{path}/masterSurfaceRef", "CalculiX 主接触面必须由单元面 faces 定义，不能仅使用节点表面。", contact_id, "含 faces 的 surface set", master_ref))  # 记录主表面定义错误。
        behavior = str(contact.get("behavior"))  # 读取接触行为。
        attributes = contact.get("attributes", {}) if isinstance(contact.get("attributes"), dict) else {}  # 读取接触扩展属性。
        if behavior != "tie":  # 检查是否需要全局接触算法。
            raw_type = str(attributes.get("calculixContactType", attributes.get("contactAlgorithm", "SURFACE TO SURFACE"))).upper().replace("-", "_")  # 读取并规范化接触算法名称。
            contact_type = aliases.get(raw_type, raw_type.replace("_", " "))  # 应用算法别名。
            requested_types.append(contact_type)  # 保存算法请求。
            if contact_type not in CALCULIX_CONTACT_TYPES:  # 检查算法属于 CalculiX 支持集合。
                issues.append(_issue("BSDL-CONTACT-008", "critical", f"{path}/attributes/calculixContactType", f"CalculiX 接触算法 {contact_type!r} 不受当前 Adapter 支持。", contact_id, sorted(CALCULIX_CONTACT_TYPES), contact_type))  # 记录未知算法。
        if behavior not in CALCULIX_CONTACT_BEHAVIORS:  # 检查行为是否已实现。
            issues.append(_issue("BSDL-CONTACT-003", "critical", f"{path}/behavior", f"CalculiX 主线尚未实现接触行为 {behavior}。", contact_id, sorted(CALCULIX_CONTACT_BEHAVIORS), behavior))  # 显式阻断未实现行为。
        normal = str(contact.get("normalBehavior"))  # 读取法向行为。
        if normal not in CALCULIX_NORMAL_BEHAVIORS:  # 检查法向行为是否已实现。
            issues.append(_issue("BSDL-CONTACT-004", "critical", f"{path}/normalBehavior", f"CalculiX 主线尚未实现法向行为 {normal}。", contact_id, sorted(CALCULIX_NORMAL_BEHAVIORS), normal))  # 显式阻断未实现法向行为。
        tangential = str(contact.get("tangentialBehavior"))  # 读取切向行为。
        if tangential not in CALCULIX_TANGENTIAL_BEHAVIORS:  # 检查切向行为是否已实现。
            issues.append(_issue("BSDL-CONTACT-005", "critical", f"{path}/tangentialBehavior", f"CalculiX 主线尚未实现切向行为 {tangential}。", contact_id, sorted(CALCULIX_TANGENTIAL_BEHAVIORS), tangential))  # 显式阻断未实现切向行为。
        if tangential == "penalty_friction" and float(contact.get("frictionCoefficient", 0.0) or 0.0) <= 0.0:  # 检查摩擦接触系数。
            issues.append(_issue("BSDL-CONTACT-006", "error", f"{path}/frictionCoefficient", "罚函数摩擦接触必须提供正摩擦系数。", contact_id, "> 0", contact.get("frictionCoefficient")))  # 记录摩擦参数错误。
        for stage_position, stage_ref in enumerate(contact.get("stageRefs", []) if isinstance(contact.get("stageRefs"), list) else []):  # 遍历接触阶段引用。
            if str(stage_ref) not in stages:  # 检查阶段存在。
                issues.append(_issue("BSDL-CONTACT-007", "critical", f"{path}/stageRefs/{stage_position}", f"接触引用的阶段 {stage_ref!r} 不存在。", contact_id, "ConstructionStage ID", stage_ref))  # 记录阶段引用错误。
    unique_types = sorted(set(requested_types))  # 统计同一文档请求的接触算法类型。
    if len(unique_types) > 1:  # 检查 CalculiX 单一 deck 的接触算法一致性。
        issues.append(_issue("BSDL-CONTACT-009", "critical", "/contacts", f"同一 CalculiX deck 不能混用多种接触算法：{unique_types}。", None, "统一 contact TYPE", unique_types))  # 记录算法混用。


def _validate_prestress(document: dict[str, Any], index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]]) -> None:  # 验证预应力系统和 CalculiX 表达前置条件。
    materials = {str(item.get("id")) for item in document.get("materials", []) if isinstance(item, dict) and item.get("id")}  # 收集材料 ID。
    stages = {str(item.get("id")) for item in document.get("constructionStages", []) if isinstance(item, dict) and item.get("id")}  # 收集阶段 ID。
    load_cases = {str(item.get("id")) for item in document.get("loadCases", []) if isinstance(item, dict) and item.get("id")}  # 收集工况 ID。
    for position, system in enumerate(document.get("prestressingSystems", [])):  # 遍历预应力系统。
        if not isinstance(system, dict):  # 跳过非法系统。
            continue  # 继续下一系统。
        system_id = str(system.get("id")) if system.get("id") is not None else None  # 读取系统 ID。
        path = f"/prestressingSystems/{position}"  # 构造系统路径。
        if str(system.get("materialRef")) not in materials:  # 检查预应力材料存在。
            issues.append(_issue("BSDL-PRESTRESS-001", "critical", f"{path}/materialRef", "预应力系统必须引用有效材料。", system_id, "Material ID", system.get("materialRef")))  # 记录材料引用错误。
        tendon_path = system.get("path", []) if isinstance(system.get("path"), list) else []  # 读取预应力路径。
        if len(tendon_path) < 2:  # 检查路径至少有两个控制点。
            issues.append(_issue("BSDL-PRESTRESS-002", "critical", f"{path}/path", "预应力路径至少需要两个控制点。", system_id, ">= 2 tendon points", len(tendon_path)))  # 记录路径错误。
        jacking_force = system.get("jackingForce")  # 读取张拉力。
        initial_stress = system.get("initialStress")  # 读取初始应力。
        if jacking_force is None and initial_stress is None:  # 检查至少提供一种张拉输入。
            issues.append(_issue("BSDL-PRESTRESS-003", "critical", path, "预应力系统必须提供 jackingForce 或 initialStress。", system_id, "张拉力或初始应力", None))  # 记录缺失张拉输入。
        representation = str(system.get("representation"))  # 读取表示方式。
        if representation not in CALCULIX_PRESTRESS_REPRESENTATIONS:  # 检查表示方式已实现。
            issues.append(_issue("BSDL-PRESTRESS-004", "critical", f"{path}/representation", f"CalculiX 主线尚未实现预应力表示 {representation}。", system_id, sorted(CALCULIX_PRESTRESS_REPRESENTATIONS), representation))  # 显式阻断未实现表示。
        for target_position, target_ref in enumerate(system.get("targetRefs", []) if isinstance(system.get("targetRefs"), list) else []):  # 遍历预应力目标引用。
            if not isinstance(target_ref, str) or target_ref not in index:  # 检查目标存在。
                issues.append(_issue("BSDL-PRESTRESS-005", "critical", f"{path}/targetRefs/{target_position}", f"预应力目标 {target_ref!r} 不存在。", system_id, "构件、FE 单元或 FE 集合 ID", target_ref))  # 记录目标引用错误。
        stage_ref = system.get("stageRef")  # 读取张拉阶段。
        if stage_ref is not None and str(stage_ref) not in stages:  # 检查阶段引用存在。
            issues.append(_issue("BSDL-PRESTRESS-006", "critical", f"{path}/stageRef", f"预应力阶段 {stage_ref!r} 不存在。", system_id, "ConstructionStage ID", stage_ref))  # 记录阶段引用错误。
        case_ref = system.get("loadCaseRef")  # 读取预应力工况。
        if case_ref is not None and str(case_ref) not in load_cases:  # 检查工况引用存在。
            issues.append(_issue("BSDL-PRESTRESS-007", "critical", f"{path}/loadCaseRef", f"预应力工况 {case_ref!r} 不存在。", system_id, "LoadCase ID", case_ref))  # 记录工况引用错误。
        if representation == "equivalent_load":  # 检查等效节点荷载路径映射。
            missing_nodes = [point_position for point_position, point in enumerate(tendon_path) if not isinstance(point, dict) or point.get("nodeRef") is None]  # 查找缺少节点引用的路径点。
            if missing_nodes:  # 检查是否存在无法映射的路径点。
                issues.append(_issue("BSDL-PRESTRESS-008", "critical", f"{path}/path", "等效荷载表示要求每个路径点提供 nodeRef。", system_id, "所有路径点包含 nodeRef", missing_nodes))  # 记录路径映射错误。
        if representation == "initial_stress" and not system.get("targetRefs"):  # 检查初始应力目标集合。
            issues.append(_issue("BSDL-PRESTRESS-009", "critical", f"{path}/targetRefs", "初始应力表示必须指定目标单元、单元集或源构件。", system_id, "非空 targetRefs", []))  # 记录缺失目标。
        if representation == "solver_native":  # 检查 CalculiX 原生预张拉截面约定。
            attributes = system.get("attributes", {}) if isinstance(system.get("attributes"), dict) else {}  # 读取原生属性。
            surface_ref = attributes.get("pretensionSurfaceRef")  # 读取预张拉截面表面引用。
            if not isinstance(surface_ref, str) or surface_ref not in index or index[surface_ref][1].get("kind") != "surface":  # 检查预张拉截面表面存在。
                issues.append(_issue("BSDL-PRESTRESS-010", "critical", f"{path}/attributes/pretensionSurfaceRef", "solver_native 表示必须通过 attributes.pretensionSurfaceRef 引用 FE surface 集合。", system_id, "FE surface set ID", surface_ref))  # 记录原生预张拉表面错误。
            control_mode = str(attributes.get("controlMode", "force"))  # 读取控制方式。
            if control_mode not in {"force", "displacement"}:  # 检查控制方式已实现。
                issues.append(_issue("BSDL-PRESTRESS-011", "critical", f"{path}/attributes/controlMode", "原生预张拉控制方式只能为 force 或 displacement。", system_id, ["force", "displacement"], control_mode))  # 记录控制方式错误。
            if control_mode == "displacement" and attributes.get("controlValue") is None:  # 检查位移控制值。
                issues.append(_issue("BSDL-PRESTRESS-012", "critical", f"{path}/attributes/controlValue", "位移控制原生预张拉必须提供 controlValue。", system_id, "数值", None))  # 记录控制值缺失。
            reference_node_ref = attributes.get("referenceFeNodeRef")  # 读取可选原生预张拉参考节点。
            if reference_node_ref is not None:  # 检查用户显式提供参考节点。
                if not isinstance(reference_node_ref, str) or reference_node_ref not in index or "/nodes/" not in index[reference_node_ref][0]:  # 检查参考节点为 FE 节点。
                    issues.append(_issue("BSDL-PRESTRESS-013", "critical", f"{path}/attributes/referenceFeNodeRef", "referenceFeNodeRef 必须引用工业 FE 模型中的 FE 节点。", system_id, "FE node ID", reference_node_ref))  # 记录参考节点错误。
                else:  # 处理存在的 FE 节点。
                    used_refs = {str(value) for model in document.get("finiteElementModels", []) if isinstance(model, dict) for element in model.get("elements", []) if isinstance(element, dict) for value in element.get("nodeRefs", [])}  # 收集参加单元连接的 FE 节点引用。
                    if reference_node_ref in used_refs:  # 检查参考节点是否同时属于结构单元。
                        issues.append(_issue("BSDL-PRESTRESS-014", "critical", f"{path}/attributes/referenceFeNodeRef", "原生预张拉参考节点必须为独立控制节点，不能参加结构单元。", system_id, "独立 FE node ID", reference_node_ref))  # 记录参考节点复用错误。


def _validate_stages(document: dict[str, Any], index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]]) -> None:  # 验证施工阶段引用和顺序。
    stages = [item for item in document.get("constructionStages", []) if isinstance(item, dict)]  # 收集有效施工阶段。
    sequences = [int(item.get("sequence")) for item in stages if isinstance(item.get("sequence"), int)]  # 收集阶段序号。
    if len(sequences) != len(set(sequences)):  # 检查阶段序号唯一。
        issues.append(_issue("BSDL-STAGE-001", "critical", "/constructionStages", "施工阶段 sequence 必须唯一。", None, "唯一正整数", sequences))  # 记录重复阶段序号。
    valid_activation_prefixes = ("/components/", "/connections/", "/finiteElementModels/")  # 定义可激活对象路径模式。
    for position, stage in enumerate(stages):  # 遍历施工阶段。
        stage_id = str(stage.get("id")) if stage.get("id") is not None else None  # 读取阶段 ID。
        path = f"/constructionStages/{position}"  # 构造阶段路径。
        for field in ["activateRefs", "deactivateRefs"]:  # 遍历激活和停用引用。
            for reference_position, reference in enumerate(stage.get(field, []) if isinstance(stage.get(field), list) else []):  # 遍历对象引用。
                if not isinstance(reference, str) or reference not in index:  # 检查对象存在。
                    issues.append(_issue("BSDL-STAGE-002", "critical", f"{path}/{field}/{reference_position}", f"阶段对象引用 {reference!r} 不存在。", stage_id, "构件、连接、FE 单元或 FE 集合 ID", reference))  # 记录悬空激活引用。
                elif not any(token in index[reference][0] for token in valid_activation_prefixes):  # 检查目标可参与阶段激活。
                    issues.append(_issue("BSDL-STAGE-003", "error", f"{path}/{field}/{reference_position}", f"对象 {reference!r} 不支持阶段激活或停用。", stage_id, valid_activation_prefixes, index[reference][0]))  # 记录目标类型错误。
        field_prefixes = {"loadCaseRefs": ("/loadCases/",), "prestressRefs": ("/prestressingSystems/",), "contactRefs": ("/contacts/",)}  # 定义阶段关联引用类型。
        for field, prefixes in field_prefixes.items():  # 遍历阶段关联集合。
            for reference_position, reference in enumerate(stage.get(field, []) if isinstance(stage.get(field), list) else []):  # 遍历关联引用。
                _check_root_ref(issues, index, reference, f"{path}/{field}/{reference_position}", stage_id, prefixes)  # 检查阶段关联引用。


def _validate_solver_and_results(document: dict[str, Any], index: dict[str, tuple[str, dict[str, Any]]], issues: list[dict[str, Any]]) -> None:  # 验证 CalculiX 求解计划、能力档案、结果和转换报告。
    for position, profile in enumerate(document.get("solverProfiles", [])):  # 遍历求解器能力档案。
        if not isinstance(profile, dict):  # 跳过非法档案。
            continue  # 继续下一档案。
        if profile.get("solver") != "calculix":  # 检查工业主线求解器。
            issues.append(_issue("BSDL-SOLVER-001", "critical", f"/solverProfiles/{position}/solver", "当前工业交付只维护 CalculiX 求解器档案。", profile.get("id"), "calculix", profile.get("solver")))  # 阻断其他求解器档案冒充受支持能力。
    for position, plan in enumerate(document.get("solverPlans", [])):  # 遍历求解计划。
        if not isinstance(plan, dict):  # 跳过非法计划。
            continue  # 继续下一计划。
        plan_id = str(plan.get("id")) if plan.get("id") is not None else None  # 读取计划 ID。
        path = f"/solverPlans/{position}"  # 构造计划路径。
        if plan.get("solver") != "calculix":  # 检查求解计划路由。
            issues.append(_issue("BSDL-SOLVER-002", "critical", f"{path}/solver", "BSDL Industrial 1.0 的工业求解计划必须使用 CalculiX。", plan_id, "calculix", plan.get("solver")))  # 阻断其他求解器。
        _check_root_ref(issues, index, plan.get("solverProfileRef"), f"{path}/solverProfileRef", plan_id, ("/solverProfiles/",), True)  # 检查求解器档案引用。
        _check_root_ref(issues, index, plan.get("finiteElementModelRef"), f"{path}/finiteElementModelRef", plan_id, ("/finiteElementModels/",), True)  # 检查 FE 模型引用。
        for stage_position, stage_ref in enumerate(plan.get("stageRefs", []) if isinstance(plan.get("stageRefs"), list) else []):  # 遍历计划阶段引用。
            _check_root_ref(issues, index, stage_ref, f"{path}/stageRefs/{stage_position}", plan_id, ("/constructionStages/",))  # 检查阶段引用。
    for position, result_set in enumerate(document.get("resultSets", [])):  # 遍历结果集。
        if not isinstance(result_set, dict):  # 跳过非法结果集。
            continue  # 继续下一结果集。
        result_id = str(result_set.get("id")) if result_set.get("id") is not None else None  # 读取结果集 ID。
        path = f"/resultSets/{position}"  # 构造结果集路径。
        _check_root_ref(issues, index, result_set.get("taskRef"), f"{path}/taskRef", result_id, ("/analysisTasks/",))  # 检查任务引用。
        _check_root_ref(issues, index, result_set.get("loadCaseRef"), f"{path}/loadCaseRef", result_id, ("/loadCases/",), True)  # 检查工况引用。
        _check_root_ref(issues, index, result_set.get("stageRef"), f"{path}/stageRef", result_id, ("/constructionStages/",), True)  # 检查阶段引用。
        for artifact_position, artifact_ref in enumerate(result_set.get("artifactRefs", []) if isinstance(result_set.get("artifactRefs"), list) else []):  # 遍历结果产物引用。
            _check_root_ref(issues, index, artifact_ref, f"{path}/artifactRefs/{artifact_position}", result_id, ("/artifacts/",))  # 检查结果产物引用。
    for position, mapping in enumerate(document.get("externalMappings", [])):  # 遍历外部映射。
        if not isinstance(mapping, dict):  # 跳过非法映射。
            continue  # 继续下一映射。
        _check_root_ref(issues, index, mapping.get("targetRef"), f"/externalMappings/{position}/targetRef", mapping.get("id"), tuple(f"/{value}/" for value in ROOT_COLLECTIONS) + ("/finiteElementModels/", "/project"))  # 检查映射目标存在。
    for position, report in enumerate(document.get("conversionReports", [])):  # 遍历转换报告。
        if not isinstance(report, dict):  # 跳过非法报告。
            continue  # 继续下一报告。
        losses = report.get("losses", []) if isinstance(report.get("losses"), list) else []  # 读取转换损失。
        critical = [item for item in losses if isinstance(item, dict) and (item.get("severity") in {"error", "critical"} or item.get("category") == "blocked")]  # 查找阻断损失。
        if critical and report.get("blocked") is not True:  # 检查阻断标志与损失一致。
            issues.append(_issue("BSDL-CONVERSION-001", "critical", f"/conversionReports/{position}/blocked", "转换报告存在关键损失时 blocked 必须为 true。", report.get("id"), True, report.get("blocked")))  # 阻止静默丢义。


def validate_industrial(document: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # 执行工业扩展完整语义验证。
    issues: list[dict[str, Any]] = []  # 初始化问题列表。
    index, root_issues = _root_index(document)  # 建立根对象索引。
    issues.extend(root_issues)  # 合并根对象 ID 问题。
    for position, section in enumerate(document.get("shellSections", [])):  # 遍历壳截面。
        if isinstance(section, dict):  # 检查截面结构。
            _check_root_ref(issues, index, section.get("materialRef"), f"/shellSections/{position}/materialRef", section.get("id"), ("/materials/",))  # 检查壳截面材料引用。
            _check_root_ref(issues, index, section.get("orientationRef"), f"/shellSections/{position}/orientationRef", section.get("id"), ("/coordinateSystems/",), True)  # 检查壳截面方向引用。
    for position, section in enumerate(document.get("solidSections", [])):  # 遍历实体截面。
        if isinstance(section, dict):  # 检查截面结构。
            _check_root_ref(issues, index, section.get("materialRef"), f"/solidSections/{position}/materialRef", section.get("id"), ("/materials/",))  # 检查实体截面材料引用。
            _check_root_ref(issues, index, section.get("orientationRef"), f"/solidSections/{position}/orientationRef", section.get("id"), ("/coordinateSystems/",), True)  # 检查实体截面方向引用。
    model_stats: list[dict[str, Any]] = []  # 初始化 FE 模型统计。
    for position, model in enumerate(document.get("finiteElementModels", [])):  # 遍历工业 FE 模型。
        if isinstance(model, dict):  # 检查模型结构。
            _add_nested_id(index, issues, model.get("id"), f"/finiteElementModels/{position}", model)  # 把 FE 模型 ID 加入统一索引。
            model_stats.append(_validate_model(document, model, position, index, issues))  # 验证模型并保存统计。
    _validate_contacts(document, index, issues)  # 验证非线性接触。
    _validate_prestress(document, index, issues)  # 验证预应力系统。
    _validate_stages(document, index, issues)  # 验证施工阶段。
    _validate_solver_and_results(document, index, issues)  # 验证求解计划、结果与转换报告。
    stats = {"industrialEntities": len(index), "finiteElementModels": len(model_stats), "finiteElementNodes": sum(item["nodes"] for item in model_stats), "finiteElementElements": sum(item["elements"] for item in model_stats), "finiteElementSets": sum(item["sets"] for item in model_stats), "elementTypes": sorted({value for item in model_stats for value in item["elementTypes"]}), "contacts": len(document.get("contacts", [])), "prestressingSystems": len(document.get("prestressingSystems", [])), "constructionStages": len(document.get("constructionStages", [])), "codeCheckPlans": len(document.get("codeCheckPlans", [])), "resultSets": len(document.get("resultSets", [])), "models": model_stats}  # 汇总工业验证统计。
    return issues, stats  # 返回工业问题和统计。

"""从 BSDL 文档提取节点、构件和 FEA 响应特征。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供角度和距离计算。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供向量运算和统计。


def _length(start: list[float], end: list[float]) -> float:  # 计算两个三维点之间的距离。
    return float(np.linalg.norm(np.asarray(end, dtype=float) - np.asarray(start, dtype=float)))  # 返回欧氏距离。


def _angle(first: np.ndarray, second: np.ndarray) -> float:  # 计算两个方向向量的夹角弧度。
    first_norm = float(np.linalg.norm(first))  # 计算第一个向量范数。
    second_norm = float(np.linalg.norm(second))  # 计算第二个向量范数。
    if first_norm <= 1e-14 or second_norm <= 1e-14:  # 检查退化方向。
        return 0.0  # 对退化向量返回零角度。
    cosine = float(np.dot(first, second) / (first_norm * second_norm))  # 计算夹角余弦。
    cosine = max(-1.0, min(1.0, cosine))  # 把余弦限制到数值安全范围。
    return float(math.acos(abs(cosine)))  # 使用无向杆件夹角并返回弧度。


def extract_features(document: dict[str, Any], fea_result: dict[str, Any] | None = None) -> dict[str, Any]:  # 提取统一结构特征和局部响应特征。
    nodes = {node["id"]: node for node in document.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)}  # 建立节点索引。
    components = {component["id"]: component for component in document.get("components", []) if isinstance(component, dict) and isinstance(component.get("id"), str)}  # 建立构件索引。
    sections = {section["id"]: section for section in document.get("sections", []) if isinstance(section, dict) and isinstance(section.get("id"), str)}  # 建立截面索引。
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}  # 初始化节点到线构件的邻接表。
    component_features: dict[str, dict[str, Any]] = {}  # 初始化构件特征表。
    lengths: list[float] = []  # 初始化活跃线构件长度集合。
    for component_id, component in components.items():  # 遍历构件。
        node_refs = component.get("nodeRefs", [])  # 读取构件节点引用。
        if component.get("topology") == "line" and len(node_refs) == 2 and node_refs[0] in nodes and node_refs[1] in nodes:  # 处理有效线构件。
            start = nodes[node_refs[0]]["position"]  # 读取构件起点。
            end = nodes[node_refs[1]]["position"]  # 读取构件终点。
            length = _length(start, end)  # 计算构件长度。
            direction = (np.asarray(end, dtype=float) - np.asarray(start, dtype=float)) / max(length, 1e-14)  # 计算构件单位方向。
            midpoint = (np.asarray(start, dtype=float) + np.asarray(end, dtype=float)) * 0.5  # 计算构件中点。
            section = sections.get(component.get("sectionRef"), {})  # 查找构件截面。
            component_features[component_id] = {"id": component_id, "length": length, "direction": [float(value) for value in direction], "midpoint": [float(value) for value in midpoint], "nodeRefs": list(node_refs), "category": component.get("category"), "materialRef": component.get("materialRef"), "sectionRef": component.get("sectionRef"), "area": float(section.get("area", 0.0) or 0.0), "iy": float(section.get("iy", 0.0) or 0.0), "iz": float(section.get("iz", 0.0) or 0.0), "active": bool(component.get("analysis", {}).get("active")), "elementType": component.get("analysis", {}).get("elementType")}  # 保存线构件结构特征。
            if component.get("analysis", {}).get("active") is True:  # 仅用活跃构件估计全局尺度。
                lengths.append(length)  # 保存活跃构件长度。
            adjacency[node_refs[0]].append(component_id)  # 把构件加入起点邻接表。
            adjacency[node_refs[1]].append(component_id)  # 把构件加入终点邻接表。
    median_length = float(np.median(lengths)) if lengths else 1.0  # 计算中位构件长度。
    minimum_length = min(lengths) if lengths else 1.0  # 计算最小构件长度。
    maximum_length = max(lengths) if lengths else 1.0  # 计算最大构件长度。
    node_features: dict[str, dict[str, Any]] = {}  # 初始化节点局部特征表。
    for node_id, node in nodes.items():  # 遍历节点。
        incident_refs = adjacency.get(node_id, [])  # 读取节点相邻构件。
        directions: list[np.ndarray] = []  # 初始化相邻构件方向列表。
        areas: list[float] = []  # 初始化相邻构件面积列表。
        materials: set[str] = set()  # 初始化相邻材料集合。
        categories: set[str] = set()  # 初始化相邻构件类别集合。
        incident_lengths: list[float] = []  # 初始化相邻构件长度列表。
        position = np.asarray(node["position"], dtype=float)  # 读取节点位置。
        for component_ref in incident_refs:  # 遍历相邻构件。
            feature = component_features.get(component_ref)  # 读取构件特征。
            if not feature:  # 跳过缺失特征。
                continue  # 继续检查下一构件。
            first_ref, second_ref = feature["nodeRefs"]  # 解包构件端点。
            other_ref = second_ref if first_ref == node_id else first_ref  # 获取另一端节点。
            other_position = np.asarray(nodes[other_ref]["position"], dtype=float)  # 读取另一端坐标。
            directions.append(other_position - position)  # 保存从当前节点指向另一端的方向。
            areas.append(float(feature.get("area", 0.0)))  # 保存截面面积。
            incident_lengths.append(float(feature.get("length", 0.0)))  # 保存构件长度。
            if feature.get("materialRef"):  # 检查材料引用存在。
                materials.add(str(feature["materialRef"]))  # 加入材料集合。
            if feature.get("category"):  # 检查构件类别存在。
                categories.add(str(feature["category"]))  # 加入类别集合。
        angles: list[float] = []  # 初始化两两夹角集合。
        for first_index in range(len(directions)):  # 遍历第一个相邻方向。
            for second_index in range(first_index + 1, len(directions)):  # 遍历第二个相邻方向。
                angles.append(_angle(directions[first_index], directions[second_index]))  # 保存无向夹角。
        positive_areas = [value for value in areas if value > 0.0]  # 筛除未知或零面积。
        area_ratio = max(positive_areas) / min(positive_areas) if positive_areas else 1.0  # 计算最大最小面积比。
        constraints = node.get("constraints", {})  # 读取节点约束。
        constrained_dofs = [name for name, value in constraints.items() if value is True] if isinstance(constraints, dict) else []  # 收集约束自由度名称。
        node_features[node_id] = {"id": node_id, "position": list(node["position"]), "degree": len(incident_refs), "incidentRefs": incident_refs, "incidentCategories": sorted(categories), "materialCount": len(materials), "sectionAreaRatio": area_ratio, "minAngle": min(angles) if angles else None, "maxAngle": max(angles) if angles else None, "meanAngle": float(np.mean(angles)) if angles else None, "constraints": constrained_dofs, "isSupport": "support" in node.get("roles", []) or bool(constrained_dofs), "roles": list(node.get("roles", [])), "localScale": min(incident_lengths) if incident_lengths else minimum_length}  # 保存节点局部特征。
    response_by_component: dict[str, dict[str, float]] = {}  # 初始化构件响应特征。
    response_by_node: dict[str, dict[str, float]] = {}  # 初始化节点响应特征。
    if isinstance(fea_result, dict):  # 检查是否提供 FEA 结果。
        for component_ref, metrics in fea_result.get("componentMetrics", {}).items():  # 遍历构件响应汇总。
            if isinstance(metrics, dict):  # 只处理字典指标。
                response_by_component[str(component_ref)] = {key: float(value) for key, value in metrics.items() if isinstance(value, (int, float))}  # 转换为稳定浮点指标。
        for result in fea_result.get("nodeResults", []):  # 遍历节点结果。
            if not isinstance(result, dict):  # 跳过非法项。
                continue  # 继续检查下一结果。
            original_ref = result.get("originalNodeRef") or result.get("nodeRef")  # 优先回映到原始结构节点。
            if original_ref in nodes:  # 仅保存原始节点响应。
                displacement = result.get("displacement", [0.0] * 6)  # 读取六自由度位移。
                response_by_node[str(original_ref)] = {"translationMagnitude": float(result.get("translationMagnitude", 0.0)), "verticalDisplacement": abs(float(displacement[2])) if len(displacement) >= 3 else 0.0}  # 保存节点位移特征。
    return {"global": {"medianLength": median_length, "minimumLength": minimum_length, "maximumLength": maximum_length, "activeLineComponentCount": len(lengths)}, "nodes": node_features, "components": component_features, "responseByComponent": response_by_component, "responseByNode": response_by_node}  # 返回完整特征包。

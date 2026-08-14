"""根据 BSDL MeshPolicy 对空间线构件执行确定性自适应分段。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供三角函数和向上取整。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供向量和矩阵运算。
from ..utils import slug  # 复用安全标识转换。


def _rotation_matrix(rotation: list[float]) -> np.ndarray:  # 根据 XYZ 欧拉角构造旋转矩阵。
    rx, ry, rz = (float(value) for value in rotation)  # 解包三个旋转角。
    cx, sx = math.cos(rx), math.sin(rx)  # 计算 X 轴旋转三角函数。
    cy, sy = math.cos(ry), math.sin(ry)  # 计算 Y 轴旋转三角函数。
    cz, sz = math.cos(rz), math.sin(rz)  # 计算 Z 轴旋转三角函数。
    matrix_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=float)  # 构造 X 轴旋转矩阵。
    matrix_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=float)  # 构造 Y 轴旋转矩阵。
    matrix_z = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=float)  # 构造 Z 轴旋转矩阵。
    return matrix_z @ matrix_y @ matrix_x  # 按 XYZ 内禀顺序组合旋转。


def point_in_region(point: list[float] | np.ndarray, region: dict[str, Any], tolerance: float = 1e-9) -> bool:  # 判断三维点是否位于区域内部。
    geometry = region.get("geometry", {})  # 读取区域几何。
    kind = geometry.get("kind")  # 读取区域类型。
    vector = np.asarray(point, dtype=float)  # 把输入点转换为数值向量。
    if kind == "sphere":  # 处理球形区域。
        center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取球心。
        radius = float(geometry.get("radius", 0.0))  # 读取球半径。
        return float(np.linalg.norm(vector - center)) <= radius + tolerance  # 判断点到球心距离。
    if kind == "box":  # 处理旋转包围盒。
        center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取包围盒中心。
        size = np.asarray(geometry.get("size", [0.0, 0.0, 0.0]), dtype=float)  # 读取包围盒尺寸。
        rotation = geometry.get("rotation", [0.0, 0.0, 0.0])  # 读取欧拉角。
        local = _rotation_matrix(rotation).T @ (vector - center)  # 把全局点转换到区域局部坐标。
        return bool(np.all(np.abs(local) <= size * 0.5 + tolerance))  # 检查三个局部坐标范围。
    return False  # 未知区域几何不参与网格判定。


def _line_box_interval(start: np.ndarray, end: np.ndarray, region: dict[str, Any]) -> tuple[float, float] | None:  # 计算线段与旋转包围盒相交参数区间。
    geometry = region.get("geometry", {})  # 读取区域几何。
    if geometry.get("kind") != "box":  # 只对包围盒执行精确区间计算。
        return None  # 其他区域由中点判定处理。
    center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取包围盒中心。
    half_size = np.asarray(geometry.get("size", [0.0, 0.0, 0.0]), dtype=float) * 0.5  # 计算半尺寸。
    rotation = _rotation_matrix(geometry.get("rotation", [0.0, 0.0, 0.0]))  # 构造区域旋转矩阵。
    local_start = rotation.T @ (start - center)  # 把线段起点转换到局部坐标。
    local_end = rotation.T @ (end - center)  # 把线段终点转换到局部坐标。
    direction = local_end - local_start  # 计算局部线段方向。
    lower = 0.0  # 初始化进入参数。
    upper = 1.0  # 初始化离开参数。
    for axis in range(3):  # 对三个局部轴执行 slab 相交测试。
        if abs(float(direction[axis])) < 1e-14:  # 处理与当前平面平行的线段。
            if local_start[axis] < -half_size[axis] or local_start[axis] > half_size[axis]:  # 检查平行线段是否位于盒外。
                return None  # 平行且盒外表示无交集。
            continue  # 平行且位于 slab 内则检查下一轴。
        first = (-half_size[axis] - local_start[axis]) / direction[axis]  # 计算与负侧平面交点参数。
        second = (half_size[axis] - local_start[axis]) / direction[axis]  # 计算与正侧平面交点参数。
        near = min(float(first), float(second))  # 获取当前轴进入参数。
        far = max(float(first), float(second))  # 获取当前轴离开参数。
        lower = max(lower, near)  # 更新总进入参数。
        upper = min(upper, far)  # 更新总离开参数。
        if lower > upper:  # 检查参数区间是否为空。
            return None  # 区间为空表示线段与盒不相交。
    if upper < 0.0 or lower > 1.0:  # 检查相交区间是否在线段外。
        return None  # 线段外相交不计入。
    return max(0.0, lower), min(1.0, upper)  # 返回截断到线段范围的参数区间。


def _line_sphere_interval(start: np.ndarray, end: np.ndarray, region: dict[str, Any]) -> tuple[float, float] | None:  # 计算线段与球形区域相交参数区间。
    geometry = region.get("geometry", {})  # 读取区域几何。
    if geometry.get("kind") != "sphere":  # 只处理球形区域。
        return None  # 其他区域返回空。
    center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取球心。
    radius = float(geometry.get("radius", 0.0))  # 读取球半径。
    direction = end - start  # 计算线段方向。
    offset = start - center  # 计算起点相对球心向量。
    a = float(np.dot(direction, direction))  # 计算二次方程二次项。
    b = 2.0 * float(np.dot(offset, direction))  # 计算二次方程一次项。
    c = float(np.dot(offset, offset) - radius * radius)  # 计算二次方程常数项。
    discriminant = b * b - 4.0 * a * c  # 计算判别式。
    if a <= 1e-20 or discriminant < 0.0:  # 检查退化线段或无实根。
        return None  # 无有效交区间。
    root = math.sqrt(discriminant)  # 计算判别式平方根。
    first = (-b - root) / (2.0 * a)  # 计算进入参数。
    second = (-b + root) / (2.0 * a)  # 计算离开参数。
    lower = max(0.0, min(first, second))  # 截断进入参数。
    upper = min(1.0, max(first, second))  # 截断离开参数。
    if lower > upper:  # 检查截断区间是否为空。
        return None  # 空区间表示线段外相交。
    return lower, upper  # 返回有效相交参数区间。


def _applicable_regions(component: dict[str, Any], regions: dict[str, dict[str, Any]], policy: dict[str, Any]) -> list[tuple[dict[str, Any], float, int]]:  # 收集对构件生效的区域规则。
    applicable: list[tuple[dict[str, Any], float, int]] = []  # 初始化生效区域列表。
    component_id = component.get("id")  # 读取构件 ID。
    node_refs = set(component.get("nodeRefs", []))  # 收集构件端点节点。
    for rule in policy.get("regionRules", []):  # 遍历策略区域规则。
        if not isinstance(rule, dict):  # 跳过非法规则。
            continue  # 继续检查下一规则。
        region = regions.get(rule.get("regionRef"))  # 查找规则引用区域。
        if not isinstance(region, dict) or region.get("active") is not True or region.get("status") == "rejected":  # 跳过不存在、不活跃或已拒绝区域。
            continue  # 继续检查下一规则。
        targets = set(region.get("targetRefs", []))  # 读取区域目标对象集合。
        if targets and component_id not in targets and not node_refs.intersection(targets):  # 检查区域是否明确指向当前构件或端点。
            continue  # 明确指向其他对象的区域不生效。
        target_size = float(rule.get("targetSize", region.get("targetSize", policy.get("baseSize", 1.0))))  # 读取规则目标尺寸。
        priority = int(rule.get("priority", 0))  # 读取规则优先级。
        applicable.append((region, target_size, priority))  # 保存生效区域及参数。
    return applicable  # 返回构件生效区域。


def mesh_document(document: dict[str, Any], mesh_policy_id: str | None = None) -> dict[str, Any]:  # 根据 BSDL 文档生成空间梁分析网格。
    nodes = {node["id"]: node for node in document.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)}  # 建立原始节点索引。
    regions = {region["id"]: region for region in document.get("regions", []) if isinstance(region, dict) and isinstance(region.get("id"), str)}  # 建立区域索引。
    policies = [policy for policy in document.get("meshPolicies", []) if isinstance(policy, dict)]  # 收集可用网格策略。
    if mesh_policy_id is None:  # 处理未显式指定策略的情况。
        policy = policies[0] if policies else {"id": "mesh.implicit", "baseSize": 1.0, "regionRules": [], "elementFamily": "frame"}  # 选择首个策略或隐式默认策略。
    else:  # 处理显式指定策略。
        matches = [item for item in policies if item.get("id") == mesh_policy_id]  # 查找同 ID 策略。
        if not matches:  # 检查策略是否存在。
            raise ValueError(f"MeshPolicy 不存在：{mesh_policy_id}")  # 对缺失策略给出明确错误。
        policy = matches[0]  # 使用匹配策略。
    base_size = float(policy.get("baseSize", 1.0))  # 读取全局基准尺寸。
    if base_size <= 0.0:  # 检查基准尺寸为正。
        raise ValueError("MeshPolicy.baseSize 必须大于零。")  # 阻止非法网格策略。
    mesh_nodes: dict[str, dict[str, Any]] = {}  # 初始化网格节点索引。
    mesh_elements: list[dict[str, Any]] = []  # 初始化网格单元列表。
    mappings: list[dict[str, Any]] = []  # 初始化构件到网格映射。
    warnings: list[str] = []  # 初始化网格警告列表。
    for node_id, node in nodes.items():  # 先把所有原始结构节点复制到网格。
        mesh_nodes[node_id] = {"id": node_id, "position": [float(value) for value in node["position"]], "originalNodeRef": node_id, "constraints": dict(node.get("constraints", {})), "roles": list(node.get("roles", []))}  # 保留约束和角色。
    for component in document.get("components", []):  # 遍历全部构件。
        if not isinstance(component, dict):  # 跳过非法构件。
            continue  # 继续检查下一构件。
        analysis = component.get("analysis", {})  # 读取构件分析属性。
        if component.get("topology") != "line" or not isinstance(analysis, dict) or analysis.get("active") is not True or analysis.get("elementType") != "frame3d":  # 仅离散活跃空间梁构件。
            continue  # 跳过非目标构件。
        component_id = str(component.get("id"))  # 读取构件 ID。
        node_refs = component.get("nodeRefs", [])  # 读取端点引用。
        if len(node_refs) != 2 or node_refs[0] not in nodes or node_refs[1] not in nodes:  # 检查端点完整性。
            raise ValueError(f"构件 {component_id} 缺少两个有效节点。")  # 阻止无法离散的构件。
        start = np.asarray(nodes[node_refs[0]]["position"], dtype=float)  # 读取起点坐标。
        end = np.asarray(nodes[node_refs[1]]["position"], dtype=float)  # 读取终点坐标。
        length = float(np.linalg.norm(end - start))  # 计算构件长度。
        if length <= 1e-12:  # 检查零长度构件。
            raise ValueError(f"构件 {component_id} 长度为零。")  # 阻止零长度单元。
        applicable = _applicable_regions(component, regions, policy)  # 收集对当前构件生效的区域。
        breakpoints = {0.0, 1.0}  # 初始化参数断点集合。
        intervals: list[tuple[float, float, dict[str, Any], float, int]] = []  # 初始化区域相交区间。
        for region, target_size, priority in applicable:  # 遍历生效区域。
            interval = _line_box_interval(start, end, region) or _line_sphere_interval(start, end, region)  # 计算线段与区域相交区间。
            if interval is None:  # 跳过无交集区域。
                continue  # 继续检查下一区域。
            lower, upper = interval  # 解包相交区间。
            breakpoints.add(round(lower, 12))  # 加入进入断点并控制浮点噪声。
            breakpoints.add(round(upper, 12))  # 加入离开断点并控制浮点噪声。
            intervals.append((lower, upper, region, target_size, priority))  # 保存区域区间和参数。
        ordered_breakpoints = sorted(breakpoints)  # 排序所有参数断点。
        component_element_ids: list[str] = []  # 初始化当前构件网格单元 ID 列表。
        component_node_ids: list[str] = []  # 初始化当前构件网格节点 ID 列表。
        last_node_id = str(node_refs[0])  # 使用原始起点作为首个网格节点。
        component_node_ids.append(last_node_id)  # 保存首个节点 ID。
        running_index = 0  # 初始化内部网格节点与单元编号。
        for interval_index in range(len(ordered_breakpoints) - 1):  # 遍历区域分段区间。
            lower = ordered_breakpoints[interval_index]  # 读取区间起点参数。
            upper = ordered_breakpoints[interval_index + 1]  # 读取区间终点参数。
            if upper - lower <= 1e-12:  # 跳过零长度参数区间。
                continue  # 继续检查下一区间。
            midpoint = (lower + upper) * 0.5  # 计算区间中点参数。
            midpoint_point = start + midpoint * (end - start)  # 计算区间中点坐标。
            active_rules = [(target_size, priority, region) for enter, leave, region, target_size, priority in intervals if enter - 1e-12 <= midpoint <= leave + 1e-12 and point_in_region(midpoint_point, region)]  # 收集中点处生效的区域规则。
            desired_size = min([base_size] + [item[0] for item in active_rules])  # 取全局与局部规则中的最小尺寸。
            physical_length = (upper - lower) * length  # 计算当前参数区间实际长度。
            subdivision_count = max(1, int(math.ceil(physical_length / desired_size)))  # 按目标尺寸确定子区间数。
            for subdivision in range(1, subdivision_count + 1):  # 逐个生成子单元。
                local_fraction = subdivision / subdivision_count  # 计算子单元终点在当前区间的比例。
                parameter = lower + (upper - lower) * local_fraction  # 计算子单元终点全局参数。
                is_component_end = interval_index == len(ordered_breakpoints) - 2 and subdivision == subdivision_count  # 判断是否到达原构件终点。
                if is_component_end:  # 处理原构件终点。
                    next_node_id = str(node_refs[1])  # 复用原始终点节点 ID。
                else:  # 处理内部网格节点。
                    running_index += 1  # 增加内部节点编号。
                    next_node_id = f"mnode.{slug(component_id)}.{running_index}"  # 生成稳定内部节点 ID。
                    position = start + parameter * (end - start)  # 计算内部节点坐标。
                    mesh_nodes[next_node_id] = {"id": next_node_id, "position": [float(value) for value in position], "originalNodeRef": None, "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "roles": ["mesh"]}  # 保存内部节点。
                element_id = f"elem.{slug(component_id)}.{len(component_element_ids) + 1}"  # 生成稳定单元 ID。
                element_length = float(np.linalg.norm(np.asarray(mesh_nodes[next_node_id]["position"], dtype=float) - np.asarray(mesh_nodes[last_node_id]["position"], dtype=float)))  # 计算子单元长度。
                mesh_elements.append({"id": element_id, "componentRef": component_id, "nodeRefs": [last_node_id, next_node_id], "materialRef": component.get("materialRef"), "sectionRef": component.get("sectionRef"), "localUp": analysis.get("localUp"), "length": element_length, "regionRefs": [str(item[2].get("id")) for item in active_rules]})  # 保存梁单元及区域来源。
                component_element_ids.append(element_id)  # 记录当前构件单元 ID。
                if next_node_id != component_node_ids[-1]:  # 避免重复保存相邻节点。
                    component_node_ids.append(next_node_id)  # 保存网格节点 ID。
                last_node_id = next_node_id  # 更新下一子单元起点。
        mappings.append({"componentRef": component_id, "meshNodeRefs": component_node_ids, "elementRefs": component_element_ids})  # 保存构件到网格映射。
    if not mesh_elements:  # 检查是否生成任何梁单元。
        warnings.append("未找到可离散的 active frame3d 构件。")  # 添加空网格警告。
    lengths = [element["length"] for element in mesh_elements]  # 收集全部单元长度。
    stats = {"nodeCount": len(mesh_nodes), "elementCount": len(mesh_elements), "componentCount": len(mappings), "minElementLength": min(lengths) if lengths else None, "maxElementLength": max(lengths) if lengths else None, "meanElementLength": sum(lengths) / len(lengths) if lengths else None, "meshPolicyRef": policy.get("id"), "baseSize": base_size}  # 汇总网格统计。
    return {"meshPolicyRef": policy.get("id"), "nodes": list(mesh_nodes.values()), "elements": mesh_elements, "mappings": mappings, "stats": stats, "warnings": warnings}  # 返回完整网格对象。

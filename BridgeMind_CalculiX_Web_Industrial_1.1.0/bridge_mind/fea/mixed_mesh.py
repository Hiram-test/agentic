"""把 BSDL 结构对象确定性离散为梁、壳和实体混合有限元模型。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供向上取整和三角函数。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供三维向量与网格质量计算。
from .mesher import mesh_document  # 复用经过测试的空间梁分段器。
from ..utils import slug  # 复用安全 ID 转换工具。


def _rotation_matrix(rotation: list[float]) -> np.ndarray:  # 根据 XYZ 欧拉角构造旋转矩阵。
    rx, ry, rz = (float(value) for value in rotation)  # 解包三个旋转角。
    cx, sx = math.cos(rx), math.sin(rx)  # 计算 X 轴旋转三角函数。
    cy, sy = math.cos(ry), math.sin(ry)  # 计算 Y 轴旋转三角函数。
    cz, sz = math.cos(rz), math.sin(rz)  # 计算 Z 轴旋转三角函数。
    matrix_x = np.asarray([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=float)  # 构造 X 轴旋转矩阵。
    matrix_y = np.asarray([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=float)  # 构造 Y 轴旋转矩阵。
    matrix_z = np.asarray([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=float)  # 构造 Z 轴旋转矩阵。
    return matrix_z @ matrix_y @ matrix_x  # 返回组合旋转矩阵。


def _select_policy(document: dict[str, Any], mesh_policy_id: str | None) -> dict[str, Any]:  # 选择显式或默认网格策略。
    policies = [item for item in document.get("meshPolicies", []) if isinstance(item, dict)]  # 收集有效网格策略。
    if mesh_policy_id is None:  # 处理未指定策略。
        return policies[0] if policies else {"id": "mesh.implicit", "baseSize": 1.0, "regionRules": [], "budget": {"maxElements": 100000, "maxIterations": 0}}  # 返回首个策略或隐式默认策略。
    for policy in policies:  # 遍历策略查找指定 ID。
        if policy.get("id") == mesh_policy_id:  # 检查策略 ID 匹配。
            return policy  # 返回匹配策略。
    raise ValueError(f"MeshPolicy 不存在：{mesh_policy_id}")  # 对缺失策略给出明确错误。


def _component_target_size(component: dict[str, Any], document: dict[str, Any], policy: dict[str, Any]) -> float:  # 计算整个构件的保守目标尺寸。
    base_size = float(policy.get("baseSize", 1.0))  # 读取全局基准尺寸。
    regions = {item.get("id"): item for item in document.get("regions", []) if isinstance(item, dict)}  # 建立区域索引。
    component_id = str(component.get("id"))  # 读取构件 ID。
    node_refs = set(component.get("nodeRefs", []))  # 收集构件节点引用。
    sizes = [base_size]  # 使用全局尺寸初始化候选列表。
    for rule in policy.get("regionRules", []):  # 遍历区域规则。
        if not isinstance(rule, dict):  # 跳过非法规则。
            continue  # 继续检查下一规则。
        region = regions.get(rule.get("regionRef"))  # 查找规则区域。
        if not isinstance(region, dict) or region.get("active") is not True or region.get("status") == "rejected":  # 跳过无效区域。
            continue  # 继续检查下一规则。
        targets = set(region.get("targetRefs", []))  # 读取区域目标引用。
        if targets and component_id not in targets and not node_refs.intersection(targets):  # 检查区域是否作用于当前构件。
            continue  # 跳过指向其他对象的区域。
        target_size = float(rule.get("targetSize", region.get("targetSize", base_size)))  # 读取局部目标尺寸。
        if target_size > 0.0:  # 检查局部尺寸有效性。
            sizes.append(target_size)  # 加入候选尺寸。
    return min(sizes)  # 返回最保守目标尺寸。


def _blank_constraints() -> dict[str, bool]:  # 构造未约束六自由度字典。
    return {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}  # 返回标准约束结构。


def _node_payload(node_id: str, position: np.ndarray, source_ref: str | None = None, constraints: dict[str, bool] | None = None) -> dict[str, Any]:  # 构造 FE 节点对象。
    return {"id": node_id, "position": [float(value) for value in position], "coordinateSystemRef": "cs.global", "sourceRef": source_ref, "constraints": dict(constraints or _blank_constraints()), "attributes": {}}  # 返回符合 Schema 的节点对象。


def _bilinear(corners: list[np.ndarray], u: float, v: float) -> np.ndarray:  # 在四角面上执行双线性插值。
    first = (1.0 - u) * (1.0 - v) * corners[0]  # 计算第一角点贡献。
    second = u * (1.0 - v) * corners[1]  # 计算第二角点贡献。
    third = u * v * corners[2]  # 计算第三角点贡献。
    fourth = (1.0 - u) * v * corners[3]  # 计算第四角点贡献。
    return first + second + third + fourth  # 返回插值坐标。


def _triangle_area(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:  # 计算三角形面积。
    return 0.5 * float(np.linalg.norm(np.cross(second - first, third - first)))  # 返回叉积面积。


def _tetra_volume(points: list[np.ndarray]) -> float:  # 计算四面体体积。
    matrix = np.column_stack((points[1] - points[0], points[2] - points[0], points[3] - points[0]))  # 构造三条边向量矩阵。
    return abs(float(np.linalg.det(matrix))) / 6.0  # 返回行列式体积。


def _box_corners(component: dict[str, Any]) -> list[np.ndarray]:  # 从 box 几何生成八个旋转角点。
    geometry = component.get("geometry", {})  # 读取构件几何。
    center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取盒中心。
    size = np.asarray(geometry.get("size", [1.0, 1.0, 1.0]), dtype=float)  # 读取盒尺寸。
    rotation = _rotation_matrix(list(geometry.get("rotation", [0.0, 0.0, 0.0])))  # 构造盒旋转矩阵。
    local_corners = [np.asarray([-0.5, -0.5, -0.5]), np.asarray([0.5, -0.5, -0.5]), np.asarray([0.5, 0.5, -0.5]), np.asarray([-0.5, 0.5, -0.5]), np.asarray([-0.5, -0.5, 0.5]), np.asarray([0.5, -0.5, 0.5]), np.asarray([0.5, 0.5, 0.5]), np.asarray([-0.5, 0.5, 0.5])]  # 定义标准盒八角点。
    return [center + rotation @ (corner * size) for corner in local_corners]  # 返回旋转后的全局角点。


def _surface_corners(component: dict[str, Any], node_lookup: dict[str, dict[str, Any]]) -> list[np.ndarray]:  # 提取面构件三角或四角坐标。
    node_refs = list(component.get("nodeRefs", []))  # 读取构件节点引用。
    if len(node_refs) in {3, 4} and all(node_ref in node_lookup for node_ref in node_refs):  # 检查显式角点节点完整性。
        return [np.asarray(node_lookup[node_ref]["position"], dtype=float) for node_ref in node_refs]  # 返回节点坐标。
    geometry = component.get("geometry", {})  # 读取构件几何。
    if geometry.get("kind") == "box":  # 检查是否使用薄盒代理表面。
        corners = _box_corners(component)  # 生成盒八角点。
        return [corners[4], corners[5], corners[6], corners[7]]  # 默认使用盒顶面作为壳中面。
    raise ValueError(f"面构件 {component.get('id')} 必须提供 3/4 个有效 nodeRefs 或 box 几何。")  # 阻止无法确定拓扑的面构件。


def _mesh_shell_component(component: dict[str, Any], node_lookup: dict[str, dict[str, Any]], target_size: float, fe_nodes: dict[str, dict[str, Any]], fe_elements: list[dict[str, Any]], sets: list[dict[str, Any]], surfaces: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:  # 离散单个壳构件。
    component_id = str(component.get("id"))  # 读取构件 ID。
    corners = _surface_corners(component, node_lookup)  # 提取壳角点。
    element_type = str(component.get("analysis", {}).get("elementType", "shell4"))  # 读取期望壳单元类型。
    generated_elements: list[str] = []  # 初始化构件单元 ID 列表。
    generated_nodes: list[str] = []  # 初始化构件节点 ID 列表。
    if len(corners) == 3:  # 处理三角壳面。
        node_ids: list[str] = []  # 初始化三角节点 ID 列表。
        for index, point in enumerate(corners):  # 遍历三个角点。
            source_ref = component.get("nodeRefs", [None, None, None])[index] if len(component.get("nodeRefs", [])) == 3 else None  # 读取来源结构节点。
            node_id = str(source_ref) if source_ref else f"fenode.{slug(component_id)}.{index + 1}"  # 复用来源节点或生成 FE 节点 ID。
            source_node = node_lookup.get(str(source_ref), {})  # 查找来源节点。
            fe_nodes.setdefault(node_id, _node_payload(node_id, point, str(source_ref) if source_ref else None, source_node.get("constraints")))  # 保存 FE 节点。
            node_ids.append(node_id)  # 记录节点 ID。
        element_id = f"felem.{slug(component_id)}.1"  # 生成三角壳单元 ID。
        fe_elements.append({"id": element_id, "type": "S3", "nodeRefs": node_ids, "componentRef": component_id, "materialRef": component.get("materialRef"), "sectionRef": component.get("sectionRef"), "active": True, "orientation": component.get("analysis", {}).get("localUp"), "solverTypeOverrides": {}, "attributes": {"area": _triangle_area(*corners)}})  # 保存三角壳单元。
        generated_elements.append(element_id)  # 记录单元 ID。
        generated_nodes.extend(node_ids)  # 记录节点 ID。
        if max(float(np.linalg.norm(corners[(index + 1) % 3] - corners[index])) for index in range(3)) > target_size * 1.5:  # 检查三角面是否明显大于目标尺寸。
            warnings.append(f"三角面 {component_id} 当前生成单个 S3；需要更细三角剖分时应使用 Gmsh 或显式 FE 模型。")  # 记录细化边界。
    else:  # 处理四边壳面。
        edge_u = max(float(np.linalg.norm(corners[1] - corners[0])), float(np.linalg.norm(corners[2] - corners[3])))  # 估计 U 方向长度。
        edge_v = max(float(np.linalg.norm(corners[3] - corners[0])), float(np.linalg.norm(corners[2] - corners[1])))  # 估计 V 方向长度。
        count_u = max(1, int(math.ceil(edge_u / target_size)))  # 计算 U 方向分段数。
        count_v = max(1, int(math.ceil(edge_v / target_size)))  # 计算 V 方向分段数。
        grid: list[list[str]] = []  # 初始化二维节点网格。
        source_refs = list(component.get("nodeRefs", []))  # 读取角点来源引用。
        for j in range(count_v + 1):  # 遍历 V 方向节点层。
            row: list[str] = []  # 初始化当前节点行。
            for i in range(count_u + 1):  # 遍历 U 方向节点。
                u = i / count_u  # 计算归一化 U 坐标。
                v = j / count_v  # 计算归一化 V 坐标。
                source_ref = None  # 初始化可复用来源节点。
                if i == 0 and j == 0 and len(source_refs) == 4:  # 检查第一角点。
                    source_ref = source_refs[0]  # 复用第一角点节点。
                elif i == count_u and j == 0 and len(source_refs) == 4:  # 检查第二角点。
                    source_ref = source_refs[1]  # 复用第二角点节点。
                elif i == count_u and j == count_v and len(source_refs) == 4:  # 检查第三角点。
                    source_ref = source_refs[2]  # 复用第三角点节点。
                elif i == 0 and j == count_v and len(source_refs) == 4:  # 检查第四角点。
                    source_ref = source_refs[3]  # 复用第四角点节点。
                node_id = str(source_ref) if source_ref else f"fenode.{slug(component_id)}.{j}.{i}"  # 构造 FE 节点 ID。
                source_node = node_lookup.get(str(source_ref), {}) if source_ref else {}  # 查找来源节点。
                fe_nodes.setdefault(node_id, _node_payload(node_id, _bilinear(corners, u, v), str(source_ref) if source_ref else None, source_node.get("constraints")))  # 保存插值节点。
                row.append(node_id)  # 加入当前节点行。
                generated_nodes.append(node_id)  # 记录构件节点。
            grid.append(row)  # 保存当前节点行。
        actual_type = "S4R" if element_type in {"shell", "shell4"} and component.get("analysis", {}).get("integration") == "reduced" else "S4"  # 选择四节点壳积分类型。
        if element_type in {"shell8"}:  # 检查高阶壳请求。
            warnings.append(f"构件 {component_id} 请求 {element_type}，内置规则网格器降级为 S4；外部 Adapter 会在 ConversionReport 中继续报告。")  # 记录高阶降级。
        for j in range(count_v):  # 遍历壳单元行。
            for i in range(count_u):  # 遍历壳单元列。
                node_ids = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]  # 按一致法向组织四节点。
                points = [np.asarray(fe_nodes[node_id]["position"], dtype=float) for node_id in node_ids]  # 读取单元节点坐标。
                area = _triangle_area(points[0], points[1], points[2]) + _triangle_area(points[0], points[2], points[3])  # 计算四边形面积。
                element_id = f"felem.{slug(component_id)}.{j * count_u + i + 1}"  # 生成壳单元 ID。
                fe_elements.append({"id": element_id, "type": actual_type, "nodeRefs": node_ids, "componentRef": component_id, "materialRef": component.get("materialRef"), "sectionRef": component.get("sectionRef"), "active": True, "orientation": component.get("analysis", {}).get("localUp"), "solverTypeOverrides": {}, "attributes": {"area": area}})  # 保存四节点壳单元。
                generated_elements.append(element_id)  # 记录壳单元 ID。
    set_id = f"feset.{slug(component_id)}"  # 生成构件单元集合 ID。
    sets.append({"id": set_id, "name": component.get("name", component_id), "kind": "mixed", "nodeRefs": sorted(set(generated_nodes)), "elementRefs": generated_elements, "componentRefs": [component_id], "attributes": {}})  # 保存构件集合。
    facets = [{"elementRef": element_id, "face": "SPOS"} for element_id in generated_elements]  # 构造壳正面分片。
    surfaces.append({"id": f"surface.{slug(component_id)}.spos", "name": f"{component.get('name', component_id)} SPOS", "kind": "element_faces", "facets": facets, "nodeRefs": [], "setRef": set_id, "normal": component.get("analysis", {}).get("localUp"), "attributes": {"side": "SPOS"}})  # 保存壳正面。
    surfaces.append({"id": f"surface.{slug(component_id)}.sneg", "name": f"{component.get('name', component_id)} SNEG", "kind": "element_faces", "facets": [{"elementRef": element_id, "face": "SNEG"} for element_id in generated_elements], "nodeRefs": [], "setRef": set_id, "normal": None, "attributes": {"side": "SNEG"}})  # 保存壳负面。
    return {"componentRef": component_id, "nodeRefs": sorted(set(generated_nodes)), "elementRefs": generated_elements, "setRef": set_id}  # 返回壳构件映射。


def _solid_grid_point(corners: list[np.ndarray], u: float, v: float, w: float) -> np.ndarray:  # 对规则六面体执行三线性插值。
    bottom = _bilinear(corners[0:4], u, v)  # 计算底面插值点。
    top = _bilinear(corners[4:8], u, v)  # 计算顶面插值点。
    return (1.0 - w) * bottom + w * top  # 沿厚度方向插值。


def _mesh_solid_component(component: dict[str, Any], node_lookup: dict[str, dict[str, Any]], target_size: float, fe_nodes: dict[str, dict[str, Any]], fe_elements: list[dict[str, Any]], sets: list[dict[str, Any]], surfaces: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:  # 离散单个实体构件。
    component_id = str(component.get("id"))  # 读取构件 ID。
    geometry = component.get("geometry", {})  # 读取构件几何。
    node_refs = list(component.get("nodeRefs", []))  # 读取实体角点引用。
    if len(node_refs) == 8 and all(node_ref in node_lookup for node_ref in node_refs):  # 检查显式六面体角点。
        corners = [np.asarray(node_lookup[node_ref]["position"], dtype=float) for node_ref in node_refs]  # 读取八角点坐标。
        dimensions = [max(float(np.linalg.norm(corners[1] - corners[0])), float(np.linalg.norm(corners[2] - corners[3]))), max(float(np.linalg.norm(corners[3] - corners[0])), float(np.linalg.norm(corners[2] - corners[1]))), max(float(np.linalg.norm(corners[4] - corners[0])), float(np.linalg.norm(corners[5] - corners[1])))]  # 估计三个方向尺寸。
    elif geometry.get("kind") == "box":  # 检查规则盒实体。
        corners = _box_corners(component)  # 生成盒八角点。
        dimensions = [float(value) for value in geometry.get("size", [1.0, 1.0, 1.0])]  # 读取盒三个方向尺寸。
    else:  # 处理无法规则离散的实体。
        raise ValueError(f"实体构件 {component_id} 必须提供 8 个角点 nodeRefs 或 box 几何。")  # 阻止不支持几何。
    count_u = max(1, int(math.ceil(dimensions[0] / target_size)))  # 计算第一方向分段数。
    count_v = max(1, int(math.ceil(dimensions[1] / target_size)))  # 计算第二方向分段数。
    count_w = max(1, int(math.ceil(dimensions[2] / target_size)))  # 计算第三方向分段数。
    grid: list[list[list[str]]] = []  # 初始化三维节点网格。
    generated_nodes: list[str] = []  # 初始化实体节点列表。
    for k in range(count_w + 1):  # 遍历厚度节点层。
        layer: list[list[str]] = []  # 初始化当前厚度层。
        for j in range(count_v + 1):  # 遍历第二方向节点行。
            row: list[str] = []  # 初始化当前节点行。
            for i in range(count_u + 1):  # 遍历第一方向节点。
                u = i / count_u  # 计算归一化第一坐标。
                v = j / count_v  # 计算归一化第二坐标。
                w = k / count_w  # 计算归一化第三坐标。
                corner_index = None  # 初始化角点索引。
                corner_lookup = {(0, 0, 0): 0, (count_u, 0, 0): 1, (count_u, count_v, 0): 2, (0, count_v, 0): 3, (0, 0, count_w): 4, (count_u, 0, count_w): 5, (count_u, count_v, count_w): 6, (0, count_v, count_w): 7}  # 定义规则网格角点映射。
                corner_index = corner_lookup.get((i, j, k))  # 查找当前节点是否为角点。
                source_ref = node_refs[corner_index] if corner_index is not None and len(node_refs) == 8 else None  # 读取可复用结构节点。
                node_id = str(source_ref) if source_ref else f"fenode.{slug(component_id)}.{k}.{j}.{i}"  # 构造 FE 节点 ID。
                source_node = node_lookup.get(str(source_ref), {}) if source_ref else {}  # 查找来源节点。
                fe_nodes.setdefault(node_id, _node_payload(node_id, _solid_grid_point(corners, u, v, w), str(source_ref) if source_ref else None, source_node.get("constraints")))  # 保存实体节点。
                row.append(node_id)  # 加入当前行。
                generated_nodes.append(node_id)  # 记录实体节点。
            layer.append(row)  # 保存当前行。
        grid.append(layer)  # 保存当前厚度层。
    requested_type = str(component.get("analysis", {}).get("elementType", "hex8"))  # 读取期望实体单元类型。
    use_tetra = requested_type in {"tet4", "tet10"}  # 判断是否拆分为四面体。
    if requested_type in {"hex20", "tet10"}:  # 检查高阶实体请求。
        warnings.append(f"构件 {component_id} 请求 {requested_type}，内置规则网格器降级为 {'C3D4' if use_tetra else 'C3D8'}。")  # 记录高阶降级。
    generated_elements: list[str] = []  # 初始化实体单元 ID 列表。
    boundary_facets: dict[str, list[dict[str, str]]] = {"S1": [], "S2": [], "S3": [], "S4": [], "S5": [], "S6": []}  # 初始化六个外表面分片。
    element_counter = 0  # 初始化单元计数器。
    for k in range(count_w):  # 遍历厚度单元层。
        for j in range(count_v):  # 遍历第二方向单元行。
            for i in range(count_u):  # 遍历第一方向单元列。
                hex_nodes = [grid[k][j][i], grid[k][j][i + 1], grid[k][j + 1][i + 1], grid[k][j + 1][i], grid[k + 1][j][i], grid[k + 1][j][i + 1], grid[k + 1][j + 1][i + 1], grid[k + 1][j + 1][i]]  # 组织 C3D8 节点顺序。
                if use_tetra:  # 处理四面体拆分。
                    patterns = [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)]  # 使用一致的五四面体拆分模式。
                    for pattern in patterns:  # 遍历当前六面体内四面体。
                        element_counter += 1  # 增加单元计数器。
                        tetra_nodes = [hex_nodes[index] for index in pattern]  # 提取四面体节点。
                        points = [np.asarray(fe_nodes[node_id]["position"], dtype=float) for node_id in tetra_nodes]  # 读取四面体坐标。
                        element_id = f"felem.{slug(component_id)}.{element_counter}"  # 生成四面体单元 ID。
                        fe_elements.append({"id": element_id, "type": "C3D4", "nodeRefs": tetra_nodes, "componentRef": component_id, "materialRef": component.get("materialRef"), "sectionRef": None, "active": True, "orientation": None, "solverTypeOverrides": {}, "attributes": {"volume": _tetra_volume(points)}})  # 保存四面体单元。
                        generated_elements.append(element_id)  # 记录四面体 ID。
                else:  # 处理八节点六面体。
                    element_counter += 1  # 增加单元计数器。
                    element_id = f"felem.{slug(component_id)}.{element_counter}"  # 生成六面体单元 ID。
                    element_type = "C3D8R" if component.get("analysis", {}).get("integration") == "reduced" else "C3D8"  # 选择积分类型。
                    fe_elements.append({"id": element_id, "type": element_type, "nodeRefs": hex_nodes, "componentRef": component_id, "materialRef": component.get("materialRef"), "sectionRef": None, "active": True, "orientation": None, "solverTypeOverrides": {}, "attributes": {"cellIndex": [i, j, k]}})  # 保存六面体单元。
                    generated_elements.append(element_id)  # 记录六面体 ID。
                    if k == 0:  # 检查底面边界。
                        boundary_facets["S1"].append({"elementRef": element_id, "face": "S1"})  # 添加底面分片。
                    if k == count_w - 1:  # 检查顶面边界。
                        boundary_facets["S2"].append({"elementRef": element_id, "face": "S2"})  # 添加顶面分片。
                    if j == 0:  # 检查前侧边界。
                        boundary_facets["S3"].append({"elementRef": element_id, "face": "S3"})  # 添加前侧分片。
                    if i == count_u - 1:  # 检查右侧边界。
                        boundary_facets["S4"].append({"elementRef": element_id, "face": "S4"})  # 添加右侧分片。
                    if j == count_v - 1:  # 检查后侧边界。
                        boundary_facets["S5"].append({"elementRef": element_id, "face": "S5"})  # 添加后侧分片。
                    if i == 0:  # 检查左侧边界。
                        boundary_facets["S6"].append({"elementRef": element_id, "face": "S6"})  # 添加左侧分片。
    set_id = f"feset.{slug(component_id)}"  # 生成实体集合 ID。
    sets.append({"id": set_id, "name": component.get("name", component_id), "kind": "mixed", "nodeRefs": sorted(set(generated_nodes)), "elementRefs": generated_elements, "componentRefs": [component_id], "attributes": {}})  # 保存实体集合。
    if not use_tetra:  # 检查是否可以直接建立元素面集合。
        for face, facets in boundary_facets.items():  # 遍历六个边界面。
            surfaces.append({"id": f"surface.{slug(component_id)}.{face.lower()}", "name": f"{component.get('name', component_id)} {face}", "kind": "element_faces", "facets": facets, "nodeRefs": [], "setRef": set_id, "normal": None, "attributes": {"side": face}})  # 保存实体边界表面。
    else:  # 处理四面体表面自动识别边界。
        warnings.append(f"构件 {component_id} 的 C3D4 外表面未由规则网格器自动枚举；接触或压力荷载应提供显式 feSurface。")  # 记录表面边界限制。
    return {"componentRef": component_id, "nodeRefs": sorted(set(generated_nodes)), "elementRefs": generated_elements, "setRef": set_id}  # 返回实体构件映射。


def build_mixed_finite_element_model(document: dict[str, Any], mesh_policy_id: str | None = None, task_id: str | None = None, model_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:  # 从结构层生成混合 FE 模型及离散报告。
    policy = _select_policy(document, mesh_policy_id)  # 选择网格策略。
    tasks = [item for item in document.get("analysisTasks", []) if isinstance(item, dict)]  # 收集分析任务。
    selected_task = task_id or (str(tasks[0].get("id")) if tasks else "task.generated")  # 选择显式或首个任务。
    node_lookup = {str(item.get("id")): item for item in document.get("nodes", []) if isinstance(item, dict) and item.get("id")}  # 建立结构节点索引。
    fe_nodes: dict[str, dict[str, Any]] = {}  # 初始化 FE 节点索引。
    fe_elements: list[dict[str, Any]] = []  # 初始化 FE 单元列表。
    sets: list[dict[str, Any]] = []  # 初始化 FE 集合列表。
    surfaces: list[dict[str, Any]] = []  # 初始化 FE 表面列表。
    mappings: list[dict[str, Any]] = []  # 初始化结构到 FE 映射。
    warnings: list[str] = []  # 初始化离散警告。
    line_mesh = mesh_document(document, mesh_policy_id)  # 生成经过验证的梁网格。
    for node in line_mesh.get("nodes", []):  # 遍历梁网格节点。
        node_id = str(node.get("id"))  # 读取节点 ID。
        fe_nodes[node_id] = _node_payload(node_id, np.asarray(node.get("position"), dtype=float), node.get("originalNodeRef"), node.get("constraints"))  # 转换为工业 FE 节点。
    line_elements_by_component: dict[str, list[str]] = {}  # 初始化梁构件单元分组。
    for element in line_mesh.get("elements", []):  # 遍历梁网格单元。
        element_id = str(element.get("id"))  # 读取梁单元 ID。
        component_ref = str(element.get("componentRef"))  # 读取来源构件。
        fe_elements.append({"id": element_id, "type": "B31", "nodeRefs": list(element.get("nodeRefs", [])), "componentRef": component_ref, "materialRef": element.get("materialRef"), "sectionRef": element.get("sectionRef"), "active": True, "orientation": element.get("localUp"), "solverTypeOverrides": {}, "attributes": {"length": element.get("length"), "regionRefs": element.get("regionRefs", [])}})  # 转换为工业梁单元。
        line_elements_by_component.setdefault(component_ref, []).append(element_id)  # 保存梁构件分组。
    for mapping in line_mesh.get("mappings", []):  # 遍历梁构件映射。
        component_ref = str(mapping.get("componentRef"))  # 读取构件引用。
        set_id = f"feset.{slug(component_ref)}"  # 生成梁构件集合 ID。
        sets.append({"id": set_id, "name": component_ref, "kind": "mixed", "nodeRefs": list(mapping.get("meshNodeRefs", [])), "elementRefs": list(mapping.get("elementRefs", [])), "componentRefs": [component_ref], "attributes": {}})  # 保存梁集合。
        mappings.append({"componentRef": component_ref, "nodeRefs": list(mapping.get("meshNodeRefs", [])), "elementRefs": list(mapping.get("elementRefs", [])), "setRef": set_id})  # 保存梁映射。
    warnings.extend(line_mesh.get("warnings", []))  # 继承梁网格警告。
    for component in document.get("components", []):  # 遍历结构构件离散壳和实体。
        if not isinstance(component, dict):  # 跳过非法构件。
            continue  # 继续检查下一构件。
        analysis = component.get("analysis", {})  # 读取分析设置。
        if not isinstance(analysis, dict) or analysis.get("active") is not True:  # 跳过未激活构件。
            continue  # 继续检查下一构件。
        element_type = str(analysis.get("elementType"))  # 读取单元类型。
        target_size = _component_target_size(component, document, policy)  # 计算构件目标尺寸。
        if component.get("topology") == "surface" and element_type in {"shell", "shell4", "shell8", "membrane", "solid_shell"}:  # 检查壳或膜构件。
            mappings.append(_mesh_shell_component(component, node_lookup, target_size, fe_nodes, fe_elements, sets, surfaces, warnings))  # 离散壳构件并保存映射。
        elif component.get("topology") == "solid" and element_type in {"solid", "tet4", "tet10", "hex8", "hex20"}:  # 检查实体构件。
            mappings.append(_mesh_solid_component(component, node_lookup, target_size, fe_nodes, fe_elements, sets, surfaces, warnings))  # 离散实体构件并保存映射。
    maximum_elements = int(policy.get("budget", {}).get("maxElements", 100000))  # 读取网格单元预算。
    if len(fe_elements) > maximum_elements:  # 检查网格预算。
        raise ValueError(f"混合网格单元数 {len(fe_elements)} 超过 MeshPolicy 预算 {maximum_elements}。")  # 阻止超预算网格。
    section_assignments: list[dict[str, Any]] = []  # 初始化截面与材料分配。
    component_lookup = {str(item.get("id")): item for item in document.get("components", []) if isinstance(item, dict)}  # 建立构件索引。
    for item in mappings:  # 遍历结构到 FE 映射。
        component = component_lookup.get(str(item.get("componentRef")), {})  # 查找来源构件。
        section_assignments.append({"setRef": item.get("setRef"), "sectionRef": component.get("sectionRef"), "materialRef": component.get("materialRef"), "orientation": component.get("analysis", {}).get("localUp") if isinstance(component.get("analysis"), dict) else None, "attributes": {}})  # 保存集合分配。
    volumes = [float(element.get("attributes", {}).get("volume")) for element in fe_elements if isinstance(element.get("attributes", {}).get("volume"), (int, float))]  # 收集四面体体积。
    areas = [float(element.get("attributes", {}).get("area")) for element in fe_elements if isinstance(element.get("attributes", {}).get("area"), (int, float))]  # 收集壳单元面积。
    quality = {"nodeCount": len(fe_nodes), "elementCount": len(fe_elements), "elementTypes": {element_type: sum(1 for item in fe_elements if item.get("type") == element_type) for element_type in sorted({str(item.get("type")) for item in fe_elements})}, "minimumTetVolume": min(volumes) if volumes else None, "minimumShellArea": min(areas) if areas else None, "negativeJacobianCount": 0, "warnings": warnings}  # 汇总离散质量。
    model = {"id": model_id or f"fem.generated.{slug(selected_task)}", "name": "BridgeMind 生成混合有限元模型", "taskRef": selected_task, "coordinateSystemRef": "cs.global", "source": "generated", "nodes": list(fe_nodes.values()), "elements": fe_elements, "sets": sets, "surfaces": surfaces, "sectionAssignments": section_assignments, "meshArtifactRef": None, "quality": quality, "status": "draft", "attributes": {"meshPolicyRef": policy.get("id"), "mappings": mappings}}  # 构造符合 BSDL 的 FE 模型。
    report = {"modelId": model["id"], "taskRef": selected_task, "meshPolicyRef": policy.get("id"), "mappedComponents": len(mappings), "nodeCount": len(fe_nodes), "elementCount": len(fe_elements), "surfaceCount": len(surfaces), "setCount": len(sets), "warnings": warnings, "blocked": False}  # 构造离散报告。
    return model, report  # 返回 FE 模型和报告。

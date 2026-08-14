"""提供壳和实体单元的确定性结构化网格生成与质量统计。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供向量范数和有限值计算。
from typing import Any  # 提供通用 JSON 类型注解。
from ..utils import content_hash  # 复用内容哈希函数。


def _add(first: list[float], second: list[float]) -> list[float]:  # 计算两个三维向量的和。
    return [float(first[index]) + float(second[index]) for index in range(3)]  # 返回逐分量相加结果。


def _scale(vector: list[float], factor: float) -> list[float]:  # 对三维向量执行标量乘法。
    return [float(value) * float(factor) for value in vector]  # 返回缩放后的向量。


def _subtract(first: list[float], second: list[float]) -> list[float]:  # 计算两个三维向量的差。
    return [float(first[index]) - float(second[index]) for index in range(3)]  # 返回逐分量相减结果。


def _dot(first: list[float], second: list[float]) -> float:  # 计算三维向量点积。
    return sum(float(first[index]) * float(second[index]) for index in range(3))  # 返回点积标量。


def _cross(first: list[float], second: list[float]) -> list[float]:  # 计算三维向量叉积。
    return [float(first[1]) * float(second[2]) - float(first[2]) * float(second[1]), float(first[2]) * float(second[0]) - float(first[0]) * float(second[2]), float(first[0]) * float(second[1]) - float(first[1]) * float(second[0])]  # 返回右手叉积向量。


def _norm(vector: list[float]) -> float:  # 计算三维向量欧氏范数。
    return math.sqrt(max(_dot(vector, vector), 0.0))  # 返回非负范数。


def _unit(vector: list[float], name: str) -> list[float]:  # 归一化三维向量并检查退化情况。
    length = _norm(vector)  # 计算输入向量长度。
    if length <= 1e-12:  # 检查向量是否退化。
        raise ValueError(f"{name} 长度必须大于零。")  # 阻止创建退化网格。
    return _scale(vector, 1.0 / length)  # 返回单位向量。


def generate_shell_plate(model_id: str, task_ref: str, coordinate_system_ref: str, origin: list[float], axis_u: list[float], axis_v: list[float], length_u: float, length_v: float, divisions_u: int, divisions_v: int, section_ref: str, source_ref: str | None = None, element_type: str = "S4R") -> dict[str, Any]:  # 生成平面四边形壳网格。
    if element_type not in {"S4", "S4R"}:  # 检查当前生成器支持的壳单元类型。
        raise ValueError("结构化板生成器只支持 S4 或 S4R。")  # 阻止不兼容单元请求。
    if length_u <= 0.0 or length_v <= 0.0:  # 检查板尺寸。
        raise ValueError("壳板两个方向长度必须大于零。")  # 阻止零尺寸板。
    if divisions_u < 1 or divisions_v < 1:  # 检查划分数量。
        raise ValueError("壳板两个方向划分数必须至少为一。")  # 阻止空网格。
    unit_u = _unit(axis_u, "axis_u")  # 归一化第一局部轴。
    projected_v = _subtract(axis_v, _scale(unit_u, _dot(axis_v, unit_u)))  # 从第二轴移除与第一轴平行的分量。
    unit_v = _unit(projected_v, "axis_v")  # 归一化正交后的第二局部轴。
    normal = _unit(_cross(unit_u, unit_v), "shell_normal")  # 计算壳法向量。
    nodes: list[dict[str, Any]] = []  # 初始化 FE 节点列表。
    elements: list[dict[str, Any]] = []  # 初始化 FE 单元列表。
    node_grid: list[list[str]] = []  # 初始化节点二维索引。
    for index_v in range(divisions_v + 1):  # 遍历第二方向节点行。
        row: list[str] = []  # 初始化当前节点行。
        ratio_v = index_v / divisions_v  # 计算第二方向归一化坐标。
        for index_u in range(divisions_u + 1):  # 遍历第一方向节点列。
            ratio_u = index_u / divisions_u  # 计算第一方向归一化坐标。
            node_id = f"{model_id}.n.{index_u}.{index_v}"  # 构造稳定节点 ID。
            position = _add(origin, _add(_scale(unit_u, length_u * ratio_u), _scale(unit_v, length_v * ratio_v)))  # 计算节点全局坐标。
            nodes.append({"id": node_id, "position": position, "coordinateSystemRef": coordinate_system_ref, "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "sourceRef": source_ref, "attributes": {"parametric": [ratio_u, ratio_v], "normal": normal}})  # 保存壳网格节点。
            row.append(node_id)  # 把节点 ID 加入二维索引。
        node_grid.append(row)  # 保存当前节点行。
    element_refs: list[str] = []  # 初始化全板单元集合引用。
    for index_v in range(divisions_v):  # 遍历第二方向单元行。
        for index_u in range(divisions_u):  # 遍历第一方向单元列。
            element_id = f"{model_id}.e.{index_u}.{index_v}"  # 构造稳定壳单元 ID。
            node_refs = [node_grid[index_v][index_u], node_grid[index_v][index_u + 1], node_grid[index_v + 1][index_u + 1], node_grid[index_v + 1][index_u]]  # 按右手法向顺序连接四个节点。
            elements.append({"id": element_id, "type": element_type, "nodeRefs": node_refs, "sectionRef": section_ref, "materialRef": None, "sourceRef": source_ref, "orientationRef": coordinate_system_ref, "setRefs": [f"{model_id}.set.all"], "active": True, "attributes": {"cell": [index_u, index_v]}})  # 保存壳单元。
            element_refs.append(element_id)  # 把单元加入全板集合。
    boundary_sets = _shell_boundary_sets(model_id, node_grid, elements)  # 生成边界节点与表面集合。
    model = {"id": model_id, "name": model_id, "taskRef": task_ref, "coordinateSystemRef": coordinate_system_ref, "nodes": nodes, "elements": elements, "sets": [{"id": f"{model_id}.set.all", "name": "全部壳单元", "kind": "element", "refs": element_refs, "faces": [], "sourceRefs": [source_ref] if source_ref else [], "attributes": {}}] + boundary_sets, "source": "generated", "meshHash": "", "status": "validated", "statistics": {}, "artifactRefs": []}  # 组装 FE 模型。
    model["statistics"] = quality_report(model)  # 计算网格质量统计。
    model["meshHash"] = content_hash({"nodes": nodes, "elements": elements, "sets": model["sets"]})  # 计算网格内容哈希。
    return model  # 返回完整壳 FE 模型。


def _shell_boundary_sets(model_id: str, node_grid: list[list[str]], elements: list[dict[str, Any]]) -> list[dict[str, Any]]:  # 生成结构化壳板的四条边界和正负表面集合。
    bottom = list(node_grid[0])  # 读取第二方向起始边节点。
    top = list(node_grid[-1])  # 读取第二方向终止边节点。
    left = [row[0] for row in node_grid]  # 读取第一方向起始边节点。
    right = [row[-1] for row in node_grid]  # 读取第一方向终止边节点。
    positive_faces = [{"elementRef": str(element["id"]), "face": "SPOS"} for element in elements]  # 构造壳正面表面集合。
    negative_faces = [{"elementRef": str(element["id"]), "face": "SNEG"} for element in elements]  # 构造壳负面表面集合。
    return [  # 返回全部边界集合。
        {"id": f"{model_id}.set.edge.u0", "name": "U 起始边", "kind": "node", "refs": left, "faces": [], "sourceRefs": [], "attributes": {}},  # 保存第一方向起始边。
        {"id": f"{model_id}.set.edge.u1", "name": "U 终止边", "kind": "node", "refs": right, "faces": [], "sourceRefs": [], "attributes": {}},  # 保存第一方向终止边。
        {"id": f"{model_id}.set.edge.v0", "name": "V 起始边", "kind": "node", "refs": bottom, "faces": [], "sourceRefs": [], "attributes": {}},  # 保存第二方向起始边。
        {"id": f"{model_id}.set.edge.v1", "name": "V 终止边", "kind": "node", "refs": top, "faces": [], "sourceRefs": [], "attributes": {}},  # 保存第二方向终止边。
        {"id": f"{model_id}.surface.positive", "name": "壳正面", "kind": "surface", "refs": [], "faces": positive_faces, "sourceRefs": [], "attributes": {}},  # 保存壳正面集合。
        {"id": f"{model_id}.surface.negative", "name": "壳负面", "kind": "surface", "refs": [], "faces": negative_faces, "sourceRefs": [], "attributes": {}},  # 保存壳负面集合。
    ]  # 完成边界集合构造。


def generate_solid_block(model_id: str, task_ref: str, coordinate_system_ref: str, origin: list[float], size: list[float], divisions: list[int], section_ref: str, source_ref: str | None = None, element_type: str = "C3D8R") -> dict[str, Any]:  # 生成结构化八节点实体网格。
    if element_type not in {"C3D8", "C3D8R"}:  # 检查当前生成器支持的实体类型。
        raise ValueError("结构化块生成器只支持 C3D8 或 C3D8R。")  # 阻止不兼容单元请求。
    if len(size) != 3 or any(float(value) <= 0.0 for value in size):  # 检查实体三向尺寸。
        raise ValueError("实体块 size 必须包含三个正数。")  # 阻止退化实体。
    if len(divisions) != 3 or any(int(value) < 1 for value in divisions):  # 检查实体三向划分数。
        raise ValueError("实体块 divisions 必须包含三个正整数。")  # 阻止空实体网格。
    count_x, count_y, count_z = (int(value) for value in divisions)  # 解包三向划分数。
    nodes: list[dict[str, Any]] = []  # 初始化实体节点列表。
    elements: list[dict[str, Any]] = []  # 初始化实体单元列表。
    grid: dict[tuple[int, int, int], str] = {}  # 初始化三维节点索引。
    for index_z in range(count_z + 1):  # 遍历 Z 方向节点层。
        for index_y in range(count_y + 1):  # 遍历 Y 方向节点行。
            for index_x in range(count_x + 1):  # 遍历 X 方向节点列。
                node_id = f"{model_id}.n.{index_x}.{index_y}.{index_z}"  # 构造稳定实体节点 ID。
                position = [float(origin[0]) + float(size[0]) * index_x / count_x, float(origin[1]) + float(size[1]) * index_y / count_y, float(origin[2]) + float(size[2]) * index_z / count_z]  # 计算节点坐标。
                nodes.append({"id": node_id, "position": position, "coordinateSystemRef": coordinate_system_ref, "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "sourceRef": source_ref, "attributes": {"grid": [index_x, index_y, index_z]}})  # 保存实体节点。
                grid[(index_x, index_y, index_z)] = node_id  # 保存三维索引到节点 ID 的映射。
    element_refs: list[str] = []  # 初始化全实体单元集合。
    face_sets: dict[str, list[dict[str, str]]] = {"xmin": [], "xmax": [], "ymin": [], "ymax": [], "zmin": [], "zmax": []}  # 初始化六个外表面集合。
    for index_z in range(count_z):  # 遍历 Z 方向单元层。
        for index_y in range(count_y):  # 遍历 Y 方向单元行。
            for index_x in range(count_x):  # 遍历 X 方向单元列。
                element_id = f"{model_id}.e.{index_x}.{index_y}.{index_z}"  # 构造稳定实体单元 ID。
                node_refs = [grid[(index_x, index_y, index_z)], grid[(index_x + 1, index_y, index_z)], grid[(index_x + 1, index_y + 1, index_z)], grid[(index_x, index_y + 1, index_z)], grid[(index_x, index_y, index_z + 1)], grid[(index_x + 1, index_y, index_z + 1)], grid[(index_x + 1, index_y + 1, index_z + 1)], grid[(index_x, index_y + 1, index_z + 1)]]  # 按标准六面体顺序连接八个节点。
                elements.append({"id": element_id, "type": element_type, "nodeRefs": node_refs, "sectionRef": section_ref, "materialRef": None, "sourceRef": source_ref, "orientationRef": coordinate_system_ref, "setRefs": [f"{model_id}.set.all"], "active": True, "attributes": {"cell": [index_x, index_y, index_z]}})  # 保存实体单元。
                element_refs.append(element_id)  # 把单元加入全实体集合。
                if index_x == 0:  # 检查 X 起始外表面。
                    face_sets["xmin"].append({"elementRef": element_id, "face": "S6"})  # 保存 X 起始面。
                if index_x == count_x - 1:  # 检查 X 终止外表面。
                    face_sets["xmax"].append({"elementRef": element_id, "face": "S4"})  # 保存 X 终止面。
                if index_y == 0:  # 检查 Y 起始外表面。
                    face_sets["ymin"].append({"elementRef": element_id, "face": "S1"})  # 保存 Y 起始面。
                if index_y == count_y - 1:  # 检查 Y 终止外表面。
                    face_sets["ymax"].append({"elementRef": element_id, "face": "S2"})  # 保存 Y 终止面。
                if index_z == 0:  # 检查 Z 起始外表面。
                    face_sets["zmin"].append({"elementRef": element_id, "face": "S3"})  # 保存 Z 起始面。
                if index_z == count_z - 1:  # 检查 Z 终止外表面。
                    face_sets["zmax"].append({"elementRef": element_id, "face": "S5"})  # 保存 Z 终止面。
    sets: list[dict[str, Any]] = [{"id": f"{model_id}.set.all", "name": "全部实体单元", "kind": "element", "refs": element_refs, "faces": [], "sourceRefs": [source_ref] if source_ref else [], "attributes": {}}]  # 创建全实体单元集合。
    for face_name, faces in face_sets.items():  # 遍历六个外表面。
        sets.append({"id": f"{model_id}.surface.{face_name}", "name": face_name, "kind": "surface", "refs": [], "faces": faces, "sourceRefs": [], "attributes": {}})  # 保存外表面集合。
    model = {"id": model_id, "name": model_id, "taskRef": task_ref, "coordinateSystemRef": coordinate_system_ref, "nodes": nodes, "elements": elements, "sets": sets, "source": "generated", "meshHash": "", "status": "validated", "statistics": {}, "artifactRefs": []}  # 组装实体 FE 模型。
    model["statistics"] = quality_report(model)  # 计算实体网格质量统计。
    model["meshHash"] = content_hash({"nodes": nodes, "elements": elements, "sets": sets})  # 计算网格内容哈希。
    return model  # 返回完整实体 FE 模型。


def expected_node_count(element_type: str) -> int | None:  # 返回已知 FE 单元类型的标准节点数。
    counts = {"T3D2": 2, "B31": 2, "B32": 3, "S3": 3, "S4": 4, "S4R": 4, "C3D4": 4, "C3D6": 6, "C3D8": 8, "C3D8R": 8, "C3D10": 10, "C3D20": 20, "C3D20R": 20, "MASS": 1, "SPRINGA": 2}  # 定义标准节点数映射。
    return counts.get(element_type)  # 返回匹配节点数或未知状态。


def element_family(element_type: str) -> str:  # 把求解器单元名称归一化为族。
    if element_type.startswith("S"):  # 检查壳单元前缀。
        return "shell"  # 返回壳单元族。
    if element_type.startswith("C3D"):  # 检查三维连续体前缀。
        return "solid"  # 返回实体单元族。
    if element_type.startswith("B"):  # 检查梁单元前缀。
        return "beam"  # 返回梁单元族。
    if element_type.startswith("T3D"):  # 检查桁架单元前缀。
        return "truss"  # 返回桁架单元族。
    return "special"  # 返回特殊单元族。


def quality_report(model: dict[str, Any]) -> dict[str, Any]:  # 计算网格拓扑、边长和简化形状质量统计。
    nodes = {str(node.get("id")): [float(value) for value in node.get("position", [0.0, 0.0, 0.0])] for node in model.get("nodes", []) if isinstance(node, dict)}  # 建立节点坐标索引。
    edge_lengths: list[float] = []  # 初始化全部单元边长集合。
    degenerate: list[str] = []  # 初始化退化单元列表。
    wrong_node_count: list[str] = []  # 初始化节点数错误单元列表。
    aspect_ratios: list[float] = []  # 初始化单元边长比列表。
    type_counts: dict[str, int] = {}  # 初始化单元类型计数。
    for element in model.get("elements", []):  # 遍历 FE 单元。
        if not isinstance(element, dict):  # 跳过非法单元项。
            continue  # 继续检查下一单元。
        element_id = str(element.get("id"))  # 读取单元 ID。
        element_type = str(element.get("type"))  # 读取单元类型。
        type_counts[element_type] = type_counts.get(element_type, 0) + 1  # 累加单元类型数量。
        refs = [str(value) for value in element.get("nodeRefs", [])]  # 读取单元节点引用。
        expected = expected_node_count(element_type)  # 获取标准节点数。
        if expected is not None and len(refs) != expected:  # 检查节点数量是否匹配。
            wrong_node_count.append(element_id)  # 记录节点数错误单元。
        points = [nodes[ref] for ref in refs if ref in nodes]  # 收集存在的单元节点坐标。
        if len(points) != len(refs) or len(set(refs)) != len(refs):  # 检查悬空引用和重复节点。
            degenerate.append(element_id)  # 记录退化或悬空单元。
            continue  # 跳过当前单元质量计算。
        local_edges = _element_edge_lengths(element_type, points)  # 计算当前单元边长。
        positive_edges = [value for value in local_edges if value > 1e-12]  # 提取有效边长。
        edge_lengths.extend(positive_edges)  # 保存有效边长。
        if not positive_edges or len(positive_edges) != len(local_edges):  # 检查零边长。
            degenerate.append(element_id)  # 记录退化单元。
            continue  # 跳过边长比计算。
        aspect_ratios.append(max(positive_edges) / min(positive_edges))  # 保存最大最小边长比。
    return {"nodeCount": len(nodes), "elementCount": sum(type_counts.values()), "setCount": len(model.get("sets", [])), "elementTypes": type_counts, "minimumEdge": min(edge_lengths) if edge_lengths else None, "maximumEdge": max(edge_lengths) if edge_lengths else None, "maximumAspectRatio": max(aspect_ratios) if aspect_ratios else None, "meanAspectRatio": sum(aspect_ratios) / len(aspect_ratios) if aspect_ratios else None, "degenerateElements": degenerate, "wrongNodeCountElements": wrong_node_count, "validTopology": not degenerate and not wrong_node_count}  # 返回质量统计。


def _element_edge_lengths(element_type: str, points: list[list[float]]) -> list[float]:  # 计算常见单元的拓扑边长度。
    edge_map = {"T3D2": [(0, 1)], "B31": [(0, 1)], "B32": [(0, 1), (1, 2)], "S3": [(0, 1), (1, 2), (2, 0)], "S4": [(0, 1), (1, 2), (2, 3), (3, 0)], "S4R": [(0, 1), (1, 2), (2, 3), (3, 0)], "C3D4": [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)], "C3D6": [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)], "C3D8": [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)], "C3D8R": [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]}  # 定义常见低阶单元边拓扑。
    pairs = edge_map.get(element_type, [(index, index + 1) for index in range(max(len(points) - 1, 0))])  # 选择已知拓扑或顺序备用拓扑。
    return [_norm(_subtract(points[first], points[second])) for first, second in pairs if first < len(points) and second < len(points)]  # 返回所有可计算边长。

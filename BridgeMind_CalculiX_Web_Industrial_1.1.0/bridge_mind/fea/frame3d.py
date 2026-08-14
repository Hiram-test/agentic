"""用于快速反馈的空间 Euler–Bernoulli 梁有限元求解器。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供平方根和有限值检查。
import time  # 提供运行时间计量。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供矩阵组装和线性方程求解。
from .mesher import mesh_document  # 复用确定性线构件网格器。
from ..utils import utc_now  # 复用统一时间戳。

DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]  # 定义每节点六自由度顺序。


class FrameSolveError(RuntimeError):  # 定义可识别的求解失败异常。
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:  # 初始化求解异常。
        super().__init__(message)  # 保存标准异常消息。
        self.details = details or {}  # 保存结构化诊断详情。


def _normalize(vector: np.ndarray, name: str) -> np.ndarray:  # 归一化三维向量并检查零长度。
    norm = float(np.linalg.norm(vector))  # 计算向量范数。
    if norm <= 1e-14:  # 检查退化向量。
        raise FrameSolveError(f"{name} 向量长度为零。")  # 阻止构造非法局部坐标系。
    return vector / norm  # 返回单位向量。


def _local_axes(start: np.ndarray, end: np.ndarray, local_up: list[float] | None) -> np.ndarray:  # 构造梁单元局部坐标到全局坐标的方向矩阵。
    axis_x = _normalize(end - start, "构件轴")  # 计算局部 X 轴。
    up = np.asarray(local_up if local_up is not None else [0.0, 0.0, 1.0], dtype=float)  # 读取或设置局部参考上方向。
    projected = up - float(np.dot(up, axis_x)) * axis_x  # 去除上方向在构件轴上的分量。
    if float(np.linalg.norm(projected)) <= 1e-10:  # 检查参考上方向是否与构件平行。
        fallback = np.asarray([0.0, 1.0, 0.0], dtype=float)  # 选择第一备用方向。
        projected = fallback - float(np.dot(fallback, axis_x)) * axis_x  # 投影第一备用方向。
    if float(np.linalg.norm(projected)) <= 1e-10:  # 检查第一备用方向是否仍退化。
        fallback = np.asarray([1.0, 0.0, 0.0], dtype=float)  # 选择第二备用方向。
        projected = fallback - float(np.dot(fallback, axis_x)) * axis_x  # 投影第二备用方向。
    axis_y = _normalize(projected, "局部 Y 轴")  # 归一化局部 Y 轴。
    axis_z = _normalize(np.cross(axis_x, axis_y), "局部 Z 轴")  # 通过右手规则计算局部 Z 轴。
    axis_y = _normalize(np.cross(axis_z, axis_x), "正交化局部 Y 轴")  # 再次正交化局部 Y 轴。
    return np.vstack([axis_x, axis_y, axis_z])  # 返回把全局向量转换为局部分量的矩阵。


def _local_stiffness(length: float, elastic_modulus: float, shear_modulus: float, area: float, iy: float, iz: float, torsion_constant: float) -> np.ndarray:  # 构造 12×12 空间梁局部刚度矩阵。
    if min(length, elastic_modulus, shear_modulus, area, iy, iz, torsion_constant) <= 0.0:  # 检查所有刚度参数为正。
        raise FrameSolveError("梁单元长度、材料和截面参数必须全部大于零。")  # 阻止非法刚度矩阵。
    matrix = np.zeros((12, 12), dtype=float)  # 初始化局部刚度矩阵。
    axial = elastic_modulus * area / length  # 计算轴向刚度。
    torsion = shear_modulus * torsion_constant / length  # 计算扭转刚度。
    bending_z_12 = 12.0 * elastic_modulus * iz / length**3  # 计算局部 XY 平面弯曲平移刚度。
    bending_z_6 = 6.0 * elastic_modulus * iz / length**2  # 计算局部 XY 平面弯曲耦合刚度。
    bending_z_4 = 4.0 * elastic_modulus * iz / length  # 计算局部 XY 平面端转动刚度。
    bending_z_2 = 2.0 * elastic_modulus * iz / length  # 计算局部 XY 平面跨端转动刚度。
    bending_y_12 = 12.0 * elastic_modulus * iy / length**3  # 计算局部 XZ 平面弯曲平移刚度。
    bending_y_6 = 6.0 * elastic_modulus * iy / length**2  # 计算局部 XZ 平面弯曲耦合刚度。
    bending_y_4 = 4.0 * elastic_modulus * iy / length  # 计算局部 XZ 平面端转动刚度。
    bending_y_2 = 2.0 * elastic_modulus * iy / length  # 计算局部 XZ 平面跨端转动刚度。
    matrix[0, 0] = axial  # 设置节点一轴向刚度。
    matrix[0, 6] = -axial  # 设置节点间轴向耦合。
    matrix[6, 0] = -axial  # 设置对称轴向耦合。
    matrix[6, 6] = axial  # 设置节点二轴向刚度。
    matrix[3, 3] = torsion  # 设置节点一扭转刚度。
    matrix[3, 9] = -torsion  # 设置节点间扭转耦合。
    matrix[9, 3] = -torsion  # 设置对称扭转耦合。
    matrix[9, 9] = torsion  # 设置节点二扭转刚度。
    matrix[1, 1] = bending_z_12  # 设置节点一局部 Y 平移刚度。
    matrix[1, 5] = bending_z_6  # 设置节点一 Y 平移与 Z 转动耦合。
    matrix[1, 7] = -bending_z_12  # 设置跨节点 Y 平移耦合。
    matrix[1, 11] = bending_z_6  # 设置节点一 Y 平移与节点二 Z 转动耦合。
    matrix[5, 1] = bending_z_6  # 设置对称耦合项。
    matrix[5, 5] = bending_z_4  # 设置节点一 Z 转动刚度。
    matrix[5, 7] = -bending_z_6  # 设置节点一 Z 转动与节点二 Y 平移耦合。
    matrix[5, 11] = bending_z_2  # 设置跨节点 Z 转动耦合。
    matrix[7, 1] = -bending_z_12  # 设置对称跨节点 Y 平移耦合。
    matrix[7, 5] = -bending_z_6  # 设置对称节点二 Y 平移与节点一 Z 转动耦合。
    matrix[7, 7] = bending_z_12  # 设置节点二局部 Y 平移刚度。
    matrix[7, 11] = -bending_z_6  # 设置节点二 Y 平移与 Z 转动耦合。
    matrix[11, 1] = bending_z_6  # 设置对称节点二 Z 转动耦合。
    matrix[11, 5] = bending_z_2  # 设置对称跨节点 Z 转动耦合。
    matrix[11, 7] = -bending_z_6  # 设置对称节点二耦合。
    matrix[11, 11] = bending_z_4  # 设置节点二 Z 转动刚度。
    matrix[2, 2] = bending_y_12  # 设置节点一局部 Z 平移刚度。
    matrix[2, 4] = -bending_y_6  # 设置节点一 Z 平移与 Y 转动耦合。
    matrix[2, 8] = -bending_y_12  # 设置跨节点 Z 平移耦合。
    matrix[2, 10] = -bending_y_6  # 设置节点一 Z 平移与节点二 Y 转动耦合。
    matrix[4, 2] = -bending_y_6  # 设置对称耦合项。
    matrix[4, 4] = bending_y_4  # 设置节点一 Y 转动刚度。
    matrix[4, 8] = bending_y_6  # 设置节点一 Y 转动与节点二 Z 平移耦合。
    matrix[4, 10] = bending_y_2  # 设置跨节点 Y 转动耦合。
    matrix[8, 2] = -bending_y_12  # 设置对称跨节点 Z 平移耦合。
    matrix[8, 4] = bending_y_6  # 设置对称节点二 Z 平移与节点一 Y 转动耦合。
    matrix[8, 8] = bending_y_12  # 设置节点二局部 Z 平移刚度。
    matrix[8, 10] = bending_y_6  # 设置节点二 Z 平移与 Y 转动耦合。
    matrix[10, 2] = -bending_y_6  # 设置对称节点二 Y 转动耦合。
    matrix[10, 4] = bending_y_2  # 设置对称跨节点 Y 转动耦合。
    matrix[10, 8] = bending_y_6  # 设置对称节点二耦合。
    matrix[10, 10] = bending_y_4  # 设置节点二 Y 转动刚度。
    return matrix  # 返回完整局部刚度矩阵。


def _transform_matrix(rotation: np.ndarray) -> np.ndarray:  # 构造 12×12 位移坐标变换矩阵。
    transform = np.zeros((12, 12), dtype=float)  # 初始化变换矩阵。
    for start in [0, 3, 6, 9]:  # 遍历两个节点的平移和转动块。
        transform[start : start + 3, start : start + 3] = rotation  # 把三维方向矩阵写入对应块。
    return transform  # 返回局部位移等于 T 乘全局位移的矩阵。


def _select_load_case(document: dict[str, Any], load_case_id: str | None) -> tuple[str, float]:  # 选择求解使用的荷载工况。
    cases = [case for case in document.get("loadCases", []) if isinstance(case, dict)]  # 收集可用荷载工况。
    if load_case_id is None:  # 处理未指定工况的情况。
        if not cases:  # 检查是否存在工况。
            raise FrameSolveError("文档不包含荷载工况。")  # 阻止无工况求解。
        selected = cases[0]  # 默认选择首个工况。
    else:  # 处理显式指定工况。
        matches = [case for case in cases if case.get("id") == load_case_id]  # 查找匹配工况。
        if not matches:  # 检查工况是否存在。
            raise FrameSolveError(f"荷载工况不存在：{load_case_id}")  # 对缺失工况给出明确错误。
        selected = matches[0]  # 使用匹配工况。
    return str(selected.get("id")), float(selected.get("factor", 1.0))  # 返回工况 ID 和系数。


def solve_document(document: dict[str, Any], mesh_policy_id: str | None = None, load_case_id: str | None = None, singular_tolerance: float = 1e-12) -> dict[str, Any]:  # 对 BSDL 空间梁模型执行线性静力求解。
    started = time.perf_counter()  # 记录高精度开始时间。
    mesh = mesh_document(document, mesh_policy_id)  # 按网格策略生成分析网格。
    mesh_nodes = mesh.get("nodes", [])  # 读取网格节点。
    mesh_elements = mesh.get("elements", [])  # 读取网格单元。
    if not mesh_elements:  # 检查是否存在可求解单元。
        raise FrameSolveError("没有可求解的 frame3d 单元。", {"meshStats": mesh.get("stats", {})})  # 阻止空模型求解。
    node_index = {node["id"]: position for position, node in enumerate(mesh_nodes)}  # 建立网格节点到序号的映射。
    node_lookup = {node["id"]: node for node in mesh_nodes}  # 建立网格节点对象索引。
    materials = {material["id"]: material for material in document.get("materials", []) if isinstance(material, dict)}  # 建立材料索引。
    sections = {section["id"]: section for section in document.get("sections", []) if isinstance(section, dict)}  # 建立截面索引。
    dof_count = len(mesh_nodes) * 6  # 计算系统总自由度数。
    stiffness = np.zeros((dof_count, dof_count), dtype=float)  # 初始化全局刚度矩阵。
    load_vector = np.zeros(dof_count, dtype=float)  # 初始化全局荷载向量。
    element_cache: dict[str, dict[str, Any]] = {}  # 初始化单元矩阵缓存以便回算端力。
    for element in mesh_elements:  # 遍历所有空间梁单元。
        element_id = str(element.get("id"))  # 读取单元 ID。
        first_ref, second_ref = element.get("nodeRefs", [None, None])  # 解包单元两个节点引用。
        if first_ref not in node_lookup or second_ref not in node_lookup:  # 检查网格节点引用。
            raise FrameSolveError(f"单元 {element_id} 引用了不存在的网格节点。")  # 阻止悬空网格引用。
        start = np.asarray(node_lookup[first_ref]["position"], dtype=float)  # 读取单元起点坐标。
        end = np.asarray(node_lookup[second_ref]["position"], dtype=float)  # 读取单元终点坐标。
        length = float(np.linalg.norm(end - start))  # 计算单元长度。
        material = materials.get(element.get("materialRef"))  # 查找单元材料。
        section = sections.get(element.get("sectionRef"))  # 查找单元截面。
        if material is None or section is None:  # 检查材料和截面是否存在。
            raise FrameSolveError(f"单元 {element_id} 缺少材料或截面。", {"materialRef": element.get("materialRef"), "sectionRef": element.get("sectionRef")})  # 阻止刚度参数缺失。
        elastic_modulus = float(material["elasticModulus"])  # 读取弹性模量。
        poisson_ratio = float(material["poissonRatio"])  # 读取泊松比。
        shear_modulus = float(material.get("shearModulus") or elastic_modulus / (2.0 * (1.0 + poisson_ratio)))  # 读取或推导剪切模量。
        local_stiffness = _local_stiffness(length, elastic_modulus, shear_modulus, float(section["area"]), float(section["iy"]), float(section["iz"]), float(section["torsionConstant"]))  # 构造局部刚度矩阵。
        rotation = _local_axes(start, end, element.get("localUp"))  # 构造局部方向矩阵。
        transform = _transform_matrix(rotation)  # 构造 12×12 变换矩阵。
        global_stiffness = transform.T @ local_stiffness @ transform  # 把局部刚度转换到全局坐标。
        dofs = [node_index[first_ref] * 6 + offset for offset in range(6)] + [node_index[second_ref] * 6 + offset for offset in range(6)]  # 生成单元全局自由度索引。
        stiffness[np.ix_(dofs, dofs)] += global_stiffness  # 把单元刚度组装到全局矩阵。
        element_cache[element_id] = {"localStiffness": local_stiffness, "transform": transform, "dofs": dofs, "length": length, "rotation": rotation, "element": element}  # 缓存端力回算所需数据。
    selected_case, case_factor = _select_load_case(document, load_case_id)  # 选择荷载工况及系数。
    nonzero_load_count = 0  # 初始化非零荷载计数。
    warnings = list(mesh.get("warnings", []))  # 继承网格阶段警告。
    for load in document.get("loads", []):  # 遍历 BSDL 荷载。
        if not isinstance(load, dict) or load.get("caseRef") != selected_case:  # 跳过非法项和其他工况荷载。
            continue  # 继续检查下一荷载。
        if load.get("kind") != "nodal":  # 当前内置求解器仅直接支持节点荷载。
            warnings.append(f"内置求解器忽略非节点荷载 {load.get('id')}，请通过 Adapter 转换。")  # 显式记录能力损失。
            continue  # 继续检查下一荷载。
        target_ref = load.get("targetNodeRef")  # 读取荷载目标节点。
        if target_ref not in node_index:  # 检查目标节点进入网格。
            raise FrameSolveError(f"节点荷载 {load.get('id')} 的目标 {target_ref} 不在网格中。")  # 阻止无法施加的荷载。
        values = np.asarray(list(load.get("force", [0.0, 0.0, 0.0])) + list(load.get("moment", [0.0, 0.0, 0.0])), dtype=float) * case_factor  # 合并力和矩并应用工况系数。
        base = node_index[target_ref] * 6  # 计算目标节点首自由度索引。
        load_vector[base : base + 6] += values  # 把节点荷载组装到全局向量。
        if float(np.linalg.norm(values)) > 0.0:  # 检查荷载是否非零。
            nonzero_load_count += 1  # 增加非零荷载计数。
    constrained: list[int] = []  # 初始化约束自由度列表。
    for node in mesh_nodes:  # 遍历网格节点约束。
        base = node_index[node["id"]] * 6  # 计算节点首自由度索引。
        constraints = node.get("constraints", {})  # 读取节点约束字典。
        for offset, name in enumerate(DOF_NAMES):  # 遍历六自由度。
            if constraints.get(name) is True:  # 检查当前自由度是否约束。
                constrained.append(base + offset)  # 保存约束自由度索引。
    constrained_array = np.asarray(sorted(set(constrained)), dtype=int)  # 去重并排序约束自由度。
    all_dofs = np.arange(dof_count, dtype=int)  # 生成全部自由度索引。
    free_array = np.setdiff1d(all_dofs, constrained_array, assume_unique=True)  # 计算自由自由度集合。
    if free_array.size == 0:  # 检查模型是否全部锁死。
        raise FrameSolveError("模型没有自由自由度。")  # 阻止无意义求解。
    if constrained_array.size == 0:  # 检查模型是否完全无约束。
        raise FrameSolveError("模型没有任何约束自由度。")  # 阻止刚体模型求解。
    if nonzero_load_count == 0:  # 检查是否施加非零荷载。
        raise FrameSolveError("选定荷载工况没有非零节点荷载。", {"loadCaseRef": selected_case})  # 阻止空荷载求解。
    reduced_stiffness = stiffness[np.ix_(free_array, free_array)]  # 提取自由自由度刚度矩阵。
    reduced_load = load_vector[free_array]  # 提取自由自由度荷载向量。
    diagonal_scale = float(np.max(np.abs(np.diag(reduced_stiffness)))) if reduced_stiffness.size else 0.0  # 计算刚度尺度。
    rank_tolerance = max(singular_tolerance * max(diagonal_scale, 1.0), np.finfo(float).eps * max(reduced_stiffness.shape) * max(diagonal_scale, 1.0))  # 构造尺度相关秩容差。
    rank = int(np.linalg.matrix_rank(reduced_stiffness, tol=rank_tolerance))  # 计算约化刚度矩阵数值秩。
    if rank < reduced_stiffness.shape[0]:  # 检查刚度矩阵是否奇异。
        singular_values = np.linalg.svd(reduced_stiffness, compute_uv=False)  # 计算奇异值用于诊断。
        raise FrameSolveError("约化刚度矩阵奇异，模型可能存在刚体模态、机构或释放错误。", {"rank": rank, "freeDofs": int(reduced_stiffness.shape[0]), "smallestSingularValues": [float(value) for value in singular_values[-min(12, len(singular_values)) :]], "tolerance": rank_tolerance})  # 返回结构化奇异性诊断。
    displacement = np.zeros(dof_count, dtype=float)  # 初始化全局位移向量。
    try:  # 捕获底层线性代数异常。
        displacement[free_array] = np.linalg.solve(reduced_stiffness, reduced_load)  # 求解自由自由度位移。
    except np.linalg.LinAlgError as error:  # 处理数值求解失败。
        raise FrameSolveError("线性方程求解失败。", {"error": str(error)}) from error  # 转换为统一异常。
    reaction = stiffness @ displacement - load_vector  # 通过完整平衡方程回算节点反力。
    node_results: list[dict[str, Any]] = []  # 初始化节点结果列表。
    maximum_displacement = 0.0  # 初始化最大平移模值。
    maximum_vertical_displacement = 0.0  # 初始化最大竖向位移绝对值。
    for node in mesh_nodes:  # 遍历网格节点生成结果。
        base = node_index[node["id"]] * 6  # 计算节点首自由度索引。
        node_displacement = displacement[base : base + 6]  # 提取节点六自由度位移。
        node_reaction = reaction[base : base + 6]  # 提取节点六自由度反力。
        translation_norm = float(np.linalg.norm(node_displacement[:3]))  # 计算节点平移模值。
        maximum_displacement = max(maximum_displacement, translation_norm)  # 更新最大平移模值。
        maximum_vertical_displacement = max(maximum_vertical_displacement, abs(float(node_displacement[2])))  # 更新最大竖向位移。
        node_results.append({"nodeRef": node["id"], "originalNodeRef": node.get("originalNodeRef"), "position": list(node["position"]), "displacement": [float(value) for value in node_displacement], "reaction": [float(value) for value in node_reaction], "translationMagnitude": translation_norm, "constrainedDofs": [name for name in DOF_NAMES if node.get("constraints", {}).get(name) is True]})  # 保存节点结果。
    element_results: list[dict[str, Any]] = []  # 初始化单元结果列表。
    component_metrics: dict[str, dict[str, float]] = {}  # 初始化构件响应汇总。
    maximum_axial = 0.0  # 初始化最大轴力绝对值。
    maximum_shear = 0.0  # 初始化最大剪力绝对值。
    maximum_moment = 0.0  # 初始化最大弯矩绝对值。
    for element_id, cache in element_cache.items():  # 遍历单元缓存回算局部端力。
        element_displacement_global = displacement[np.asarray(cache["dofs"], dtype=int)]  # 提取单元全局位移。
        element_displacement_local = cache["transform"] @ element_displacement_global  # 转换到单元局部位移。
        end_forces = cache["localStiffness"] @ element_displacement_local  # 计算局部节点端力。
        axial = max(abs(float(end_forces[0])), abs(float(end_forces[6])))  # 计算单元最大端轴力。
        shear = max(abs(float(end_forces[1])), abs(float(end_forces[2])), abs(float(end_forces[7])), abs(float(end_forces[8])))  # 计算单元最大端剪力。
        moment = max(abs(float(end_forces[4])), abs(float(end_forces[5])), abs(float(end_forces[10])), abs(float(end_forces[11])))  # 计算单元最大端弯矩。
        torsion = max(abs(float(end_forces[3])), abs(float(end_forces[9])))  # 计算单元最大端扭矩。
        maximum_axial = max(maximum_axial, axial)  # 更新全局最大轴力。
        maximum_shear = max(maximum_shear, shear)  # 更新全局最大剪力。
        maximum_moment = max(maximum_moment, moment)  # 更新全局最大弯矩。
        component_ref = str(cache["element"].get("componentRef"))  # 读取来源构件 ID。
        metrics = component_metrics.setdefault(component_ref, {"maxAxial": 0.0, "maxShear": 0.0, "maxMoment": 0.0, "maxTorsion": 0.0, "elementCount": 0.0})  # 获取或创建构件汇总。
        metrics["maxAxial"] = max(metrics["maxAxial"], axial)  # 更新构件最大轴力。
        metrics["maxShear"] = max(metrics["maxShear"], shear)  # 更新构件最大剪力。
        metrics["maxMoment"] = max(metrics["maxMoment"], moment)  # 更新构件最大弯矩。
        metrics["maxTorsion"] = max(metrics["maxTorsion"], torsion)  # 更新构件最大扭矩。
        metrics["elementCount"] += 1.0  # 增加构件单元数量。
        first_ref, second_ref = cache["element"]["nodeRefs"]  # 读取单元节点引用。
        midpoint = (np.asarray(node_lookup[first_ref]["position"], dtype=float) + np.asarray(node_lookup[second_ref]["position"], dtype=float)) * 0.5  # 计算单元中点。
        element_results.append({"elementRef": element_id, "componentRef": component_ref, "nodeRefs": [first_ref, second_ref], "midpoint": [float(value) for value in midpoint], "length": float(cache["length"]), "localDisplacement": [float(value) for value in element_displacement_local], "localEndForces": [float(value) for value in end_forces], "maxAxial": axial, "maxShear": shear, "maxMoment": moment, "maxTorsion": torsion, "regionRefs": list(cache["element"].get("regionRefs", []))})  # 保存单元局部结果。
    applied_force = np.zeros(3, dtype=float)  # 初始化全局外力合力。
    applied_moment = np.zeros(3, dtype=float)  # 初始化全局外力矩合量。
    support_force = np.zeros(3, dtype=float)  # 初始化支反力合力。
    support_moment = np.zeros(3, dtype=float)  # 初始化支反矩合量。
    for node in mesh_nodes:  # 遍历节点累加荷载与反力。
        base = node_index[node["id"]] * 6  # 计算节点首自由度索引。
        applied_force += load_vector[base : base + 3]  # 累加外力。
        applied_moment += load_vector[base + 3 : base + 6]  # 累加外加节点矩。
        support_force += reaction[base : base + 3]  # 累加反力。
        support_moment += reaction[base + 3 : base + 6]  # 累加反矩。
    force_balance_residual = float(np.linalg.norm(applied_force + support_force))  # 计算力平衡残差。
    force_scale = max(float(np.linalg.norm(applied_force)), 1.0)  # 计算力平衡归一化尺度。
    relative_force_balance = force_balance_residual / force_scale  # 计算相对力平衡残差。
    condition_number = float(np.linalg.cond(reduced_stiffness))  # 计算约化刚度矩阵条件数。
    elapsed = time.perf_counter() - started  # 计算求解耗时。
    global_metrics = {"maxTranslation": maximum_displacement, "maxVerticalDisplacement": maximum_vertical_displacement, "maxAxial": maximum_axial, "maxShear": maximum_shear, "maxMoment": maximum_moment, "forceBalanceResidual": force_balance_residual, "relativeForceBalanceResidual": relative_force_balance, "conditionNumber": condition_number, "dofCount": dof_count, "freeDofCount": int(free_array.size), "constrainedDofCount": int(constrained_array.size), "loadCaseRef": selected_case, "wallSeconds": elapsed}  # 汇总全局数值指标。
    if relative_force_balance > 1e-8:  # 检查反力平衡质量。
        warnings.append(f"相对力平衡残差为 {relative_force_balance:.3e}。")  # 添加平衡警告。
    if not math.isfinite(condition_number) or condition_number > 1e16:  # 检查刚度矩阵病态程度。
        warnings.append(f"约化刚度矩阵条件数较高：{condition_number:.3e}。")  # 添加病态矩阵警告。
    return {"solver": "builtin_frame3d", "solverVersion": "0.1.0", "status": "succeeded", "startedAt": utc_now(), "loadCaseRef": selected_case, "mesh": mesh, "nodeResults": node_results, "elementResults": element_results, "componentMetrics": component_metrics, "globalMetrics": global_metrics, "warnings": warnings}  # 返回完整求解结果。

"""计算预应力束即时损失、沿程力和等效节点荷载。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供指数、反余弦和平方根函数。
from typing import Any  # 提供通用 JSON 类型注解。


def _subtract(first: list[float], second: list[float]) -> list[float]:  # 计算三维向量差。
    return [float(first[index]) - float(second[index]) for index in range(3)]  # 返回逐分量差。


def _add(first: list[float], second: list[float]) -> list[float]:  # 计算三维向量和。
    return [float(first[index]) + float(second[index]) for index in range(3)]  # 返回逐分量和。


def _scale(vector: list[float], factor: float) -> list[float]:  # 对三维向量执行标量乘法。
    return [float(value) * float(factor) for value in vector]  # 返回缩放向量。


def _dot(first: list[float], second: list[float]) -> float:  # 计算三维向量点积。
    return sum(float(first[index]) * float(second[index]) for index in range(3))  # 返回点积结果。


def _norm(vector: list[float]) -> float:  # 计算三维向量范数。
    return math.sqrt(max(_dot(vector, vector), 0.0))  # 返回非负欧氏范数。


def _unit(vector: list[float]) -> list[float]:  # 归一化非零三维向量。
    length = _norm(vector)  # 计算向量长度。
    if length <= 1e-12:  # 检查路径相邻点是否重合。
        raise ValueError("预应力束路径包含重合控制点。")  # 阻止退化路径。
    return _scale(vector, 1.0 / length)  # 返回单位方向。


def _turning_angle(first_direction: list[float], second_direction: list[float]) -> float:  # 计算相邻路径段之间的转角。
    cosine = max(-1.0, min(1.0, _dot(first_direction, second_direction)))  # 限制浮点误差后的余弦值。
    return math.acos(cosine)  # 返回弧度制转角。


def analyze_prestress(system: dict[str, Any]) -> dict[str, Any]:  # 计算预应力沿程力、应力和损失分解。
    path = [point for point in system.get("path", []) if isinstance(point, dict)]  # 读取有效路径控制点。
    if len(path) < 2:  # 检查路径最少点数。
        raise ValueError("预应力束至少需要两个路径控制点。")  # 阻止空路径计算。
    positions = [[float(value) for value in point.get("position", [0.0, 0.0, 0.0])] for point in path]  # 提取控制点坐标。
    directions: list[list[float]] = []  # 初始化路径段单位方向。
    lengths: list[float] = []  # 初始化路径段长度。
    for index in range(len(positions) - 1):  # 遍历相邻控制点。
        vector = _subtract(positions[index + 1], positions[index])  # 计算路径段向量。
        length = _norm(vector)  # 计算路径段长度。
        directions.append(_unit(vector))  # 保存路径段单位方向。
        lengths.append(length)  # 保存路径段长度。
    jacking_force = system.get("jackingForce")  # 读取张拉力。
    initial_stress = system.get("initialStress")  # 读取初始应力。
    area = float(system.get("area", 0.0))  # 读取束面积。
    if area <= 0.0:  # 检查束面积。
        raise ValueError("预应力束面积必须大于零。")  # 阻止无效截面。
    if jacking_force is None and initial_stress is None:  # 检查是否提供张拉初值。
        raise ValueError("预应力束必须提供 jackingForce 或 initialStress。")  # 阻止缺失初始力。
    initial_force = float(jacking_force) if jacking_force is not None else float(initial_stress) * area  # 统一换算为初始力。
    if initial_force <= 0.0:  # 检查初始力为正。
        raise ValueError("预应力初始力必须大于零。")  # 阻止无效预应力。
    friction = float(system.get("frictionCoefficient", 0.0))  # 读取曲率摩阻系数。
    wobble = float(system.get("wobbleCoefficient", 0.0))  # 读取管道偏差系数。
    immediate_loss = float(system.get("immediateLossFactor", 0.0))  # 读取即时损失比例。
    long_term_loss = float(system.get("longTermLossFactor", 0.0))  # 读取长期损失比例。
    anchorage_slip = float(system.get("anchorageSlip", 0.0))  # 读取锚具回缩量。
    elastic_modulus = float(system.get("attributes", {}).get("tendonElasticModulus", 1.95e11))  # 读取或使用钢束弹性模量。
    total_length = sum(lengths)  # 计算束总长度。
    slip_force_loss = elastic_modulus * area * anchorage_slip / total_length if total_length > 0.0 else 0.0  # 计算均匀锚具回缩力损失近似值。
    cumulative_length = 0.0  # 初始化累计路径长度。
    cumulative_angle = 0.0  # 初始化累计转角。
    stations: list[dict[str, Any]] = []  # 初始化控制点沿程结果。
    for index, point in enumerate(path):  # 遍历所有控制点。
        if index > 0:  # 检查是否越过一个路径段。
            cumulative_length += lengths[index - 1]  # 累加路径段长度。
        if 0 < index < len(path) - 1:  # 检查当前点是否为内部转折点。
            cumulative_angle += _turning_angle(directions[index - 1], directions[index])  # 累加内部转角。
        friction_factor = math.exp(-(friction * cumulative_angle + wobble * cumulative_length))  # 计算曲率和偏差摩阻衰减。
        force_after_friction = initial_force * friction_factor  # 计算摩阻后的预应力力。
        force_after_slip = max(force_after_friction - slip_force_loss, 0.0)  # 扣除锚具回缩近似损失。
        force_after_immediate = force_after_slip * max(1.0 - immediate_loss, 0.0)  # 扣除其他即时损失。
        effective_force = force_after_immediate * max(1.0 - long_term_loss, 0.0)  # 扣除长期损失。
        stations.append({"index": index, "station": cumulative_length, "position": positions[index], "nodeRef": point.get("nodeRef"), "cumulativeAngle": cumulative_angle, "frictionFactor": friction_factor, "forceAfterFriction": force_after_friction, "forceAfterAnchorageSlip": force_after_slip, "forceAfterImmediateLoss": force_after_immediate, "effectiveForce": effective_force, "effectiveStress": effective_force / area})  # 保存当前控制点结果。
    return {"systemId": system.get("id"), "initialForce": initial_force, "area": area, "totalLength": total_length, "anchorageSlipForceLoss": slip_force_loss, "stations": stations, "lossSummary": {"frictionAtEnd": initial_force - stations[-1]["forceAfterFriction"], "anchorageSlip": min(slip_force_loss, stations[-1]["forceAfterFriction"]), "immediate": stations[-1]["forceAfterAnchorageSlip"] - stations[-1]["forceAfterImmediateLoss"], "longTerm": stations[-1]["forceAfterImmediateLoss"] - stations[-1]["effectiveForce"], "totalAtEnd": initial_force - stations[-1]["effectiveForce"]}}  # 返回完整预应力分析结果。


def equivalent_nodal_loads(system: dict[str, Any], use_effective_force: bool = True) -> list[dict[str, Any]]:  # 把折线预应力束转换为控制点等效节点力。
    analysis = analyze_prestress(system)  # 先计算沿程力。
    path = [point for point in system.get("path", []) if isinstance(point, dict)]  # 读取路径控制点。
    positions = [[float(value) for value in point.get("position", [0.0, 0.0, 0.0])] for point in path]  # 提取路径坐标。
    directions = [_unit(_subtract(positions[index + 1], positions[index])) for index in range(len(positions) - 1)]  # 计算各路径段单位方向。
    station_forces = [float(station["effectiveForce"] if use_effective_force else station["forceAfterImmediateLoss"]) for station in analysis["stations"]]  # 选择长期有效力或即时力。
    output: list[dict[str, Any]] = []  # 初始化等效节点力列表。
    first_vector = _scale(directions[0], station_forces[0])  # 计算起点沿束方向张拉作用。
    output.append({"pathIndex": 0, "nodeRef": path[0].get("nodeRef"), "position": positions[0], "force": first_vector, "kind": "anchor"})  # 保存起点锚固力。
    for index in range(1, len(path) - 1):  # 遍历内部折点。
        incoming = _scale(directions[index - 1], -station_forces[index])  # 计算前一段对节点的作用力。
        outgoing = _scale(directions[index], station_forces[index])  # 计算后一段对节点的作用力。
        resultant = _add(incoming, outgoing)  # 计算折点等效横向力。
        output.append({"pathIndex": index, "nodeRef": path[index].get("nodeRef"), "position": positions[index], "force": resultant, "kind": "deviation"})  # 保存折点等效力。
    last_vector = _scale(directions[-1], -station_forces[-1])  # 计算终点反向锚固力。
    output.append({"pathIndex": len(path) - 1, "nodeRef": path[-1].get("nodeRef"), "position": positions[-1], "force": last_vector, "kind": "anchor"})  # 保存终点锚固力。
    return output  # 返回所有等效节点力。


def prestress_as_loads(system: dict[str, Any], coordinate_system_ref: str, load_case_ref: str | None = None) -> list[dict[str, Any]]:  # 把具有 nodeRef 的等效力转换为 BSDL 节点荷载对象。
    loads: list[dict[str, Any]] = []  # 初始化 BSDL 荷载列表。
    for item in equivalent_nodal_loads(system):  # 遍历等效节点力。
        node_ref = item.get("nodeRef")  # 读取控制点节点引用。
        if not node_ref:  # 检查是否能够映射到结构节点。
            continue  # 跳过没有节点引用的控制点。
        loads.append({"id": f"load.prestress.{system.get('id')}.{item['pathIndex']}", "name": f"{system.get('name', system.get('id'))} 等效荷载 {item['pathIndex']}", "caseRef": load_case_ref or system.get("loadCaseRef"), "kind": "nodal", "targetNodeRef": node_ref, "targetComponentRef": None, "force": [float(value) for value in item["force"]], "moment": [0.0, 0.0, 0.0], "coordinateSystemRef": coordinate_system_ref, "attributes": {"sourcePrestressRef": system.get("id"), "equivalentKind": item["kind"]}})  # 保存标准 BSDL 节点荷载。
    return loads  # 返回可直接参与梁系试算的荷载列表。

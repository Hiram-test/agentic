"""把 CalculiX/Abaqus 风格 .inp 解析为仅供显示的 BSDL，并保留原生 deck 直通契约。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import hashlib  # 提供稳定短 ID 哈希。
import math  # 提供包围盒和主方向计算。
import re  # 提供关键字与参数解析。
from pathlib import Path  # 提供输入与原生 deck 路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from ..industrial.document import new_document  # 复用工业文档工厂。
from ..utils import content_hash, utc_now  # 复用内容哈希和统一时间戳。

LINE_ELEMENT_TYPES = {"S4", "B31", "T3D2"}  # 按兼容契约映射为线构件的单元类型。
MASS_ELEMENT_TYPES = {"MASS"}  # 不生成显示构件的质量单元类型。
SHELL_ELEMENT_TYPES = {"S3", "S4", "S4R", "S8", "S8R"}  # 壳单元类型集合。
SOLID_ELEMENT_TYPES = {"C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D15", "C3D20", "C3D20R"}  # 实体单元类型集合。
BEAM_ELEMENT_TYPES = {"B31", "B32", "B33"}  # 梁单元类型集合。
TRUSS_ELEMENT_TYPES = {"T3D2", "T3D3"}  # 桁架单元类型集合。
LENGTH_SCALE = 0.001  # 把 N-mm-tonne-s 的毫米长度换算为米。
MASS_SCALE = 1000.0  # 把吨换算为千克。
STRESS_SCALE = 1.0e6  # 把 N/mm² 换算为 Pa。
DENSITY_SCALE = 1.0e12  # 把 tonne/mm³ 换算为 kg/m³。
_KEYWORD_PATTERN = re.compile(r"^\s*\*([A-Z][A-Z0-9 _-]*)", re.IGNORECASE)  # 识别星号关键字行。
_PARAM_PATTERN = re.compile(r"([A-Z][A-Z0-9 _-]*)\s*=\s*([^,]+)", re.IGNORECASE)  # 识别关键字参数。


def _safe_token(value: str, prefix: str) -> str:  # 把任意 CalculiX 名称转换为 BSDL 合法 ID。
    cleaned = "".join(character if character.isalnum() else "." for character in value).strip(".")  # 清理不兼容字符。
    if not cleaned:  # 检查清理后是否为空。
        cleaned = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]  # 使用哈希生成稳定后缀。
    token = f"{prefix}.{cleaned[:96]}"  # 拼接前缀并限制长度。
    if not re.match(r"^[A-Za-z][A-Za-z0-9_.:-]{1,127}$", token):  # 检查是否满足 BSDL ID 模式。
        token = f"{prefix}.{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"  # 回退到稳定哈希 ID。
    return token[:128]  # 返回满足长度限制的稳定 ID。


def _parse_params(line: str) -> dict[str, str]:  # 解析关键字行上的逗号参数。
    params: dict[str, str] = {}  # 初始化参数字典。
    for match in _PARAM_PATTERN.finditer(line):  # 遍历所有 name=value 片段。
        params[match.group(1).strip().upper().replace(" ", "")] = match.group(2).strip().strip("'\"")  # 规范化参数名并保存值。
    return params  # 返回参数映射。


def _parse_number(value: str) -> float | None:  # 从字段安全解析浮点数。
    try:  # 捕获非法数值。
        return float(value.strip())  # 返回浮点数值。
    except (TypeError, ValueError):  # 处理空字段或非数值文本。
        return None  # 返回空表示无法解析。


def _parse_integer(value: str) -> int | None:  # 从字段安全解析整数。
    try:  # 捕获非法编号。
        return int(float(value.strip()))  # 允许 1. 形式的整数。
    except (TypeError, ValueError):  # 处理非整数文本。
        return None  # 返回空表示无法解析。


def _split_fields(line: str) -> list[str]:  # 按逗号拆分数据行并去除空白。
    return [field.strip() for field in line.split(",") if field.strip() != ""]  # 返回非空字段列表。


def _expand_generate(fields: list[str]) -> list[int]:  # 展开 NSET/ELSET GENERATE 起止步长。
    if len(fields) < 2:  # 检查最少起止字段。
        return []  # 字段不足时不展开。
    start = _parse_integer(fields[0])  # 读取起始编号。
    stop = _parse_integer(fields[1])  # 读取结束编号。
    step = _parse_integer(fields[2]) if len(fields) >= 3 else 1  # 读取可选步长。
    if start is None or stop is None or not step:  # 检查展开参数合法。
        return []  # 非法 GENERATE 行返回空。
    if step > 0:  # 处理正向步长。
        return list(range(start, stop + 1, step))  # 返回闭区间编号。
    return list(range(start, stop - 1, step))  # 返回负步长闭区间编号。


def _scale_point(point: list[float]) -> list[float]:  # 把毫米坐标换算为米。
    return [float(value) * LENGTH_SCALE for value in point]  # 返回显示用 SI 坐标。


def _bounds(points: list[list[float]]) -> tuple[list[float], list[float], list[float]]:  # 计算点集中心、尺寸和主轴端点。
    if not points:  # 处理空点集。
        return [0.0, 0.0, 0.0], [1e-6, 1e-6, 1e-6], [[0.0, 0.0, 0.0], [1e-6, 0.0, 0.0]]  # 返回安全占位几何。
    minimum = [min(point[index] for point in points) for index in range(3)]  # 计算三向最小坐标。
    maximum = [max(point[index] for point in points) for index in range(3)]  # 计算三向最大坐标。
    center = [(minimum[index] + maximum[index]) * 0.5 for index in range(3)]  # 计算包围盒中心。
    size = [max(maximum[index] - minimum[index], 1e-6) for index in range(3)]  # 计算并限制包围盒尺寸。
    longest_axis = max(range(3), key=lambda index: size[index])  # 确定最长包围盒方向。
    start = list(center)  # 初始化主轴起点。
    end = list(center)  # 初始化主轴终点。
    start[longest_axis] = minimum[longest_axis]  # 设置主轴起点坐标。
    end[longest_axis] = maximum[longest_axis]  # 设置主轴终点坐标。
    if sum((end[index] - start[index]) ** 2 for index in range(3)) <= 1e-18:  # 检查主轴是否退化。
        end[longest_axis] += 1e-6  # 添加微小长度保持拓扑合法。
    return center, size, [start, end]  # 返回包围盒和主轴端点。


def _principal_ends(points: list[list[float]]) -> list[list[float]]:  # 用第一主方向估计线构件端点。
    if len(points) < 2:  # 点数不足时回退包围盒。
        _, _, axis = _bounds(points)  # 计算包围盒主轴。
        return axis  # 返回包围盒端点。
    center = [sum(point[index] for point in points) / len(points) for index in range(3)]  # 计算点集质心。
    covariance = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]  # 初始化协方差矩阵。
    for point in points:  # 累加去中心化外积。
        delta = [point[index] - center[index] for index in range(3)]  # 计算相对质心位移。
        for row in range(3):  # 遍历矩阵行。
            for column in range(3):  # 遍历矩阵列。
                covariance[row][column] += delta[row] * delta[column]  # 累加协方差贡献。
    scale = 1.0 / max(len(points) - 1, 1)  # 计算样本协方差缩放。
    for row in range(3):  # 遍历矩阵行。
        for column in range(3):  # 遍历矩阵列。
            covariance[row][column] *= scale  # 完成协方差归一化。
    axis = [1.0, 0.0, 0.0]  # 初始化幂迭代起始向量。
    for _ in range(8):  # 执行有限次幂迭代。
        product = [sum(covariance[row][column] * axis[column] for column in range(3)) for row in range(3)]  # 计算矩阵向量积。
        norm = math.sqrt(sum(value * value for value in product)) or 1.0  # 计算向量范数。
        axis = [value / norm for value in product]  # 归一化主方向。
    projections = [sum((point[index] - center[index]) * axis[index] for index in range(3)) for point in points]  # 计算主方向投影。
    start = [center[index] + min(projections) * axis[index] for index in range(3)]  # 构造主轴起点。
    end = [center[index] + max(projections) * axis[index] for index in range(3)]  # 构造主轴终点。
    if sum((end[index] - start[index]) ** 2 for index in range(3)) <= 1e-18:  # 检查主轴是否退化。
        _, _, axis_points = _bounds(points)  # 回退到包围盒主轴。
        return axis_points  # 返回包围盒端点。
    return [start, end]  # 返回主方向端点。


def _category_for_type(element_type: str) -> tuple[str, str, str]:  # 把单元类型映射为显示类别、拓扑和分析单元。
    if element_type in BEAM_ELEMENT_TYPES:  # 处理梁单元。
        return "girder", "line", "frame3d"  # 映射为梁线构件。
    if element_type in TRUSS_ELEMENT_TYPES:  # 处理桁架单元。
        return "rod", "line", "truss3d"  # 映射为桁架线构件。
    if element_type in LINE_ELEMENT_TYPES:  # 处理契约要求的线显示类型。
        return "surface" if element_type == "S4" else "rod", "line", "shell" if element_type == "S4" else "truss3d"  # S4 仍按线拓扑显示。
    if element_type in SHELL_ELEMENT_TYPES:  # 处理其余壳单元。
        return "surface", "surface", "shell"  # 映射为面构件。
    if element_type in SOLID_ELEMENT_TYPES:  # 处理实体单元。
        return "solid_region", "solid", "solid"  # 映射为实体区域。
    return "other", "solid", "excluded"  # 未知类型仅作显示占位。


def _read_inp_lines(path: Path, seen: set[str] | None = None) -> list[tuple[Path, int, str]]:  # 读取 deck 并展开 *INCLUDE。
    file_path = path.resolve()  # 规范化当前文件路径。
    visited = seen if seen is not None else set()  # 复用或创建已读集合。
    if str(file_path) in visited:  # 阻止循环包含。
        return []  # 已读文件不再展开。
    visited.add(str(file_path))  # 记录当前文件。
    if not file_path.is_file():  # 检查文件存在。
        raise FileNotFoundError(file_path)  # 对缺失文件抛出标准异常。
    rows: list[tuple[Path, int, str]] = []  # 初始化带路径行号的文本行。
    pending = ""  # 初始化逗号续行缓冲。
    text = file_path.read_text(encoding="utf-8", errors="replace")  # 读取文本并兼容损坏字节。
    for line_number, raw_line in enumerate(text.splitlines(), start=1):  # 逐行扫描输入文件。
        line = raw_line.rstrip()  # 去除行尾空白但保留前导空格判断。
        stripped = line.strip()  # 读取去空白文本。
        if not stripped:  # 跳过空行。
            continue  # 继续下一行。
        if stripped.startswith("**"):  # 跳过 CalculiX 注释。
            continue  # 注释不参与解析。
        if pending:  # 处理上一行以逗号结束的续行。
            stripped = pending + stripped  # 拼接续行文本。
            pending = ""  # 清空续行缓冲。
        if stripped.endswith(",") and not stripped.startswith("*"):  # 检查数据行是否声明续行。
            pending = stripped  # 保存未完成数据行。
            continue  # 等待下一行补齐。
        rows.append((file_path, line_number, stripped))  # 保存完整逻辑行。
    expanded: list[tuple[Path, int, str]] = []  # 初始化展开后的行列表。
    for source, line_number, line in rows:  # 遍历当前文件逻辑行。
        match = _KEYWORD_PATTERN.match(line)  # 识别关键字。
        keyword = re.sub(r"\s+", " ", match.group(1).strip().upper()) if match else ""  # 规范化关键字名称。
        if keyword == "INCLUDE":  # 处理嵌套包含。
            params = _parse_params(line)  # 解析 INCLUDE 参数。
            included = params.get("INPUT") or params.get("FILE")  # 读取被包含文件名。
            if included:  # 检查包含路径存在。
                included_path = (source.parent / included).resolve() if not Path(included).is_absolute() else Path(included)  # 解析相对或绝对包含路径。
                expanded.extend(_read_inp_lines(included_path, visited))  # 递归展开被包含文件。
            continue  # 包含行本身不进入数据流。
        expanded.append((source, line_number, line))  # 保存普通关键字或数据行。
    return expanded  # 返回展开后的全部逻辑行。


def parse_calculix_inp(path: str | Path) -> dict[str, Any]:  # 解析 CalculiX .inp 为结构化中间表示。
    file_path = Path(path)  # 规范化输入路径。
    rows = _read_inp_lines(file_path)  # 读取并展开包含文件。
    nodes: dict[int, list[float]] = {}  # 初始化节点坐标表。
    elements: dict[int, dict[str, Any]] = {}  # 初始化单元表。
    nsets: dict[str, set[int]] = {}  # 初始化节点集。
    elsets: dict[str, set[int]] = {}  # 初始化单元集。
    materials: dict[str, dict[str, Any]] = {}  # 初始化材料表。
    sections: list[dict[str, Any]] = []  # 初始化截面与材料绑定。
    boundaries: list[dict[str, Any]] = []  # 初始化边界条件。
    cloads: list[dict[str, Any]] = []  # 初始化集中荷载。
    headings: list[str] = []  # 初始化标题文本。
    keywords: list[str] = []  # 初始化关键字顺序。
    current_keyword: str | None = None  # 初始化当前关键字上下文。
    current_params: dict[str, str] = {}  # 初始化当前关键字参数。
    current_generate = False  # 初始化 GENERATE 集合展开开关。
    current_material: str | None = None  # 初始化当前材料名称。
    current_element_type = ""  # 初始化当前单元类型。
    current_element_elset = ""  # 初始化当前单元默认 ELSET。
    for _source, _line_number, line in rows:  # 逐逻辑行解析。
        match = _KEYWORD_PATTERN.match(line)  # 识别关键字行。
        if match:  # 处理新关键字。
            current_keyword = re.sub(r"\s+", " ", match.group(1).strip().upper())  # 规范化关键字名称。
            current_params = _parse_params(line)  # 解析关键字参数。
            current_generate = bool(re.search(r"(?:^|,)\s*GENERATE\b", line, re.IGNORECASE)) or "GENERATE" in current_params  # 识别无值 GENERATE 标志。
            keywords.append(current_keyword)  # 保存关键字顺序。
            if current_keyword == "ELEMENT":  # 记录单元块上下文。
                current_element_type = current_params.get("TYPE", "").upper()  # 读取单元类型。
                current_element_elset = current_params.get("ELSET", "")  # 读取可选默认单元集。
            elif current_keyword == "MATERIAL":  # 记录材料块上下文。
                current_material = current_params.get("NAME") or current_params.get("ELSET") or f"MAT{len(materials) + 1}"  # 读取或生成材料名。
                materials.setdefault(current_material, {"name": current_material})  # 确保材料对象存在。
            elif current_keyword in {"SOLID SECTION", "SHELL SECTION", "BEAM SECTION"}:  # 记录截面绑定。
                sections.append({"kind": current_keyword, "elset": current_params.get("ELSET", ""), "material": current_params.get("MATERIAL", ""), "params": dict(current_params)})  # 保存截面到材料映射。
            continue  # 关键字行不作为数据解析。
        if current_keyword is None:  # 跳过文件开头的非关键字文本。
            continue  # 继续下一行。
        fields = _split_fields(line)  # 拆分数据字段。
        if not fields:  # 跳过空数据行。
            continue  # 继续下一行。
        if current_keyword == "HEADING":  # 收集标题文本。
            headings.append(line)  # 保存标题行。
        elif current_keyword == "NODE":  # 解析节点坐标。
            node_id = _parse_integer(fields[0])  # 读取节点号。
            if node_id is None or len(fields) < 4:  # 检查节点号和三维坐标。
                continue  # 跳过损坏节点行。
            nodes[node_id] = [float(fields[1]), float(fields[2]), float(fields[3])]  # 保存原始毫米坐标。
            nset_name = current_params.get("NSET")  # 读取可选节点集。
            if nset_name:  # 检查 NODE 行附带 NSET。
                nsets.setdefault(nset_name, set()).add(node_id)  # 把节点加入声明集合。
        elif current_keyword == "ELEMENT":  # 解析单元连接。
            element_id = _parse_integer(fields[0])  # 读取单元号。
            if element_id is None or len(fields) < 2:  # 检查单元号和至少一个节点。
                continue  # 跳过损坏单元行。
            connectivity = [value for value in (_parse_integer(field) for field in fields[1:]) if value is not None]  # 解析连接节点。
            elements[element_id] = {"id": element_id, "type": current_element_type, "nodes": connectivity, "elset": current_element_elset}  # 保存单元记录。
            if current_element_elset:  # 检查单元块声明了 ELSET。
                elsets.setdefault(current_element_elset, set()).add(element_id)  # 把单元加入默认集合。
        elif current_keyword == "NSET":  # 解析节点集。
            name = current_params.get("NSET") or current_params.get("NAME")  # 读取节点集名称。
            if not name:  # 缺少名称时无法保存。
                continue  # 跳过非法节点集。
            values = _expand_generate(fields) if current_generate else [_parse_integer(field) for field in fields]  # 展开或逐项读取编号。
            nsets.setdefault(name, set()).update(value for value in values if value is not None)  # 合并节点编号。
        elif current_keyword == "ELSET":  # 解析单元集。
            name = current_params.get("ELSET") or current_params.get("NAME")  # 读取单元集名称。
            if not name:  # 缺少名称时无法保存。
                continue  # 跳过非法单元集。
            values = _expand_generate(fields) if current_generate else [_parse_integer(field) for field in fields]  # 展开或逐项读取编号。
            elsets.setdefault(name, set()).update(value for value in values if value is not None)  # 合并单元编号。
        elif current_keyword == "ELASTIC" and current_material:  # 解析线弹性常数。
            if len(fields) >= 2:  # 检查弹性模量和泊松比字段。
                young = _parse_number(fields[0])  # 读取弹性模量。
                poisson = _parse_number(fields[1])  # 读取泊松比。
                if young is not None:  # 检查弹性模量可解析。
                    materials[current_material]["elasticModulus"] = young  # 保存原始弹性模量。
                if poisson is not None:  # 检查泊松比可解析。
                    materials[current_material]["poissonRatio"] = poisson  # 保存泊松比。
        elif current_keyword == "DENSITY" and current_material:  # 解析材料密度。
            density = _parse_number(fields[0])  # 读取密度。
            if density is not None:  # 检查密度可解析。
                materials[current_material]["density"] = density  # 保存原始密度。
        elif current_keyword == "EXPANSION" and current_material:  # 解析热膨胀系数。
            expansion = _parse_number(fields[0])  # 读取线膨胀系数。
            if expansion is not None:  # 检查膨胀系数可解析。
                materials[current_material]["thermalExpansion"] = expansion  # 保存热膨胀系数。
        elif current_keyword == "BOUNDARY":  # 解析位移约束。
            if len(fields) >= 2:  # 检查目标和自由度字段。
                first = _parse_integer(fields[1]) if len(fields) >= 2 else None  # 读取起始自由度。
                last = _parse_integer(fields[2]) if len(fields) >= 3 else first  # 读取结束自由度。
                boundaries.append({"target": fields[0], "first": first, "last": last, "value": _parse_number(fields[3]) if len(fields) >= 4 else 0.0})  # 保存边界条件。
        elif current_keyword == "CLOAD":  # 解析集中荷载。
            if len(fields) >= 3:  # 检查目标、自由度和幅值。
                cloads.append({"target": fields[0], "dof": _parse_integer(fields[1]), "magnitude": _parse_number(fields[2])})  # 保存集中荷载。
    mass_elsets = {name for name, ids in elsets.items() if ids and all(str(elements.get(element_id, {}).get("type", "")).upper() in MASS_ELEMENT_TYPES for element_id in ids)}  # 识别仅含 MASS 的单元集。
    for element in elements.values():  # 把 TYPE=MASS 的默认 ELSET 也标记为质量集。
        if str(element.get("type", "")).upper() in MASS_ELEMENT_TYPES and element.get("elset"):  # 检查质量单元默认集合。
            mass_elsets.add(str(element["elset"]))  # 把质量默认集合加入跳过名单。
    return {  # 返回结构化解析结果。
        "path": str(file_path),  # 保存源文件路径。
        "heading": " ".join(headings).strip(),  # 合并标题文本。
        "keywords": keywords,  # 保存关键字顺序。
        "nodes": nodes,  # 保存节点表。
        "elements": elements,  # 保存单元表。
        "nsets": {name: sorted(values) for name, values in nsets.items()},  # 保存排序后的节点集。
        "elsets": {name: sorted(values) for name, values in elsets.items()},  # 保存排序后的单元集。
        "materials": materials,  # 保存材料表。
        "sections": sections,  # 保存截面绑定。
        "boundaries": boundaries,  # 保存边界条件。
        "cloads": cloads,  # 保存集中荷载。
        "massElsets": sorted(mass_elsets),  # 保存应跳过显示的质量集合。
        "stats": {"nodes": len(nodes), "elements": len(elements), "nsets": len(nsets), "elsets": len(elsets), "materials": len(materials), "keywords": len(keywords)},  # 汇总解析统计。
    }  # 完成解析结果构造。


def _display_groups(parsed: dict[str, Any]) -> list[dict[str, Any]]:  # 按 ELSET 或单元类型构造显示分组。
    elements: dict[int, dict[str, Any]] = parsed["elements"]  # 读取单元表。
    mass_elsets = set(parsed.get("massElsets", []))  # 读取质量集合跳过名单。
    assigned: set[int] = set()  # 初始化已分组单元。
    groups: list[dict[str, Any]] = []  # 初始化显示分组。
    for name, element_ids in parsed.get("elsets", {}).items():  # 优先按命名单元集分组。
        if name in mass_elsets:  # 跳过 MASS 集合。
            continue  # 质量集不进入显示构件。
        live_ids = [element_id for element_id in element_ids if element_id in elements and str(elements[element_id].get("type", "")).upper() not in MASS_ELEMENT_TYPES]  # 过滤质量单元。
        if not live_ids:  # 跳过空集合。
            continue  # 继续下一集合。
        types = sorted({str(elements[element_id].get("type", "")).upper() for element_id in live_ids})  # 收集集合内单元类型。
        groups.append({"name": name, "elementIds": live_ids, "types": types, "source": "elset"})  # 保存 ELSET 显示分组。
        assigned.update(live_ids)  # 标记这些单元已分组。
    leftovers: dict[str, list[int]] = {}  # 初始化未分组单元按类型归类。
    for element_id, element in elements.items():  # 遍历全部单元。
        element_type = str(element.get("type", "")).upper()  # 读取单元类型。
        if element_id in assigned or element_type in MASS_ELEMENT_TYPES:  # 跳过已分组和质量单元。
            continue  # 继续下一单元。
        leftovers.setdefault(element_type or "UNKNOWN", []).append(element_id)  # 按类型归入剩余分组。
    for element_type, element_ids in leftovers.items():  # 为剩余类型创建显示分组。
        groups.append({"name": f"TYPE_{element_type}", "elementIds": element_ids, "types": [element_type], "source": "element_type"})  # 保存类型分组。
    return groups  # 返回全部显示分组。


def _group_points(parsed: dict[str, Any], element_ids: list[int]) -> list[list[float]]:  # 收集分组单元的显示坐标。
    nodes: dict[int, list[float]] = parsed["nodes"]  # 读取节点表。
    elements: dict[int, dict[str, Any]] = parsed["elements"]  # 读取单元表。
    points: list[list[float]] = []  # 初始化点列表。
    seen: set[int] = set()  # 初始化节点去重集合。
    for element_id in element_ids:  # 遍历分组单元。
        element = elements.get(element_id)  # 读取单元记录。
        if not isinstance(element, dict):  # 跳过缺失单元。
            continue  # 继续下一单元。
        for node_id in element.get("nodes", []):  # 遍历连接节点。
            if node_id in seen or node_id not in nodes:  # 跳过重复或缺失节点。
                continue  # 继续下一节点。
            seen.add(node_id)  # 记录已使用节点。
            points.append(_scale_point(nodes[node_id]))  # 保存换算后的显示坐标。
    return points  # 返回分组显示点。


def _constraint_from_dofs(first: int | None, last: int | None) -> dict[str, bool]:  # 把 CalculiX 自由度范围映射为六约束。
    names = ["ux", "uy", "uz", "rx", "ry", "rz"]  # 定义自由度名称顺序。
    constraints = {name: False for name in names}  # 初始化全部自由。
    if first is None:  # 缺少起始自由度时不约束。
        return constraints  # 返回空约束。
    stop = last if last is not None else first  # 解析结束自由度。
    low, high = sorted((first, stop))  # 规范化范围方向。
    for dof in range(low, high + 1):  # 遍历 inclusive 自由度。
        if 1 <= dof <= 6:  # 检查结构自由度范围。
            constraints[names[dof - 1]] = True  # 标记对应约束。
    return constraints  # 返回六自由度约束。


def _resolve_nset(parsed: dict[str, Any], target: str) -> list[int]:  # 把边界或荷载目标解析为节点号。
    node_id = _parse_integer(target)  # 尝试把目标当作节点号。
    if node_id is not None and node_id in parsed["nodes"]:  # 检查目标是已定义节点。
        return [node_id]  # 返回单节点。
    return list(parsed.get("nsets", {}).get(target, []))  # 返回同名节点集。


def build_bsdl_from_calculix_inp(path: str | Path, native_deck_path: str | Path | None = None, artifact_uri: str | Path | None = None, project_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:  # 从 .inp 生成仅供显示的 BSDL 并声明原生 deck 直通。
    file_path = Path(path).resolve()  # 规范化源 deck 路径。
    if not file_path.is_file():  # 检查输入文件存在。
        raise FileNotFoundError(file_path)  # 对缺失文件抛出标准异常。
    parsed = parse_calculix_inp(file_path)  # 解析 CalculiX 关键字输入。
    if not parsed["nodes"] and not parsed["elements"]:  # 检查文件是否包含可识别网格。
        raise ValueError(f"CalculiX .inp 不包含可解析的 *NODE/*ELEMENT：{file_path}")  # 对空 deck 给出明确错误。
    native_path = Path(native_deck_path).resolve() if native_deck_path else file_path  # 解析原生 deck 保存路径。
    artifact_path = Path(artifact_uri).resolve() if artifact_uri else native_path  # 解析产物 URI。
    stable_project_id = project_id or f"project.inp.{content_hash({'path': file_path.name, 'nodes': parsed['stats']['nodes'], 'elements': parsed['stats']['elements']})[:12]}"  # 生成稳定项目 ID。
    document = new_document(stable_project_id, file_path.stem, "由 CalculiX .inp 兼容导入的显示-only 结构描述；求解以原生 deck 直通为准。", "imported", str(artifact_path), "software.calculix_inp_importer")  # 创建工业 BSDL 基线文档。
    for load_case in document.get("loadCases", []):  # 把工厂默认工况改成工业 Schema 允许的类型。
        if isinstance(load_case, dict):  # 检查工况结构。
            load_case["type"] = "static"  # 使用 Schema 枚举中的静力工况。
    document["analysisTasks"] = [{"id": "task.native", "name": "原生 CalculiX deck 直通任务", "type": "linear_static", "loadCaseRefs": [document["loadCases"][0]["id"]] if document.get("loadCases") else [], "qoi": ["displacement", "reaction"], "accuracyTarget": 0.05, "budget": {"maxElements": 5000000, "maxRuns": 20, "maxWallSeconds": 86400.0}, "status": "draft"}]  # 按契约固定分析任务 ID。
    for policy in document.get("meshPolicies", []):  # 把网格策略绑到原生任务。
        if isinstance(policy, dict):  # 检查策略结构。
            policy["taskRef"] = "task.native"  # 更新任务引用。
    for plan in document.get("solverPlans", []):  # 把求解计划绑到原生任务。
        if isinstance(plan, dict):  # 检查计划结构。
            plan["taskRef"] = "task.native"  # 更新任务引用。
    document["nodes"] = []  # 清除文档工厂占位节点。
    document["components"] = []  # 清除文档工厂占位构件。
    document["materials"] = []  # 清除空材料集合以便写入换算后的显示材料。
    material_id_by_name: dict[str, str] = {}  # 初始化材料名称到 BSDL ID 映射。
    for name, material in parsed["materials"].items():  # 遍历解析到的材料。
        young = material.get("elasticModulus")  # 读取原始弹性模量。
        poisson = material.get("poissonRatio")  # 读取泊松比。
        density = material.get("density")  # 读取原始密度。
        if not isinstance(young, (int, float)) or young <= 0:  # 跳过不完整材料。
            continue  # 显示材料必须满足 Schema 正值约束。
        if not isinstance(poisson, (int, float)) or not (-0.99 <= float(poisson) <= 0.4999):  # 检查泊松比范围。
            poisson = 0.2  # 使用安全显示默认泊松比。
        if not isinstance(density, (int, float)) or density <= 0:  # 检查密度是否可用于 Schema。
            density = 7.85e-9  # 使用 N-mm-tonne 钢密度作为显示回退。
        material_id = _safe_token(name, "material.inp")  # 构造材料 ID。
        material_id_by_name[name] = material_id  # 保存名称映射。
        document["materials"].append({"id": material_id, "name": name, "model": "linear_elastic", "density": float(density) * DENSITY_SCALE, "elasticModulus": float(young) * STRESS_SCALE, "poissonRatio": float(poisson), "shearModulus": None, "thermalExpansion": material.get("thermalExpansion"), "yieldStrength": None, "plasticity": None, "creep": None, "relaxation": None, "tags": ["imported", "display_only"]})  # 写入换算后的显示材料。
    elset_material = {str(item.get("elset")): str(item.get("material")) for item in parsed.get("sections", []) if item.get("elset") and item.get("material")}  # 建立 ELSET 到材料名映射。
    groups = _display_groups(parsed)  # 构造显示分组。
    root_id = "component.inp.root"  # 定义导入根构件 ID。
    all_points = [_scale_point(point) for point in parsed["nodes"].values()]  # 换算全部节点用于根包围盒。
    root_center, root_size, _root_axis = _bounds(all_points)  # 计算整体包围盒。
    document["components"].append({"id": root_id, "name": file_path.stem, "category": "bridge", "topology": "solid", "parentRef": None, "nodeRefs": [], "materialRef": None, "sectionRef": None, "geometry": {"kind": "box", "center": root_center, "size": root_size, "rotation": [0.0, 0.0, 0.0]}, "analysis": {"elementType": "excluded", "active": False, "localUp": None, "finiteElementModelRef": None, "shellSectionRef": None, "solidSectionRef": None}, "attributes": {"displayOnly": True, "nativeDeck": True}, "featureDescriptors": {"nodeCount": float(parsed["stats"]["nodes"]), "elementCount": float(parsed["stats"]["elements"])}, "tags": ["imported", "calculix", "display_only"], "sourceIds": {"inpFile": file_path.name}})  # 创建显示根构件。
    node_by_coordinate: dict[tuple[float, float, float], str] = {}  # 初始化显示节点去重。
    skipped_mass_groups = 0  # 统计因 MASS 跳过的集合。
    for sequence, group in enumerate(groups, start=1):  # 遍历显示分组。
        points = _group_points(parsed, group["elementIds"])  # 收集分组显示点。
        if not points:  # 跳过没有坐标的分组。
            continue  # 继续下一分组。
        types = group["types"]  # 读取分组单元类型。
        primary_type = types[0] if types else "UNKNOWN"  # 选择代表单元类型。
        if primary_type in MASS_ELEMENT_TYPES:  # 防御性跳过质量分组。
            skipped_mass_groups += 1  # 增加跳过计数。
            continue  # 质量单元不生成显示构件。
        line_like = any(element_type in LINE_ELEMENT_TYPES or element_type in BEAM_ELEMENT_TYPES or element_type in TRUSS_ELEMENT_TYPES for element_type in types)  # 判断是否按线构件显示。
        category, topology, element_type = _category_for_type(primary_type)  # 映射显示语义。
        if line_like:  # 契约：S4/B31/T3D2 及同类梁桁架显示为线。
            topology = "line"  # 强制线拓扑。
            axis_points = _principal_ends(points)  # 用主方向估计线端点。
            node_refs: list[str] = []  # 初始化线端点引用。
            for suffix, point in (("start", axis_points[0]), ("end", axis_points[1])):  # 为两端创建或复用显示节点。
                key = tuple(round(float(value), 8) for value in point)  # 构造坐标去重键。
                node_id = node_by_coordinate.get(key)  # 查找已有显示节点。
                if node_id is None:  # 检查是否需要新节点。
                    node_id = f"node.inp.{len(node_by_coordinate) + 1}.{suffix}"  # 构造稳定显示节点 ID。
                    if not re.match(r"^[A-Za-z][A-Za-z0-9_.:-]{1,127}$", node_id):  # 检查 ID 模式。
                        node_id = f"node.inp.{len(node_by_coordinate) + 1}"  # 回退到短 ID。
                    node_by_coordinate[key] = node_id  # 保存坐标映射。
                    document["nodes"].append({"id": node_id, "name": f"{group['name']} {suffix}", "position": [float(value) for value in point], "coordinateSystemRef": "cs.global", "roles": ["geometry"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported", "display_only"], "sourceIds": {"elset": group["name"]}, "attributes": {"displayOnly": True}})  # 创建显示节点。
                node_refs.append(node_id)  # 保存端点引用。
            if len(node_refs) != 2 or node_refs[0] == node_refs[1]:  # 线构件必须两个不同节点。
                continue  # 退化分组不进入文档以免验证失败。
            geometry: dict[str, Any] = {"kind": "line", "points": axis_points}  # 构造线几何代理。
        else:  # 处理面或实体显示分组。
            center, size, _axis = _bounds(points)  # 计算包围盒。
            key = tuple(round(float(value), 8) for value in center)  # 构造中心去重键。
            node_id = node_by_coordinate.get(key)  # 查找已有中心节点。
            if node_id is None:  # 检查是否需要新节点。
                node_id = f"node.inp.{len(node_by_coordinate) + 1}.center"  # 构造中心节点 ID。
                node_by_coordinate[key] = node_id  # 保存坐标映射。
                document["nodes"].append({"id": node_id, "name": f"{group['name']} center", "position": [float(value) for value in center], "coordinateSystemRef": "cs.global", "roles": ["geometry"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported", "display_only"], "sourceIds": {"elset": group["name"]}, "attributes": {"displayOnly": True}})  # 创建中心显示节点。
            node_refs = [node_id]  # 非线构件使用单代理节点。
            geometry = {"kind": "box", "center": center, "size": size, "rotation": [0.0, 0.0, 0.0]}  # 构造包围盒几何代理。
        material_name = elset_material.get(group["name"])  # 查找该集合绑定的材料。
        material_ref = material_id_by_name.get(material_name) if material_name else None  # 解析可选材料引用。
        component_id = _safe_token(group["name"], "component.inp")  # 构造构件 ID。
        if any(item.get("id") == component_id for item in document["components"]):  # 处理重名集合。
            component_id = f"{component_id}.{sequence}"  # 追加序号保持唯一。
        document["components"].append({"id": component_id, "name": group["name"], "category": category, "topology": topology, "parentRef": root_id, "nodeRefs": node_refs, "materialRef": material_ref, "sectionRef": None, "geometry": geometry, "analysis": {"elementType": "excluded" if topology != "line" else element_type, "active": False, "localUp": [0.0, 0.0, 1.0] if topology == "line" else None, "finiteElementModelRef": None, "shellSectionRef": None, "solidSectionRef": None}, "attributes": {"displayOnly": True, "calculixTypes": ",".join(types), "elementCount": len(group["elementIds"]), "source": group["source"]}, "featureDescriptors": {"elementCount": float(len(group["elementIds"]))}, "tags": ["imported", "calculix", "display_only"], "sourceIds": {"elset": group["name"], "calculixType": primary_type}})  # 创建显示构件。
    dof_names = ["ux", "uy", "uz", "rx", "ry", "rz"]  # 定义约束名称。
    for boundary in parsed.get("boundaries", []):  # 把约束投影到最近的显示节点。
        constraints = _constraint_from_dofs(boundary.get("first"), boundary.get("last"))  # 解析自由度范围。
        if not any(constraints.values()):  # 跳过空约束。
            continue  # 继续下一条边界。
        target_ids = _resolve_nset(parsed, str(boundary.get("target", "")))  # 解析目标节点号。
        for node_id in target_ids[:32]:  # 限制约束投影数量。
            raw = parsed["nodes"].get(node_id)  # 读取原始坐标。
            if raw is None:  # 跳过缺失节点。
                continue  # 继续下一目标。
            scaled = _scale_point(raw)  # 换算显示坐标。
            key = tuple(round(float(value), 8) for value in scaled)  # 构造坐标键。
            display_id = node_by_coordinate.get(key)  # 查找已有显示节点。
            if display_id is None:  # 为约束目标补一个显示节点。
                display_id = f"node.inp.bc.{node_id}"  # 使用源节点号构造 ID。
                node_by_coordinate[key] = display_id  # 保存映射。
                document["nodes"].append({"id": display_id, "name": f"BC {node_id}", "position": scaled, "coordinateSystemRef": "cs.global", "roles": ["support"], "constraints": constraints, "tags": ["imported", "support"], "sourceIds": {"calculixNode": str(node_id)}, "attributes": {"displayOnly": True}})  # 创建约束显示节点。
            else:  # 合并到已有显示节点。
                for node in document["nodes"]:  # 查找目标节点对象。
                    if node.get("id") == display_id:  # 匹配显示节点。
                        existing = node.setdefault("constraints", {name: False for name in dof_names})  # 读取已有约束。
                        for name in dof_names:  # 合并约束标志。
                            existing[name] = bool(existing.get(name)) or constraints[name]  # 按或逻辑合并。
                        roles = node.setdefault("roles", [])  # 读取角色列表。
                        if "support" not in roles:  # 补充支承角色。
                            roles.append("support")  # 标记为支承节点。
                        break  # 结束该显示节点更新。
    if not document["nodes"]:  # 检查是否生成了任何显示节点。
        document["nodes"].append({"id": "node.inp.origin", "name": "导入原点", "position": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "roles": ["geometry"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["placeholder"], "sourceIds": {}, "attributes": {"placeholder": True}})  # 创建安全占位节点。
    if len(document["components"]) == 1 and not groups:  # 检查除根构件外是否没有显示对象。
        document["components"][0]["nodeRefs"] = [document["nodes"][0]["id"]]  # 把根构件挂到占位节点。
    deck_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()  # 计算源 deck 内容哈希。
    artifact = {"id": "artifact.inp.native", "kind": "solver_input", "uri": str(artifact_path), "format": "inp", "hash": deck_hash, "createdAt": utc_now()}  # 构造原生输入产物。
    document["artifacts"] = [artifact]  # 写入产物清单。
    report = {  # 构造导入报告。
        "adapter": "bridge_mind.importers.calculix_inp",  # 声明导入器。
        "sourcePath": str(file_path),  # 保存源路径。
        "nativeDeckPath": str(native_path),  # 保存原生 deck 路径。
        "displayOnly": True,  # 明确 BSDL 仅供显示。
        "useNativeDeck": True,  # 声明导出与求解走原生 deck。
        "units": {"source": "N-mm-tonne-s", "display": "m-N-kg-Pa", "lengthScale": LENGTH_SCALE, "stressScale": STRESS_SCALE, "densityScale": DENSITY_SCALE, "massScale": MASS_SCALE},  # 记录单位换算。
        "skippedMassElsets": list(parsed.get("massElsets", [])),  # 列出跳过的质量集合。
        "displayGroups": len(groups),  # 记录显示分组数量。
        "skippedMassGroups": skipped_mass_groups,  # 记录额外跳过的质量分组。
        "stats": parsed["stats"],  # 附带解析统计。
        "heading": parsed.get("heading", ""),  # 附带标题。
    }  # 完成导入报告。
    document.setdefault("extensions", {})["nativeCalculiX"] = {"useNativeDeck": True, "deckPath": str(native_path), "sourcePath": str(file_path), "displayOnly": True, "units": report["units"], "stats": parsed["stats"]}  # 写入原生 deck 直通扩展。
    document["extensions"]["bridgemind:calculixInpImport"] = report  # 保存导入报告扩展。
    document["conversionReports"] = [{"id": f"conversion.inp.{deck_hash[:16]}", "adapter": "bridge_mind.importers.calculix_inp", "adapterVersion": "1.1.0", "sourceVersion": "CalculiX keyword input", "targetVersion": "BSDL Industrial 1.0.0 display-only", "createdAt": utc_now(), "mapped": {"nodes": len(document["nodes"]), "components": len(document["components"]), "materials": len(document["materials"]), "elsets": parsed["stats"]["elsets"]}, "losses": [{"category": "irreversible", "sourceRef": "task.native", "targetRef": "task.native", "path": "/extensions/nativeCalculiX", "message": "BSDL 仅为显示代理；数值求解必须直通原生 .inp。", "severity": "info", "action": "导出时复制 nativeCalculiX.deckPath，不要从 BSDL 重建 deck。"}], "blocked": False, "artifactRefs": ["artifact.inp.native"], "roundTrip": {"supported": False, "reason": "导入不把 .inp 重建为可编辑力学真相源。"}}]  # 写入转换报告。
    document["revision"]["summary"] = f"CalculiX .inp 兼容导入 {file_path.name}"  # 记录修订摘要。
    document["project"]["tags"] = ["imported", "calculix", "display_only", "native_deck"]  # 标记项目来源。
    return document, report  # 返回显示文档和导入报告。

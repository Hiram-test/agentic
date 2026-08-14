"""解析 CalculiX DAT 与 FRD 文本结果并生成可审计摘要。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供向量范数和有限值检查。
import re  # 提供科学计数法数值提取。
from pathlib import Path  # 提供结果文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。

_NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?")  # 定义浮点数识别表达式。


def _numbers(line: str) -> list[float]:  # 从一行文本中提取浮点数。
    values: list[float] = []  # 初始化数值列表。
    for token in _NUMBER_PATTERN.findall(line):  # 遍历匹配到的数值文本。
        try:  # 捕获异常格式。
            values.append(float(token.replace("D", "E").replace("d", "e")))  # 转换 Fortran D 指数和普通浮点数。
        except ValueError:  # 处理无法转换数值。
            continue  # 跳过非法数值。
    return values  # 返回提取结果。


def parse_dat(path: str | Path) -> dict[str, Any]:  # 解析 CalculiX 文本结果和收敛信息。
    result_path = Path(path)  # 规范化 DAT 路径。
    if not result_path.is_file():  # 检查文件存在。
        return {"status": "missing", "path": str(result_path), "records": [], "errors": ["DAT 文件不存在。"]}  # 返回明确缺失状态。
    lines = result_path.read_text(encoding="utf-8", errors="replace").splitlines()  # 读取 DAT 文本行。
    records: list[dict[str, Any]] = []  # 初始化数值记录。
    messages: list[str] = []  # 初始化诊断消息。
    current_section: str | None = None  # 初始化当前结果段。
    current_step: int | None = None  # 初始化当前步编号。
    for line_number, raw_line in enumerate(lines, start=1):  # 逐行扫描 DAT 文件。
        upper = raw_line.upper()  # 构造大写诊断文本。
        if "DISPLACEMENTS" in upper:  # 识别位移结果段。
            current_section = "displacement"  # 设置当前段类型。
            continue  # 继续下一行。
        if "FORCES" in upper and "NODE" in upper:  # 识别节点力或反力结果段。
            current_section = "reaction"  # 设置当前段类型。
            continue  # 继续下一行。
        if "STRESSES" in upper:  # 识别应力结果段。
            current_section = "stress"  # 设置当前段类型。
            continue  # 继续下一行。
        if "STRAINS" in upper:  # 识别应变结果段。
            current_section = "strain"  # 设置当前段类型。
            continue  # 继续下一行。
        if "STEP" in upper:  # 尝试读取当前步号。
            step_values = [int(value) for value in _numbers(raw_line) if float(value).is_integer()]  # 提取整数候选。
            if step_values:  # 检查找到步号。
                current_step = step_values[0]  # 保存首个步号。
        if "ERROR" in upper or "DIVERGEN" in upper or "SINGULAR" in upper:  # 识别求解错误和发散消息。
            messages.append(raw_line.strip())  # 保存原始诊断消息。
        values = _numbers(raw_line)  # 提取当前行数值。
        if current_section and len(values) >= 4:  # 检查是否像节点或单元结果行。
            entity_id = int(values[0]) if math.isfinite(values[0]) else None  # 使用首个数值作为实体编号。
            if entity_id is None:  # 跳过无有效实体编号的行。
                continue  # 继续下一行。
            components = values[1:]  # 保存其余分量。
            records.append({"section": current_section, "step": current_step, "entityId": entity_id, "components": components, "line": line_number})  # 保存结构化记录。
    status = "failed" if messages else "parsed"  # 根据诊断消息计算解析状态。
    return {"status": status, "path": str(result_path), "records": records, "messages": messages, "lineCount": len(lines)}  # 返回 DAT 解析结果。


def _parse_frd_record_tokens(line: str) -> tuple[int | None, list[float]]:  # 解析 FRD 结果记录的实体号和分量。
    tokens = line.split()  # 使用空白拆分常见自由格式 FRD 记录。
    if len(tokens) >= 3 and tokens[0] == "-1":  # 处理标准 -1 数据记录。
        try:  # 捕获实体号或分量格式错误。
            entity_id = int(tokens[1])  # 读取第二字段实体编号。
            components = [float(token.replace("D", "E").replace("d", "e")) for token in tokens[2:]]  # 解析剩余分量。
            return entity_id, components  # 返回标准自由格式结果。
        except ValueError:  # 处理固定宽度或异常记录。
            pass  # 继续使用数值后备解析。
    values = _numbers(line)  # 使用通用数值提取作为后备。
    if len(values) >= 3 and int(values[0]) == -1:  # 检查固定宽度 -1 记录。
        return int(values[1]), values[2:]  # 返回第二个数值作为实体号。
    return None, []  # 返回无法解析状态。


def parse_frd(path: str | Path) -> dict[str, Any]:  # 解析 FRD 中的节点位移、应力等数据块。
    result_path = Path(path)  # 规范化 FRD 路径。
    if not result_path.is_file():  # 检查文件存在。
        return {"status": "missing", "path": str(result_path), "datasets": [], "errors": ["FRD 文件不存在。"]}  # 返回明确缺失状态。
    lines = result_path.read_text(encoding="utf-8", errors="replace").splitlines()  # 读取 FRD 文本行。
    datasets: list[dict[str, Any]] = []  # 初始化数据集列表。
    current: dict[str, Any] | None = None  # 初始化当前数据集。
    for line_number, raw_line in enumerate(lines, start=1):  # 逐行扫描 FRD 文件。
        stripped = raw_line.strip()  # 去除首尾空白。
        if stripped.startswith("-4"):  # 识别数据集名称记录。
            name = stripped[2:].strip() or "UNKNOWN"  # 提取数据集名称。
            current = {"name": name, "components": [], "records": [], "startLine": line_number}  # 创建新数据集。
            datasets.append(current)  # 保存数据集。
            continue  # 继续下一行。
        if stripped.startswith("-5") and current is not None:  # 识别分量名称记录。
            component_name = stripped[2:].strip().split()[0] if stripped[2:].strip() else f"C{len(current['components']) + 1}"  # 提取分量名称。
            current["components"].append(component_name)  # 保存分量名。
            continue  # 继续下一行。
        if stripped.startswith("-3"):  # 识别数据集结束记录。
            current = None  # 清除当前数据集。
            continue  # 继续下一行。
        if current is not None and stripped.startswith("-1"):  # 处理数据记录。
            entity_id, components = _parse_frd_record_tokens(stripped)  # 解析实体编号和分量。
            if entity_id is not None and components:  # 检查记录有效。
                current["records"].append({"entityId": entity_id, "components": components, "line": line_number})  # 保存数据记录。
    return {"status": "parsed", "path": str(result_path), "datasets": datasets, "lineCount": len(lines)}  # 返回 FRD 解析结果。


def summarize_results(dat_result: dict[str, Any] | None = None, frd_result: dict[str, Any] | None = None) -> dict[str, Any]:  # 汇总 DAT 与 FRD 解析结果中的关键数量级。
    dat_payload = dat_result or {"records": [], "messages": []}  # 规范化 DAT 输入。
    frd_payload = frd_result or {"datasets": []}  # 规范化 FRD 输入。
    maxima: dict[str, float] = {}  # 初始化各结果类型最大范数。
    counts: dict[str, int] = {}  # 初始化各结果类型记录数。
    for record in dat_payload.get("records", []):  # 遍历 DAT 记录。
        section = str(record.get("section", "unknown"))  # 读取结果类型。
        components = [float(value) for value in record.get("components", []) if isinstance(value, (int, float))]  # 读取数值分量。
        norm = math.sqrt(sum(value * value for value in components)) if components else 0.0  # 计算分量范数。
        maxima[section] = max(maxima.get(section, 0.0), norm)  # 更新最大范数。
        counts[section] = counts.get(section, 0) + 1  # 累加记录数量。
    for dataset in frd_payload.get("datasets", []):  # 遍历 FRD 数据集。
        name = str(dataset.get("name", "unknown")).strip().lower()  # 规范化数据集名称。
        for record in dataset.get("records", []):  # 遍历数据集记录。
            components = [float(value) for value in record.get("components", []) if isinstance(value, (int, float))]  # 读取数值分量。
            norm = math.sqrt(sum(value * value for value in components)) if components else 0.0  # 计算分量范数。
            maxima[name] = max(maxima.get(name, 0.0), norm)  # 更新数据集最大范数。
            counts[name] = counts.get(name, 0) + 1  # 累加数据集记录数。
    return {"status": "failed" if dat_payload.get("messages") else "parsed", "maxima": maxima, "counts": counts, "diagnostics": list(dat_payload.get("messages", [])), "datPath": dat_payload.get("path"), "frdPath": frd_payload.get("path")}  # 返回统一摘要。

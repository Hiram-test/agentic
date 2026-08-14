"""解析 CalculiX DAT 文本并生成 BSDL Industrial ResultSet 摘要。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import hashlib  # 提供真实 SHA-256 内容哈希。
import json  # 提供 ID 映射文件读取。
import math  # 提供向量模长计算。
import re  # 提供科学计数法数值解析。
from pathlib import Path  # 提供结果文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from ..utils import content_hash, utc_now  # 复用稳定哈希和统一时间戳。

_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?")  # 定义兼容 D/E 指数的数值模式。


def _numbers(line: str) -> list[float]:  # 从一行文本提取全部浮点数。
    return [float(value.replace("D", "E").replace("d", "e")) for value in _NUMBER.findall(line)]  # 返回标准浮点数组。


def _load_id_map(path: str | Path | None) -> dict[str, dict[int, str]]:  # 读取 CalculiX 数值 ID 到 BSDL ID 的反向映射。
    if path is None:  # 处理未提供映射文件。
        return {"nodes": {}, "elements": {}}  # 返回空映射。
    candidate = Path(path)  # 规范化映射文件路径。
    if not candidate.is_file():  # 检查映射文件是否存在。
        return {"nodes": {}, "elements": {}}  # 缺失时返回空映射并保留数值 ID。
    payload = json.loads(candidate.read_text(encoding="utf-8"))  # 读取 JSON 映射文件。
    nodes = {int(number): str(reference) for reference, number in payload.get("nodes", {}).items()}  # 反转节点编号映射。
    elements = {int(number): str(reference) for reference, number in payload.get("elements", {}).items()}  # 反转单元编号映射。
    return {"nodes": nodes, "elements": elements}  # 返回节点和单元反向映射。


def _section_name(line: str) -> str | None:  # 根据 CalculiX DAT 标题识别结果区段。
    text = line.strip().lower()  # 规范化标题文本。
    if "displacement" in text:  # 检查位移标题。
        return "displacement"  # 返回位移区段。
    if "reaction" in text or ("forces" in text and "node" in text):  # 检查反力或节点力标题。
        return "reaction"  # 返回反力区段。
    if "stress" in text and "contact" not in text:  # 检查应力标题。
        return "stress"  # 返回应力区段。
    if "strain" in text:  # 检查应变标题。
        return "strain"  # 返回应变区段。
    if "contact" in text and ("stress" in text or "cstr" in text):  # 检查接触应力标题。
        return "contact_stress"  # 返回接触应力区段。
    if "contact" in text and ("displacement" in text or "cdis" in text):  # 检查接触位移标题。
        return "contact_displacement"  # 返回接触位移区段。
    return None  # 未识别标题时返回空。


def _magnitude(values: list[float]) -> float:  # 计算结果向量的欧氏模长。
    return math.sqrt(sum(float(value) * float(value) for value in values))  # 返回非负模长。


def _summary(rows: list[dict[str, Any]], component_count: int) -> dict[str, Any]:  # 计算结果区段的数量、极值和控制位置。
    if not rows:  # 处理空结果区段。
        return {"count": 0, "maximumMagnitude": None, "maximumAbsoluteComponents": [], "controllingRef": None}  # 返回空摘要。
    components = [0.0 for _ in range(component_count)]  # 初始化逐分量最大绝对值。
    controlling = max(rows, key=lambda item: float(item.get("magnitude", 0.0)))  # 查找模长控制行。
    for row in rows:  # 遍历全部结果行。
        for index, value in enumerate(row.get("values", [])[:component_count]):  # 遍历目标分量。
            components[index] = max(components[index], abs(float(value)))  # 更新逐分量最大绝对值。
    return {"count": len(rows), "maximumMagnitude": float(controlling.get("magnitude", 0.0)), "maximumAbsoluteComponents": components, "controllingRef": controlling.get("reference"), "controllingNumericId": controlling.get("numericId")}  # 返回完整摘要。


def parse_dat(dat_path: str | Path, id_map_path: str | Path | None = None) -> dict[str, Any]:  # 解析 CalculiX DAT 中的节点、单元和接触结果摘要。
    path = Path(dat_path).resolve()  # 规范化 DAT 文件路径。
    if not path.is_file():  # 检查结果文件存在。
        raise FileNotFoundError(path)  # 抛出明确文件缺失错误。
    id_map = _load_id_map(id_map_path)  # 读取数值 ID 反向映射。
    rows: dict[str, list[dict[str, Any]]] = {"displacement": [], "reaction": [], "stress": [], "strain": [], "contact_stress": [], "contact_displacement": []}  # 初始化各结果区段。
    current: str | None = None  # 初始化当前解析区段。
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():  # 逐行读取 DAT 文本。
        detected = _section_name(raw_line)  # 尝试识别新标题。
        if detected is not None:  # 检查是否进入新结果区段。
            current = detected  # 更新当前结果区段。
            continue  # 标题行不按数值行解析。
        if current is None:  # 检查是否尚未进入结果区段。
            continue  # 跳过其他日志文本。
        values = _numbers(raw_line)  # 提取当前行数值。
        if current in {"displacement", "reaction"}:  # 处理节点三分量结果。
            if len(values) < 4 or int(values[0]) != values[0]:  # 检查节点号和三个结果分量。
                continue  # 跳过列标题或不完整行。
            numeric_id = int(values[0])  # 读取节点数值 ID。
            vector = [float(value) for value in values[1:4]]  # 读取三个平移或力分量。
            rows[current].append({"numericId": numeric_id, "reference": id_map["nodes"].get(numeric_id, f"ccx.node.{numeric_id}"), "values": vector, "magnitude": _magnitude(vector)})  # 保存节点结果行。
            continue  # 完成当前数值行。
        if current in {"stress", "strain"}:  # 处理单元六分量结果。
            if len(values) < 7 or int(values[0]) != values[0]:  # 检查单元号和至少六个分量。
                continue  # 跳过列标题或不完整行。
            numeric_id = int(values[0])  # 读取单元数值 ID。
            offset = 2 if len(values) >= 8 and int(values[1]) == values[1] else 1  # 兼容带积分点编号的输出行。
            tensor = [float(value) for value in values[offset : offset + 6]]  # 读取六个对称张量分量。
            if len(tensor) < 6:  # 检查张量列完整性。
                continue  # 跳过不完整行。
            rows[current].append({"numericId": numeric_id, "reference": id_map["elements"].get(numeric_id, f"ccx.element.{numeric_id}"), "integrationPoint": int(values[1]) if offset == 2 else None, "values": tensor, "magnitude": _magnitude(tensor)})  # 保存单元结果行。
            continue  # 完成当前数值行。
        if current in {"contact_stress", "contact_displacement"}:  # 处理接触结果的可变列数据。
            if len(values) < 2:  # 检查最小数值列。
                continue  # 跳过不完整行。
            numeric_id = int(values[0]) if int(values[0]) == values[0] else len(rows[current]) + 1  # 读取或生成接触行编号。
            vector = [float(value) for value in values[1:]]  # 保存剩余接触结果分量。
            rows[current].append({"numericId": numeric_id, "reference": f"ccx.contact.{numeric_id}", "values": vector, "magnitude": _magnitude(vector)})  # 保存接触结果行。
    summaries = {"displacement": _summary(rows["displacement"], 3), "reaction": _summary(rows["reaction"], 3), "stress": _summary(rows["stress"], 6), "strain": _summary(rows["strain"], 6), "contactStress": _summary(rows["contact_stress"], max((len(item["values"]) for item in rows["contact_stress"]), default=0)), "contactDisplacement": _summary(rows["contact_displacement"], max((len(item["values"]) for item in rows["contact_displacement"]), default=0))}  # 计算全部结果摘要。
    return {"format": "calculix_dat", "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": rows, "summaries": summaries, "parsedAt": utc_now()}  # 返回解析结果和审计哈希。


def build_result_set(parsed: dict[str, Any], run_ref: str, task_ref: str, coordinate_system_ref: str | None, load_case_ref: str | None = None, stage_ref: str | None = None, artifact_ref: str | None = None) -> dict[str, Any]:  # 把 DAT 摘要封装为 BSDL ResultSet。
    summaries = parsed.get("summaries", {})  # 读取解析摘要。
    fields: list[dict[str, Any]] = []  # 初始化结果字段目录。
    definitions = [("displacement", "node", ["U1", "U2", "U3"], "m"), ("reaction", "node", ["RF1", "RF2", "RF3"], "N"), ("stress", "integration_point", ["S11", "S22", "S33", "S12", "S13", "S23"], "Pa"), ("strain", "integration_point", ["E11", "E22", "E33", "E12", "E13", "E23"], "1"), ("contactStress", "surface", ["CSTR"], "Pa"), ("contactDisplacement", "surface", ["CDIS"], "m")]  # 定义标准字段映射。
    for name, location, components, unit in definitions:  # 遍历字段定义。
        summary = summaries.get(name, {})  # 读取对应摘要。
        if int(summary.get("count", 0) or 0) <= 0:  # 检查字段是否包含有效数据。
            continue  # 跳过空字段。
        fields.append({"name": name, "location": location, "components": components, "unit": unit, "coordinateSystemRef": coordinate_system_ref, "artifactRef": artifact_ref, "summary": summary})  # 保存 BSDL 结果字段。
    result_id = f"result.calculix.{content_hash({'run': run_ref, 'path': parsed.get('path')})[:16]}"  # 构造稳定结果集 ID。
    return {"id": result_id, "name": "CalculiX DAT 结果摘要", "runRef": run_ref, "taskRef": task_ref, "loadCaseRef": load_case_ref, "stageRef": stage_ref, "fields": fields, "artifactRefs": [artifact_ref] if artifact_ref else [], "status": "complete" if fields else "partial", "createdAt": utc_now()}  # 返回 Schema 兼容结果集。

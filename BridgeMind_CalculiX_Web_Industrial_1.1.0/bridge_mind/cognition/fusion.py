"""把多个专家的三维区域提案融合为稳定 BSDL Region。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供包围盒和距离计算。
from ..utils import content_hash  # 复用稳定内容哈希。

SOURCE_PRIORITY = {"agent": 1, "fea": 2, "human": 3, "imported": 0}  # 定义不同来源的裁决优先级。
TYPE_PRIORITY = {"support": 95, "joint": 85, "discontinuity": 80, "hotspot": 90, "boundary": 75, "user_defined": 100, "smooth": 20}  # 定义不同区域类型的网格优先级。


def _aabb(geometry: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:  # 把区域几何转换为轴对齐包围盒近似。
    kind = geometry.get("kind")  # 读取区域几何类型。
    center = np.asarray(geometry.get("center", [0.0, 0.0, 0.0]), dtype=float)  # 读取区域中心。
    if kind == "sphere":  # 处理球形区域。
        radius = float(geometry.get("radius", 0.0))  # 读取球半径。
        half = np.asarray([radius, radius, radius], dtype=float)  # 构造三个方向半尺寸。
        return center - half, center + half  # 返回球的轴对齐包围盒。
    size = np.asarray(geometry.get("size", [0.0, 0.0, 0.0]), dtype=float)  # 读取包围盒尺寸。
    rotation = np.asarray(geometry.get("rotation", [0.0, 0.0, 0.0]), dtype=float)  # 读取旋转角用于保守扩展。
    expansion = 1.0 + min(float(np.linalg.norm(rotation)), 1.0) * 0.25  # 对旋转盒做小幅保守扩展。
    half = size * 0.5 * expansion  # 计算保守半尺寸。
    return center - half, center + half  # 返回轴对齐包围盒。


def _overlap_score(first: dict[str, Any], second: dict[str, Any]) -> float:  # 计算两个区域包围盒的交并比。
    first_min, first_max = _aabb(first.get("geometry", {}))  # 计算第一个区域边界。
    second_min, second_max = _aabb(second.get("geometry", {}))  # 计算第二个区域边界。
    intersection_size = np.maximum(0.0, np.minimum(first_max, second_max) - np.maximum(first_min, second_min))  # 计算交集尺寸。
    intersection = float(np.prod(intersection_size))  # 计算交集体积。
    first_volume = float(np.prod(np.maximum(first_max - first_min, 0.0)))  # 计算第一个区域体积。
    second_volume = float(np.prod(np.maximum(second_max - second_min, 0.0)))  # 计算第二个区域体积。
    union = first_volume + second_volume - intersection  # 计算并集体积。
    return intersection / union if union > 1e-18 else 0.0  # 返回交并比。


def _center_distance_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:  # 计算中心距离相对区域尺度。
    first_min, first_max = _aabb(first.get("geometry", {}))  # 计算第一个区域边界。
    second_min, second_max = _aabb(second.get("geometry", {}))  # 计算第二个区域边界。
    first_center = (first_min + first_max) * 0.5  # 计算第一个区域中心。
    second_center = (second_min + second_max) * 0.5  # 计算第二个区域中心。
    scale = max(float(np.linalg.norm(first_max - first_min)), float(np.linalg.norm(second_max - second_min)), 1e-9)  # 计算比较尺度。
    return float(np.linalg.norm(first_center - second_center)) / scale  # 返回归一化中心距离。


def _merge_geometry(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:  # 合并两个区域为覆盖二者的轴对齐包围盒。
    first_min, first_max = _aabb(first)  # 计算第一个区域边界。
    second_min, second_max = _aabb(second)  # 计算第二个区域边界。
    lower = np.minimum(first_min, second_min)  # 计算合并下界。
    upper = np.maximum(first_max, second_max)  # 计算合并上界。
    center = (lower + upper) * 0.5  # 计算合并中心。
    size = np.maximum(upper - lower, 1e-6)  # 计算合并尺寸并避免零尺寸。
    return {"kind": "box", "center": [float(value) for value in center], "size": [float(value) for value in size], "rotation": [0.0, 0.0, 0.0]}  # 返回合并包围盒。


def _merge_pair(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:  # 合并两个语义相同的专家提案。
    first_source = str(first.get("source", "agent"))  # 读取第一个提案来源。
    second_source = str(second.get("source", "agent"))  # 读取第二个提案来源。
    source = first_source if SOURCE_PRIORITY.get(first_source, 0) >= SOURCE_PRIORITY.get(second_source, 0) else second_source  # 选择优先级更高的来源。
    status = "accepted" if source == "human" or first.get("status") == "accepted" or second.get("status") == "accepted" else ("needs_review" if first.get("status") == "needs_review" or second.get("status") == "needs_review" else "proposed")  # 合并提案状态。
    merged_attributes = dict(first.get("attributes", {}))  # 复制第一个提案属性。
    merged_attributes.update(second.get("attributes", {}))  # 用第二个提案属性补充或覆盖。
    merged_attributes["expertIds"] = sorted(set([str(first.get("expertId")), str(second.get("expertId"))] + list(merged_attributes.get("expertIds", []))))  # 保存所有参与专家 ID。
    return {"proposalId": first.get("proposalId"), "expertId": "fusion", "semanticType": first.get("semanticType"), "source": source, "geometry": _merge_geometry(first.get("geometry", {}), second.get("geometry", {})), "targetRefs": sorted(set(list(first.get("targetRefs", [])) + list(second.get("targetRefs", [])))), "active": bool(first.get("active", True) or second.get("active", True)), "meshLevel": max(int(first.get("meshLevel", 0)), int(second.get("meshLevel", 0))), "targetSize": min(float(first.get("targetSize", 1.0)), float(second.get("targetSize", 1.0))) if first.get("semanticType") != "smooth" else max(float(first.get("targetSize", 1.0)), float(second.get("targetSize", 1.0))), "elementFamily": first.get("elementFamily", second.get("elementFamily", "frame")), "amrEngine": second.get("amrEngine") if source == second_source else first.get("amrEngine"), "maxIterations": max(int(first.get("maxIterations", 0)), int(second.get("maxIterations", 0))), "reason": list(dict.fromkeys(list(first.get("reason", [])) + list(second.get("reason", [])))), "confidence": max(float(first.get("confidence", 0.0)), float(second.get("confidence", 0.0))), "status": status, "evidenceRefs": sorted(set(list(first.get("evidenceRefs", [])) + list(second.get("evidenceRefs", [])))), "attributes": merged_attributes}  # 返回融合提案。


def fuse_proposals(proposals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # 融合所有专家提案并生成稳定区域 ID。
    ordered = sorted([proposal for proposal in proposals if isinstance(proposal, dict)], key=lambda item: (-SOURCE_PRIORITY.get(str(item.get("source")), 0), -TYPE_PRIORITY.get(str(item.get("semanticType")), 0), -float(item.get("confidence", 0.0))))  # 按来源、类型和置信度排序。
    fused: list[dict[str, Any]] = []  # 初始化融合提案列表。
    merged_count = 0  # 初始化合并次数。
    for proposal in ordered:  # 遍历排序后的专家提案。
        merge_index: int | None = None  # 初始化可合并目标索引。
        for index, existing in enumerate(fused):  # 遍历已有融合提案。
            if existing.get("semanticType") != proposal.get("semanticType"):  # 只合并语义类型相同的区域。
                continue  # 继续检查下一现有区域。
            if existing.get("source") == "human" or proposal.get("source") == "human":  # 人工区域默认保持独立以保留操作边界。
                continue  # 不自动合并人工区域。
            overlap = _overlap_score(existing, proposal)  # 计算区域交并比。
            distance_ratio = _center_distance_ratio(existing, proposal)  # 计算归一化中心距离。
            shared_targets = bool(set(existing.get("targetRefs", [])).intersection(proposal.get("targetRefs", [])))  # 检查是否共享目标对象。
            if overlap >= 0.12 or (shared_targets and distance_ratio <= 0.55):  # 判断是否达到合并条件。
                merge_index = index  # 记录合并目标索引。
                break  # 停止搜索其他候选。
        if merge_index is None:  # 处理无法合并的提案。
            candidate = dict(proposal)  # 复制提案避免修改输入。
            candidate.setdefault("attributes", {})["expertIds"] = [str(proposal.get("expertId"))]  # 记录原始专家 ID。
            fused.append(candidate)  # 直接加入融合列表。
        else:  # 处理可合并提案。
            fused[merge_index] = _merge_pair(fused[merge_index], proposal)  # 合并到已有区域。
            merged_count += 1  # 增加合并计数。
    regions: list[dict[str, Any]] = []  # 初始化最终 BSDL 区域列表。
    for sequence, proposal in enumerate(fused, start=1):  # 遍历融合提案生成稳定区域。
        signature = {"semanticType": proposal.get("semanticType"), "source": proposal.get("source"), "geometry": proposal.get("geometry"), "targetRefs": sorted(proposal.get("targetRefs", [])), "experts": proposal.get("attributes", {}).get("expertIds", [])}  # 构造区域稳定签名。
        region_id = f"region.{proposal.get('source', 'agent')}.{proposal.get('semanticType', 'other')}.{content_hash(signature)[:10]}"  # 生成基于内容的稳定区域 ID。
        region = {"id": region_id, "name": f"{proposal.get('semanticType')}区域{sequence}", "semanticType": proposal.get("semanticType"), "source": proposal.get("source", "agent"), "geometry": proposal.get("geometry"), "targetRefs": list(proposal.get("targetRefs", [])), "active": bool(proposal.get("active", True)), "meshLevel": int(proposal.get("meshLevel", 0)), "targetSize": float(proposal.get("targetSize", 1.0)), "elementFamily": proposal.get("elementFamily", "frame"), "amrEngine": proposal.get("amrEngine", "rule_based"), "maxIterations": int(proposal.get("maxIterations", 0)), "reason": list(proposal.get("reason", [])), "confidence": float(proposal.get("confidence", 0.0)), "status": proposal.get("status", "proposed"), "evidenceRefs": list(proposal.get("evidenceRefs", [])), "attributes": dict(proposal.get("attributes", {}))}  # 构造符合 Schema 的区域对象。
        regions.append(region)  # 保存最终区域。
    report = {"proposalCount": len(ordered), "fusedCount": len(regions), "mergeCount": merged_count, "bySource": {source: sum(1 for region in regions if region.get("source") == source) for source in ["agent", "human", "fea", "imported"]}, "byType": {semantic_type: sum(1 for region in regions if region.get("semanticType") == semantic_type) for semantic_type in TYPE_PRIORITY}}  # 汇总融合统计。
    return regions, report  # 返回区域和融合报告。

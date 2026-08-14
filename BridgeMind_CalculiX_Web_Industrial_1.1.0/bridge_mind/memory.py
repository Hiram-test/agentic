"""把历史 BSDL 经验检索、筛选并读回为待审核的区域策略补丁。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供对数尺度相似度和有限数检查。
from typing import Any  # 提供通用 JSON 类型注解。
from .cognition.features import extract_features  # 复用结构特征提取器。
from .utils import content_hash, deep_copy, utc_now  # 复用稳定哈希、深复制和时间戳。


DESCRIPTOR_VERSION = "1.0"  # 声明经验描述符版本。


def default_memory_policy() -> dict[str, Any]:  # 返回确定性的默认经验读回策略。
    return {"enabled": True, "descriptorVersion": DESCRIPTOR_VERSION, "minSimilarity": 0.62, "minQuality": 0.45, "maxMatchesPerRegion": 3, "crossProjectOnly": True, "allowedStatuses": ["accepted", "candidate"], "applySources": ["agent"], "statusAfterApply": "needs_review", "requireAnalysisTypeMatch": True, "maxMeshLevelDelta": 2, "maxTargetSizeFactor": 2.0, "minTargetSizeRatio": 0.08, "maxTargetSizeRatio": 3.0, "minimumActionWeight": 0.35, "applyFields": ["meshLevel", "targetSizeRatio", "amrEngine", "maxIterations"]}  # 返回可直接序列化的策略对象。


def normalize_memory_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:  # 合并并约束调用方提供的经验读回策略。
    normalized = default_memory_policy()  # 从完整默认策略开始。
    if isinstance(policy, dict):  # 检查是否提供策略覆盖。
        normalized.update(deep_copy(policy))  # 合并调用方覆盖值。
    normalized["enabled"] = bool(normalized.get("enabled", True))  # 规范化启用开关。
    normalized["minSimilarity"] = max(0.0, min(1.0, float(normalized.get("minSimilarity", 0.62))))  # 约束最低相似度。
    normalized["minQuality"] = max(0.0, min(1.0, float(normalized.get("minQuality", 0.45))))  # 约束最低经验质量。
    normalized["maxMatchesPerRegion"] = max(1, min(20, int(normalized.get("maxMatchesPerRegion", 3))))  # 约束单区域最大匹配数。
    normalized["crossProjectOnly"] = bool(normalized.get("crossProjectOnly", True))  # 规范化跨项目开关。
    normalized["allowedStatuses"] = sorted({str(value) for value in normalized.get("allowedStatuses", ["accepted", "candidate"])})  # 规范化允许状态。
    normalized["applySources"] = sorted({str(value) for value in normalized.get("applySources", ["agent"])})  # 规范化允许修改的区域来源。
    normalized["statusAfterApply"] = str(normalized.get("statusAfterApply", "needs_review"))  # 规范化读回后的审核状态。
    normalized["requireAnalysisTypeMatch"] = bool(normalized.get("requireAnalysisTypeMatch", True))  # 规范化分析类型硬门槛。
    normalized["maxMeshLevelDelta"] = max(0, min(10, int(normalized.get("maxMeshLevelDelta", 2))))  # 约束网格等级最大改变量。
    normalized["maxTargetSizeFactor"] = max(1.0, float(normalized.get("maxTargetSizeFactor", 2.0)))  # 约束单次尺寸最大倍率。
    normalized["minTargetSizeRatio"] = max(1e-6, float(normalized.get("minTargetSizeRatio", 0.08)))  # 约束相对基准尺寸下限。
    normalized["maxTargetSizeRatio"] = max(normalized["minTargetSizeRatio"], float(normalized.get("maxTargetSizeRatio", 3.0)))  # 约束相对基准尺寸上限。
    normalized["minimumActionWeight"] = max(0.0, float(normalized.get("minimumActionWeight", 0.35)))  # 约束最低聚合动作权重。
    normalized["applyFields"] = sorted({str(value) for value in normalized.get("applyFields", ["meshLevel", "targetSizeRatio", "amrEngine", "maxIterations"])})  # 规范化允许读回字段。
    normalized["descriptorVersion"] = str(normalized.get("descriptorVersion", DESCRIPTOR_VERSION))  # 规范化描述符版本。
    return normalized  # 返回规范化策略。


def _safe_float(value: Any, default: float | None = None) -> float | None:  # 把任意数值安全转换为有限浮点数。
    try:  # 捕获不可转换值。
        converted = float(value)  # 执行浮点转换。
    except (TypeError, ValueError):  # 处理空值和非数值字符串。
        return default  # 返回调用方默认值。
    return converted if math.isfinite(converted) else default  # 仅接受有限数值。


def _sorted_strings(values: Any) -> list[str]:  # 把列表、集合或单值转换为稳定字符串集合。
    if values is None:  # 处理空值。
        return []  # 返回空集合。
    sequence = values if isinstance(values, (list, tuple, set)) else [values]  # 统一输入为可迭代序列。
    return sorted({str(value) for value in sequence if value is not None and str(value)})  # 返回去重排序字符串。


def _task_context(document: dict[str, Any]) -> dict[str, Any]:  # 提取与经验适用性有关的任务上下文。
    tasks = [item for item in document.get("analysisTasks", []) if isinstance(item, dict)]  # 读取分析任务。
    cases = [item for item in document.get("loadCases", []) if isinstance(item, dict)]  # 读取荷载工况。
    loads = [item for item in document.get("loads", []) if isinstance(item, dict)]  # 读取荷载对象。
    return {"analysisTypes": _sorted_strings([item.get("type") for item in tasks]), "qoi": _sorted_strings([value for item in tasks for value in item.get("qoi", [])]), "loadCaseTypes": _sorted_strings([item.get("type") for item in cases]), "loadKinds": _sorted_strings([item.get("kind") for item in loads]), "accuracyTargets": sorted(round(float(value), 8) for value in [item.get("accuracyTarget") for item in tasks] if isinstance(value, (int, float)))}  # 返回稳定任务上下文。


def _region_scale_ratio(region: dict[str, Any], median_length: float) -> float | None:  # 计算区域几何尺度相对结构中位长度的比值。
    geometry = region.get("geometry", {}) if isinstance(region.get("geometry"), dict) else {}  # 读取区域几何。
    if geometry.get("kind") == "sphere":  # 处理球形区域。
        scale = 2.0 * float(geometry.get("radius", 0.0) or 0.0)  # 使用直径作为特征尺度。
    else:  # 处理盒形或其他区域。
        size = [_safe_float(value, 0.0) or 0.0 for value in geometry.get("size", [])]  # 读取区域三个方向尺寸。
        positive = [value for value in size if value > 0.0]  # 筛选有效尺寸。
        scale = sum(positive) / len(positive) if positive else 0.0  # 使用平均边长作为特征尺度。
    return round(scale / median_length, 6) if scale > 0.0 and median_length > 0.0 else None  # 返回无量纲尺度比。


def build_region_descriptor(document: dict[str, Any], region: dict[str, Any], features: dict[str, Any] | None = None) -> dict[str, Any]:  # 把项目内区域转换为跨项目可比较的结构描述符。
    extracted = features or extract_features(document)  # 复用或计算统一结构特征。
    global_features = extracted.get("global", {}) if isinstance(extracted.get("global"), dict) else {}  # 读取全局结构特征。
    median_length = max(float(global_features.get("medianLength", 1.0) or 1.0), 1e-12)  # 获取稳定中位长度尺度。
    node_features = extracted.get("nodes", {}) if isinstance(extracted.get("nodes"), dict) else {}  # 读取节点特征索引。
    component_features = extracted.get("components", {}) if isinstance(extracted.get("components"), dict) else {}  # 读取构件特征索引。
    components = {str(item.get("id")): item for item in document.get("components", []) if isinstance(item, dict) and item.get("id")}  # 建立原始构件索引。
    target_refs = [str(value) for value in region.get("targetRefs", [])]  # 读取本地目标引用但不写入描述符。
    target_nodes = [node_features[value] for value in target_refs if value in node_features]  # 收集目标节点特征。
    target_components = [component_features[value] for value in target_refs if value in component_features]  # 收集目标构件特征。
    node_degrees = [int(item.get("degree", 0)) for item in target_nodes]  # 收集节点连接度。
    support_states = [bool(item.get("isSupport")) for item in target_nodes]  # 收集节点支承状态。
    material_counts = [int(item.get("materialCount", 0)) for item in target_nodes]  # 收集节点材料种类数。
    area_ratios = [_safe_float(item.get("sectionAreaRatio")) for item in target_nodes]  # 收集节点截面面积比。
    angle_ratios = [(_safe_float(item.get("minAngle")) or 0.0) / math.pi for item in target_nodes if _safe_float(item.get("minAngle")) is not None]  # 收集归一化最小夹角。
    local_scale_ratios = [float(item.get("localScale", median_length) or median_length) / median_length for item in target_nodes]  # 收集节点局部尺度比。
    component_length_ratios = [float(item.get("length", median_length) or median_length) / median_length for item in target_components]  # 收集构件长度比。
    component_categories = _sorted_strings([item.get("category") for item in target_components])  # 收集目标构件类别。
    component_topologies = _sorted_strings([components.get(str(item.get("id")), {}).get("topology") for item in target_components])  # 收集目标构件拓扑类型。
    element_types = _sorted_strings([item.get("elementType") for item in target_components])  # 收集目标构件分析单元类型。
    incident_categories = _sorted_strings([value for item in target_nodes for value in item.get("incidentCategories", [])])  # 收集目标节点邻接构件类别。
    constrained_dofs = _sorted_strings([value for item in target_nodes for value in item.get("constraints", [])])  # 收集目标节点约束自由度模式。
    context = _task_context(document)  # 提取分析任务上下文。
    base_size = next((float(item.get("baseSize")) for item in document.get("meshPolicies", []) if isinstance(item, dict) and isinstance(item.get("baseSize"), (int, float)) and float(item.get("baseSize")) > 0.0), median_length / 8.0)  # 读取当前基准网格尺寸。
    descriptor = {"descriptorVersion": DESCRIPTOR_VERSION, "semanticType": str(region.get("semanticType", "unknown")), "geometryKind": str(region.get("geometry", {}).get("kind", "unknown")), "elementFamily": str(region.get("elementFamily", "auto")), "analysisTypes": context["analysisTypes"], "qoi": context["qoi"], "loadCaseTypes": context["loadCaseTypes"], "loadKinds": context["loadKinds"], "projectTags": _sorted_strings(document.get("project", {}).get("tags", [])), "targetProfile": {"nodeCount": len(target_nodes), "componentCount": len(target_components), "nodeDegree": round(sum(node_degrees) / len(node_degrees), 6) if node_degrees else None, "isSupport": any(support_states) if support_states else None, "constrainedDofs": constrained_dofs, "incidentCategories": incident_categories, "componentCategories": component_categories, "componentTopologies": component_topologies, "elementTypes": element_types, "materialCount": round(sum(material_counts) / len(material_counts), 6) if material_counts else None, "sectionAreaRatio": round(max(value for value in area_ratios if value is not None), 6) if any(value is not None for value in area_ratios) else None, "minAngleRatio": round(min(angle_ratios), 6) if angle_ratios else None, "localScaleRatio": round(sum(local_scale_ratios) / len(local_scale_ratios), 6) if local_scale_ratios else None, "componentLengthRatio": round(sum(component_length_ratios) / len(component_length_ratios), 6) if component_length_ratios else None}, "regionScaleRatio": _region_scale_ratio(region, median_length), "baseSizeRatio": round(base_size / median_length, 6) if median_length > 0.0 else None}  # 构造不依赖项目 ID 和绝对坐标的描述符。
    return descriptor  # 返回跨项目区域描述符。


def descriptor_signature(descriptor: dict[str, Any]) -> str:  # 计算描述符的稳定短签名。
    return content_hash(descriptor)[:24]  # 返回便于数据库索引和显示的哈希。


def build_region_action(document: dict[str, Any], region: dict[str, Any] | None) -> dict[str, Any]:  # 把区域最终状态转换为可重放的无量纲动作。
    if region is None:  # 处理区域被删除的情况。
        return {"operation": "deactivate_region"}  # 返回只供负面记忆使用的停用动作。
    base_size = next((float(item.get("baseSize")) for item in document.get("meshPolicies", []) if isinstance(item, dict) and isinstance(item.get("baseSize"), (int, float)) and float(item.get("baseSize")) > 0.0), None)  # 读取当前网格策略基准尺寸。
    target_size = _safe_float(region.get("targetSize"), 1.0) or 1.0  # 读取区域目标尺寸。
    ratio = target_size / base_size if isinstance(base_size, (int, float)) and base_size > 0.0 else None  # 计算相对基准尺寸比。
    return {"operation": "upsert_region", "active": bool(region.get("active", True)), "meshLevel": int(region.get("meshLevel", 0)), "targetSizeRatio": round(ratio, 8) if ratio is not None else None, "targetSizeAbsolute": round(target_size, 8), "elementFamily": str(region.get("elementFamily", "auto")), "amrEngine": str(region.get("amrEngine", "rule_based")), "maxIterations": int(region.get("maxIterations", 0)), "semanticType": str(region.get("semanticType", "unknown"))}  # 返回可跨尺度重放的动作对象。


def _legacy_descriptor(record: dict[str, Any]) -> dict[str, Any]:  # 为旧版经验记录构造最低限度描述符。
    reference = record.get("after") if isinstance(record.get("after"), dict) else record.get("before")  # 选择旧经验中的区域快照。
    region = reference if isinstance(reference, dict) else {}  # 规范化区域快照。
    return {"descriptorVersion": "legacy", "semanticType": str(region.get("semanticType", "unknown")), "geometryKind": str(region.get("geometry", {}).get("kind", "unknown")), "elementFamily": str(region.get("elementFamily", "auto")), "analysisTypes": [], "qoi": [], "loadCaseTypes": [], "loadKinds": [], "projectTags": [], "targetProfile": {}, "regionScaleRatio": None, "baseSizeRatio": None}  # 返回保守旧版描述符。


def _record_descriptor(record: dict[str, Any]) -> dict[str, Any]:  # 读取新经验描述符并兼容旧版数据。
    descriptor = record.get("descriptor")  # 读取结构化描述符。
    return descriptor if isinstance(descriptor, dict) and descriptor else _legacy_descriptor(record)  # 返回新描述符或保守旧描述符。


def _record_action(record: dict[str, Any]) -> dict[str, Any]:  # 读取新经验动作并兼容旧版数据。
    action = record.get("action")  # 读取结构化动作。
    if isinstance(action, dict) and action:  # 检查新动作存在。
        return action  # 直接返回新动作。
    reference = record.get("after") if isinstance(record.get("after"), dict) else None  # 读取旧经验最终区域。
    return build_region_action({}, reference) if reference is not None else {"operation": "deactivate_region"}  # 返回兼容动作。


def _jaccard(first: Any, second: Any) -> float | None:  # 计算两个离散集合的 Jaccard 相似度。
    first_set = set(_sorted_strings(first))  # 构造第一个集合。
    second_set = set(_sorted_strings(second))  # 构造第二个集合。
    if not first_set and not second_set:  # 处理双方都缺失该特征。
        return None  # 表示该字段不参与评分。
    union = first_set | second_set  # 计算并集。
    return len(first_set & second_set) / len(union) if union else 1.0  # 返回交并比。


def _numeric_similarity(first: Any, second: Any, scale: float = 1.0) -> float | None:  # 计算普通数值字段的平滑相似度。
    left = _safe_float(first)  # 转换第一个数值。
    right = _safe_float(second)  # 转换第二个数值。
    if left is None or right is None:  # 处理任一字段缺失。
        return None  # 表示该字段不参与评分。
    return 1.0 / (1.0 + abs(left - right) / max(scale, 1e-12))  # 返回位于零到一之间的相似度。


def _ratio_similarity(first: Any, second: Any) -> float | None:  # 计算正数比例字段的对数尺度相似度。
    left = _safe_float(first)  # 转换第一个比例。
    right = _safe_float(second)  # 转换第二个比例。
    if left is None or right is None or left <= 0.0 or right <= 0.0:  # 处理缺失或非正比例。
        return None  # 表示该字段不参与评分。
    return math.exp(-abs(math.log(left / right)))  # 返回对尺度变化对称的相似度。


def _boolean_similarity(first: Any, second: Any) -> float | None:  # 计算布尔字段是否一致。
    if not isinstance(first, bool) or not isinstance(second, bool):  # 处理缺失或非布尔字段。
        return None  # 表示该字段不参与评分。
    return 1.0 if first == second else 0.0  # 返回精确一致性。


def score_experience(current: dict[str, Any], record: dict[str, Any], policy: dict[str, Any]) -> tuple[float, list[str]]:  # 计算一个历史经验对当前区域的适用相似度。
    historical = _record_descriptor(record)  # 读取历史结构描述符。
    reasons: list[str] = []  # 初始化匹配说明。
    if str(current.get("semanticType")) != str(historical.get("semanticType")):  # 检查区域语义类型硬约束。
        return 0.0, ["semantic_type_mismatch"]  # 对不同机制区域直接拒绝。
    current_family = str(current.get("elementFamily", "auto"))  # 读取当前单元族。
    historical_family = str(historical.get("elementFamily", "auto"))  # 读取历史单元族。
    if current_family != historical_family and "auto" not in {current_family, historical_family}:  # 检查单元族兼容性。
        return 0.0, ["element_family_mismatch"]  # 对不兼容离散类型直接拒绝。
    current_types = set(_sorted_strings(current.get("analysisTypes")))  # 读取当前分析类型。
    historical_types = set(_sorted_strings(historical.get("analysisTypes")))  # 读取历史分析类型。
    if policy.get("requireAnalysisTypeMatch") and current_types and historical_types and not current_types.intersection(historical_types):  # 检查分析类型硬约束。
        return 0.0, ["analysis_type_mismatch"]  # 对不同物理任务直接拒绝。
    current_profile = current.get("targetProfile", {}) if isinstance(current.get("targetProfile"), dict) else {}  # 读取当前目标结构画像。
    historical_profile = historical.get("targetProfile", {}) if isinstance(historical.get("targetProfile"), dict) else {}  # 读取历史目标结构画像。
    weighted: list[tuple[float, float, str]] = []  # 初始化字段相似度和权重。
    weighted.append((1.0, 0.24, "semanticType"))  # 记录已通过的语义类型一致性。
    weighted.append((1.0 if current_family == historical_family else 0.75, 0.08, "elementFamily"))  # 记录单元族一致性。
    comparisons = [(_jaccard(current.get("analysisTypes"), historical.get("analysisTypes")), 0.12, "analysisTypes"), (_jaccard(current.get("qoi"), historical.get("qoi")), 0.08, "qoi"), (_jaccard(current.get("loadKinds"), historical.get("loadKinds")), 0.05, "loadKinds"), (_boolean_similarity(current_profile.get("isSupport"), historical_profile.get("isSupport")), 0.10, "isSupport"), (_numeric_similarity(current_profile.get("nodeDegree"), historical_profile.get("nodeDegree"), 2.0), 0.08, "nodeDegree"), (_jaccard(current_profile.get("constrainedDofs"), historical_profile.get("constrainedDofs")), 0.08, "constrainedDofs"), (_jaccard(current_profile.get("incidentCategories"), historical_profile.get("incidentCategories")), 0.05, "incidentCategories"), (_jaccard(current_profile.get("componentCategories"), historical_profile.get("componentCategories")), 0.05, "componentCategories"), (_jaccard(current_profile.get("componentTopologies"), historical_profile.get("componentTopologies")), 0.03, "componentTopologies"), (_numeric_similarity(current_profile.get("materialCount"), historical_profile.get("materialCount"), 1.0), 0.03, "materialCount"), (_ratio_similarity(current_profile.get("sectionAreaRatio"), historical_profile.get("sectionAreaRatio")), 0.05, "sectionAreaRatio"), (_ratio_similarity(current_profile.get("localScaleRatio"), historical_profile.get("localScaleRatio")), 0.03, "localScaleRatio"), (_ratio_similarity(current.get("regionScaleRatio"), historical.get("regionScaleRatio")), 0.03, "regionScaleRatio")]  # 定义所有软匹配字段。
    for similarity, weight, name in comparisons:  # 遍历可用字段比较结果。
        if similarity is not None:  # 只使用双方都存在的字段。
            weighted.append((float(similarity), float(weight), name))  # 保存字段相似度。
    total_weight = sum(weight for _, weight, _ in weighted)  # 计算实际参与评分的权重总和。
    score = sum(value * weight for value, weight, _ in weighted) / total_weight if total_weight > 0.0 else 0.0  # 计算归一化加权相似度。
    strongest = sorted(weighted, key=lambda item: item[0] * item[1], reverse=True)[:5]  # 选择贡献最大的匹配字段。
    reasons.extend([f"{name}={value:.3f}" for value, _, name in strongest])  # 生成可审计匹配说明。
    return max(0.0, min(1.0, float(score))), reasons  # 返回规范化相似度和说明。


def _weighted_mean(values: list[tuple[float, float]]) -> float | None:  # 计算带权浮点平均值。
    usable = [(float(value), float(weight)) for value, weight in values if weight > 0.0 and math.isfinite(float(value))]  # 筛选有效值和正权重。
    total = sum(weight for _, weight in usable)  # 计算总权重。
    return sum(value * weight for value, weight in usable) / total if total > 0.0 else None  # 返回带权平均值。


def _weighted_mode(values: list[tuple[str, float]]) -> str | None:  # 计算带权离散众数。
    totals: dict[str, float] = {}  # 初始化类别权重表。
    for value, weight in values:  # 遍历类别和权重。
        if value and weight > 0.0:  # 只累计有效类别。
            totals[str(value)] = totals.get(str(value), 0.0) + float(weight)  # 累加类别权重。
    return max(sorted(totals), key=lambda key: totals[key]) if totals else None  # 返回最高权重类别并保持稳定并列裁决。


def _aggregate_action(matches: list[dict[str, Any]], current_region: dict[str, Any], base_size: float, policy: dict[str, Any]) -> dict[str, Any]:  # 聚合多个历史经验为单个受限策略动作。
    weighted_actions = [(match["action"], float(match["actionWeight"])) for match in matches]  # 收集历史动作及其有效权重。
    target_ratios = [(float(action["targetSizeRatio"]), weight) for action, weight in weighted_actions if isinstance(action.get("targetSizeRatio"), (int, float))]  # 收集相对目标尺寸。
    mesh_levels = [(float(action["meshLevel"]), weight) for action, weight in weighted_actions if isinstance(action.get("meshLevel"), (int, float))]  # 收集网格等级。
    iteration_values = [(float(action["maxIterations"]), weight) for action, weight in weighted_actions if isinstance(action.get("maxIterations"), (int, float))]  # 收集最大迭代次数。
    engine_values = [(str(action["amrEngine"]), weight) for action, weight in weighted_actions if action.get("amrEngine")]  # 收集 AMR 引擎。
    current_size = max(float(current_region.get("targetSize", base_size) or base_size), 1e-12)  # 读取当前区域目标尺寸。
    current_level = int(current_region.get("meshLevel", 0))  # 读取当前网格等级。
    proposed: dict[str, Any] = {}  # 初始化聚合动作。
    ratio = _weighted_mean(target_ratios)  # 聚合相对目标尺寸。
    if ratio is not None and "targetSizeRatio" in policy.get("applyFields", []):  # 检查是否允许尺寸读回。
        bounded_ratio = max(float(policy["minTargetSizeRatio"]), min(float(policy["maxTargetSizeRatio"]), ratio))  # 按策略约束尺寸比。
        raw_size = max(base_size * bounded_ratio, 1e-9)  # 把无量纲动作还原到当前项目尺度。
        factor = float(policy["maxTargetSizeFactor"])  # 读取单次最大尺寸倍率。
        proposed["targetSize"] = max(current_size / factor, min(current_size * factor, raw_size))  # 限制单次读回对当前策略的改动幅度。
        proposed["targetSizeRatio"] = proposed["targetSize"] / base_size if base_size > 0.0 else bounded_ratio  # 保存实际应用后的相对尺寸。
    level = _weighted_mean(mesh_levels)  # 聚合网格等级。
    if level is not None and "meshLevel" in policy.get("applyFields", []):  # 检查是否允许等级读回。
        raw_level = int(round(level))  # 把平均等级离散化。
        delta = int(policy["maxMeshLevelDelta"])  # 读取最大等级改变量。
        proposed["meshLevel"] = max(0, min(10, max(current_level - delta, min(current_level + delta, raw_level))))  # 限制网格等级变化。
    iterations = _weighted_mean(iteration_values)  # 聚合最大迭代次数。
    if iterations is not None and "maxIterations" in policy.get("applyFields", []):  # 检查是否允许迭代次数读回。
        proposed["maxIterations"] = max(0, min(100, int(round(iterations))))  # 保存受 Schema 约束的迭代次数。
    engine = _weighted_mode(engine_values)  # 聚合 AMR 引擎。
    if engine is not None and "amrEngine" in policy.get("applyFields", []):  # 检查是否允许引擎读回。
        proposed["amrEngine"] = engine  # 保存最高证据权重引擎。
    return proposed  # 返回聚合且受限的动作。


def preview_memory_readback(document: dict[str, Any], regions: list[dict[str, Any]], experiences: list[dict[str, Any]], policy: dict[str, Any] | None = None, features: dict[str, Any] | None = None, base_size: float | None = None, current_project_id: str | None = None) -> dict[str, Any]:  # 预览历史经验对当前区域的匹配和拟议动作。
    normalized = normalize_memory_policy(policy)  # 规范化经验读回策略。
    extracted = features or extract_features(document)  # 复用或计算当前结构特征。
    project_id = current_project_id or str(document.get("project", {}).get("id", ""))  # 读取当前项目 ID。
    effective_base_size = float(base_size) if isinstance(base_size, (int, float)) and float(base_size) > 0.0 else next((float(item.get("baseSize")) for item in document.get("meshPolicies", []) if isinstance(item, dict) and isinstance(item.get("baseSize"), (int, float)) and float(item.get("baseSize")) > 0.0), float(extracted.get("global", {}).get("medianLength", 1.0)) / 8.0)  # 确定当前项目基准网格尺寸。
    region_reports: list[dict[str, Any]] = []  # 初始化逐区域读回报告。
    eligible_records = [record for record in experiences if isinstance(record, dict) and record.get("scopeType") == "region" and str(record.get("status", "candidate")) in normalized["allowedStatuses"] and float(record.get("qualityScore", 0.0) or 0.0) >= normalized["minQuality"] and _record_action(record).get("operation") == "upsert_region"]  # 预筛选可读回区域经验。
    for region in regions:  # 遍历当前策略区域。
        if not isinstance(region, dict):  # 跳过非法区域对象。
            continue  # 继续检查下一区域。
        descriptor = build_region_descriptor(document, region, extracted)  # 构造当前区域跨项目描述符。
        matches: list[dict[str, Any]] = []  # 初始化当前区域候选经验。
        for record in eligible_records:  # 遍历预筛选经验。
            if normalized["crossProjectOnly"] and str(record.get("projectId", "")) == project_id:  # 检查是否禁止同项目记忆回灌。
                continue  # 跳过同项目经验。
            similarity, reasons = score_experience(descriptor, record, normalized)  # 计算结构和任务相似度。
            if similarity < normalized["minSimilarity"]:  # 检查最低相似度门槛。
                continue  # 跳过低相似度经验。
            quality = max(0.0, min(1.0, float(record.get("qualityScore", 0.0) or 0.0)))  # 读取经验质量。
            action_weight = similarity * quality  # 组合相似度和证据质量为动作权重。
            if action_weight < normalized["minimumActionWeight"]:  # 检查最低动作权重。
                continue  # 跳过证据不足的经验。
            matches.append({"experienceId": str(record.get("experienceId")), "projectId": str(record.get("projectId", "")), "similarity": round(similarity, 6), "qualityScore": round(quality, 6), "actionWeight": round(action_weight, 6), "status": str(record.get("status", "candidate")), "summary": str(record.get("summary", "")), "reasons": reasons, "action": _record_action(record), "descriptor": _record_descriptor(record)})  # 保存可审计匹配记录。
        matches.sort(key=lambda item: (-float(item["actionWeight"]), -float(item["similarity"]), str(item["experienceId"])))  # 按有效证据权重稳定排序。
        selected = matches[: int(normalized["maxMatchesPerRegion"])]  # 截取单区域允许的最大匹配数。
        proposed = _aggregate_action(selected, region, effective_base_size, normalized) if selected else {}  # 聚合历史动作。
        changed_fields = [key for key, value in proposed.items() if key != "targetSizeRatio" and value != region.get(key)]  # 识别真正会改变当前区域的字段。
        region_reports.append({"regionId": str(region.get("id")), "semanticType": str(region.get("semanticType")), "source": str(region.get("source")), "eligibleSource": str(region.get("source")) in normalized["applySources"], "descriptor": descriptor, "descriptorSignature": descriptor_signature(descriptor), "matches": selected, "matchCount": len(selected), "proposed": proposed, "changedFields": changed_fields, "wouldApply": bool(normalized["enabled"] and str(region.get("source")) in normalized["applySources"] and selected and changed_fields)})  # 保存逐区域预览结果。
    matched_count = sum(1 for item in region_reports if item["matchCount"] > 0)  # 统计存在经验匹配的区域数。
    applicable_count = sum(1 for item in region_reports if item["wouldApply"])  # 统计真正会产生补丁的区域数。
    return {"enabled": normalized["enabled"], "policy": normalized, "projectId": project_id, "baseSize": effective_base_size, "experienceCount": len(experiences), "eligibleExperienceCount": len(eligible_records), "regionCount": len(region_reports), "matchedRegionCount": matched_count, "applicableRegionCount": applicable_count, "regions": region_reports}  # 返回完整读回预览。


def apply_memory_readback(document: dict[str, Any], regions: list[dict[str, Any]], experiences: list[dict[str, Any]], policy: dict[str, Any] | None = None, features: dict[str, Any] | None = None, base_size: float | None = None, actor_id: str = "software.bridgemind") -> tuple[list[dict[str, Any]], dict[str, Any]]:  # 把通过门槛的历史经验应用为待审核区域补丁。
    preview = preview_memory_readback(document, regions, experiences, policy, features, base_size)  # 先生成完全可审计的读回预览。
    updated_regions = deep_copy(regions)  # 深复制区域列表避免修改调用方数据。
    region_index = {str(region.get("id")): region for region in updated_regions if isinstance(region, dict)}  # 建立更新区域索引。
    applied_experience_ids: list[str] = []  # 初始化实际应用经验 ID 列表。
    applied_regions: list[dict[str, Any]] = []  # 初始化实际补丁摘要。
    if preview["enabled"]:  # 检查读回总开关。
        for region_report in preview["regions"]:  # 遍历逐区域匹配报告。
            if not region_report.get("wouldApply"):  # 跳过无动作或来源不允许的区域。
                continue  # 继续检查下一区域。
            region = region_index.get(str(region_report["regionId"]))  # 定位待更新区域。
            if region is None:  # 处理区域在更新列表中缺失。
                continue  # 跳过无法定位的区域。
            before = {key: region.get(key) for key in ["meshLevel", "targetSize", "amrEngine", "maxIterations", "status"]}  # 保存补丁前关键状态。
            proposed = dict(region_report.get("proposed", {}))  # 复制聚合动作。
            proposed.pop("targetSizeRatio", None)  # 移除只用于审计的派生字段。
            for key, value in proposed.items():  # 遍历允许写回的区域字段。
                region[key] = value  # 写入聚合动作。
            region["status"] = str(preview["policy"].get("statusAfterApply", "needs_review"))  # 强制进入人工审核状态。
            experience_ids = [str(match["experienceId"]) for match in region_report.get("matches", [])]  # 收集当前补丁引用的经验 ID。
            region["evidenceRefs"] = sorted(set(list(region.get("evidenceRefs", [])) + experience_ids))  # 把经验记录挂到区域证据引用。
            attributes = dict(region.get("attributes", {}))  # 复制区域扩展属性。
            attributes["memoryReadback"] = {"descriptorVersion": DESCRIPTOR_VERSION, "descriptorSignature": region_report.get("descriptorSignature"), "experienceIds": experience_ids, "similarities": [match.get("similarity") for match in region_report.get("matches", [])], "qualityScores": [match.get("qualityScore") for match in region_report.get("matches", [])], "policy": {"minSimilarity": preview["policy"]["minSimilarity"], "minQuality": preview["policy"]["minQuality"], "crossProjectOnly": preview["policy"]["crossProjectOnly"]}, "before": before, "proposed": proposed, "appliedAt": utc_now(), "appliedBy": actor_id}  # 保存完整读回来源和补丁审计信息。
            region["attributes"] = attributes  # 写回区域扩展属性。
            top_match = region_report.get("matches", [{}])[0]  # 读取最高权重经验。
            memory_reason = f"经验读回：{top_match.get('experienceId')}，相似度 {float(top_match.get('similarity', 0.0)):.3f}，需人工与 FEA 复核。"  # 构造可读补丁理由。
            region["reason"] = list(dict.fromkeys(list(region.get("reason", [])) + [memory_reason]))  # 把经验依据加入区域理由。
            region["confidence"] = max(float(region.get("confidence", 0.0)), min(0.98, sum(float(match.get("similarity", 0.0)) * float(match.get("qualityScore", 0.0)) for match in region_report.get("matches", [])) / max(sum(float(match.get("qualityScore", 0.0)) for match in region_report.get("matches", [])), 1e-12)))  # 用历史证据提高但不夸大区域置信度。
            applied_experience_ids.extend(experience_ids)  # 汇总产品实际使用的经验 ID。
            applied_regions.append({"regionId": region_report["regionId"], "changedFields": region_report["changedFields"], "experienceIds": experience_ids, "before": before, "after": {key: region.get(key) for key in ["meshLevel", "targetSize", "amrEngine", "maxIterations", "status"]}})  # 保存实际补丁摘要。
    report = {**preview, "appliedRegionCount": len(applied_regions), "appliedExperienceIds": sorted(set(applied_experience_ids)), "appliedRegions": applied_regions}  # 扩展预览为实际应用报告。
    return updated_regions, report  # 返回更新后的区域和完整读回报告。

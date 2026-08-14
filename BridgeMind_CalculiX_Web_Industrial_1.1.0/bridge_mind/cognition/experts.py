"""桥梁局部认知与网格资源分配的规则化专家集合。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import math  # 提供角度阈值和平方根。
from typing import Any, Protocol  # 提供通用类型和专家接口协议。
import numpy as np  # 提供统计和向量计算。


class Expert(Protocol):  # 定义可替换专家统一接口。
    expert_id: str  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 定义专家提案方法。
        ...  # 由具体专家实现提案逻辑。


def _box(center: list[float], size: float | list[float]) -> dict[str, Any]:  # 构造标准三维包围盒几何。
    size_vector = [float(size), float(size), float(size)] if isinstance(size, (int, float)) else [float(value) for value in size]  # 把标量尺寸扩展为三维尺寸。
    return {"kind": "box", "center": [float(value) for value in center], "size": size_vector, "rotation": [0.0, 0.0, 0.0]}  # 返回轴对齐包围盒。


def _proposal(expert_id: str, sequence: int, semantic_type: str, center: list[float], size: float | list[float], targets: list[str], mesh_level: int, target_size: float, reason: list[str], confidence: float, source: str = "agent", status: str = "proposed", evidence_refs: list[str] | None = None, attributes: dict[str, Any] | None = None) -> dict[str, Any]:  # 构造统一 RegionProposal。
    return {"proposalId": f"proposal.{expert_id}.{sequence}", "expertId": expert_id, "semanticType": semantic_type, "source": source, "geometry": _box(center, size), "targetRefs": targets, "active": True, "meshLevel": max(0, min(10, int(mesh_level))), "targetSize": max(float(target_size), 1e-6), "elementFamily": "frame", "amrEngine": "rule_based" if source != "fea" else "gradient", "maxIterations": 4, "reason": reason, "confidence": max(0.0, min(1.0, float(confidence))), "status": status, "evidenceRefs": evidence_refs or [], "attributes": attributes or {}}  # 返回完整提案字段。


class GlobalAllocator:  # 根据全局尺度和预算确定基准尺寸。
    expert_id = "global_allocator"  # 声明专家稳定 ID。
    def allocate(self, document: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:  # 计算全局网格尺度和预算。
        median_length = float(features.get("global", {}).get("medianLength", 1.0))  # 读取中位构件长度。
        task = next((item for item in document.get("analysisTasks", []) if isinstance(item, dict)), {})  # 选择首个分析任务。
        max_elements = int(task.get("budget", {}).get("maxElements", 5000))  # 读取最大单元预算。
        active_count = max(1, int(features.get("global", {}).get("activeLineComponentCount", 1)))  # 读取活跃线构件数量。
        target_per_component = max(2.0, min(20.0, max_elements / active_count))  # 估计每构件可分配单元数。
        budget_size = median_length / target_per_component  # 按预算估计基准尺寸。
        base_size = max(median_length / 8.0, budget_size, median_length / 20.0)  # 限制基准尺寸避免过密或过粗。
        return {"expertId": self.expert_id, "baseSize": float(base_size), "medianLength": median_length, "maxElements": max_elements, "activeComponentCount": active_count, "reason": ["根据中位构件长度建立全局尺度", "根据任务 maxElements 约束平均分段数量"]}  # 返回资源分配结果。


class SupportJointExpert:  # 识别支承节点和高连接度节点。
    expert_id = "support_joint"  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 生成支承和节点区域提案。
        base_size = float(features.get("global", {}).get("medianLength", 1.0)) / 8.0  # 估计局部基准尺寸。
        proposals: list[dict[str, Any]] = []  # 初始化提案列表。
        for node_id, node_feature in features.get("nodes", {}).items():  # 遍历节点特征。
            is_support = bool(node_feature.get("isSupport"))  # 判断是否为支承节点。
            degree = int(node_feature.get("degree", 0))  # 读取节点连接度。
            if not is_support and degree < 3:  # 跳过普通二连节点和端点。
                continue  # 继续检查下一节点。
            local_scale = max(float(node_feature.get("localScale", base_size * 4.0)), base_size)  # 获取节点局部尺度。
            semantic_type = "support" if is_support else "joint"  # 根据约束状态选择区域类型。
            mesh_level = 5 if is_support else 4  # 为支承赋予更高加密等级。
            target_size = min(base_size * (0.45 if is_support else 0.6), local_scale / 6.0)  # 计算局部目标尺寸。
            reasons = [f"节点连接度为 {degree}"]  # 初始化节点识别理由。
            if is_support:  # 补充支承理由。
                reasons.append(f"约束自由度：{', '.join(node_feature.get('constraints', []))}")  # 记录约束自由度。
            if degree >= 3:  # 补充多构件交汇理由。
                reasons.append("多构件在该节点交汇")  # 记录交汇特征。
            confidence = min(0.98, 0.72 + 0.05 * degree + (0.1 if is_support else 0.0))  # 根据支承和连接度估计置信度。
            proposals.append(_proposal(self.expert_id, len(proposals) + 1, semantic_type, node_feature["position"], max(local_scale * 0.45, base_size * 2.0), [node_id] + list(node_feature.get("incidentRefs", [])), mesh_level, target_size, reasons, confidence, attributes={"nodeDegree": degree, "constraints": node_feature.get("constraints", [])}))  # 保存区域提案。
        return proposals  # 返回全部支承与节点提案。


class DiscontinuityExpert:  # 识别截面、材料和方向突变。
    expert_id = "discontinuity"  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 生成突变区域提案。
        median_length = float(features.get("global", {}).get("medianLength", 1.0))  # 读取全局中位长度。
        base_size = median_length / 8.0  # 估计全局基准尺寸。
        proposals: list[dict[str, Any]] = []  # 初始化提案列表。
        for node_id, node_feature in features.get("nodes", {}).items():  # 遍历节点特征。
            area_ratio = float(node_feature.get("sectionAreaRatio", 1.0))  # 读取截面面积比。
            material_count = int(node_feature.get("materialCount", 0))  # 读取材料种类数。
            min_angle = node_feature.get("minAngle")  # 读取最小构件夹角。
            sharp_angle = isinstance(min_angle, (int, float)) and float(min_angle) < math.radians(25.0)  # 判断是否存在锐角交汇。
            if area_ratio < 1.8 and material_count <= 1 and not sharp_angle:  # 跳过无明显突变节点。
                continue  # 继续检查下一节点。
            reasons: list[str] = []  # 初始化突变理由。
            if area_ratio >= 1.8:  # 检查截面突变。
                reasons.append(f"相邻构件截面面积比为 {area_ratio:.2f}")  # 记录截面变化。
            if material_count > 1:  # 检查材料突变。
                reasons.append(f"相邻构件包含 {material_count} 种材料")  # 记录材料变化。
            if sharp_angle:  # 检查锐角交汇。
                reasons.append(f"最小无向夹角为 {math.degrees(float(min_angle)):.1f}°")  # 记录方向突变。
            local_scale = max(float(node_feature.get("localScale", median_length)), base_size)  # 获取节点局部尺度。
            confidence = min(0.95, 0.6 + min(area_ratio / 10.0, 0.2) + 0.1 * max(0, material_count - 1) + (0.1 if sharp_angle else 0.0))  # 估计突变置信度。
            proposals.append(_proposal(self.expert_id, len(proposals) + 1, "discontinuity", node_feature["position"], max(local_scale * 0.35, base_size * 2.0), [node_id] + list(node_feature.get("incidentRefs", [])), 5, min(base_size * 0.5, local_scale / 7.0), reasons, confidence, attributes={"sectionAreaRatio": area_ratio, "materialCount": material_count, "minAngle": min_angle}))  # 保存突变区域提案。
        return proposals  # 返回全部突变提案。


class SmoothRegionExpert:  # 识别长而连续的平滑构件区段。
    expert_id = "smooth_region"  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 生成可放松网格区域提案。
        median_length = float(features.get("global", {}).get("medianLength", 1.0))  # 读取全局中位长度。
        base_size = median_length / 8.0  # 估计全局基准尺寸。
        node_features = features.get("nodes", {})  # 读取节点特征表。
        proposals: list[dict[str, Any]] = []  # 初始化提案列表。
        for component_id, component_feature in features.get("components", {}).items():  # 遍历线构件特征。
            if component_feature.get("active") is not True or float(component_feature.get("length", 0.0)) < median_length * 0.9:  # 跳过非活跃或较短构件。
                continue  # 继续检查下一构件。
            first_ref, second_ref = component_feature.get("nodeRefs", [None, None])  # 解包构件端点。
            first = node_features.get(first_ref, {})  # 读取起点特征。
            second = node_features.get(second_ref, {})  # 读取终点特征。
            if first.get("isSupport") or second.get("isSupport"):  # 避免把支承附近整体标为平滑区。
                continue  # 继续检查下一构件。
            if int(first.get("degree", 0)) > 3 or int(second.get("degree", 0)) > 3:  # 避免复杂节点邻近构件。
                continue  # 继续检查下一构件。
            direction = np.asarray(component_feature["direction"], dtype=float)  # 读取构件单位方向。
            length = float(component_feature["length"])  # 读取构件长度。
            center = np.asarray(component_feature["midpoint"], dtype=float)  # 读取构件中点。
            axis_extent = np.abs(direction) * length * 0.55 + base_size * 0.8  # 估计覆盖构件中部的轴对齐包围盒尺寸。
            transverse = np.maximum(base_size * 1.5, median_length * 0.18)  # 估计横向区域尺寸。
            size = [float(max(axis_extent[index], transverse)) for index in range(3)]  # 构造三维包围盒尺寸。
            proposals.append(_proposal(self.expert_id, len(proposals) + 1, "smooth", [float(value) for value in center], size, [component_id], 1, base_size * 1.5, ["构件长度不小于中位长度", "两端不属于支承或高连接度复杂节点", "允许在满足响应要求时放松网格"], 0.68, attributes={"componentLength": length, "baseSize": base_size}))  # 保存平滑区提案。
        return proposals  # 返回全部平滑区提案。


class FEAHotspotExpert:  # 根据快速 FEA 的局部响应识别热点区。
    expert_id = "fea_hotspot"  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 生成 FEA 热点区域提案。
        if not isinstance(fea_result, dict) or fea_result.get("status") != "succeeded":  # 检查是否存在成功求解结果。
            return []  # 无有效结果时不提出热点。
        element_results = [item for item in fea_result.get("elementResults", []) if isinstance(item, dict)]  # 收集单元响应结果。
        if not element_results:  # 检查是否有单元结果。
            return []  # 空结果不提出热点。
        moment_values = np.asarray([float(item.get("maxMoment", 0.0)) for item in element_results], dtype=float)  # 收集单元弯矩指标。
        shear_values = np.asarray([float(item.get("maxShear", 0.0)) for item in element_results], dtype=float)  # 收集单元剪力指标。
        moment_threshold = float(np.quantile(moment_values, 0.85)) if len(moment_values) > 1 else float(moment_values[0])  # 计算弯矩热点阈值。
        shear_threshold = float(np.quantile(shear_values, 0.90)) if len(shear_values) > 1 else float(shear_values[0])  # 计算剪力热点阈值。
        median_length = float(features.get("global", {}).get("medianLength", 1.0))  # 读取全局中位构件长度。
        base_size = median_length / 8.0  # 估计全局基准尺寸。
        candidates = [item for item in element_results if float(item.get("maxMoment", 0.0)) >= moment_threshold or float(item.get("maxShear", 0.0)) >= shear_threshold]  # 选择高响应单元。
        candidates.sort(key=lambda item: max(float(item.get("maxMoment", 0.0)) / max(moment_threshold, 1e-12), float(item.get("maxShear", 0.0)) / max(shear_threshold, 1e-12)), reverse=True)  # 按归一化响应强度排序。
        proposals: list[dict[str, Any]] = []  # 初始化热点提案列表。
        for item in candidates[: max(1, min(12, len(candidates)))]:  # 限制单次反馈的热点数量。
            component_ref = str(item.get("componentRef"))  # 读取来源构件 ID。
            center = item.get("midpoint", [0.0, 0.0, 0.0])  # 读取热点单元中点。
            element_length = max(float(item.get("length", base_size)), base_size)  # 获取热点局部尺度。
            moment_ratio = float(item.get("maxMoment", 0.0)) / max(moment_threshold, 1e-12)  # 计算弯矩相对阈值。
            shear_ratio = float(item.get("maxShear", 0.0)) / max(shear_threshold, 1e-12)  # 计算剪力相对阈值。
            response_ratio = max(moment_ratio, shear_ratio)  # 选择主导响应比。
            confidence = min(0.98, 0.72 + 0.08 * min(response_ratio - 1.0, 3.0))  # 根据响应超阈程度估计置信度。
            proposals.append(_proposal(self.expert_id, len(proposals) + 1, "hotspot", center, max(element_length * 1.8, base_size * 2.0), [component_ref], 6, min(base_size * 0.4, element_length / 4.0), [f"单元弯矩指标为 {float(item.get('maxMoment', 0.0)):.6g}", f"单元剪力指标为 {float(item.get('maxShear', 0.0)):.6g}", "响应位于当前网格结果高分位区"], confidence, source="fea", evidence_refs=[str(item.get("elementRef"))], attributes={"momentThreshold": moment_threshold, "shearThreshold": shear_threshold, "responseRatio": response_ratio}))  # 保存 FEA 热点提案。
        return proposals  # 返回全部热点提案。


class HumanOverrideExpert:  # 把人工区域作为不可被低优先级建议覆盖的策略输入。
    expert_id = "human_override"  # 声明专家稳定 ID。
    def propose(self, document: dict[str, Any], features: dict[str, Any], fea_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 转换人工区域为高优先级提案。
        proposals: list[dict[str, Any]] = []  # 初始化人工提案列表。
        for region in document.get("regions", []):  # 遍历已有区域。
            if not isinstance(region, dict) or region.get("source") != "human" or region.get("status") == "rejected":  # 只处理有效人工区域。
                continue  # 继续检查下一区域。
            proposal = {"proposalId": f"proposal.{self.expert_id}.{len(proposals) + 1}", "expertId": self.expert_id, **{key: value for key, value in region.items() if key != "id"}}  # 复制人工区域并转换为提案。
            proposal["confidence"] = 1.0  # 人工确认区域使用最高置信度。
            proposal["status"] = "accepted"  # 人工区域直接标记为接受。
            proposal.setdefault("attributes", {})["originalRegionRef"] = region.get("id")  # 保留原人工区域引用。
            proposals.append(proposal)  # 保存人工覆盖提案。
        return proposals  # 返回人工覆盖提案。


def default_experts(include_fea: bool = True) -> list[Expert]:  # 返回默认局部专家集合。
    experts: list[Expert] = [SupportJointExpert(), DiscontinuityExpert(), SmoothRegionExpert(), HumanOverrideExpert()]  # 组装结构与人工专家。
    if include_fea:  # 检查是否启用 FEA 专家。
        experts.append(FEAHotspotExpert())  # 加入计算反馈专家。
    return experts  # 返回专家列表。

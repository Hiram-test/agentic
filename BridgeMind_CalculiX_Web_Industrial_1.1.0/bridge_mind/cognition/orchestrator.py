"""执行全局分配、多专家提案、融合和 BSDL 文档更新。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from .experts import GlobalAllocator, default_experts  # 导入全局分配器和默认专家集合。
from .features import extract_features  # 导入统一特征提取器。
from .fusion import TYPE_PRIORITY, fuse_proposals  # 导入区域融合器和类型优先级。
from ..memory import apply_memory_readback  # 导入外部经验读回和补丁生成器。
from ..utils import deep_copy, utc_now  # 复用深复制和统一时间戳。


def _build_cognitive_map(regions: list[dict[str, Any]], features: dict[str, Any]) -> dict[str, Any]:  # 根据区域和特征构造局部有限元认知地图。
    landmarks: list[dict[str, Any]] = []  # 初始化地标列表。
    decision_edges: list[dict[str, Any]] = []  # 初始化决策边列表。
    for sequence, region in enumerate(regions, start=1):  # 遍历最终区域。
        geometry = region.get("geometry", {})  # 读取区域几何。
        center = geometry.get("center", [0.0, 0.0, 0.0])  # 读取区域中心。
        target_refs = list(region.get("targetRefs", []))  # 读取区域目标对象。
        feature_vector: dict[str, Any] = {"meshLevel": region.get("meshLevel"), "targetSize": region.get("targetSize"), "source": region.get("source"), "semanticType": region.get("semanticType")}  # 初始化区域特征向量。
        for target_ref in target_refs:  # 遍历区域目标对象。
            if target_ref in features.get("nodes", {}):  # 检查目标是否为节点。
                node_feature = features["nodes"][target_ref]  # 读取节点特征。
                feature_vector.update({"nodeDegree": node_feature.get("degree"), "isSupport": node_feature.get("isSupport"), "sectionAreaRatio": node_feature.get("sectionAreaRatio"), "materialCount": node_feature.get("materialCount")})  # 合并节点结构特征。
                break  # 一个代表性节点即可。
            if target_ref in features.get("components", {}):  # 检查目标是否为构件。
                component_feature = features["components"][target_ref]  # 读取构件特征。
                feature_vector.update({"componentLength": component_feature.get("length"), "componentCategory": component_feature.get("category"), "sectionArea": component_feature.get("area")})  # 合并构件结构特征。
                break  # 一个代表性构件即可。
        landmark_id = f"landmark.{region['id'].split('region.', 1)[-1]}"  # 根据区域 ID 生成稳定地标 ID。
        landmarks.append({"id": landmark_id, "kind": region.get("semanticType") if region.get("semanticType") in {"support", "joint", "discontinuity", "smooth", "hotspot", "boundary"} else "other", "targetRefs": target_refs, "position": [float(value) for value in center], "featureVector": feature_vector, "reason": list(region.get("reason", [])), "confidence": float(region.get("confidence", 0.0))})  # 保存局部认知地标。
        decision_source = "experience" if isinstance(region.get("attributes", {}).get("memoryReadback"), dict) else ("human" if region.get("source") == "human" else ("fea" if region.get("source") == "fea" else "rule"))  # 根据区域证据确定决策边来源。
        decision_edges.append({"id": f"decision.{sequence}.{region['id'].split('.')[-1]}", "fromRef": landmark_id, "toRef": region["id"], "condition": "; ".join(region.get("reason", [])) or "区域特征满足当前专家规则", "action": f"meshLevel={region.get('meshLevel')}, targetSize={region.get('targetSize')}", "source": decision_source})  # 保存从地标到网格动作的决策关系。
    return {"landmarks": landmarks, "decisionEdges": decision_edges, "version": 1}  # 返回完整认知地图。


def propose_strategy(document: dict[str, Any], fea_result: dict[str, Any] | None = None, replace_generated: bool = True, actor_id: str = "software.bridgemind", memory_records: list[dict[str, Any]] | None = None, memory_policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:  # 执行多专家生成、经验读回和 BSDL 更新。
    updated = deep_copy(document)  # 深复制输入文档以保持函数无副作用。
    features = extract_features(updated, fea_result)  # 提取结构与可选响应特征。
    allocation = GlobalAllocator().allocate(updated, features)  # 执行全局资源分配。
    proposals: list[dict[str, Any]] = []  # 初始化所有专家提案列表。
    expert_reports: list[dict[str, Any]] = []  # 初始化专家运行报告。
    for expert in default_experts(include_fea=True):  # 遍历默认专家集合。
        expert_proposals = expert.propose(updated, features, fea_result)  # 运行当前专家。
        proposals.extend(expert_proposals)  # 汇总专家提案。
        expert_reports.append({"expertId": expert.expert_id, "proposalCount": len(expert_proposals)})  # 保存专家提案统计。
    fused_regions, fusion_report = fuse_proposals(proposals)  # 融合重叠和重复提案。
    existing_regions = [region for region in updated.get("regions", []) if isinstance(region, dict)]  # 读取已有区域。
    preserved = [region for region in existing_regions if region.get("source") in {"human", "imported"} or not replace_generated]  # 保留人工、导入或全部旧区域。
    preserved_ids = {region.get("id") for region in preserved}  # 收集保留区域 ID。
    generated = [region for region in fused_regions if region.get("source") not in {"human", "imported"} and region.get("id") not in preserved_ids]  # 选择新的 Agent 和 FEA 区域。
    human_from_fusion = [region for region in fused_regions if region.get("source") == "human" and region.get("attributes", {}).get("originalRegionRef") not in preserved_ids]  # 收集未在文档中存在的人工提案。
    updated["regions"] = preserved + generated + human_from_fusion  # 写入规则专家融合后的区域列表。
    memory_report: dict[str, Any] = {"enabled": False, "experienceCount": len(memory_records or []), "eligibleExperienceCount": 0, "matchedRegionCount": 0, "applicableRegionCount": 0, "appliedRegionCount": 0, "appliedExperienceIds": [], "appliedRegions": [], "regions": []}  # 初始化无经验读回报告。
    if memory_records is not None:  # 检查服务层是否显式提供经验库。
        updated["regions"], memory_report = apply_memory_readback(updated, updated["regions"], memory_records, memory_policy, features, float(allocation["baseSize"]), actor_id)  # 在固定规则策略之后应用跨项目经验补丁。
        updated["experienceRefs"] = sorted(set(list(updated.get("experienceRefs", [])) + list(memory_report.get("appliedExperienceIds", []))))  # 把实际使用经验写入根级经验引用。
    task = next((item for item in updated.get("analysisTasks", []) if isinstance(item, dict)), None)  # 选择首个分析任务。
    if task is None:  # 检查分析任务存在。
        raise ValueError("生成网格策略前必须至少存在一个 AnalysisTask。")  # 阻止无任务策略生成。
    policies = [item for item in updated.get("meshPolicies", []) if isinstance(item, dict)]  # 读取已有网格策略。
    if policies:  # 处理已有策略。
        policy = policies[0]  # 使用首个策略作为当前策略。
        policy["baseSize"] = float(allocation["baseSize"])  # 更新全局基准尺寸。
        policy["taskRef"] = task["id"]  # 绑定当前任务。
        policy["elementFamily"] = "frame"  # 当前原型使用空间梁网格。
        policy["status"] = "draft"  # 新生成策略保持待审核状态。
    else:  # 处理无已有策略。
        policy = {"id": "mesh.generated", "name": "多专家生成网格策略", "taskRef": task["id"], "baseSize": float(allocation["baseSize"]), "elementFamily": "frame", "regionRules": [], "budget": {"maxElements": int(task.get("budget", {}).get("maxElements", 5000)), "maxIterations": 4}, "status": "draft"}  # 创建新网格策略。
        policies = [policy]  # 初始化策略数组。
    policy["budget"] = {"maxElements": int(task.get("budget", {}).get("maxElements", 5000)), "maxIterations": int(policy.get("budget", {}).get("maxIterations", 4))}  # 同步任务计算预算。
    policy["regionRules"] = [{"regionRef": region["id"], "targetSize": float(region["targetSize"]), "priority": int(TYPE_PRIORITY.get(region.get("semanticType"), 50) + (5 if region.get("source") == "fea" else 0) + (5 if region.get("source") == "human" else 0))} for region in updated["regions"] if region.get("active") is True and region.get("status") != "rejected"]  # 为所有活跃区域生成策略规则。
    updated["meshPolicies"] = policies  # 写回网格策略数组。
    updated["cognitiveMap"] = _build_cognitive_map(updated["regions"], features)  # 重新构造局部有限元认知地图。
    feedback_id = f"feedback.strategy.{len(updated.get('feedback', [])) + 1}"  # 生成策略反馈 ID。
    updated.setdefault("feedback", []).append({"id": feedback_id, "source": "agent", "kind": "parameter_edit", "createdAt": utc_now(), "createdBy": actor_id, "targetRefs": [policy["id"]] + [region["id"] for region in generated], "before": {"regionCount": len(existing_regions)}, "after": {"regionCount": len(updated["regions"]), "baseSize": policy["baseSize"]}, "metrics": {"proposalCount": fusion_report["proposalCount"], "fusedCount": fusion_report["fusedCount"], "generatedRegionCount": len(generated)}, "comment": "全局分配器与局部多 expert 生成区域级网格策略。", "status": "recorded"})  # 记录 Agent 策略生成活动。
    if int(memory_report.get("appliedRegionCount", 0)) > 0:  # 检查经验读回是否真实改变策略。
        memory_feedback_id = f"feedback.memory.{len(updated.get('feedback', [])) + 1}"  # 生成经验读回反馈 ID。
        memory_targets = [str(item.get("regionId")) for item in memory_report.get("appliedRegions", []) if item.get("regionId")]  # 收集被经验补丁修改的区域。
        updated.setdefault("feedback", []).append({"id": memory_feedback_id, "source": "agent", "kind": "experience", "createdAt": utc_now(), "createdBy": actor_id, "targetRefs": memory_targets, "before": {"memoryApplied": False}, "after": {"memoryApplied": True, "experienceRefs": list(memory_report.get("appliedExperienceIds", [])), "regions": list(memory_report.get("appliedRegions", []))}, "metrics": {"matchedRegionCount": int(memory_report.get("matchedRegionCount", 0)), "appliedRegionCount": int(memory_report.get("appliedRegionCount", 0)), "appliedExperienceCount": len(memory_report.get("appliedExperienceIds", []))}, "comment": "历史 BSDL 经验经相似度、质量和任务兼容性门槛读回为 needs_review 区域补丁。", "status": "recorded"})  # 保存经验真正进入未来决策路径的证据。
    report = {"allocation": allocation, "experts": expert_reports, "fusion": fusion_report, "memory": memory_report, "memoryEnabled": bool(memory_report.get("enabled")), "memoryMatchedRegionCount": int(memory_report.get("matchedRegionCount", 0)), "memoryAppliedRegionCount": int(memory_report.get("appliedRegionCount", 0)), "preservedRegionCount": len(preserved), "generatedRegionCount": len(generated), "finalRegionCount": len(updated["regions"]), "hotspotRegionCount": sum(1 for region in updated["regions"] if region.get("semanticType") == "hotspot" and region.get("source") == "fea"), "feaFeedbackUsed": fea_result is not None, "meshPolicyRef": policy["id"], "featureStats": features.get("global", {})}  # 汇总规则专家、计算反馈和经验读回报告。
    return updated, report  # 返回更新文档和报告。

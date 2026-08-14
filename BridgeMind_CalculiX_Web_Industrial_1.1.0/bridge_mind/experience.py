"""把 BSDL 修订差异提取为可检索、可审核和可读回的局部结构经验。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from .cognition.features import extract_features  # 复用结构特征提取器。
from .memory import build_region_action, build_region_descriptor, descriptor_signature  # 导入跨项目描述符和无量纲动作生成器。
from .utils import content_hash, json_diff, utc_now  # 复用内容哈希、JSON 差异和时间戳。


def _index(values: list[Any]) -> dict[str, dict[str, Any]]:  # 按 ID 索引对象数组。
    return {str(item["id"]): item for item in values if isinstance(item, dict) and isinstance(item.get("id"), str)}  # 返回稳定对象索引。


def _feedback_evidence(document: dict[str, Any], region_id: str) -> dict[str, Any]:  # 收集作用于指定区域的人工、Agent 和 FEA 反馈证据。
    relevant = [item for item in document.get("feedback", []) if isinstance(item, dict) and region_id in item.get("targetRefs", [])]  # 筛选直接引用当前区域的反馈。
    return {"feedbackIds": [str(item.get("id")) for item in relevant if item.get("id")], "sources": sorted({str(item.get("source")) for item in relevant if item.get("source")}), "kinds": sorted({str(item.get("kind")) for item in relevant if item.get("kind")}), "acceptedCount": sum(1 for item in relevant if item.get("status") == "accepted" or item.get("kind") == "approval"), "rejectedCount": sum(1 for item in relevant if item.get("status") == "rejected" or item.get("kind") == "rejection"), "feaCount": sum(1 for item in relevant if item.get("source") == "fea" or item.get("kind") == "fea_result"), "humanCount": sum(1 for item in relevant if item.get("source") == "human")}  # 返回可序列化证据摘要。


def _experience_status(region: dict[str, Any] | None, evidence: dict[str, Any]) -> str:  # 根据区域最终状态和反馈确定经验生命周期状态。
    if region is None or region.get("active") is False or region.get("status") == "rejected" or int(evidence.get("rejectedCount", 0)) > 0:  # 检查删除、停用或拒绝状态。
        return "rejected"  # 把负面结果作为禁止自动读回的经验保存。
    if region.get("status") == "accepted" or int(evidence.get("acceptedCount", 0)) > 0:  # 检查明确批准证据。
        return "accepted"  # 标记为可优先读回的已接受经验。
    return "candidate"  # 其余经验进入候选状态等待人工或计算复核。


def _quality_score(region: dict[str, Any] | None, evidence: dict[str, Any], run_metrics: dict[str, Any] | None, status: str) -> float:  # 估计经验证据质量而不把语言流畅度当成可靠性。
    score = 0.20  # 为完整结构化修订差异提供基础分。
    if isinstance(region, dict) and region.get("source") == "human":  # 检查是否来自人工修订。
        score += 0.30  # 提高人工明确操作的证据权重。
    if status == "accepted":  # 检查是否经过批准。
        score += 0.20  # 提高已批准经验权重。
    if run_metrics:  # 检查是否附带求解或试验指标。
        score += 0.15  # 提高具有外部计算反馈的经验权重。
    if int(evidence.get("feaCount", 0)) > 0:  # 检查文档内是否存在 FEA 反馈。
        score += 0.10  # 提高直接关联计算反馈的经验权重。
    if isinstance(region, dict) and region.get("evidenceRefs"):  # 检查区域是否带显式证据引用。
        score += 0.05  # 提高具有外部证据链接的经验权重。
    if status == "rejected":  # 检查负面经验状态。
        score = min(score, 0.25)  # 防止拒绝经验进入正向读回策略。
    return round(max(0.0, min(1.0, score)), 6)  # 返回零到一之间的质量分。


def _applicability(descriptor: dict[str, Any], region: dict[str, Any] | None) -> dict[str, Any]:  # 保存经验可迁移范围和必须复核的边界。
    return {"analysisTypes": list(descriptor.get("analysisTypes", [])), "qoi": list(descriptor.get("qoi", [])), "loadKinds": list(descriptor.get("loadKinds", [])), "semanticType": descriptor.get("semanticType"), "elementFamily": descriptor.get("elementFamily"), "requiresSameAnalysisType": True, "requiresCompatibleElementFamily": True, "requiresHumanReview": True, "failureBoundary": ["新的非线性机制、接触、稳定或施工阶段问题不得仅凭本经验自动批准", "经验只生成 proposed/needs_review 补丁，最终由 FEA 或人工验收"] if region is not None else ["该经验表示删除或拒绝，仅用于负面检索，不自动停用新项目区域"]}  # 返回明确适用范围和失败边界。


def extract_experiences(project_id: str, revision_from: int, revision_to: int, before: dict[str, Any], after: dict[str, Any], run_metrics: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # 比较两个修订并生成结构化经验记录。
    before_regions = _index(before.get("regions", []))  # 索引旧修订区域。
    after_regions = _index(after.get("regions", []))  # 索引新修订区域。
    before_features = extract_features(before)  # 提取旧修订结构特征。
    after_features = extract_features(after)  # 提取新修订结构特征。
    records: list[dict[str, Any]] = []  # 初始化经验记录列表。
    all_region_ids = sorted(set(before_regions) | set(after_regions))  # 收集前后所有区域 ID。
    for region_id in all_region_ids:  # 遍历区域变化。
        previous = before_regions.get(region_id)  # 读取旧区域。
        current = after_regions.get(region_id)  # 读取新区域。
        if previous == current:  # 跳过完全未变化区域。
            continue  # 继续检查下一区域。
        reference = current or previous or {}  # 选择可用于特征提取的区域版本。
        reference_document = after if current is not None else before  # 选择与区域版本一致的文档上下文。
        reference_features = after_features if current is not None else before_features  # 选择与区域版本一致的结构特征。
        if previous is None:  # 判断区域新增。
            action_name = "新增区域"  # 设置动作摘要。
            outcome = "created"  # 设置经验结果状态。
        elif current is None:  # 判断区域删除。
            action_name = "删除区域"  # 设置动作摘要。
            outcome = "removed"  # 设置经验结果状态。
        else:  # 处理区域参数变化。
            action_name = "修改区域参数"  # 设置动作摘要。
            outcome = "modified"  # 设置经验结果状态。
        changes = json_diff(previous, current, f"/regions/{region_id}")  # 计算区域字段差异。
        descriptor = build_region_descriptor(reference_document, reference, reference_features)  # 构造跨项目可比较描述符。
        action = build_region_action(after, current)  # 构造以当前基准尺寸归一化的可重放动作。
        evidence = _feedback_evidence(after, region_id)  # 收集人工和计算反馈证据。
        evidence["runMetrics"] = dict(run_metrics or {})  # 关联可选求解运行指标。
        evidence["changePaths"] = [str(item.get("path")) for item in changes if isinstance(item, dict) and item.get("path")]  # 保存精确变更路径。
        status = _experience_status(current, evidence)  # 确定经验候选、接受或拒绝状态。
        quality_score = _quality_score(current, evidence, run_metrics, status)  # 计算经验质量分。
        semantic_type = reference.get("semanticType", "unknown")  # 读取区域语义类型。
        target_count = len(reference.get("targetRefs", []))  # 统计项目内目标对象数量而不保存其身份为匹配特征。
        summary = f"{action_name}：{semantic_type}，涉及 {target_count} 个结构对象，共 {len(changes)} 项字段变化；经验状态 {status}，质量 {quality_score:.2f}。"  # 生成确定性经验摘要。
        record = {"experienceId": f"experience.{content_hash({'project': project_id, 'from': revision_from, 'to': revision_to, 'region': region_id})[:24]}", "projectId": project_id, "revisionFrom": revision_from, "revisionTo": revision_to, "scopeType": "region", "scopeRef": region_id, "featureSignature": descriptor_signature(descriptor), "descriptor": descriptor, "action": action, "applicability": _applicability(descriptor, current), "evidence": evidence, "qualityScore": quality_score, "status": status, "review": {}, "before": previous, "after": current, "metrics": {"changeCount": len(changes), **(run_metrics or {})}, "summary": summary, "outcome": outcome, "tags": [str(semantic_type), str(reference.get("source", "unknown")), "region_strategy", status], "createdAt": utc_now()}  # 组装完整区域经验对象。
        records.append(record)  # 保存区域经验对象。
    before_policy = before.get("meshPolicies", [])  # 读取旧网格策略。
    after_policy = after.get("meshPolicies", [])  # 读取新网格策略。
    policy_changes = json_diff(before_policy, after_policy, "/meshPolicies")  # 计算网格策略整体变化。
    if policy_changes:  # 检查是否存在策略变化。
        descriptor = {"descriptorVersion": "1.0", "analysisTypes": sorted(str(item.get("type")) for item in after.get("analysisTasks", []) if isinstance(item, dict) and item.get("type")), "qoi": sorted(str(value) for item in after.get("analysisTasks", []) if isinstance(item, dict) for value in item.get("qoi", [])), "projectTags": sorted(str(value) for value in after.get("project", {}).get("tags", []))}  # 构造策略级描述符。
        records.append({"experienceId": f"experience.{content_hash({'project': project_id, 'from': revision_from, 'to': revision_to, 'scope': 'meshPolicy'})[:24]}", "projectId": project_id, "revisionFrom": revision_from, "revisionTo": revision_to, "scopeType": "mesh_policy", "scopeRef": after_policy[0].get("id") if after_policy and isinstance(after_policy[0], dict) else None, "featureSignature": descriptor_signature(descriptor), "descriptor": descriptor, "action": {"operation": "update_mesh_policy", "after": after_policy}, "applicability": {"requiresHumanReview": True}, "evidence": {"runMetrics": dict(run_metrics or {}), "changePaths": [str(item.get("path")) for item in policy_changes if isinstance(item, dict) and item.get("path")]}, "qualityScore": 0.35 if not run_metrics else 0.50, "status": "candidate", "review": {}, "before": before_policy, "after": after_policy, "metrics": {"changeCount": len(policy_changes), **(run_metrics or {})}, "summary": f"网格策略从 V{revision_from} 更新到 V{revision_to}，包含 {len(policy_changes)} 项变化。", "outcome": "modified", "tags": ["mesh_policy", "revision_diff", "candidate"], "createdAt": utc_now()})  # 保存策略级经验对象。
    if not records:  # 处理没有区域或策略差异的情况。
        overall_changes = json_diff(before, after)  # 计算完整文档差异。
        if overall_changes:  # 检查是否存在其他变化。
            descriptor = {"descriptorVersion": "1.0", "analysisTypes": sorted(str(item.get("type")) for item in after.get("analysisTasks", []) if isinstance(item, dict) and item.get("type")), "projectTags": sorted(str(value) for value in after.get("project", {}).get("tags", []))}  # 构造项目级描述符。
            records.append({"experienceId": f"experience.{content_hash({'project': project_id, 'from': revision_from, 'to': revision_to, 'scope': 'project'})[:24]}", "projectId": project_id, "revisionFrom": revision_from, "revisionTo": revision_to, "scopeType": "project", "scopeRef": project_id, "featureSignature": descriptor_signature(descriptor), "descriptor": descriptor, "action": {"operation": "project_revision"}, "applicability": {"requiresHumanReview": True}, "evidence": {"runMetrics": dict(run_metrics or {}), "changePaths": [str(item.get("path")) for item in overall_changes if isinstance(item, dict) and item.get("path")]}, "qualityScore": 0.25, "status": "candidate", "review": {}, "before": {"revision": before.get("revision")}, "after": {"revision": after.get("revision")}, "metrics": {"changeCount": len(overall_changes), **(run_metrics or {})}, "summary": f"项目从 V{revision_from} 更新到 V{revision_to}，共 {len(overall_changes)} 项文档变化。", "outcome": "modified", "tags": ["project", "revision_diff", "candidate"], "createdAt": utc_now()})  # 保存项目级经验对象。
    return records  # 返回全部提取经验。

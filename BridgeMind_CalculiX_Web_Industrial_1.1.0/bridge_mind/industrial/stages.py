"""编译施工阶段、生成阶段快照并执行梁系阶段试算。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from ..fea.frame3d import FrameSolveError, solve_document  # 复用内置空间梁求解器。
from ..utils import deep_copy  # 复用安全深复制。
from .prestress import prestress_as_loads  # 复用预应力等效荷载转换。


def _all_activation_refs(document: dict[str, Any]) -> set[str]:  # 收集可由施工阶段激活或停用的对象 ID。
    refs: set[str] = set()  # 初始化对象 ID 集合。
    for component in document.get("components", []):  # 遍历结构构件。
        if isinstance(component, dict) and component.get("id"):  # 检查构件有效 ID。
            refs.add(str(component["id"]))  # 保存构件 ID。
    for model in document.get("finiteElementModels", []):  # 遍历 FE 模型。
        if not isinstance(model, dict):  # 跳过非法模型。
            continue  # 继续检查下一模型。
        for element in model.get("elements", []):  # 遍历 FE 单元。
            if isinstance(element, dict) and element.get("id"):  # 检查单元有效 ID。
                refs.add(str(element["id"]))  # 保存 FE 单元 ID。
        for item_set in model.get("sets", []):  # 遍历 FE 集合。
            if isinstance(item_set, dict) and item_set.get("id"):  # 检查集合有效 ID。
                refs.add(str(item_set["id"]))  # 保存集合 ID。
    return refs  # 返回全部可激活对象 ID。


def compile_stage_plan(document: dict[str, Any]) -> dict[str, Any]:  # 把阶段增量操作编译为每阶段累计活动状态。
    stages = sorted([stage for stage in document.get("constructionStages", []) if isinstance(stage, dict)], key=lambda item: int(item.get("sequence", 0)))  # 按序号稳定排序阶段。
    known_refs = _all_activation_refs(document)  # 收集可激活对象。
    active_refs: set[str] = set()  # 初始化累计活动对象集合。
    for component in document.get("components", []):  # 遍历结构构件确定初始状态。
        if isinstance(component, dict) and component.get("id") and component.get("analysis", {}).get("active") is True:  # 检查构件初始活跃状态。
            active_refs.add(str(component["id"]))  # 保存初始活动构件。
    for model in document.get("finiteElementModels", []):  # 遍历 FE 模型确定初始状态。
        if not isinstance(model, dict):  # 跳过非法模型。
            continue  # 继续检查下一模型。
        for element in model.get("elements", []):  # 遍历 FE 单元。
            if isinstance(element, dict) and element.get("id") and element.get("active") is True:  # 检查单元初始活跃状态。
                active_refs.add(str(element["id"]))  # 保存初始活动单元。
    compiled: list[dict[str, Any]] = []  # 初始化编译后的阶段列表。
    issues: list[dict[str, Any]] = []  # 初始化阶段编译问题。
    seen_sequences: set[int] = set()  # 初始化已使用阶段序号集合。
    active_contacts: set[str] = set()  # 初始化累计活动接触集合。
    applied_prestress: set[str] = set()  # 初始化已施加预应力集合。
    active_load_cases: set[str] = set()  # 初始化当前活动荷载工况集合。
    for stage in stages:  # 遍历排序后的阶段。
        sequence = int(stage.get("sequence", 0))  # 读取阶段序号。
        stage_id = str(stage.get("id"))  # 读取阶段 ID。
        if sequence in seen_sequences:  # 检查阶段序号重复。
            issues.append({"ruleId": "BSDL-STAGE-001", "severity": "critical", "stageRef": stage_id, "message": f"施工阶段序号重复：{sequence}"})  # 记录重复序号。
        seen_sequences.add(sequence)  # 保存当前阶段序号。
        unknown_activations = [str(ref) for ref in stage.get("activateRefs", []) if str(ref) not in known_refs]  # 查找未知激活对象。
        unknown_deactivations = [str(ref) for ref in stage.get("deactivateRefs", []) if str(ref) not in known_refs]  # 查找未知停用对象。
        if unknown_activations or unknown_deactivations:  # 检查是否存在未知对象。
            issues.append({"ruleId": "BSDL-STAGE-002", "severity": "critical", "stageRef": stage_id, "message": "阶段引用了不存在的构件、单元或集合。", "unknownActivateRefs": unknown_activations, "unknownDeactivateRefs": unknown_deactivations})  # 记录未知对象问题。
        for ref in stage.get("activateRefs", []):  # 遍历本阶段激活对象。
            active_refs.add(str(ref))  # 把对象加入累计活动集合。
        for ref in stage.get("deactivateRefs", []):  # 遍历本阶段停用对象。
            active_refs.discard(str(ref))  # 从累计活动集合移除对象。
        if not bool(stage.get("carryOver", True)):  # 检查是否清除既有荷载工况。
            active_load_cases.clear()  # 清空累计活动荷载工况。
        active_load_cases.update(str(ref) for ref in stage.get("loadCaseRefs", []))  # 加入本阶段荷载工况。
        active_contacts.update(str(ref) for ref in stage.get("contactRefs", []))  # 加入本阶段接触关系。
        applied_prestress.update(str(ref) for ref in stage.get("prestressRefs", []))  # 加入本阶段预应力系统。
        compiled.append({"stageId": stage_id, "name": stage.get("name", stage_id), "sequence": sequence, "duration": float(stage.get("duration", 0.0)), "activeRefs": sorted(active_refs), "activeLoadCaseRefs": sorted(active_load_cases), "activeContactRefs": sorted(active_contacts), "appliedPrestressRefs": sorted(applied_prestress), "solverSettings": deep_copy(stage.get("solverSettings", {})), "status": stage.get("status", "draft")})  # 保存阶段累计状态。
    return {"valid": not any(item.get("severity") == "critical" for item in issues), "stageCount": len(compiled), "stages": compiled, "issues": issues}  # 返回阶段编译结果。


def stage_snapshot(document: dict[str, Any], compiled_stage: dict[str, Any]) -> dict[str, Any]:  # 根据编译状态生成可供 Adapter 或试算使用的阶段文档。
    snapshot = deep_copy(document)  # 深复制完整项目文档。
    active_refs = set(str(ref) for ref in compiled_stage.get("activeRefs", []))  # 读取当前活动对象集合。
    active_load_cases = set(str(ref) for ref in compiled_stage.get("activeLoadCaseRefs", []))  # 读取当前活动荷载工况。
    prestress_refs = set(str(ref) for ref in compiled_stage.get("appliedPrestressRefs", []))  # 读取已施加预应力系统。
    for component in snapshot.get("components", []):  # 遍历结构构件设置活跃状态。
        if isinstance(component, dict) and component.get("id"):  # 检查构件有效性。
            component.setdefault("analysis", {})["active"] = str(component["id"]) in active_refs  # 根据累计状态设置分析激活标志。
    for model in snapshot.get("finiteElementModels", []):  # 遍历 FE 模型设置单元活跃状态。
        if not isinstance(model, dict):  # 跳过非法模型。
            continue  # 继续检查下一模型。
        active_set_refs = {str(item_set.get("id")): [str(ref) for ref in item_set.get("refs", [])] for item_set in model.get("sets", []) if isinstance(item_set, dict)}  # 建立集合到元素引用的映射。
        expanded_active = set(active_refs)  # 复制活动引用集合。
        for set_ref, refs in active_set_refs.items():  # 遍历 FE 集合。
            if set_ref in active_refs:  # 检查集合是否被激活。
                expanded_active.update(refs)  # 激活集合包含的所有单元。
        for element in model.get("elements", []):  # 遍历 FE 单元。
            if isinstance(element, dict) and element.get("id"):  # 检查单元有效性。
                element["active"] = str(element["id"]) in expanded_active  # 根据阶段状态设置单元激活标志。
    snapshot["loads"] = [load for load in snapshot.get("loads", []) if isinstance(load, dict) and str(load.get("caseRef")) in active_load_cases]  # 只保留当前累计荷载工况的荷载。
    coordinate_system_ref = str(snapshot.get("coordinateSystems", [{}])[0].get("id", "cs.global"))  # 选择默认全局坐标系。
    for system in snapshot.get("prestressingSystems", []):  # 遍历预应力系统。
        if not isinstance(system, dict) or str(system.get("id")) not in prestress_refs:  # 跳过尚未施加的预应力系统。
            continue  # 继续检查下一系统。
        if system.get("representation") == "equivalent_load":  # 检查是否使用等效荷载表示。
            snapshot["loads"].extend(prestress_as_loads(system, coordinate_system_ref, system.get("loadCaseRef")))  # 把预应力等效力加入阶段荷载。
    snapshot.setdefault("extensions", {})["industrialStageContext"] = {"stageRef": compiled_stage.get("stageId"), "sequence": compiled_stage.get("sequence"), "activeContactRefs": compiled_stage.get("activeContactRefs", []), "appliedPrestressRefs": compiled_stage.get("appliedPrestressRefs", [])}  # 保存阶段上下文。
    return snapshot  # 返回阶段快照。


def run_staged_frame_snapshots(document: dict[str, Any], mesh_policy_id: str | None = None) -> dict[str, Any]:  # 对梁系阶段快照逐阶段执行线性静力试算。
    compiled = compile_stage_plan(document)  # 编译施工阶段。
    if not compiled["valid"]:  # 检查阶段编译是否通过。
        raise ValueError({"message": "施工阶段编译失败。", "issues": compiled["issues"]})  # 阻止非法阶段进入试算。
    results: list[dict[str, Any]] = []  # 初始化阶段试算结果。
    for stage in compiled["stages"]:  # 遍历编译后的阶段。
        snapshot = stage_snapshot(document, stage)  # 生成当前阶段快照。
        load_cases = stage.get("activeLoadCaseRefs", [])  # 读取当前活动荷载工况。
        if not load_cases:  # 检查当前阶段是否存在荷载。
            results.append({"stageRef": stage["stageId"], "sequence": stage["sequence"], "status": "skipped", "reason": "当前阶段没有活动荷载工况。"})  # 保存跳过状态。
            continue  # 继续下一阶段。
        try:  # 捕获阶段梁系求解失败。
            result = solve_document(snapshot, mesh_policy_id, str(load_cases[-1]))  # 对当前阶段最后一个活动工况执行快照试算。
            results.append({"stageRef": stage["stageId"], "sequence": stage["sequence"], "status": "succeeded", "loadCaseRef": load_cases[-1], "result": result})  # 保存阶段试算结果。
        except FrameSolveError as error:  # 处理梁系求解失败。
            results.append({"stageRef": stage["stageId"], "sequence": stage["sequence"], "status": "failed", "error": {"message": str(error), "details": error.details}})  # 保存结构化阶段错误。
    return {"method": "linear_stage_snapshot", "historyDependentStressTransfer": False, "compiled": compiled, "results": results, "warning": "内置阶段试算重建每阶段线弹性快照，用于快速反馈；真实应力历史、徐变收缩、接触状态和单元生死由外部非线性求解器执行。"}  # 返回阶段试算总结果。

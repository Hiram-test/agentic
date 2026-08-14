"""生成包含壳、实体、摩擦接触、预应力和施工阶段的工业示例。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
from pathlib import Path  # 提供示例文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from bridge_mind.industrial.mesh import generate_shell_plate, generate_solid_block, quality_report  # 导入确定性壳和实体网格器。
from bridge_mind.industrial.migration import default_solver_profiles, upgrade_document  # 导入工业升级器和求解器档案。
from bridge_mind.utils import content_hash, load_json, save_json  # 导入文档、哈希和保存工具。
from bridge_mind.validator import validate_document  # 导入完整 BSDL 验证器。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。
SOURCE = ROOT / "examples" / "two_girder_bridge.bsdl.json"  # 指定核心 BSDL 基础示例。
TARGET = ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json"  # 指定工业示例输出路径。


def _constraints(ux: bool = False, uy: bool = False, uz: bool = False, rx: bool = False, ry: bool = False, rz: bool = False) -> dict[str, bool]:  # 构造完整六自由度约束对象。
    return {"ux": ux, "uy": uy, "uz": uz, "rx": rx, "ry": ry, "rz": rz}  # 返回约束字典。


def _combine_models(parts: list[dict[str, Any]], model_id: str, task_ref: str, coordinate_system_ref: str) -> dict[str, Any]:  # 把多个唯一 ID 的网格部件组合为混合维度 FE 模型。
    nodes = [node for part in parts for node in part.get("nodes", [])]  # 合并全部 FE 节点。
    elements = [element for part in parts for element in part.get("elements", [])]  # 合并全部 FE 单元。
    sets = [item_set for part in parts for item_set in part.get("sets", [])]  # 合并全部节点、单元和表面集合。
    model = {"id": model_id, "name": "桥面壳—支座实体—预应力筋混合模型", "taskRef": task_ref, "coordinateSystemRef": coordinate_system_ref, "nodes": nodes, "elements": elements, "sets": sets, "source": "generated", "meshHash": "", "status": "approved", "statistics": {}, "artifactRefs": []}  # 组装混合维度 FE 模型。
    model["statistics"] = quality_report(model)  # 重新计算组合模型质量统计。
    model["meshHash"] = content_hash({"nodes": nodes, "elements": elements, "sets": sets})  # 计算组合模型内容哈希。
    return model  # 返回组合 FE 模型。


def build_document() -> dict[str, Any]:  # 构造完整工业示例文档。
    document = upgrade_document(load_json(SOURCE))  # 无损升级核心示例为工业语言。
    document["documentId"] = "document.calculix_industrial_bridge_segment"  # 设置工业示例文档 ID。
    document["project"] = {"id": "project.calculix_industrial_bridge_segment", "name": "CalculiX 壳实体接触预应力施工阶段示例", "description": "用于验证 BSDL Industrial 1.0 与 CalculiX 2.23 Adapter 的混合单元、接触、预应力、阶段、结果和验算链。", "sourceType": "synthetic", "sourceUri": None, "tags": ["calculix", "shell", "solid", "contact", "prestress", "construction_stage"]}  # 设置项目元数据。
    document["revision"] = {"number": 1, "parent": None, "createdAt": "2026-08-13T00:00:00Z", "createdBy": "human.demo", "status": "approved", "summary": "CalculiX 工业示例首版"}  # 设置不可变修订元数据。
    document["materials"] = [  # 定义结构材料和预应力材料。
        {"id": "mat.steel", "name": "结构钢", "model": "bilinear_plastic", "density": 7850.0, "elasticModulus": 206000000000.0, "poissonRatio": 0.3, "shearModulus": 79230769230.8, "thermalExpansion": 1.2e-5, "yieldStrength": 345000000.0, "tags": ["steel"], "plasticity": {"points": [{"stress": 345000000.0, "plasticStrain": 0.0}, {"stress": 380000000.0, "plasticStrain": 0.02}]}, "creep": None, "relaxation": None},  # 定义钢材双线性模型。
        {"id": "mat.concrete", "name": "混凝土等效弹性材料", "model": "linear_elastic", "density": 2500.0, "elasticModulus": 34500000000.0, "poissonRatio": 0.2, "shearModulus": None, "thermalExpansion": 1.0e-5, "yieldStrength": None, "tags": ["concrete", "equivalent"], "plasticity": None, "creep": None, "relaxation": None},  # 定义当前示例使用的混凝土等效弹性模型。
        {"id": "mat.prestress", "name": "1860 MPa 预应力钢绞线", "model": "linear_elastic", "density": 7850.0, "elasticModulus": 195000000000.0, "poissonRatio": 0.3, "shearModulus": None, "thermalExpansion": 1.2e-5, "yieldStrength": 1670000000.0, "tags": ["prestress"], "plasticity": None, "creep": None, "relaxation": {"model": "project_defined"}},  # 定义预应力钢绞线材料。
    ]  # 完成材料列表。
    document["sections"] = [  # 定义梁和桁架截面。
        {"id": "sec.tendon", "name": "预应力筋等效面积", "shape": "circular", "area": 0.0014, "iy": 1.56e-7, "iz": 1.56e-7, "torsionConstant": 3.12e-7, "dimensions": {"diameter": 0.0422}, "tags": ["tendon"]},  # 定义钢束桁架截面。
        {"id": "sec.girder", "name": "保留的主梁截面", "shape": "rectangular", "area": 0.12, "iy": 0.18, "iz": 0.012, "torsionConstant": 0.002, "dimensions": {"width": 0.6, "depth": 1.8}, "tags": ["beam"]},  # 保留兼容梁截面。
        {"id": "sec.crossbeam", "name": "保留的横梁截面", "shape": "rectangular", "area": 0.16, "iy": 0.06, "iz": 0.025, "torsionConstant": 0.006, "dimensions": {"width": 0.5, "depth": 1.2}, "tags": ["beam", "crossbeam"]},  # 保留原核心横梁引用所需截面。
    ]  # 完成梁截面列表。
    document["shellSections"] = [{"id": "shell.deck.025", "name": "250 mm 桥面板壳截面", "materialRef": "mat.concrete", "thickness": 0.25, "offset": 0.0, "integrationPoints": 5, "formulation": "general", "orientationRef": "cs.global", "layers": [], "tags": ["deck", "shell"]}]  # 定义桥面壳截面。
    document["solidSections"] = [{"id": "solid.bearing.steel", "name": "钢支座实体截面", "materialRef": "mat.steel", "orientationRef": "cs.global", "integration": "reduced", "tags": ["bearing", "solid"]}]  # 定义支座实体截面。
    document["loadCases"] = [  # 定义施工和运营工况。
        {"id": "lc.dead", "name": "自重", "type": "static", "factor": 1.0},  # 定义自重工况。
        {"id": "lc.prestress", "name": "预应力", "type": "static", "factor": 1.0},  # 定义预应力工况。
        {"id": "lc.service", "name": "桥面服务压力", "type": "static", "factor": 1.0},  # 定义服务压力工况。
    ]  # 完成工况列表。
    document["analysisTasks"] = [{"id": "task.industrial", "name": "壳实体接触预应力施工阶段非线性静力分析", "type": "other", "loadCaseRefs": ["lc.dead", "lc.prestress", "lc.service"], "qoi": ["vertical_displacement", "contact_pressure", "von_mises_stress", "reaction_balance"], "accuracyTarget": 0.05, "budget": {"maxElements": 1000000, "maxRuns": 30, "maxWallSeconds": 7200.0}, "status": "approved"}]  # 定义工业分析任务。
    document["meshPolicies"] = [{"id": "mesh.industrial", "name": "壳实体混合网格策略", "taskRef": "task.industrial", "baseSize": 1.0, "elementFamily": "auto", "regionRules": [], "budget": {"maxElements": 1000000, "maxIterations": 8}, "status": "approved"}]  # 定义工业网格策略。
    deck = generate_shell_plate("fem.deck", "task.industrial", "cs.global", [0.0, 0.0, 2.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], 12.0, 4.0, 6, 2, "shell.deck.025", "comp.bridge", "S4R")  # 生成桥面板规则壳网格。
    bearing = generate_solid_block("fem.bearing", "task.industrial", "cs.global", [5.0, 1.5, 1.5], [2.0, 1.0, 0.5], [2, 1, 1], "solid.bearing.steel", "comp.crossbeam.2", "C3D8R")  # 生成支座规则实体网格。
    for element in deck["elements"]:  # 遍历桥面壳单元。
        element["active"] = False  # 让桥面单元由施工阶段激活。
    for node in deck["nodes"]:  # 遍历桥面壳节点并建立最小稳定边界。
        x_coordinate = float(node["position"][0])  # 读取节点纵向坐标。
        y_coordinate = float(node["position"][1])  # 读取节点横向坐标。
        if abs(x_coordinate) <= 1e-9 or abs(x_coordinate - 12.0) <= 1e-9:  # 检查节点是否位于两端简支边。
            node["constraints"]["uz"] = True  # 约束两端边竖向平动以形成稳定支承。
        if abs(x_coordinate) <= 1e-9 and abs(y_coordinate) <= 1e-9:  # 检查左端角点。
            node["constraints"]["ux"] = True  # 在左端角点约束纵向刚体位移。
            node["constraints"]["uy"] = True  # 在左端角点约束横向刚体位移。
        if abs(x_coordinate) <= 1e-9 and abs(y_coordinate - 4.0) <= 1e-9:  # 检查左端另一角点。
            node["constraints"]["uy"] = True  # 约束第二个横向自由度以消除平面刚体转动。
    for element in bearing["elements"]:  # 遍历支座实体单元。
        element["active"] = False  # 让支座单元由施工阶段激活。
    bottom_nodes = set(next(item["refs"] for item in bearing["sets"] if item["id"] == "fem.bearing.surface.zmin")) if any(item["id"] == "fem.bearing.surface.zmin" and item["refs"] for item in bearing["sets"]) else set()  # 尝试读取节点型底面集合。
    if not bottom_nodes:  # 处理实体表面由 faces 定义的情况。
        bottom_nodes = {node["id"] for node in bearing["nodes"] if abs(float(node["position"][2]) - 1.5) <= 1e-9}  # 按几何坐标识别支座底面节点。
    for node in bearing["nodes"]:  # 遍历支座节点。
        if node["id"] in bottom_nodes:  # 检查节点是否位于支座底面。
            node["constraints"] = _constraints(True, True, True, False, False, False)  # 固定实体节点三个平动自由度。
    tendon_node_refs = ["fem.deck.n.0.1", "fem.deck.n.3.1", "fem.deck.n.6.1"]  # 选择与桥面壳共享的三个钢束锚固和偏转节点。
    tendon_elements = [  # 定义两段与桥面共享节点的 T3D2 预应力筋单元。
        {"id": "fem.tendon.e.0", "type": "T3D2", "nodeRefs": [tendon_node_refs[0], tendon_node_refs[1]], "sectionRef": "sec.tendon", "materialRef": "mat.prestress", "sourceRef": None, "orientationRef": "cs.global", "setRefs": ["fem.tendon.set.all"], "active": False, "attributes": {"role": "prestress_tendon", "coupling": "shared_shell_nodes"}},  # 定义第一段钢束单元。
        {"id": "fem.tendon.e.1", "type": "T3D2", "nodeRefs": [tendon_node_refs[1], tendon_node_refs[2]], "sectionRef": "sec.tendon", "materialRef": "mat.prestress", "sourceRef": None, "orientationRef": "cs.global", "setRefs": ["fem.tendon.set.all"], "active": False, "attributes": {"role": "prestress_tendon", "coupling": "shared_shell_nodes"}},  # 定义第二段钢束单元。
    ]  # 完成预应力束单元。
    tendon = {"id": "fem.tendon", "name": "共享节点预应力束 FE 子模型", "taskRef": "task.industrial", "coordinateSystemRef": "cs.global", "nodes": [], "elements": tendon_elements, "sets": [{"id": "fem.tendon.set.all", "name": "全部预应力筋单元", "kind": "element", "refs": ["fem.tendon.e.0", "fem.tendon.e.1"], "faces": [], "sourceRefs": [], "attributes": {"coupling": "shared_shell_nodes"}}], "source": "human", "meshHash": content_hash({"elements": tendon_elements}), "status": "approved", "statistics": {"nodeCount": 0, "sharedNodeCount": 3, "elementCount": 2, "elementTypes": {"T3D2": 2}, "validTopology": True}, "artifactRefs": []}  # 组装共享节点钢束 FE 子模型。
    model = _combine_models([deck, bearing, tendon], "fem.bridge_segment", "task.industrial", "cs.global")  # 合并壳、实体和桁架模型。
    model["sets"].append({"id": "fem.bridge_segment.set.all", "name": "全部混合单元", "kind": "element", "refs": [element["id"] for element in model["elements"]], "faces": [], "sourceRefs": ["comp.bridge"], "attributes": {"mixedDimensional": True}})  # 添加全模型单元集合。
    model["statistics"] = quality_report(model)  # 更新包含全模型集合后的质量统计。
    model["meshHash"] = content_hash({"nodes": model["nodes"], "elements": model["elements"], "sets": model["sets"]})  # 更新组合模型哈希。
    document["finiteElementModels"] = [model]  # 保存唯一工业 FE 模型。
    document["contacts"] = [{"id": "contact.deck.bearing", "name": "桥面板—支座摩擦接触", "masterSurfaceRef": "fem.bearing.surface.zmax", "slaveSurfaceRef": "fem.deck.surface.negative", "behavior": "contact", "normalBehavior": "linear_penalty", "tangentialBehavior": "penalty_friction", "frictionCoefficient": 0.3, "penaltyStiffness": 1000000000000.0, "allowSeparation": True, "finiteSliding": False, "stageRefs": ["stage.deck", "stage.prestress", "stage.service"], "status": "approved", "attributes": {"calculixContactType": "SURFACE TO SURFACE", "calibrationRequired": True}}]  # 定义可分离有限滑移摩擦接触。
    document["prestressingSystems"] = [{"id": "prestress.tendon.eq", "name": "折线预应力束等效荷载", "kind": "internal_bonded", "representation": "equivalent_load", "materialRef": "mat.prestress", "area": 0.0014, "path": [{"position": [0.0, 2.0, 2.0], "nodeRef": tendon_node_refs[0], "station": 0.0, "attributes": {"role": "active_anchor"}}, {"position": [6.0, 2.0, 1.75], "nodeRef": tendon_node_refs[1], "station": 6.005, "attributes": {"role": "deviation"}}, {"position": [12.0, 2.0, 2.0], "nodeRef": tendon_node_refs[2], "station": 12.01, "attributes": {"role": "passive_anchor"}}], "jackingForce": 1800000.0, "initialStress": None, "frictionCoefficient": 0.02, "wobbleCoefficient": 0.0015, "anchorageSlip": 0.006, "immediateLossFactor": 0.04, "longTermLossFactor": 0.12, "anchorRefs": [tendon_node_refs[0], tendon_node_refs[2]], "targetRefs": ["fem.tendon.set.all"], "stageRef": "stage.prestress", "loadCaseRef": "lc.prestress", "status": "approved", "attributes": {"tendonElasticModulus": 195000000000.0, "lossModel": "project_defined_demo", "forceApplication": "shared_shell_nodes"}}]  # 定义通过共享壳节点传递的折线预应力等效荷载系统。
    document["loads"] = [  # 定义阶段荷载对象。
        {"id": "load.dead", "name": "全模型自重", "caseRef": "lc.dead", "kind": "self_weight", "targetNodeRef": None, "targetComponentRef": "comp.bridge", "force": [0.0, 0.0, -9.81], "moment": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "attributes": {"elementSetRef": "fem.bridge_segment.set.all"}},  # 定义重力荷载。
        {"id": "load.service.pressure", "name": "桥面均布压力", "caseRef": "lc.service", "kind": "other", "targetNodeRef": None, "targetComponentRef": "comp.bridge", "force": [0.0, 0.0, 0.0], "moment": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "attributes": {"surfaceRef": "fem.deck.surface.positive", "pressure": -25000.0}},  # 定义桥面服务压力。
        {"id": "load.service.anchor", "name": "服务阶段节点校核荷载", "caseRef": "lc.service", "kind": "nodal", "targetNodeRef": "node.L.2", "targetComponentRef": None, "force": [0.0, 0.0, -100000.0], "moment": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "attributes": {"purpose": "同时满足核心梁系预览和工业 FE 回归测试", "finiteElementNodeRef": "fem.deck.n.3.1"}},  # 定义可由核心验证器识别的非零节点荷载。
    ]  # 完成荷载列表。
    document["constructionStages"] = [  # 定义四个累计施工阶段。
        {"id": "stage.support", "name": "支座安装", "sequence": 1, "duration": 1.0, "activateRefs": ["fem.bearing.set.all"], "deactivateRefs": [], "loadCaseRefs": ["lc.dead"], "prestressRefs": [], "contactRefs": [], "carryOver": True, "solverSettings": {"analysis": "nonlinear_static", "nlgeom": True, "initialIncrement": 0.1, "maximumIncrement": 0.2}, "status": "approved"},  # 定义首阶段支座激活。
        {"id": "stage.deck", "name": "桥面板架设并建立接触", "sequence": 2, "duration": 1.0, "activateRefs": ["fem.deck.set.all"], "deactivateRefs": [], "loadCaseRefs": ["lc.dead"], "prestressRefs": [], "contactRefs": ["contact.deck.bearing"], "carryOver": True, "solverSettings": {"analysis": "nonlinear_static", "nlgeom": True, "initialIncrement": 0.05, "maximumIncrement": 0.1}, "status": "approved"},  # 定义桥面板与接触激活阶段。
        {"id": "stage.prestress", "name": "激活钢束并施加预应力", "sequence": 3, "duration": 0.5, "activateRefs": ["fem.tendon.set.all"], "deactivateRefs": [], "loadCaseRefs": ["lc.prestress"], "prestressRefs": ["prestress.tendon.eq"], "contactRefs": ["contact.deck.bearing"], "carryOver": True, "solverSettings": {"analysis": "nonlinear_static", "nlgeom": True, "initialIncrement": 0.02, "maximumIncrement": 0.08}, "status": "approved"},  # 定义预应力阶段。
        {"id": "stage.service", "name": "运营服务阶段", "sequence": 4, "duration": 1.0, "activateRefs": [], "deactivateRefs": [], "loadCaseRefs": ["lc.service"], "prestressRefs": ["prestress.tendon.eq"], "contactRefs": ["contact.deck.bearing"], "carryOver": True, "solverSettings": {"analysis": "nonlinear_static", "nlgeom": True, "initialIncrement": 0.02, "maximumIncrement": 0.08, "contactOutput": True}, "status": "approved"},  # 定义服务压力阶段。
    ]  # 完成施工阶段列表。
    document["solverProfiles"] = default_solver_profiles()  # 写入 CalculiX 2.23 和非权威预览器能力档案。
    document["solverPlans"] = [{"id": "solver.calculix.industrial", "name": "CalculiX 2.23 非线性施工阶段计划", "taskRef": "task.industrial", "meshPolicyRef": "mesh.industrial", "solver": "calculix", "settings": {"analysis": "nonlinear_static", "nlgeom": True, "strictConversion": True, "timeoutSeconds": 3600, "threads": 2, "contactOutput": True}, "status": "approved", "solverProfileRef": "solver.profile.calculix.2_23", "finiteElementModelRef": "fem.bridge_segment", "stageRefs": ["stage.support", "stage.deck", "stage.prestress", "stage.service"]}]  # 定义唯一 CalculiX 工业求解计划。
    document["codeCheckPlans"] = [{"id": "check.generic.service", "name": "服务性、应力与平衡通用验算", "taskRef": "task.industrial", "standard": {"code": "PROJECT-GENERIC", "edition": "2026-08", "nationalAnnex": None, "licensedContentRequired": False}, "limitState": "custom", "rulePack": "generic.bridge", "targetRefs": ["comp.bridge"], "resultSetRef": None, "parameters": {}, "acceptance": {"allowableDisplacement": 0.03, "designStrength": 310000000.0, "maxReactionBalanceResidual": 1e-5}, "status": "approved"}]  # 定义非规范性通用验算计划。
    document["codeCheckResults"] = []  # 初始化验算结果数组。
    document["resultSets"] = []  # 初始化求解结果数组。
    document["externalMappings"] = [  # 定义 IFC 4.3 身份映射示例。
        {"id": "mapping.ifc.bridge", "sourceSystem": "IFC4X3_ADD2.DesignTransferView", "sourceVersion": "IFC 4.3.2.0", "sourceId": "2SyntheticBridgeGlobalId", "targetRef": "comp.bridge", "kind": "identity", "method": "direct", "confidence": 1.0, "geometryHash": None, "status": "needs_review", "attributes": {"ifcType": "IfcBridge", "syntheticFixture": True}},  # 映射桥梁身份。
        {"id": "mapping.ifc.deck.mesh", "sourceSystem": "IFC4X3_ADD2.DesignTransferView", "sourceVersion": "IFC 4.3.2.0", "sourceId": "3SyntheticDeckGlobalId", "targetRef": "fem.deck.set.all", "kind": "mesh_region", "method": "rule", "confidence": 0.9, "geometryHash": deck["meshHash"], "status": "needs_review", "attributes": {"ifcType": "IfcSlab", "syntheticFixture": True}},  # 映射桥面网格区域。
    ]  # 完成外部映射列表。
    document["conversionReports"] = []  # 初始化转换报告数组。
    document["artifacts"] = []  # 初始化外部产物数组。
    document["feedback"] = []  # 初始化反馈数组。
    document["experienceRefs"] = []  # 初始化经验引用数组。
    document.setdefault("extensions", {})["calculixIndustrialProfile"] = {"targetVersion": "2.23", "syntheticExample": True, "engineeringUse": "language_and_adapter_validation_only", "nativePretensionSection": "blocked_until_benchmark_validated"}  # 记录示例边界和求解器目标。
    return document  # 返回完整工业文档。


def main() -> int:  # 生成、验证并保存工业示例。
    document = build_document()  # 构造示例文档。
    validation = validate_document(document)  # 执行 Schema、引用、拓扑和工业规则验证。
    if not validation["valid"]:  # 检查验证结果。
        raise RuntimeError(validation)  # 阻止写出非法示例。
    save_json(TARGET, document)  # 保存格式化工业示例。
    print(f"VALID {TARGET} level={validation.get('level')} stats={validation.get('stats')}")  # 输出可审计生成摘要。
    return 0  # 返回成功退出码。


if __name__ == "__main__":  # 检查脚本直接执行入口。
    raise SystemExit(main())  # 执行生成流程并返回退出码。

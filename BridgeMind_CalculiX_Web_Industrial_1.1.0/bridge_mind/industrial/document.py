"""创建满足 BSDL Industrial 1.0 基线要求的空项目文档。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from typing import Any  # 提供通用 JSON 类型注解。
from ..utils import utc_now  # 复用统一时间戳。
from .migration import upgrade_document  # 复用工业版本升级函数。


def new_document(project_id: str, name: str, description: str, source_type: str, source_uri: str | None = None, author: str = "software.bridgemind") -> dict[str, Any]:  # 创建可继续填充的工业 BSDL 文档。
    task_id = f"task.{project_id.split('.')[-1]}.default"  # 构造默认分析任务 ID。
    mesh_id = f"mesh.{project_id.split('.')[-1]}.default"  # 构造默认网格策略 ID。
    solver_id = f"solver.{project_id.split('.')[-1]}.default"  # 构造默认求解计划 ID。
    load_case_id = f"lc.{project_id.split('.')[-1]}.self_weight"  # 构造默认荷载工况 ID。
    placeholder_node_id = f"node.{project_id.split('.')[-1]}.origin"  # 构造占位节点 ID。
    placeholder_component_id = f"component.{project_id.split('.')[-1]}.root"  # 构造占位构件 ID。
    document = {  # 构造核心 BSDL 文档。
        "$schema": "../schema/bsdl.schema.json",  # 指向核心 Schema 以便升级函数替换。
        "language": "Bridge-Structural-Description-Language",  # 设置语言名称。
        "languageVersion": "0.1.0",  # 设置临时核心版本。
        "documentId": f"doc.{project_id.split('.')[-1]}",  # 设置文档稳定 ID。
        "revision": {"number": 1, "parent": None, "createdAt": utc_now(), "createdBy": author, "status": "working", "summary": "创建工业 BSDL 项目"},  # 设置首个修订元数据。
        "project": {"id": project_id, "name": name, "description": description, "sourceType": source_type, "sourceUri": source_uri, "tags": ["industrial"]},  # 设置项目元数据。
        "units": {"length": "m", "force": "N", "mass": "kg", "stress": "Pa", "angle": "rad"},  # 使用 SI 单位约定。
        "coordinateSystems": [{"id": "cs.global", "name": "全局坐标系", "parentRef": None, "origin": [0.0, 0.0, 0.0], "xAxis": [1.0, 0.0, 0.0], "yAxis": [0.0, 1.0, 0.0], "zAxis": [0.0, 0.0, 1.0]}],  # 创建全局坐标系。
        "agents": [{"id": author, "name": author, "kind": "software" if author.startswith("software.") else "person", "version": "1.0.0"}],  # 记录创建主体。
        "materials": [],  # 初始化材料集合。
        "sections": [],  # 初始化梁截面集合。
        "nodes": [{"id": placeholder_node_id, "name": "导入原点", "position": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "roles": ["reference"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["placeholder"], "sourceIds": {}, "attributes": {"placeholder": True}}],  # 创建占位节点保证初始文档完整。
        "components": [{"id": placeholder_component_id, "name": name, "category": "bridge", "topology": "point", "parentRef": None, "nodeRefs": [placeholder_node_id], "materialRef": None, "sectionRef": None, "geometry": {"kind": "box", "center": [0.0, 0.0, 0.0], "size": [1e-6, 1e-6, 1e-6], "rotation": [0.0, 0.0, 0.0]}, "analysis": {"elementType": "excluded", "active": False, "localUp": None}, "attributes": {"placeholder": True}, "featureDescriptors": {}, "tags": ["placeholder"], "sourceIds": {}}],  # 创建项目根构件。
        "connections": [],  # 初始化连接集合。
        "loadCases": [{"id": load_case_id, "name": "自重或导入默认工况", "type": "dead", "factor": 1.0}],  # 创建默认荷载工况。
        "loads": [],  # 初始化荷载集合。
        "analysisTasks": [{"id": task_id, "name": "默认结构分析任务", "type": "linear_static", "loadCaseRefs": [load_case_id], "qoi": ["displacement", "reaction"], "accuracyTarget": 0.05, "budget": {"maxElements": 5000000, "maxRuns": 20, "maxWallSeconds": 86400.0}, "status": "draft"}],  # 创建默认分析任务。
        "cognitiveMap": {"landmarks": [], "decisionEdges": [], "version": 1},  # 初始化有限元认知地图。
        "regions": [],  # 初始化局部区域集合。
        "meshPolicies": [{"id": mesh_id, "name": "默认工业网格策略", "taskRef": task_id, "baseSize": 1.0, "elementFamily": "auto", "regionRules": [], "budget": {"maxElements": 5000000, "maxIterations": 10}, "status": "draft"}],  # 创建默认网格策略。
        "solverPlans": [{"id": solver_id, "name": "默认求解计划", "taskRef": task_id, "meshPolicyRef": mesh_id, "solver": "calculix", "settings": {}, "status": "draft"}],  # 创建默认求解计划。
        "feedback": [],  # 初始化反馈集合。
        "artifacts": [],  # 初始化产物集合。
        "experienceRefs": [],  # 初始化经验引用。
        "extensions": {},  # 初始化命名空间扩展。
    }  # 完成核心文档构造。
    return upgrade_document(document)  # 升级并返回工业 BSDL 文档。

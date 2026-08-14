"""执行 BridgeMind Studio 的结构、数值、服务、界面资源和闭环自检。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供自检结果序列化。
import shutil  # 提供可选 Node.js 命令检测。
import subprocess  # 提供 JavaScript 语法检查执行。
import tempfile  # 提供隔离数据库和导出目录。
import sys  # 提供项目根目录模块搜索路径配置。
from pathlib import Path  # 提供项目路径处理。
from typing import Any, Callable  # 提供自检函数类型注解。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。
sys.path.insert(0, str(ROOT))  # 确保直接运行脚本时可以导入 bridge_mind 包。

from fastapi.testclient import TestClient  # 提供 API 集成测试客户端。
from jsonschema import Draft202012Validator  # 提供 Schema 元验证。
from bridge_mind.api import create_app  # 导入 FastAPI 应用工厂。
from bridge_mind.cognition.orchestrator import propose_strategy  # 导入多专家策略编排器。
from bridge_mind.fea.frame3d import solve_document  # 导入空间梁快速求解器。
from bridge_mind.importers.point_cloud import build_bsdl_from_point_cloud  # 导入点云转换器。
from bridge_mind.service import BridgeMindService  # 导入高层业务闭环服务。
from bridge_mind.utils import deep_copy, load_json  # 导入深复制和 JSON 读取工具。
from bridge_mind.validator import validate_document  # 导入 BSDL 验证器。


def execute_check(name: str, function: Callable[[], dict[str, Any]]) -> dict[str, Any]:  # 执行单项自检并捕获结构化结果。
    try:  # 捕获任意自检异常。
        details = function()  # 执行具体自检函数。
        return {"name": name, "status": "PASS", "details": details}  # 返回通过状态和指标。
    except Exception as error:  # 处理自检失败。
        return {"name": name, "status": "FAIL", "details": {"type": type(error).__name__, "message": str(error)}}  # 返回失败状态和异常摘要。


def check_schema() -> dict[str, Any]:  # 检查 BSDL Schema 自身合法性。
    schema = load_json(ROOT / "schema" / "bsdl.schema.json")  # 读取正式 Schema。
    Draft202012Validator.check_schema(schema)  # 执行 Draft 2020-12 元验证。
    return {"definitionCount": len(schema.get("$defs", {})), "schemaId": schema.get("$id")}  # 返回 Schema 规模指标。


def check_examples() -> dict[str, Any]:  # 检查两个正式示例的语言一致性。
    output: dict[str, Any] = {}  # 初始化示例报告。
    for filename in ["two_girder_bridge.bsdl.json", "cantilever_3d.bsdl.json"]:  # 遍历两个正式示例。
        document = load_json(ROOT / "examples" / filename)  # 读取示例文档。
        validation = validate_document(document)  # 执行完整 BSDL 验证。
        if not validation["valid"]:  # 检查示例是否合法。
            raise AssertionError({"file": filename, "errors": validation["errors"]})  # 对非法示例抛出明确失败。
        output[filename] = {"level": validation["level"], "stats": validation["stats"]}  # 保存示例验证指标。
    return output  # 返回两个示例的验证结果。


def check_strategy_and_solver() -> dict[str, Any]:  # 检查多专家策略、认知地图和快速 FEA。
    document = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取双主梁桥示例。
    proposed, initial_report = propose_strategy(document)  # 生成初始区域网格策略。
    result = solve_document(proposed)  # 根据策略执行空间梁快速试算。
    feedback_document, feedback_report = propose_strategy(proposed, result)  # 根据计算结果生成 FEA 热点区。
    validation = validate_document(feedback_document)  # 验证反馈闭环文档。
    if not validation["valid"]:  # 检查反馈文档合法性。
        raise AssertionError(validation["errors"])  # 对反馈规则失败给出明确异常。
    if result["globalMetrics"]["relativeForceBalanceResidual"] >= 1.0e-7:  # 检查高密度网格下反力平衡残差。
        raise AssertionError(result["globalMetrics"])  # 对数值平衡失败给出完整指标。
    return {"initialRegions": initial_report["finalRegionCount"], "feedbackRegions": feedback_report["finalRegionCount"], "hotspots": feedback_report["hotspotRegionCount"], "landmarks": len(feedback_document["cognitiveMap"]["landmarks"]), "mesh": result["mesh"]["stats"], "globalMetrics": result["globalMetrics"]}  # 返回策略和求解指标。


def check_repository_workflow() -> dict[str, Any]:  # 检查修订、运行、经验、模板和 Adapter 全闭环。
    with tempfile.TemporaryDirectory() as temporary_directory:  # 创建隔离的自检工作目录。
        temporary = Path(temporary_directory)  # 规范化临时目录路径。
        service = BridgeMindService(ROOT, temporary / "selfcheck.sqlite3")  # 使用临时数据库创建服务。
        service.runs_directory = temporary / "runs"  # 把导出产物重定向到临时目录。
        service.runs_directory.mkdir(parents=True, exist_ok=True)  # 创建临时运行目录。
        seeded_projects = service.seed_examples()  # 装入示例项目。
        seeded_templates = service.seed_templates()  # 装入包括经验读回策略在内的初始模板。
        project_id = "project.two_girder_bridge"  # 选择完整闭环示例项目。
        strategy = service.propose_project_strategy(project_id)  # 保存 V2 多专家策略。
        solved = service.solve_project(project_id)  # 保存 V3 FEA 反馈。
        experience = service.extract_and_save_experiences(project_id, 1, 3, solved["runId"])  # 提取 V1 到 V3 经验。
        exports = {adapter: service.export_project(project_id, adapter)["report"] for adapter in ["bsdl", "gmsh", "calculix"]}  # 执行三个确定性导出器。
        if any(report.get("blocked") for report in exports.values()):  # 检查是否出现阻断性导出问题。
            raise AssertionError(exports)  # 对阻断性转换返回完整报告。
        return {"seededProjects": len(seeded_projects), "seededTemplates": len(seeded_templates), "strategyRevision": strategy["savedRevision"]["revision"], "feedbackRevision": solved["feedbackRevision"]["revision"], "runStatus": solved["result"]["status"], "experienceCount": experience["recordCount"], "revisionCount": len(service.repository.list_revisions(project_id)), "templateCount": len(service.repository.list_templates()), "exportAdapters": list(exports)}  # 返回业务闭环指标。


def check_memory_readback() -> dict[str, Any]:  # 检查跨项目经验写入、检索、读回和人工审核闭环。
    with tempfile.TemporaryDirectory() as temporary_directory:  # 创建隔离的经验读回工作目录。
        temporary = Path(temporary_directory)  # 规范化临时目录路径。
        service = BridgeMindService(ROOT, temporary / "memory.sqlite3", temporary / "runs")  # 创建隔离业务服务。
        service.seed_templates()  # 装入默认经验读回策略。
        source = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取训练与测试共同使用的结构原型。
        training = deep_copy(source)  # 复制训练项目文档。
        training["documentId"] = "document.memory.selfcheck.train"  # 设置训练文档稳定 ID。
        training["project"]["id"] = "project.memory.selfcheck.train"  # 设置训练项目稳定 ID。
        training["project"]["name"] = "经验读回自检训练项目"  # 设置训练项目名称。
        service.create_project(training)  # 保存训练项目初始修订。
        strategy = service.propose_project_strategy(training["project"]["id"], use_memory=False)  # 生成不使用历史经验的基线策略。
        revised = deep_copy(strategy["document"])  # 复制基线策略供专家修订。
        support = next(region for region in revised["regions"] if region.get("semanticType") == "support" and region.get("source") == "agent")  # 选择一个规则专家生成的支座区域。
        support["targetSize"] = float(support["targetSize"]) * 0.5  # 模拟专家把支座目标网格尺寸减半。
        support["meshLevel"] = min(10, int(support["meshLevel"]) + 2)  # 模拟专家提高支座网格等级。
        support["source"] = "human"  # 标记最终策略来自专家修订。
        support["status"] = "accepted"  # 标记专家已经批准该局部策略。
        support.setdefault("reason", []).append("自检专家批准进一步加密支座区域。")  # 保存可审计的人工修订理由。
        saved = service.save_revision(training["project"]["id"], revised, "human.selfcheck", "human", "经验读回自检专家修订", "approved", 2)  # 保存训练项目人工修订。
        extracted = service.extract_and_save_experiences(training["project"]["id"], 2, int(saved["revision"]["revision"]))  # 把人工修订编译成结构化经验。
        accepted = [record for record in extracted["records"] if record.get("scopeType") == "region" and record.get("status") == "accepted"]  # 筛选可供未来读取的局部经验。
        if not accepted:  # 检查是否成功沉淀已批准经验。
            raise AssertionError(extracted)  # 对经验写入失败返回完整记录。
        testing = deep_copy(source)  # 复制一个新的未见测试项目。
        testing["documentId"] = "document.memory.selfcheck.test"  # 设置测试文档稳定 ID。
        testing["project"]["id"] = "project.memory.selfcheck.test"  # 设置测试项目稳定 ID。
        testing["project"]["name"] = "经验读回自检测试项目"  # 设置测试项目名称。
        for node in testing.get("nodes", []):  # 遍历节点以改变绝对空间位置。
            node["position"][0] = float(node["position"][0]) + 100.0  # 沿桥轴整体平移以验证经验不依赖绝对坐标。
        service.create_project(testing)  # 保存新用户测试项目。
        baseline = service.propose_project_strategy(testing["project"]["id"], commit=False, use_memory=False)  # 生成不读经验的控制策略。
        inherited = service.propose_project_strategy(testing["project"]["id"], commit=False, use_memory=True)  # 生成读取跨项目经验的实验策略。
        memory = inherited["strategy"].get("memory", {})  # 读取经验读回报告。
        if int(memory.get("appliedRegionCount", 0)) < 1:  # 检查经验是否真实影响未来策略。
            raise AssertionError(memory)  # 对未读回经验返回完整匹配报告。
        baseline_actions = sorted((region.get("semanticType"), round(float(region.get("targetSize", 0.0)), 9), int(region.get("meshLevel", 0))) for region in baseline["document"].get("regions", []) if region.get("semanticType") == "support")  # 汇总控制组支座动作。
        inherited_actions = sorted((region.get("semanticType"), round(float(region.get("targetSize", 0.0)), 9), int(region.get("meshLevel", 0))) for region in inherited["document"].get("regions", []) if region.get("semanticType") == "support")  # 汇总经验组支座动作。
        if baseline_actions == inherited_actions:  # 检查产品行为是否发生可测量变化。
            raise AssertionError({"baseline": baseline_actions, "inherited": inherited_actions})  # 对行为未变化返回两组动作。
        used_ids = inherited["document"].get("experienceRefs", [])  # 读取实际进入未来策略的经验引用。
        if not used_ids:  # 检查读回结果是否可追溯。
            raise AssertionError(inherited["document"].get("feedback", []))  # 对缺少经验来源返回反馈记录。
        return {"acceptedExperienceCount": len(accepted), "matchedRegionCount": int(memory.get("matchedRegionCount", 0)), "appliedRegionCount": int(memory.get("appliedRegionCount", 0)), "usedExperienceIds": used_ids, "baselineSupportActions": baseline_actions, "inheritedSupportActions": inherited_actions}  # 返回跨项目读回指标。


def check_point_cloud() -> dict[str, Any]:  # 检查点云分割和 BSDL 初始对象生成。
    document, report = build_bsdl_from_point_cloud(ROOT / "examples" / "two_girder_bridge.xyz")  # 执行示例点云转换。
    validation = validate_document(document)  # 验证生成的 BSDL 文档。
    if not validation["valid"]:  # 检查点云文档合法性。
        raise AssertionError(validation["errors"])  # 对非法转换结果返回验证问题。
    return {"inputPoints": report["inputPointCount"], "sampledPoints": report["sampledPointCount"], "clusters": report["clusterCount"], "components": len(document["components"]), "validationLevel": validation["level"]}  # 返回点云处理指标。


def check_api() -> dict[str, Any]:  # 检查 API 和静态 Web 资源的可访问性。
    with tempfile.TemporaryDirectory() as temporary_directory:  # 创建隔离 API 数据库目录。
        client = TestClient(create_app(Path(temporary_directory) / "api.sqlite3"))  # 创建测试客户端。
        health = client.get("/api/health")  # 请求健康检查。
        projects = client.get("/api/projects")  # 请求项目列表。
        templates = client.get("/api/templates")  # 请求模板列表。
        html = client.get("/")  # 请求 Web 首页。
        javascript = client.get("/app.js")  # 请求前端脚本。
        stylesheet = client.get("/styles.css")  # 请求前端样式。
        document = client.get("/api/projects/project.two_girder_bridge").json()  # 读取示例文档。
        validation = client.post("/api/validate", json={"document": document})  # 验证未保存会话文档接口。
        statuses = [health.status_code, projects.status_code, templates.status_code, html.status_code, javascript.status_code, stylesheet.status_code, validation.status_code]  # 汇总关键 HTTP 状态。
        if any(status != 200 for status in statuses) or validation.json().get("valid") is not True:  # 检查 API 和静态资源状态。
            raise AssertionError({"statuses": statuses, "validation": validation.json()})  # 对失败状态给出完整上下文。
        return {"health": health.json(), "projectCount": len(projects.json()), "templateCount": len(templates.json()), "htmlBytes": len(html.content), "javascriptBytes": len(javascript.content), "stylesheetBytes": len(stylesheet.content)}  # 返回 API 与资源指标。


def check_javascript() -> dict[str, Any]:  # 使用 Node.js 检查前端 JavaScript 语法。
    executable = shutil.which("node")  # 查找 Node.js 可执行文件。
    if executable is None:  # 处理环境未安装 Node.js。
        return {"status": "SKIPPED", "reason": "node executable not found"}  # 返回非阻断跳过状态。
    completed = subprocess.run([executable, "--check", str(ROOT / "web" / "app.js")], capture_output=True, text=True, check=False)  # 执行 JavaScript 语法检查。
    if completed.returncode != 0:  # 检查 Node.js 返回状态。
        raise AssertionError(completed.stderr or completed.stdout)  # 对语法失败返回诊断文本。
    return {"node": executable, "file": "web/app.js", "bytes": (ROOT / "web" / "app.js").stat().st_size}  # 返回前端语法检查指标。


def write_report(checks: list[dict[str, Any]]) -> Path:  # 把自检结果写成 Markdown 报告。
    passed = sum(1 for check in checks if check["status"] == "PASS")  # 统计通过项数量。
    failed = sum(1 for check in checks if check["status"] == "FAIL")  # 统计失败项数量。
    lines = ["# BridgeMind Studio 1.1.0 + BSDL Industrial 1.0 自检报告", "", f"结果：{passed} 项通过，{failed} 项失败。", ""]  # 初始化报告标题与总览。
    for check in checks:  # 遍历全部自检项。
        lines.extend([f"## {check['status']} · {check['name']}", "", "```json", json.dumps(check["details"], ensure_ascii=False, indent=2), "```", ""])  # 写入每项结构化结果。
    report_path = ROOT / "SELF_CHECK_REPORT.md"  # 指定自检报告输出路径。
    report_path.write_text("\n".join(lines), encoding="utf-8")  # 保存 Markdown 报告。
    return report_path  # 返回报告路径。


def main() -> int:  # 执行全部自检并返回进程状态码。
    checks = [  # 定义固定顺序的自检清单。
        execute_check("JSON Schema 元验证", check_schema),  # 检查语言 Schema。
        execute_check("正式示例验证", check_examples),  # 检查 BSDL 示例。
        execute_check("多专家认知与快速 FEA", check_strategy_and_solver),  # 检查策略和数值闭环。
        execute_check("修订—反馈—经验—Adapter 闭环", check_repository_workflow),  # 检查业务持久化闭环。
        execute_check("跨项目经验读回链", check_memory_readback),  # 检查外部程序记忆是否改变新项目策略。
        execute_check("点云分割到 BSDL", check_point_cloud),  # 检查上游点云入口。
        execute_check("FastAPI 与 Web 资源", check_api),  # 检查 API 和静态界面资源。
        execute_check("JavaScript 语法", check_javascript),  # 检查前端脚本语法。
    ]  # 完成自检清单定义。
    report_path = write_report(checks)  # 生成 Markdown 自检报告。
    print(json.dumps({"report": str(report_path), "checks": checks}, ensure_ascii=False, indent=2))  # 输出机器可读自检结果。
    return 0 if all(check["status"] == "PASS" for check in checks) else 1  # 以状态码区分整体通过和失败。


if __name__ == "__main__":  # 检查脚本是否直接执行。
    raise SystemExit(main())  # 执行自检并传播状态码。

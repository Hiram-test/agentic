"""BridgeMind CalculiX Web 的项目、版本、导出、执行、反馈与经验编排。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import shutil  # 提供文件复制与阶段包归档能力。
import zipfile  # 提供 CalculiX 阶段包 ZIP 归档。
from pathlib import Path  # 提供项目和输出路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from .adapters.calculix import detect_calculix, export_calculix, run_calculix  # 导入 CalculiX 专用链路。
from .adapters.gmsh import export_gmsh  # 导入 Gmsh GEO 导出器。
from .cognition.orchestrator import propose_strategy  # 导入多专家策略编排器。
from .code_checks.engine import run_code_check_plan  # 导入可审计规范验算引擎。
from .experience import extract_experiences  # 导入修订经验提取器。
from .memory import apply_memory  # 导入跨项目经验读回与策略投影器。
from .fea.frame3d import FrameSolveError, solve_document  # 导入非权威空间梁预览求解器。
from .importers.calculix_inp import build_bsdl_from_calculix_inp  # 导入 CalculiX .inp 兼容转换器。
from .importers.ifc import import_ifc  # 导入 IFC 4.3 映射器。
from .importers.point_cloud import build_bsdl_from_point_cloud  # 导入点云到 BSDL 转换器。
from .repository import Repository  # 导入 SQLite 持久化仓库。
from .utils import content_hash, deep_copy, load_json, save_json, utc_now  # 复用哈希、文档和时间工具。
from .validator import validate_document  # 导入完整 BSDL 验证器。


class BridgeMindService:  # 封装项目、策略、求解、反馈、审计和经验业务流程。
    def __init__(self, root: str | Path, database_path: str | Path | None = None, runs_directory: str | Path | None = None) -> None:  # 初始化服务和可配置持久化目录。
        self.root = Path(root).resolve()  # 规范化项目根目录。
        self.runs_directory = Path(runs_directory).expanduser().resolve() if runs_directory is not None else self.root / "runs"  # 解析部署环境或本地默认运行目录。
        self.runs_directory.mkdir(parents=True, exist_ok=True)  # 确保运行目录存在。
        self.repository = Repository(database_path or self.root / "data" / "bridgemind.sqlite3")  # 初始化 SQLite 仓库。

    def seed_examples(self) -> list[dict[str, Any]]:  # 把基础和工业示例装入数据库但不覆盖用户修订。
        seeded: list[dict[str, Any]] = []  # 初始化示例载入结果。
        filenames = ["two_girder_bridge.bsdl.json", "cantilever_3d.bsdl.json", "calculix_industrial_bridge_segment.bsdl.json"]  # 定义默认示例文件。
        for filename in filenames:  # 遍历默认示例文件。
            path = self.root / "examples" / filename  # 构造示例路径。
            if not path.exists():  # 跳过缺失示例。
                continue  # 继续检查下一示例。
            document = load_json(path)  # 读取示例 BSDL 文档。
            seeded.append(self.repository.ensure_project(document))  # 确保示例项目存在。
        return seeded  # 返回示例载入状态。

    def seed_templates(self) -> list[dict[str, Any]]:  # 首次启动或升级时确保每类内置模板至少存在一个版本。
        existing_ids = {str(item.get("templateId")) for item in self.repository.list_templates()}  # 收集数据库中已有模板稳定 ID。
        templates = [  # 定义与人机闭环对应的初始模板。
            {"templateId": "template.structure_questionnaire", "name": "结构标准问卷 V1", "kind": "structure_questionnaire", "body": {"purpose": "把三维分割对象整理为 BSDL", "requiredSections": ["identity", "geometry", "material", "section", "nodes", "connections", "constraints", "loads", "task", "uncertainty"], "output": "BSDL JSON", "rules": ["未知信息显式标记 unknown", "不得虚构材料与约束", "保留点云或 BIM 源对象 ID"]}},  # 定义结构问卷模板。
            {"templateId": "template.mesh_strategy", "name": "区域网格策略 V1", "kind": "mesh_strategy", "body": {"globalAllocator": ["计算预算", "结构尺度", "任务精度"], "experts": ["support_joint", "discontinuity", "smooth", "fea_hotspot", "human_override"], "actions": ["add_region", "reject_region", "set_mesh_level", "set_target_size"], "approval": "人工修改形成新修订"}},  # 定义多专家策略模板。
            {"templateId": "template.experience_summary", "name": "交互经验摘要 V1", "kind": "experience_summary", "body": {"input": ["before_revision", "after_revision", "fea_metrics"], "outputFields": ["feature_signature", "human_action", "agent_action", "calculation_feedback", "outcome", "applicability", "failure_boundary"], "reuse": "按局部结构特征检索"}},  # 定义经验提炼模板。
            {"templateId": "template.memory_policy", "name": "BSDL 经验读回策略 V1", "kind": "memory_policy", "body": {"enabled": True, "minScore": 0.72, "maxExperiences": 500, "maxPerRegion": 3, "includeSameProject": False, "requireReview": True, "transfer": ["targetSizeRatio", "meshLevel", "maxIterations"], "guardrails": ["不复制项目本地 targetRefs", "不复制绝对坐标和绝对 targetSize", "人工和 FEA 区域不被历史经验覆盖", "经验迁移后默认 needs_review"]}},  # 定义跨项目经验读回策略模板。
        ]  # 完成初始模板定义。
        missing = [item for item in templates if item["templateId"] not in existing_ids]  # 只选择旧数据库中尚未出现的内置模板。
        return [self.repository.save_template(item["templateId"], item["name"], item["kind"], item["body"], True) for item in missing]  # 保存缺失模板并把该类别首版设为默认。

    def _audit(self, action: str, actor: str, source: str, status: str, details: dict[str, Any] | None = None, project_id: str | None = None, revision: int | None = None) -> dict[str, Any]:  # 统一写入审计事件。
        return self.repository.record_audit_event(action, actor, source, status, details, project_id, revision)  # 委托仓库保存不可变事件。

    def _memory_settings(self) -> dict[str, Any]:  # 从默认模板读取经验读回策略并提供安全回退值。
        template = self.repository.get_default_template("memory_policy")  # 读取当前默认经验策略模板。
        body = template.get("body", {}) if isinstance(template, dict) and isinstance(template.get("body"), dict) else {}  # 提取模板主体。
        return {"enabled": bool(body.get("enabled", True)), "minScore": float(body.get("minScore", 0.72)), "maxExperiences": int(body.get("maxExperiences", 500)), "maxPerRegion": int(body.get("maxPerRegion", 3)), "includeSameProject": bool(body.get("includeSameProject", False)), "requireReview": bool(body.get("requireReview", True)), "template": template}  # 返回规范化经验读回设置。

    def _apply_memory_readback(self, document: dict[str, Any], project_id: str, actor: str, enabled: bool | None = None, min_score: float | None = None, limit: int | None = None, max_per_region: int | None = None, include_same_project: bool | None = None) -> tuple[dict[str, Any], dict[str, Any]]:  # 使用数据库经验和默认模板执行一次读回。
        settings = self._memory_settings()  # 读取默认经验读回设置。
        memory_enabled = settings["enabled"] if enabled is None else bool(enabled)  # 合并调用参数和默认启用状态。
        if not memory_enabled:  # 检查是否关闭经验读回。
            return deep_copy(document), {"enabled": False, "candidateExperienceCount": 0, "matchedRegionCount": 0, "appliedRegionCount": 0, "experienceRefs": [], "perRegion": [], "template": settings.get("template")}  # 返回明确的关闭报告。
        memory_limit = max(1, min(5000, int(limit if limit is not None else settings["maxExperiences"])))  # 规范化经验查询上限。
        experiences = self.repository.list_experiences(None, None, memory_limit)  # 从全局经验库读取最近经验。
        updated, report = apply_memory(document, experiences, project_id, float(min_score if min_score is not None else settings["minScore"]), int(max_per_region if max_per_region is not None else settings["maxPerRegion"]), bool(include_same_project if include_same_project is not None else settings["includeSameProject"]), actor, bool(settings["requireReview"]))  # 把历史经验投影到当前 BSDL 策略。
        report["template"] = settings.get("template")  # 记录本次读回采用的模板版本。
        return updated, report  # 返回经验增强文档和读回报告。

    def _artifact_relative_path(self, path: str | Path) -> str:  # 把运行产物转换为安全相对下载路径。
        candidate = Path(path).resolve()  # 规范化产物路径。
        root = self.runs_directory.resolve()  # 规范化运行目录。
        if candidate != root and root not in candidate.parents:  # 检查产物是否位于隔离目录。
            raise ValueError(f"产物不在 runs 目录中：{candidate}")  # 阻止路径逃逸。
        return candidate.relative_to(root).as_posix()  # 返回跨平台相对路径。

    def _zip_directory(self, directory: str | Path) -> Path:  # 把阶段输出目录归档为可下载 ZIP。
        source = Path(directory).resolve()  # 规范化阶段目录。
        archive = source.with_suffix(".zip")  # 构造归档路径。
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:  # 创建压缩归档。
            for path in sorted(source.rglob("*")):  # 遍历阶段目录中的全部文件。
                if path.is_file():  # 只归档普通文件。
                    bundle.write(path, path.relative_to(source).as_posix())  # 保存稳定相对路径。
        return archive  # 返回 ZIP 路径。

    def create_project(self, document: dict[str, Any], author: str = "human.web", source: str = "manual", summary: str = "创建项目") -> dict[str, Any]:  # 验证并创建新项目。
        report = validate_document(document)  # 对输入文档执行完整验证。
        if not report["valid"]:  # 检查是否存在阻断问题。
            raise ValueError({"message": "BSDL 文档验证失败。", "validation": report})  # 阻止保存非法项目。
        created = self.repository.create_project(document, author, source, summary)  # 保存首个不可变修订。
        self._audit("project.create", author, source, "succeeded", {"summary": summary, "contentHash": created["contentHash"]}, created["projectId"], 1)  # 保存项目创建审计。
        return {"project": created, "validation": report}  # 返回项目创建结果和验证报告。

    def validate_project(self, project_id: str, revision: int | None = None) -> dict[str, Any]:  # 验证数据库中的指定修订。
        document = self.repository.get_document(project_id, revision)  # 读取目标修订文档。
        return validate_document(document)  # 返回完整验证报告。

    def save_revision(self, project_id: str, document: dict[str, Any], author: str, source: str, summary: str, status: str = "working", expected_revision: int | None = None) -> dict[str, Any]:  # 验证并保存带并发保护的新修订。
        report = validate_document(document)  # 执行保存前验证。
        if not report["valid"]:  # 检查是否存在阻断问题。
            raise ValueError({"message": "新修订验证失败，未写入数据库。", "validation": report})  # 阻止非法修订进入版本链。
        saved = self.repository.save_revision(project_id, document, author, source, summary, status, expected_revision)  # 保存不可变修订。
        self._audit("revision.save", author, source, "succeeded", {"summary": summary, "status": status, "parentRevision": saved["parentRevision"], "contentHash": saved["contentHash"]}, project_id, saved["revision"])  # 保存版本审计。
        return {"revision": saved, "validation": report}  # 返回保存结果和验证报告。

    def propose_project_strategy(self, project_id: str, revision: int | None = None, commit: bool = True, author: str = "software.bridgemind", summary: str = "多专家生成区域网格策略", use_memory: bool | None = None, memory_min_score: float | None = None, memory_limit: int | None = None, memory_max_per_region: int | None = None, include_same_project_memory: bool | None = None) -> dict[str, Any]:  # 对项目运行多专家策略并自动读回历史经验。
        document = self.repository.get_document(project_id, revision)  # 读取目标修订文档。
        input_revision = int(document.get("revision", {}).get("number", revision or 1))  # 读取策略输入修订。
        updated, report = propose_strategy(document, None, replace_generated=True, actor_id=author)  # 先用当前结构和规则专家生成基础策略。
        updated, memory_report = self._apply_memory_readback(updated, project_id, author, use_memory, memory_min_score, memory_limit, memory_max_per_region, include_same_project_memory)  # 再把跨项目历史经验读回基础策略。
        validation = validate_document(updated)  # 验证经验增强后的文档。
        if not validation["valid"]:  # 检查生成策略是否合法。
            raise RuntimeError({"message": "策略生成或经验读回结果未通过 BSDL 验证。", "validation": validation, "strategy": report, "memory": memory_report})  # 阻止非法自动结果。
        saved = self.repository.save_revision(project_id, updated, author, "agent", summary, "working", input_revision) if commit else None  # 根据请求保存带并发保护的 Agent 修订。
        if saved is not None:  # 检查是否写入版本链。
            updated = saved["document"]  # 使用数据库规范化后的修订元数据。
        self._audit("strategy.propose", author, "agent", "succeeded", {"commit": commit, "generatedRegionCount": report.get("generatedRegionCount"), "memoryEnabled": memory_report.get("enabled"), "memoryAppliedRegionCount": memory_report.get("appliedRegionCount"), "memoryExperienceRefs": memory_report.get("experienceRefs", [])}, project_id, saved.get("revision") if saved else input_revision)  # 保存策略与经验读回审计。
        return {"document": updated, "strategy": report, "memory": memory_report, "validation": validation, "savedRevision": saved}  # 返回策略、经验读回、文档和可选修订。

    def preview_project_memory(self, project_id: str, revision: int | None = None, min_score: float | None = None, limit: int | None = None, max_per_region: int | None = None, include_same_project: bool | None = None, actor: str = "software.bridgemind") -> dict[str, Any]:  # 在不保存修订的情况下预览经验读回效果。
        document = self.repository.get_document(project_id, revision)  # 读取目标项目修订。
        proposed, strategy_report = propose_strategy(document, None, replace_generated=True, actor_id=actor)  # 先生成可比较的基础区域策略。
        enhanced, memory_report = self._apply_memory_readback(proposed, project_id, actor, True, min_score, limit, max_per_region, include_same_project)  # 执行只读经验匹配和策略投影。
        validation = validate_document(enhanced)  # 验证预览结果仍满足 BSDL 规则。
        return {"document": enhanced, "strategy": strategy_report, "memory": memory_report, "validation": validation}  # 返回不落库的读回预览。

    def solve_project(self, project_id: str, revision: int | None = None, mesh_policy_id: str | None = None, load_case_id: str | None = None, commit_feedback: bool = True, author: str = "software.bridgemind") -> dict[str, Any]:  # 执行非权威快速预览并可把结果反馈写入新修订。
        document = self.repository.get_document(project_id, revision)  # 读取目标修订文档。
        actual_revision = int(document.get("revision", {}).get("number", revision or 1))  # 获取实际修订号。
        validation = validate_document(document)  # 执行求解前验证。
        if not validation["valid"]:  # 检查求解前阻断问题。
            raise ValueError({"message": "求解前 BSDL 验证失败。", "validation": validation})  # 阻止非法模型进入求解器。
        input_payload = {"meshPolicyRef": mesh_policy_id, "loadCaseRef": load_case_id, "documentId": document.get("documentId"), "authoritative": False}  # 构造运行输入摘要。
        run_id = self.repository.start_run(project_id, actual_revision, "builtin_frame3d_preview", input_payload)  # 创建运行记录。
        try:  # 捕获确定性求解失败。
            result = solve_document(document, mesh_policy_id, load_case_id)  # 执行空间梁快速预览。
            result["runId"] = run_id  # 把数据库运行 ID 写入结果。
            result["authoritative"] = False  # 明确该结果只用于交互预览。
            self.repository.finish_run(run_id, result=result)  # 保存成功运行结果。
        except FrameSolveError as error:  # 处理结构或数值求解失败。
            error_payload = {"type": "FrameSolveError", "message": str(error), "details": error.details}  # 构造结构化错误对象。
            self.repository.finish_run(run_id, error=error_payload)  # 保存失败运行状态。
            self._audit("preview.solve", author, "builtin_frame3d", "failed", error_payload, project_id, actual_revision)  # 保存失败审计。
            raise RuntimeError(error_payload) from error  # 向 API 或 CLI 返回明确失败。
        feedback_revision = None  # 初始化可选 FEA 反馈修订。
        feedback_document = None  # 初始化可选反馈文档。
        strategy_report = None  # 初始化可选热点策略报告。
        if commit_feedback:  # 检查是否把计算结果写回版本链。
            feedback_document = deep_copy(document)  # 深复制求解输入文档。
            feedback_id = f"feedback.fea.{run_id.split('.')[-1][:12]}"  # 生成 FEA 反馈 ID。
            feedback_document.setdefault("feedback", []).append({"id": feedback_id, "source": "fea", "kind": "fea_result", "createdAt": utc_now(), "createdBy": author, "targetRefs": [str(item.get("componentRef")) for item in result.get("elementResults", [])[:20]], "before": None, "after": {"runId": run_id, "loadCaseRef": result.get("loadCaseRef")}, "metrics": dict(result.get("globalMetrics", {})), "comment": "内置空间梁非权威快速预览结果与反力平衡反馈。", "status": "recorded"})  # 保存计算反馈对象。
            feedback_document, strategy_report = propose_strategy(feedback_document, result, replace_generated=True, actor_id=author)  # 根据预览结果重建 Agent 区域并加入热点区。
            feedback_document, memory_report = self._apply_memory_readback(feedback_document, project_id, author)  # 在 FEA 热点形成后重新读回跨项目经验并保留 FEA 高优先级区域。
            strategy_report["memory"] = memory_report  # 把读回报告挂到本次 FEA 策略报告中。
            feedback_validation = validate_document(feedback_document)  # 验证反馈文档。
            if not feedback_validation["valid"]:  # 检查反馈闭环是否合法。
                raise RuntimeError({"message": "FEA 反馈文档未通过验证。", "validation": feedback_validation})  # 阻止非法反馈修订。
            feedback_revision = self.repository.save_revision(project_id, feedback_document, author, "fea_preview", f"快速预览反馈 {run_id}", "working", actual_revision)  # 保存新的反馈修订。
            feedback_document = feedback_revision["document"]  # 使用数据库规范化后的修订元数据。
        self._audit("preview.solve", author, "builtin_frame3d", "succeeded", {"runId": run_id, "commitFeedback": commit_feedback, "authoritative": False}, project_id, actual_revision)  # 保存成功审计。
        return {"runId": run_id, "result": result, "inputRevision": actual_revision, "feedbackRevision": feedback_revision, "feedbackDocument": feedback_document, "strategy": strategy_report}  # 返回运行和可选反馈修订。

    def extract_and_save_experiences(self, project_id: str, revision_from: int, revision_to: int, run_id: str | None = None) -> dict[str, Any]:  # 从两个修订提取经验并写入经验库。
        before = self.repository.get_document(project_id, revision_from)  # 读取旧修订。
        after = self.repository.get_document(project_id, revision_to)  # 读取新修订。
        metrics: dict[str, Any] = {}  # 初始化可选运行指标。
        if run_id is not None:  # 检查是否关联一次 FEA 运行。
            run = self.repository.get_run(run_id)  # 读取运行记录。
            if isinstance(run.get("result"), dict):  # 检查运行结果存在。
                metrics = dict(run["result"].get("globalMetrics", run["result"].get("summary", {})))  # 提取预览或 CalculiX 指标。
        records = extract_experiences(project_id, revision_from, revision_to, before, after, metrics)  # 生成结构化经验记录。
        saved = [self.repository.save_experience(record) for record in records]  # 把所有经验写入数据库。
        self._audit("experience.extract", "software.bridgemind", "experience", "succeeded", {"revisionFrom": revision_from, "revisionTo": revision_to, "recordCount": len(records), "runId": run_id}, project_id, revision_to)  # 保存经验提取审计。
        return {"recordCount": len(records), "records": records, "saved": saved}  # 返回经验提取结果。

    def import_point_cloud(self, path: str | Path, eps: float = 0.6, min_samples: int = 6, voxel_size: float = 0.2, author: str = "software.pointcloud_importer") -> dict[str, Any]:  # 导入点云并创建新 BSDL 项目。
        document, report = build_bsdl_from_point_cloud(path, eps, min_samples, voxel_size)  # 执行点云分割和语言生成。
        validation = validate_document(document)  # 验证生成文档。
        if not validation["valid"]:  # 检查生成文档合法性。
            raise RuntimeError({"message": "点云生成的 BSDL 未通过验证。", "validation": validation})  # 阻止非法导入项目。
        created = self.repository.create_project(document, author, "point_cloud", "点云分割生成初始 BSDL 项目")  # 创建点云项目。
        self._audit("import.point_cloud", author, "point_cloud", "succeeded", report, created["projectId"], created["revision"])  # 保存导入审计。
        return {"project": created, "import": report, "validation": validation}  # 返回导入结果。

    def import_calculix_inp(self, path: str | Path, author: str = "software.calculix_inp_importer") -> dict[str, Any]:  # 导入 CalculiX .inp 并创建显示-only BSDL 项目。
        source = Path(path)  # 规范化上传或本地 deck 路径。
        native_directory = self.runs_directory / "native_decks"  # 指定原生 deck 隔离目录。
        native_directory.mkdir(parents=True, exist_ok=True)  # 确保原生 deck 目录存在。
        destination = native_directory / f"{source.stem}_{content_hash({'name': source.name, 'size': source.stat().st_size})[:12]}{source.suffix or '.inp'}"  # 构造稳定且不覆盖的原生 deck 路径。
        shutil.copy2(source, destination)  # 把上传 deck 复制到 runs/native_decks。
        document, report = build_bsdl_from_calculix_inp(source, destination, destination)  # 生成显示 BSDL 并声明原生 deck 直通。
        document.setdefault("extensions", {}).setdefault("nativeCalculiX", {})["useNativeDeck"] = True  # 强制启用原生 deck 直通。
        document["extensions"]["nativeCalculiX"]["deckPath"] = str(destination)  # 把服务侧保存路径写入扩展。
        validation = validate_document(document)  # 验证生成文档。
        if not validation["valid"]:  # 检查生成文档合法性。
            raise RuntimeError({"message": "CalculiX .inp 生成的 BSDL 未通过验证。", "validation": validation})  # 阻止非法导入项目。
        created = self.repository.create_project(document, author, "imported", f"CalculiX .inp 兼容导入 {source.name}")  # 创建导入项目。
        self._audit("import.calculix_inp", author, "imported", "succeeded", report, created["projectId"], created["revision"])  # 保存导入审计。
        return {"project": created, "import": report, "validation": validation}  # 返回导入结果。

    def import_ifc_file(self, path: str | Path, mvd_profile_path: str | Path | None = None, project_id: str | None = None, author: str = "software.ifc43_importer") -> dict[str, Any]:  # 导入 IFC 4.3 文件并创建 BSDL 项目。
        imported = import_ifc(path, mvd_profile_path, project_id)  # 执行 IFC 4.3、MVD 和身份映射。
        document = imported["document"]  # 读取转换后的 BSDL 文档。
        validation = validate_document(document)  # 执行 BSDL 工业验证。
        if not validation["valid"]:  # 检查导入结果是否可保存。
            raise RuntimeError({"message": "IFC 转换结果未通过 BSDL 验证。", "validation": validation, "conversion": imported["conversionReport"]})  # 阻止非法项目进入数据库。
        created = self.repository.create_project(document, author, "ifc43", "IFC 4.3/MVD 导入初始 BSDL 项目")  # 创建 IFC 项目。
        self._audit("import.ifc43", author, "ifc43", "succeeded", {"mvd": imported["mvd"], "conversionReport": imported["conversionReport"]}, created["projectId"], created["revision"])  # 保存 IFC 导入审计。
        return {**imported, "project": created, "validation": validation}  # 返回项目、MVD 和转换报告。

    def export_project(self, project_id: str, adapter: str, revision: int | None = None, mesh_policy_id: str | None = None, load_case_id: str | None = None, solver_plan_id: str | None = None, finite_element_model_id: str | None = None, strict: bool | None = None, actor: str = "human.web") -> dict[str, Any]:  # 导出当前项目到外部工具输入格式。
        document = self.repository.get_document(project_id, revision)  # 读取目标修订文档。
        actual_revision = int(document.get("revision", {}).get("number", revision or 1))  # 获取实际修订号。
        safe_project = project_id.replace(":", "_").replace("/", "_")  # 构造安全输出文件名前缀。
        if adapter == "calculix":  # 处理 CalculiX 导出。
            requested_output = self.runs_directory / f"{safe_project}_V{actual_revision}.inp"  # 构造 CalculiX 输入路径。
            report = export_calculix(document, requested_output, mesh_policy_id, load_case_id, solver_plan_id, finite_element_model_id, strict)  # 执行 CalculiX 转换。
            raw_output = Path(str(report.get("output", requested_output))).resolve()  # 读取单 deck 或阶段目录。
            output = self._zip_directory(raw_output) if raw_output.is_dir() else raw_output  # 把阶段目录归档为 ZIP。
        elif adapter == "gmsh":  # 处理 Gmsh 导出。
            output = self.runs_directory / f"{safe_project}_V{actual_revision}.geo"  # 构造 Gmsh 脚本路径。
            report = export_gmsh(document, output, mesh_policy_id)  # 执行 Gmsh 转换。
        elif adapter == "bsdl":  # 处理规范化 BSDL 导出。
            output = self.runs_directory / f"{safe_project}_V{actual_revision}.bsdl.json"  # 构造 BSDL 输出路径。
            save_json(output, document)  # 写入完整 BSDL 文档。
            report = {"adapter": "bsdl", "output": str(output), "losses": [], "warnings": [], "blocked": False}  # 构造无损导出报告。
        else:  # 处理未知 Adapter。
            raise ValueError(f"未知导出 Adapter：{adapter}")  # 返回明确错误。
        download_path = self._artifact_relative_path(output)  # 构造安全下载路径。
        self._audit("adapter.export", actor, adapter, "blocked" if report.get("blocked") else "succeeded", {"downloadPath": download_path, "reportId": report.get("id"), "lossCount": len(report.get("losses", []))}, project_id, actual_revision)  # 保存导出审计。
        return {"projectId": project_id, "revision": actual_revision, "report": report, "output": str(output), "downloadPath": download_path}  # 返回导出结果。

    def run_code_check_project(self, project_id: str, plan_id: str, revision: int | None, result_context: dict[str, Any], commit: bool = True, actor: str = "human.web") -> dict[str, Any]:  # 执行项目规则包验算并可保存为新修订。
        document = self.repository.get_document(project_id, revision)  # 读取指定或当前 BSDL 修订。
        actual_revision = int(document.get("revision", {}).get("number", revision or 1))  # 获取验算所基于的实际修订号。
        report = run_code_check_plan(document, plan_id, result_context, self.root)  # 执行受限表达式规则包。
        saved: dict[str, Any] | None = None  # 初始化可选修订保存结果。
        if commit:  # 检查是否需要把验算结果写回项目。
            updated = deep_copy(document)  # 深复制文档避免修改历史快照。
            retained = [item for item in updated.get("codeCheckResults", []) if isinstance(item, dict) and item.get("planRef") != plan_id]  # 保留其他验算计划的结果。
            updated["codeCheckResults"] = retained + list(report.get("results", []))  # 写入当前计划的最新可审计结果。
            for plan in updated.get("codeCheckPlans", []):  # 遍历验算计划更新执行状态。
                if isinstance(plan, dict) and plan.get("id") == plan_id:  # 查找当前验算计划。
                    plan["status"] = "blocked" if report.get("status") == "blocked" else "executed"  # 保存计划最终执行状态。
            validation = validate_document(updated)  # 验证验算结果写回后的完整文档。
            if not validation["valid"]:  # 检查写回文档是否合法。
                raise RuntimeError({"message": "规范验算结果写回后未通过 BSDL 验证。", "validation": validation, "report": report})  # 阻止非法修订进入数据库。
            saved = self.repository.save_revision(project_id, updated, actor, "code_check", f"执行验算计划 {plan_id}", "working", actual_revision)  # 使用乐观并发保护保存新修订。
        audit_revision = int(saved["revision"]) if saved else actual_revision  # 选择审计关联修订号。
        self._audit("code_check.run", actor, "code_check", str(report.get("status", "completed")), {"planId": plan_id, "summary": report.get("summary"), "committed": bool(saved)}, project_id, audit_revision)  # 保存规范验算审计。
        return {"projectId": project_id, "baseRevision": actual_revision, "resultRevision": saved.get("revision") if saved else None, "report": report, "saved": saved}  # 返回验算报告和可选修订结果。

    def calculix_status(self, executable: str | None = None) -> dict[str, Any]:  # 返回当前服务器 CalculiX 可用状态。
        return detect_calculix(executable)  # 委托 CalculiX 探测器。

    def _commit_calculix_results(self, project_id: str, base_revision: int, run_id: str, jobs: list[dict[str, Any]], actor: str) -> dict[str, Any] | None:  # 把成功求解产物和 ResultSet 写入新 BSDL 修订。
        successful = [job for job in jobs if isinstance(job.get("execution"), dict) and job["execution"].get("status") == "succeeded" and isinstance(job["execution"].get("resultSet"), dict)]  # 筛选包含可导入结果集的成功作业。
        if not successful:  # 检查是否存在可提交的求解结果。
            return None  # 没有结果时不创建空修订。
        document = self.repository.get_document(project_id, base_revision)  # 读取运行所基于的不可变文档快照。
        updated = deep_copy(document)  # 深复制文档用于结果回写。
        existing_artifact_ids = {str(item.get("id")) for item in updated.get("artifacts", []) if isinstance(item, dict)}  # 收集已有产物 ID。
        existing_result_ids = {str(item.get("id")) for item in updated.get("resultSets", []) if isinstance(item, dict)}  # 收集已有结果集 ID。
        added_artifacts: list[str] = []  # 初始化新增产物 ID 列表。
        added_results: list[str] = []  # 初始化新增结果集 ID 列表。
        for job in successful:  # 遍历每个成功 CalculiX 作业。
            execution = job["execution"]  # 读取作业执行对象。
            artifact_ids: list[str] = []  # 初始化当前作业产物引用。
            dat_artifact_id: str | None = None  # 初始化 DAT 结果产物引用。
            for artifact in execution.get("artifacts", []):  # 遍历真实文件产物清单。
                if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):  # 检查产物清单基本字段。
                    continue  # 跳过不完整产物记录。
                artifact_path = Path(str(artifact["path"]))  # 解析产物文件路径。
                relative = self._artifact_relative_path(artifact_path)  # 转换为 runs 目录内的安全相对路径。
                suffix = artifact_path.suffix.lower()  # 读取产物扩展名。
                kind = "solver_input" if suffix == ".inp" else ("solver_output" if suffix in {".dat", ".frd", ".sta", ".cvg", ".12d", ".eig"} else ("log" if suffix in {".out", ".log"} else "other"))  # 根据扩展名确定产物类型。
                artifact_id = f"artifact.ccx.{content_hash({'sha': artifact['sha256'], 'name': artifact_path.name})[:20]}"  # 构造稳定且避免空日志哈希冲突的产物 ID。
                artifact_ids.append(artifact_id)  # 保存当前作业产物引用。
                if suffix == ".dat":  # 检查当前产物是否为 DAT 结果文件。
                    dat_artifact_id = artifact_id  # 保存结果字段首选产物引用。
                if artifact_id in existing_artifact_ids:  # 检查产物是否已经写入文档。
                    continue  # 跳过重复产物实体。
                updated.setdefault("artifacts", []).append({"id": artifact_id, "kind": kind, "uri": relative, "format": suffix.lstrip(".") or "binary", "hash": str(artifact["sha256"]), "createdAt": utc_now()})  # 写入 Schema 兼容产物实体。
                existing_artifact_ids.add(artifact_id)  # 更新产物 ID 索引。
                added_artifacts.append(artifact_id)  # 记录本次新增产物。
            result_set = deep_copy(execution["resultSet"])  # 复制 Adapter 生成的结果集摘要。
            result_set["id"] = f"result.calculix.{content_hash({'run': run_id, 'deck': job.get('deck')})[:20]}"  # 使用数据库运行和 deck 构造稳定结果 ID。
            result_set["runRef"] = run_id  # 关联数据库中的真实运行记录。
            result_set["artifactRefs"] = list(dict.fromkeys(artifact_ids))  # 关联当前作业全部产物。
            for field in result_set.get("fields", []):  # 遍历结果字段。
                if isinstance(field, dict):  # 检查字段对象。
                    field["artifactRef"] = dat_artifact_id  # 把字段关联到可解析 DAT 产物。
            if result_set["id"] in existing_result_ids:  # 检查结果集是否已经存在。
                continue  # 跳过重复结果集实体。
            updated.setdefault("resultSets", []).append(result_set)  # 写入结果集实体。
            existing_result_ids.add(result_set["id"])  # 更新结果 ID 索引。
            added_results.append(result_set["id"])  # 记录本次新增结果集。
        if not added_results:  # 检查是否实际新增结果集。
            return None  # 不创建无变化修订。
        validation = validate_document(updated)  # 验证结果和产物回写后的完整 BSDL 文档。
        if not validation["valid"]:  # 检查结果修订合法性。
            raise RuntimeError({"message": "CalculiX 结果回写后未通过 BSDL 验证。", "validation": validation})  # 阻止非法结果修订。
        saved = self.repository.save_revision(project_id, updated, actor, "calculix_result_import", f"导入 CalculiX 运行 {run_id} 的结果与产物", "working", base_revision)  # 使用乐观并发保护保存结果修订。
        return {"revision": saved["revision"], "artifactIds": added_artifacts, "resultSetIds": added_results, "validationLevel": validation.get("level")}  # 返回结果回写摘要。

    def run_calculix_project(self, project_id: str, revision: int | None = None, mesh_policy_id: str | None = None, load_case_id: str | None = None, solver_plan_id: str | None = None, finite_element_model_id: str | None = None, strict: bool | None = True, executable: str | None = None, timeout: float = 3600.0, threads: int = 1, actor: str = "human.web", commit_result: bool = True) -> dict[str, Any]:  # 导出并受控执行 CalculiX 单 deck 或阶段包。
        exported = self.export_project(project_id, "calculix", revision, mesh_policy_id, load_case_id, solver_plan_id, finite_element_model_id, strict, actor)  # 先生成并静态检查 CalculiX 输入。
        actual_revision = int(exported["revision"])  # 读取实际修订号。
        report = exported["report"]  # 读取转换报告。
        raw_output = Path(str(report.get("output", exported["output"]))).resolve()  # 定位单 deck 或阶段目录。
        decks = sorted(raw_output.glob("*.inp")) if raw_output.is_dir() else [raw_output]  # 收集待运行 deck。
        input_payload = {"decks": [str(path) for path in decks], "solverPlanId": solver_plan_id, "finiteElementModelId": finite_element_model_id, "timeout": timeout, "threads": threads, "conversionReportId": report.get("id")}  # 构造运行输入摘要。
        run_id = self.repository.start_run(project_id, actual_revision, "calculix_2.23", input_payload)  # 创建 CalculiX 运行记录。
        if report.get("blocked") or not decks:  # 检查转换阻断或无输入文件。
            error = {"type": "CalculiXExportBlocked", "message": "CalculiX 输入生成被阻断。", "conversion": report}  # 构造阻断错误。
            self.repository.finish_run(run_id, error=error, status_override="blocked")  # 保存阻断运行状态。
            self._audit("calculix.run", actor, "calculix", "blocked", error, project_id, actual_revision)  # 保存阻断审计。
            return {"runId": run_id, "status": "blocked", "export": exported, "jobs": [], "summary": {"message": error["message"]}}  # 返回阻断结果。
        jobs: list[dict[str, Any]] = []  # 初始化阶段或单作业结果。
        for deck in decks:  # 遍历待执行输入文件。
            execution = run_calculix(deck, executable, timeout, threads)  # 受控执行 ccx 或返回 unavailable。
            parsed = execution.get("parsedResults") if execution.get("status") == "succeeded" else None  # 复用 Adapter 已完成的 DAT 结果回读。
            jobs.append({"deck": str(deck), "execution": execution, "results": parsed})  # 保存作业结果。
        statuses = [str(job["execution"].get("status")) for job in jobs]  # 收集作业状态。
        if statuses and all(status == "succeeded" for status in statuses):  # 检查全部作业成功。
            overall_status = "succeeded"  # 设置成功状态。
        elif statuses and all(status == "unavailable" for status in statuses):  # 检查服务器未安装 ccx。
            overall_status = "unavailable"  # 设置不可用状态。
        elif "timeout" in statuses:  # 检查是否存在超时。
            overall_status = "timeout"  # 设置超时状态。
        elif "blocked" in statuses:  # 检查静态阻断。
            overall_status = "blocked"  # 设置阻断状态。
        else:  # 处理部分或全部求解失败。
            overall_status = "failed"  # 设置失败状态。
        summary = {"jobCount": len(jobs), "statuses": statuses, "resultSummaries": [job["results"].get("summaries", {}) for job in jobs if isinstance(job.get("results"), dict)], "authoritative": True, "realSolverExecuted": any(status not in {"unavailable", "blocked"} for status in statuses)}  # 组装运行摘要。
        result_commit = self._commit_calculix_results(project_id, actual_revision, run_id, jobs, actor) if commit_result and overall_status == "succeeded" else None  # 在成功时可选保存结果和产物修订。
        result = {"status": overall_status, "export": exported, "jobs": jobs, "summary": summary, "resultCommit": result_commit}  # 组装数据库结果对象。
        error_payload = None if overall_status in {"succeeded", "unavailable"} else {"type": "CalculiXRunFailure", "message": f"CalculiX 作业状态：{overall_status}", "statuses": statuses}  # 构造可选错误对象。
        self.repository.finish_run(run_id, result=result, error=error_payload, status_override=overall_status)  # 保存最终运行状态和产物。
        self._audit("calculix.run", actor, "calculix", overall_status, {"runId": run_id, "resultCommit": result_commit, **summary}, project_id, int(result_commit["revision"]) if result_commit else actual_revision)  # 保存运行和结果回写审计。
        return {"runId": run_id, **result}  # 返回 CalculiX 运行结果。

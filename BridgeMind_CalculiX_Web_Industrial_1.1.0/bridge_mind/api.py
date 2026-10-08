"""BridgeMind CalculiX Web 的 FastAPI、PWA、文件上传与工业任务接口。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import os  # 提供生产环境配置读取。
import secrets  # 提供 API 密钥常量时间比较。
import shutil  # 提供上传文件复制能力。
import uuid  # 提供上传文件唯一名称。
from pathlib import Path  # 提供路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile  # 提供 Web API、文件上传和请求上下文。
from fastapi.responses import FileResponse, JSONResponse  # 提供文件下载和中间件错误响应。
from fastapi.staticfiles import StaticFiles  # 提供自包含 PWA 静态文件服务。
from pydantic import BaseModel, Field  # 提供请求体结构校验。
from .industrial.capabilities import build_capability_matrix  # 导入工业能力矩阵。
from .repository import RevisionConflictError  # 导入乐观并发冲突异常。
from .service import BridgeMindService  # 导入高层业务服务。
from .validator import validate_document as validate_bsdl_document  # 导入原始文档验证器。
from .version import LANGUAGE_VERSION, PACKAGE_VERSION  # 导入统一版本常量。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


class CreateProjectRequest(BaseModel):  # 定义创建项目请求。
    document: dict[str, Any]  # 接收完整 BSDL 文档。
    author: str = "human.web"  # 设置默认创建者。
    source: str = "manual"  # 设置默认来源。
    summary: str = "创建项目"  # 设置默认摘要。


class ValidateDocumentRequest(BaseModel):  # 定义浏览器未保存文档验证请求。
    document: dict[str, Any]  # 接收当前会话中的完整 BSDL 文档。


class RevisionRequest(BaseModel):  # 定义保存修订请求。
    document: dict[str, Any]  # 接收当前编辑后的完整 BSDL 文档。
    baseRevision: int | None = Field(default=None, ge=1)  # 指定浏览器编辑所基于的修订号。
    author: str = "human.web"  # 设置默认修订作者。
    source: str = "human"  # 设置默认修订来源。
    summary: str = "人工交互修改"  # 设置默认修订摘要。
    status: str = "working"  # 设置默认修订状态。


class StrategyRequest(BaseModel):  # 定义多专家策略与经验读回请求。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    commit: bool = True  # 控制是否保存为新修订。
    author: str = "software.bridgemind"  # 设置默认策略执行者。
    summary: str = "多专家生成区域网格策略"  # 设置默认修订摘要。
    useMemory: bool | None = None  # 可选覆盖默认经验读回开关。
    memoryMinScore: float | None = Field(default=None, ge=0.0, le=1.0)  # 可选覆盖经验相似度阈值。
    memoryLimit: int | None = Field(default=None, ge=1, le=5000)  # 可选覆盖全局经验查询数量。
    memoryMaxPerRegion: int | None = Field(default=None, ge=1, le=20)  # 可选覆盖每个区域最多聚合经验数。
    includeSameProjectMemory: bool | None = None  # 可选允许同项目历史经验参与读回。


class MemoryPreviewRequest(BaseModel):  # 定义不落库的经验读回预览请求。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    minScore: float | None = Field(default=None, ge=0.0, le=1.0)  # 可选覆盖经验相似度阈值。
    limit: int | None = Field(default=None, ge=1, le=5000)  # 可选覆盖经验查询数量。
    maxPerRegion: int | None = Field(default=None, ge=1, le=20)  # 可选覆盖单区域经验数量。
    includeSameProject: bool | None = None  # 可选允许同项目经验参与预览。
    actor: str = "software.bridgemind"  # 设置默认预览执行者。


class SolveRequest(BaseModel):  # 定义非权威快速预览请求。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    meshPolicyId: str | None = None  # 可选指定网格策略。
    loadCaseId: str | None = None  # 可选指定荷载工况。
    commitFeedback: bool = True  # 控制是否保存 FEA 反馈修订。
    author: str = "software.bridgemind"  # 设置默认求解执行者。


class ExperienceRequest(BaseModel):  # 定义经验提取请求。
    revisionFrom: int = Field(ge=1)  # 指定起始修订号。
    revisionTo: int = Field(ge=1)  # 指定结束修订号。
    runId: str | None = None  # 可选关联 FEA 运行指标。


class TemplateRequest(BaseModel):  # 定义提示或策略模板保存请求。
    templateId: str  # 指定模板稳定 ID。
    name: str  # 指定模板显示名称。
    kind: str  # 指定模板类别。
    body: dict[str, Any]  # 保存结构化模板内容。
    makeDefault: bool = False  # 控制是否设为同类默认模板。


class ExportRequest(BaseModel):  # 定义确定性 Adapter 导出请求。
    adapter: str  # 指定 bsdl、gmsh 或 calculix Adapter。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    meshPolicyId: str | None = None  # 可选指定网格策略。
    loadCaseId: str | None = None  # 可选指定荷载工况。
    solverPlanId: str | None = None  # 可选指定 CalculiX 求解计划。
    finiteElementModelId: str | None = None  # 可选指定显式 FE 模型。
    strict: bool | None = None  # 控制是否把未解决的工业语义设为阻断。
    actor: str = "human.web"  # 指定导出动作主体。


class CodeCheckRequest(BaseModel):  # 定义规范验算执行请求。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    resultContext: dict[str, Any] = Field(default_factory=dict)  # 提供规则包所需的结果摘要和验证指标。
    commit: bool = True  # 控制是否把验算结果保存为新修订。
    actor: str = "human.web"  # 指定验算执行主体。


class CalculiXRunRequest(BaseModel):  # 定义 CalculiX 受控运行请求。
    revision: int | None = Field(default=None, ge=1)  # 可选指定历史修订。
    meshPolicyId: str | None = None  # 可选指定网格策略。
    loadCaseId: str | None = None  # 可选指定荷载工况。
    solverPlanId: str | None = None  # 可选指定 CalculiX 求解计划。
    finiteElementModelId: str | None = None  # 可选指定显式 FE 模型。
    strict: bool = True  # 默认使用严格工业转换。
    executable: str | None = None  # 可选指定服务器 ccx 可执行路径。
    timeout: float = Field(default=3600.0, ge=1.0, le=86400.0)  # 设置单作业超时秒数。
    threads: int = Field(default=1, ge=1, le=128)  # 设置 CalculiX 线程数。
    actor: str = "human.web"  # 指定运行发起者。
    commitResult: bool = True  # 控制是否把成功结果和产物保存为新 BSDL 修订。


def _configured_api_keys() -> list[str]:  # 读取逗号分隔的生产 API 密钥。
    return [item.strip() for item in os.getenv("BRIDGEMIND_API_KEYS", "").split(",") if item.strip()]  # 返回非空密钥列表。


def _key_is_valid(provided: str | None, configured: list[str]) -> bool:  # 使用常量时间比较验证 API 密钥。
    return bool(provided) and any(secrets.compare_digest(str(provided), key) for key in configured)  # 返回密钥匹配状态。


def create_app(database_path: str | Path | None = None) -> FastAPI:  # 创建可测试和可部署的 FastAPI 应用。
    configured_database = database_path or os.getenv("BRIDGEMIND_DATABASE_PATH")  # 优先使用测试参数并允许生产环境配置数据库路径。
    configured_runs = os.getenv("BRIDGEMIND_RUNS_PATH")  # 读取可选的持久化作业目录。
    service = BridgeMindService(ROOT, configured_database, configured_runs)  # 初始化高层服务和部署卷路径。
    service.seed_examples()  # 确保基础和工业示例存在。
    service.seed_templates()  # 确保结构问卷、网格策略、经验摘要和读回策略模板存在。
    app = FastAPI(title="BridgeMind CalculiX Web", version=PACKAGE_VERSION, description="BSDL Industrial、移动触控、CalculiX 2.23、IFC 4.3、版本审计和跨项目经验读回闭环。")  # 创建 API 应用。
    app.state.service = service  # 把业务服务挂到应用状态。

    @app.middleware("http")  # 注册 API 密钥与安全响应头中间件。
    async def production_security(request: Request, call_next: Any) -> Any:  # 对生产 API 执行可选访问控制。
        configured = _configured_api_keys()  # 读取当前生产密钥配置。
        exempt = request.url.path in {"/api/health", "/api/capabilities", "/api/calculix/status"}  # 定义无需密钥的探活和只读状态端点。
        if configured and request.url.path.startswith("/api/") and not exempt and not _key_is_valid(request.headers.get("X-API-Key"), configured):  # 检查受保护 API 请求。
            return JSONResponse(status_code=401, content={"detail": "缺少或无效的 X-API-Key。"})  # 返回标准未授权响应。
        response = await call_next(request)  # 执行后续路由或静态文件处理。
        response.headers["X-Content-Type-Options"] = "nosniff"  # 禁止 MIME 类型嗅探。
        response.headers["X-Frame-Options"] = "SAMEORIGIN"  # 限制跨站嵌入。
        response.headers["Referrer-Policy"] = "same-origin"  # 限制来源信息泄露。
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"  # 默认关闭未使用设备权限。
        return response  # 返回处理完成的响应。

    @app.get("/api/health")  # 注册健康检查路由。
    def health() -> dict[str, Any]:  # 返回服务状态和版本。
        return {"status": "ok", "version": PACKAGE_VERSION, "languageVersion": LANGUAGE_VERSION, "projects": len(service.repository.list_projects())}  # 返回健康信息。

    @app.get("/api/capabilities")  # 注册工业能力检查路由。
    def capabilities() -> dict[str, Any]:  # 返回当前实现和运行环境能力。
        return build_capability_matrix()  # 返回单一可信能力矩阵。

    @app.get("/api/calculix/status")  # 注册 CalculiX 运行时探测路由。
    def calculix_status(executable: str | None = None) -> dict[str, Any]:  # 返回 ccx 可执行状态。
        return service.calculix_status(executable)  # 执行受控探测。

    @app.post("/api/validate")  # 注册会话文档直接验证路由。
    def validate_raw_document(request: ValidateDocumentRequest) -> dict[str, Any]:  # 验证尚未保存的浏览器 BSDL 文档。
        return validate_bsdl_document(request.document)  # 返回结构、引用、拓扑和工业验证报告。

    @app.get("/api/projects")  # 注册项目列表路由。
    def list_projects() -> list[dict[str, Any]]:  # 返回所有项目摘要。
        return service.repository.list_projects()  # 查询并返回项目列表。

    @app.post("/api/projects")  # 注册创建项目路由。
    def create_project(request: CreateProjectRequest) -> dict[str, Any]:  # 创建经过验证的新 BSDL 项目。
        try:  # 捕获业务校验错误。
            return service.create_project(request.document, request.author, request.source, request.summary)  # 执行项目创建。
        except (ValueError, RuntimeError) as error:  # 处理可预期业务错误。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回结构化 400 响应。

    @app.get("/api/projects/{project_id}")  # 注册项目文档读取路由。
    def get_project(project_id: str, revision: int | None = Query(default=None, ge=1)) -> dict[str, Any]:  # 读取当前或历史修订文档。
        try:  # 捕获项目或修订缺失。
            return service.repository.get_document(project_id, revision)  # 返回完整 BSDL 文档。
        except KeyError as error:  # 处理不存在资源。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。

    @app.get("/api/projects/{project_id}/revisions")  # 注册修订列表路由。
    def list_revisions(project_id: str) -> list[dict[str, Any]]:  # 返回项目全部修订元数据。
        return service.repository.list_revisions(project_id)  # 查询并返回修订列表。

    @app.post("/api/projects/{project_id}/revisions")  # 注册保存修订路由。
    def save_revision(project_id: str, request: RevisionRequest) -> dict[str, Any]:  # 保存人工或外部工具修改后的新修订。
        try:  # 捕获验证、项目缺失和并发冲突。
            return service.save_revision(project_id, request.document, request.author, request.source, request.summary, request.status, request.baseRevision)  # 执行修订保存。
        except RevisionConflictError as error:  # 处理多人编辑冲突。
            raise HTTPException(status_code=409, detail={"message": str(error), "projectId": error.project_id, "expectedRevision": error.expected_revision, "actualRevision": error.actual_revision}) from error  # 返回可机器处理的 409 响应。
        except KeyError as error:  # 处理不存在项目。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError) as error:  # 处理验证失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/validate")  # 注册项目验证路由。
    def validate_project(project_id: str, revision: int | None = Query(default=None, ge=1)) -> dict[str, Any]:  # 验证当前或历史修订。
        try:  # 捕获项目或修订缺失。
            return service.validate_project(project_id, revision)  # 返回完整验证报告。
        except KeyError as error:  # 处理不存在资源。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。

    @app.post("/api/projects/{project_id}/strategy")  # 注册多专家策略路由。
    def propose_project_strategy(project_id: str, request: StrategyRequest) -> dict[str, Any]:  # 生成或预览区域级网格策略。
        try:  # 捕获策略生成业务错误。
            return service.propose_project_strategy(project_id, request.revision, request.commit, request.author, request.summary, request.useMemory, request.memoryMinScore, request.memoryLimit, request.memoryMaxPerRegion, request.includeSameProjectMemory)  # 执行规则专家与经验读回编排。
        except RevisionConflictError as error:  # 处理策略提交期间的并发冲突。
            raise HTTPException(status_code=409, detail={"message": str(error), "actualRevision": error.actual_revision}) from error  # 返回冲突状态。
        except KeyError as error:  # 处理不存在项目。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError) as error:  # 处理生成或验证失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/memory/preview")  # 注册经验读回预览路由。
    def preview_project_memory(project_id: str, request: MemoryPreviewRequest) -> dict[str, Any]:  # 在不保存修订的情况下查看历史经验会怎样影响当前策略。
        try:  # 捕获项目和验证错误。
            return service.preview_project_memory(project_id, request.revision, request.minScore, request.limit, request.maxPerRegion, request.includeSameProject, request.actor)  # 执行只读经验匹配和策略投影。
        except KeyError as error:  # 处理不存在项目或修订。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError) as error:  # 处理策略或验证失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/solve")  # 注册非权威快速预览路由。
    def solve_project(project_id: str, request: SolveRequest) -> dict[str, Any]:  # 执行内置空间梁预览和可选反馈修订。
        try:  # 捕获求解业务错误。
            return service.solve_project(project_id, request.revision, request.meshPolicyId, request.loadCaseId, request.commitFeedback, request.author)  # 执行快速预览。
        except RevisionConflictError as error:  # 处理反馈修订并发冲突。
            raise HTTPException(status_code=409, detail={"message": str(error), "actualRevision": error.actual_revision}) from error  # 返回冲突状态。
        except KeyError as error:  # 处理不存在项目或修订。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError) as error:  # 处理验证或求解失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/code-checks/{plan_id}")  # 注册可审计规范验算路由。
    def run_code_check(project_id: str, plan_id: str, request: CodeCheckRequest) -> dict[str, Any]:  # 执行项目规则包并可保存结果。
        try:  # 捕获项目、规则包和并发错误。
            return service.run_code_check_project(project_id, plan_id, request.revision, request.resultContext, request.commit, request.actor)  # 执行规范验算业务流程。
        except RevisionConflictError as error:  # 处理验算写回期间的修订冲突。
            raise HTTPException(status_code=409, detail={"message": str(error), "actualRevision": error.actual_revision}) from error  # 返回可处理的并发冲突。
        except KeyError as error:  # 处理项目、修订或计划缺失。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError, FileNotFoundError) as error:  # 处理规则或写回验证失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/calculix/export")  # 注册 CalculiX 专用导出路由。
    def export_calculix_project(project_id: str, request: ExportRequest) -> dict[str, Any]:  # 生成单 deck 或阶段 ZIP。
        try:  # 捕获项目缺失和转换错误。
            return service.export_project(project_id, "calculix", request.revision, request.meshPolicyId, request.loadCaseId, request.solverPlanId, request.finiteElementModelId, request.strict, request.actor)  # 执行 CalculiX 导出。
        except KeyError as error:  # 处理不存在资源。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except ValueError as error:  # 处理转换错误。
            raise HTTPException(status_code=400, detail=str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/calculix/run")  # 注册 CalculiX 受控运行路由。
    def run_calculix_project(project_id: str, request: CalculiXRunRequest) -> dict[str, Any]:  # 生成、静态检查并执行 ccx。
        try:  # 捕获项目、转换和执行错误。
            return service.run_calculix_project(project_id, request.revision, request.meshPolicyId, request.loadCaseId, request.solverPlanId, request.finiteElementModelId, request.strict, request.executable, request.timeout, request.threads, request.actor, request.commitResult)  # 执行完整 CalculiX 链路。
        except KeyError as error:  # 处理不存在资源。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except (ValueError, RuntimeError, FileNotFoundError) as error:  # 处理转换或执行错误。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.get("/api/projects/{project_id}/runs")  # 注册运行列表路由。
    def list_runs(project_id: str, limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:  # 返回项目最近运行记录。
        return service.repository.list_runs(project_id, limit)  # 查询并返回运行列表。

    @app.get("/api/runs/{run_id}")  # 注册单个运行读取路由。
    def get_run(run_id: str) -> dict[str, Any]:  # 返回完整运行输入、结果或错误。
        try:  # 捕获运行缺失。
            return service.repository.get_run(run_id)  # 查询并返回运行记录。
        except KeyError as error:  # 处理不存在运行。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。

    @app.post("/api/projects/{project_id}/experiences/extract")  # 注册经验提取路由。
    def extract_experience(project_id: str, request: ExperienceRequest) -> dict[str, Any]:  # 比较两个修订并写入经验库。
        try:  # 捕获修订或运行缺失。
            return service.extract_and_save_experiences(project_id, request.revisionFrom, request.revisionTo, request.runId)  # 执行经验提取。
        except KeyError as error:  # 处理不存在资源。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。

    @app.get("/api/experiences")  # 注册经验检索路由。
    def list_experiences(projectId: str | None = None, q: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:  # 按项目和关键词检索经验。
        return service.repository.list_experiences(projectId, q, limit)  # 查询并返回经验记录。

    @app.get("/api/audit")  # 注册审计日志查询路由。
    def list_audit(projectId: str | None = None, action: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:  # 查询项目或动作审计事件。
        return service.repository.list_audit_events(projectId, action, limit)  # 返回不可变审计事件。

    @app.post("/api/templates")  # 注册模板保存路由。
    def save_template(request: TemplateRequest) -> dict[str, Any]:  # 保存提示词或策略模板新版本。
        result = service.repository.save_template(request.templateId, request.name, request.kind, request.body, request.makeDefault)  # 执行模板保存。
        service.repository.record_audit_event("template.save", "human.web", "template", "succeeded", result)  # 保存模板审计。
        return result  # 返回模板版本。

    @app.get("/api/templates")  # 注册模板列表路由。
    def list_templates(kind: str | None = None) -> list[dict[str, Any]]:  # 返回全部或指定类型模板。
        return service.repository.list_templates(kind)  # 查询并返回模板列表。

    @app.post("/api/import/point-cloud")  # 注册点云上传与导入路由。
    async def import_point_cloud(file: UploadFile = File(...), eps: float = 0.6, minSamples: int = 6, voxelSize: float = 0.2) -> dict[str, Any]:  # 上传点云并创建 BSDL 项目。
        suffix = Path(file.filename or "point_cloud.xyz").suffix or ".xyz"  # 获取上传文件扩展名。
        upload_path = service.runs_directory / f"upload_{uuid.uuid4().hex}{suffix}"  # 构造隔离且唯一的上传路径。
        with upload_path.open("wb") as target:  # 打开本地目标文件。
            shutil.copyfileobj(file.file, target)  # 流式复制上传内容。
        try:  # 捕获点云解析和项目创建错误。
            return service.import_point_cloud(upload_path, eps, minSamples, voxelSize)  # 执行点云导入闭环。
        except (ValueError, RuntimeError) as error:  # 处理点云导入失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/import/inp")
    async def import_calculix_inp(file: UploadFile = File(...)) -> dict[str, Any]:
        suffix = Path(file.filename or "model.inp").suffix.lower() or ".inp"
        if suffix != ".inp":
            raise HTTPException(status_code=400, detail="只接受 .inp 文件。")
        upload_path = service.runs_directory / f"upload_{uuid.uuid4().hex}{suffix}"
        with upload_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
        try:
            return service.import_calculix_inp(upload_path)
        except (ValueError, RuntimeError, FileNotFoundError) as error:
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error

    @app.post("/api/import/ifc")  # 注册 IFC 4.3 文件导入路由。
    async def import_ifc_file(file: UploadFile = File(...), projectId: str | None = None) -> dict[str, Any]:  # 上传 IFC 并执行 MVD 与身份映射。
        suffix = Path(file.filename or "bridge.ifc").suffix.lower() or ".ifc"  # 获取上传扩展名。
        if suffix not in {".ifc", ".ifczip", ".ifcxml"}:  # 检查允许的 IFC 文件类型。
            raise HTTPException(status_code=400, detail="只接受 .ifc、.ifczip 或 .ifcxml 文件。")  # 阻止无关上传。
        upload_path = service.runs_directory / f"upload_{uuid.uuid4().hex}{suffix}"  # 构造隔离且唯一的 IFC 路径。
        with upload_path.open("wb") as target:  # 打开本地目标文件。
            shutil.copyfileobj(file.file, target)  # 流式复制上传内容。
        try:  # 捕获依赖缺失、MVD 和转换错误。
            return service.import_ifc_file(upload_path, ROOT / "mvd" / "bridge_analysis_delivery_view.json", projectId)  # 执行 IFC 导入。
        except (ValueError, RuntimeError, FileNotFoundError) as error:  # 处理导入失败。
            raise HTTPException(status_code=400, detail=error.args[0] if error.args else str(error)) from error  # 返回 400 响应。

    @app.post("/api/projects/{project_id}/export")  # 注册通用外部格式导出路由。
    def export_project(project_id: str, request: ExportRequest) -> dict[str, Any]:  # 导出 BSDL、Gmsh 或 CalculiX 文件。
        try:  # 捕获项目缺失和 Adapter 错误。
            return service.export_project(project_id, request.adapter, request.revision, request.meshPolicyId, request.loadCaseId, request.solverPlanId, request.finiteElementModelId, request.strict, request.actor)  # 执行格式导出。
        except KeyError as error:  # 处理不存在项目或修订。
            raise HTTPException(status_code=404, detail=str(error)) from error  # 返回 404 响应。
        except ValueError as error:  # 处理未知 Adapter 或转换错误。
            raise HTTPException(status_code=400, detail=str(error)) from error  # 返回 400 响应。

    @app.get("/api/artifacts")  # 注册导出产物下载路由。
    def get_artifact(path: str) -> FileResponse:  # 安全返回 runs 目录中的导出文件。
        candidate = (service.runs_directory / path).resolve()  # 解析用户请求的文件路径。
        root = service.runs_directory.resolve()  # 解析隔离目录路径。
        if candidate != root and root not in candidate.parents:  # 检查路径逃逸。
            raise HTTPException(status_code=404, detail="产物不存在。")  # 阻止任意文件访问。
        if not candidate.is_file():  # 检查文件存在性。
            raise HTTPException(status_code=404, detail="产物不存在。")  # 返回文件缺失状态。
        return FileResponse(candidate, filename=candidate.name)  # 返回文件下载响应。

    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")  # 把自包含响应式 PWA 挂载到根路径。
    return app  # 返回配置完成的应用。


app = create_app()  # 提供 uvicorn 可直接发现的默认应用。

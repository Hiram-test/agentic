"""BridgeMind Studio 的 SQLite 项目、修订、运行、经验和模板仓库。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供数据库 JSON 序列化。
import sqlite3  # 提供无需外部服务的持久化数据库。
import uuid  # 提供运行和经验记录唯一 ID。
from pathlib import Path  # 提供数据库路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from .utils import content_hash, deep_copy, utc_now  # 复用哈希、深复制和时间戳。


class RevisionConflictError(RuntimeError):  # 表示客户端基于过期修订提交修改。
    def __init__(self, project_id: str, expected_revision: int, actual_revision: int) -> None:  # 保存冲突上下文。
        self.project_id = project_id  # 保存项目 ID。
        self.expected_revision = expected_revision  # 保存客户端基准修订。
        self.actual_revision = actual_revision  # 保存服务器当前修订。
        super().__init__(f"修订冲突：{project_id} 当前为 V{actual_revision}，提交基于 V{expected_revision}。")  # 构造可读错误消息。


class Repository:  # 封装所有 SQLite 数据访问操作。
    def __init__(self, database_path: str | Path) -> None:  # 初始化仓库并建立表结构。
        self.database_path = Path(database_path)  # 规范化数据库路径。
        self.database_path.parent.mkdir(parents=True, exist_ok=True)  # 确保数据库父目录存在。
        self.initialize()  # 创建所需数据表。

    def _connect(self) -> sqlite3.Connection:  # 创建配置完成的数据库连接。
        connection = sqlite3.connect(self.database_path, timeout=30.0)  # 打开 SQLite 数据库。
        connection.row_factory = sqlite3.Row  # 让查询结果支持按列名读取。
        connection.execute("PRAGMA foreign_keys = ON")  # 启用外键约束。
        connection.execute("PRAGMA journal_mode = WAL")  # 使用 WAL 提高并发读写稳定性。
        return connection  # 返回数据库连接。

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:  # 为旧数据库补充向后兼容字段。
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}  # 读取当前表字段集合。
        if column not in columns:  # 检查目标字段是否缺失。
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")  # 原位迁移旧数据库且保留已有数据。

    def initialize(self) -> None:  # 创建项目所需全部数据表和索引。
        with self._connect() as connection:  # 使用事务创建表结构。
            connection.executescript(  # 执行完整数据库建表脚本。
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    current_revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    project_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    parent_revision INTEGER,
                    author TEXT NOT NULL,
                    source TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, revision_number),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    solver TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (project_id, revision_number) REFERENCES revisions(project_id, revision_number) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS experiences (
                    experience_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    revision_from INTEGER NOT NULL,
                    revision_to INTEGER NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_ref TEXT,
                    feature_signature TEXT NOT NULL,
                    descriptor_json TEXT NOT NULL DEFAULT '{}',
                    action_json TEXT NOT NULL DEFAULT '{}',
                    applicability_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    quality_score REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    review_json TEXT NOT NULL DEFAULT '{}',
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS templates (
                    template_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (template_id, version)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    revision_number INTEGER,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id, revision_number DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiences_project ON experiences(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action, created_at DESC);
                """  # 定义项目、修订、运行、经验、模板和审计表。
            )  # 完成建表脚本执行。
            self._ensure_column(connection, "experiences", "descriptor_json", "TEXT NOT NULL DEFAULT '{}'")  # 为 1.0 数据库补充结构描述符。
            self._ensure_column(connection, "experiences", "action_json", "TEXT NOT NULL DEFAULT '{}'")  # 为 1.0 数据库补充可重放动作。
            self._ensure_column(connection, "experiences", "applicability_json", "TEXT NOT NULL DEFAULT '{}'")  # 为 1.0 数据库补充适用范围。
            self._ensure_column(connection, "experiences", "evidence_json", "TEXT NOT NULL DEFAULT '{}'")  # 为 1.0 数据库补充证据对象。
            self._ensure_column(connection, "experiences", "quality_score", "REAL NOT NULL DEFAULT 0.0")  # 为 1.0 数据库补充经验质量分。
            self._ensure_column(connection, "experiences", "status", "TEXT NOT NULL DEFAULT 'candidate'")  # 为 1.0 数据库补充经验生命周期状态。
            self._ensure_column(connection, "experiences", "review_json", "TEXT NOT NULL DEFAULT '{}'")  # 为 1.0 数据库补充人工审核记录。
            connection.execute("CREATE INDEX IF NOT EXISTS idx_experiences_status ON experiences(status, quality_score DESC, created_at DESC)")  # 建立经验读回筛选索引。
            connection.execute("CREATE INDEX IF NOT EXISTS idx_experiences_signature ON experiences(feature_signature, created_at DESC)")  # 建立结构特征签名索引。

    def create_project(self, document: dict[str, Any], author: str, source: str = "manual", summary: str = "创建项目") -> dict[str, Any]:  # 创建项目并保存首个修订。
        project = document.get("project", {})  # 读取 BSDL 项目元数据。
        project_id = str(project.get("id"))  # 读取项目稳定 ID。
        if not project_id or project_id == "None":  # 检查项目 ID 有效性。
            raise ValueError("BSDL 文档缺少 project.id。")  # 阻止无项目 ID 创建。
        now = utc_now()  # 生成统一创建时间。
        prepared = deep_copy(document)  # 深复制文档避免修改调用方数据。
        prepared.setdefault("revision", {})  # 确保修订对象存在。
        prepared["revision"].update({"number": 1, "parent": None, "createdAt": now, "createdBy": author, "status": prepared["revision"].get("status", "working"), "summary": summary})  # 规范化首个修订元数据。
        payload = json.dumps(prepared, ensure_ascii=False)  # 序列化完整文档快照。
        digest = content_hash(prepared)  # 计算修订内容哈希。
        with self._connect() as connection:  # 在单事务中创建项目和修订。
            existing = connection.execute("SELECT project_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()  # 检查项目是否已存在。
            if existing is not None:  # 处理重复项目 ID。
                raise ValueError(f"项目已存在：{project_id}")  # 阻止静默覆盖已有项目。
            connection.execute("INSERT INTO projects(project_id, name, description, current_revision, created_at, updated_at) VALUES(?,?,?,?,?,?)", (project_id, str(project.get("name", project_id)), str(project.get("description", "")), 1, now, now))  # 插入项目索引记录。
            connection.execute("INSERT INTO revisions(project_id, revision_number, parent_revision, author, source, summary, status, content_hash, document_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (project_id, 1, None, author, source, summary, prepared["revision"]["status"], digest, payload, now))  # 插入首个不可变修订。
        return {"projectId": project_id, "revision": 1, "contentHash": digest, "document": prepared}  # 返回创建结果。

    def ensure_project(self, document: dict[str, Any], author: str = "software.bridgemind", source: str = "seed", summary: str = "载入示例项目") -> dict[str, Any]:  # 确保示例项目存在但不覆盖用户修订。
        project_id = str(document.get("project", {}).get("id"))  # 读取示例项目 ID。
        with self._connect() as connection:  # 查询项目是否存在。
            existing = connection.execute("SELECT project_id, current_revision FROM projects WHERE project_id = ?", (project_id,)).fetchone()  # 获取已有项目记录。
        if existing is not None:  # 处理项目已经存在。
            return {"projectId": project_id, "revision": int(existing["current_revision"]), "created": False}  # 返回现有项目状态。
        created = self.create_project(document, author, source, summary)  # 创建不存在的示例项目。
        return {"projectId": project_id, "revision": created["revision"], "created": True}  # 返回新建状态。

    def list_projects(self) -> list[dict[str, Any]]:  # 列出所有项目及当前修订。
        with self._connect() as connection:  # 执行只读查询。
            rows = connection.execute("SELECT project_id, name, description, current_revision, created_at, updated_at FROM projects ORDER BY updated_at DESC").fetchall()  # 按更新时间倒序读取项目。
        return [{"projectId": row["project_id"], "name": row["name"], "description": row["description"], "currentRevision": int(row["current_revision"]), "createdAt": row["created_at"], "updatedAt": row["updated_at"]} for row in rows]  # 转换为 API 友好对象。

    def get_document(self, project_id: str, revision: int | None = None) -> dict[str, Any]:  # 读取指定项目的当前或历史修订文档。
        with self._connect() as connection:  # 执行修订查询。
            if revision is None:  # 处理读取当前修订。
                project = connection.execute("SELECT current_revision FROM projects WHERE project_id = ?", (project_id,)).fetchone()  # 查询当前修订号。
                if project is None:  # 检查项目存在。
                    raise KeyError(f"项目不存在：{project_id}")  # 对缺失项目给出明确错误。
                revision = int(project["current_revision"])  # 使用当前修订号。
            row = connection.execute("SELECT document_json FROM revisions WHERE project_id = ? AND revision_number = ?", (project_id, revision)).fetchone()  # 查询修订快照。
        if row is None:  # 检查修订存在。
            raise KeyError(f"修订不存在：{project_id} V{revision}")  # 对缺失修订给出明确错误。
        document = json.loads(row["document_json"])  # 解析文档快照。
        if not isinstance(document, dict):  # 检查数据库内容完整性。
            raise RuntimeError("数据库中的 BSDL 修订不是 object。")  # 报告存储损坏。
        return document  # 返回修订文档。

    def save_revision(self, project_id: str, document: dict[str, Any], author: str, source: str, summary: str, status: str = "working", expected_revision: int | None = None) -> dict[str, Any]:  # 保存新的不可变修订并执行乐观并发检查。
        now = utc_now()  # 生成统一保存时间。
        prepared = deep_copy(document)  # 深复制文档避免修改调用方对象。
        with self._connect() as connection:  # 在事务中读取当前修订并写入新版本。
            connection.execute("BEGIN IMMEDIATE")  # 获取写锁并保证检查与更新原子执行。
            project = connection.execute("SELECT current_revision FROM projects WHERE project_id = ?", (project_id,)).fetchone()  # 读取项目当前修订。
            if project is None:  # 检查项目存在。
                raise KeyError(f"项目不存在：{project_id}")  # 阻止向不存在项目写修订。
            parent_revision = int(project["current_revision"])  # 保存服务器当前修订号。
            if expected_revision is not None and int(expected_revision) != parent_revision:  # 检查客户端基准版本。
                raise RevisionConflictError(project_id, int(expected_revision), parent_revision)  # 阻止覆盖其他用户已经保存的修改。
            next_revision = parent_revision + 1  # 计算新修订号。
            prepared.setdefault("revision", {})  # 确保文档修订对象存在。
            prepared["revision"] = {"number": next_revision, "parent": parent_revision, "createdAt": now, "createdBy": author, "status": status, "summary": summary}  # 写入规范化修订元数据。
            payload = json.dumps(prepared, ensure_ascii=False)  # 序列化完整文档快照。
            digest = content_hash(prepared)  # 计算内容哈希。
            connection.execute("INSERT INTO revisions(project_id, revision_number, parent_revision, author, source, summary, status, content_hash, document_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (project_id, next_revision, parent_revision, author, source, summary, status, digest, payload, now))  # 插入不可变修订。
            connection.execute("UPDATE projects SET current_revision = ?, name = ?, description = ?, updated_at = ? WHERE project_id = ?", (next_revision, str(prepared.get("project", {}).get("name", project_id)), str(prepared.get("project", {}).get("description", "")), now, project_id))  # 更新项目当前修订索引。
        return {"projectId": project_id, "revision": next_revision, "parentRevision": parent_revision, "contentHash": digest, "document": prepared}  # 返回保存结果。

    def list_revisions(self, project_id: str) -> list[dict[str, Any]]:  # 列出项目全部修订元数据。
        with self._connect() as connection:  # 执行只读查询。
            rows = connection.execute("SELECT revision_number, parent_revision, author, source, summary, status, content_hash, created_at FROM revisions WHERE project_id = ? ORDER BY revision_number DESC", (project_id,)).fetchall()  # 按版本倒序读取修订。
        return [{"revision": int(row["revision_number"]), "parentRevision": int(row["parent_revision"]) if row["parent_revision"] is not None else None, "author": row["author"], "source": row["source"], "summary": row["summary"], "status": row["status"], "contentHash": row["content_hash"], "createdAt": row["created_at"]} for row in rows]  # 转换为 API 友好对象。

    def start_run(self, project_id: str, revision: int, solver: str, input_payload: dict[str, Any]) -> str:  # 创建处于 running 状态的试算记录。
        run_id = f"run.{uuid.uuid4().hex}"  # 生成运行唯一 ID。
        now = utc_now()  # 生成运行创建时间。
        with self._connect() as connection:  # 在事务中插入运行记录。
            connection.execute("INSERT INTO runs(run_id, project_id, revision_number, solver, status, input_json, result_json, error_json, created_at, completed_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, project_id, revision, solver, "running", json.dumps(input_payload, ensure_ascii=False), None, None, now, None))  # 保存运行输入和状态。
        return run_id  # 返回运行 ID。

    def finish_run(self, run_id: str, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None, status_override: str | None = None) -> dict[str, Any]:  # 完成试算并保存结果、错误或显式状态。
        status = status_override or ("succeeded" if error is None else "failed")  # 根据显式状态或错误状态确定最终运行状态。
        completed = utc_now()  # 生成完成时间。
        with self._connect() as connection:  # 在事务中更新运行记录。
            existing = connection.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()  # 检查运行记录存在。
            if existing is None:  # 处理缺失运行记录。
                raise KeyError(f"运行不存在：{run_id}")  # 阻止更新不存在运行。
            connection.execute("UPDATE runs SET status = ?, result_json = ?, error_json = ?, completed_at = ? WHERE run_id = ?", (status, json.dumps(result, ensure_ascii=False) if result is not None else None, json.dumps(error, ensure_ascii=False) if error is not None else None, completed, run_id))  # 保存最终结果或错误。
        return {"runId": run_id, "status": status, "completedAt": completed}  # 返回运行完成状态。

    def get_run(self, run_id: str) -> dict[str, Any]:  # 读取单个运行记录。
        with self._connect() as connection:  # 执行运行查询。
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()  # 查询指定运行。
        if row is None:  # 检查运行存在。
            raise KeyError(f"运行不存在：{run_id}")  # 对缺失运行给出明确错误。
        return {"runId": row["run_id"], "projectId": row["project_id"], "revision": int(row["revision_number"]), "solver": row["solver"], "status": row["status"], "input": json.loads(row["input_json"]), "result": json.loads(row["result_json"]) if row["result_json"] else None, "error": json.loads(row["error_json"]) if row["error_json"] else None, "createdAt": row["created_at"], "completedAt": row["completed_at"]}  # 转换为完整运行对象。

    def list_runs(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:  # 列出项目最近试算任务。
        with self._connect() as connection:  # 执行只读查询。
            rows = connection.execute("SELECT run_id, revision_number, solver, status, created_at, completed_at, result_json, error_json FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project_id, int(limit))).fetchall()  # 按创建时间倒序读取运行。
        output: list[dict[str, Any]] = []  # 初始化运行摘要列表。
        for row in rows:  # 遍历运行记录。
            result = json.loads(row["result_json"]) if row["result_json"] else None  # 解析可选结果。
            error = json.loads(row["error_json"]) if row["error_json"] else None  # 解析可选错误。
            output.append({"runId": row["run_id"], "revision": int(row["revision_number"]), "solver": row["solver"], "status": row["status"], "createdAt": row["created_at"], "completedAt": row["completed_at"], "globalMetrics": result.get("globalMetrics") if isinstance(result, dict) else None, "meshStats": result.get("mesh", {}).get("stats") if isinstance(result, dict) else None, "error": error})  # 保存运行摘要。
        return output  # 返回运行列表。

    def _experience_from_row(self, row: sqlite3.Row) -> dict[str, Any]:  # 把 SQLite 行转换为完整经验对象。
        return {"experienceId": row["experience_id"], "projectId": row["project_id"], "revisionFrom": int(row["revision_from"]), "revisionTo": int(row["revision_to"]), "scopeType": row["scope_type"], "scopeRef": row["scope_ref"], "featureSignature": row["feature_signature"], "descriptor": json.loads(row["descriptor_json"] or "{}"), "action": json.loads(row["action_json"] or "{}"), "applicability": json.loads(row["applicability_json"] or "{}"), "evidence": json.loads(row["evidence_json"] or "{}"), "qualityScore": float(row["quality_score"] or 0.0), "status": str(row["status"] or "candidate"), "review": json.loads(row["review_json"] or "{}"), "before": json.loads(row["before_json"]), "after": json.loads(row["after_json"]), "metrics": json.loads(row["metrics_json"]), "summary": row["summary"], "outcome": row["outcome"], "tags": json.loads(row["tags_json"]), "createdAt": row["created_at"]}  # 返回 API 和记忆引擎统一使用的经验对象。

    def save_experience(self, record: dict[str, Any]) -> dict[str, Any]:  # 幂等保存一条结构化经验记录。
        experience_id = str(record.get("experienceId") or f"experience.{uuid.uuid4().hex}")  # 读取或生成经验 ID。
        created_at = str(record.get("createdAt") or utc_now())  # 读取或生成创建时间。
        quality_score = max(0.0, min(1.0, float(record.get("qualityScore", 0.0) or 0.0)))  # 规范化经验质量分。
        with self._connect() as connection:  # 在事务中插入或升级经验记录。
            connection.execute("INSERT INTO experiences(experience_id, project_id, revision_from, revision_to, scope_type, scope_ref, feature_signature, descriptor_json, action_json, applicability_json, evidence_json, quality_score, status, review_json, before_json, after_json, metrics_json, summary, outcome, tags_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(experience_id) DO UPDATE SET feature_signature=excluded.feature_signature, descriptor_json=excluded.descriptor_json, action_json=excluded.action_json, applicability_json=excluded.applicability_json, evidence_json=excluded.evidence_json, quality_score=excluded.quality_score, status=CASE WHEN experiences.status IN ('accepted','rejected','archived') THEN experiences.status ELSE excluded.status END, before_json=excluded.before_json, after_json=excluded.after_json, metrics_json=excluded.metrics_json, summary=excluded.summary, outcome=excluded.outcome, tags_json=excluded.tags_json", (experience_id, record["projectId"], int(record["revisionFrom"]), int(record["revisionTo"]), str(record.get("scopeType", "project")), record.get("scopeRef"), str(record.get("featureSignature", "")), json.dumps(record.get("descriptor", {}), ensure_ascii=False), json.dumps(record.get("action", {}), ensure_ascii=False), json.dumps(record.get("applicability", {}), ensure_ascii=False), json.dumps(record.get("evidence", {}), ensure_ascii=False), quality_score, str(record.get("status", "candidate")), json.dumps(record.get("review", {}), ensure_ascii=False), json.dumps(record.get("before"), ensure_ascii=False), json.dumps(record.get("after"), ensure_ascii=False), json.dumps(record.get("metrics", {}), ensure_ascii=False), str(record.get("summary", "")), str(record.get("outcome", "unknown")), json.dumps(record.get("tags", []), ensure_ascii=False), created_at))  # 保存经验全部可读回字段并保护既有人工审核状态。
        return {"experienceId": experience_id, "createdAt": created_at, "qualityScore": quality_score, "status": str(record.get("status", "candidate"))}  # 返回经验保存结果。

    def get_experience(self, experience_id: str) -> dict[str, Any]:  # 读取单条完整经验记录。
        with self._connect() as connection:  # 执行经验查询。
            row = connection.execute("SELECT * FROM experiences WHERE experience_id = ?", (experience_id,)).fetchone()  # 查询指定经验。
        if row is None:  # 检查经验是否存在。
            raise KeyError(f"经验不存在：{experience_id}")  # 对缺失经验给出明确错误。
        return self._experience_from_row(row)  # 返回完整经验对象。

    def review_experience(self, experience_id: str, status: str, reviewer: str, comment: str = "") -> dict[str, Any]:  # 人工接受、拒绝或归档一条经验。
        allowed = {"candidate", "accepted", "rejected", "archived"}  # 定义允许的经验生命周期状态。
        if status not in allowed:  # 检查请求状态是否合法。
            raise ValueError(f"经验状态必须属于：{', '.join(sorted(allowed))}")  # 阻止非法状态写入数据库。
        review = {"reviewedAt": utc_now(), "reviewedBy": reviewer, "status": status, "comment": comment}  # 构造可审计审核对象。
        with self._connect() as connection:  # 在事务中更新经验审核状态。
            existing = connection.execute("SELECT experience_id FROM experiences WHERE experience_id = ?", (experience_id,)).fetchone()  # 检查经验存在。
            if existing is None:  # 处理缺失经验。
                raise KeyError(f"经验不存在：{experience_id}")  # 阻止更新不存在经验。
            connection.execute("UPDATE experiences SET status = ?, review_json = ? WHERE experience_id = ?", (status, json.dumps(review, ensure_ascii=False), experience_id))  # 保存状态和人工审核信息。
        return self.get_experience(experience_id)  # 返回更新后的完整经验对象。

    def list_experiences(self, project_id: str | None = None, query: str | None = None, limit: int = 100, status: str | None = None, exclude_project_id: str | None = None) -> list[dict[str, Any]]:  # 检索经验记录并支持读回过滤。
        clauses: list[str] = []  # 初始化 SQL 条件列表。
        parameters: list[Any] = []  # 初始化 SQL 参数列表。
        if project_id is not None:  # 检查是否限定项目。
            clauses.append("project_id = ?")  # 添加项目条件。
            parameters.append(project_id)  # 添加项目参数。
        if exclude_project_id is not None:  # 检查是否排除当前项目。
            clauses.append("project_id <> ?")  # 添加跨项目条件。
            parameters.append(exclude_project_id)  # 添加排除项目参数。
        if status is not None:  # 检查是否限定经验状态。
            clauses.append("status = ?")  # 添加状态条件。
            parameters.append(status)  # 添加状态参数。
        if query:  # 检查是否提供关键词。
            clauses.append("(summary LIKE ? OR feature_signature LIKE ? OR tags_json LIKE ? OR descriptor_json LIKE ?)")  # 添加摘要、特征、标签和描述符模糊检索。
            token = f"%{query}%"  # 构造 LIKE 模式。
            parameters.extend([token, token, token, token])  # 添加四个检索参数。
        where = " WHERE " + " AND ".join(clauses) if clauses else ""  # 构造可选 WHERE 子句。
        parameters.append(int(limit))  # 添加查询数量限制。
        with self._connect() as connection:  # 执行只读查询。
            rows = connection.execute(f"SELECT * FROM experiences{where} ORDER BY quality_score DESC, created_at DESC LIMIT ?", parameters).fetchall()  # 按质量和时间读取匹配经验。
        return [self._experience_from_row(row) for row in rows]  # 转换为完整经验对象列表。

    def save_template(self, template_id: str, name: str, kind: str, body: dict[str, Any], make_default: bool = False) -> dict[str, Any]:  # 保存一个新版本的策略或提示模板。
        now = utc_now()  # 生成模板创建时间。
        with self._connect() as connection:  # 在事务中读取版本并插入模板。
            row = connection.execute("SELECT COALESCE(MAX(version), 0) AS max_version FROM templates WHERE template_id = ?", (template_id,)).fetchone()  # 查询当前最大版本号。
            version = int(row["max_version"]) + 1  # 计算新模板版本号。
            if make_default:  # 检查是否设为默认模板。
                connection.execute("UPDATE templates SET is_default = 0 WHERE kind = ?", (kind,))  # 取消同类模板默认状态。
            connection.execute("INSERT INTO templates(template_id, version, name, kind, body_json, is_default, created_at) VALUES(?,?,?,?,?,?,?)", (template_id, version, name, kind, json.dumps(body, ensure_ascii=False), 1 if make_default else 0, now))  # 插入模板新版本。
        return {"templateId": template_id, "version": version, "isDefault": make_default, "createdAt": now}  # 返回模板保存结果。

    def list_templates(self, kind: str | None = None) -> list[dict[str, Any]]:  # 列出模板版本。
        with self._connect() as connection:  # 执行模板查询。
            if kind is None:  # 处理不限定模板类型。
                rows = connection.execute("SELECT * FROM templates ORDER BY kind, template_id, version DESC").fetchall()  # 读取所有模板。
            else:  # 处理限定模板类型。
                rows = connection.execute("SELECT * FROM templates WHERE kind = ? ORDER BY template_id, version DESC", (kind,)).fetchall()  # 读取指定类型模板。
        return [{"templateId": row["template_id"], "version": int(row["version"]), "name": row["name"], "kind": row["kind"], "body": json.loads(row["body_json"]), "isDefault": bool(row["is_default"]), "createdAt": row["created_at"]} for row in rows]  # 转换为模板对象列表。

    def get_template(self, template_id: str, version: int | None = None) -> dict[str, Any]:  # 读取指定稳定 ID 的最新或历史模板。
        with self._connect() as connection:  # 执行模板查询。
            if version is None:  # 处理读取最新模板版本。
                row = connection.execute("SELECT * FROM templates WHERE template_id = ? ORDER BY version DESC LIMIT 1", (template_id,)).fetchone()  # 查询最新版本。
            else:  # 处理读取指定模板版本。
                row = connection.execute("SELECT * FROM templates WHERE template_id = ? AND version = ?", (template_id, int(version))).fetchone()  # 查询历史版本。
        if row is None:  # 检查模板是否存在。
            raise KeyError(f"模板不存在：{template_id}{f' V{version}' if version is not None else ''}")  # 对缺失模板给出明确错误。
        return {"templateId": row["template_id"], "version": int(row["version"]), "name": row["name"], "kind": row["kind"], "body": json.loads(row["body_json"]), "isDefault": bool(row["is_default"]), "createdAt": row["created_at"]}  # 返回完整模板对象。

    def get_default_template(self, kind: str) -> dict[str, Any] | None:  # 读取指定类别的默认或最新模板。
        with self._connect() as connection:  # 执行默认模板查询。
            row = connection.execute("SELECT * FROM templates WHERE kind = ? ORDER BY is_default DESC, version DESC LIMIT 1", (kind,)).fetchone()  # 优先读取默认版本并回退到最新版本。
        if row is None:  # 处理模板类别尚不存在。
            return None  # 返回空值供服务层使用内置默认策略。
        return {"templateId": row["template_id"], "version": int(row["version"]), "name": row["name"], "kind": row["kind"], "body": json.loads(row["body_json"]), "isDefault": bool(row["is_default"]), "createdAt": row["created_at"]}  # 返回完整模板对象。

    def record_audit_event(self, action: str, actor: str, source: str, status: str, details: dict[str, Any] | None = None, project_id: str | None = None, revision: int | None = None) -> dict[str, Any]:  # 写入不可变审计事件。
        event_id = f"audit.{uuid.uuid4().hex}"  # 生成审计事件唯一 ID。
        created_at = utc_now()  # 生成事件时间。
        payload = json.dumps(details or {}, ensure_ascii=False)  # 序列化审计详情。
        with self._connect() as connection:  # 在独立事务中保存审计事件。
            connection.execute("INSERT INTO audit_events(event_id, project_id, revision_number, actor, action, source, status, details_json, created_at) VALUES(?,?,?,?,?,?,?,?,?)", (event_id, project_id, revision, actor, action, source, status, payload, created_at))  # 插入审计事件。
        return {"eventId": event_id, "projectId": project_id, "revision": revision, "actor": actor, "action": action, "source": source, "status": status, "details": details or {}, "createdAt": created_at}  # 返回审计事件对象。

    def list_audit_events(self, project_id: str | None = None, action: str | None = None, limit: int = 200) -> list[dict[str, Any]]:  # 查询最近审计事件。
        clauses: list[str] = []  # 初始化查询条件。
        parameters: list[Any] = []  # 初始化查询参数。
        if project_id is not None:  # 检查是否限定项目。
            clauses.append("project_id = ?")  # 添加项目条件。
            parameters.append(project_id)  # 添加项目参数。
        if action is not None:  # 检查是否限定动作。
            clauses.append("action = ?")  # 添加动作条件。
            parameters.append(action)  # 添加动作参数。
        where = " WHERE " + " AND ".join(clauses) if clauses else ""  # 构造可选 WHERE 子句。
        parameters.append(int(limit))  # 添加数量限制。
        with self._connect() as connection:  # 执行只读查询。
            rows = connection.execute(f"SELECT * FROM audit_events{where} ORDER BY created_at DESC LIMIT ?", parameters).fetchall()  # 读取审计事件。
        return [{"eventId": row["event_id"], "projectId": row["project_id"], "revision": int(row["revision_number"]) if row["revision_number"] is not None else None, "actor": row["actor"], "action": row["action"], "source": row["source"], "status": row["status"], "details": json.loads(row["details_json"]), "createdAt": row["created_at"]} for row in rows]  # 转换为 API 友好对象。

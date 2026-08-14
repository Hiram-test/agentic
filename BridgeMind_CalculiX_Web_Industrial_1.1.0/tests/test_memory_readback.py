"""验证 BSDL 经验能够跨项目读回并受任务兼容性和人工审核约束。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供旧数据库迁移测试的 JSON 序列化。
import sqlite3  # 提供 1.0 数据库结构构造。
from pathlib import Path  # 提供临时数据库和示例路径处理。
from bridge_mind.memory import build_region_descriptor, score_experience  # 导入描述符和适用性评分器。
from bridge_mind.repository import Repository  # 导入数据库仓库以验证迁移。
from bridge_mind.service import BridgeMindService  # 导入完整业务闭环。
from bridge_mind.utils import deep_copy, load_json  # 导入深复制和示例读取工具。


ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


def _rename_structure_ids(document: dict, suffix: str) -> dict:  # 复制项目并替换结构对象 ID 以验证不依赖本地引用。
    copied = deep_copy(document)  # 深复制输入文档。
    ids: set[str] = set()  # 初始化可替换对象 ID 集合。

    def collect(value: object) -> None:  # 递归收集所有对象的 id 字段。
        if isinstance(value, dict):  # 处理对象节点。
            if isinstance(value.get("id"), str) and not str(value["id"]).startswith(("human.", "software.")):  # 排除跨项目共享的人员和软件主体。
                ids.add(str(value["id"]))  # 保存需要替换的稳定 ID。
            for child in value.values():  # 遍历对象字段。
                collect(child)  # 递归收集子对象。
        elif isinstance(value, list):  # 处理数组节点。
            for child in value:  # 遍历数组元素。
                collect(child)  # 递归收集子元素。

    collect(copied)  # 收集文档内全部结构 ID。
    mapping = {value: f"{value}.{suffix}" for value in ids}  # 构造一一对应的新项目 ID 映射。

    def replace(value: object) -> object:  # 递归替换对象 ID 和引用。
        if isinstance(value, dict):  # 处理对象节点。
            return {key: replace(child) for key, child in value.items()}  # 递归替换所有字段。
        if isinstance(value, list):  # 处理数组节点。
            return [replace(child) for child in value]  # 递归替换所有元素。
        if isinstance(value, str):  # 处理字符串值。
            return mapping.get(value, value)  # 仅替换精确匹配的对象 ID。
        return value  # 保留数值、布尔和空值。

    renamed = replace(copied)  # 执行完整引用一致替换。
    assert isinstance(renamed, dict)  # 确认递归结果仍为文档对象。
    renamed["documentId"] = f"document.memory.{suffix}"  # 设置新的文档 ID。
    renamed["project"]["id"] = f"project.memory.{suffix}"  # 设置新的项目 ID。
    renamed["project"]["name"] = f"经验读回测试项目 {suffix}"  # 设置新的项目名称。
    for node in renamed.get("nodes", []):  # 遍历节点以改变绝对坐标。
        node["position"][0] = float(node["position"][0]) + 100.0  # 沿桥轴平移且保持局部物理结构不变。
    return renamed  # 返回 ID 和坐标均不同的同构项目。


def _train_one_support_experience(service: BridgeMindService) -> dict:  # 让专家修改一个支座区域并沉淀可读回经验。
    source = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取双主梁桥基础项目。
    training = _rename_structure_ids(source, "train")  # 构造独立训练项目。
    service.create_project(training)  # 保存训练项目 V1。
    strategy = service.propose_project_strategy(training["project"]["id"], use_memory=False)  # 生成不含历史经验的 V2 规则策略。
    revised = deep_copy(strategy["document"])  # 复制 V2 供专家修订。
    support = next(region for region in revised["regions"] if region.get("semanticType") == "support" and region.get("source") == "agent")  # 选择一个规则专家支座区域。
    support["targetSize"] = float(support["targetSize"]) * 0.5  # 模拟专家把支座网格目标尺寸减半。
    support["meshLevel"] = min(10, int(support["meshLevel"]) + 2)  # 模拟专家提高支座加密等级。
    support["source"] = "human"  # 标记最终动作来自人工。
    support["status"] = "accepted"  # 标记专家已经批准该局部策略。
    support["reason"].append("专家基于支座约束和局部响应批准进一步加密。")  # 保存人工修改理由。
    saved = service.save_revision(training["project"]["id"], revised, "human.demo", "human", "支座区域专家修订", "approved", 2)  # 保存 V3 人工修订。
    extracted = service.extract_and_save_experiences(training["project"]["id"], 2, int(saved["revision"]["revision"]))  # 把 V2 到 V3 差异提取为经验。
    record = next(item for item in extracted["records"] if item.get("scopeType") == "region")  # 选择局部区域经验。
    assert record["status"] == "accepted"  # 确认已批准人工修订进入 accepted 状态。
    assert float(record["qualityScore"]) >= 0.7  # 确认经验质量达到默认读回门槛。
    return record  # 返回训练经验供其他测试复用。


def test_new_user_inherits_expert_experience_without_weight_training(tmp_path: Path) -> None:  # 验证不同项目和不同对象 ID 仍能继承专家策略。
    service = BridgeMindService(ROOT, tmp_path / "memory.sqlite3", tmp_path / "runs")  # 创建隔离业务服务。
    service.seed_templates()  # 装入默认经验读回策略。
    record = _train_one_support_experience(service)  # 沉淀一个已批准支座经验。
    source = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 重新读取未见测试项目。
    testing = _rename_structure_ids(source, "test")  # 构造 ID 和绝对坐标都不同的同构项目。
    service.create_project(testing)  # 保存新用户项目 V1。
    baseline = service.propose_project_strategy(testing["project"]["id"], commit=False, use_memory=False)  # 生成不读历史经验的控制方案。
    inherited = service.propose_project_strategy(testing["project"]["id"], commit=False, use_memory=True)  # 使用相同基础模型和规则但开启经验读回。
    assert inherited["strategy"]["memoryMatchedRegionCount"] >= 1  # 确认新项目至少匹配一个历史经验。
    assert inherited["strategy"]["memoryAppliedRegionCount"] >= 1  # 确认经验真实改变至少一个未来区域行为。
    assert record["experienceId"] in inherited["document"]["experienceRefs"]  # 确认产品文档记录实际使用的经验 ID。
    baseline_supports = sorted((round(float(region["targetSize"]), 9), int(region["meshLevel"])) for region in baseline["document"]["regions"] if region.get("semanticType") == "support")  # 收集控制组支座动作。
    inherited_supports = sorted((round(float(region["targetSize"]), 9), int(region["meshLevel"])) for region in inherited["document"]["regions"] if region.get("semanticType") == "support")  # 收集经验组支座动作。
    assert inherited_supports != baseline_supports  # 确认相同规则策略在加入外部记忆后产生不同动作。
    memory_regions = [region for region in inherited["document"]["regions"] if isinstance(region.get("attributes", {}).get("memoryReadback"), dict)]  # 找到带读回证据的区域。
    assert memory_regions  # 确认至少一个区域保存完整经验来源。
    assert all(region["status"] == "needs_review" for region in memory_regions)  # 确认经验不会跳过人工与 FEA 审核直接批准。
    assert any(edge.get("source") == "experience" for edge in inherited["document"]["cognitiveMap"]["decisionEdges"])  # 确认认知地图显式标记经验来源。


def test_incompatible_analysis_type_is_hard_rejected(tmp_path: Path) -> None:  # 验证不同物理任务不会仅因几何相似而错误迁移。
    service = BridgeMindService(ROOT, tmp_path / "guard.sqlite3", tmp_path / "runs")  # 创建隔离业务服务。
    record = _train_one_support_experience(service)  # 生成线性静力支座经验。
    source = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取测试结构。
    proposed = service.propose_project_strategy(record["projectId"], revision=1, commit=False, use_memory=False)  # 生成当前区域供描述符构造。
    region = next(item for item in proposed["document"]["regions"] if item.get("semanticType") == "support")  # 选择支座区域。
    modal_document = deep_copy(proposed["document"])  # 复制结构但改变分析任务。
    modal_document["analysisTasks"][0]["type"] = "modal"  # 把当前任务改为模态分析。
    descriptor = build_region_descriptor(modal_document, region)  # 构造模态任务描述符。
    score, reasons = score_experience(descriptor, record, {"requireAnalysisTypeMatch": True})  # 计算对线性静力经验的适用性。
    assert score == 0.0  # 确认分析类型不兼容时相似度被硬置零。
    assert "analysis_type_mismatch" in reasons  # 确认拒绝原因可审计。


def test_repository_migrates_legacy_experience_table(tmp_path: Path) -> None:  # 验证 1.0 数据库可原位升级且不丢历史记录。
    database = tmp_path / "legacy.sqlite3"  # 构造旧数据库路径。
    with sqlite3.connect(database) as connection:  # 创建最小 1.0 数据库结构。
        connection.executescript("CREATE TABLE projects(project_id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,current_revision INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL); CREATE TABLE experiences(experience_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,revision_from INTEGER NOT NULL,revision_to INTEGER NOT NULL,scope_type TEXT NOT NULL,scope_ref TEXT,feature_signature TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,metrics_json TEXT NOT NULL,summary TEXT NOT NULL,outcome TEXT NOT NULL,tags_json TEXT NOT NULL,created_at TEXT NOT NULL);")  # 建立不含读回字段的旧表。
        connection.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)", ("project.legacy", "legacy", "", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))  # 插入旧项目索引。
        connection.execute("INSERT INTO experiences VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("experience.legacy", "project.legacy", 1, 2, "region", "region.legacy", "abc", json.dumps(None), json.dumps({"semanticType": "support", "elementFamily": "frame", "targetSize": 1.0}), json.dumps({}), "legacy", "modified", json.dumps(["support"]), "2026-01-01T00:00:00Z"))  # 插入旧经验记录。
    repository = Repository(database)  # 初始化新版仓库并触发原位迁移。
    record = repository.get_experience("experience.legacy")  # 读取迁移后的历史经验。
    assert record["experienceId"] == "experience.legacy"  # 确认旧记录未丢失。
    assert record["descriptor"] == {}  # 确认新增字段使用安全默认值。
    assert record["status"] == "candidate"  # 确认旧经验默认进入候选而非自动批准。


def test_memory_preview_and_review_api(tmp_path: Path) -> None:  # 验证 Web API 能预览、拒绝并重新接受经验。
    from fastapi.testclient import TestClient  # 在局部导入同步 API 测试客户端。
    from bridge_mind.api import create_app  # 在局部导入应用工厂避免全局数据库副作用。
    app = create_app(tmp_path / "memory_api.sqlite3")  # 创建隔离 FastAPI 应用。
    service = app.state.service  # 读取应用使用的业务服务。
    record = _train_one_support_experience(service)  # 沉淀一条已接受支座经验。
    source = load_json(ROOT / "examples" / "two_girder_bridge.bsdl.json")  # 读取未见测试结构。
    testing = _rename_structure_ids(source, "api")  # 构造新项目。
    service.create_project(testing)  # 保存新项目供 API 访问。
    client = TestClient(app)  # 创建同步测试客户端。
    preview = client.post(f"/api/projects/{testing['project']['id']}/memory/preview", json={})  # 请求无副作用经验读回预览。
    assert preview.status_code == 200  # 确认预览端点可用。
    assert preview.json()["memory"]["applicableRegionCount"] >= 1  # 确认预览发现可应用补丁。
    rejected = client.post(f"/api/experiences/{record['experienceId']}/review", json={"status": "rejected", "reviewer": "human.demo", "comment": "回归测试暂时拒绝"})  # 拒绝经验进入未来策略。
    assert rejected.status_code == 200  # 确认拒绝操作成功。
    blocked_preview = client.post(f"/api/projects/{testing['project']['id']}/memory/preview", json={})  # 再次请求经验读回预览。
    assert blocked_preview.json()["memory"]["applicableRegionCount"] == 0  # 确认被拒绝经验不再影响新项目。
    accepted = client.post(f"/api/experiences/{record['experienceId']}/review", json={"status": "accepted", "reviewer": "human.demo", "comment": "回归测试恢复接受"})  # 重新接受该经验。
    assert accepted.status_code == 200  # 确认接受操作成功。
    restored_preview = client.post(f"/api/projects/{testing['project']['id']}/memory/preview", json={})  # 再次请求读回预览。
    assert restored_preview.json()["memory"]["applicableRegionCount"] >= 1  # 确认接受后经验重新进入决策路径。

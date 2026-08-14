"""验证工业网站 API、CalculiX 结果回写和规范验算闭环。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
from pathlib import Path  # 提供临时路径类型。
from fastapi.testclient import TestClient  # 提供同步 API 测试客户端。
from bridge_mind.api import create_app  # 导入应用工厂。
from tests.test_calculix_execution import build_fake_ccx  # 复用可控求解器替身。

PROJECT_ID = "project.calculix_industrial_bridge_segment"  # 定义工业示例项目 ID。


def test_pwa_and_capability_endpoints(tmp_path: Path) -> None:  # 检查移动网站和真实能力矩阵。
    client = TestClient(create_app(tmp_path / "pwa.sqlite3"))  # 使用临时数据库创建应用。
    assert client.get("/manifest.webmanifest").status_code == 200  # 确认 PWA 清单可访问。
    assert client.get("/service-worker.js").status_code == 200  # 确认离线缓存脚本可访问。
    capabilities = client.get("/api/capabilities").json()  # 读取能力矩阵。
    assert capabilities["web"]["touch"]["pinchZoom"] is True  # 确认双指缩放能力被声明。
    assert capabilities["exports"]["commercialSolverDecks"] is False  # 确认未把商业求解器接口冒充已实现能力。
    assert capabilities["execution"]["nativeCalculiXBundled"] is False  # 确认包内没有伪称捆绑求解器。


def test_calculix_api_commits_artifacts_and_result_set(tmp_path: Path) -> None:  # 检查 API 从 deck 到新修订的完整结果链。
    client = TestClient(create_app(tmp_path / "run.sqlite3"))  # 使用临时数据库创建应用。
    executable = build_fake_ccx(tmp_path)  # 创建可控外部求解程序。
    response = client.post(f"/api/projects/{PROJECT_ID}/calculix/run", json={"executable": str(executable), "timeout": 30, "threads": 2, "commitResult": True})  # 发起完整工业运行。
    assert response.status_code == 200  # 确认运行接口成功。
    payload = response.json()  # 解析运行响应。
    assert payload["status"] == "succeeded"  # 确认作业成功。
    assert payload["resultCommit"]["revision"] == 2  # 确认结果被写为新修订。
    document = client.get(f"/api/projects/{PROJECT_ID}?revision=2").json()  # 读取结果修订。
    assert document["resultSets"]  # 确认结果集进入统一语言。
    assert document["artifacts"]  # 确认输入、输出和日志产物进入统一语言。
    assert all(len(item["hash"]) == 64 for item in document["artifacts"] if item["hash"])  # 确认产物使用真实内容哈希。


def test_code_check_api_is_auditable_and_committed(tmp_path: Path) -> None:  # 检查项目规则包验算和修订审计。
    client = TestClient(create_app(tmp_path / "check.sqlite3"))  # 使用临时数据库创建应用。
    context = {"maxDisplacement": 0.012, "maxStress": 210000000.0, "reactionBalanceResidual": 0.000001}  # 提供可复核的结果摘要。
    response = client.post(f"/api/projects/{PROJECT_ID}/code-checks/check.generic.service", json={"resultContext": context, "commit": True, "actor": "human.test"})  # 执行通用规则包。
    assert response.status_code == 200  # 确认验算接口成功。
    payload = response.json()  # 解析验算响应。
    assert payload["report"]["summary"]["fail"] == 0  # 确认示例输入没有失败规则。
    assert payload["report"]["rulePack"]["version"] == "1.0.0"  # 确认规则包版本被审计。
    assert payload["resultRevision"] == 2  # 确认验算结果进入新修订。
    document = client.get(f"/api/projects/{PROJECT_ID}?revision=2").json()  # 读取验算修订。
    assert len(document["codeCheckResults"]) == 3  # 确认三条规则结果被保存。
    assert document["codeCheckPlans"][0]["status"] == "executed"  # 确认计划状态更新。


def test_api_key_middleware_protects_project_data(tmp_path: Path, monkeypatch) -> None:  # 检查生产密钥同时保护 API 并保留公开探活端点。
    monkeypatch.setenv("BRIDGEMIND_API_KEYS", "test-secret-key")  # 为隔离测试启用一把生产 API 密钥。
    client = TestClient(create_app(tmp_path / "secured.sqlite3"))  # 使用启用访问控制的临时应用。
    assert client.get("/api/health").status_code == 200  # 确认健康检查保持公开可用。
    assert client.get("/api/capabilities").status_code == 200  # 确认能力矩阵保持公开可用。
    assert client.get("/api/projects").status_code == 401  # 确认项目数据在无密钥时被拒绝。
    response = client.get("/api/projects", headers={"X-API-Key": "test-secret-key"})  # 使用有效密钥读取受保护项目数据。
    assert response.status_code == 200  # 确认有效密钥可以访问受保护端点。
    assert response.json()  # 确认授权响应包含已装入的示例项目。

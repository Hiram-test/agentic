"""验证 BridgeMind FastAPI 和静态三维界面的关键路由。"""  # 说明测试文件用途。
from pathlib import Path  # 提供临时数据库路径类型。
from fastapi.testclient import TestClient  # 提供同步 API 测试客户端。
from bridge_mind.api import create_app  # 导入可测试应用工厂。


def test_api_closed_loop(tmp_path: Path) -> None:  # 检查健康、项目、策略、试算和经验 API。
    client = TestClient(create_app(tmp_path / "api.sqlite3"))  # 使用临时数据库创建测试客户端。
    assert client.get("/api/health").status_code == 200  # 确认服务健康检查可用。
    assert client.get("/").status_code == 200  # 确认三维 Web 页面可访问。
    projects = client.get("/api/projects").json()  # 读取自动装入的示例项目。
    assert len(projects) >= 2  # 确认两个示例均已载入。
    project_id = "project.two_girder_bridge"  # 指定完整闭环示例项目。
    strategy_response = client.post(f"/api/projects/{project_id}/strategy", json={})  # 调用策略生成接口。
    assert strategy_response.status_code == 200  # 确认策略接口成功。
    solve_response = client.post(f"/api/projects/{project_id}/solve", json={})  # 调用快速 FEA 接口。
    assert solve_response.status_code == 200  # 确认求解接口成功。
    solve_payload = solve_response.json()  # 解析求解响应。
    experience_response = client.post(f"/api/projects/{project_id}/experiences/extract", json={"revisionFrom": 1, "revisionTo": 3, "runId": solve_payload["runId"]})  # 调用经验提取接口。
    assert experience_response.status_code == 200  # 确认经验接口成功。
    assert experience_response.json()["recordCount"] > 0  # 确认 API 返回经验记录。

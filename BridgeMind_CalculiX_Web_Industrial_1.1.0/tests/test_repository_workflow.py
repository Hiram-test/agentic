"""验证项目、修订、试算、经验和导出完整闭环。"""  # 说明测试文件用途。
from pathlib import Path  # 提供导出文件路径检查。
from bridge_mind.service import BridgeMindService  # 导入高层业务服务。


def test_complete_revision_and_experience_workflow(tmp_path: Path) -> None:  # 检查 V1 到策略、FEA 和经验沉淀的全过程。
    root = Path(__file__).resolve().parents[1]  # 获取项目根目录。
    service = BridgeMindService(root, tmp_path / "workflow.sqlite3")  # 使用临时数据库创建业务服务。
    service.runs_directory = tmp_path / "runs"  # 把测试导出产物隔离到临时目录。
    service.runs_directory.mkdir(parents=True, exist_ok=True)  # 创建临时运行目录。
    service.seed_examples()  # 装入两个正式示例项目。
    project_id = "project.two_girder_bridge"  # 指定双主梁桥项目。
    strategy = service.propose_project_strategy(project_id)  # 生成并保存 V2 区域策略。
    assert strategy["savedRevision"]["revision"] == 2  # 确认策略修订号为 V2。
    assert strategy["document"]["revision"]["number"] == 2  # 确认返回文档元数据同步到 V2。
    solved = service.solve_project(project_id)  # 执行试算并保存 V3 FEA 反馈。
    assert solved["result"]["status"] == "succeeded"  # 确认快速试算成功。
    assert solved["feedbackRevision"]["revision"] == 3  # 确认 FEA 反馈形成 V3。
    assert solved["feedbackDocument"]["revision"]["number"] == 3  # 确认返回文档元数据同步到 V3。
    experiences = service.extract_and_save_experiences(project_id, 1, 3, solved["runId"])  # 比较 V1 和 V3 并提取经验。
    assert experiences["recordCount"] > 0  # 确认修订差异被转成经验记录。
    assert len(service.repository.list_experiences(project_id)) == experiences["recordCount"]  # 确认经验已经写入 SQLite。
    for adapter in ["bsdl", "gmsh", "calculix"]:  # 遍历三个确定性导出器。
        exported = service.export_project(project_id, adapter)  # 执行格式导出。
        assert Path(exported["output"]).is_file()  # 确认导出文件真实存在。
        assert exported["report"]["blocked"] is False  # 确认示例没有阻断性转换问题。

"""验证单节点生产部署文件、持久化路径和 CalculiX 挂载契约。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
import os  # 提供临时环境变量设置。
from pathlib import Path  # 提供交付文件路径处理。
from bridge_mind.api import create_app  # 导入应用工厂。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


def test_container_deployment_contract_is_complete() -> None:  # 检查容器部署所需文件和关键配置。
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")  # 读取应用镜像定义。
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")  # 读取服务编排文件。
    nginx = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")  # 读取反向代理配置。
    assert "USER bridgemind" in dockerfile  # 确认应用使用非特权用户。
    assert "HEALTHCHECK" in dockerfile  # 确认容器包含健康检查。
    assert "./solver:/opt/calculix:ro" in compose  # 确认 CalculiX 采用只读外部挂载。
    assert "bridgemind-data" in compose and "bridgemind-runs" in compose  # 确认数据库和作业产物持久化。
    assert "client_max_body_size 512m" in nginx  # 确认 BIM 和点云上传容量已配置。
    assert "proxy_read_timeout 86400s" in nginx  # 确认长时间有限元任务不会被短代理超时中断。


def test_environment_paths_are_honored(tmp_path: Path, monkeypatch: object) -> None:  # 检查生产数据库和运行目录可由环境变量隔离。
    database = tmp_path / "persistent" / "bridge.sqlite3"  # 构造临时数据库路径。
    runs = tmp_path / "persistent" / "runs"  # 构造临时作业目录。
    monkeypatch.setenv("BRIDGEMIND_DATABASE_PATH", str(database))  # 配置数据库环境变量。
    monkeypatch.setenv("BRIDGEMIND_RUNS_PATH", str(runs))  # 配置作业目录环境变量。
    application = create_app()  # 使用环境变量创建应用实例。
    service = application.state.service  # 读取应用绑定的业务服务。
    assert service.repository.database_path == database  # 确认数据库路径生效。
    assert service.runs_directory == runs.resolve()  # 确认作业目录路径生效。
    assert database.is_file()  # 确认数据库已经初始化。
    assert runs.is_dir()  # 确认作业目录已经创建。

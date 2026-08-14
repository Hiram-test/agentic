"""一键启动 BridgeMind Studio 本地 Web Demo。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
import argparse  # 提供端口和主机参数解析。
import uvicorn  # 提供 ASGI 本地服务运行器。


def main() -> None:  # 解析参数并启动 Web 服务。
    parser = argparse.ArgumentParser(description="启动 BridgeMind Studio。")  # 创建命令行解析器。
    parser.add_argument("--host", default="127.0.0.1")  # 设置默认本机监听地址。
    parser.add_argument("--port", type=int, default=8000)  # 设置默认监听端口。
    parser.add_argument("--reload", action="store_true")  # 提供开发模式自动重载开关。
    arguments = parser.parse_args()  # 解析命令行参数。
    uvicorn.run("bridge_mind.api:app", host=arguments.host, port=arguments.port, reload=arguments.reload)  # 启动 FastAPI 应用。


if __name__ == "__main__":  # 检查脚本是否直接执行。
    main()  # 运行启动流程。

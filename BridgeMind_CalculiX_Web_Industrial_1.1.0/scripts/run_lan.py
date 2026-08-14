"""在局域网启动 BridgeMind 并打印电脑与手机访问地址。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
import argparse  # 提供端口参数解析。
import socket  # 提供局域网地址探测。
import uvicorn  # 提供 ASGI 服务运行器。


def _local_ip() -> str:  # 探测当前电脑在局域网中的 IPv4 地址。
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # 创建无需建立会话的 UDP 套接字。
    try:  # 确保套接字最终关闭。
        connection.connect(("8.8.8.8", 80))  # 仅利用路由表选择本机出口地址而不发送业务数据。
        return str(connection.getsockname()[0])  # 返回局域网出口地址。
    except OSError:  # 处理离线或无默认路由环境。
        return "127.0.0.1"  # 回退为本机地址。
    finally:  # 无论探测是否成功都执行清理。
        connection.close()  # 关闭临时套接字。


def main() -> None:  # 解析参数并启动可供手机访问的网站。
    parser = argparse.ArgumentParser(description="启动 BridgeMind 局域网触控网站。")  # 创建命令行解析器。
    parser.add_argument("--port", type=int, default=8000)  # 设置默认服务端口。
    arguments = parser.parse_args()  # 解析用户参数。
    address = _local_ip()  # 获取手机可访问的电脑地址。
    print(f"电脑访问：http://127.0.0.1:{arguments.port}")  # 输出本机访问地址。
    print(f"同一 Wi-Fi 手机访问：http://{address}:{arguments.port}")  # 输出局域网手机地址。
    print("首次启动时请允许 Python 通过系统防火墙的专用网络规则。")  # 提醒用户处理本机防火墙。
    uvicorn.run("bridge_mind.api:app", host="0.0.0.0", port=arguments.port)  # 启动绑定全部局域网网卡的服务。


if __name__ == "__main__":  # 检查脚本是否直接运行。
    main()  # 执行局域网启动流程。

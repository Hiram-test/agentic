# syntax=docker/dockerfile:1
# 使用受支持的精简 Python 运行环境。
FROM python:3.12-slim AS runtime
# 禁止生成无用字节码并启用即时日志输出。
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# 安装健康检查所需的最小系统工具并清理软件索引。
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
# 创建非特权运行用户和用户组。
RUN groupadd --system bridgemind && useradd --system --gid bridgemind --home-dir /app bridgemind
# 设置应用工作目录。
WORKDIR /app
# 复制依赖清单以利用容器构建缓存。
COPY requirements.txt pyproject.toml ./
# 安装 Python 运行依赖和当前项目元数据依赖。
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
# 复制服务端、前端、Schema、规则、示例和部署所需资源。
COPY bridge_mind ./bridge_mind
COPY web ./web
COPY schema ./schema
COPY rules ./rules
COPY mvd ./mvd
COPY examples ./examples
COPY prompts ./prompts
COPY skills ./skills
COPY run_demo.py README.md LICENSE ./
# 创建持久化目录并交给非特权用户。
RUN mkdir -p /app/data /app/runs && chown -R bridgemind:bridgemind /app
# 切换到非特权用户运行服务。
USER bridgemind
# 配置容器内默认持久化路径和 CalculiX 挂载路径。
ENV BRIDGEMIND_DATABASE_PATH=/app/data/bridgemind.sqlite3 BRIDGEMIND_RUNS_PATH=/app/runs CCX_EXECUTABLE=/opt/calculix/ccx
# 声明 FastAPI 服务端口。
EXPOSE 8000
# 使用公开探活接口判断容器健康状态。
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD curl --fail http://127.0.0.1:8000/api/health || exit 1
# 使用单进程模式保护 SQLite 写入一致性并接受反向代理头。
CMD ["python", "-m", "uvicorn", "bridge_mind.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]

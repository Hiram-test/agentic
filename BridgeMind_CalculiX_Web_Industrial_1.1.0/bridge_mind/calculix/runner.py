"""以受控子进程方式执行 CalculiX ccx 并保存日志与产物清单。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import hashlib  # 提供真实文件 SHA-256。
import json  # 提供运行清单序列化。
import os  # 提供环境变量处理。
import shutil  # 提供可执行文件查找。
import subprocess  # 提供外部进程执行。
from pathlib import Path  # 提供文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from .linter import lint_deck  # 复用输入文件静态检查。

_ARTIFACT_SUFFIXES = [".inp", ".dat", ".frd", ".sta", ".cvg", ".12d", ".eig", ".out", ".log"]  # 定义已知 CalculiX 产物扩展名。


def _sha256(path: Path) -> str:  # 计算真实文件 SHA-256。
    digest = hashlib.sha256()  # 创建哈希对象。
    with path.open("rb") as stream:  # 以二进制模式打开文件。
        for block in iter(lambda: stream.read(1024 * 1024), b""):  # 分块读取大文件。
            digest.update(block)  # 更新哈希状态。
    return digest.hexdigest()  # 返回十六进制哈希。


def detect_ccx(executable: str | None = None, expected_version: str = "2.23") -> dict[str, Any]:  # 探测 ccx 可执行文件。
    requested = executable or os.getenv("CCX_EXECUTABLE") or "ccx"  # 解析参数、环境变量和默认程序名。
    candidate = Path(requested).expanduser()  # 构造显式路径候选。
    resolved = str(candidate.resolve()) if candidate.is_file() else shutil.which(requested)  # 解析路径或在 PATH 中查找。
    return {"available": bool(resolved), "requested": requested, "executable": resolved, "expectedVersion": expected_version, "message": "已找到 CalculiX 可执行文件。" if resolved else "未找到 ccx；系统仍可生成、检查和下载 CalculiX 输入文件。"}  # 返回探测结果。


def _artifacts(directory: Path, stem: str) -> list[dict[str, Any]]:  # 收集作业产物及真实哈希。
    output: list[dict[str, Any]] = []  # 初始化产物清单。
    for suffix in _ARTIFACT_SUFFIXES:  # 遍历已知扩展名。
        path = directory / f"{stem}{suffix}"  # 构造候选路径。
        if path.is_file():  # 检查文件存在。
            output.append({"name": path.name, "path": str(path), "sizeBytes": path.stat().st_size, "sha256": _sha256(path)})  # 保存产物元数据。
    return output  # 返回产物清单。


def run_ccx(input_path: str | Path, executable: str | None = None, timeout: float = 3600.0, threads: int = 1, require_clean_lint: bool = True) -> dict[str, Any]:  # 执行一个 CalculiX 作业并生成可审计运行清单。
    path = Path(input_path).resolve()  # 规范化输入文件路径。
    if not path.is_file():  # 检查输入文件存在。
        raise FileNotFoundError(path)  # 抛出标准文件缺失异常。
    lint = lint_deck(path)  # 执行运行前静态检查。
    if require_clean_lint and not lint["valid"]:  # 检查是否允许执行静态非法 deck。
        result = {"status": "blocked", "message": "CalculiX 输入静态检查未通过，未启动 ccx。", "input": str(path), "lint": lint, "artifacts": _artifacts(path.parent, path.stem)}  # 构造阻断结果。
        manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入阻断清单。
        result["manifest"] = str(manifest_path)  # 保存清单路径。
        return result  # 返回阻断状态。
    solver = detect_ccx(executable)  # 探测求解器。
    if not solver["available"]:  # 处理本机未安装 ccx。
        result = {"status": "unavailable", "message": solver["message"], "input": str(path), "solver": solver, "lint": lint, "artifacts": _artifacts(path.parent, path.stem)}  # 构造不可用状态。
        manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入不可用清单。
        result["manifest"] = str(manifest_path)  # 保存清单路径。
        return result  # 返回不可用状态。
    environment = dict(os.environ)  # 复制当前环境变量。
    environment["OMP_NUM_THREADS"] = str(max(1, int(threads)))  # 设置求解线程数。
    environment["CCX_NPROC_RESULTS"] = str(max(1, int(threads)))  # 设置结果处理线程数。
    stdout_path = path.with_suffix(".out")  # 构造标准输出文件。
    stderr_path = path.with_suffix(".log")  # 构造标准错误文件。
    try:  # 捕获超时异常。
        completed = subprocess.run([str(solver["executable"]), "-i", path.stem], cwd=path.parent, capture_output=True, text=True, timeout=float(timeout), check=False, env=environment)  # 执行 ccx -i 作业名。
        stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")  # 保存标准输出。
        stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")  # 保存标准错误。
        diagnostic_text = f"{completed.stdout or ''}\n{completed.stderr or ''}".upper()  # 合并诊断文本。
        status = "succeeded" if completed.returncode == 0 and "*ERROR" not in diagnostic_text else "failed"  # 判定进程状态。
        result = {"status": status, "returnCode": completed.returncode, "input": str(path), "job": path.stem, "directory": str(path.parent), "solver": solver, "lint": lint, "stdout": str(stdout_path), "stderr": str(stderr_path), "timeoutSeconds": float(timeout), "threads": max(1, int(threads)), "artifacts": _artifacts(path.parent, path.stem)}  # 构造运行结果。
    except subprocess.TimeoutExpired as error:  # 处理运行超时。
        stdout_text = error.stdout if isinstance(error.stdout, str) else ""  # 读取超时前标准输出。
        stderr_text = error.stderr if isinstance(error.stderr, str) else ""  # 读取超时前标准错误。
        stdout_path.write_text(stdout_text, encoding="utf-8", errors="replace")  # 保存超时输出。
        stderr_path.write_text(stderr_text, encoding="utf-8", errors="replace")  # 保存超时错误。
        result = {"status": "timeout", "message": f"CalculiX 超过 {timeout} 秒运行上限。", "input": str(path), "job": path.stem, "directory": str(path.parent), "solver": solver, "lint": lint, "stdout": str(stdout_path), "stderr": str(stderr_path), "timeoutSeconds": float(timeout), "threads": max(1, int(threads)), "artifacts": _artifacts(path.parent, path.stem)}  # 构造超时结果。
    manifest_path = path.with_suffix(".run.json")  # 构造运行清单路径。
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入运行清单。
    result["manifest"] = str(manifest_path)  # 保存清单路径。
    return result  # 返回运行结果。

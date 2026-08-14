"""BridgeMind Studio 的通用确定性工具。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解以简化前向引用。
import copy  # 提供文档深复制能力。
import hashlib  # 提供内容哈希能力。
import json  # 提供规范化 JSON 序列化能力。
from datetime import datetime, timezone  # 提供统一 UTC 时间戳。
from pathlib import Path  # 提供跨平台路径处理。
from typing import Any  # 提供通用 JSON 类型注解。


def utc_now() -> str:  # 返回 ISO 8601 UTC 时间戳。
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # 生成带 Z 后缀的时间字符串。


def deep_copy(document: dict[str, Any]) -> dict[str, Any]:  # 对 BSDL 文档执行深复制。
    return copy.deepcopy(document)  # 返回与原对象无共享可变引用的副本。


def canonical_json(document: Any) -> str:  # 生成稳定排序的规范化 JSON 文本。
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))  # 关闭空白并稳定键顺序。


def content_hash(document: Any) -> str:  # 计算 JSON 内容的 SHA-256 哈希。
    payload = canonical_json(document).encode("utf-8")  # 把规范化文本编码为字节。
    return hashlib.sha256(payload).hexdigest()  # 返回十六进制摘要。


def load_json(path: str | Path) -> dict[str, Any]:  # 从路径读取 JSON 文档。
    file_path = Path(path)  # 规范化输入路径。
    with file_path.open("r", encoding="utf-8") as stream:  # 以 UTF-8 打开文件。
        value = json.load(stream)  # 解析 JSON 内容。
    if not isinstance(value, dict):  # 检查根对象必须是字典。
        raise ValueError(f"JSON 根对象必须是 object：{file_path}")  # 对非法根类型给出明确错误。
    return value  # 返回解析后的文档。


def save_json(path: str | Path, value: Any) -> Path:  # 把对象保存为易读 JSON 文件。
    file_path = Path(path)  # 规范化输出路径。
    file_path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在。
    file_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # 写入格式化 JSON。
    return file_path  # 返回实际输出路径。


def finite_number(value: Any) -> bool:  # 判断值是否为有限实数。
    if not isinstance(value, (int, float)) or isinstance(value, bool):  # 排除非数值和布尔值。
        return False  # 非数值直接判定无效。
    return value == value and value not in (float("inf"), float("-inf"))  # 排除 NaN 和正负无穷。


def slug(value: str) -> str:  # 把任意标识转换为文件安全短名。
    cleaned = "".join(character if character.isalnum() else "_" for character in value)  # 替换不安全字符。
    compact = "_".join(part for part in cleaned.split("_") if part)  # 合并连续分隔符。
    return compact or "item"  # 对空结果返回稳定默认值。


def json_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:  # 计算两个 JSON 值的对象级差异。
    changes: list[dict[str, Any]] = []  # 初始化差异列表。
    if type(before) is not type(after):  # 检测类型变化。
        changes.append({"op": "replace", "path": path or "/", "before": before, "after": after})  # 记录整体替换。
        return changes  # 类型不同无需继续递归。
    if isinstance(before, dict):  # 处理对象差异。
        before_keys = set(before)  # 收集旧对象键。
        after_keys = set(after)  # 收集新对象键。
        for key in sorted(before_keys - after_keys):  # 遍历被删除键。
            child_path = f"{path}/{key}"  # 构造子路径。
            changes.append({"op": "remove", "path": child_path, "before": before[key], "after": None})  # 记录删除。
        for key in sorted(after_keys - before_keys):  # 遍历新增键。
            child_path = f"{path}/{key}"  # 构造子路径。
            changes.append({"op": "add", "path": child_path, "before": None, "after": after[key]})  # 记录新增。
        for key in sorted(before_keys & after_keys):  # 遍历共有键。
            child_path = f"{path}/{key}"  # 构造子路径。
            changes.extend(json_diff(before[key], after[key], child_path))  # 递归比较共有值。
        return changes  # 返回对象差异。
    if isinstance(before, list):  # 处理数组差异。
        if before != after:  # 数组只在内容不同时记录替换。
            changes.append({"op": "replace", "path": path or "/", "before": before, "after": after})  # 保留完整前后数组便于审计。
        return changes  # 返回数组差异。
    if before != after:  # 处理标量变化。
        changes.append({"op": "replace", "path": path or "/", "before": before, "after": after})  # 记录标量替换。
    return changes  # 返回最终差异列表。

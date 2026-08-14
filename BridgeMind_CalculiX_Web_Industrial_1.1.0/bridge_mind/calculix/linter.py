"""对 BridgeMind 生成的 CalculiX 输入文件执行确定性静态检查。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import re  # 提供关键字和数值行解析。
from pathlib import Path  # 提供输入文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。

_KEYWORD_PATTERN = re.compile(r"^\s*\*([A-Z][A-Z0-9 _-]*)(?:,|$)", re.IGNORECASE)  # 定义 CalculiX 关键字识别表达式。
_SUPPORTED_KEYWORDS = {  # 声明本项目主动生成并静态核验的关键字集合。
    "AMPLITUDE",  # 允许幅值定义。
    "BEAM SECTION",  # 允许梁截面定义。
    "BOUNDARY",  # 允许边界条件定义。
    "BUCKLE",  # 允许线性屈曲过程。
    "CLOAD",  # 允许节点集中荷载。
    "CONTACT FILE",  # 允许接触结果输出。
    "CONTACT PAIR",  # 允许接触对定义。
    "DENSITY",  # 允许材料密度定义。
    "DLOAD",
    "DSLOAD",  # 允许分布荷载定义。
    "EL FILE",  # 允许单元结果文件输出。
    "EL PRINT",  # 允许单元文本结果输出。
    "ELASTIC",  # 允许线弹性材料定义。
    "ELEMENT",  # 允许单元定义。
    "ELSET",  # 允许单元集合定义。
    "END STEP",  # 允许分析步结束。
    "EQUATION",  # 允许多点约束方程。
    "FRICTION",  # 允许库仑摩擦定义。
    "FREQUENCY",  # 允许模态分析过程。
    "HEADING",  # 允许输入文件标题。
    "INITIAL CONDITIONS",  # 允许初始状态定义。
    "MATERIAL",  # 允许材料定义。
    "MODEL CHANGE",  # 允许施工阶段单元和接触生死控制。
    "NODE",  # 允许节点定义。
    "NODE FILE",  # 允许节点结果文件输出。
    "NODE PRINT",  # 允许节点文本结果输出。
    "NSET",  # 允许节点集合定义。
    "PLASTIC",  # 允许塑性材料曲线定义。
    "PRE-TENSION SECTION",  # 允许原生预紧截面定义。
    "SHELL SECTION",  # 允许壳截面定义。
    "SOLID SECTION",  # 允许实体和桁架截面定义。
    "STATIC",  # 允许静力分析过程。
    "STEP",  # 允许分析步定义。
    "SURFACE",  # 允许接触表面定义。
    "SURFACE BEHAVIOR",  # 允许法向接触行为定义。
    "SURFACE INTERACTION",  # 允许表面相互作用定义。
    "TEMPERATURE",  # 允许温度场定义。
    "TIE",  # 允许绑定约束定义。
}  # 完成受支持关键字集合。


def _issue(code: str, severity: str, line: int | None, message: str, value: Any = None) -> dict[str, Any]:  # 构造统一静态检查问题。
    return {"code": code, "severity": severity, "line": line, "message": message, "value": value}  # 返回问题对象。


def _parse_integer(value: str) -> int | None:  # 从逗号字段安全解析整数。
    try:  # 捕获非法编号。
        return int(value.strip())  # 返回整数编号。
    except (TypeError, ValueError):  # 处理非整数文本。
        return None  # 返回空表示无法解析。


def lint_deck(source: str | Path, from_text: bool = False) -> dict[str, Any]:  # 检查 CalculiX deck 的关键字、编号和最小分析结构。
    text = str(source) if from_text else Path(source).read_text(encoding="utf-8", errors="replace")  # 读取文本或使用直接文本。
    lines = text.splitlines()  # 拆分输入文件行。
    issues: list[dict[str, Any]] = []  # 初始化问题列表。
    keywords: list[str] = []  # 初始化关键字顺序列表。
    node_ids: set[int] = set()  # 初始化节点编号集合。
    element_ids: set[int] = set()  # 初始化单元编号集合。
    referenced_nodes: set[int] = set()  # 初始化单元引用节点集合。
    current_keyword: str | None = None  # 初始化当前关键字上下文。
    blocked_marker = False  # 初始化转换阻断标记。
    for line_number, raw_line in enumerate(lines, start=1):  # 逐行扫描输入文件。
        line = raw_line.strip()  # 去除首尾空白。
        if not line:  # 跳过空行。
            continue  # 继续下一行。
        if line.startswith("**"):  # 处理 CalculiX 注释。
            if "BLOCKED" in line.upper():  # 检查 Adapter 阻断标记。
                blocked_marker = True  # 记录该 deck 仅供检查。
            continue  # 注释不参与语法状态。
        match = _KEYWORD_PATTERN.match(line)  # 识别关键字行。
        if match:  # 处理关键字。
            current_keyword = re.sub(r"\s+", " ", match.group(1).strip().upper())  # 规范化关键字名称。
            keywords.append(current_keyword)  # 保存关键字顺序。
            if current_keyword not in _SUPPORTED_KEYWORDS:  # 检查未知或未核验关键字。
                issues.append(_issue("CCX-LINT-KEYWORD-001", "warning", line_number, f"关键字 {current_keyword} 不在 BridgeMind 已核验生成子集中。", current_keyword))  # 记录未知关键字警告。
            continue  # 继续下一行。
        if line.startswith("*"):  # 处理无法识别的星号行。
            issues.append(_issue("CCX-LINT-KEYWORD-002", "error", line_number, "关键字行无法解析。", line))  # 记录关键字语法错误。
            current_keyword = None  # 清除当前上下文。
            continue  # 继续下一行。
        fields = [field.strip() for field in line.split(",")]  # 拆分数据字段。
        if current_keyword == "NODE":  # 解析节点数据行。
            node_id = _parse_integer(fields[0]) if fields else None  # 读取节点号。
            if node_id is None or len(fields) < 4:  # 检查节点号和三维坐标字段。
                issues.append(_issue("CCX-LINT-NODE-001", "error", line_number, "节点行必须包含整数节点号和三个坐标。", line))  # 记录节点行错误。
            elif node_id in node_ids:  # 检查重复节点号。
                issues.append(_issue("CCX-LINT-NODE-002", "error", line_number, f"节点号 {node_id} 重复。", node_id))  # 记录重复节点。
            else:  # 处理合法节点号。
                node_ids.add(node_id)  # 保存节点号。
        elif current_keyword == "ELEMENT":  # 解析单元数据行。
            element_id = _parse_integer(fields[0]) if fields else None  # 读取单元号。
            if element_id is None or len(fields) < 3:  # 检查单元号和连接字段。
                issues.append(_issue("CCX-LINT-ELEMENT-001", "error", line_number, "单元行必须包含整数单元号和至少两个节点号。", line))  # 记录单元行错误。
            elif element_id in element_ids:  # 检查重复单元号。
                issues.append(_issue("CCX-LINT-ELEMENT-002", "error", line_number, f"单元号 {element_id} 重复。", element_id))  # 记录重复单元。
            else:  # 处理合法单元号。
                element_ids.add(element_id)  # 保存单元号。
                for field in fields[1:]:  # 遍历连接节点字段。
                    node_id = _parse_integer(field)  # 解析节点号。
                    if node_id is not None:  # 检查字段为节点号。
                        referenced_nodes.add(node_id)  # 保存单元引用节点。
    missing_nodes = sorted(referenced_nodes - node_ids)  # 查找单元引用但未定义的节点。
    for node_id in missing_nodes[:100]:  # 限制一次报告的悬空节点数量。
        issues.append(_issue("CCX-LINT-REF-001", "error", None, f"单元引用了未定义节点 {node_id}。", node_id))  # 记录悬空节点。
    required_keywords = {"NODE", "ELEMENT", "STEP", "END STEP"}  # 定义可执行结构分析 deck 的最小关键字。
    missing_keywords = sorted(required_keywords - set(keywords))  # 查找缺失关键字。
    for keyword in missing_keywords:  # 遍历缺失关键字。
        issues.append(_issue("CCX-LINT-STRUCTURE-001", "error", None, f"缺少必需关键字 *{keyword}。", keyword))  # 记录结构缺项。
    step_depth = 0  # 初始化分析步嵌套深度。
    for keyword in keywords:  # 遍历关键字顺序。
        if keyword == "STEP":  # 处理分析步开始。
            step_depth += 1  # 增加未闭合步数。
        elif keyword == "END STEP":  # 处理分析步结束。
            step_depth -= 1  # 减少未闭合步数。
            if step_depth < 0:  # 检查先结束后开始。
                issues.append(_issue("CCX-LINT-STEP-001", "error", None, "出现没有对应 *STEP 的 *END STEP。"))  # 记录步结构错误。
                step_depth = 0  # 重置深度避免重复错误。
    if step_depth != 0:  # 检查是否存在未闭合分析步。
        issues.append(_issue("CCX-LINT-STEP-002", "error", None, f"存在 {step_depth} 个未闭合分析步。", step_depth))  # 记录未闭合步。
    errors = [item for item in issues if item["severity"] == "error"]  # 提取阻断静态问题。
    warnings = [item for item in issues if item["severity"] == "warning"]  # 提取静态警告。
    return {"valid": not errors and not blocked_marker, "blockedMarker": blocked_marker, "issues": issues, "errors": errors, "warnings": warnings, "stats": {"lines": len(lines), "nodes": len(node_ids), "elements": len(element_ids), "keywords": len(keywords), "steps": keywords.count("STEP")}, "keywords": keywords}  # 返回完整静态检查报告。

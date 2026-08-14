"""执行版本化规则包并生成逐条可追溯验算结果。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import ast  # 提供受限表达式语法树解析。
import math  # 提供允许的数学函数。
import operator  # 提供受限算术运算符。
from pathlib import Path  # 提供规则包路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
import yaml  # 提供 YAML 规则包读取。
from ..utils import utc_now  # 复用统一时间戳。

_BINARY_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}  # 定义允许的二元运算。
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}  # 定义允许的一元运算。
_COMPARISON_OPERATORS = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Is: operator.is_, ast.IsNot: operator.is_not}  # 定义允许的比较运算并支持空值判定。
_FUNCTIONS = {"abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "exp": math.exp, "log": math.log, "sin": math.sin, "cos": math.cos, "tan": math.tan}  # 定义允许的纯函数。


def _attribute(value: Any, name: str) -> Any:  # 安全读取字典属性并禁止任意 Python 对象访问。
    if isinstance(value, dict) and name in value:  # 检查字典是否包含指定键。
        return value[name]  # 返回字典字段值。
    raise ValueError(f"规则表达式引用了不存在的属性：{name}")  # 阻止访问未知属性。


def _evaluate_node(node: ast.AST, context: dict[str, Any]) -> Any:  # 递归计算受限表达式语法树。
    if isinstance(node, ast.Expression):  # 处理表达式根节点。
        return _evaluate_node(node.body, context)  # 计算表达式主体。
    if isinstance(node, ast.Constant):  # 处理常量。
        if isinstance(node.value, (int, float, bool, str, type(None))):  # 检查常量类型安全性。
            return node.value  # 返回允许的常量值。
        raise ValueError("规则表达式包含不允许的常量。")  # 阻止复杂常量。
    if isinstance(node, ast.Name):  # 处理上下文变量。
        if node.id in context:  # 检查变量是否存在。
            return context[node.id]  # 返回上下文变量值。
        if node.id in _FUNCTIONS:  # 检查是否为允许函数名。
            return _FUNCTIONS[node.id]  # 返回允许函数对象。
        raise ValueError(f"规则表达式引用了未知变量：{node.id}")  # 阻止未知变量。
    if isinstance(node, ast.Attribute):  # 处理字典点号字段访问。
        return _attribute(_evaluate_node(node.value, context), node.attr)  # 安全读取嵌套字段。
    if isinstance(node, ast.Subscript):  # 处理字典或列表下标访问。
        container = _evaluate_node(node.value, context)  # 计算容器对象。
        key = _evaluate_node(node.slice, context)  # 计算下标键。
        if isinstance(container, (dict, list, tuple)):  # 检查容器类型。
            return container[key]  # 返回下标值。
        raise ValueError("规则表达式只能对字典或列表使用下标。")  # 阻止任意对象下标。
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:  # 处理允许的二元运算。
        left = _evaluate_node(node.left, context)  # 计算左操作数。
        right = _evaluate_node(node.right, context)  # 计算右操作数。
        return _BINARY_OPERATORS[type(node.op)](left, right)  # 执行受限二元运算。
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:  # 处理允许的一元运算。
        return _UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand, context))  # 执行受限一元运算。
    if isinstance(node, ast.BoolOp):  # 处理布尔与或表达式。
        values = [_evaluate_node(value, context) for value in node.values]  # 计算全部布尔项。
        return all(values) if isinstance(node.op, ast.And) else any(values)  # 返回与或结果。
    if isinstance(node, ast.Compare):  # 处理链式比较表达式。
        left = _evaluate_node(node.left, context)  # 计算第一个比较值。
        for operator_node, comparator in zip(node.ops, node.comparators):  # 遍历每一段比较。
            right = _evaluate_node(comparator, context)  # 计算右侧比较值。
            function = _COMPARISON_OPERATORS.get(type(operator_node))  # 查找允许的比较函数。
            if function is None:  # 检查比较运算是否允许。
                raise ValueError("规则表达式包含不允许的比较运算。")  # 阻止未授权比较。
            if not function(left, right):  # 执行当前比较。
                return False  # 任一比较失败即返回假。
            left = right  # 把右值作为下一段比较左值。
        return True  # 返回链式比较成功。
    if isinstance(node, ast.Call):  # 处理允许函数调用。
        function = _evaluate_node(node.func, context)  # 解析函数对象。
        if function not in _FUNCTIONS.values():  # 检查函数是否在白名单中。
            raise ValueError("规则表达式调用了不允许的函数。")  # 阻止任意函数执行。
        arguments = [_evaluate_node(argument, context) for argument in node.args]  # 计算位置参数。
        if node.keywords:  # 检查是否使用关键字参数。
            raise ValueError("规则表达式不允许关键字参数。")  # 简化并限制函数调用。
        return function(*arguments)  # 调用白名单纯函数。
    if isinstance(node, ast.IfExp):  # 处理三元条件表达式。
        condition = _evaluate_node(node.test, context)  # 计算条件。
        return _evaluate_node(node.body if condition else node.orelse, context)  # 返回对应分支结果。
    raise ValueError(f"规则表达式包含不允许的语法：{type(node).__name__}")  # 阻止其他 Python 语法。


def safe_eval(expression: str, context: dict[str, Any]) -> Any:  # 在无脚本执行能力的环境中计算工程表达式。
    tree = ast.parse(expression, mode="eval")  # 把表达式解析为语法树。
    return _evaluate_node(tree, context)  # 返回受限求值结果。


def load_rule_pack(rule_pack: str, root: str | Path) -> dict[str, Any]:  # 读取内置或项目规则包。
    root_path = Path(root).resolve()  # 规范化项目根目录。
    aliases = {"generic.bridge": root_path / "rules" / "code_checks" / "generic_bridge_checks.yaml"}  # 定义内置规则包别名。
    candidate = aliases.get(rule_pack, Path(rule_pack))  # 解析规则包别名或路径。
    candidate = candidate if candidate.is_absolute() else (root_path / candidate)  # 把相对路径解析到项目根目录。
    resolved = candidate.resolve()  # 规范化规则包绝对路径。
    if root_path not in resolved.parents and resolved != root_path:  # 检查规则包路径是否逃逸项目目录。
        raise ValueError("规则包路径必须位于项目目录内。")  # 阻止任意文件读取。
    if not resolved.is_file():  # 检查规则包存在。
        raise FileNotFoundError(resolved)  # 返回标准文件缺失异常。
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))  # 解析 YAML 规则包。
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):  # 检查规则包基本结构。
        raise ValueError("规则包必须是包含 rules 数组的对象。")  # 阻止非法规则包。
    payload["_resolvedPath"] = str(resolved)  # 保存实际规则包路径用于审计。
    return payload  # 返回规则包对象。


def _target_context(document: dict[str, Any], target_ref: str, global_context: dict[str, Any]) -> dict[str, Any]:  # 构造单个验算目标的表达式上下文。
    collections = ["components", "nodes", "connections", "materials", "sections", "shellSections", "solidSections", "contacts", "prestressingSystems"]  # 定义可被验算目标引用的对象集合。
    target: dict[str, Any] | None = None  # 初始化目标对象。
    for collection in collections:  # 遍历所有可验算集合。
        for item in document.get(collection, []):  # 遍历集合对象。
            if isinstance(item, dict) and str(item.get("id")) == target_ref:  # 检查目标 ID 是否匹配。
                target = item  # 保存匹配目标对象。
                break  # 退出当前集合循环。
        if target is not None:  # 检查是否已经找到目标。
            break  # 退出集合遍历。
    context = dict(global_context)  # 复制全局计算上下文。
    context["target"] = target or {"id": target_ref}  # 加入目标对象。
    if target and target.get("materialRef"):  # 检查目标是否引用材料。
        context["material"] = next((item for item in document.get("materials", []) if isinstance(item, dict) and item.get("id") == target.get("materialRef")), {})  # 加入目标材料对象。
    else:  # 处理目标没有材料引用。
        context["material"] = {}  # 提供空材料对象。
    if target and target.get("sectionRef"):  # 检查目标是否引用截面。
        context["section"] = next((item for item in document.get("sections", []) if isinstance(item, dict) and item.get("id") == target.get("sectionRef")), {})  # 加入目标截面对象。
    else:  # 处理目标没有截面引用。
        context["section"] = {}  # 提供空截面对象。
    return context  # 返回目标表达式上下文。


def run_code_check_plan(document: dict[str, Any], plan_id: str, result_context: dict[str, Any], root: str | Path) -> dict[str, Any]:  # 执行一个版本化验算计划并返回结果对象。
    plan = next((item for item in document.get("codeCheckPlans", []) if isinstance(item, dict) and item.get("id") == plan_id), None)  # 查找验算计划。
    if plan is None:  # 检查验算计划是否存在。
        raise KeyError(f"规范验算计划不存在：{plan_id}")  # 对缺失计划给出明确错误。
    standard = plan.get("standard", {})  # 读取规范引用。
    try:  # 捕获规则包缺失并转换为可审计阻断报告。
        rule_pack = load_rule_pack(str(plan.get("rulePack")), root)  # 读取规则包。
    except FileNotFoundError as error:  # 处理规则包不存在。
        return {"planRef": plan_id, "status": "blocked", "reason": "规则包不存在。", "licensedContentRequired": bool(standard.get("licensedContentRequired")), "missingRulePack": str(error), "results": []}  # 返回阻断状态。
    global_context = {"parameters": plan.get("parameters", {}), "acceptance": plan.get("acceptance", {}), "results": result_context, "standard": standard}  # 构造全局表达式上下文。
    targets = [str(value) for value in plan.get("targetRefs", [])] or [str(document.get("project", {}).get("id", "project"))]  # 读取验算目标或使用项目目标。
    outputs: list[dict[str, Any]] = []  # 初始化逐条验算结果。
    blocked_count = 0  # 初始化阻断规则计数。
    for target_ref in targets:  # 遍历所有验算目标。
        context = _target_context(document, target_ref, global_context)  # 构造目标上下文。
        for rule in rule_pack.get("rules", []):  # 遍历规则包规则。
            if not isinstance(rule, dict):  # 跳过非法规则项。
                continue  # 继续检查下一规则。
            rule_id = str(rule.get("id", "UNKNOWN"))  # 读取稳定规则 ID。
            try:  # 捕获规则表达式缺少数据或计算失败。
                applicable = bool(safe_eval(str(rule.get("applicability", "True")), context))  # 计算适用条件。
                if not applicable:  # 检查规则是否适用。
                    outputs.append({"id": f"check.{plan_id}.{target_ref}.{rule_id}", "planRef": plan_id, "targetRef": target_ref, "ruleId": rule_id, "demand": 0.0, "capacity": 0.0, "utilization": 0.0, "unit": str(rule.get("unit", "")), "verdict": "not_applicable", "evidenceRefs": [], "calculatedAt": utc_now(), "engineVersion": "1.0.0", "details": {"title": rule.get("title"), "reason": "适用条件为假。"}})  # 保存不适用结果。
                    continue  # 继续下一规则。
                demand = float(safe_eval(str(rule.get("demand")), context))  # 计算作用效应或需求值。
                capacity = float(safe_eval(str(rule.get("capacity")), context))  # 计算抗力或限值。
                if capacity <= 0.0:  # 检查容量或限值为正。
                    raise ValueError("capacity 必须大于零。")  # 阻止无意义利用率。
                utilization = abs(demand) / capacity  # 计算统一利用率。
                warning_limit = float(rule.get("warningUtilization", 0.9))  # 读取预警利用率阈值。
                verdict = "pass" if utilization <= 1.0 else "fail"  # 根据容量判定通过或失败。
                if verdict == "pass" and utilization >= warning_limit:  # 检查是否接近容量。
                    verdict = "warning"  # 标记预警状态。
                outputs.append({"id": f"check.{plan_id}.{target_ref}.{rule_id}", "planRef": plan_id, "targetRef": target_ref, "ruleId": rule_id, "demand": demand, "capacity": capacity, "utilization": utilization, "unit": str(rule.get("unit", "")), "verdict": verdict, "evidenceRefs": [str(value) for value in rule.get("evidenceRefs", [])], "calculatedAt": utc_now(), "engineVersion": "1.0.0", "details": {"title": rule.get("title"), "clause": rule.get("clause"), "demandExpression": rule.get("demand"), "capacityExpression": rule.get("capacity"), "rulePack": rule_pack.get("id"), "rulePackVersion": rule_pack.get("version")}})  # 保存可审计验算结果。
            except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as error:  # 处理规则数据或计算失败。
                blocked_count += 1  # 累加阻断规则数量。
                outputs.append({"id": f"check.{plan_id}.{target_ref}.{rule_id}", "planRef": plan_id, "targetRef": target_ref, "ruleId": rule_id, "demand": 0.0, "capacity": 0.0, "utilization": 0.0, "unit": str(rule.get("unit", "")), "verdict": "blocked", "evidenceRefs": [], "calculatedAt": utc_now(), "engineVersion": "1.0.0", "details": {"title": rule.get("title"), "error": str(error), "requiredInputs": rule.get("requiredInputs", [])}})  # 保存阻断结果而不伪造数值。
    summary = {"total": len(outputs), "pass": sum(1 for item in outputs if item["verdict"] == "pass"), "warning": sum(1 for item in outputs if item["verdict"] == "warning"), "fail": sum(1 for item in outputs if item["verdict"] == "fail"), "blocked": sum(1 for item in outputs if item["verdict"] == "blocked"), "notApplicable": sum(1 for item in outputs if item["verdict"] == "not_applicable"), "maximumUtilization": max((float(item["utilization"]) for item in outputs if item["verdict"] not in {"blocked", "not_applicable"}), default=0.0)}  # 汇总验算统计。
    status = "blocked" if blocked_count == len(outputs) and outputs else ("failed" if summary["fail"] else "completed")  # 计算计划执行状态。
    return {"planRef": plan_id, "status": status, "standard": standard, "rulePack": {"id": rule_pack.get("id"), "version": rule_pack.get("version"), "path": rule_pack.get("_resolvedPath")}, "summary": summary, "results": outputs, "disclaimer": "本引擎负责规则版本、输入、计算和证据审计；只有经项目责任工程师核验并合法配置的正式规则包才能用于规范符合性结论。"}  # 返回完整验算报告。

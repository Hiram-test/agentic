"""提供 CalculiX 输入检查、受控执行和结果解析工具。"""  # 说明包用途。
from .linter import lint_deck  # 导出输入文件静态检查函数。
from .results import parse_dat, parse_frd, summarize_results  # 导出结果解析函数。
from .runner import detect_ccx, run_ccx  # 导出可执行文件探测和运行函数。

__all__ = ["lint_deck", "parse_dat", "parse_frd", "summarize_results", "detect_ccx", "run_ccx"]  # 声明公共接口。

"""BridgeMind Studio 的命令行入口。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import argparse  # 提供命令行参数解析。
import json  # 提供控制台 JSON 输出。
from pathlib import Path  # 提供文件路径处理。
from .adapters.calculix import export_calculix  # 导入 CalculiX 导出器。
from .adapters.gmsh import export_gmsh  # 导入 Gmsh 导出器。
from .cognition.orchestrator import propose_strategy  # 导入多专家策略生成器。
from .fea.frame3d import solve_document  # 导入内置空间梁求解器。
from .importers.point_cloud import build_bsdl_from_point_cloud  # 导入点云转换器。
from .utils import load_json, save_json  # 导入 JSON 文件工具。
from .validator import validate_document  # 导入 BSDL 验证器。


def _print(value: object) -> None:  # 以 UTF-8 友好格式输出 JSON。
    print(json.dumps(value, ensure_ascii=False, indent=2))  # 把对象格式化到标准输出。


def build_parser() -> argparse.ArgumentParser:  # 构造 BridgeMind 命令行解析器。
    parser = argparse.ArgumentParser(prog="bridgemind", description="BSDL 统一结构描述、区域策略和快速 FEA 工具。")  # 创建根解析器。
    commands = parser.add_subparsers(dest="command", required=True)  # 创建必选子命令集合。
    validate = commands.add_parser("validate", help="验证 BSDL 文档。")  # 添加验证命令。
    validate.add_argument("input")  # 添加输入文档路径。
    propose = commands.add_parser("propose", help="生成多专家区域策略。")  # 添加策略命令。
    propose.add_argument("input")  # 添加输入文档路径。
    propose.add_argument("--output", required=True)  # 添加输出文档路径。
    solve = commands.add_parser("solve", help="执行内置空间梁快速试算。")  # 添加求解命令。
    solve.add_argument("input")  # 添加输入文档路径。
    solve.add_argument("--output", required=True)  # 添加结果输出路径。
    solve.add_argument("--mesh-policy")  # 添加可选网格策略 ID。
    solve.add_argument("--load-case")  # 添加可选荷载工况 ID。
    calculix = commands.add_parser("export-calculix", help="导出 CalculiX 梁、壳、实体、接触、预应力和施工阶段输入。")  # 添加 CalculiX 导出命令。
    calculix.add_argument("input")  # 添加输入文档路径。
    calculix.add_argument("--output", required=True)  # 添加输入文件输出路径。
    gmsh = commands.add_parser("export-gmsh", help="导出 Gmsh GEO 线网格脚本。")  # 添加 Gmsh 导出命令。
    gmsh.add_argument("input")  # 添加输入文档路径。
    gmsh.add_argument("--output", required=True)  # 添加 GEO 输出路径。
    point_cloud = commands.add_parser("import-point-cloud", help="把 XYZ/CSV 点云转换为初始 BSDL。")  # 添加点云导入命令。
    point_cloud.add_argument("input")  # 添加点云输入路径。
    point_cloud.add_argument("--output", required=True)  # 添加 BSDL 输出路径。
    point_cloud.add_argument("--eps", type=float, default=0.6)  # 添加 DBSCAN 邻域半径。
    point_cloud.add_argument("--min-samples", type=int, default=6)  # 添加 DBSCAN 最小样本数。
    point_cloud.add_argument("--voxel-size", type=float, default=0.2)  # 添加体素降采样尺寸。
    return parser  # 返回命令行解析器。


def main() -> int:  # 执行命令行请求并返回进程状态码。
    arguments = build_parser().parse_args()  # 解析命令行参数。
    if arguments.command == "validate":  # 处理 BSDL 验证命令。
        report = validate_document(load_json(arguments.input))  # 读取并验证文档。
        _print(report)  # 输出验证报告。
        return 0 if report["valid"] else 2  # 以状态码区分验证通过和失败。
    if arguments.command == "propose":  # 处理多专家策略命令。
        document = load_json(arguments.input)  # 读取输入 BSDL 文档。
        updated, report = propose_strategy(document)  # 生成区域和网格策略。
        save_json(arguments.output, updated)  # 保存更新文档。
        _print(report)  # 输出策略报告。
        return 0  # 返回成功状态。
    if arguments.command == "solve":  # 处理内置求解命令。
        document = load_json(arguments.input)  # 读取输入 BSDL 文档。
        result = solve_document(document, arguments.mesh_policy, arguments.load_case)  # 执行快速 FEA。
        save_json(arguments.output, result)  # 保存求解结果。
        _print({"status": result["status"], "output": str(Path(arguments.output)), "globalMetrics": result["globalMetrics"], "meshStats": result["mesh"]["stats"]})  # 输出结果摘要。
        return 0  # 返回成功状态。
    if arguments.command == "export-calculix":  # 处理 CalculiX 导出命令。
        report = export_calculix(load_json(arguments.input), arguments.output)  # 执行输入文件转换。
        _print(report)  # 输出转换报告。
        return 0  # 返回成功状态。
    if arguments.command == "export-gmsh":  # 处理 Gmsh 导出命令。
        report = export_gmsh(load_json(arguments.input), arguments.output)  # 执行 GEO 转换。
        _print(report)  # 输出转换报告。
        return 0  # 返回成功状态。
    if arguments.command == "import-point-cloud":  # 处理点云导入命令。
        document, report = build_bsdl_from_point_cloud(arguments.input, arguments.eps, arguments.min_samples, arguments.voxel_size)  # 执行点云分割和 BSDL 生成。
        save_json(arguments.output, document)  # 保存生成文档。
        _print({"output": str(Path(arguments.output)), "import": report, "validation": validate_document(document)})  # 输出导入与验证报告。
        return 0  # 返回成功状态。
    return 1  # 对不可达未知命令返回失败状态。


if __name__ == "__main__":  # 检查模块是否直接执行。
    raise SystemExit(main())  # 执行 CLI 并把状态码传给进程。

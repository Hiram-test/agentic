"""验证 CalculiX 外部进程、DAT 回读、产物哈希和结果集生成。"""  # 说明测试文件用途。
from __future__ import annotations  # 启用延迟类型注解。
import json  # 提供示例文档读取。
from pathlib import Path  # 提供临时路径类型。
from bridge_mind.adapters.calculix import export_calculix, run_calculix  # 导入导出和运行链路。

ROOT = Path(__file__).resolve().parents[1]  # 获取项目根目录。


def build_fake_ccx(directory: Path) -> Path:  # 创建行为可控的 CalculiX 测试替身。
    executable = directory / "fake_ccx.py"  # 构造测试可执行文件路径。
    executable.write_text("""#!/usr/bin/env python3
import pathlib  # 提供作业文件路径处理。
import sys  # 提供命令行参数读取。
arguments = sys.argv[1:]  # 读取 ccx 风格命令行参数。
stem = arguments[arguments.index('-i') + 1]  # 读取 -i 后的作业名。
root = pathlib.Path.cwd()  # 获取 Adapter 设置的作业目录。
dat = '''displacements (vx,vy,vz) for set NALL and time 1.0\n1 1.0E-3 0.0 0.0\nreaction forces for set NALL and time 1.0\n1 100.0 0.0 0.0\nstresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time 1.0\n1 1 1.0E6 0.0 0.0 0.0 0.0 0.0\nstrains (elem, integ.pnt.,exx,eyy,ezz,exy,exz,eyz) for set EALL and time 1.0\n1 1 1.0E-5 0.0 0.0 0.0 0.0 0.0\n'''  # 构造最小可解析 DAT 文本。
(root / f'{stem}.dat').write_text(dat, encoding='utf-8')  # 写入结果文本。
(root / f'{stem}.frd').write_text('FAKE FRD ARTIFACT\\n', encoding='utf-8')  # 写入结果场产物。
print('fake CalculiX completed')  # 输出可归档标准日志。
""", encoding="utf-8")  # 保存测试替身脚本。
    executable.chmod(0o755)  # 赋予可执行权限。
    return executable  # 返回测试替身路径。


def test_fake_ccx_execution_imports_results(tmp_path: Path) -> None:  # 检查真实子进程契约和结果回读。
    document = json.loads((ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json").read_text(encoding="utf-8"))  # 读取工业示例。
    deck = tmp_path / "bridge_job.inp"  # 构造临时作业路径。
    export_calculix(document, deck, solver_plan_id="solver.calculix.industrial", finite_element_model_id="fem.bridge_segment", strict=True)  # 生成真实 CalculiX 输入和 ID 映射。
    executable = build_fake_ccx(tmp_path)  # 创建测试替身程序。
    result = run_calculix(deck, str(executable), timeout=30.0, threads=2)  # 通过标准子进程接口执行作业。
    assert result["status"] == "succeeded"  # 确认进程和错误检查均通过。
    assert result["parsedResults"]["summaries"]["displacement"]["count"] == 1  # 确认 DAT 位移回读成功。
    assert result["parsedResults"]["summaries"]["stress"]["maximumMagnitude"] == 1000000.0  # 确认应力摘要正确。
    assert result["resultSet"]["status"] == "complete"  # 确认生成 Schema 兼容结果集。
    assert any(item["name"].endswith(".frd") and len(item["sha256"]) == 64 for item in result["artifacts"])  # 确认 FRD 产物和真实 SHA-256 被保留。


def test_missing_ccx_is_explicitly_unavailable(tmp_path: Path) -> None:  # 检查环境缺失不会伪造成求解成功。
    document = json.loads((ROOT / "examples" / "calculix_industrial_bridge_segment.bsdl.json").read_text(encoding="utf-8"))  # 读取工业示例。
    deck = tmp_path / "unavailable_job.inp"  # 构造临时作业路径。
    export_calculix(document, deck, solver_plan_id="solver.calculix.industrial", finite_element_model_id="fem.bridge_segment", strict=True)  # 生成待运行 deck。
    result = run_calculix(deck, str(tmp_path / "missing_ccx"), timeout=10.0, threads=1)  # 指定不存在的可执行路径。
    assert result["status"] == "unavailable"  # 确认返回显式不可用状态。
    assert result["solver"]["available"] is False  # 确认能力状态没有伪造。

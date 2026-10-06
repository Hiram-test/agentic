# 01 安装、文件契约与一键执行

## 目录与依赖

- `assets/inputs/`：六份原件INP；每份约1 MB，UTF-8。P1是一分析步，其他是两分析步。
- `assets/reference/original_review_0324.pdf`：用户上传的118页原始报告，随包携带。
- `assets/reference/original_review_text.txt`：按物理PDF页编号提取的文本。
- `manifest.json`：原仓库、分支、固定commit、每个INP哈希。
- `span_groups.json`：从原始MCT读取的8个索跨度单元集合；不要用节点号范围猜跨度。
- `benchmarks.json`：报告索力与MAPDL位移，必须保留来源区分。
- `P*_input_audit.json`：材料、截面、边界、质量、每步荷载合力/力矩、温度与初应力数量。
- `assets/integrity.json`：包括原PDF在内的资产哈希。
- `scripts/model.py`：本版输入解析、审计、DAT读取、轴力恢复。
- `scripts/mesh_gmsh.py`：实际Gmsh网格生成及编号映射。
- `scripts/postprocess.py`：完整性校验、数值比较、云图与VTU。
- `scripts/report.py`：同一数据生成中文DOCX及PDF。
- `scripts/run.py`：完整编排。脚本无外部model仓库依赖，无LLM账号依赖。

Python建议3.11或3.12。本次实际使用版本记录于示例run.json。安装 `requirements.txt` 中锁定的gmsh、numpy、matplotlib、python-docx、reportlab。运行不需要LibreOffice，PDF由ReportLab直接生成；Word目录域需在Word里更新。

Gmsh Python包会加载原生库。在Linux出现 `libGLU.so.1` 错误时安装系统包 `libglu1-mesa`（例如 `apt-get install libglu1-mesa`），然后 `python -c "import gmsh; print(gmsh.__version__)"` 验证。无桌面的服务器可正常执行此处的API，脚本不调用 `gmsh.fltk.run()`。

## Linux独立运行

```bash
SKILL_ROOT=/absolute/path/to/catwalk-static-review
python3 -m venv "$SKILL_ROOT/.venv"
"$SKILL_ROOT/.venv/bin/python" -m pip install -r "$SKILL_ROOT/requirements.txt"
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --verify-only
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --out /absolute/path/to/run-001
```

没有给 `--solver` 时，仅Linux x86_64自动下载：

`https://github.com/Hiram-test/model/releases/download/c3-ft14-parser-safe-667c5047/ccx-2.23-UCOR6-UCAB3-FT14-linux-x86_64`

执行前要求SHA256为：

`b498dad80b0415d53ab112409adc85b8a1fd19eb7846dc31e778f4c83b437a0e`

网络不通时，用已下载的同哈希可执行文件 `--solver /path/to/ccx`。必要时运行 `ldd /path/to/ccx` 核查动态库；不要通过改输入来修复动态库缺失。

## Windows PowerShell

```powershell
$SkillRoot = 'C:\work\catwalk-static-review'
py -3.12 -m venv "$SkillRoot\.venv"
& "$SkillRoot\.venv\Scripts\python.exe" -m pip install -r "$SkillRoot\requirements.txt"
& "$SkillRoot\.venv\Scripts\python.exe" "$SkillRoot\scripts\run.py" --verify-only
& "$SkillRoot\.venv\Scripts\python.exe" "$SkillRoot\scripts\run.py" `
  --solver 'C:\CalculiX\ccx.exe' --allow-solver-variant `
  --out 'C:\work\runs\run-001'
```

Linux ELF求解器不能在Windows直接运行；优先WSL2运行锁定Linux二进制。使用本地Windows ccx.exe是**替代求解器试算**，必须指定 `--allow-solver-variant`，记录其哈希和版本，并重新完成六工况对照。此标志仅放行求解器哈希，不放行INP版本、不放行不收敛或超差结果。macOS同理使用兼容本地求解器试算；当前不声称已测试Windows/macOS。

## 运行成功与失败

默认每工况600秒超时，可用 `--timeout 1800` 对慢机器增加时限。所有结果留在输出目录；失败后不要在该目录原地重跑，选择新目录，保留失败现场。程序会记录失败到run.json；启动前输入校验失败可能没有输出目录。

正常输出包括：P1—P6每个结果目录、mesh目录、run.json、summary.json、comparison.csv、两种报告、SHA256SUMS。正常进程退出0。超差或不满足会写出报告并以非零码退出，报告呈现实际未通过项。

执行日志必须同时检查：

1. 求解器退出0且出现 `Job finished`。
2. `solver.log` 中没有 `*ERROR`。
3. `job.sta` 最后一行P1是step1/time1，其余是step2/time2，各步最终局部时间1。
4. DAT最后的位移与应力输出时间相同并匹配总分析时间。
5. 1125个原始节点U，1123个索杆×8积分点S。
6. 所有数值有限，UY量级接近零，索力为正，参考比较和报告安全系数均满足。

## 集成到AI助手

将**整个文件夹**放到助手已支持的skills目录，例如BridgeMind程序根目录的 `skills/catwalk-static-review/`，保留相对结构。是否自动发现以宿主实现为准；本包不擅自修改其 `experts.yaml` 结构，也不假定有注册API。让助手读取SKILL.md后，先执行 `--verify-only`，再实跑。

不要把脚本静态输出、此前聊天结论或examples当作这一次执行。无需把API密钥写进此Skill，不依赖豆包/GLM特定账号。LLM负责调用工具和解释证据，求解数值由CalculiX产生。

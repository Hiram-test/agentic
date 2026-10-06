---
name: catwalk-static-review
description: 对张靖皋猫道及门架承重索的固定版本 P1–P6 INP 进行完整静力复算；核验材料、截面、初应力、荷载和边界，调用 Gmsh 校验一维网格，运行 CalculiX，输出云图、VTU、Word/PDF 报告和可追溯证据。适用于本包六工况二维整体索系，不用于抖振、C0–C5 三维系列或局部构件验算。
---

# 猫道及门架承重索静力复核：端到端执行 Skill

## 0. 目标、范围及必须遵守的规则

使用本包**已经核对版本与来源**的六份 INP，从输入核验一直运行到可阅读的 Word/PDF 计算报告。默认必须实际求解六个工况，不得用报告中的参考数值填充“计算结果”，不得只给方案或伪造截图。用户已明确不需要转索鞍、锚固等局部构件，报告不生成这些章节或占位任务。

当前对象是猫道承重索、门架承重索及其整体等效连接杆：1125 节点、1194 单元，二维 X–Z 模型，全部 UY=0。工程本体有双幅及横向通道，但本 INP 不能据此变成三维模型。P5 的含义是“恒载+最大阵风”静力组合，不能自动等同名为 C05 或 C0–C5 的其他试验系列。

**先执行、再下结论**。允许失败并保留错误证据，不允许把失败输出描述为“已通过”。不要以退出码 0 为唯一完成条件。不要为了拟合参考结果修改材料密度、截面、边界或初应力。

### 来源优先级

1. 本包 `assets/integrity.json`、`assets/reference/manifest.json` 锁定的输入及原PDF。
2. INP 卡片中的实际数值、节点号、单元连接与分析步。
3. 原 PDF 第11页表1-7、第30页表1-11、第39页表1-14；位移另用已注明来源的 MAPDL 基准。
4. 说明文档和历史结果。与上面冲突时先记录差异，不要悄悄覆盖输入。

同名旧版 `model/catwalk-fem/eval/formfind_974211b2/daughters/migrate_P*.inp` 不是本任务输入。旧版第二步覆盖恒载会得到错误线形；本包新版已经保留恒载。**绝对不要再对本包第二步加一次第一步 CLOAD**，否则重复计载。

## 1. 按需读取的文件

首次执行，依次阅读：

1. [安装、文件契约与一键执行](references/01-execution.md)
2. [材料、截面、初应力与单位](references/02-materials-model.md)
3. [Gmsh 调用、编号映射及加密网格边界](references/03-gmsh.md)
4. [分析步、荷载、温度与支承](references/04-steps-loads-boundaries.md)
5. [结果校验、索力恢复与云图](references/05-postprocessing.md)
6. [原报告格式与自动报告规则](references/06-report.md)
7. [失败诊断与回归验收](references/07-troubleshooting.md)

输入数值的机器可读明细见 `assets/reference/P1_input_audit.json` 至 `P6_input_audit.json`。不要让语言模型手工抄写 8984 条初始应力或上千条荷载。

## 2. 快速执行：完整路径

先以实际 Skill 所在位置确定 `SKILL_ROOT`，不能假设当前工作目录就是 Skill 目录。脚本通过自身路径定位资产，不依赖原作者的 `/workspace` 或 model 仓库。

Linux/macOS 风格的 Shell 示意（自动下载求解器仅支持 Linux x86_64）：

```bash
SKILL_ROOT=/absolute/path/to/catwalk-static-review
python3 -m venv "$SKILL_ROOT/.venv"
"$SKILL_ROOT/.venv/bin/python" -m pip install -r "$SKILL_ROOT/requirements.txt"
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --verify-only
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" --out /absolute/path/to/new-run
```

已有锁定求解器时：

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run.py" \
  --solver /absolute/path/to/ccx \
  --out /absolute/path/to/new-run
```

Windows 路径、替代求解器、依赖、报错处理详见 01-execution。输出目录必须不存在或为空，禁止覆盖已有计算。

程序依次执行：

1. 核验所有资产 SHA256，确认六份 INP 原件；读取完整卡片并对比数值审计快照。
2. 确认六工况几何、单元、截面、初应力和边界完全一致。
3. 用 Gmsh 实际建立原始点、直线，`setTransfiniteCurve(eid, 2)` 后 `generate(1)`，生成 `.msh`、`.geo_unrolled` 与编号映射，检验连接完全一致。
4. 保留原 INP 卡片不变，将每工况复制为独立目录的 `job.inp`。运行 CalculiX，单线程，默认单工况超时600秒。
5. 验证收敛、末步时间、节点/积分点完整性和有限数值；读取末步 U、S。
6. 恢复索力，输出节点与单元CSV、VTU、位移/索力/应力线单元云图。
7. 计算与参考值的差异、索束安全系数、正拉力检查，生成有实际数据的 Word/PDF。
8. 写 `run.json`、汇总 CSV/JSON、输出文件 SHA256 清单。最后给用户报告和数据包链接。

## 3. 必须区分的三种“通过”

- **数值执行完成**：求解器结束、所有预期分析步完成、末步数据完整、没有错误或 NaN。
- **回归一致**：位移峰值节点与基准一致；USUM误差≤1%；各跨度索力误差≤1.5%。这是本流程数值对照阈值，**不是规范允许误差**。
- **报告口径强度满足**：猫道索束破断力38080 kN、门架索束14280 kN，按 `K=Nbreak/Nmax`；要求P1≥3.2、P2/P3/P4/P6≥2.7、P5≥2.5。必须使用本次计算的 Nmax。

不把这三者混为“全部工程通过”。未输出反力平衡就写清楚未核查；本原件没有 RF 输出。工况6的原PDF部分正文写2.5，表1-7写2.7，本流程取2.7并说明。

## 4. 关键阻断条件

下面任何一项发生，保留已生成日志，停止生成“通过”结论：

- INP或参考数据哈希不符；1125节点/1194单元/8984初应力记录不符。
- 新增了支持外文件、未知单元类型或本解析器不支持的卡片语义；不能把当前专用解析器当通用 INP 解析器。
- Gmsh 连通性或坐标不一致；出现节点合并、丢失原节点号或二阶单元。
- 求解器不符合版本策略且没有显式选择替代求解器试算。
- 出现 `*ERROR`、未 `Job finished`、未达到末步时间或结果不完整。
- U/S来自不同步；把第一步输出当作P2—P6最终组合输出。
- 索力为零或负值；这提示杆模型与真实只受拉索的相容性需要复查。
- 回归值或安全系数未达到要求；不得隐去失败的工况继续给整体通过结论。

## 5. 交付物与最终回答

必须交付：`catwalk_static_review.pdf`、`.docx`、`comparison.csv`、`summary.json`、`run.json`、`SHA256SUMS`，以及可获取的P1—P6输入、求解日志、DAT/FRD/STA、CSV、VTU、PNG和Gmsh映射。

最终回答先说实际运行了哪些工况，再给位移/底索/门架索三项最大差、是否存在不满足项、报告链接和二维适用范围。没有实际执行则明确说“Skill 已编写，尚未实跑”，不能套用本包示例结果。

## 6. 扩展与变更

本 Skill 默认 **原件复算**，不是自动优化/校准工具。需要新网格、新截面、新荷载或三维模型时，另建派生输入和新的来源清单；保留原基准。Gmsh 的 `--subdivisions 2` 可生成候选加密网格，但不自动迁移初应力、节点荷载、边界或输出分析 INP；不得将它作为已完成的加密求解。转换工作清单和验证要求见 03-gmsh。

## 7. 报告字体与样式是固定要求

严格使用 `report_style.py` 和 `assets/reference/report_style.json`，宋体正文12磅、黑体标题、Times New Roman数字、白底细线四跨验算表。字体文件随包携带并嵌入PDF/Word；不得退回STSong-Light、通用无衬线字体或自创彩色报告模板。详见06-report。

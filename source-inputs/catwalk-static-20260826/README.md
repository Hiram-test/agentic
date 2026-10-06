# 猫道六工况静力输入（已核对版本）

本目录是 agentic 中本次猫道静力复核的固定入口。请使用 `inputs/migrate_P1.inp` 至 `migrate_P6.inp`，先用 `sha256sum -c SHA256SUMS` 核对，避免仅凭同名文件选错版本。

## 来源与版本区别

P2–P6 来自 Hiram-test/model 的 `feat/catwalk-ccx-20260826` 分支，固定提交 `ebd0e3d8eea740de6d2d4539feda51885d80e3f8`，原路径 `source-inputs/zjg-catwalk-ccx-20260826/cases_vs_ansys_974211b2/ccx_run/P*/migrate_P*.inp`。P1 是配套 COMPARE.json 锁定的恒载输入。逐文件来源及哈希见 manifest.json。六份输入保持复算原件字节不变。

**不要替换为旧目录 `catwalk-fem/eval/formfind_974211b2/daughters/` 中的同名 P2–P6 文件。** 旧版第二步荷载覆盖问题不适用于本目录归档版；归档版第二步保留二期恒载并叠加工况荷载。

## 2026-10-06 复核

- 六工况均实际求解完成，使用 CalculiX 2.23 FT14，原输入未修改。
- 对既有二维 MCT 独立 MAPDL 位移基准，峰值节点一致，最大位移相对差绝对值小于 0.87%。
- 对复核报告表 1-11、1-14：底索最大差 0.854%，门架承重索最大差 1.126%。报告依据是归档提取文本。
- P5 最大总位移 1325.314 mm，节点 306，竖向位移 -1325.275 mm；不是旧版的上抬 3059 mm。
- 首步默认步长警告；P3/P6 另有 N_THERM 集合上限截断警告，详见日志。

本组是约束全部 UY 的二维 MCT 等效模型；不能用本组结果代替双幅、完整三维或 C0–C5 系列验证，也不能仅因名称相似把用户所说 C05 等同 P5。

## 文件

- `inputs/`：六份可直接提交求解的 INP。
- `COMPARE.json`：来源归档的原配套对照表，保持原样；其中历史求解数据与本次复算数据分开保存。
- `review/review.txt`、`comparison.csv`、`results.json`、`report_comparison.json`：本次复核说明和数据。
- `review/review_report_text.txt`：复核报告归档提取文本。
- `review/catwalk-archive-original-review.zip`：完整本次输入、求解输出和日志。压缩包保留归档时原始说明与脚本；脚本中的 /workspace 路径属于原复算环境，移机需调整。包内“未推送 GitHub”为打包时状态，以本目录说明为准。

运行示例（需安装兼容 CalculiX）：将某份 INP 复制到独立工作目录为 job.inp，然后 `OMP_NUM_THREADS=1 ccx -i job`。本次求解器 SHA256：`b498dad80b0415d53ab112409adc85b8a1fd19eb7846dc31e778f4c83b437a0e`。

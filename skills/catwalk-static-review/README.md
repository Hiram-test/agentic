# 猫道静力复核 Skill

入口：[SKILL.md](SKILL.md)。本包包括详细执行指令、7份专题文档、独立Python脚本、六份已核验INP、原始118页报告PDF和机器可读基准。

**已实跑验证**：Gmsh生成1125节点/1194线单元，坐标与连接关系完全一致；CalculiX完成P1—P6；位移最大差0.860%，底索最大差0.854%，门架索最大差1.126%。这些是随包示例运行结果，不替代下一次运行。

示例：[17页PDF](examples/catwalk_static_review.pdf) / [Word](examples/catwalk_static_review.docx) / [完整运行证据ZIP](examples/validated-run.zip)。报告仅包含猫道及门架承重索整体静力，不含用户已排除的局部构件章节。

```bash
python -m pip install -r requirements.txt
python scripts/run.py --verify-only
python scripts/run.py --out /absolute/path/to/new-run
```

自动下载求解器仅支持Linux x86_64；离线及Windows执行详见[执行文档](references/01-execution.md)。目录可以整体复制，脚本不依赖外部model仓库。

测试：`python -m unittest discover -s tests -v`。只重新排版已有完成结果：`python scripts/rebuild_report.py --run /path/to/completed-run`。

本版默认保留原件计算，不更改网格或物理定义以拟合结果。Gmsh加密选项只输出候选网格，尚未包含新网格的物理卡片迁移，见[网格文档](references/03-gmsh.md)。

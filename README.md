# agentic

## 猫道静力复核

已核对的六工况 INP、配套对照表与计算结果统一放在 [猫道静力固定入口](source-inputs/catwalk-static-20260826/README.md)。后续复核请从此处读取，并核验 SHA256SUMS；不要混用 model 仓库旧版同名 INP。

程序发行附件见本仓库 Releases。

## 完整静力复核 Skill

[详细 Skill 与一键运行脚本](skills/catwalk-static-review/README.md)：含材料、初应力、Gmsh、荷载边界、求解、云图与 Word/PDF 报告生成；随包附原始报告PDF及已实跑的六工况示例。

## 英文 Skill 与 SCI 论文框架

[英文 Skill v1.3.0](skills/catwalk-static-review/SKILL.md) 已包含完整英文执行说明；工程报告保留原定中文字体与版式。

[论文工作目录](papers/agentic-fea-framework/README.md) 包含 FeaGPT 原文、五张图逐图学习、三张表与算法对应关系、英文 SCI 论文框架（Word/PDF/LaTeX），以及由六工况真实结果生成的四联对比图。

[读图与输入核对的三个英文版本](skills/catwalk-static-review/README.md#drawing-to-model-input-readback-v130)：按 6 个阶段、18 个操作、36 个细步骤组织，使用相同构件范围及 8 张固定输入表。
